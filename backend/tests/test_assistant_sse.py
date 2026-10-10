import importlib
import json
import unittest
from unittest.mock import patch
from uuid import uuid4
import httpx
from app.assistant.models import AssistantRun
from app.assistant.schemas import ProfileBinding
from tests.assistant_fixtures import assistant_fixture
from tests.test_assistant_proxy import FakeHermes, RID


async def chunks(data, size=1):
    for i in range(0, len(data), size):
        yield data[i : i + size]


class AssistantSSEParserTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        try:
            self.module = importlib.import_module("app.assistant.hermes_client")
        except ModuleNotFoundError:
            self.fail("Hermes SSE parser is missing")

    async def test_utf8_chunks_multiline_data_crlf_comments_and_ids(self):
        wire = (
            ': heartbeat\r\n\r\nid: 7\r\ndata: {"event":"message.delta",\r\ndata: "run_id":"'
            + RID
            + '","delta":"你好","seq":7}\r\n\r\n: alive\r\n\r\n'
        )
        events = [e async for e in self.module.iter_sse(chunks(wire.encode(), 1))]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["delta"], "你好")
        self.assertEqual(events[0]["seq"], 7)

    async def test_event_limit_is_checked_before_json_parse(self):
        with self.assertRaises(self.module.UpstreamError) as caught:
            _ = [
                e
                async for e in self.module.iter_sse(
                    chunks(b"data: " + b"x" * (128 * 1024 + 1), 4096)
                )
            ]
        self.assertEqual(caught.exception.code, "upstream_response_too_large")

    async def test_incomplete_json_and_mismatched_sequence_are_errors(self):
        for wire in [
            b"data: {invalid\n\n",
            b'id: 2\ndata: {"event":"message.delta","seq":3}\n\n',
        ]:
            with self.assertRaises(self.module.UpstreamError):
                _ = [e async for e in self.module.iter_sse(chunks(wire, 3))]


class StreamFake(FakeHermes):
    def __init__(self, events):
        super().__init__()
        self.events = events

    async def stream_events(self, profile, rid, last_event_id=None):
        self.calls.append(("stream", profile.user_id, rid, last_event_id))
        for event in self.events:
            if event["event"] == "run.completed":
                self.state.update(
                    event,
                    status="completed",
                    last_event="run.completed",
                    completed=True,
                    interrupted=False,
                    partial=False,
                )
            yield event


class AssistantSSETests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        try:
            self.service = importlib.import_module("app.assistant.sessions")
            self.module = importlib.import_module("app.assistant.hermes_client")
        except ModuleNotFoundError:
            self.fail("Assistant streaming projection is missing")
        self.f = assistant_fixture(self)
        self.f.db.get(AssistantRun, self.f.rid).upstream_run_id = RID
        self.f.db.commit()
        self.binding = ProfileBinding(
            user_id=1,
            profile_name="he-user-1",
            api_key="synthetic_profile_" + ("x" * 40),
            api_key_generation=1,
            tool_token_hash="f" * 64,
        )
        profile_patch = patch.object(
            self.service.config, "get_profile", return_value=self.binding
        )
        profile_patch.start()
        self.addCleanup(profile_patch.stop)

    def event(self, event, seq, **extra):
        return {"event": event, "seq": seq, "run_id": RID, **extra}

    async def collect(self, fake, last_event_id=None):
        fake.state["session_id"] = "he-" + self.f.sid
        return [
            e.model_dump(mode="json")
            async for e in self.service.stream_events(
                self.f.db, 1, self.f.rid, last_event_id=last_event_id, client=fake
            )
        ]

    async def test_only_public_events_and_one_final_replace_partial_and_duplicate_terminal(
        self,
    ):
        fake = StreamFake(
            [
                self.event("message.delta", 0, delta="半截"),
                self.event(
                    "reasoning.available", 1, text="private reasoning API_SERVER_KEY"
                ),
                self.event("message.interim", 2, text="commentary"),
                self.event(
                    "tool.completed",
                    3,
                    tool="terminal",
                    preview="API_SERVER_KEY=private /opt/data",
                ),
                self.event(
                    "run.completed",
                    4,
                    output="权威答案",
                    usage={"input_tokens": 2, "output_tokens": 3, "total_tokens": 5},
                ),
                self.event("run.completed", 4, output="duplicate"),
            ]
        )
        events = await self.collect(fake)
        encoded = json.dumps(events, ensure_ascii=False)
        self.assertNotIn("API_SERVER_KEY", encoded)
        self.assertNotIn("/opt/data", encoded)
        self.assertNotIn("private reasoning", encoded)
        self.assertNotIn("commentary", encoded)
        finals = [
            e
            for e in events
            if e["type"] == "run_status" and e["data"]["status"] == "completed"
        ]
        self.assertEqual(len(finals), 1)
        self.assertEqual(finals[0]["data"]["output"], "权威答案")
        deltas = [e for e in events if e["type"] == "text_delta"]
        self.assertEqual(deltas[0]["message_id"], finals[0]["message_id"])

    async def test_tool_preview_is_ignored_and_only_persisted_dto_is_projected(self):
        call_id = str(uuid4())
        row = self.f.db.get(AssistantRun, self.f.rid)
        row.tool_results_json = json.dumps(
            [
                {
                    "tool_call_id": call_id,
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
        self.f.db.commit()
        fake = StreamFake(
            [
                self.event(
                    "tool.completed",
                    0,
                    tool="mcp__he__get_library_stats",
                    preview="{malicious private headers}",
                ),
                self.event("run.completed", 1, output="完成"),
            ]
        )
        events = await self.collect(fake)
        trusted = [
            e["data"]
            for e in events
            if e["type"] == "tool_status" and "result" in e["data"]
        ]
        self.assertEqual(len(trusted), 1)
        self.assertEqual(trusted[0]["tool_call_id"], call_id)
        self.assertEqual(trusted[0]["result"]["total"], 62)
        self.assertNotIn("malicious", json.dumps(events))

    async def test_expired_sse_buffer_falls_back_to_status_without_submitting_new_run(
        self,
    ):
        class Expired(StreamFake):
            async def stream_events(inner, *args, **kwargs):
                inner.state.update(
                    status="completed",
                    last_event="run.completed",
                    completed=True,
                    partial=False,
                    interrupted=False,
                    output="恢复后的完整答案",
                )
                raise self.module.UpstreamError("upstream_events_expired")
                yield

        fake = Expired([])
        events = await self.collect(fake, last_event_id="999")
        self.assertEqual(events[-1]["data"]["output"], "恢复后的完整答案")
        self.assertFalse(any(c[0] == "start_run" for c in fake.calls))

    async def test_replayed_sequences_are_skipped_and_wrong_run_is_rejected(self):
        fake = StreamFake(
            [
                self.event("message.delta", 1, delta="old"),
                self.event("message.delta", 2, delta="new"),
                self.event("message.delta", 2, delta="duplicate"),
                self.event("run.completed", 3, output="final"),
            ]
        )
        events = await self.collect(fake, last_event_id="1")
        self.assertEqual(
            [e["data"]["delta"] for e in events if e["type"] == "text_delta"], ["new"]
        )
        row = self.f.db.get(AssistantRun, self.f.rid)
        row.status = "running"
        row.executor_exited_at = None
        row.output = ""
        self.f.db.commit()
        fake = StreamFake(
            [
                {
                    "event": "message.delta",
                    "seq": 0,
                    "run_id": "run_" + ("b" * 32),
                    "delta": "wrong",
                }
            ]
        )
        events = await self.collect(fake)
        self.assertNotIn("wrong", json.dumps(events))
        self.assertTrue(any(e["type"] == "error" for e in events))

    async def test_disconnecting_subscription_does_not_stop_run(self):
        fake = StreamFake([self.event("message.delta", 0, delta="fragment")])
        fake.state["session_id"] = "he-" + self.f.sid
        stream = self.service.stream_events(self.f.db, 1, self.f.rid, client=fake)
        await anext(stream)
        await stream.aclose()
        self.assertFalse(any(c[0] == "stop_run" for c in fake.calls))
        self.f.db.expire_all()
        self.assertIsNone(self.f.db.get(AssistantRun, self.f.rid).stop_requested_at)

    async def test_public_sse_rejects_rotated_generation_before_http_200(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.routers import assistant as routes

        public = FastAPI()
        public.include_router(routes.router)

        def get_db():
            with self.f.factory() as db:
                yield db

        public.dependency_overrides[routes.get_db] = get_db
        from app.models import User

        public.dependency_overrides[routes.auth.require_admin] = lambda: self.f.db.get(
            User, 1
        )
        with (
            patch.object(
                self.service.config,
                "get_profile",
                return_value=self.binding.model_copy(update={"api_key_generation": 2}),
            ),
            TestClient(public) as client,
        ):
            response = client.get("/assistant/runs/" + self.f.rid + "/events")
        self.assertEqual(response.status_code, 409)

    async def test_terminal_stream_remains_readable_without_profile_files(self):
        from datetime import datetime

        row = self.f.db.get(AssistantRun, self.f.rid)
        row.status = "completed"
        row.executor_exited_at = datetime.utcnow()
        row.output = "已完成"
        self.f.db.commit()
        with patch.object(
            self.service.config,
            "get_profile",
            side_effect=AssertionError("final history must not require private files"),
        ):
            result = [
                e async for e in self.service.stream_events(self.f.db, 1, self.f.rid)
            ]
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].data["output"], "已完成")

    async def test_stream_size_fault_remains_durable_after_confirmed_cancellation(self):
        fake = StreamFake([self.event("message.delta", 0, delta="文" * 23000)])
        events = await self.collect(fake)
        self.assertTrue(
            any(
                e["type"] == "error"
                and e["data"]["code"] == "upstream_response_too_large"
                for e in events
            )
        )
        self.f.db.expire_all()
        status = self.service.get_status(self.f.db, 1, self.f.rid)
        self.assertEqual(status.status, "cancelled")
        self.assertEqual(status.error_code, "upstream_response_too_large")
