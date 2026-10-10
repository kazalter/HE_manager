import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app import auth, models as he_models


class AssistantIdentityTests(unittest.TestCase):
    def setUp(self):
        try:
            self.identity = importlib.import_module("app.assistant.identity")
            self.models = importlib.import_module("app.assistant.models")
            self.schemas = importlib.import_module("app.assistant.schemas")
            self.config = importlib.import_module("app.assistant.config")
        except ModuleNotFoundError:
            self.fail("Assistant identity is not implemented")
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.engine = create_engine("sqlite:///" + str(self.root / "test.db"))
        he_models.Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.db.add_all(
            [
                he_models.User(
                    id=i,
                    username="admin" + str(i),
                    password_hash="unused",
                    is_admin=True,
                    is_active=True,
                )
                for i in (1, 2)
            ]
        )
        self.token = "synthetic_tool_token_" + ("a" * 40)
        self.binding = self.models.AssistantToolIdentity(
            user_id=1,
            profile_name="he-user-1",
            tool_token_hash=self.identity.hash_tool_token(self.token),
            credential_generation=1,
            enabled=True,
        )
        self.db.add(self.binding)
        self.sid = str(uuid4())
        self.rid = str(uuid4())
        self.db.add(
            self.models.AssistantSession(
                id=self.sid,
                user_id=1,
                upstream_session_id="he-" + self.sid,
                state="active",
                title="Synthetic",
            )
        )
        self.db.add(
            self.models.AssistantRun(
                id=self.rid,
                user_id=1,
                session_id=self.sid,
                client_request_id=str(uuid4()),
                input_hash="hash",
                status="running",
                api_key_generation=1,
            )
        )
        self.db.commit()
        self.env = patch.dict(
            os.environ,
            {
                "HE_ASSISTANT_ENABLED": "1",
                "HE_ASSISTANT_DATA_DIR": str(self.root / "assistant"),
            },
        )
        self.env.start()
        # unittest runs cleanup callbacks in reverse registration order.
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.db.close)
        self.addCleanup(self.env.stop)

    def context(self):
        return self.schemas.ToolContext(session_id=self.sid, run_id=self.rid)

    def test_tool_auth_uses_hash_table_without_private_configuration(self):
        self.assertFalse((self.root / "assistant").exists())
        principal = self.identity.authenticate_tool_token(self.db, self.token)
        self.assertEqual(principal.user_id, 1)
        self.assertEqual(
            self.identity.require_tool_context(self.db, principal, self.context()).id,
            self.rid,
        )

    def test_rotated_token_and_inactive_binding_fail_closed(self):
        self.binding.tool_token_hash = self.identity.hash_tool_token(
            "replacement_" + ("b" * 40)
        )
        self.db.commit()
        with self.assertRaises(HTTPException) as caught:
            self.identity.authenticate_tool_token(self.db, self.token)
        self.assertEqual(caught.exception.status_code, 401)
        self.binding.enabled = False
        self.db.commit()
        with self.assertRaises(HTTPException):
            self.identity.authenticate_tool_token(self.db, "replacement_" + ("b" * 40))

    def test_tool_token_is_not_a_public_user_token(self):
        with self.assertRaises(HTTPException) as caught:
            auth.authenticate_access_token(self.db, self.token)
        self.assertEqual(caught.exception.status_code, 401)

    def test_user_demotion_and_deactivation_close_tool_access(self):
        user = self.db.get(he_models.User, 1)
        for field in ("is_admin", "is_active"):
            setattr(user, field, False)
            self.db.commit()
            with self.assertRaises(HTTPException):
                self.identity.authenticate_tool_token(self.db, self.token)
            setattr(user, field, True)
            self.db.commit()

    def test_stopped_run_and_clearing_session_reject_late_context(self):
        principal = self.identity.authenticate_tool_token(self.db, self.token)
        run = self.db.get(self.models.AssistantRun, self.rid)
        for state in ("stopping", "completed", "submission_unknown", "reconciling"):
            run.status = state
            self.db.commit()
            with self.assertRaises(HTTPException):
                self.identity.require_tool_context(self.db, principal, self.context())
        run.status = "running"
        session = self.db.get(self.models.AssistantSession, self.sid)
        session.state = "deleting"
        self.db.commit()
        with self.assertRaises(HTTPException):
            self.identity.require_tool_context(self.db, principal, self.context())

    def test_token_generation_mismatch_rejects_old_run(self):
        principal = self.identity.authenticate_tool_token(self.db, self.token)
        self.binding.credential_generation = 2
        self.db.commit()
        with self.assertRaises(HTTPException):
            self.identity.require_tool_context(self.db, principal, self.context())

    def test_other_principal_cannot_select_run_by_context(self):
        principal = self.schemas.ToolPrincipal(user_id=2, profile_name="he-user-2")
        with self.assertRaises(HTTPException) as caught:
            self.identity.require_tool_context(self.db, principal, self.context())
        self.assertEqual(caught.exception.status_code, 404)

    def test_feature_off_blocks_tool_authentication(self):
        with patch.dict(os.environ, {"HE_ASSISTANT_ENABLED": "0"}):
            with self.assertRaises(HTTPException):
                self.identity.authenticate_tool_token(self.db, self.token)

    def test_stop_timestamp_blocks_tools_even_if_upstream_completed_race_is_delayed(
        self,
    ):
        from datetime import datetime

        principal = self.identity.authenticate_tool_token(self.db, self.token)
        row = self.db.get(self.models.AssistantRun, self.rid)
        row.stop_requested_at = datetime.utcnow()
        self.db.commit()
        with self.assertRaises(HTTPException):
            self.identity.require_tool_context(self.db, principal, self.context())

    def test_expired_deadline_blocks_late_tools(self):
        from datetime import datetime, timedelta

        principal = self.identity.authenticate_tool_token(self.db, self.token)
        row = self.db.get(self.models.AssistantRun, self.rid)
        row.deadline_at = datetime.utcnow() - timedelta(seconds=1)
        self.db.commit()
        with self.assertRaises(HTTPException):
            self.identity.require_tool_context(self.db, principal, self.context())

    def test_world_readable_profile_registry_fails_closed(self):
        path = self.root / "assistant/profiles.json"
        path.parent.mkdir(mode=0o700)
        path.write_text('{"profiles":{}}')
        path.chmod(0o644)
        with self.assertRaises(HTTPException):
            self.config.get_profile(1)

    def test_missing_model_configuration_does_not_create_profile_files(self):
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": ""}):
            with self.assertRaises(HTTPException):
                self.identity.prepare_profile(
                    self.db, 1, profile_root=self.root / "hermes"
                )
        self.assertFalse((self.root / "hermes").exists())

    def test_missing_profile_never_falls_back_to_default(self):
        with self.assertRaises(HTTPException) as caught:
            self.config.get_profile(1)
        self.assertEqual(caught.exception.detail, "assistant_unconfigured")

    def test_preparation_cli_runs_in_image_layout_and_sanitizes_output(self):
        import shutil, subprocess, sys

        repo = Path(__file__).resolve().parents[2]
        image = self.root / "image"
        image.mkdir()
        shutil.copytree(
            repo / "backend/app",
            image / "app",
            ignore=shutil.ignore_patterns(
                "__pycache__", "*.db", "*.db-wal", "*.db-shm"
            ),
        )
        shutil.copytree(repo / "deploy/hermes", image / "deploy/hermes")
        (image / "scripts").mkdir()
        shutil.copyfile(
            repo / "scripts/prepare_hermes.py", image / "scripts/prepare_hermes.py"
        )
        model_path = self.root / "assistant/hermes-model.json"
        model_path.parent.mkdir(mode=0o700)
        key = "synthetic_cli_key_" + ("e" * 40)
        model_path.write_text(
            json.dumps(
                {
                    "model": "fixture-model",
                    "base_url": "https://model.example/v1",
                    "api_key": key,
                }
            )
        )
        model_path.chmod(0o600)
        environment = dict(
            os.environ, HE_DATABASE_URL="sqlite:///" + str(self.root / "test.db")
        )
        environment.pop("PYTHONPATH", None)
        result = subprocess.run(
            [
                sys.executable,
                str(image / "scripts/prepare_hermes.py"),
                "--user-id",
                "2",
                "--profile-root",
                str(image / "hermes"),
            ],
            cwd=image,
            env=environment,
            text=True,
            capture_output=True,
            timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "PASS profile_prepared he-user-2")
        self.assertNotIn(key, result.stdout + result.stderr)
        self.assertTrue((image / "hermes/profiles/he-user-2/config.yaml").is_file())

    def test_runtime_template_directory_is_used_outside_repository_layout(self):
        from datetime import datetime

        run = self.db.get(self.models.AssistantRun, self.rid)
        run.executor_exited_at = datetime.utcnow()
        run.status = "completed"
        self.db.commit()
        model_path = self.root / "assistant/hermes-model.json"
        model_path.parent.mkdir(mode=0o700)
        model_path.write_text(
            json.dumps(
                {
                    "model": "fixture-model",
                    "base_url": "https://model.example/v1",
                    "api_key": "synthetic_" + ("d" * 40),
                }
            )
        )
        model_path.chmod(0o600)
        templates = self.root / "image-templates"
        templates.mkdir()
        source = (
            Path(__file__).resolve().parents[2] / "deploy/hermes/config.example.yaml"
        )
        (templates / "config.example.yaml").write_text(source.read_text())
        (templates / "SOUL.md").write_text("Synthetic image template marker")
        with patch.dict(os.environ, {"HE_ASSISTANT_TEMPLATE_DIR": str(templates)}):
            self.identity.prepare_profile(self.db, 1, profile_root=self.root / "hermes")
        self.assertEqual(
            (self.root / "hermes/profiles/he-user-1/SOUL.md").read_text(),
            "Synthetic image template marker",
        )

    def test_prepare_profile_is_idempotent_and_does_not_copy_raw_tool_token_to_he(self):
        from datetime import datetime

        run = self.db.get(self.models.AssistantRun, self.rid)
        run.status = "completed"
        run.executor_exited_at = datetime.utcnow()
        self.db.commit()
        prepare = importlib.import_module("app.assistant.identity").prepare_profile
        model = {
            "provider": "custom",
            "model": "fixture-model",
            "base_url": "https://model.example/v1",
            "api_key": "synthetic_model_key_" + ("c" * 40),
        }
        model_path = self.root / "assistant/hermes-model.json"
        model_path.parent.mkdir(mode=0o700)
        model_path.write_text(json.dumps(model))
        model_path.chmod(0o600)
        profile_root = self.root / "hermes"
        first = prepare(self.db, 1, profile_root=profile_root)
        he_cfg = self.root / "assistant/profiles.json"
        before = he_cfg.read_bytes()
        env_path = profile_root / "profiles/he-user-1/.env"
        before_env = env_path.read_bytes()
        prefs = env_path.parent / "memories/USER.md"
        prefs.parent.mkdir(exist_ok=True)
        prefs.write_text("Keep preferences")
        second = prepare(self.db, 1, profile_root=profile_root)
        self.assertEqual(
            first.api_key.get_secret_value(), second.api_key.get_secret_value()
        )
        self.assertEqual(before, he_cfg.read_bytes())
        self.assertEqual(before_env, env_path.read_bytes())
        self.assertEqual(prefs.read_text(), "Keep preferences")
        raw_tool = next(
            line.partition("=")[2]
            for line in env_path.read_text().splitlines()
            if line.startswith("HE_TOOL_TOKEN=")
        )
        self.assertNotIn(raw_tool, he_cfg.read_text())
        self.assertNotIn(model["api_key"], he_cfg.read_text())
        stored = self.db.get(self.models.AssistantToolIdentity, 1)
        self.db.refresh(stored)
        self.assertEqual(
            stored.tool_token_hash, self.identity.hash_tool_token(raw_tool)
        )
        self.assertTrue(stored.enabled)
        if os.name != "nt":
            self.assertEqual(env_path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(env_path.parent.stat().st_mode & 0o777, 0o700)
        self.assertNotIn(raw_tool, repr(first))
        self.assertNotIn(first.api_key.get_secret_value(), repr(first))
