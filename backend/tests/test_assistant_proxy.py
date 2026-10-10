import importlib
import json
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch
from uuid import uuid4
import httpx
from fastapi import HTTPException
from app.assistant.models import AssistantRun, AssistantSession, AssistantProposal
from app.assistant.schemas import ProfileBinding, RunRequest, SubmissionEnvelope
from tests.assistant_fixtures import assistant_fixture


def stream_response(status, **kwargs):
    raw = kwargs.get("content")
    if raw is None:
        raw = json.dumps(kwargs.get("json")).encode()
    return httpx.Response(status, stream=httpx.ByteStream(raw))


RID = "run_" + ("a" * 32)


class FakeHermes:
    def __init__(self):
        self.calls = []
        self.timeout = False
        self.delete_fails = False
        self.stop_to_terminal = True
        self.state = {
            "run_id": RID,
            "session_id": None,
            "status": "running",
            "last_event": "run.started",
        }

    async def create_session(self, profile, sid):
        self.calls.append(("create_session", profile.user_id, str(sid)))
        return "he-" + str(sid)

    async def start_run(self, profile, envelope):
        self.calls.append(("start_run", profile.user_id, envelope.model_dump_json()))
        self.state["session_id"] = envelope.session_id
        if self.timeout:
            self.timeout = False
            raise httpx.ReadTimeout("synthetic timeout after acceptance")
        return RID

    async def get_run(self, profile, rid):
        self.calls.append(("get_run", profile.user_id, rid))
        return dict(self.state)

    async def stop_run(self, profile, rid):
        self.calls.append(("stop_run", profile.user_id, rid))
        if self.stop_to_terminal:
            self.state.update(
                status="cancelled",
                last_event="run.cancelled",
                turn_exit_reason="interrupted_during_api_call",
                interrupted=True,
            )
        return {"run_id": rid, "status": "stopping"}

    async def delete_session(self, profile, sid):
        self.calls.append(("delete_session", profile.user_id, sid))
        if self.delete_fails:
            raise httpx.ConnectError("synthetic private upstream offline")

    async def aclose(self):
        self.calls.append(("close",))


class AssistantProxyTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        try:
            self.service = importlib.import_module("app.assistant.sessions")
            self.client_module = importlib.import_module("app.assistant.hermes_client")
        except ModuleNotFoundError:
            self.fail("Hermes session adapter is not implemented")
        self.f = assistant_fixture(self)
        old = self.f.db.get(AssistantRun, self.f.rid)
        old.status = "completed"
        old.executor_exited_at = datetime.utcnow()
        self.f.db.commit()
        self.binding = ProfileBinding(
            user_id=1,
            profile_name="he-user-1",
            api_key="synthetic_api_profile_" + ("x" * 40),
            api_key_generation=1,
            tool_token_hash="f" * 64,
        )
        self.fake = FakeHermes()
        self.patches = [
            patch.object(self.service.config, "get_profile", return_value=self.binding),
            patch.object(
                self.service.config,
                "load_model",
                return_value={"provider": "custom:he-model", "model": "deepseek-flash"},
            ),
            patch.object(self.service.database, "SessionLocal", self.f.factory),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    async def submit(self, text="推荐温馨作品", request_id=None):
        return await self.service.submit_run(
            self.f.db,
            1,
            self.f.sid,
            RunRequest(input=text, client_request_id=request_id or uuid4()),
            client=self.fake,
        )

    async def test_same_client_request_keeps_he_run_upstream_id_and_frozen_body(self):
        request_id = uuid4()
        first = await self.submit(request_id=request_id)
        with patch.object(
            self.service.config,
            "load_model",
            return_value={"provider": "changed", "model": "changed"},
        ):
            retry = await self.submit(request_id=request_id)
        self.assertEqual(first.id, retry.id)
        self.f.db.expire_all()
        row = self.f.db.get(AssistantRun, str(first.id))
        self.assertEqual(row.client_request_id, str(request_id))
        self.assertEqual(row.upstream_run_id, RID)
        submitted = [c[2] for c in self.fake.calls if c[0] == "start_run"]
        self.assertEqual(len(set(submitted)), 1)
        envelope = SubmissionEnvelope.model_validate_json(row.submission_envelope_json)
        self.assertIn(str(first.id), envelope.instructions)
        self.assertIn(self.f.sid, envelope.instructions)
        self.assertNotIn(self.binding.api_key.get_secret_value(), envelope.instructions)
        self.assertEqual(envelope.max_turns, 8)
        self.assertEqual(envelope.output_tokens, 2048)

    async def test_timeout_after_acceptance_replays_same_key_and_body(self):
        self.fake.timeout = True
        request_id = uuid4()
        first = await self.submit(request_id=request_id)
        self.assertEqual(first.status, "submission_unknown")
        self.f.db.expire_all()
        row = self.f.db.get(AssistantRun, str(first.id))
        original = row.submission_envelope_json
        recovered = await self.service.reconcile_run(
            self.f.db, 1, first.id, client=self.fake
        )
        self.assertEqual(recovered.id, first.id)
        self.f.db.expire_all()
        row = self.f.db.get(AssistantRun, str(first.id))
        self.assertEqual(row.upstream_run_id, RID)
        self.assertEqual(row.submission_envelope_json, original)
        bodies = [c[2] for c in self.fake.calls if c[0] == "start_run"]
        self.assertEqual(bodies, [original, original])

    async def test_conflicting_request_is_409_and_other_owner_is_404(self):
        request_id = uuid4()
        run = await self.submit(request_id=request_id)
        with self.assertRaises(HTTPException) as caught:
            await self.submit("changed", request_id)
        self.assertEqual(caught.exception.status_code, 409)
        with self.assertRaises(HTTPException) as caught:
            self.service.get_status(self.f.db, 2, run.id)
        self.assertEqual(caught.exception.status_code, 404)

    async def test_global_slot_and_unknown_terminal_executor_exit_are_fenced(self):
        run = await self.submit()
        self.fake.state.update(
            status="interrupted",
            last_event="run.interrupted",
            error="gateway restarted",
        )
        result = await self.service.reconcile_run(
            self.f.db, 1, run.id, client=self.fake
        )
        self.assertEqual(result.status, "interrupted")
        self.f.db.expire_all()
        self.assertIsNone(self.f.db.get(AssistantRun, str(run.id)).executor_exited_at)
        with self.assertRaises(HTTPException) as caught:
            await self.submit("new request")
        self.assertEqual(caught.exception.status_code, 409)

    async def test_cancelled_without_exit_reason_never_releases_slot(self):
        run = await self.submit()
        self.fake.state.update(status="cancelled", last_event="run.cancelled")
        await self.service.reconcile_run(self.f.db, 1, run.id, client=self.fake)
        self.f.db.expire_all()
        self.assertIsNone(self.f.db.get(AssistantRun, str(run.id)).executor_exited_at)

    async def test_between_tools_user_cancel_proves_exit_and_releases_global_slot(self):
        run = await self.submit()
        self.fake.state.update(
            status="cancelled",
            last_event="run.cancelled",
            turn_exit_reason="interrupted_by_user",
            interrupted=True,
            partial=False,
            completed=False,
        )
        result = await self.service.reconcile_run(
            self.f.db, 1, run.id, client=self.fake
        )
        self.assertEqual(result.status, "cancelled")
        self.f.db.expire_all()
        self.assertIsNotNone(
            self.f.db.get(AssistantRun, str(run.id)).executor_exited_at
        )
        await self.submit("new request after confirmed executor exit")

    async def test_between_tools_cancel_requires_all_flags_and_no_shutdown(self):
        base = dict(
            status="cancelled",
            last_event="run.cancelled",
            turn_exit_reason="interrupted_by_user",
            interrupted=True,
            partial=False,
            completed=False,
        )
        for change in (
            {"partial": True},
            {"interrupted": False},
            {"completed": True},
            {"shutdown_requested_at": "synthetic"},
            {"turn_exit_reason": "unknown"},
        ):
            with self.subTest(change=change):
                self.assertFalse(self.service.proves_exit({**base, **change}))
        missing = dict(base)
        missing.pop("partial")
        self.assertFalse(self.service.proves_exit(missing))

    async def test_normal_completed_is_one_authoritative_final_message(self):
        run = await self.submit()
        self.fake.state.update(
            status="completed",
            last_event="run.completed",
            completed=True,
            partial=False,
            interrupted=False,
            output="最终答案",
            usage={"input_tokens": 2, "output_tokens": 3, "total_tokens": 5},
        )
        first = await self.service.reconcile_run(self.f.db, 1, run.id, client=self.fake)
        again = await self.service.reconcile_run(self.f.db, 1, run.id, client=self.fake)
        self.assertEqual(first.final_message_id, again.final_message_id)
        self.assertEqual(first.output, "最终答案")
        self.f.db.expire_all()
        self.assertIsNotNone(
            self.f.db.get(AssistantRun, str(run.id)).executor_exited_at
        )
        history = self.service.get_history(
            self.f.db, 1, self.f.sid, limit=100, offset=0
        )
        matches = [
            m for m in history["items"] if m["id"] == str(first.final_message_id)
        ]
        self.assertEqual(len(matches), 1)

    async def test_watchdog_stops_expired_run_without_a_subscriber_even_when_disabled(
        self,
    ):
        run = await self.submit()
        row = self.f.db.get(AssistantRun, str(run.id))
        row.deadline_at = datetime.utcnow() - timedelta(seconds=1)
        self.f.db.commit()
        with patch.dict("os.environ", {"HE_ASSISTANT_ENABLED": "0"}):
            await self.service.background_tick(client=self.fake)
        self.assertIn(("stop_run", 1, RID), self.fake.calls)
        self.f.db.expire_all()
        row = self.f.db.get(AssistantRun, str(run.id))
        self.assertIsNotNone(row.stop_requested_at)
        self.assertIsNotNone(row.executor_exited_at)

    async def test_restart_marks_reconciling_and_stops_running_upstream_without_releasing_early(
        self,
    ):
        run = await self.submit()
        self.fake.stop_to_terminal = False
        self.service.prepare_recovery()
        self.f.db.expire_all()
        row = self.f.db.get(AssistantRun, str(run.id))
        self.assertEqual(row.status, "reconciling")
        self.assertIsNone(row.executor_exited_at)
        await self.service.background_tick(client=self.fake)
        self.assertIn(("stop_run", 1, RID), self.fake.calls)
        self.f.db.expire_all()
        self.assertIsNone(self.f.db.get(AssistantRun, str(run.id)).executor_exited_at)

    async def test_rotated_key_and_expired_idempotency_window_do_not_resubmit(self):
        self.fake.timeout = True
        run = await self.submit()
        self.fake.calls = []
        changed = self.binding.model_copy(update={"api_key_generation": 2})
        with patch.object(self.service.config, "get_profile", return_value=changed):
            await self.service.reconcile_run(self.f.db, 1, run.id, client=self.fake)
        self.assertFalse(self.fake.calls)
        self.f.db.expire_all()
        row = self.f.db.get(AssistantRun, str(run.id))
        self.assertEqual(row.error_code, "assistant_credential_changed")
        self.assertIsNone(row.executor_exited_at)
        row.created_at = datetime.utcnow() - timedelta(days=2)
        self.f.db.commit()
        await self.service.reconcile_run(self.f.db, 1, run.id, client=self.fake)
        self.assertFalse(self.fake.calls)
        self.f.db.expire_all()
        self.assertEqual(
            self.f.db.get(AssistantRun, str(run.id)).error_code,
            "assistant_idempotency_window_expired",
        )

    async def test_clear_commits_invalidations_before_network_and_retries_deletion(
        self,
    ):
        run = await self.submit()
        self.fake.delete_fails = True
        result = await self.service.clear_session(
            self.f.db, 1, self.f.sid, client=self.fake
        )
        self.assertEqual(result.state, "deleting")
        self.f.db.expire_all()
        self.assertIsNotNone(self.f.db.get(AssistantRun, str(run.id)).stop_requested_at)
        self.fake.delete_fails = False
        await self.service.background_tick(client=self.fake)
        self.f.db.expire_all()
        self.assertEqual(self.f.db.get(AssistantSession, self.f.sid).state, "cleared")

    async def test_demoted_owner_does_not_prevent_background_deadline_stop(self):
        from app.models import User

        run = await self.submit()
        self.f.db.get(AssistantRun, str(run.id)).deadline_at = (
            datetime.utcnow() - timedelta(seconds=1)
        )
        self.f.db.get(User, 1).is_admin = False
        self.f.db.commit()
        await self.service.background_tick(client=self.fake)
        self.assertIn(("stop_run", 1, RID), self.fake.calls)

    async def test_startup_does_not_wait_for_offline_upstream_and_client_is_closed(
        self,
    ):
        import asyncio

        class Offline(FakeHermes):
            async def get_run(self, *args):
                await asyncio.Event().wait()

        offline = Offline()
        self.service.prepare_recovery()
        with patch.object(self.service, "get_client", return_value=offline):
            task = self.service.start_background()
            self.assertFalse(task.done())
            await self.service.stop_background()
        self.assertIn(("close",), offline.calls)

    async def test_validated_results_recover_independently_of_upstream_preview(self):
        run = await self.submit()
        row = self.f.db.get(AssistantRun, str(run.id))
        row.tool_results_json = json.dumps(
            [
                {
                    "tool_call_id": str(uuid4()),
                    "tool_name": "get_library_stats",
                    "result": {
                        "total": 62,
                        "by_type": {"manga": 1},
                        "favorite_count": 1,
                        "watched_count": 0,
                    },
                }
            ]
        )
        row.tool_results_truncated = True
        self.f.db.commit()
        result = self.service.get_results(self.f.db, 1, run.id)
        self.assertEqual(result.items[0].result.total, 62)
        self.assertTrue(result.truncated)

    async def test_final_utf8_output_is_bounded_without_releasing_on_proxy_failure(
        self,
    ):
        run = await self.submit()
        self.fake.state.update(
            status="completed",
            last_event="run.completed",
            completed=True,
            partial=False,
            interrupted=False,
            output="文" * 30000,
        )
        result = await self.service.reconcile_run(
            self.f.db, 1, run.id, client=self.fake
        )
        self.assertLessEqual(len(result.output.encode()), 65536)
        self.assertEqual(result.error_code, "upstream_response_too_large")


class HermesHTTPClientTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        try:
            self.module = importlib.import_module("app.assistant.hermes_client")
        except ModuleNotFoundError:
            self.fail("Hermes HTTP client is missing")
        self.profile = ProfileBinding(
            user_id=1,
            profile_name="he-user-1",
            api_key="synthetic_api_" + ("x" * 40),
            api_key_generation=1,
            tool_token_hash="f" * 64,
        )

    async def test_fixed_profile_prefix_and_session_conflict_is_verified(self):
        sid = uuid4()
        requests = []

        def handler(request):
            requests.append(request)
            if request.method == "GET":
                if len(requests) == 1:
                    return stream_response(404, json={"error": "missing"})
                return stream_response(
                    200,
                    json={
                        "object": "hermes.session",
                        "session": {"id": "he-" + str(sid), "source": "api_server"},
                    },
                )
            return stream_response(409, json={"error": "exists"})

        client = self.module.HermesClient(
            base_url="http://hermes.test", transport=httpx.MockTransport(handler)
        )
        try:
            self.assertEqual(
                await client.create_session(self.profile, sid), "he-" + str(sid)
            )
        finally:
            await client.aclose()
        self.assertTrue(all(r.url.path.startswith("/p/he-user-1/") for r in requests))
        self.assertTrue(
            all(
                r.headers["Authorization"]
                == "Bearer " + self.profile.api_key.get_secret_value()
                for r in requests
            )
        )

    async def test_mismatched_existing_session_is_rejected(self):
        client = self.module.HermesClient(
            base_url="http://hermes.test",
            transport=httpx.MockTransport(
                lambda r: stream_response(
                    200,
                    json={
                        "object": "hermes.session",
                        "session": {"id": "he-wrong", "source": "api_server"},
                    },
                )
            ),
        )
        try:
            with self.assertRaises(self.module.UpstreamError):
                await client.create_session(self.profile, uuid4())
        finally:
            await client.aclose()

    async def test_json_limit_errors_and_read_retry_are_bounded_and_sanitized(self):
        for content, status, code, count in [
            (b"{bad", 200, "upstream_invalid_response", 1),
            (b"x" * (8 * 1024 * 1024 + 1), 200, "upstream_response_too_large", 1),
            (b'{"API_SERVER_KEY":"synthetic-secret"}', 429, "upstream_busy", 2),
            (b"private traceback", 503, "upstream_unavailable", 2),
        ]:
            calls = []

            def handler(request):
                calls.append(request)
                return stream_response(status, content=content)

            client = self.module.HermesClient(
                base_url="http://hermes.test", transport=httpx.MockTransport(handler)
            )
            try:
                with self.assertRaises(self.module.UpstreamError) as caught:
                    await client.get_run(self.profile, RID)
                self.assertEqual(caught.exception.code, code)
                self.assertNotIn("synthetic-secret", str(caught.exception))
                self.assertEqual(len(calls), count)
            finally:
                await client.aclose()

    async def test_start_uses_same_idempotency_header_and_only_fixed_envelope_fields(
        self,
    ):
        calls = []
        sid = uuid4()
        envelope = SubmissionEnvelope(
            input="fixture",
            instructions="trusted",
            provider="custom:he-model",
            model="deepseek-flash",
            session_id="he-" + str(sid),
            idempotency_key=str(uuid4()),
            api_key_generation=1,
        )

        def handler(request):
            calls.append(request)
            return stream_response(
                202, json={"run_id": RID, "status": "started", "replayed": False}
            )

        client = self.module.HermesClient(
            base_url="http://hermes.test", transport=httpx.MockTransport(handler)
        )
        try:
            self.assertEqual(await client.start_run(self.profile, envelope), RID)
            self.assertEqual(await client.start_run(self.profile, envelope), RID)
        finally:
            await client.aclose()
        self.assertEqual(calls[0].content, calls[1].content)
        self.assertEqual(calls[0].headers["Idempotency-Key"], envelope.idempotency_key)
        self.assertNotIn("api_key_generation", json.loads(calls[0].content))


class AssistantSubmissionRaceTests(unittest.IsolatedAsyncioTestCase):
    setUp = AssistantProxyTests.setUp
    submit = AssistantProxyTests.submit

    async def test_two_initial_requests_share_reserved_envelope_and_one_upstream_key(
        self,
    ):
        import asyncio, threading
        from concurrent.futures import ThreadPoolExecutor

        request_id = uuid4()
        barrier = threading.Barrier(2)
        original = self.service.store.reserve_run

        def reserve(*args, **kwargs):
            barrier.wait(timeout=5)
            return original(*args, **kwargs)

        def worker():
            with self.f.factory() as db:
                return asyncio.run(
                    self.service.submit_run(
                        db,
                        1,
                        self.f.sid,
                        RunRequest(input="same input", client_request_id=request_id),
                        client=self.fake,
                    )
                )

        with (
            patch.object(self.service.store, "reserve_run", side_effect=reserve),
            ThreadPoolExecutor(max_workers=2) as pool,
        ):
            loop = asyncio.get_running_loop()
            results = await asyncio.gather(
                loop.run_in_executor(pool, worker), loop.run_in_executor(pool, worker)
            )
        self.assertEqual(results[0].id, results[1].id)
        bodies = [c[2] for c in self.fake.calls if c[0] == "start_run"]
        self.assertEqual(len(set(bodies)), 1)

    async def test_session_creation_unknown_is_reconciled_with_same_reserved_id(self):
        class CreationTimeout(FakeHermes):
            def __init__(inner):
                super().__init__()
                inner.fail = True

            async def create_session(inner, profile, sid):
                inner.calls.append(("create_session", profile.user_id, str(sid)))
                if inner.fail:
                    inner.fail = False
                    raise httpx.ReadTimeout("synthetic timeout")
                return "he-" + str(sid)

        fake = CreationTimeout()
        with self.assertRaises(HTTPException):
            await self.service.create_session(self.f.db, 1, "retry", client=fake)
        self.f.db.expire_all()
        pending = self.f.db.query(AssistantSession).filter_by(state="creating").one()
        await self.service.background_tick(client=fake)
        self.f.db.expire_all()
        self.assertEqual(self.f.db.get(AssistantSession, pending.id).state, "active")
        created = [c[2] for c in fake.calls if c[0] == "create_session"]
        self.assertEqual(created, [pending.id, pending.id])

    async def test_watchdog_fence_survives_blocked_poll_and_temporary_database_busy(
        self,
    ):
        import asyncio
        from sqlalchemy.exc import OperationalError

        blocked = asyncio.Event()
        saved = asyncio.Event()

        class Blocked(FakeHermes):
            async def get_run(inner, *args):
                blocked.set()
                await asyncio.Event().wait()

        fake = Blocked()
        original = self.service.trusted_stop
        attempts = []

        def stop(db, user_id, rid):
            attempts.append(1)
            if len(attempts) == 1:
                raise OperationalError("UPDATE", {}, Exception("database is locked"))
            result = original(db, user_id, rid)
            saved.set()
            return result

        # Starting recovery with no active executor is immediate. A new run's
        # deadline then expires while a separate status RPC is deliberately stuck.
        with patch.object(self.service, "get_client", return_value=fake):
            self.service.start_background()
            try:
                run = await self.service.submit_run(
                    self.f.db,
                    1,
                    self.f.sid,
                    RunRequest(input="deadline", client_request_id=uuid4()),
                    client=fake,
                )
                await asyncio.wait_for(blocked.wait(), 0.5)
                self.f.db.get(AssistantRun, str(run.id)).deadline_at = (
                    datetime.utcnow() + timedelta(seconds=0.05)
                )
                self.f.db.commit()
                with patch.object(self.service, "trusted_stop", side_effect=stop):
                    await asyncio.wait_for(saved.wait(), 1.5)
                self.f.db.expire_all()
                self.assertIsNotNone(
                    self.f.db.get(AssistantRun, str(run.id)).stop_requested_at
                )
                self.assertGreaterEqual(len(attempts), 2)
            finally:
                await self.service.stop_background()

    async def test_restart_observes_completed_run_before_stop_and_preserves_pending_proposal(
        self,
    ):
        from app.assistant import proposals
        from app.assistant.schemas import ToolContext

        run = await self.submit()
        proposal = proposals.create_proposal(
            self.f.db,
            self.f.principal,
            ToolContext(session_id=self.f.sid, run_id=run.id),
            "media_update",
            {"media_id": 1, "patch": {"rating": 5}},
        )
        self.fake.state.update(
            status="completed",
            last_event="run.completed",
            completed=True,
            partial=False,
            interrupted=False,
            output="already finished",
        )
        self.fake.calls = []
        self.service.prepare_recovery()
        await self.service.background_tick(client=self.fake)
        self.assertFalse(any(c[0] == "stop_run" for c in self.fake.calls))
        self.assertEqual(self.fake.calls[0][0], "get_run")
        self.f.db.expire_all()
        self.assertEqual(
            self.f.db.get(AssistantProposal, str(proposal.id)).state, "pending"
        )
        self.assertIsNotNone(
            self.f.db.get(AssistantRun, str(run.id)).executor_exited_at
        )
