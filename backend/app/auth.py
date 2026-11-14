from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib
import hmac
import os
import secrets
import threading
import time

from fastapi import Depends, Header, HTTPException, Query, Request
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from . import models
from .database import get_db


PASSWORD_ITERATIONS = 260_000
ACCESS_TOKEN_TTL_DAYS = int(os.getenv("HE_ACCESS_TOKEN_TTL_DAYS", "30"))
ACCESS_TOKEN_TOUCH_INTERVAL_SECONDS = max(
    60, int(os.getenv("HE_ACCESS_TOKEN_TOUCH_INTERVAL_SECONDS", "600"))
)
ACCESS_TOKEN_RETENTION_DAYS = max(
    1, int(os.getenv("HE_ACCESS_TOKEN_RETENTION_DAYS", "7"))
)
AUTH_CACHE_TTL_SECONDS = max(
    0.0, float(os.getenv("HE_AUTH_CACHE_TTL_SECONDS", "20"))
)
AUTH_CACHE_MAX_SIZE = 256


@dataclass(frozen=True)
class CachedAuthUser:
    """Read-only user snapshot cached across high-frequency static/API requests."""

    id: int
    username: str
    is_admin: bool
    is_active: bool
    created_at: datetime


@dataclass
class _AuthCacheEntry:
    user: CachedAuthUser
    cached_at: float
    token_expires_at: datetime | None
    next_touch_at: datetime


_auth_cache: OrderedDict[str, _AuthCacheEntry] = OrderedDict()
_auth_cache_lock = threading.Lock()


def invalidate_auth_cache() -> None:
    """Clear all cached request auth snapshots."""
    with _auth_cache_lock:
        _auth_cache.clear()


def invalidate_token_hash(token_hash: str) -> None:
    """Evict a single token hash from the request auth cache."""
    with _auth_cache_lock:
        _auth_cache.pop(token_hash, None)


def invalidate_user_auth_cache(user_id: int) -> None:
    """Evict all cached token snapshots belonging to a user."""
    with _auth_cache_lock:
        keys = [key for key, entry in _auth_cache.items() if entry.user.id == user_id]
        for key in keys:
            _auth_cache.pop(key, None)


def query_token_allowed(method: str, path: str) -> bool:
    """Limit URL tokens to binary GETs that cannot reliably set headers."""
    if method.upper() != "GET":
        return False
    norm = path[4:] if path.startswith("/api/") else path
    parts = [part for part in norm.split("/") if part]
    if len(parts) == 2 and parts[0] in {"thumbnails", "stream"}:
        return True
    if len(parts) == 3 and parts[:2] in (["mobile", "thumbnails"], ["mobile", "stream"]):
        return True
    if len(parts) == 4 and parts[0] == "manga" and parts[2] == "page":
        return True
    if len(parts) == 5 and parts[:2] == ["mobile", "manga"] and parts[3] == "page":
        return True
    if len(parts) == 4 and parts[0] == "audio" and parts[2] == "track":
        return True
    if len(parts) == 4 and parts[:2] == ["external", "favorites"] and parts[3] == "cover":
        return True
    if len(parts) == 4 and parts[:3] == ["external", "pawchive", "media"]:
        return True
    if len(parts) == 6 and parts[:3] == ["external", "pawchive", "creator-image"]:
        return True
    return False


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS)
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        scheme, iterations, salt_hex, digest_hex = password_hash.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt_hex),
            int(iterations),
        )
        return hmac.compare_digest(digest.hex(), digest_hex)
    except Exception:
        return False


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def cleanup_access_tokens(db: Session, now: datetime | None = None) -> int:
    """Remove expired tokens and old revoked tokens from the persistent store."""
    now = now or datetime.utcnow()
    expired_before = now - timedelta(days=ACCESS_TOKEN_TTL_DAYS)
    revoked_before = now - timedelta(days=ACCESS_TOKEN_RETENTION_DAYS)
    deleted = (
        db.query(models.AccessToken)
        .filter(or_(
            models.AccessToken.created_at < expired_before,
            and_(
                models.AccessToken.revoked == True,
                models.AccessToken.created_at < revoked_before,
            ),
        ))
        .delete(synchronize_session=False)
    )
    if deleted:
        db.commit()
        invalidate_auth_cache()
    return int(deleted or 0)


def create_access_token(db: Session, user: models.User) -> str:
    cleanup_access_tokens(db)
    token = secrets.token_urlsafe(32)
    db_token = models.AccessToken(token_hash=hash_token(token), user=user)
    db.add(db_token)
    db.commit()
    return token


def token_from_authorization(authorization: str | None) -> str | None:
    if not authorization:
        return None
    prefix = "Bearer "
    if not authorization.startswith(prefix):
        return None
    return authorization[len(prefix):].strip() or None


def extract_token(authorization: str | None = None, query_token: str | None = None) -> str | None:
    return query_token or token_from_authorization(authorization)


def _authenticate_access_token_row(db: Session, raw_token: str) -> tuple[models.User, models.AccessToken]:
    token_hash = hash_token(raw_token)
    db_token = (
        db.query(models.AccessToken)
        .filter(models.AccessToken.token_hash == token_hash, models.AccessToken.revoked == False)
        .first()
    )
    if not db_token or not db_token.user or not db_token.user.is_active:
        invalidate_token_hash(token_hash)
        raise HTTPException(status_code=401, detail="Invalid access token")

    now = datetime.utcnow()
    if db_token.created_at and now - db_token.created_at > timedelta(days=ACCESS_TOKEN_TTL_DAYS):
        db_token.revoked = True
        db.commit()
        invalidate_token_hash(token_hash)
        raise HTTPException(status_code=401, detail="Access token expired")

    if (
        not db_token.last_used_at
        or (now - db_token.last_used_at).total_seconds() >= ACCESS_TOKEN_TOUCH_INTERVAL_SECONDS
    ):
        db_token.last_used_at = now
        db.commit()
    return db_token.user, db_token


def authenticate_access_token(db: Session, raw_token: str) -> models.User:
    user, _ = _authenticate_access_token_row(db, raw_token)
    return user


_UNPATCHED_AUTHENTICATE_ACCESS_TOKEN = authenticate_access_token


def get_cached_request_user(raw_token: str) -> CachedAuthUser | None:
    """Return a cached user snapshot for middleware when still fresh and active."""
    if AUTH_CACHE_TTL_SECONDS <= 0:
        return None
    token_hash = hash_token(raw_token)
    mono_now = time.monotonic()
    utc_now = datetime.utcnow()
    with _auth_cache_lock:
        entry = _auth_cache.get(token_hash)
        if entry is None:
            return None
        if (
            mono_now - entry.cached_at >= AUTH_CACHE_TTL_SECONDS
            or (entry.token_expires_at is not None and utc_now > entry.token_expires_at)
            or utc_now >= entry.next_touch_at
            or not entry.user.is_active
        ):
            _auth_cache.pop(token_hash, None)
            return None
        _auth_cache.move_to_end(token_hash)
        return entry.user


def _cache_authenticated_user(
    token_hash: str,
    db_token: models.AccessToken,
    user: models.User,
) -> CachedAuthUser:
    snapshot = CachedAuthUser(
        id=user.id,
        username=user.username,
        is_admin=bool(user.is_admin),
        is_active=bool(user.is_active),
        created_at=user.created_at,
    )
    if AUTH_CACHE_TTL_SECONDS <= 0:
        return snapshot
    token_expires_at = (
        db_token.created_at + timedelta(days=ACCESS_TOKEN_TTL_DAYS)
        if db_token.created_at
        else None
    )
    touch_base = db_token.last_used_at or datetime.utcnow()
    next_touch_at = touch_base + timedelta(seconds=ACCESS_TOKEN_TOUCH_INTERVAL_SECONDS)
    with _auth_cache_lock:
        _auth_cache[token_hash] = _AuthCacheEntry(
            user=snapshot,
            cached_at=time.monotonic(),
            token_expires_at=token_expires_at,
            next_touch_at=next_touch_at,
        )
        _auth_cache.move_to_end(token_hash)
        while len(_auth_cache) > AUTH_CACHE_MAX_SIZE:
            _auth_cache.popitem(last=False)
    return snapshot


def authenticate_request_token(db: Session, raw_token: str) -> CachedAuthUser | models.User:
    """Authenticate an HTTP request token using the short-TTL cache on hits."""
    cached = get_cached_request_user(raw_token)
    if cached is not None:
        return cached
    if authenticate_access_token is not _UNPATCHED_AUTHENTICATE_ACCESS_TOKEN:
        return authenticate_access_token(db, raw_token)
    user, db_token = _authenticate_access_token_row(db, raw_token)
    return _cache_authenticated_user(db_token.token_hash, db_token, user)


def revoke_access_token(db: Session, raw_token: str) -> bool:
    token_hash = hash_token(raw_token)
    db_token = (
        db.query(models.AccessToken)
        .filter(models.AccessToken.token_hash == token_hash, models.AccessToken.revoked == False)
        .first()
    )
    if not db_token:
        invalidate_token_hash(token_hash)
        return False
    db_token.revoked = True
    db.commit()
    invalidate_token_hash(token_hash)
    return True


def get_current_user(
    request: Request,
    authorization: str | None = Header(default=None),
    token: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> models.User:
    state_user = getattr(request.state, "current_user", None)
    if state_user is not None:
        return state_user

    query_token = token if query_token_allowed(request.method, request.url.path) else None
    raw_token = extract_token(authorization, query_token)
    if not raw_token:
        raise HTTPException(status_code=401, detail="Missing access token")

    return authenticate_access_token(db, raw_token)


def require_admin(user: models.User = Depends(get_current_user)) -> models.User:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin permission required")
    return user
