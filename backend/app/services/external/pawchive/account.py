"""Pawchive account sessions and account-scoped creator favorites."""
from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass, field
from http.cookies import SimpleCookie
from urllib.parse import quote

from . import client, provider

_sessions: dict[int, "AccountSession"] = {}
_sessions_lock = threading.RLock()
_COOKIE_NAME = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]{1,128}$")
_COOKIE_VALUE = re.compile(r"^[!\x23-\x2B\x2D-\x3A\x3C-\x5B\x5D-\x7E]*$")


@dataclass
class AccountSession:
    cookies: dict[str, str] = field(default_factory=dict)
    lock: threading.RLock = field(default_factory=threading.RLock)


def _merge_cookies(session: AccountSession, headers: list[tuple[str, str]]) -> None:
    for header, value in headers:
        if header.lower() != "set-cookie":
            continue
        parsed = SimpleCookie()
        try:
            parsed.load(value)
        except Exception:
            continue
        for name, morsel in parsed.items():
            cookie_value = morsel.value
            if not _COOKIE_NAME.fullmatch(name) or not _COOKIE_VALUE.fullmatch(cookie_value):
                continue
            if morsel["max-age"] == "0":
                session.cookies.pop(name, None)
            else:
                session.cookies[name] = cookie_value


def _request(session: AccountSession, target: str, *, method: str = "GET", form: dict[str, str] | None = None):
    status, headers, body = client.account_request(
        target,
        method=method,
        cookies=session.cookies,
        form=form,
    )
    _merge_cookies(session, headers)
    return status, body


def _upstream_error(status: int) -> client.PawchiveError:
    if status == 401:
        return client.PawchiveError("ACCOUNT_AUTH_REQUIRED", "Pawchive 登录已失效，请重新登录", 401)
    if status == 403:
        return client.PawchiveError("ACCESS_RESTRICTED", "Pawchive 账号接口限制访问", 403)
    if status == 404:
        return client.PawchiveError("NOT_FOUND", "Pawchive 作者不存在", 404)
    if status == 429:
        return client.PawchiveError("RATE_LIMITED", "Pawchive 请求过快，请稍后重试", 429)
    if 300 <= status < 400:
        return client.PawchiveError("UPSTREAM_REDIRECT", "Pawchive 账号服务返回了意外跳转", 502)
    return client.PawchiveError("UPSTREAM_UNAVAILABLE", "Pawchive 账号服务返回错误", 502)


def _require_ok(status: int) -> None:
    if status < 200 or status >= 300:
        raise _upstream_error(status)


def _session_for(user_id: int) -> AccountSession:
    with _sessions_lock:
        session = _sessions.get(user_id)
    if session is None:
        raise client.PawchiveError("ACCOUNT_AUTH_REQUIRED", "请先登录 Pawchive 账号", 401)
    return session


def _forget_if_same(user_id: int, session: AccountSession) -> None:
    with _sessions_lock:
        if _sessions.get(user_id) is session:
            _sessions.pop(user_id, None)


def _parse_creator_list(body: bytes) -> list[dict]:
    try:
        items = json.loads(body)
    except (ValueError, UnicodeDecodeError) as exc:
        raise client.PawchiveError("UPSTREAM_INVALID", "Pawchive 收藏列表格式无效", 502) from exc
    if isinstance(items, dict):
        items = items.get("items") or items.get("data")
    if not isinstance(items, list):
        raise client.PawchiveError("UPSTREAM_INVALID", "Pawchive 收藏列表格式无效", 502)

    creators = []
    for item in items:
        if not isinstance(item, dict):
            continue
        service = str(item.get("service") or "")
        creator_id = str(item.get("id") or item.get("creator_id") or item.get("user") or "")
        try:
            service, creator_id = provider.validate_id(service), provider.validate_id(creator_id)
        except client.PawchiveError:
            continue
        creator_name = str(item.get("name") or item.get("creator_name") or creator_id)[:240]
        creators.append({
            "service": service,
            "creator_id": creator_id,
            "creator_name": creator_name,
            "updated_at": item.get("updated") if isinstance(item.get("updated"), str) else None,
            "source_url": f"https://pawchive.pw/{quote(service)}/user/{quote(creator_id)}",
            "banner_url": f"https://pawchive.pw/banners/{quote(service)}/{quote(creator_id)}",
            "icon_url": f"https://pawchive.pw/icons/{quote(service)}/{quote(creator_id)}",
        })
    return creators


def _fetch_favorites(session: AccountSession) -> list[dict]:
    status, body = _request(session, "/api/v1/account/favorites?type=artist")
    if status == 401:
        raise _upstream_error(status)
    _require_ok(status)
    return _parse_creator_list(body)


def status(user_id: int) -> dict:
    with _sessions_lock:
        return {"connected": user_id in _sessions}


def login(user_id: int, username: str, password: str) -> dict:
    if not username or len(username) > 200 or not password or len(password) > 1024:
        raise client.PawchiveError("INVALID_REQUEST", "请输入 Pawchive 用户名和密码", 400)

    session = AccountSession()
    with session.lock:
        status_code, _ = _request(session, "/account/login?location=%2Ffavorites")
        _require_ok(status_code)
        status_code, _ = _request(
            session,
            "/account/login",
            method="POST",
            form={"location": "/favorites", "username": username, "password": password},
        )
        if status_code == 401:
            raise client.PawchiveError("INVALID_ACCOUNT_CREDENTIALS", "Pawchive 用户名或密码不正确", 401)
        if status_code == 429:
            raise _upstream_error(status_code)
        if status_code == 403:
            raise _upstream_error(status_code)
        if not (200 <= status_code < 300 or 300 <= status_code < 400):
            _require_ok(status_code)

        try:
            favorites = _fetch_favorites(session)
        except client.PawchiveError as exc:
            if exc.code == "ACCOUNT_AUTH_REQUIRED":
                raise client.PawchiveError("INVALID_ACCOUNT_CREDENTIALS", "Pawchive 用户名或密码不正确", 401) from exc
            raise

    with _sessions_lock:
        _sessions[user_id] = session
    return {"connected": True, "items": favorites}


def favorites(user_id: int) -> list[dict]:
    session = _session_for(user_id)
    with session.lock:
        try:
            return _fetch_favorites(session)
        except client.PawchiveError as exc:
            if exc.code == "ACCOUNT_AUTH_REQUIRED":
                _forget_if_same(user_id, session)
            raise


def set_favorite(user_id: int, service: str, creator_id: str, favorite: bool) -> dict:
    service, creator_id = provider.validate_id(service), provider.validate_id(creator_id)
    session = _session_for(user_id)
    path = f"/api/v1/favorites/creator/{quote(service)}/{quote(creator_id)}"
    with session.lock:
        try:
            status_code, _ = _request(session, path, method="POST" if favorite else "DELETE")
            if status_code == 401:
                raise _upstream_error(status_code)
            _require_ok(status_code)
        except client.PawchiveError as exc:
            if exc.code == "ACCOUNT_AUTH_REQUIRED":
                _forget_if_same(user_id, session)
            raise
    return {"service": service, "creator_id": creator_id, "favorite": favorite}


def logout(user_id: int) -> None:
    with _sessions_lock:
        session = _sessions.pop(user_id, None)
    if session is None:
        return
    # Revoke the Pawchive-side session where the site accepts its logout route;
    # always discard the local copy, even if the site is temporarily unavailable.
    try:
        with session.lock:
            _request(session, "/account/logout")
    except client.PawchiveError:
        pass
