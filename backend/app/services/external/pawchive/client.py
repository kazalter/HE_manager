"""Fixed-host Pawchive HTTP client with bounded responses and pinned DNS.

All requests use the shared external-favorites proxy when configured. Without
one, direct connections keep pinned DNS checks. Account cookies are handled
only by the separate allowlisted account_request. Media streams keep their
connection open only while the response iterator runs.
"""
from __future__ import annotations

import http.client
import ipaddress
import json
import re
import socket
import threading
import time
from collections import OrderedDict
from urllib.parse import urlencode, urlsplit

API_HOST = "pawchive.pw"
FILE_HOST = "file.pawchive.pw"
IMAGE_HOST = "img.pawchive.pw"
JSON_LIMIT = 8 * 1024 * 1024
CACHE_LIMIT = 16 * 1024 * 1024
CACHE_TTL = 300
_cache: OrderedDict[str, tuple[float, bytes]] = OrderedDict()
_cache_bytes = 0
_cache_lock = threading.Lock()
_rate_lock = threading.Lock()
_next_api_request = 0.0
_ACCOUNT_CREATOR_PATH = re.compile(r"^/api/v1/favorites/creator/[A-Za-z0-9_-]{1,100}/[A-Za-z0-9_-]{1,100}$")
_ACCOUNT_COOKIE_NAME = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]{1,128}$")
_ACCOUNT_COOKIE_VALUE = re.compile(r"^[!\x23-\x2B\x2D-\x3A\x3C-\x5B\x5D-\x7E]*$")


class PawchiveError(Exception):
    def __init__(self, code: str, message: str, status: int = 502, retry_after: str | None = None):
        super().__init__(message)
        self.code = code
        self.status = status
        self.retry_after = retry_after


class PinnedHTTPSConnection(http.client.HTTPSConnection):
    """TLS to a checked public address with SNI/certificate bound to the host."""

    def connect(self):
        try:
            addresses = socket.getaddrinfo(self.host, self.port, type=socket.SOCK_STREAM)
        except OSError as exc:
            raise PawchiveError("UPSTREAM_UNAVAILABLE", "无法解析 Pawchive 主机", 502) from exc
        if not addresses or any(not ipaddress.ip_address(info[4][0]).is_global for info in addresses):
            raise PawchiveError("UPSTREAM_UNAVAILABLE", "Pawchive 主机地址无效", 502)
        last_error: OSError | None = None
        for family, socktype, proto, _, address in addresses:
            sock = socket.socket(family, socktype, proto)
            sock.settimeout(self.timeout)
            try:
                sock.connect(address)
                self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
                return
            except OSError as exc:
                last_error = exc
                sock.close()
        raise PawchiveError("UPSTREAM_UNAVAILABLE", "无法连接 Pawchive", 502) from last_error


def _new_connection(host: str, *, timeout: float = 20) -> http.client.HTTPSConnection:
    from app.external_config import get_external_favorites_proxy, validate_external_favorites_proxy

    proxy = get_external_favorites_proxy()
    if not proxy:
        return PinnedHTTPSConnection(host, timeout=timeout)
    try:
        proxy = validate_external_favorites_proxy(proxy)
        parsed = urlsplit(proxy or "")
        connection = http.client.HTTPSConnection(parsed.hostname, parsed.port or 80, timeout=timeout)
    except (ValueError, TypeError) as exc:
        raise PawchiveError("INVALID_CONFIG", "外部收藏代理地址无效，请填写 HTTP 代理", 503) from exc
    connection.set_tunnel(host, 443)
    return connection


def _request(host: str, target: str, *, range_header: str | None = None):
    if host not in {API_HOST, FILE_HOST, IMAGE_HOST} or not target.startswith("/") or ".." in target:
        raise PawchiveError("INVALID_REQUEST", "非法上游请求", 400)
    connection = _new_connection(host)
    headers = {
        "Host": host,
        "Accept": "application/json" if host == API_HOST else "image/*, video/*",
        "Accept-Encoding": "identity",
        "User-Agent": "HE-Manager-Pawchive/1.0",
    }
    if range_header:
        headers["Range"] = range_header
    try:
        connection.request("GET", target, headers=headers)
        response = connection.getresponse()
        if 300 <= response.status < 400:
            raise PawchiveError("UPSTREAM_REDIRECT", "Pawchive 媒体地址已变化", 502)
        return connection, response
    except PawchiveError:
        connection.close()
        raise
    except (OSError, TimeoutError, http.client.HTTPException) as exc:
        connection.close()
        raise PawchiveError("UPSTREAM_UNAVAILABLE", "Pawchive 暂时不可用", 502) from exc


def _raise_for_status(response):
    if response.status == 403 or response.status == 401:
        raise PawchiveError("ACCESS_RESTRICTED", "来源站点限制访问", 403)
    if response.status == 429:
        raise PawchiveError("RATE_LIMITED", "来源站点请求过快", 429, response.getheader("Retry-After"))
    if response.status == 404:
        raise PawchiveError("NOT_FOUND", "来源内容不存在", 404)
    if response.status >= 400:
        raise PawchiveError("UPSTREAM_UNAVAILABLE", "Pawchive 返回错误", 502)


def _deadline_timeout(timeout: float, deadline: float | None) -> float:
    if deadline is None:
        return timeout
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise PawchiveError("UPSTREAM_UNAVAILABLE", "读取 Pawchive 收藏超时", 502)
    return min(timeout, remaining)


def _throttle_api(deadline: float | None = None):
    global _next_api_request
    acquired = (_rate_lock.acquire(timeout=_deadline_timeout(30, deadline))
                if deadline is not None else _rate_lock.acquire())
    if not acquired:
        raise PawchiveError("UPSTREAM_UNAVAILABLE", "等待 Pawchive 请求超时", 502)
    try:
        now = time.monotonic()
        if _next_api_request > now:
            delay = _next_api_request - now
            if deadline is not None and delay >= _deadline_timeout(30, deadline):
                raise PawchiveError("UPSTREAM_UNAVAILABLE", "等待 Pawchive 请求超时", 502)
            time.sleep(delay)
        _deadline_timeout(30, deadline)
        _next_api_request = time.monotonic() + 1.0
    finally:
        _rate_lock.release()


def _set_account_read_timeout(sock, timeout: float, deadline: float | None):
    remaining = _deadline_timeout(timeout, deadline)
    if sock is not None:
        sock.settimeout(min(sock.gettimeout() or timeout, remaining))


def _read_account_body(response, sock, limit: int, timeout: float, deadline: float | None) -> bytes:
    if deadline is None:
        return response.read(limit + 1)
    body = bytearray()
    while len(body) <= limit:
        _set_account_read_timeout(sock, timeout, deadline)
        chunk = response.read1(min(64 * 1024, limit + 1 - len(body)))
        if not chunk:
            break
        body.extend(chunk)
        if response.isclosed():
            break
    _deadline_timeout(timeout, deadline)
    return bytes(body)


def get_json(path: str, params: dict[str, str | int] | None = None):
    if not path.startswith("/api/v1/") or ".." in path:
        raise PawchiveError("INVALID_REQUEST", "非法 API 路径", 400)
    target = path + ("?" + urlencode(params) if params else "")
    now = time.monotonic()
    with _cache_lock:
        hit = _cache.get(target)
        if hit and hit[0] > now:
            _cache.move_to_end(target)
            return json.loads(hit[1])
    _throttle_api()
    connection, response = _request(API_HOST, target)
    try:
        _raise_for_status(response)
        if not (response.getheader("Content-Type") or "").lower().startswith("application/json"):
            raise PawchiveError("UPSTREAM_INVALID", "Pawchive 返回了非 JSON 内容", 502)
        body = response.read(JSON_LIMIT + 1)
        if len(body) > JSON_LIMIT:
            raise PawchiveError("UPSTREAM_INVALID", "Pawchive 响应超出限制", 502)
        try:
            value = json.loads(body)
        except (ValueError, UnicodeDecodeError) as exc:
            raise PawchiveError("UPSTREAM_INVALID", "Pawchive JSON 无法解析", 502) from exc
    finally:
        connection.close()
    if len(body) <= CACHE_LIMIT // 2:
        global _cache_bytes
        with _cache_lock:
            old = _cache.pop(target, None)
            if old:
                _cache_bytes -= len(old[1])
            _cache[target] = (time.monotonic() + CACHE_TTL, body)
            _cache_bytes += len(body)
            while len(_cache) > 128 or _cache_bytes > CACHE_LIMIT:
                _, (_, removed) = _cache.popitem(last=False)
                _cache_bytes -= len(removed)
    return value


def account_request(
    target: str,
    *,
    method: str = "GET",
    cookies: dict[str, str] | None = None,
    form: dict[str, str] | None = None,
    body_limit: int = JSON_LIMIT,
    timeout: float = 20,
    budget: float | None = None,
):
    """Make a bounded request to Pawchive's fixed-host account endpoints.

    Account cookies are accepted only for the login, logout, and creator-favorite
    endpoints on API_HOST. The public metadata and media clients never receive
    these cookies.
    """
    parsed = urlsplit(target)
    if (parsed.scheme or parsed.netloc or not parsed.path.startswith("/")
            or ".." in parsed.path or "\r" in target or "\n" in target):
        raise PawchiveError("INVALID_REQUEST", "非法 Pawchive 账号请求", 400)
    if parsed.path == "/account/login":
        if method not in {"GET", "POST"} or parsed.query not in {"", "location=%2Ffavorites"}:
            raise PawchiveError("INVALID_REQUEST", "非法 Pawchive 登录请求", 400)
    elif parsed.path == "/account/logout":
        if method != "GET" or parsed.query:
            raise PawchiveError("INVALID_REQUEST", "非法 Pawchive 退出请求", 400)
    elif parsed.path == "/api/v1/account/favorites":
        if method != "GET" or parsed.query != "type=artist":
            raise PawchiveError("INVALID_REQUEST", "非法 Pawchive 收藏请求", 400)
    elif _ACCOUNT_CREATOR_PATH.fullmatch(parsed.path):
        if method not in {"POST", "DELETE"} or parsed.query:
            raise PawchiveError("INVALID_REQUEST", "非法 Pawchive 作者收藏请求", 400)
    else:
        raise PawchiveError("INVALID_REQUEST", "不支持的 Pawchive 账号请求", 400)
    if body_limit < 1 or body_limit > JSON_LIMIT:
        raise PawchiveError("INVALID_REQUEST", "Pawchive 响应大小限制无效", 400)

    headers = {
        "Host": API_HOST,
        "Accept": "text/html, application/json;q=0.9, */*;q=0.1",
        "Accept-Encoding": "identity",
        "User-Agent": "HE-Manager-Pawchive/1.0",
        "Origin": f"https://{API_HOST}",
    }
    if parsed.path.startswith("/api/v1/"):
        headers["Accept"] = "application/json"
        headers["Referer"] = f"https://{API_HOST}/favorites"
    elif parsed.path == "/account/login":
        headers["Referer"] = f"https://{API_HOST}/account/login?location=%2Ffavorites"
    if cookies:
        if len(cookies) > 32:
            raise PawchiveError("INVALID_REQUEST", "Pawchive 会话 Cookie 无效", 400)
        if any(not _ACCOUNT_COOKIE_NAME.fullmatch(name) or not _ACCOUNT_COOKIE_VALUE.fullmatch(value)
               for name, value in cookies.items()):
            raise PawchiveError("INVALID_REQUEST", "Pawchive 会话 Cookie 无效", 400)
        cookie_header = "; ".join(f"{name}={value}" for name, value in cookies.items())
        if len(cookie_header) > 4096 or "\r" in cookie_header or "\n" in cookie_header:
            raise PawchiveError("INVALID_REQUEST", "Pawchive 会话 Cookie 无效", 400)
        headers["Cookie"] = cookie_header
    body = None
    if form is not None:
        if method != "POST" or parsed.path != "/account/login":
            raise PawchiveError("INVALID_REQUEST", "非法 Pawchive 表单请求", 400)
        body = urlencode(form).encode("utf-8")
        if len(body) > 8192:
            raise PawchiveError("INVALID_REQUEST", "Pawchive 登录表单过长", 400)
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        headers["Content-Length"] = str(len(body))

    deadline = time.monotonic() + budget if budget is not None else None
    _throttle_api(deadline)
    connection = _new_connection(API_HOST, timeout=_deadline_timeout(timeout, deadline))
    response = None
    sock = None
    deadline_timer = None
    if deadline is not None:
        def interrupt_read():
            # http.client can make repeated reads inside header/chunk parsing.
            # Socket inactivity timeouts alone do not bound a slow-drip reply.
            current_socket = sock if sock is not None else connection.sock
            if current_socket is not None:
                try:
                    current_socket.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

        deadline_timer = threading.Timer(_deadline_timeout(budget, deadline), interrupt_read)
        deadline_timer.daemon = True
        deadline_timer.start()
    try:
        connection.request(method, target, body=body, headers=headers)
        sock = connection.sock
        _set_account_read_timeout(sock, timeout, deadline)
        response = connection.getresponse()
        _deadline_timeout(timeout, deadline)
        if response.status >= 400:
            # Status headers already tell us whether this request is forbidden
            # or rate-limited. Never let a broken error body hide that status.
            return response.status, response.getheaders(), b""
        response_body = _read_account_body(response, sock, body_limit, timeout, deadline)
        if len(response_body) > body_limit:
            raise PawchiveError("UPSTREAM_INVALID", "Pawchive 账号响应超出限制", 502)
        return response.status, response.getheaders(), response_body
    except PawchiveError:
        raise
    except (OSError, TimeoutError, http.client.HTTPException) as exc:
        raise PawchiveError("UPSTREAM_UNAVAILABLE", "无法连接 Pawchive 账号服务", 502) from exc
    finally:
        if deadline_timer is not None:
            deadline_timer.cancel()
            deadline_timer.join()
        if response is not None:
            response.close()
        connection.close()


def open_media(path: str, *, preview: bool = False, range_header: str | None = None):
    host = IMAGE_HOST if preview else FILE_HOST
    prefix = "/thumbnail/data" if preview else "/data"
    connection, response = _request(host, prefix + path, range_header=range_header)
    try:
        if response.status != 416:
            _raise_for_status(response)
        return connection, response
    except Exception:
        connection.close()
        raise
