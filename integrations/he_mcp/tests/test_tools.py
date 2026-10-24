"""Real SDK transport tests; no production credentials or media database."""

import asyncio
import importlib
import json
import socket
import os
import subprocess
import sys
import unittest
from contextlib import asynccontextmanager
from uuid import uuid4
import httpx2
import uvicorn
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

# Keep expectations explicit: deriving this allowlist from TOOL_CATALOG would
# silently approve accidental exposure of a new tool.
HISTORICAL_NAMES = {
    "search_media",
    "get_media_detail",
    "get_library_stats",
    "recommend_media",
    "list_duplicate_candidates",
    "list_tags",
    "list_folders",
    "propose_media_update",
    "propose_scan",
}
PAGE = {"items": [], "total": 0, "offset": 0, "has_more": False}
READ_CASES = {
    "search_media": ({"query": "你好"}, PAGE),
    "get_media_detail": (
        {"media_id": 1},
        {"id": 1, "title": "媒体", "media_type": "manga"},
    ),
    "get_library_stats": (
        {},
        {"total": 0, "by_type": {}, "favorite_count": 0, "watched_count": 0},
    ),
    "recommend_media": (
        {},
        {"items": [], "basis": "资料筛选", "method": "metadata_filter"},
    ),
    "list_duplicate_candidates": ({}, PAGE),
    "list_tags": ({}, PAGE),
    "list_folders": ({}, PAGE),
    "list_creators": ({}, PAGE),
    "get_creator_detail": (
        {"key": "a:作者"},
        {**PAGE, "key": "a:作者", "name": "作者"},
    ),
    "list_tasks": ({}, PAGE),
    "get_task_detail": (
        {"task_id": "scan-folder-1"},
        {
            "task_id": "scan-folder-1",
            "kind": "scan",
            "status": "idle",
            "summary": "尚未扫描",
        },
    ),
    "get_project_status": ({}, {"storage": [], "backup": [], "backup_count": 0}),
    "get_project_settings": ({}, PAGE),
    "list_directory": ({"folder_id": 1}, PAGE),
    "read_text": (
        {"folder_id": 1, "relative_path": "note.txt"},
        {
            "folder_id": 1,
            "relative_path": "note.txt",
            "text": "正文",
            "offset_bytes": 0,
            "truncated": False,
        },
    ),
    "get_media_preview": (
        {"media_id": 1, "page_index": 2},
        {
            "media_id": 1,
            "media_type": "manga",
            "page_index": 2,
            "page_count": 3,
            "preview_path": "/assistant/media/1/preview?page_index=2",
        },
    ),
    "read_logs": ({"source": "scan", "limit": 1}, {"items": [], "has_more": False}),
}
PROPOSAL_ARGS = {
    "propose_media_update": {"media_id": 1, "patch": {"rating": 4}},
    "propose_scan": {"folder_id": 1},
    "propose_media_batch_update": {"items": [{"media_id": 1, "patch": {"rating": 4}}]},
    "propose_tag_rename": {"tag_id": 1, "name": "新标签"},
    "propose_tag_merge": {"source_tag_id": 1, "target_tag_id": 2},
    "propose_maintenance": {"action": "backup_database"},
    "propose_file_move": {
        "media_id": 1,
        "destination_folder_id": 1,
        "destination_relative_path": "new.cbz",
    },
}
NAMES = set(READ_CASES) | set(PROPOSAL_ARGS)
CONTEXT = {"session_id": str(uuid4()), "run_id": str(uuid4())}
TOKEN_A = "test-admin-a-" + "a" * 32
TOKEN_B = "test-admin-b-" + "b" * 32


@asynccontextmanager
async def serving(app):
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="critical", lifespan="on"))
    task = asyncio.create_task(server.serve(sockets=[sock]))
    try:
        async with asyncio.timeout(5):
            while not server.started:
                if task.done():
                    await task
                await asyncio.sleep(0.01)
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        await asyncio.wait_for(task, 5)
        sock.close()


@asynccontextmanager
async def sdk(url, token):
    async with httpx2.AsyncClient(
        headers={"Authorization": "Bearer " + token}, trust_env=False
    ) as http:
        async with streamable_http_client(url + "/mcp", http_client=http) as streams:
            async with ClientSession(streams[0], streams[1]) as session:
                await session.initialize()
                yield session


class BridgeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.server = importlib.import_module("integrations.he_mcp.server")
        self.client = importlib.import_module("integrations.he_mcp.client")
        self.calls = []
        self.failures = 0
        self.barrier = None

    async def test_internal_health_is_readonly_and_does_not_require_a_tool_token(self):
        app = self.server.create_app()
        async with serving(app) as base:
            async with httpx2.AsyncClient(trust_env=False) as http:
                response = await http.get(base + "/healthz")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), {"status": "ok", "tools": len(NAMES)})
                denied = await http.post(base + "/mcp", json={})
                self.assertEqual(denied.status_code, 401)

    async def handler(self, request):
        body = await request.json()
        name = request.path_params["name"]
        self.calls.append((request.headers["authorization"], name, body))
        if self.barrier:
            if len(self.calls) == 2:
                self.barrier.set()
            await asyncio.wait_for(self.barrier.wait(), 3)
        if self.failures:
            self.failures -= 1
            return JSONResponse(
                {"detail": "secret path and token never forward"}, status_code=503
            )
        if body["context"] != CONTEXT:
            return JSONResponse({"detail": "foreign run secret"}, status_code=404)
        if name.startswith("propose_"):
            result = {
                "id": str(uuid4()),
                "kind": name.removeprefix("propose_"),
                "target_id": 1,
                "target_label": "媒体",
                "state": "pending",
                "expires_at": "2026-10-10T10:00:00",
            }
        else:
            result = READ_CASES[name][1]
        return JSONResponse(
            {"tool_name": name, "tool_call_id": str(uuid4()), "result": result}
        )

    @asynccontextmanager
    async def bridge(self):
        upstream = Starlette(
            routes=[Route("/tools/{name}", self.handler, methods=["POST"])]
        )
        async with serving(upstream) as base:
            async with self.client.HeToolClient(base_url=base) as client:
                async with serving(self.server.create_app(client=client)) as url:
                    yield url, client

    async def test_exact_catalog_annotations_and_structured_unwrapped_result(self):
        async with self.bridge() as (url, _):
            async with sdk(url, TOKEN_A) as session:
                tools = (await session.list_tools()).tools
                self.assertEqual({t.name for t in tools}, NAMES)
                for tool in tools:
                    self.assertEqual(
                        tool.annotations.read_only_hint,
                        not tool.name.startswith("propose_"),
                    )
                    self.assertFalse(tool.annotations.open_world_hint)
                    self.assertFalse(tool.annotations.destructive_hint)
                    self.assertEqual(
                        set(tool.input_schema["properties"]), {"context", "args"}
                    )
                result = await session.call_tool(
                    "search_media", {"context": CONTEXT, "args": {"query": "你好"}}
                )
                self.assertFalse(result.is_error)
                self.assertEqual(
                    result.structured_content,
                    {"items": [], "total": 0, "offset": 0, "has_more": False},
                )
                self.assertNotIn("tool_call_id", result.structured_content)

    async def test_every_read_tool_forwards_arguments_and_preserves_typed_result(self):
        async with self.bridge() as (url, _):
            async with sdk(url, TOKEN_A) as session:
                for name, (args, expected) in READ_CASES.items():
                    with self.subTest(tool=name):
                        result = await session.call_tool(
                            name, {"context": CONTEXT, "args": args}
                        )
                        self.assertFalse(result.is_error, str(result))
                        self.assertEqual(result.structured_content, expected)
                        self.assertEqual(
                            self.calls[-1],
                            (
                                "Bearer " + TOKEN_A,
                                name,
                                {"context": CONTEXT, "args": args},
                            ),
                        )

    async def test_every_tool_rejects_extra_identity_before_upstream(self):
        cases = {name: args for name, (args, _) in READ_CASES.items()} | PROPOSAL_ARGS
        async with self.bridge() as (url, _):
            async with sdk(url, TOKEN_A) as session:
                for name, args in cases.items():
                    with self.subTest(tool=name):
                        result = await session.call_tool(
                            name, {"context": CONTEXT, "args": {**args, "user_id": 2}}
                        )
                        self.assertTrue(result.is_error)
        self.assertEqual(self.calls, [])

    async def test_two_admin_tokens_are_scoped_to_each_concurrent_request(self):
        self.barrier = asyncio.Event()
        async with self.bridge() as (url, _):
            async with sdk(url, TOKEN_A) as a, sdk(url, TOKEN_B) as b:
                results = await asyncio.gather(
                    a.call_tool("search_media", {"context": CONTEXT, "args": {}}),
                    b.call_tool("search_media", {"context": CONTEXT, "args": {}}),
                )
                self.assertTrue(all(not r.is_error for r in results))
        self.assertEqual(
            {c[0] for c in self.calls}, {"Bearer " + TOKEN_A, "Bearer " + TOKEN_B}
        )

    async def test_unknown_tool_extra_identity_and_foreign_context_fail_closed(self):
        async with self.bridge() as (url, _):
            async with sdk(url, TOKEN_A) as session:
                for name, args in [
                    ("confirm_proposal", {}),
                    ("search_media", {"user_id": 2}),
                    ("propose_scan", {"folder_id": 1, "url": "http://evil"}),
                ]:
                    result = await session.call_tool(
                        name, {"context": CONTEXT, "args": args}
                    )
                    self.assertTrue(result.is_error)
                self.assertEqual(self.calls, [])
                result = await session.call_tool(
                    "search_media",
                    {
                        "context": {"session_id": str(uuid4()), "run_id": str(uuid4())},
                        "args": {},
                    },
                )
                self.assertTrue(result.is_error)
                self.assertNotIn("foreign run secret", str(result))

    async def test_proposals_are_only_pending_and_never_call_confirm(self):
        async with self.bridge() as (url, _):
            async with sdk(url, TOKEN_A) as session:
                for name, args in PROPOSAL_ARGS.items():
                    result = await session.call_tool(
                        name, {"context": CONTEXT, "args": args}
                    )
                    self.assertFalse(result.is_error)
                    self.assertEqual(result.structured_content["state"], "pending")
                    self.assertEqual(
                        result.structured_content["kind"], name.removeprefix("propose_")
                    )
        self.assertEqual([c[1] for c in self.calls], list(PROPOSAL_ARGS))

    async def test_read_retry_once_proposal_no_automatic_retry(self):
        async with self.bridge() as (url, _):
            async with sdk(url, TOKEN_A) as session:
                for name, (args, _) in READ_CASES.items():
                    with self.subTest(tool=name):
                        self.calls.clear()
                        self.failures = 1
                        read = await session.call_tool(
                            name, {"context": CONTEXT, "args": args}
                        )
                        self.assertFalse(read.is_error, str(read))
                        self.assertEqual(len(self.calls), 2)
                for name, args in PROPOSAL_ARGS.items():
                    with self.subTest(tool=name):
                        self.calls.clear()
                        self.failures = 1
                        proposal = await session.call_tool(
                            name, {"context": CONTEXT, "args": args}
                        )
                        self.assertTrue(proposal.is_error)
                        self.assertEqual(len(self.calls), 1)
                        self.assertNotIn("secret path", str(proposal))

    async def test_missing_authorization_rejected_on_every_transport_method(self):
        async with self.bridge() as (url, _):
            async with httpx2.AsyncClient(trust_env=False) as http:
                for method in ("POST", "GET", "DELETE"):
                    r = await http.request(method, url + "/mcp", json={})
                    self.assertEqual(r.status_code, 401)
        self.assertEqual(self.calls, [])

    async def test_client_rejects_unknown_path_and_invalid_result(self):
        async with self.bridge() as (_, client):
            with self.assertRaises(self.client.ToolError):
                await client.call_he_tool(TOKEN_A, "../confirm", CONTEXT, {})
            self.assertEqual(self.calls, [])

            async def invalid(request):
                return httpx2.Response(
                    200,
                    stream=httpx2.ByteStream(
                        json.dumps(
                            {
                                "tool_call_id": str(uuid4()),
                                "tool_name": "search_media",
                                "result": {
                                    "items": [],
                                    "total": 0,
                                    "password": "secret",
                                },
                            }
                        ).encode()
                    ),
                )

            async with self.client.HeToolClient(
                base_url="http://he-tools:8021", transport=httpx2.MockTransport(invalid)
            ) as client:
                with self.assertRaises(self.client.ToolError) as caught:
                    await client.call_he_tool(TOKEN_A, "search_media", CONTEXT, {})
                self.assertEqual(str(caught.exception), "he_invalid_tool_response")

    async def test_response_limit_timeout_attempt_count_and_redirect_never_leak_body(
        self,
    ):
        calls = []
        mode = "size"

        async def responder(request):
            calls.append(request)
            if mode == "timeout":
                raise httpx2.ReadTimeout("synthetic private token", request=request)
            if mode == "redirect":
                return httpx2.Response(
                    302,
                    headers={"location": "http://evil.test/secret"},
                    stream=httpx2.ByteStream(b"private secret path"),
                )
            return httpx2.Response(
                200, stream=httpx2.ByteStream(b"x" * (128 * 1024 + 1))
            )

        async with self.client.HeToolClient(
            base_url="http://he-tools:8021", transport=httpx2.MockTransport(responder)
        ) as client:
            with self.assertRaises(self.client.ToolError) as error:
                await client.call_he_tool(TOKEN_A, "search_media", CONTEXT, {})
            self.assertEqual(str(error.exception), "he_tool_response_too_large")
            self.assertEqual(len(calls), 1)
            calls.clear()
            mode = "timeout"
            with self.assertRaises(self.client.ToolError):
                await client.call_he_tool(TOKEN_A, "search_media", CONTEXT, {})
            self.assertEqual(len(calls), 2)
            calls.clear()
            with self.assertRaises(self.client.ToolError):
                await client.call_he_tool(
                    TOKEN_A, "propose_scan", CONTEXT, {"folder_id": 1}
                )
            self.assertEqual(len(calls), 1)
            calls.clear()
            mode = "redirect"
            with self.assertRaises(self.client.ToolError) as error:
                await client.call_he_tool(TOKEN_A, "search_media", CONTEXT, {})
            self.assertEqual(str(error.exception), "he_tool_rejected")
            self.assertEqual(len(calls), 1)
            self.assertEqual(
                str(calls[0].url), "http://he-tools:8021/tools/search_media"
            )

    async def test_historical_runtime_lock_is_preserved_without_private_he_runtime_imports(
        self,
    ):
        from pathlib import Path

        root = Path(__file__).resolve().parents[3]
        lock = json.loads((root / "deploy/hermes/runtime-lock.json").read_text())
        # This is evidence of the original H01 verification, not today's live
        # allowlist. Do not rewrite that historical attestation to make tests pass.
        self.assertEqual(set(lock["bridge"]["tool_names"]), HISTORICAL_NAMES)
        self.assertLess(HISTORICAL_NAMES, NAMES)
        self.assertEqual(
            set(lock["toolset_config"]["model_tool_names"]),
            {"mcp__he__" + n for n in HISTORICAL_NAMES} | {"memory"},
        )
        self.assertNotIn("app.database", sys.modules)
        self.assertNotIn("app.scanner", sys.modules)
        self.assertNotIn("app.main", sys.modules)


class RealHEIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_temporary_profile_search_propose_retry_reject_changes_no_media(self):
        # HE and MCP retain separate interpreters and dependency sets.
        python = os.environ.get("HE_TEST_PYTHON")
        if not python:
            self.skipTest("Set HE_TEST_PYTHON to the HE test interpreter")
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()
        process = subprocess.Popen(
            [
                python,
                "-m",
                "uvicorn",
                "integrations.he_mcp.tests.he_fixture_server:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--no-access-log",
                "--log-level",
                "critical",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            async with httpx2.AsyncClient(trust_env=False) as http:
                async with asyncio.timeout(25):
                    while True:
                        if process.poll() is not None:
                            self.fail("HE fixture exited before readiness")
                        try:
                            response = await http.get(
                                f"http://127.0.0.1:{port}/fixture/context"
                            )
                            if response.status_code == 200:
                                break
                        except httpx2.HTTPError:
                            pass
                        await asyncio.sleep(0.05)
                binding = response.json()
                self.assertEqual(binding["profile"], "he-user-1")
                from integrations.he_mcp.client import HeToolClient
                from integrations.he_mcp.server import create_app

                async with HeToolClient(base_url=f"http://127.0.0.1:{port}") as client:
                    async with serving(create_app(client=client)) as url:
                        async with sdk(url, binding["token"]) as session:
                            query = {
                                "context": binding["context"],
                                "args": {"query": "温馨"},
                            }
                            read = await session.call_tool("search_media", query)
                            self.assertFalse(read.is_error)
                            self.assertEqual(
                                read.structured_content["items"][0]["id"], 1
                            )
                            self.assertNotIn(
                                "absolute_path", json.dumps(read.structured_content)
                            )
                            self.assertNotIn(
                                "source_url", json.dumps(read.structured_content)
                            )
                            proposal_args = {
                                "context": binding["context"],
                                "args": {
                                    "media_id": 1,
                                    "patch": {
                                        "rating": 5,
                                        "add_tags": [{"name": "新的标签"}],
                                    },
                                },
                            }
                            first = await session.call_tool(
                                "propose_media_update", proposal_args
                            )
                            replay = await session.call_tool(
                                "propose_media_update", proposal_args
                            )
                            self.assertFalse(first.is_error)
                            self.assertEqual(
                                first.structured_content["state"], "pending"
                            )
                            self.assertEqual(
                                first.structured_content["id"],
                                replay.structured_content["id"],
                            )
                            proposal_id = first.structured_content["id"]
                            declined = await http.post(
                                f"http://127.0.0.1:{port}/fixture/reject/{proposal_id}"
                            )
                            self.assertEqual(declined.status_code, 200)
                            self.assertEqual(declined.json()["state"], "rejected")
                            invariant = (
                                await http.get(
                                    f"http://127.0.0.1:{port}/fixture/unchanged"
                                )
                            ).json()
                            self.assertEqual(
                                invariant,
                                {"unchanged": True, "proposals": 1, "audits": 0},
                            )
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
