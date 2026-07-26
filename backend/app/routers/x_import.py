from datetime import datetime
import os
import re
import shutil
import time
from typing import List, Optional
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..services import job_lifecycle
from ..services.media_access import get_x_source_or_404
from ..services.thumbnails import THUMBNAIL_DIR
from ..services.x_import_runtime import (
    X_ARCHIVE_UPLOAD_DIR,
    get_or_create_x_source,
    x_import_stats,
)
from ..x_import import archive as x_archive
from ..x_import import importer as x_importer
from ..x_import import storage as x_storage
from ..x_import import sync as x_sync

router = APIRouter()


@router.get("/x/sources", response_model=List[schemas.XImportSource])
def list_x_sources(db: Session = Depends(get_db)):
    if db.query(models.XImportSource).count() == 0:
        get_or_create_x_source(db)
    return db.query(models.XImportSource).order_by(models.XImportSource.id.asc()).all()


@router.patch("/x/sources/{source_id}", response_model=schemas.XImportSource)
def update_x_source(source_id: int, payload: schemas.XImportSourceUpdate, db: Session = Depends(get_db)):
    source = get_x_source_or_404(source_id, db)
    data = payload.dict(exclude_unset=True)
    if "name" in data and data["name"]:
        source.name = data["name"].strip() or source.name
    if "cookie" in data:
        source.cookie = (data["cookie"] or "").strip() or None
    if "download_root_path" in data:
        path = (data["download_root_path"] or "").strip() or None
        if path:
            try:
                normalized = x_storage.normalize_root(path)
            except ValueError:
                raise HTTPException(status_code=400, detail="下载路径无效")
            source.download_root_path = normalized
            os.makedirs(x_storage.x_root_dir(normalized), exist_ok=True)
        else:
            source.download_root_path = None
    if "proxy" in data:
        source.proxy = (data["proxy"] or "").strip() or None
    db.commit()
    db.refresh(source)
    return source


@router.get("/x/sources/{source_id}/stats", response_model=schemas.XImportStats)
def get_x_source_stats(source_id: int, db: Session = Depends(get_db)):
    get_x_source_or_404(source_id, db)
    return x_import_stats(source_id, db)


@router.get("/x/sources/{source_id}/posts", response_model=List[schemas.XPost])
def list_x_posts(
    source_id: int,
    response: Response,
    status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    get_x_source_or_404(source_id, db)
    query = db.query(models.XPost).filter(models.XPost.source_id == source_id)
    if status:
        query = query.filter(models.XPost.status == status)
    response.headers["X-Total-Count"] = str(query.order_by(None).count())
    response.headers["Access-Control-Expose-Headers"] = "X-Total-Count"
    return (
        query.order_by(models.XPost.discovered_at.desc(), models.XPost.id.desc())
        .offset(max(0, offset))
        .limit(max(1, min(limit, 200)))
        .all()
    )


@router.post("/x/sources/{source_id}/archive", response_model=schemas.XImportArchiveUploadResponse)
def upload_x_archive(
    source_id: int,
    file: UploadFile = File(...),
    download_root_path: Optional[str] = Form(default=None),
    db: Session = Depends(get_db),
):
    source = get_x_source_or_404(source_id, db)

    if download_root_path is not None:
        trimmed = download_root_path.strip()
        if trimmed:
            source.download_root_path = x_storage.normalize_root(trimmed)
            db.commit()

    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", file.filename or "archive.zip")
    saved_name = f"{int(time.time())}_{safe_name}"
    saved_path = os.path.join(X_ARCHIVE_UPLOAD_DIR, saved_name)
    with open(saved_path, "wb") as out:
        shutil.copyfileobj(file.file, out)

    try:
        likes = x_archive.parse_likes_from_zip(saved_path)
    except Exception as exc:
        try:
            os.remove(saved_path)
        except OSError:
            pass
        raise HTTPException(status_code=400, detail=f"解析归档失败：{exc}")

    new_count = 0
    existing_count = 0
    for like in likes:
        existing = (
            db.query(models.XPost)
            .filter(models.XPost.source_id == source.id, models.XPost.tweet_id == like.tweet_id)
            .first()
        )
        if existing:
            existing_count += 1
            if not existing.full_text and like.full_text:
                existing.full_text = like.full_text
            existing.archive_name = file.filename or saved_name
            continue
        post = models.XPost(
            source_id=source.id,
            tweet_id=like.tweet_id,
            url=like.url,
            author_screen_name=like.author_screen_name,
            full_text=like.full_text,
            archive_name=file.filename or saved_name,
            status="pending",
        )
        db.add(post)
        new_count += 1

    source.last_archive_name = file.filename or saved_name
    source.last_archive_imported_at = datetime.utcnow()
    db.commit()
    db.refresh(source)

    return {
        "source": source,
        "archive_name": source.last_archive_name,
        "parsed": len(likes),
        "new_posts": new_count,
        "existing_posts": existing_count,
        "stats": x_import_stats(source.id, db),
    }


@router.post("/x/imports", response_model=schemas.XImportJob)
def start_x_import(payload: schemas.XImportStartRequest, db: Session = Depends(get_db)):
    source = get_x_source_or_404(payload.source_id, db)
    if not source.download_root_path:
        raise HTTPException(status_code=400, detail="请先设置下载位置")

    existing = x_importer.latest_job_for_source(source.id)
    if existing and existing.status in {"queued", "preparing", "running", "paused"}:
        raise HTTPException(status_code=409, detail="已有正在进行的导入任务")

    post_ids = x_importer.select_pending_post_ids(
        db,
        source.id,
        retry_failed_only=payload.retry_failed_only,
        retry_skipped_only=payload.retry_skipped_only,
    )
    job_id = str(uuid.uuid4())
    try:
        job = x_importer.start_job(
            job_id=job_id,
            source_id=source.id,
            download_root=source.download_root_path,
            thumbnail_dir=THUMBNAIL_DIR,
            post_ids=post_ids,
            cookie=source.cookie,
        )
    except job_lifecycle.JobCapacityError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return job.to_dict()


@router.get("/x/imports/{job_id}", response_model=schemas.XImportJob)
def get_x_import_job(job_id: str):
    job = x_importer.get_job(job_id)
    if job:
        return job.to_dict()
    snapshot = job_lifecycle.get_job_snapshot("x_import", job_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="导入任务不存在或已被清理")
    return snapshot


@router.get("/x/sources/{source_id}/active-job", response_model=Optional[schemas.XImportJob])
def get_x_active_job(source_id: int):
    job = x_importer.latest_job_for_source(source_id)
    return job.to_dict() if job else None


@router.post("/x/imports/{job_id}/pause", response_model=schemas.XImportJob)
def pause_x_import_job(job_id: str):
    job = x_importer.request_pause(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="导入任务不存在")
    return job.to_dict()


@router.post("/x/imports/{job_id}/resume", response_model=schemas.XImportJob)
def resume_x_import_job(job_id: str):
    job = x_importer.request_resume(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="导入任务不存在")
    return job.to_dict()


@router.post("/x/imports/{job_id}/cancel", response_model=schemas.XImportJob)
def cancel_x_import_job(job_id: str):
    job = x_importer.request_cancel(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="导入任务不存在")
    return job.to_dict()


@router.post("/x/sources/{source_id}/sync", response_model=schemas.XSyncJob)
def start_x_sync(source_id: int, db: Session = Depends(get_db)):
    source = get_x_source_or_404(source_id, db)
    if not source.cookie:
        raise HTTPException(status_code=400, detail="请先保存账号 cookie 再使用直接同步")

    existing = x_sync.latest_sync_for_source(source.id)
    if existing and existing.status in ("queued", "running"):
        raise HTTPException(status_code=409, detail="已有同步任务在进行")

    try:
        job = x_sync.start_sync(source_id=source.id, cookie=source.cookie)
    except job_lifecycle.JobCapacityError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return job.to_dict()


@router.get("/x/syncs/{job_id}", response_model=schemas.XSyncJob)
def get_x_sync_job(job_id: str):
    job = x_sync.get_sync(job_id)
    if job:
        return job.to_dict()
    snapshot = job_lifecycle.get_job_snapshot("x_sync", job_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="同步任务不存在或已被清理")
    return snapshot


@router.get("/x/sources/{source_id}/active-sync", response_model=Optional[schemas.XSyncJob])
def get_x_active_sync(source_id: int):
    job = x_sync.latest_sync_for_source(source_id)
    return job.to_dict() if job else None


@router.post("/x/syncs/{job_id}/cancel", response_model=schemas.XSyncJob)
def cancel_x_sync_job(job_id: str):
    job = x_sync.request_cancel(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="同步任务不存在")
    return job.to_dict()
