"""Fixed-host Pawchive HTTP client with bounded JSON and pinned public DNS.

No caller supplies a URL. Redirects, cookies and proxy environment variables
are intentionally unsupported. Media streams keep the connection open only
while their response iterator is consumed.
"""
from __future__ import annotations

import http.client
import ipaddress
import json
import os
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


def _new_connection(host: str) -> http.client.HTTPSConnection:
    from app.external_config import get_external_favorites_proxy, validate_external_favorites_proxy

    proxy = get_external_favorites_proxy()
    if not proxy:
        return PinnedHTTPSConnection(host, timeout=20)
    try:
        proxy = validate_external_favorites_proxy(proxy)
        parsed = urlsplit(proxy or "")
        connection = http.client.HTTPSConnection(parsed.hostname, parsed.port or 80, timeout=20)
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


def _throttle_api():
    global _next_api_request
    with _rate_lock:
        now = time.monotonic()
        if _next_api_request > now:
            time.sleep(_next_api_request - now)
        _next_api_request = time.monotonic() + 1.0


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
