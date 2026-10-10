import importlib
import json
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect
from app.assistant.models import AssistantRun, AssistantSession
from tests.assistant_fixtures import assistant_fixture, business_snapshot


class AssistantInternalAPITests(unittest.TestCase):
    def setUp(self):
        try:
            self.module = importlib.import_module("app.assistant.internal_app")
        except ModuleNotFoundError:
            self.fail("Assistant internal HTTP app is not implemented")
        self.f = assistant_fixture(self)

        def get_db():
            with self.f.factory() as db:
                yield db

        self.module.app.dependency_overrides[self.module.get_db] = get_db
        self.client = TestClient(self.module.app)
        self.addCleanup(self.module.app.dependency_overrides.clear)
        self.addCleanup(self.client.close)

    def call(self, name="search_media", args=None, token=True):
        return self.client.post(
            "/tools/" + name,
            json={
                "context": self.f.context.model_dump(mode="json"),
                "args": args or {},
            },
            headers={"Authorization": "Bearer " + self.f.token} if token else {},
        )

    def test_internal_authentication_and_unknown_tool_fail_closed(self):
        self.assertEqual(self.call(token=False).status_code, 401)
        self.assertEqual(self.call("terminal").status_code, 404)
        self.assertEqual(
            self.call(args={"url": "https://evil.example"}).status_code, 422
        )
        self.assertEqual(
            self.client.post("/assistant/proposals/fake/confirm").status_code, 404
        )

    def test_business_data_stays_unchanged_but_validated_display_result_is_durable(
        self,
    ):
        before = business_snapshot(self.f.engine)
        response = self.call(args={"query": "温馨"})
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(result["tool_name"], "search_media")
        self.assertTrue(result["tool_call_id"])
        self.assertEqual(result["result"]["items"][0]["id"], 1)
        self.f.db.expire_all()
        stored = json.loads(self.f.db.get(AssistantRun, self.f.rid).tool_results_json)
        self.assertEqual(stored, [result])
        self.assertEqual(business_snapshot(self.f.engine), before)

    def test_late_result_after_stop_is_never_persisted(self):
        original = self.module.execute_read_tool

        def stopped(db, principal, context, name, args):
            result = original(db, principal, context, name, args)
            with self.f.factory() as other:
                from datetime import datetime

                run = other.get(AssistantRun, self.f.rid)
                run.stop_requested_at = datetime.utcnow()
                run.status = "stopping"
                other.commit()
            return result

        with patch.object(self.module, "execute_read_tool", side_effect=stopped):
            response = self.call()
        self.assertEqual(response.status_code, 409)
        self.f.db.expire_all()
        self.assertEqual(
            json.loads(self.f.db.get(AssistantRun, self.f.rid).tool_results_json), []
        )

    def test_clearing_session_and_wrong_context_are_denied(self):
        context = self.f.context.model_dump(mode="json")
        context["run_id"] = "10000000-0000-0000-0000-000000000001"
        response = self.client.post(
            "/tools/search_media",
            json={"context": context, "args": {}},
            headers={"Authorization": "Bearer " + self.f.token},
        )
        self.assertEqual(response.status_code, 404)
        self.f.db.get(AssistantSession, self.f.sid).state = "deleting"
        self.f.db.commit()
        self.assertEqual(self.call().status_code, 409)

    def test_oversize_result_returns_durable_truncation_flag_and_preserves_previous_results(
        self,
    ):
        self.assertEqual(self.call("get_library_stats").status_code, 200)
        self.f.db.expire_all()
        previous = self.f.db.get(AssistantRun, self.f.rid).tool_results_json
        # Every item is individually valid; the complete JSON exceeds64KiB.
        giant = {
            "items": [
                {
                    "id": i + 1,
                    "title": "文" * 500,
                    "media_type": "manga",
                    "artist": "人" * 500,
                    "tags": [],
                }
                for i in range(50)
            ],
            "total": 50,
            "offset": 0,
            "has_more": False,
        }
        with patch.object(self.module, "execute_read_tool", return_value=giant):
            # A single oversize page is shortened and points at the next page.
            paged = self.call()
            self.assertEqual(paged.status_code, 200)
            self.assertTrue(paged.json()["result"]["has_more"])
            self.assertLess(len(paged.json()["result"]["items"]), 50)
            self.f.db.expire_all()
            previous = self.f.db.get(AssistantRun, self.f.rid).tool_results_json
            # Results that no longer fit in the run store become a durable flag.
            response = self.call()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["result"]["truncated"])
        self.f.db.expire_all()
        run = self.f.db.get(AssistantRun, self.f.rid)
        self.assertLessEqual(len(run.tool_results_json.encode()), 65536)
        self.assertEqual(run.tool_results_json, previous)
        self.assertTrue(run.tool_results_truncated)

    def test_malformed_result_is_rejected_before_storage(self):
        with patch.object(
            self.module,
            "execute_read_tool",
            return_value={
                "items": [{"id": 1, "absolute_path": "/private"}],
                "total": 1,
            },
        ):
            response = self.call()
        self.assertEqual(response.status_code, 502)
        self.f.db.expire_all()
        self.assertEqual(
            self.f.db.get(AssistantRun, self.f.rid).tool_results_json, "[]"
        )

    def test_flag_off_and_missing_schema_do_not_create_tables(self):
        with patch.dict("os.environ", {"HE_ASSISTANT_ENABLED": "0"}):
            self.assertEqual(self.call().status_code, 503)
        empty = create_engine("sqlite:///" + str(self.f.root / "empty.db"))
        self.addCleanup(empty.dispose)
        from sqlalchemy.orm import Session

        def empty_db():
            with Session(empty) as db:
                yield db

        self.module.app.dependency_overrides[self.module.get_db] = empty_db
        response = self.client.get("/healthz")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(inspect(empty).get_table_names(), [])

    def test_h02_database_migrates_truncation_flag_idempotently(self):
        from app.migrations import ensure_assistant_tables

        legacy = create_engine("sqlite:///" + str(self.f.root / "legacy.db"))
        self.addCleanup(legacy.dispose)
        # Preserve the exact previous phase schema, including unrelated users.
        with legacy.begin() as conn:
            conn.exec_driver_sql("CREATE TABLE users (id INTEGER PRIMARY KEY)")
            conn.exec_driver_sql("INSERT INTO users VALUES (17)")
            conn.exec_driver_sql(
                "CREATE TABLE assistant_runs (id VARCHAR PRIMARY KEY, tool_results_json TEXT NOT NULL DEFAULT '[]')"
            )
            conn.exec_driver_sql("INSERT INTO assistant_runs (id) VALUES ('old-run')")
        ensure_assistant_tables(legacy)
        ensure_assistant_tables(legacy)
        with legacy.connect() as conn:
            self.assertEqual(
                conn.exec_driver_sql(
                    "SELECT tool_results_truncated FROM assistant_runs"
                ).scalar(),
                0,
            )
            self.assertEqual(conn.exec_driver_sql("SELECT id FROM users").scalar(), 17)
