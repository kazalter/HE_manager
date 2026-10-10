"""Bounded metadata reads. Never open media files or call view/history routes."""

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import case, func, or_
from sqlalchemy.orm import selectinload
from .. import models, recommendations
from .identity import require_tool_context
from . import schemas

READ_TOOLS = frozenset(
    {
        "search_media",
        "get_media_detail",
        "get_library_stats",
        "recommend_media",
        "list_duplicate_candidates",
        "list_tags",
        "list_folders",
    }
)
HIDDEN = ("checking", "strong_duplicate", "suspected_duplicate", "dedup_excluded")


class DetailQuery(schemas.ScopeQuery):
    media_id: schemas.PositiveID


ARGS = {
    "search_media": schemas.MediaQuery,
    "get_media_detail": DetailQuery,
    "get_library_stats": schemas.ScopeQuery,
    "recommend_media": schemas.RecommendationQuery,
    "list_duplicate_candidates": schemas.PageQuery,
    "list_tags": schemas.PageQuery,
    "list_folders": schemas.PageQuery,
}


def scoped(db, scope="normal"):
    rows = db.query(models.Media).filter(models.Media.media_type.in_(("manga", "video", "image", "audio")))
    if scope == "all":
        return rows
    if scope == "missing":
        return rows.filter(models.Media.is_missing == True)
    if scope == "duplicate":
        return rows.filter(models.Media.duplicate_status.in_(("strong_duplicate", "suspected_duplicate", "dedup_excluded", "weak_suspected")))
    if scope == "checking":
        return rows.filter(models.Media.duplicate_status.in_(("checking", "dedup_pending")))
    return visible(db)


def visible(db):
    return db.query(models.Media).filter(
        models.Media.is_missing == False,
        models.Media.duplicate_status.notin_(HIDDEN),
        models.Media.media_type.in_(("manga", "video", "image", "audio")),
    )


def tag_dto(tag, count=0):
    return schemas.TagDTO(
        id=tag.id,
        name=(tag.name or "")[:80],
        namespace=(tag.namespace or "general")[:40],
        count=count,
    ).model_dump()


def safe_source_url(value):
    try:
        schemas.MediaPatch(source_url=value)
        return value
    except ValueError:
        return None


def folder_label(path, fallback):
    # Model-facing results name roots without exposing server absolute paths.
    label = (path or "").replace("\\", "/").rstrip("/").split("/")[-1]
    return label[:500] if label and not label.endswith(":") else fallback


def media_dto(row):
    tags = sorted(row.tags, key=lambda t: t.id)
    site = row.source_site
    if site and any(c in site for c in ("://", "/", "\\", "@", "?")):
        site = None
    return schemas.MediaDetailDTO(
        id=row.id,
        title=(row.title or "")[:500],
        artist=(row.artist[:500] if row.artist else None),
        media_type=row.media_type,
        tags=[tag_dto(t) for t in tags[:50]],
        rating=max(0, min(5, row.rating or 0)),
        favorite=bool(row.favorite),
        view_status=(row.view_status or "unviewed")[:30],
        duration=max(0, row.duration) if row.duration is not None else None,
        page_count=max(0, row.page_count) if row.page_count is not None else None,
        source_site=site[:100] if site else None,
        folder_id=row.folder_id,
        file_size=max(0, row.file_size) if row.file_size is not None else None,
        progress=max(0, row.progress or 0),
        is_missing=bool(row.is_missing),
        duplicate_status=row.duplicate_status or "unique",
        source_url=safe_source_url(row.source_url),
        truncated=len(tags) > 50
        or len(row.title or "") > 500
        or len(row.artist or "") > 500,
    ).model_dump()


def page(items, total, args):
    return {
        "items": items,
        "total": total,
        "offset": args.offset,
        "has_more": args.offset + len(items) < total,
        "next_offset": args.offset + len(items) if args.offset + len(items) < total else None,
    }


def execute_read_tool(db, principal, context, name, args):
    if name not in READ_TOOLS:
        raise HTTPException(404, "assistant_unknown_tool")
    require_tool_context(db, principal, context)
    try:
        query = ARGS[name].model_validate(args)
    except ValidationError:
        raise HTTPException(422, "assistant_invalid_tool_args") from None
    if name == "search_media":
        rows = scoped(db, query.scope).options(selectinload(models.Media.tags))
        if query.query:
            rows = rows.filter(
                models.Media.title.icontains(query.query, autoescape=True)
            )
        if query.media_type:
            rows = rows.filter(models.Media.media_type == query.media_type)
        if query.tag:
            rows = rows.filter(models.Media.tags.any(models.Tag.name == query.tag))
        if query.favorite is not None:
            rows = rows.filter(models.Media.favorite == query.favorite)
        if query.view_status:
            rows = rows.filter(models.Media.view_status == query.view_status)
        total = rows.count()
        items = [
            media_dto(x)
            for x in rows.order_by(*((models.Media.title, models.Media.id) if query.sort == "title" else (models.Media.id.desc(),)))
            .offset(query.offset)
            .limit(query.limit)
        ]
        result = page(items, total, query)
    elif name == "get_media_detail":
        row = (
            scoped(db, query.scope)
            .options(selectinload(models.Media.tags))
            .filter(models.Media.id == query.media_id)
            .first()
        )
        if row is None:
            raise HTTPException(404, "assistant_media_not_found")
        result = media_dto(row)
    elif name == "get_library_stats":
        rows = scoped(db, query.scope)
        counts = dict(
            rows.with_entities(models.Media.media_type, func.count(models.Media.id))
            .group_by(models.Media.media_type)
            .all()
        )
        result = {
            "scope": query.scope,
            "total": sum(counts.values()),
            "by_type": counts,
            "favorite_count": rows.filter(models.Media.favorite == True).count(),
            "watched_count": rows.filter(models.Media.view_status == "viewed").count(),
        }
    elif name == "recommend_media":
        if query.media_type in (None, "manga"):
            reply = recommendations.recommend_manga(
                db,
                query.query,
                query.limit,
                query.avoid_tags,
                query.preferred_tags,
                seed=query.seed,
                allow_ai=False,
            )
            result = {
                "items": [media_dto(x["media"]) for x in reply["recommendations"]],
                "method": "manga_retrieval",
                "basis": (
                    "依据已有标题、标签、画像及本地检索排序；未分析媒体原文件。"
                    + (reply.get("message") or "")
                )[:2000],
            }
        else:
            rows = (
                visible(db)
                .options(selectinload(models.Media.tags))
                .filter(models.Media.media_type == query.media_type)
            )
            if query.query:
                rows = rows.filter(
                    models.Media.title.icontains(query.query, autoescape=True)
                )
            if query.avoid_tags:
                rows = rows.filter(
                    ~models.Media.tags.any(models.Tag.name.in_(query.avoid_tags))
                )
            score = sum(
                (
                    case((models.Media.tags.any(models.Tag.name == t), 1), else_=0)
                    for t in query.preferred_tags
                ),
                0,
            )
            if query.preferred_tags:
                rows = rows.order_by(score.desc())
            result = {
                "items": [
                    media_dto(x)
                    for x in rows.order_by(
                        models.Media.rating.desc(), models.Media.id.desc()
                    ).limit(query.limit)
                ],
                "method": "metadata_filter",
                "basis": "依据已有标题、标签、评分和 ID 筛选排序；信息不足时无法判断内容品质，未分析媒体原文件。",
            }
    elif name == "list_tags":
        # Count only normal library items; tags remain useful even with zero matches.
        allowed = visible(db).with_entities(models.Media.id).subquery()
        counts = (
            db.query(models.media_tags.c.tag_id, func.count())
            .filter(models.media_tags.c.media_id.in_(db.query(allowed.c.id)))
            .group_by(models.media_tags.c.tag_id)
            .subquery()
        )
        rows = db.query(models.Tag, func.coalesce(counts.c[1], 0)).outerjoin(
            counts, models.Tag.id == counts.c.tag_id
        )
        result = page(
            [
                tag_dto(t, int(n))
                for t, n in rows.order_by(models.Tag.id)
                .offset(query.offset)
                .limit(query.limit)
            ],
            db.query(models.Tag).count(),
            query,
        )
    elif name == "list_folders":
        rows = db.query(models.Folder)
        items = []
        for row in (
            rows.order_by(models.Folder.id).offset(query.offset).limit(query.limit)
        ):
            items.append(
                {
                    "id": row.id,
                    "display_name": folder_label(row.path, "目录 " + str(row.id)),
                    "status": (row.status or "idle")[:80],
                    "readable": __import__("os").path.isdir(row.path or ""),
                }
            )
        result = page(items, rows.count(), query)
    else:
        rows = db.query(models.DuplicateCandidate).filter(
            models.DuplicateCandidate.status == "pending"
        )
        total = rows.count()
        items = []
        for row in (
            rows.order_by(models.DuplicateCandidate.id)
            .offset(query.offset)
            .limit(query.limit)
        ):
            media_ids = [row.existing_media_id, row.candidate_media_id]
            titles = [
                (
                    (db.get(models.Media, i).title or "")[:500]
                    if db.get(models.Media, i)
                    else "已移除条目"
                )
                for i in media_ids
            ]
            items.append(
                {
                    "id": row.id,
                    "media_ids": media_ids,
                    "titles": titles,
                    "score": float(row.similarity or 0),
                    "basis": "已有重复候选记录："
                    + ("强重复" if row.level == "strong_duplicate" else "疑似重复")
                    + "；仅供核查，未执行合并或删除。",
                }
            )
        result = page(items, total, query)
    return schemas.RESULT_TYPES[name].model_validate(result).model_dump(mode="json")
