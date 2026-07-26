from datetime import datetime, timedelta
import hashlib
import hmac
import os
import secrets

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


def authenticate_access_token(db: Session, raw_token: str) -> models.User:
    db_token = (
        db.query(models.AccessToken)
        .filter(models.AccessToken.token_hash == hash_token(raw_token), models.AccessToken.revoked == False)
        .first()
    )
    if not db_token or not db_token.user or not db_token.user.is_active:
        raise HTTPException(status_code=401, detail="Invalid access token")

    if db_token.created_at and datetime.utcnow() - db_token.created_at > timedelta(days=ACCESS_TOKEN_TTL_DAYS):
        db_token.revoked = True
        db.commit()
        raise HTTPException(status_code=401, detail="Access token expired")

    now = datetime.utcnow()
    if (
        not db_token.last_used_at
        or (now - db_token.last_used_at).total_seconds() >= ACCESS_TOKEN_TOUCH_INTERVAL_SECONDS
    ):
        db_token.last_used_at = now
        db.commit()
    return db_token.user


def revoke_access_token(db: Session, raw_token: str) -> bool:
    db_token = (
        db.query(models.AccessToken)
        .filter(models.AccessToken.token_hash == hash_token(raw_token), models.AccessToken.revoked == False)
        .first()
    )
    if not db_token:
        return False
    db_token.revoked = True
    db.commit()
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
