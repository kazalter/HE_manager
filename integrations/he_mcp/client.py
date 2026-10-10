"""Fixed HE tool endpoint, per-call credentials, bounded validated replies."""

import asyncio
import json
import os
import re
from urllib.parse import urlsplit
import httpx2
from pydantic import ValidationError
from app.assistant import schemas

from app.assistant.tool_catalog import TOOL_CATALOG, READ_TOOLS
from app.assistant.tool_errors import MESSAGES
NAMES = frozenset(TOOL_CATALOG)


class ToolError(Exception):
    pass


def valid_token(token):
    return (
        isinstance(token, str)
        and re.fullmatch(r"[A-Za-z0-9._~-]{32,1000}", token) is not None
    )


class HeToolClient:
    def __init__(self, base_url=None, *, transport=None):
        base_url = base_url or os.getenv("HE_TOOLS_URL", "http://he-tools:8021")
        try:
            parts = urlsplit(base_url)
            if (
                parts.scheme not in ("http", "https")
                or not parts.hostname
                or parts.username
                or parts.password
                or parts.path not in ("", "/")
                or parts.query
                or parts.fragment
            ):
                raise ValueError
            _ = parts.port
        except ValueError:
            raise ToolError("he_tool_configuration_invalid") from None
        self.base_url = base_url.rstrip("/")
        self.http = httpx2.AsyncClient(
            transport=transport,
            trust_env=False,
            follow_redirects=False,
            timeout=10,
            limits=httpx2.Limits(max_connections=8, max_keepalive_connections=4),
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        await self.aclose()

    async def aclose(self):
        await self.http.aclose()

    async def call_he_tool(self, token, name, context, args):
        if not valid_token(token):
            raise ToolError("he_tool_authorization_required")
        if name not in NAMES:
            raise ToolError("he_unknown_tool")
        try:
            context = schemas.ToolContext.model_validate(context)
            payload = json.dumps(
                {"context": context.model_dump(mode="json"), "args": args},
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode()
            if len(payload) > 65536:
                raise ValueError
        except (ValidationError, TypeError, ValueError):
            raise ToolError("he_invalid_tool_arguments") from None
        attempts = 2 if name in READ_TOOLS else 1
        for attempt in range(attempts):
            try:
                async with asyncio.timeout(12):
                    async with self.http.stream(
                        "POST",
                        self.base_url + "/tools/" + name,
                        headers={
                            "Authorization": "Bearer " + token,
                            "Content-Type": "application/json",
                            "Accept-Encoding": "identity",
                        },
                        content=payload,
                    ) as response:
                        if response.status_code in (429, 500, 502, 503, 504):
                            if attempt + 1 < attempts:
                                continue
                            raise ToolError("he_tool_unavailable")
                        if response.status_code != 200:
                            raw_error = bytearray()
                            async for chunk in response.aiter_raw(4096):
                                if len(raw_error) + len(chunk) > 8192:
                                    raise ToolError("he_tool_rejected")
                                raw_error.extend(chunk)
                            try:
                                error = schemas.ToolErrorDTO.model_validate_json(raw_error)
                                if error.code not in MESSAGES:
                                    raise ValueError
                            except (ValueError, ValidationError):
                                raise ToolError("he_tool_rejected") from None
                            raise ToolError(error.code + ": " + MESSAGES[error.code] + " [" + error.request_id[:36] + "]")
                        if response.headers.get("content-encoding", "identity") not in (
                            "",
                            "identity",
                        ):
                            raise ToolError("he_invalid_tool_response")
                        raw = bytearray()
                        async for chunk in response.aiter_raw(16384):
                            if len(raw) + len(chunk) > 128 * 1024:
                                raise ToolError("he_tool_response_too_large")
                            raw.extend(chunk)
                        try:
                            result = schemas.ToolResultDTO.model_validate_json(raw)
                            if result.tool_name != name:
                                raise ValueError
                        except (ValidationError, ValueError, TypeError):
                            raise ToolError("he_invalid_tool_response") from None
                        return result.result.model_dump(mode="json", exclude_unset=True)
            except (httpx2.HTTPError, TimeoutError):
                if attempt + 1 >= attempts:
                    raise ToolError("he_tool_unavailable") from None
        raise ToolError("he_tool_unavailable")
