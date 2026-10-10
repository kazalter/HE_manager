"""Isolated H01 fake model and same-name MCP stub. Never mount HE data here."""
from __future__ import annotations
import json
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

NAMES = ("search_media", "get_media_detail", "get_library_stats", "recommend_media",
         "list_duplicate_candidates", "list_tags", "list_folders", "propose_media_update", "propose_scan")
CAPTURES: list[dict] = []
CAPTURE_LOCK = threading.Lock()


def catalog_snapshot(body: dict) -> dict:
    text = json.dumps(body.get("messages", []), ensure_ascii=False)
    return {"tool_names": sorted(tool.get("function", {}).get("name", "") for tool in body.get("tools", [])),
            "max_tokens": body.get("max_tokens", body.get("max_completion_tokens")),
            "model": body.get("model"), "stream": body.get("stream", False),
            "memory_markers": sorted(set(re.findall(r"H01_ADMIN_\d+_LIKES_[A-Z]+", text)))}


def make_completion(body: dict) -> dict:
    messages = body.get("messages", [])
    text = " ".join(str(m.get("content", "")) for m in messages if m.get("role") == "user")
    tools = {t.get("function", {}).get("name", "") for t in body.get("tools", [])}
    message = {"role": "assistant", "content": "H01 synthetic operation completed."}
    finish = "stop"
    if "H01 LOOP" in text or not any(m.get("role") == "tool" for m in messages):
        name, args = None, {}
        if ("H01 SEARCH" in text or "H01 LOOP" in text) and "mcp__he__search_media" in tools:
            name, args = "mcp__he__search_media", {"query": "fixture"}
        if "H01 PROPOSAL" in text and "mcp__he__propose_scan" in tools:
            name, args = "mcp__he__propose_scan", {"folder_id": 1}
        if "H01 MEMORY-A" in text and "memory" in tools:
            name, args = "memory", {"action": "add", "target": "user", "content": "H01_ADMIN_1001_LIKES_RED"}
        if "H01 MEMORY-B" in text and "memory" in tools:
            name, args = "memory", {"action": "add", "target": "user", "content": "H01_ADMIN_1002_LIKES_BLUE"}
        if name:
            message = {"role": "assistant", "content": None, "tool_calls": [{"id": "call_h01_fixture", "type": "function",
                       "function": {"name": name, "arguments": json.dumps(args)}}]}
            finish = "tool_calls"
    return {"id": "chatcmpl_h01_fixture", "object": "chat.completion", "created": 1, "model": body.get("model", "h01-model"),
            "choices": [{"index": 0, "message": message, "finish_reason": finish}],
            "usage": {"prompt_tokens": 17, "completion_tokens": 9, "total_tokens": 26}}


class ProviderHandler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def send_json(self, code: int, result):
        raw = json.dumps(result).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path in ("/v1/models", "/models"):
            self.send_json(200, {"object": "list", "data": [{"id": "h01-model", "object": "model", "owned_by": "h01"}]})
        elif self.path == "/capture":
            with CAPTURE_LOCK:
                self.send_json(200, list(CAPTURES))
        else:
            self.send_json(200, {"status": "ok"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length > 2 * 1024 * 1024:
            self.send_json(413, {"error": "fixture_input_too_large"})
            return
        try:
            body = json.loads(self.rfile.read(length))
        except (ValueError, TypeError):
            self.send_json(400, {"error": "invalid_fixture_json"})
            return
        with CAPTURE_LOCK:
            CAPTURES.append(catalog_snapshot(body))
            del CAPTURES[:-100]
        if any("H01 SLOW" in str(m.get("content", "")) for m in body.get("messages", []) if m.get("role") == "user"):
            time.sleep(15)
        if any("H01 BUDGET" in str(m.get("content", "")) for m in body.get("messages", []) if m.get("role") == "user"):
            time.sleep(30)
        reply = make_completion(body)
        if not body.get("stream"):
            self.send_json(200, reply)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        message = reply["choices"][0]["message"]
        delta = {"role": "assistant"}
        if message.get("tool_calls"):
            delta["tool_calls"] = [{"index": i, **call} for i, call in enumerate(message["tool_calls"])]
        else:
            delta["content"] = message["content"]
        for data in (
            {"id": reply["id"], "object": "chat.completion.chunk", "created": 1, "model": reply["model"],
             "choices": [{"index": 0, "delta": delta, "finish_reason": None}]},
            {"id": reply["id"], "object": "chat.completion.chunk", "created": 1, "model": reply["model"],
             "choices": [{"index": 0, "delta": {}, "finish_reason": reply["choices"][0]["finish_reason"]}], "usage": reply["usage"]},
        ):
            self.wfile.write(("data: " + json.dumps(data) + "\n\n").encode())
            self.wfile.flush()
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()
        self.close_connection = True


def main():
    # Imports stay lazy: HE's test environment does not need the MCP runtime installed.
    import uvicorn
    from mcp.server import MCPServer
    from mcp.types import ToolAnnotations
    from mcp.server.transport_security import TransportSecuritySettings
    config = json.loads(Path("/probe/service-config.json").read_text())
    tokens = config["tool_tokens"]
    server = MCPServer("he-h01-fixed-fixture")

    def register(name):
        async def tool(query: str = "", media_id: int = 1, folder_id: int = 1, limit: int = 20,
                       offset: int = 0, patch: dict | None = None) -> dict[str, Any]:
            if name.startswith("propose_"):
                return {"id": "10000000-0000-0000-0000-000000000001", "kind": "scan" if name == "propose_scan" else "media_update",
                        "target_id": folder_id if name == "propose_scan" else media_id, "target_label": "H01 fake target",
                        "state": "pending", "expires_at": "2099-01-01T00:00:00Z"}
            if name == "get_library_stats":
                return {"total": 1, "by_type": {"manga": 1}, "favorite_count": 0, "watched_count": 0}
            if name == "get_media_detail":
                return {"id": media_id, "title": "H01 fake manga", "media_type": "manga", "tags": []}
            if name == "list_folders":
                return {"items": [{"id": 1, "display_name": "H01 fake folder", "status": "ready"}], "total": 1}
            return {"items": [{"id": 1, "title": "H01 fake manga", "media_type": "manga", "tags": []}],
                    "total": 1, "offset": offset, "has_more": False}
        server.tool(name=name, structured_output=True, annotations=ToolAnnotations(read_only_hint=not name.startswith("propose_")))(tool)

    for name in NAMES:
        register(name)
    app = server.streamable_http_app(stateless_http=True, json_response=True, host="0.0.0.0",
        transport_security=TransportSecuritySettings(allowed_hosts=["he-hermes-h01-services:*", "localhost:*", "127.0.0.1:*"], allowed_origins=[]))

    class BearerGuard:
        async def __call__(self, scope, receive, send):
            if scope["type"] == "http":
                headers = dict(scope.get("headers", []))
                token = headers.get(b"authorization", b"").decode()
                if token not in {"Bearer " + value for value in tokens.values()}:
                    await send({"type": "http.response.start", "status": 401, "headers": [(b"content-type", b"application/json")]})
                    await send({"type": "http.response.body", "body": b'{"error":"unauthorized"}'})
                    return
            await app(scope, receive, send)

    provider = ThreadingHTTPServer(("0.0.0.0", 8090), ProviderHandler)
    threading.Thread(target=provider.serve_forever, daemon=True).start()
    uvicorn.run(BearerGuard(), host="0.0.0.0", port=8020, access_log=False, log_level="warning")


if __name__ == "__main__":
    main()
