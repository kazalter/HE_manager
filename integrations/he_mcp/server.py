"""MCP SDK 2.0 Streamable HTTP; credentials come only from this HTTP request."""

from contextlib import asynccontextmanager
from typing import Any
from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from starlette.responses import JSONResponse
from starlette.routing import Route
from app.assistant import schemas
from .client import HeToolClient, READ_TOOLS, valid_token, ToolError


from app.assistant.tool_catalog import TOOL_CATALOG
ARGS = {name: spec.args_type for name, spec in TOOL_CATALOG.items()}
DESCRIPTIONS = {name: spec.description for name, spec in TOOL_CATALOG.items()}


class BearerMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["path"].rstrip("/") == "/mcp":
            values = [
                v.decode("latin-1")
                for k, v in scope.get("headers", [])
                if k.lower() == b"authorization"
            ]
            if (
                len(values) != 1
                or not values[0].startswith("Bearer ")
                or not valid_token(values[0][7:])
            ):
                await JSONResponse(
                    {"error": "he_tool_authorization_required"}, status_code=401
                )(scope, receive, send)
                return
        await self.app(scope, receive, send)


def create_app(*, client=None):
    owned = client is None
    client = client or HeToolClient()

    @asynccontextmanager
    async def lifespan(_):
        try:
            yield {}
        finally:
            if owned:
                await client.aclose()

    mcp = MCPServer("he", lifespan=lifespan)

    def register(name, model):
        async def invoke(
            context: schemas.ToolContext, args, ctx: Context
        ) -> dict[str, Any]:
            request = ctx.request_context.request
            header = (
                request.headers.get("authorization", "") if request is not None else ""
            )
            if not header.startswith("Bearer ") or not valid_token(header[7:]):
                raise ToolError("he_tool_authorization_required")
            return await client.call_he_tool(
                header[7:],
                name,
                context,
                args.model_dump(mode="json", exclude_unset=True),
            )

        invoke.__annotations__["args"] = model
        invoke.__name__ = name
        mcp.tool(
            name=name,
            description=DESCRIPTIONS[name],
            annotations=ToolAnnotations(
                read_only_hint=name in READ_TOOLS,
                destructive_hint=False,
                idempotent_hint=True,
                open_world_hint=False,
            ),
            structured_output=True,
        )(invoke)

    for name, model in ARGS.items():
        register(name, model)
    app = mcp.streamable_http_app(
        stateless_http=True,
        json_response=True,
        max_request_body_size=65536,
        host="0.0.0.0",
        transport_security=TransportSecuritySettings(
            allowed_hosts=["he-mcp:8020", "127.0.0.1:*", "localhost:*"],
            allowed_origins=[],
        ),
    )

    async def health(_request):
        return JSONResponse({"status": "ok", "tools": len(ARGS)})

    app.routes.append(Route("/healthz", health, methods=["GET"]))
    app.add_middleware(BearerMiddleware)
    return app


app = create_app()
