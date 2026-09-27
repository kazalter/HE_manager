"""Public Pawchive browse operations and scope-bound pagination."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from . import client, normalize, refs

ID = re.compile(r"^[A-Za-z0-9_-]{1,100}$")
PAGE_SIZE = 50


def validate_id(value: str) -> str:
    if not ID.fullmatch(value):
        raise client.PawchiveError("INVALID_REQUEST", "非法来源标识", 400)
    return value


def capabilities() -> dict:
    return {
        "provider": "pawchive",
        "search": True,
        "creator_scope": True,
        "creator_search": False,
        "global_tags": False,
        "creator_tags": True,
        "media_filter": "attachments_only",
        "sort": ["newest"],
        "image": True,
        "video": ["mp4", "webm"],
        "page_size": PAGE_SIZE,
    }


def _scope_key(scope: dict[str, Any]) -> str:
    canonical = json.dumps(scope, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:24]


def _list_raw(scope: dict[str, Any], offset: int):
    params: dict[str, str | int] = {"o": offset}
    if scope["query"]:
        params["q"] = scope["query"]
    if scope["creator_id"]:
        path = f"/api/v1/{scope['service']}/user/{scope['creator_id']}"
        if scope["tag"]:
            params["tag"] = scope["tag"]
    else:
        path = "/api/v1/posts"
    items = client.get_json(path, params)
    if not isinstance(items, list):
        raise client.PawchiveError("UPSTREAM_INVALID", "帖子列表格式无效", 502)
    return items


def list_posts(*, query: str = "", service: str = "", creator_id: str = "", tag: str = "",
               media_type: str = "all", cursor: str = "") -> dict:
    query = query.strip()
    service = service.strip()
    creator_id = creator_id.strip()
    tag = tag.strip()
    if (service and not creator_id) or (creator_id and not service):
        raise client.PawchiveError("INVALID_REQUEST", "创作者范围需要服务与 ID", 400)
    if service:
        validate_id(service)
        validate_id(creator_id)
    if query and len(query) < 3:
        raise client.PawchiveError("INVALID_REQUEST", "搜索词至少 3 个字符", 400)
    if len(query) > 200 or len(tag) > 100 or (tag and not creator_id):
        raise client.PawchiveError("INVALID_REQUEST", "筛选条件无效", 400)
    if media_type not in {"all", "image", "video"}:
        raise client.PawchiveError("INVALID_REQUEST", "媒体类型无效", 400)
    scope = {"query": query, "service": service, "creator_id": creator_id,
             "tag": tag, "media_type": media_type, "sort": "newest"}
    scope_key = _scope_key(scope)
    try:
        offset = refs.read_cursor(cursor, scope_key) if cursor else 0
    except ValueError as exc:
        raise client.PawchiveError("INVALID_CURSOR", "分页游标已过期或不属于当前范围", 400) from exc
    raw_items = _list_raw(scope, offset)
    items = [normalize.normalize_post(raw) for raw in raw_items
             if isinstance(raw, dict) and all(ID.fullmatch(str(raw.get(field) or ""))
                                                  for field in ("service", "user", "id"))]
    # The public API has no total/next field. Probe instead of treating exactly
    # 50 results as proof that another page exists.
    has_more = bool(_list_raw(scope, offset + PAGE_SIZE)) if len(raw_items) >= PAGE_SIZE else False
    return {
        "items": items,
        "next_cursor": refs.sign_cursor(offset + PAGE_SIZE, scope_key) if has_more else None,
        "has_more": has_more,
        "total": None,
        "applied_filters": scope,
        "filter_scope": "server" if media_type == "all" else "attachments_only",
        "warnings": ["媒体类型仅筛选打开帖子后的附件，列表仍包含所有帖子"] if media_type != "all" else [],
    }


def creator_profile(service: str, creator_id: str) -> dict:
    service, creator_id = validate_id(service), validate_id(creator_id)
    raw = client.get_json(f"/api/v1/{service}/user/{creator_id}/profile")
    if not isinstance(raw, dict):
        raise client.PawchiveError("UPSTREAM_INVALID", "创作者资料格式无效", 502)
    return {"service": service, "creator_id": creator_id,
            "name": str(raw.get("name") or creator_id)[:240],
            "source_url": f"https://pawchive.pw/{service}/user/{creator_id}"}


def post_detail(service: str, creator_id: str, post_id: str) -> dict:
    service, creator_id, post_id = map(validate_id, (service, creator_id, post_id))
    raw = client.get_json(f"/api/v1/{service}/user/{creator_id}/post/{post_id}")
    if (not isinstance(raw, dict) or str(raw.get("id")) != post_id
            or str(raw.get("user")) != creator_id or str(raw.get("service")) != service):
        raise client.PawchiveError("UPSTREAM_INVALID", "帖子详情身份不匹配", 502)
    try:
        name = creator_profile(service, creator_id)["name"]
    except client.PawchiveError:
        name = creator_id
    return normalize.normalize_post(raw, creator_name=name, detail=True)
