"""Short-lived, signed media and pagination references."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time

_secret = (os.getenv("HE_PAWCHIVE_STREAM_SECRET") or "").encode() or secrets.token_bytes(32)


def _encode(payload: dict) -> str:
    body = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()).rstrip(b"=")
    signature = hmac.new(_secret, body, hashlib.sha256).hexdigest()[:32]
    return body.decode() + "." + signature


def _decode(token: str) -> dict:
    try:
        body, signature = token.split(".", 1)
        if len(body) > 1024 or not hmac.compare_digest(
            hmac.new(_secret, body.encode(), hashlib.sha256).hexdigest()[:32], signature
        ):
            raise ValueError("invalid signature")
        payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        if not isinstance(payload, dict) or payload.get("exp", 0) < time.time():
            raise ValueError("expired")
        return payload
    except (ValueError, TypeError, KeyError) as exc:
        raise ValueError("invalid or expired reference") from exc


def sign_media(path: str, kind: str) -> str:
    return _encode({"kind": kind, "path": path, "exp": int(time.time()) + 3600})


def read_media(token: str) -> tuple[str, str]:
    payload = _decode(token)
    if payload.get("kind") not in {"image", "video", "preview"}:
        raise ValueError("invalid media kind")
    return str(payload.get("path") or ""), payload["kind"]


def sign_cursor(offset: int, scope_key: str) -> str:
    return _encode({"offset": offset, "scope": scope_key, "exp": int(time.time()) + 7200})


def read_cursor(token: str, scope_key: str) -> int:
    payload = _decode(token)
    if payload.get("scope") != scope_key or not isinstance(payload.get("offset"), int):
        raise ValueError("cursor does not match scope")
    offset = payload["offset"]
    if offset < 0 or offset % 50:
        raise ValueError("invalid cursor offset")
    return offset
