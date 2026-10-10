"""HTTP acceptance with synthetic users, real SQLite and disposable media only."""

import importlib.util
import json
import os
from pathlib import Path
import sys
import unittest
from datetime import datetime
from unittest.mock import patch
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
from app import auth, models, scanner
from app.assistant import identity, internal_app, sessions, scan_jobs
from app.assistant.models import AssistantRun, AssistantAudit
from app.routers import assistant, auth as auth_router
from tests.assistant_fixtures import assistant_fixture, business_snapshot
from tests.test_assistant_sse import StreamFake


class AssistantHTTPAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.f = assistant_fixture(self)
        old = self.f.db.get(AssistantRun, self.f.rid)
        old.status = "completed"
        old.executor_exited_at = datetime.utcnow()
        for uid in (1, 2):
            self.f.db.get(models.User, uid).password_hash = auth.hash_password(
                "synthetic-password"
            )
        media_root = self.f.root / "disposable-media"
        media_root.mkdir()
        Image.new("RGB", (32, 32), "blue").save(media_root / "acceptance.png")
        self.f.db.get(models.Folder, 1).path = str(media_root)
        self.f.db.get(models.Folder, 1).scan_mode = "image"
        self.f.db.commit()
        model = {
            "provider": "custom:he-model",
            "model": "deepseek-flash",
            "base_url": "https://api.deepseek.com/v1",
            "api_key": "synthetic-model-key",
            "extra_body": {},
        }
        self.patches = [
            patch.object(identity.config, "load_model", return_value=model),
            patch.object(sessions.database, "SessionLocal", self.f.factory),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)
        self.bindings = {
            uid: identity.prepare_profile(self.f.db, uid) for uid in (1, 2)
        }
        self.tokens = {}
        app = FastAPI()
        app.include_router(auth_router.router)
        app.include_router(assistant.router)

        def db_dependency():
            with self.f.factory() as db:
                yield db

        app.dependency_overrides[assistant.get_db] = db_dependency
        internal_app.app.dependency_overrides[internal_app.get_db] = db_dependency
        self.addCleanup(internal_app.app.dependency_overrides.clear)
        self.public = TestClient(app)
        self.private = TestClient(internal_app.app)
        self.addCleanup(self.public.close)
        self.addCleanup(self.private.close)
        for uid in (1, 2):
            response = self.public.post(
                "/auth/login",
                json={
                    "username": "test-admin-" + str(uid),
                    "password": "synthetic-password",
                },
            )
            self.assertEqual(response.status_code, 200, response.text)
            self.tokens[uid] = response.json()["access_token"]
        self.fake = StreamFake([])
        transport = patch.object(sessions, "get_client", return_value=self.fake)
        transport.start()
        self.addCleanup(transport.stop)
        created = self.public.post(
            "/assistant/sessions", headers=self.headers(), json={"title": "验收"}
        )
        self.assertEqual(created.status_code, 200, created.text)
        self.sid = created.json()["id"]
        cid = str(uuid4())
        response = self.public.post(
            "/assistant/sessions/" + self.sid + "/runs",
            headers=self.headers(),
            json={"input": "搜索并提出建议", "client_request_id": cid},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.run = response.json()
        self.context = {"session_id": self.sid, "run_id": self.run["id"]}
        env = identity._read_env(self.f.root / "hermes/profiles/he-user-1/.env")
        self.tool_token = env["HE_TOOL_TOKEN"]
        self.env_a = env
        self.env_b = identity._read_env(self.f.root / "hermes/profiles/he-user-2/.env")

    def headers(self, uid=1):
        return {"Authorization": "Bearer " + self.tokens[uid]}

    def tool(self, name, args):
        response = self.private.post(
            "/tools/" + name,
            headers={"Authorization": "Bearer " + self.tool_token},
            json={"context": self.context, "args": args},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["result"]

    def preview(self, proposal):
        response = self.public.get(
            "/assistant/proposals/" + proposal["id"], headers=self.headers()
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def confirm(self, proposal):
        preview = self.preview(proposal)
        return self.public.post(
            "/assistant/proposals/" + proposal["id"] + "/confirm",
            headers=self.headers(),
            json={"payload_hash": preview["payload_hash"]},
        )

    def test_login_search_propose_reject_confirm_repeat_stream_restore_clear(self):
        before = business_snapshot(self.f.engine)
        found = self.tool("search_media", {"query": "温馨"})
        self.assertEqual(found["items"][0]["id"], 1)
        proposal = self.tool(
            "propose_media_update", {"media_id": 1, "patch": {"rating": 5}}
        )
        self.assertEqual(business_snapshot(self.f.engine), before)
        rejected = self.public.post(
            "/assistant/proposals/" + proposal["id"] + "/reject", headers=self.headers()
        )
        self.assertEqual(rejected.status_code, 200)
        self.assertEqual(rejected.json()["state"], "rejected")
        proposal = self.tool(
            "propose_media_update", {"media_id": 1, "patch": {"rating": 2}}
        )
        self.assertEqual(business_snapshot(self.f.engine), before)
        first = self.confirm(proposal)
        again = self.confirm(proposal)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json(), again.json())
        self.f.db.expire_all()
        self.assertEqual(self.f.db.get(models.Media, 1).rating, 2)
        self.assertEqual(self.f.db.query(AssistantAudit).count(), 1)
        self.fake.events = [
            {
                "event": "message.delta",
                "seq": 1,
                "run_id": self.fake.state["run_id"],
                "delta": "半截",
            },
            {
                "event": "run.completed",
                "seq": 2,
                "run_id": self.fake.state["run_id"],
                "output": "权威最终回复",
                "usage": {"input_tokens": 2, "output_tokens": 3, "total_tokens": 5},
            },
        ]
        stream = self.public.get(
            "/assistant/runs/" + self.run["id"] + "/events", headers=self.headers()
        )
        self.assertEqual(stream.status_code, 200, stream.text)
        self.assertIn("权威最终回复", stream.text)
        status = self.public.get(
            "/assistant/runs/" + self.run["id"], headers=self.headers()
        ).json()
        self.assertEqual(status["status"], "completed")
        history = self.public.get(
            "/assistant/sessions/" + self.sid + "/messages", headers=self.headers()
        ).json()
        finals = [m for m in history["items"] if m["role"] == "assistant"]
        self.assertEqual(len(finals), 1)
        self.assertEqual(finals[0]["content"], "权威最终回复")
        result = self.public.get(
            "/assistant/runs/" + self.run["id"] + "/results", headers=self.headers()
        ).json()
        self.assertEqual(result["items"][0]["tool_name"], "search_media")
        clear = self.public.delete(
            "/assistant/sessions/" + self.sid, headers=self.headers()
        )
        self.assertEqual(clear.status_code, 200, clear.text)
        self.assertEqual(clear.json()["state"], "cleared")
        self.assertEqual(
            self.public.get(
                "/assistant/sessions/" + self.sid + "/messages", headers=self.headers()
            ).json()["items"],
            [],
        )
        self.assertTrue((self.f.root / "hermes/profiles/he-user-1/.env").exists())

    def test_profile_and_http_ownership_tool_user_tokens_are_separate(self):
        self.assertNotEqual(self.env_a["API_SERVER_KEY"], self.env_b["API_SERVER_KEY"])
        self.assertNotEqual(self.env_a["HE_TOOL_TOKEN"], self.env_b["HE_TOOL_TOKEN"])
        proposal = self.tool(
            "propose_media_update", {"media_id": 1, "patch": {"rating": 5}}
        )
        paths = [
            "/assistant/runs/" + self.run["id"],
            "/assistant/runs/" + self.run["id"] + "/results",
            "/assistant/sessions/" + self.sid + "/messages",
            "/assistant/proposals/" + proposal["id"],
        ]
        for path in paths:
            self.assertEqual(
                self.public.get(path, headers=self.headers(2)).status_code, 404, path
            )
        preview = self.preview(proposal)
        for token in (self.tool_token, self.env_a["API_SERVER_KEY"]):
            response = self.public.post(
                "/assistant/proposals/" + proposal["id"] + "/confirm",
                headers={"Authorization": "Bearer " + token},
                json={"payload_hash": preview["payload_hash"]},
            )
            self.assertEqual(response.status_code, 401)
        self.assertEqual(
            self.public.get(
                "/assistant/runs/" + self.run["id"] + "?token=" + self.tokens[1]
            ).status_code,
            401,
        )
        denied = self.private.post(
            "/tools/search_media",
            headers=self.headers(),
            json={"context": self.context, "args": {}},
        )
        self.assertEqual(denied.status_code, 401)
        self.f.db.get(models.User, 1).is_admin = False
        self.f.db.commit()
        self.assertEqual(
            self.public.get(paths[0], headers=self.headers()).status_code, 403
        )
        denied = self.private.post(
            "/tools/search_media",
            headers={"Authorization": "Bearer " + self.tool_token},
            json={"context": self.context, "args": {}},
        )
        self.assertEqual(denied.status_code, 403)

    def test_real_temporary_image_scan_and_restart_never_replay_job(self):
        proposal = self.tool("propose_scan", {"folder_id": 1})
        self.assertEqual(self.f.db.query(models.BackgroundJob).count(), 0)
        queued = []
        with patch.object(
            scan_jobs, "enqueue_scan_job", side_effect=lambda *args: queued.append(args)
        ):
            first = self.confirm(proposal)
            again = self.confirm(proposal)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json(), again.json())
        self.assertEqual(len(queued), 1)
        scan_jobs.run_scan_job(*queued[0])
        self.f.db.expire_all()
        job_id = first.json()["job_id"]
        job = self.public.get(
            "/assistant/jobs/" + job_id, headers=self.headers()
        ).json()
        self.assertEqual(job["status"], "completed", job)
        found = (
            self.f.db.query(models.Media)
            .filter(
                models.Media.absolute_path
                == str(self.f.root / "disposable-media/acceptance.png")
            )
            .first()
        )
        self.assertIsNotNone(found)
        self.assertEqual(
            self.public.get(
                "/assistant/jobs/" + job_id, headers=self.headers(2)
            ).status_code,
            404,
        )
        with patch.object(
            scanner, "scan_folder", side_effect=AssertionError("must not replay")
        ):
            self.assertEqual(scan_jobs.recover_scan_jobs(), 0)
        self.assertEqual(self.f.db.query(AssistantAudit).count(), 1)


class AcceptanceRunnerConfigurationTests(unittest.TestCase):
    def test_runner_requires_private_bounded_config_and_rejects_unknown_fields(self):
        path = (
            Path(__file__).resolve().parents[2] / "scripts/run_assistant_acceptance.py"
        )
        if not path.exists():
            self.fail("acceptance runner is missing")
        spec = importlib.util.spec_from_file_location("acceptance_runner", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.json"
            config.write_text(json.dumps({"mode": "offline"}))
            config.chmod(0o600)
            self.assertEqual(module.load_config(config), {"mode": "offline"})
            config.write_text(
                json.dumps({"mode": "offline", "command": "arbitrary shell"})
            )
            with self.assertRaises(ValueError):
                module.load_config(config)
            config.write_text(json.dumps({"mode": "offline"}))
            config.chmod(0o644)
            if os.name != "nt":
                with self.assertRaises(ValueError):
                    module.load_config(config)


class AssistantDeploymentContractTests(unittest.TestCase):
    def test_compose_is_optional_internal_bounded_and_masks_non_database_data(self):
        import yaml

        root = Path(__file__).resolve().parents[2]
        path = root / "docker-compose.assistant.yml"
        self.assertTrue(path.exists(), "assistant compose is missing")
        config = yaml.safe_load(path.read_text())
        services = config["services"]
        self.assertEqual(
            set(services),
            {"backend", "assistant-tools", "assistant-mcp", "hermes-agent"},
        )
        self.assertNotIn("depends_on", services["backend"])
        self.assertEqual(
            services["backend"]["environment"]["HE_HERMES_URL"],
            "http://hermes-agent:8642",
        )
        self.assertEqual(
            set(services["backend"]["networks"]), {"default", "assistant_internal"}
        )
        self.assertTrue(config["networks"]["assistant_internal"]["internal"])
        self.assertNotIn("internal", config["networks"]["assistant_egress"])
        for name in ("assistant-tools", "assistant-mcp", "hermes-agent"):
            service = services[name]
            self.assertNotIn("ports", service)
            self.assertFalse(service.get("privileged", False))
            self.assertIn("no-new-privileges:true", service["security_opt"])
            self.assertIn("healthcheck", service)
            self.assertIn("mem_limit", service)
            self.assertIn("cpus", service)
            self.assertIn("pids_limit", service)
            self.assertTrue(
                all(value.startswith("/") for value in service.get("tmpfs", []))
            )
            self.assertNotIn("docker.sock", json.dumps(service))
        self.assertEqual(
            set(services["assistant-tools"]["networks"]), {"assistant_internal"}
        )
        self.assertEqual(
            set(services["assistant-mcp"]["networks"]), {"assistant_internal"}
        )
        self.assertEqual(
            set(services["hermes-agent"]["networks"]),
            {"assistant_internal", "assistant_egress"},
        )
        self.assertNotIn("volumes", services["assistant-mcp"])
        self.assertEqual(services["assistant-tools"]["user"], "1000:1000")
        masks = {
            v["target"]
            for v in services["assistant-tools"]["volumes"]
            if v.get("read_only")
        }
        for name in (
            "assistant",
            "hermes",
            "backups",
            "deepseek.json",
            "external_config.json",
            "pawchive_stream.key",
            "library.db.backup-pre-5ee4ac3",
            "he-manager.db",
            "media.db",
        ):
            self.assertIn("/data/" + name, masks)
        for key in services["assistant-tools"]["environment"]:
            self.assertFalse(
                any(word in key.upper() for word in ("SECRET", "TOKEN", "API_KEY"))
            )
        self.assertIn(
            "internal_app:app", " ".join(services["assistant-tools"]["command"])
        )

    def test_gateway_bootstrap_has_no_default_he_tools_or_shared_credentials(self):
        import tempfile

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "hermes"
            self.assertTrue(
                hasattr(identity, "prepare_gateway_root"),
                "gateway bootstrap is missing",
            )
            identity.prepare_gateway_root(root)
            env = identity._read_env(root / ".env")
            self.assertGreaterEqual(len(env["API_SERVER_KEY"]), 32)
            self.assertNotIn("HE_TOOL_TOKEN", env)
            self.assertNotIn("HE_ASSISTANT_MODEL_KEY", env)
            before = (root / ".env").read_bytes()
            identity.prepare_gateway_root(root)
            self.assertEqual((root / ".env").read_bytes(), before)
            import yaml

            cfg = yaml.safe_load((root / "config.yaml").read_text())
            self.assertEqual(cfg["platform_toolsets"]["api_server"], [])
            self.assertEqual(cfg.get("mcp_servers", {}), {})
            self.assertTrue(cfg["gateway"]["multiplex_profiles"])
            self.assertFalse(cfg["gateway"]["auto_multiplex_migration"])

    def test_deployment_inventory_fails_closed_on_new_files_and_symlinked_database(
        self,
    ):
        import tempfile

        path = (
            Path(__file__).resolve().parents[2]
            / "scripts/check_assistant_deployment.py"
        )
        self.assertTrue(path.exists(), "deployment inventory checker is missing")
        spec = importlib.util.spec_from_file_location("deployment_checker", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "library.db").write_bytes(b"fixture")
            (root / "assistant").mkdir()
            module.validate_inventory(root, {"assistant"})
            (root / "new-secret.json").write_text("synthetic secret")
            with self.assertRaises(ValueError):
                module.validate_inventory(root, {"assistant"})
            (root / "new-secret.json").unlink()
            if os.name == "nt":
                # Windows need not grant the test process symlink privilege.
                with patch.object(Path, "is_symlink", lambda p: p.name == "library.db"):
                    with self.assertRaises(ValueError):
                        module.validate_inventory(root, {"assistant"})
            else:
                (root / "library.db").unlink()
                (root / "library.db").symlink_to(root / "outside-secret")
                with self.assertRaises(ValueError):
                    module.validate_inventory(root, {"assistant"})
