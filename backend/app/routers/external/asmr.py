from datetime import datetime
import hashlib
import logging
import os
import uuid
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from ... import asmr_source, models, schemas, scanner
from ...database import get_db
from ...services import job_lifecycle
from ...services.external import (
    DOWNLOAD_JOBS,
    external_cover_sidecar_rel_path,
    get_cover_extension,
    prepare_asmr_download_plan_for_item,
    run_asmr_download_job,
    serialize_external_favorite_items,
)
from ...services.media_access import get_source_or_404
from ...services.thumbnails import THUMBNAIL_DIR
from .downloader import _push_external_items

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/external/asmr/mirrors/ping")
def asmr_ping_mirrors(payload: dict = None):
    payload = payload or {}
    api_base = (payload.get("api_base") or "").strip()
    raw_mirrors = payload.get("api_mirrors") or ""
    bases = asmr_source.candidate_bases(
        preferred=api_base if api_base else None,
        mirrors=asmr_source.parse_mirrors(raw_mirrors) if raw_mirrors else None,
    )
    seen = set()
    ordered = []
    for b in bases:
        if b not in seen:
            seen.add(b)
            ordered.append(b)
    return {"results": [asmr_source.ping_mirror(b) for b in ordered]}


@router.post("/external/asmr/recheck-covers")
def asmr_recheck_covers(db: Session = Depends(get_db)):
    """Backfill cover thumbnails for audio Media rows downloaded before the
    cover step existed in the pipeline.
    """
    rows = db.query(models.Media).filter(
        models.Media.media_type == "audio",
        models.Media.cover_path.is_(None),
    ).all()

    checked = 0
    fixed = 0
    fetched_remote = 0
    failed = 0

    for media in rows:
        if not media.absolute_path or not os.path.isdir(media.absolute_path):
            continue
        checked += 1
        item_dir = media.absolute_path

        cover_src = scanner.get_work_cover_path(item_dir)

        if not cover_src and media.source_url:
            item = (
                db.query(models.ExternalFavoriteItem)
                .filter(
                    models.ExternalFavoriteItem.url == media.source_url,
                    models.ExternalFavoriteItem.source_type == "asmr",
                )
                .first()
            )
            cover_url = (item.cover_url or "").strip() if item else ""
            if cover_url:
                try:
                    content, content_type = asmr_source.fetch_file(cover_url)
                    ext = get_cover_extension(content_type, cover_url)
                    cover_dst = os.path.join(item_dir, f"cover{ext}")
                    with open(cover_dst, "wb") as cover_file:
                        cover_file.write(content)
                    cover_src = cover_dst
                    fetched_remote += 1
                except Exception as exc:  # noqa: BLE001
                    logger.warning("recheck-covers: remote fetch failed for %r: %s", media.title, exc)
                    failed += 1
                    continue

        if not cover_src:
            continue

        digest = hashlib.md5(item_dir.encode("utf-8")).hexdigest()[:12]
        thumb_name = f"thumb_audio_{digest}_{int(datetime.now().timestamp())}.jpg"
        thumb_path = os.path.join(THUMBNAIL_DIR, thumb_name)
        if scanner.make_work_thumbnail(cover_src, thumb_path):
            media.cover_path = thumb_name
            fixed += 1
        else:
            failed += 1

    db.commit()
    return {
        "checked": checked,
        "fixed": fixed,
        "fetched_remote": fetched_remote,
        "failed": failed,
    }


@router.post("/external/asmr/sync", response_model=schemas.ExternalFavoriteSyncResponse)
def sync_asmr_favorites(payload: schemas.AsmrSyncRequest, db: Session = Depends(get_db)):
    if payload.source_id:
        source = get_source_or_404(payload.source_id, db)
    else:
        source = (
            db.query(models.ExternalFavoriteSource)
            .filter(
                models.ExternalFavoriteSource.source_type == "asmr",
                models.ExternalFavoriteSource.favorites_url == payload.api_base,
            )
            .first()
        )
        if not source:
            source = models.ExternalFavoriteSource(
                source_type="asmr",
                name=payload.name or "ASMR",
                favorites_url=payload.api_base,
            )
            db.add(source)
            db.flush()

    source.name = payload.name or source.name
    source.favorites_url = payload.api_base or source.favorites_url
    source.api_mirrors = payload.api_mirrors if payload.api_mirrors is not None else source.api_mirrors
    source.audio_format_filter = payload.audio_format_filter or source.audio_format_filter or "all"
    source.audio_version_filter = payload.audio_version_filter or source.audio_version_filter or "all"
    source.playlist_url = payload.playlist_url if payload.playlist_url is not None else source.playlist_url
    if payload.download_root_path is not None:
        source.download_root_path = payload.download_root_path.strip() or None
    if payload.username:
        source.username = payload.username

    api_base = asmr_source.normalize_api_base(source.favorites_url)
    mirrors = asmr_source.parse_mirrors(source.api_mirrors) if source.api_mirrors else None
    token = source.cookie or ""

    if payload.password:
        login_name = (payload.username or source.username or "").strip()
        if not login_name:
            raise HTTPException(status_code=400, detail="登录需要用户名")
        try:
            token, working_base = asmr_source.login(
                preferred_base=api_base,
                name=login_name,
                password=payload.password,
                mirrors=mirrors,
            )
        except asmr_source.AsmrApiError as exc:
            source.status = "error"
            source.last_error = f"登录失败：{exc}"
            db.commit()
            raise HTTPException(status_code=401, detail=f"asmr.one 登录失败：{exc}")
        source.favorites_url = working_base
        source.cookie = token
        source.username = login_name
    elif not token:
        raise HTTPException(
            status_code=400,
            detail="尚未登录 asmr.one：请填写账号密码后再同步（密码只用于换取 token，不会存储）",
        )

    source.status = "syncing"
    source.last_error = None
    db.commit()

    try:
        if source.playlist_url:
            playlist_id = asmr_source.extract_playlist_id(source.playlist_url)
            parsed_works = asmr_source.fetch_playlist_works(
                preferred_base=source.favorites_url,
                token=token,
                playlist_id=playlist_id,
                page_limit=payload.page_limit,
                mirrors=mirrors,
            )
        else:
            parsed_works = asmr_source.fetch_marked_works(
                working_base=source.favorites_url,
                token=token,
                page_limit=payload.page_limit,
                mirrors=mirrors,
            )

        now = datetime.utcnow()
        existing_items = {
            item.external_id: item
            for item in db.query(models.ExternalFavoriteItem)
            .filter(models.ExternalFavoriteItem.source_id == source.id)
            .all()
        }
        for db_item in existing_items.values():
            db_item.sync_position = None

        deduped = {w.external_id: w for w in parsed_works if w.external_id}
        for sync_position, work in enumerate(deduped.values()):
            db_item = existing_items.get(work.external_id)
            if not db_item:
                db_item = models.ExternalFavoriteItem(
                    source=source,
                    source_type="asmr",
                    external_id=work.external_id,
                    title=work.title or work.external_id,
                    url=work.url or "",
                    cover_url=work.cover_url,
                    category_name=work.category_name or None,
                    sync_position=sync_position,
                    last_seen_at=now,
                )
                db.add(db_item)
            else:
                db_item.title = work.title or db_item.title
                db_item.url = work.url or db_item.url
                db_item.cover_url = work.cover_url or db_item.cover_url
                db_item.category_name = work.category_name or db_item.category_name
                db_item.sync_position = sync_position
                db_item.last_seen_at = now

        source.status = "ok"
        source.last_synced_at = now
        source.last_error = None
        db.commit()
        db.refresh(source)

        items = (
            db.query(models.ExternalFavoriteItem)
            .filter(models.ExternalFavoriteItem.source_id == source.id)
            .order_by(
                models.ExternalFavoriteItem.sync_position.is_(None),
                models.ExternalFavoriteItem.sync_position.asc(),
                models.ExternalFavoriteItem.id.desc(),
            )
            .limit(100)
            .all()
        )
        return {
            "source": source,
            "synced_count": len(deduped),
            "items": serialize_external_favorite_items(items, db),
        }
    except HTTPException:
        source.status = "error"
        source.last_error = "同步失败"
        db.commit()
        raise
    except asmr_source.AsmrApiError as exc:
        source.status = "error"
        source.last_error = f"API 错误：{exc}"
        if exc.status == 401:
            source.cookie = None
        db.commit()
        http_status = 401 if exc.status == 401 else 502
        raise HTTPException(status_code=http_status, detail=f"同步 ASMR 收藏失败：{exc}")
    except Exception as exc:
        source.status = "error"
        source.last_error = str(exc)
        db.commit()
        raise HTTPException(status_code=502, detail=f"同步 ASMR 收藏失败：{exc}")


@router.post("/external/asmr/downloads", response_model=schemas.ExternalDownloadJob)
def create_asmr_download_job(
    payload: schemas.ExternalDownloadRequest,
    background_tasks: BackgroundTasks,
):
    download_root_path = payload.download_root_path.strip()
    if not download_root_path:
        raise HTTPException(status_code=400, detail="请先设置下载位置")

    try:
        job_lifecycle.admit_new_job("external_download", DOWNLOAD_JOBS)
    except job_lifecycle.JobCapacityError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    job_id = str(uuid.uuid4())
    DOWNLOAD_JOBS[job_id] = {
        "job_id": job_id,
        "status": "running",
        "total": len(payload.item_ids),
        "completed": 0,
        "failed": 0,
        "message": "准备下载",
        "pages_total": 0,
        "pages_done": 0,
        "bytes_total": 0,
        "downloaded_bytes": 0,
        "bytes_total_known": False,
        "unknown_size_files": 0,
        "cancel_requested": False,
        "current_book_title": "",
        "current_book_total_pages": 0,
        "current_book_downloaded_pages": 0,
        "tasks": [
            {
                "id": str(item_id),
                "item_id": item_id,
                "title": "",
                "status": "pending",
                "total_pages": 0,
                "downloaded_pages": 0,
                "error": None,
            }
            for item_id in payload.item_ids
        ],
        "results": [],
    }
    job_lifecycle.record_job("external_download", DOWNLOAD_JOBS[job_id])
    background_tasks.add_task(run_asmr_download_job, job_id, payload.item_ids, download_root_path)
    return DOWNLOAD_JOBS[job_id]


@router.post("/external/asmr/push")
def push_asmr_to_downloader(payload: schemas.ExternalDownloadRequest, db: Session = Depends(get_db)):
    def build(item, source, root):
        if (source.source_type or "") != "asmr":
            raise RuntimeError("不是 ASMR 条目")
        plan = prepare_asmr_download_plan_for_item(item, source, root)
        item_dir = plan["item_dir"]
        files = []
        for f in plan["files"]:
            rel = os.path.relpath(f["local_path"], item_dir).replace(os.sep, "/")
            files.append({
                "url": f["url"],
                "rel_path": rel,
                "headers": {
                    "User-Agent": "HE-Manager/1.0 local ASMR sync",
                    "Referer": asmr_source.WEB_WORK_BASE + "/",
                },
            })
        cover_rel = external_cover_sidecar_rel_path(item)
        if cover_rel:
            files.append({
                "url": item.cover_url,
                "rel_path": cover_rel,
                "optional": True,
                "headers": {
                    "User-Agent": "HE-Manager/1.0 local ASMR sync",
                    "Referer": asmr_source.WEB_WORK_BASE + "/",
                },
            })
        return item_dir, files

    return _push_external_items(payload, db, build)
