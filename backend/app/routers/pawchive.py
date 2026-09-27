"""Authenticated HE Manager API for public Pawchive browsing."""
from __future__ import annotations

import os
import re

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse
from starlette.background import BackgroundTask
from pydantic import BaseModel, Field, SecretStr
from sqlalchemy.orm import Session

from .. import auth, models
from ..database import get_db
from ..services import job_lifecycle
from ..services.external.pawchive import account, client, downloader, normalize, provider, refs

router = APIRouter(prefix="/external/pawchive", tags=["pawchive"])


def require_enabled():
    if os.getenv("HE_PAWCHIVE_ENABLED", "0").lower() not in {"1", "true", "yes", "on"}:
        raise HTTPException(status_code=503, detail={"code": "PROVIDER_DISABLED", "message": "Pawchive 模块未启用"})


def _run(operation, *args, **kwargs):
    require_enabled()
    try:
        return operation(*args, **kwargs)
    except client.PawchiveError as exc:
        raise HTTPException(status_code=exc.status, detail={
            "code": exc.code,
            "message": str(exc),
            "retryable": exc.code in {"UPSTREAM_UNAVAILABLE", "RATE_LIMITED"},
            "retry_after": exc.retry_after,
        }) from exc


@router.get("/capabilities")
def get_capabilities():
    return _run(provider.capabilities)


class PawchiveAccountLogin(BaseModel):
    username: str = Field(min_length=1, max_length=200)
    password: SecretStr = Field(min_length=1, max_length=1024)


@router.get("/account/status")
def pawchive_account_status(user: models.User = Depends(auth.get_current_user)):
    return _run(account.status, user.id)


@router.post("/account/login")
def pawchive_account_login(
    payload: PawchiveAccountLogin,
    user: models.User = Depends(auth.get_current_user),
):
    return _run(account.login, user.id, payload.username, payload.password.get_secret_value())


@router.delete("/account/session", status_code=204)
def pawchive_account_logout(user: models.User = Depends(auth.get_current_user)):
    _run(account.logout, user.id)
    return Response(status_code=204)


@router.get("/account/favorites")
def pawchive_account_favorites(user: models.User = Depends(auth.get_current_user)):
    return {"items": _run(account.favorites, user.id), "source": "pawchive_account"}


@router.put("/account/favorites/{service}/{creator_id}")
def set_pawchive_account_favorite(
    service: str,
    creator_id: str,
    user: models.User = Depends(auth.get_current_user),
):
    return _run(account.set_favorite, user.id, service, creator_id, True)


@router.delete("/account/favorites/{service}/{creator_id}")
def remove_pawchive_account_favorite(
    service: str,
    creator_id: str,
    user: models.User = Depends(auth.get_current_user),
):
    return _run(account.set_favorite, user.id, service, creator_id, False)


@router.get("/posts")
def get_posts(q: str = "", service: str = "", creator_id: str = "", tag: str = "",
              media_type: str = "all", cursor: str = ""):
    return _run(provider.list_posts, query=q, service=service, creator_id=creator_id,
                tag=tag, media_type=media_type, cursor=cursor)


@router.get("/creators/{service}/{creator_id}")
def get_creator(service: str, creator_id: str):
    return _run(provider.creator_profile, service, creator_id)


@router.get("/posts/{service}/{creator_id}/{post_id}")
def get_post(service: str, creator_id: str, post_id: str):
    return _run(provider.post_detail, service, creator_id, post_id)


class CreatorFavoriteRequest(BaseModel):
    service: str = Field(min_length=1, max_length=100)
    creator_id: str = Field(min_length=1, max_length=100)
    creator_name: str = Field(default="", max_length=240)


def _serialize_creator_favorite(row: models.PawchiveCreatorFavorite) -> dict:
    return {
        "service": row.service,
        "creator_id": row.creator_id,
        "creator_name": row.creator_name,
        "source_url": row.source_url,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.get("/favorites")
def list_creator_favorites(
    db: Session = Depends(get_db),
    user: models.User = Depends(auth.get_current_user),
):
    rows = (db.query(models.PawchiveCreatorFavorite)
            .filter_by(user_id=user.id)
            .order_by(models.PawchiveCreatorFavorite.created_at.desc(),
                      models.PawchiveCreatorFavorite.id.desc())
            .all())
    return {"items": [_serialize_creator_favorite(row) for row in rows], "source": "he_manager"}


@router.put("/favorites")
def save_creator_favorite(
    payload: CreatorFavoriteRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(auth.get_current_user),
):
    try:
        service = provider.validate_id(payload.service.strip())
        creator_id = provider.validate_id(payload.creator_id.strip())
    except client.PawchiveError as exc:
        raise HTTPException(status_code=exc.status, detail={"code": exc.code, "message": str(exc)}) from exc
    creator_name = payload.creator_name.strip()[:240] or creator_id
    row = (db.query(models.PawchiveCreatorFavorite)
           .filter_by(user_id=user.id, service=service, creator_id=creator_id)
           .first())
    if row is None:
        row = models.PawchiveCreatorFavorite(
            user_id=user.id,
            service=service,
            creator_id=creator_id,
            creator_name=creator_name,
            source_url=f"https://pawchive.pw/{service}/user/{creator_id}",
        )
        db.add(row)
    else:
        row.creator_name = creator_name
    db.commit()
    db.refresh(row)
    return _serialize_creator_favorite(row)


@router.delete("/favorites/{service}/{creator_id}", status_code=204)
def remove_creator_favorite(
    service: str,
    creator_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(auth.get_current_user),
):
    try:
        service = provider.validate_id(service)
        creator_id = provider.validate_id(creator_id)
    except client.PawchiveError as exc:
        raise HTTPException(status_code=exc.status, detail={"code": exc.code, "message": str(exc)}) from exc
    row = (db.query(models.PawchiveCreatorFavorite)
           .filter_by(user_id=user.id, service=service, creator_id=creator_id)
           .first())
    if row is not None:
        db.delete(row)
        db.commit()
    return Response(status_code=204)


_SINGLE_RANGE = re.compile(r"^bytes=(?:\d+-\d*|-\d+)$")
_CONTENT_RANGE = re.compile(r"^bytes \d+-\d+/(?:\d+|\*)$")


def stream_media_response(stream_ref: str, range_header: str | None = None):
    try:
        path, kind = refs.read_media(stream_ref)
    except ValueError as exc:
        raise client.PawchiveError("INVALID_REF", "媒体引用已过期，请重新打开帖子", 400) from exc
    media = normalize.file_type(path)
    if not media or (kind != "preview" and media[0] != kind):
        raise client.PawchiveError("MEDIA_UNSUPPORTED", "媒体格式不受支持", 415)
    if range_header and not _SINGLE_RANGE.fullmatch(range_header):
        raise client.PawchiveError("INVALID_RANGE", "仅支持单一区间读取", 416)
    connection, upstream = client.open_media(path, preview=kind == "preview", range_header=range_header)
    content_range = upstream.getheader("Content-Range")
    if upstream.status == 416:
        connection.close()
        headers = {"Content-Range": content_range} if content_range and content_range.startswith("bytes */") else {}
        return Response(status_code=416, headers=headers)
    content_type = (upstream.getheader("Content-Type") or "").split(";", 1)[0].strip().lower()
    expected_prefix = "image/" if kind in {"image", "preview"} else "video/"
    if (upstream.status not in {200, 206} or not content_type.startswith(expected_prefix)
            or (upstream.status == 206 and not _CONTENT_RANGE.fullmatch(content_range or ""))):
        connection.close()
        raise client.PawchiveError("UPSTREAM_INVALID", "来源返回了无效的媒体响应", 502)
    headers = {"Cache-Control": "private, max-age=60"}
    for upstream_name, public_name in (
        ("Content-Length", "Content-Length"), ("Content-Range", "Content-Range"),
        ("Accept-Ranges", "Accept-Ranges"), ("ETag", "ETag"),
        ("Last-Modified", "Last-Modified"),
    ):
        value = upstream.getheader(upstream_name)
        if value:
            headers[public_name] = value

    def chunks():
        try:
            while part := upstream.read(64 * 1024):
                yield part
        finally:
            connection.close()

    return StreamingResponse(chunks(), status_code=upstream.status, media_type=content_type,
                             headers=headers, background=BackgroundTask(connection.close))


@router.get("/media/{stream_ref}")
def get_media(stream_ref: str, request: Request):
    return _run(stream_media_response, stream_ref, request.headers.get("range"))


class DownloadSelection(BaseModel):
    service: str
    creator_id: str
    post_id: str
    attachment_keys: list[str] | None = None


class DownloadRequest(BaseModel):
    selections: list[DownloadSelection] = Field(min_length=1, max_length=downloader.MAX_SELECTIONS)


@router.post("/downloads/preview")
def preview_download(payload: DownloadRequest, db: Session = Depends(get_db)):
    return _run(downloader.preview_download, [selection.model_dump() for selection in payload.selections], db)


@router.post("/downloads")
def create_download(payload: DownloadRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    return _run(downloader.create_download, [selection.model_dump() for selection in payload.selections], db,
                background_tasks)


@router.get("/downloads")
def list_downloads(limit: int = Query(50, ge=1, le=100), db: Session = Depends(get_db)):
    require_enabled()
    rows = (db.query(models.BackgroundJob).filter_by(kind=downloader.JOB_KIND)
            .order_by(models.BackgroundJob.created_at.desc()).limit(limit).all())
    return {"items": [job_lifecycle.get_job_snapshot(downloader.JOB_KIND, row.job_id) for row in rows]}


@router.get("/downloads/{job_id}")
def get_download(job_id: str, db: Session = Depends(get_db)):
    require_enabled()
    snapshot = job_lifecycle.get_job_snapshot(downloader.JOB_KIND, job_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "下载任务不存在"})
    rows = db.query(models.PawchiveAttachment).filter_by(job_id=job_id).order_by(models.PawchiveAttachment.id).all()
    snapshot["attachments"] = [
        {**downloader._serialize_attachment(row), "post_key":
         f"pawchive:{row.post.service}:{row.post.creator_id}:{row.post.post_id}"}
        for row in rows
    ] or snapshot.get("attachments", [])
    return snapshot


@router.post("/downloads/{job_id}/cancel")
def cancel_download(job_id: str):
    return _run(downloader.cancel_download, job_id)


@router.post("/downloads/{job_id}/retry")
def retry_download(job_id: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    require_enabled()
    snapshot = job_lifecycle.get_job_snapshot(downloader.JOB_KIND, job_id)
    if not snapshot or snapshot.get("status") not in {"failed", "canceled", "interrupted"}:
        raise HTTPException(status_code=409, detail={"code": "INVALID_REQUEST", "message": "任务不可重试"})
    ids = snapshot.get("attachment_ids") or []
    rows = db.query(models.PawchiveAttachment).filter(models.PawchiveAttachment.id.in_(ids)).all()
    selections = {}
    for row in rows:
        if downloader._healthy_attachment(row, db):
            continue
        post = row.post
        key = (post.service, post.creator_id, post.post_id)
        selections.setdefault(key, []).append(row.attachment_key)
    if not selections:
        return {"job_id": None, "status": "already_downloaded", "queued": 0}
    requested = [{"service": service, "creator_id": creator_id, "post_id": post_id,
                  "attachment_keys": keys} for (service, creator_id, post_id), keys in selections.items()]
    return _run(downloader.create_download, requested, db, background_tasks)
