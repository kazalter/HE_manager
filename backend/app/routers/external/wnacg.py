from datetime import datetime
from typing import List
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from ... import downloader_push, external_sources, models, schemas
from ...database import get_db
from ...services import job_lifecycle
from ...services.external import (
    DOWNLOAD_JOBS,
    external_cover_sidecar_rel_path,
    get_url_base,
    prepare_wnacg_download_plan,
    run_wnacg_download_job,
    serialize_external_favorite_items,
)
from ...services.media_access import get_source_or_404
from .downloader import _push_external_items

router = APIRouter()


@router.post("/external/wnacg/sync", response_model=schemas.ExternalFavoriteSyncResponse)
def sync_wnacg_favorites(payload: schemas.ExternalFavoriteSyncRequest, db: Session = Depends(get_db)):
    if payload.source_id:
        source = get_source_or_404(payload.source_id, db)
        source.name = payload.name or source.name
        source.favorites_url = payload.favorites_url or source.favorites_url
        if payload.download_root_path is not None:
            source.download_root_path = payload.download_root_path.strip() or None
        if payload.cookie is not None:
            source.cookie = payload.cookie.strip()
    else:
        source = (
            db.query(models.ExternalFavoriteSource)
            .filter(
                models.ExternalFavoriteSource.source_type == "wnacg",
                models.ExternalFavoriteSource.favorites_url == payload.favorites_url,
            )
            .first()
        )
        if not source:
            source = models.ExternalFavoriteSource(
                source_type="wnacg",
                name=payload.name,
                favorites_url=payload.favorites_url,
                cookie=(payload.cookie or "").strip() or None,
                download_root_path=(payload.download_root_path or "").strip() or None,
            )
            db.add(source)
            db.flush()
        else:
            source.name = payload.name or source.name
            if payload.download_root_path is not None:
                source.download_root_path = payload.download_root_path.strip() or None
            if payload.cookie is not None:
                source.cookie = payload.cookie.strip() or None

    cookie = source.cookie or ""
    if not cookie:
        raise HTTPException(status_code=400, detail="请填写你自己账号的 Cookie 后再同步收藏页")

    source.status = "syncing"
    source.last_error = None
    db.commit()

    try:
        existing_items = {
            item.external_id: item
            for item in db.query(models.ExternalFavoriteItem).filter(models.ExternalFavoriteItem.source_id == source.id).all()
        }
        existing_external_ids = set(existing_items.keys())
        base_url = get_url_base(source.favorites_url)
        first_html = external_sources.fetch_html(source.favorites_url, cookie, proxy=source.proxy)
        categories = external_sources.parse_wnacg_categories(first_html)
        parsed_items: List[external_sources.ParsedExternalFavorite] = []

        if payload.category_id:
            categories = [category for category in categories if category.id == payload.category_id]
            if not categories:
                categories = [external_sources.WnacgCategory(id=payload.category_id, name=f"分类 {payload.category_id}")]

        if categories:
            for category in categories:
                for page in range(1, payload.page_limit + 1):
                    page_url = external_sources.wnacg_category_url(category.id, page, base_url=base_url)
                    page_html = external_sources.fetch_html(page_url, cookie, proxy=source.proxy)
                    page_items = external_sources.parse_wnacg_favorites(
                        page_html,
                        base_url=base_url,
                        category_id=category.id,
                        category_name=category.name,
                    )
                    parsed_items.extend(page_items)
                    if any(item.external_id in existing_external_ids for item in page_items):
                        break
                    if not external_sources.html_has_next_page(page_html):
                        break
        else:
            parsed_items = external_sources.parse_wnacg_favorites(first_html, base_url=base_url)

        now = datetime.utcnow()
        for db_item in existing_items.values():
            db_item.sync_position = None

        deduped = {item.external_id: item for item in parsed_items}
        for sync_position, item in enumerate(deduped.values()):
            db_item = existing_items.get(item.external_id)
            if not db_item:
                db_item = models.ExternalFavoriteItem(
                    source=source,
                    source_type="wnacg",
                    external_id=item.external_id,
                    title=item.title,
                    url=item.url,
                    cover_url=item.cover_url,
                    category_id=item.category_id,
                    category_name=item.category_name,
                    sync_position=sync_position,
                    last_seen_at=now,
                )
                db.add(db_item)
            else:
                db_item.title = item.title
                db_item.url = item.url
                db_item.cover_url = item.cover_url or db_item.cover_url
                db_item.category_id = item.category_id
                db_item.category_name = item.category_name
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
    except Exception as exc:
        source.status = "error"
        source.last_error = str(exc)
        db.commit()
        raise HTTPException(status_code=502, detail=f"同步 WNACG 收藏失败：{exc}")


@router.post("/external/wnacg/downloads", response_model=schemas.ExternalDownloadJob)
def create_wnacg_download_job(
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
    background_tasks.add_task(run_wnacg_download_job, job_id, payload.item_ids, download_root_path)
    return DOWNLOAD_JOBS[job_id]


@router.post("/external/wnacg/push")
def push_wnacg_to_downloader(payload: schemas.ExternalDownloadRequest, db: Session = Depends(get_db)):
    """把选中的 wnacg 收藏推给下载中心。"""
    def build(item, source, root):
        if (source.source_type or "wnacg") != "wnacg":
            raise RuntimeError("不是 wnacg 条目")
        plan = prepare_wnacg_download_plan(item, source, root)
        item_dir = plan["item_dir"]
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": item.url or source.favorites_url or "",
        }
        if source.cookie:
            headers["Cookie"] = source.cookie
        files = [
            {"url": url, "rel_path": f"{idx:03d}{downloader_push.url_ext(url)}", "headers": headers}
            for idx, url in enumerate(plan["image_urls"], start=1)
        ]
        cover_rel = external_cover_sidecar_rel_path(item)
        if cover_rel:
            cover_headers = dict(headers)
            cover_headers["Referer"] = source.favorites_url or item.url or ""
            files.append({"url": item.cover_url, "rel_path": cover_rel, "headers": cover_headers, "optional": True})
        return item_dir, files

    return _push_external_items(payload, db, build)
