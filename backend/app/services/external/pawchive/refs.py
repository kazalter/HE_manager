"""Short-lived, signed media and pagination references."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time

from app.external_config import CONFIG_PATH

logger = logging.getLogger(__name__)
SECRET_PATH = os.path.join(os.path.dirname(CONFIG_PATH) or ".", "pawchive_stream.key")
# Open viewers keep refs for a whole browsing session; expiry only bounds replay
# of already-validated, authenticated media paths.
MEDIA_TTL = 12 * 3600
# Media expiry is rounded up to this step so a file keeps the same URL across
# list refreshes and stays in the browser cache; refs then live 12-18 hours.
MEDIA_EXPIRY_STEP = 6 * 3600
CURSOR_TTL = 12 * 3600


def _load_secret() -> bytes:
    """Keep refs valid across restarts: env override, else a persisted key."""
    configured = (os.getenv("HE_PAWCHIVE_STREAM_SECRET") or "").encode()
    if configured:
        return configured
    try:
        with open(SECRET_PATH, "rb") as handle:
            stored = handle.read().strip()
        if len(stored) >= 32:
            return stored
    except OSError:
        pass
    generated = secrets.token_hex(32).encode()
    try:
        os.makedirs(os.path.dirname(SECRET_PATH) or ".", mode=0o700, exist_ok=True)
        temp_path = f"{SECRET_PATH}.{secrets.token_hex(4)}.tmp"
        descriptor = os.open(temp_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(generated)
        os.replace(temp_path, SECRET_PATH)
    except OSError:
        logger.warning("Pawchive stream key not persisted; refs reset on restart", exc_info=True)
    return generated


_secret = _load_secret()


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
    expires = -(-(int(time.time()) + MEDIA_TTL) // MEDIA_EXPIRY_STEP) * MEDIA_EXPIRY_STEP
    return _encode({"kind": kind, "path": path, "exp": expires})


def read_media(token: str) -> tuple[str, str]:
    payload = _decode(token)
    if payload.get("kind") not in {"image", "video", "preview"}:
        raise ValueError("invalid media kind")
    return str(payload.get("path") or ""), payload["kind"]


def sign_cursor(offset: int, scope_key: str) -> str:
    return _encode({"offset": offset, "scope": scope_key, "exp": int(time.time()) + CURSOR_TTL})


def read_cursor(token: str, scope_key: str) -> int:
    payload = _decode(token)
    if payload.get("scope") != scope_key or not isinstance(payload.get("offset"), int):
        raise ValueError("cursor does not match scope")
    offset = payload["offset"]
    if offset < 0 or offset % 50:
        raise ValueError("invalid cursor offset")
    return offset
