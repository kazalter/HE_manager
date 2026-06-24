import os
import time

from fastapi import Request


LOGIN_FAILURES: dict[str, list[float]] = {}
LOGIN_FAILURE_WINDOW_SECONDS = int(os.getenv("HE_LOGIN_FAILURE_WINDOW_SECONDS", "300"))
LOGIN_MAX_FAILURES = int(os.getenv("HE_LOGIN_MAX_FAILURES", "5"))
# Per-username backstop independent of client IP. The IP+username bucket above
# can be defeated by an attacker who rotates a forged X-Forwarded-For on every
# request; this counter keys on the username alone so it survives that.
LOGIN_MAX_FAILURES_PER_USER = int(os.getenv("HE_LOGIN_MAX_FAILURES_PER_USER", "15"))
# Only honour X-Forwarded-For when explicitly told to by a trusted reverse proxy.
_TRUST_FORWARDED_FOR = os.getenv("HE_TRUST_FORWARDED_FOR", "").lower() in {"1", "true", "yes", "on"}


def _client_ip(request: Request) -> str:
    if _TRUST_FORWARDED_FOR:
        forwarded = (request.headers.get("x-forwarded-for") or "").split(",", 1)[0].strip()
        if forwarded:
            return forwarded
    return request.client.host if request.client else "unknown"


def _login_failure_key(request: Request, username: str) -> str:
    return f"{_client_ip(request)}:{username.strip().lower()}"


def _pruned_login_failures(key: str) -> list[float]:
    now = time.time()
    failures = [ts for ts in LOGIN_FAILURES.get(key, []) if now - ts <= LOGIN_FAILURE_WINDOW_SECONDS]
    if failures:
        LOGIN_FAILURES[key] = failures
    else:
        LOGIN_FAILURES.pop(key, None)
    return failures


def _record_login_failure(key: str) -> None:
    failures = _pruned_login_failures(key)
    failures.append(time.time())
    LOGIN_FAILURES[key] = failures
