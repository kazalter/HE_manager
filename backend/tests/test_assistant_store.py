"""Identity and reservation contracts use independent, real SQLite connections."""

import importlib
import json
import tempfile
import threading
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import create_engine, event, inspect
from sqlalchemy.orm import sessionmaker
from app import models as he_models


class AssistantStoreTests(unittest.TestCase):
    def setUp(self):
        try:
            self.store = importlib.import_module("app.assistant.store")
            self.models = importlib.import_module("app.assistant.models")
            self.schemas = importlib.import_module("app.assistant.schemas")
        except ModuleNotFoundError:
            self.fail("Assistant identity and persistence have not been implemented")
        self.tmp = tempfile.TemporaryDirectory()
        self.engine = create_engine(
            "sqlite:///" + str(Path(self.tmp.name) / "test.db"),
            connect_args={"check_same_thread": False},
        )

        @event.listens_for(self.engine, "connect")
        def pragma(conn, _):
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA busy_timeout=5000")

        he_models.Base.metadata.create_all(self.engine)
        self.factory = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.db = self.factory()
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
        self.db.commit()
        self.env = patch.dict("os.environ", {"HE_ASSISTANT_ENABLED": "1"})
        self.env.start()
        # unittest runs cleanup callbacks in reverse registration order.
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.db.close)
        self.addCleanup(self.env.stop)

    def envelope(self, session, text="synthetic"):
        return self.schemas.SubmissionEnvelope(
            input=text,
            instructions="Trusted synthetic context",
            provider="custom:he-model",
            model="fixture-model",
            session_id=session.upstream_session_id,
            idempotency_key=str(uuid4()),
            api_key_generation=1,
        )

    def session(self, uid=1):
        created = self.store.create_session(self.db, uid, "Synthetic session")
        row = self.db.get(self.models.AssistantSession, created.id)
        row.state = "active"
        self.db.commit()
        return row

    def reserve(self, session, request=None, digest="synthetic-hash", envelope=None):
        return self.store.reserve_run(
            self.db,
            session.user_id,
            session.id,
            request or str(uuid4()),
            digest,
            envelope or self.envelope(session),
        )

    def test_other_admin_cannot_read_session(self):
        session = self.session()
        with self.assertRaises(HTTPException) as caught:
            self.store.require_owned_session(self.db, 2, session.id)
        self.assertEqual(caught.exception.status_code, 404)

    def test_retry_returns_original_run_and_frozen_envelope(self):
        session = self.session()
        request = str(uuid4())
        first = self.reserve(session, request)
        alternative = self.envelope(session)
        alternative = alternative.model_copy(update={"model": "new-default"})
        repeated = self.reserve(session, request, envelope=alternative)
        self.assertEqual(first.id, repeated.id)
        self.assertEqual(
            json.loads(repeated.submission_envelope_json)["model"], "fixture-model"
        )
        self.assertEqual(first.final_message_id, repeated.final_message_id)

    def test_same_request_different_payload_conflicts(self):
        session = self.session()
        request = str(uuid4())
        self.reserve(session, request)
        with self.assertRaises(HTTPException) as caught:
            self.reserve(session, request, digest="changed")
        self.assertEqual(caught.exception.status_code, 409)

    def test_same_request_different_session_conflicts(self):
        first = self.session()
        second = self.session()
        request = str(uuid4())
        self.reserve(first, request)
        with self.assertRaises(HTTPException) as caught:
            self.reserve(second, request)
        self.assertEqual(caught.exception.status_code, 409)

    def test_trusted_tool_context_can_reference_the_preallocated_run(self):
        session = self.session()
        planned_id = str(uuid4())
        envelope = self.envelope(session).model_copy(
            update={
                "idempotency_key": planned_id,
                "instructions": json.dumps(
                    {"session_id": session.id, "run_id": planned_id}
                ),
            }
        )
        run = self.reserve(session, envelope=envelope)
        persisted = json.loads(run.submission_envelope_json)
        self.assertEqual(json.loads(persisted["instructions"])["run_id"], run.id)

    def test_run_deadline_and_results_are_persisted(self):
        run = self.reserve(self.session())
        self.assertAlmostEqual(
            (run.deadline_at - run.created_at).total_seconds(), 180, delta=0.01
        )
        self.assertEqual(json.loads(run.tool_results_json), [])
        self.assertIsNone(run.stop_requested_at)
        self.assertIsNone(run.executor_exited_at)

    def test_concurrent_admin_reservation_admits_only_one(self):
        sessions = [self.session(i) for i in (1, 2)]
        barrier = threading.Barrier(2)
        out = []

        def worker(session):
            with self.factory() as db:
                barrier.wait()
                try:
                    out.append(("ok", self.reserve_with(db, session).id))
                except HTTPException as e:
                    out.append(("error", e.status_code))

        threads = [threading.Thread(target=worker, args=(s,)) for s in sessions]
        for t in threads:
            t.start()
        for t in threads:
            t.join(10)
        self.assertFalse(any(t.is_alive() for t in threads))
        self.assertEqual(sorted(x[0] for x in out), ["error", "ok"])
        self.assertIn(("error", 409), out)
        self.assertEqual(self.db.query(self.models.AssistantRun).count(), 1)

    def reserve_with(self, db, session):
        return self.store.reserve_run(
            db,
            session.user_id,
            session.id,
            str(uuid4()),
            "hash",
            self.envelope(session),
        )

    def test_interrupted_without_executor_exit_keeps_global_fence(self):
        first = self.reserve(self.session())
        first = self.db.get(self.models.AssistantRun, first.id)
        first.status = "interrupted"
        self.db.commit()
        with self.assertRaises(HTTPException) as caught:
            self.reserve(self.session(2))
        self.assertEqual(caught.exception.detail, "assistant_busy")
        first.executor_exited_at = datetime.utcnow()
        self.db.commit()
        self.assertEqual(self.reserve(self.session(2)).status, "submitting")

    def test_inactive_or_demoted_admin_cannot_reserve(self):
        session = self.session()
        for field in ("is_active", "is_admin"):
            user = self.db.get(he_models.User, 1)
            setattr(user, field, False)
            self.db.commit()
            with self.assertRaises(HTTPException) as caught:
                self.reserve(session)
            self.assertEqual(caught.exception.status_code, 403)
            setattr(user, field, True)
            self.db.commit()

    def test_feature_off_blocks_new_state_but_not_history(self):
        session = self.session()
        with patch.dict("os.environ", {"HE_ASSISTANT_ENABLED": "0"}):
            self.assertEqual(
                self.store.require_owned_session(self.db, 1, session.id).id, session.id
            )
            with self.assertRaises(HTTPException):
                self.reserve(session)
            with self.assertRaises(HTTPException):
                self.session()

    def test_deleted_session_cannot_submit(self):
        session = self.session()
        row = self.db.get(self.models.AssistantSession, session.id)
        row.state = "deleting"
        self.db.commit()
        with self.assertRaises(HTTPException) as caught:
            self.reserve(session)
        self.assertEqual(caught.exception.status_code, 409)

    def test_schema_creation_is_idempotent_and_preserves_old_rows(self):
        from app.migrations import ensure_assistant_tables

        for _ in range(2):
            ensure_assistant_tables(self.engine)
        self.assertEqual(self.db.query(he_models.User).count(), 2)
        self.assertTrue(
            {
                "assistant_tool_identities",
                "assistant_sessions",
                "assistant_runs",
                "assistant_proposals",
                "assistant_audits",
            }
            <= set(inspect(self.engine).get_table_names())
        )
        columns = {
            c["name"]
            for c in inspect(self.engine).get_columns("assistant_tool_identities")
        }
        self.assertNotIn("api_key", columns)
        self.assertNotIn("tool_token", columns)

    def test_old_library_gets_assistant_tables_without_replacing_users(self):
        from app.migrations import ensure_assistant_tables

        older = create_engine("sqlite:///" + str(Path(self.tmp.name) / "older.db"))
        try:
            he_models.User.__table__.create(older)
            with older.begin() as connection:
                connection.execute(
                    he_models.User.__table__.insert().values(
                        id=7,
                        username="old-admin",
                        password_hash="unused",
                        is_admin=True,
                        is_active=True,
                    )
                )
            ensure_assistant_tables(older)
            ensure_assistant_tables(older)
            with older.connect() as connection:
                self.assertEqual(
                    connection.execute(he_models.User.__table__.select())
                    .one()
                    .username,
                    "old-admin",
                )
            self.assertIn("assistant_runs", inspect(older).get_table_names())
        finally:
            older.dispose()

    def test_input_and_patch_contracts_reject_unknown_or_unsafe_fields(self):
        from pydantic import ValidationError

        for payload in (
            {"query": "x", "limit": 51},
            {"query": "x", "absolute_path": "/private"},
        ):
            with self.assertRaises(ValidationError):
                self.schemas.MediaQuery(**payload)
        for payload in (
            {"rating": 6},
            {"favorite": None},
            {"source_url": "https://user:password@example.com"},
            {"source_url": "https://example.com?token=secret"},
            {"source_url": "https://example.com?X-Goog-Credential=secret"},
            {"title": "unsupported"},
        ):
            with self.assertRaises(ValidationError):
                self.schemas.MediaPatch(**payload)
        patch_value = self.schemas.MediaPatch(source_url=None)
        self.assertEqual(
            patch_value.model_dump(exclude_unset=True), {"source_url": None}
        )
        self.assertEqual(
            self.schemas.TagInput(name=" tag ", namespace="").namespace, "general"
        )

    def test_tool_result_requires_matching_named_dto(self):
        from pydantic import ValidationError

        with self.assertRaises(ValidationError):
            self.schemas.ToolResultDTO(
                tool_call_id=uuid4(),
                tool_name="get_media_detail",
                result={"absolute_path": "private"},
            )
        with self.assertRaises(ValidationError):
            self.schemas.ToolResultDTO(
                tool_call_id=uuid4(), tool_name="terminal", result={}
            )
