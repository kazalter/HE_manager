"""Pinned Hermes HTTP/SSE transport. Raw responses remain private to this adapter."""

import asyncio
import json
import re
from urllib.parse import urlsplit
from uuid import UUID
import httpx
from .store import canonical_json

JSON_LIMIT = 8 * 1024 * 1024
EVENT_LIMIT = 128 * 1024


class UpstreamError(Exception):
    def __init__(self, code, http_status=None):
        self.code = code
        self.http_status = http_status
        super().__init__(code)


def event_from_lines(lines):
    data = []
    event_id = None
    for line in lines:
        if line.startswith(b"data:"):
            data.append(line[5:].removeprefix(b" "))
        elif line.startswith(b"id:"):
            event_id = line[3:].strip()
    if not data:
        return None
    try:
        value = json.loads(b"\n".join(data).decode("utf-8"))
        seq = value["seq"]
        if (
            not isinstance(value, dict)
            or type(seq) is not int
            or seq < 0
            or (event_id is not None and event_id != str(seq).encode())
        ):
            raise ValueError
        return value
    except (ValueError, UnicodeError, KeyError, TypeError, RecursionError):
        raise UpstreamError("upstream_invalid_response") from None


async def iter_sse(chunks):
    """Check received bytes before buffering/parsing, including incomplete lines."""
    buffer = bytearray()
    lines = []
    event_bytes = 0
    first = True
    async for chunk in chunks:
        if not isinstance(chunk, bytes):
            raise UpstreamError("upstream_invalid_response")
        # Each received chunk is scanned before a growing event is allocated.
        start = 0
        while start < len(chunk):
            end = chunk.find(b"\n", start)
            end = len(chunk) if end < 0 else end + 1
            piece = chunk[start:end]
            if event_bytes + len(piece) > EVENT_LIMIT:
                raise UpstreamError("upstream_response_too_large")
            event_bytes += len(piece)
            buffer.extend(piece)
            start = end
            if not buffer.endswith(b"\n"):
                continue
            line = bytes(buffer[:-1]).removesuffix(b"\r")
            buffer.clear()
            if first:
                line = line.removeprefix(b"\xef\xbb\xbf")
                first = False
            if not line:
                value = event_from_lines(lines)
                lines = []
                event_bytes = 0
                if value is not None:
                    yield value
            elif not line.startswith(b":"):
                lines.append(line)
    if buffer:
        lines.append(bytes(buffer).removesuffix(b"\r"))
    if lines:
        value = event_from_lines(lines)
        if value is not None:
            yield value


class HermesClient:
    def __init__(self, base_url="http://hermes:8642", *, transport=None):
        try:
            parts = urlsplit(base_url)
            if (
                parts.scheme not in ("http", "https")
                or not parts.hostname
                or parts.username
                or parts.password
                or parts.query
                or parts.fragment
                or parts.path not in ("", "/")
            ):
                raise ValueError
            _ = parts.port
        except ValueError:
            raise UpstreamError("assistant_upstream_unconfigured") from None
        self.base_url = base_url.rstrip("/")
        self.http = httpx.AsyncClient(
            transport=transport,
            timeout=httpx.Timeout(10, read=15),
            limits=httpx.Limits(max_connections=8, max_keepalive_connections=4),
            follow_redirects=False,
            trust_env=False,
        )
        self.stream_http = httpx.AsyncClient(
            transport=transport,
            timeout=httpx.Timeout(10, read=15),
            limits=httpx.Limits(max_connections=2, max_keepalive_connections=2),
            follow_redirects=False,
            trust_env=False,
        )

    def _url(self, profile, path):
        if profile.profile_name != "he-user-" + str(profile.user_id):
            raise UpstreamError("assistant_invalid_profile")
        return self.base_url + "/p/" + profile.profile_name + path

    def _headers(self, profile):
        return {
            "Authorization": "Bearer " + profile.api_key.get_secret_value(),
            "Accept-Encoding": "identity",
        }

    @staticmethod
    def run_id(value):
        if not isinstance(value, str) or not re.fullmatch(r"run_[0-9a-f]{32}", value):
            raise UpstreamError("upstream_invalid_response")
        return value

    @staticmethod
    def session_id(value):
        try:
            if (
                not isinstance(value, str)
                or not value.startswith("he-")
                or "he-" + str(UUID(value[3:])) != value
            ):
                raise ValueError
        except ValueError:
            raise UpstreamError("upstream_invalid_response") from None
        return value

    async def _json(self, profile, method, path, *, body=None, headers=None):
        attempts = 2 if method == "GET" else 1
        for attempt in range(attempts):
            try:
                async with asyncio.timeout(15):
                    async with self.http.stream(
                        method,
                        self._url(profile, path),
                        headers={**self._headers(profile), **(headers or {})},
                        content=(
                            canonical_json(body).encode() if body is not None else None
                        ),
                    ) as response:
                        status = response.status_code
                        if status == 429:
                            raise UpstreamError("upstream_busy", status)
                        if status >= 500:
                            raise UpstreamError("upstream_unavailable", status)
                        if status == 404:
                            raise UpstreamError("upstream_not_found", status)
                        if status == 409:
                            raise UpstreamError("upstream_conflict", status)
                        if status not in (200, 201, 202):
                            raise UpstreamError("upstream_rejected", status)
                        if response.headers.get("content-encoding", "identity") not in (
                            "",
                            "identity",
                        ):
                            raise UpstreamError("upstream_invalid_response")
                        raw = bytearray()
                        async for chunk in response.aiter_raw(16384):
                            if len(raw) + len(chunk) > JSON_LIMIT:
                                raise UpstreamError("upstream_response_too_large")
                            raw.extend(chunk)
                        try:
                            value = json.loads(raw)
                            if not isinstance(value, dict):
                                raise ValueError
                        except (ValueError, UnicodeError, RecursionError):
                            raise UpstreamError("upstream_invalid_response") from None
                        return value
            except (httpx.HTTPError, TimeoutError):
                if attempt + 1 >= attempts:
                    raise UpstreamError("upstream_unavailable") from None
            except UpstreamError as exc:
                if attempt + 1 >= attempts or exc.code not in (
                    "upstream_busy",
                    "upstream_unavailable",
                ):
                    raise
        raise UpstreamError("upstream_unavailable")

    async def _session(self, profile, sid):
        value = await self._json(profile, "GET", "/api/sessions/" + sid)
        row = value.get("session")
        if (
            not isinstance(row, dict)
            or row.get("id") != sid
            or row.get("source") != "api_server"
        ):
            raise UpstreamError("upstream_invalid_response")
        return sid

    async def create_session(self, profile, he_session_id):
        sid = self.session_id("he-" + str(UUID(str(he_session_id))))
        try:
            return await self._session(profile, sid)
        except UpstreamError as exc:
            if exc.http_status != 404:
                raise
        try:
            value = await self._json(
                profile,
                "POST",
                "/api/sessions",
                body={"id": sid, "source": "api_server"},
                headers={"Content-Type": "application/json"},
            )
            row = value.get("session")
            if (
                not isinstance(row, dict)
                or row.get("id") != sid
                or row.get("source") != "api_server"
            ):
                raise UpstreamError("upstream_invalid_response")
            return sid
        except UpstreamError as exc:
            if exc.code not in (
                "upstream_conflict",
                "upstream_unavailable",
                "upstream_busy",
            ):
                raise
            return await self._session(profile, sid)

    async def start_run(self, profile, envelope):
        body = {
            k: getattr(envelope, k)
            for k in ("input", "instructions", "provider", "model", "session_id")
        }
        # Iteration and token limits are enforced by the H01-verified profile,
        # not invented per-request parameters ignored by the pinned gateway.
        value = await self._json(
            profile,
            "POST",
            "/v1/runs",
            body=body,
            headers={
                "Content-Type": "application/json",
                "Idempotency-Key": envelope.idempotency_key,
            },
        )
        return self.run_id(value.get("run_id"))

    async def get_run(self, profile, upstream_run_id):
        rid = self.run_id(upstream_run_id)
        value = await self._json(profile, "GET", "/v1/runs/" + rid)
        if value.get("run_id") != rid:
            raise UpstreamError("upstream_invalid_response")
        return value

    async def stop_run(self, profile, upstream_run_id):
        rid = self.run_id(upstream_run_id)
        value = await self._json(profile, "POST", "/v1/runs/" + rid + "/stop")
        if value.get("run_id") != rid or value.get("status") not in (
            "stopping",
            "completed",
            "failed",
            "cancelled",
            "interrupted",
        ):
            raise UpstreamError("upstream_invalid_response")
        return value

    async def delete_session(self, profile, upstream_session_id):
        try:
            await self._json(
                profile,
                "DELETE",
                "/api/sessions/" + self.session_id(upstream_session_id),
            )
        except UpstreamError as exc:
            if exc.http_status != 404:
                raise

    async def get_messages(self, profile, upstream_session_id, *, limit=100, offset=0):
        if not 1 <= limit <= 100 or offset < 0:
            raise UpstreamError("assistant_invalid_pagination")
        value = await self._json(
            profile,
            "GET",
            "/api/sessions/"
            + self.session_id(upstream_session_id)
            + "/messages?limit="
            + str(limit)
            + "&offset="
            + str(offset)
            + "&order=oldest",
        )
        data = value.get("data")
        if not isinstance(data, list) or len(data) > 100:
            raise UpstreamError("upstream_invalid_response")
        # Caller never publishes raw Hermes history. HE's persisted run projection
        # is the display authority, without tool/system/reasoning messages.
        return value

    async def stream_events(self, profile, upstream_run_id, last_event_id=None):
        rid = self.run_id(upstream_run_id)
        headers = self._headers(profile)
        if last_event_id is not None:
            if not re.fullmatch(r"[0-9]{1,20}", str(last_event_id)):
                raise UpstreamError("assistant_invalid_event_cursor")
            headers["Last-Event-ID"] = str(last_event_id)
        try:
            async with self.stream_http.stream(
                "GET",
                self._url(profile, "/v1/runs/" + rid + "/events"),
                headers=headers,
            ) as response:
                if response.status_code == 404:
                    raise UpstreamError("upstream_events_expired", 404)
                if response.status_code != 200:
                    raise UpstreamError(
                        (
                            "upstream_busy"
                            if response.status_code == 429
                            else "upstream_unavailable"
                        ),
                        response.status_code,
                    )
                if response.headers.get("content-encoding", "identity") not in (
                    "",
                    "identity",
                ):
                    raise UpstreamError("upstream_invalid_response")
                async for event in iter_sse(response.aiter_raw(16384)):
                    yield event
        except httpx.HTTPError:
            raise UpstreamError("upstream_unavailable") from None

    async def aclose(self):
        await self.http.aclose()
        await self.stream_http.aclose()
