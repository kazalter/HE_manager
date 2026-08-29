import mimetypes
import os
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import FileResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from ... import models, schemas
from ...database import get_db
from ...services import job_lifecycle
from ...services.external import (
    DOWNLOAD_JOBS,
    ensure_external_cover_cache,
    find_local_media_for_external_item,
    get_external_storage_dirs,
    serialize_external_favorite_items,
)
from ...services.media_access import get_source_or_404

router = APIRouter()


def _cover_media_type(path: str) -> str:
    """Return an image MIME type from the actual cached bytes, not its suffix.

    WNACG's CDN can serve WebP bytes from URLs ending in ``.jpg`` or ``.png``.
    The cache preserves that URL-derived suffix, so FileResponse's default MIME
    inference can make browsers reject the image under ``nosniff``.
    """
    try:
        with open(path, "rb") as image_file:
            header = image_file.read(16)
    except OSError:
        return "application/octet-stream"
    if header.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if header.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if header.startswith(b"RIFF") and header[8:12] == b"WEBP":
        return "image/webp"
    if len(header) >= 12 and header[4:12] in (b"ftypavif", b"ftypavis"):
        return "image/avif"
    return mimetypes.guess_type(path)[0] or "application/octet-stream"


@router.get("/external/sources", response_model=List[schemas.ExternalFavoriteSource])
def list_external_sources(db: Session = Depends(get_db)):
    return db.query(models.ExternalFavoriteSource).order_by(models.ExternalFavoriteSource.id.desc()).all()


@router.patch("/external/sources/{source_id}", response_model=schemas.ExternalFavoriteSource)
def update_external_source(source_id: int, payload: schemas.ExternalFavoriteSourceUpdate, db: Session = Depends(get_db)):
    source = get_source_or_404(source_id, db)
    data = payload.dict(exclude_unset=True)
    if "name" in data and data["name"]:
        source.name = data["name"]
    if "favorites_url" in data and data["favorites_url"]:
        source.favorites_url = data["favorites_url"]
    if "download_root_path" in data:
        source.download_root_path = (data["download_root_path"] or "").strip() or None
        if (source.source_type or "wnacg") != "asmr":
            get_external_storage_dirs(source)
    if "audio_format_filter" in data:
        source.audio_format_filter = (data["audio_format_filter"] or "").strip() or "all"
    if "audio_version_filter" in data:
        source.audio_version_filter = (data["audio_version_filter"] or "").strip() or "all"
    if "playlist_url" in data:
        source.playlist_url = (data["playlist_url"] or "").strip() or None
    if "api_mirrors" in data:
        source.api_mirrors = (data["api_mirrors"] or "").strip() or None
    if "proxy" in data:
        source.proxy = (data["proxy"] or "").strip() or None
    db.commit()
    db.refresh(source)
    return source


@router.get("/external/favorites", response_model=List[schemas.ExternalFavoriteItem])
def list_external_favorites(
    response: Response,
    source_type: Optional[str] = None,
    source_id: Optional[int] = None,
    search: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    query = db.query(models.ExternalFavoriteItem).options(
        joinedload(models.ExternalFavoriteItem.source)
    )
    if source_type:
        query = query.filter(models.ExternalFavoriteItem.source_type == source_type)
    if source_id:
        query = query.filter(models.ExternalFavoriteItem.source_id == source_id)
    if search:
        pattern = f"%{search}%"
        query = query.filter(or_(
            models.ExternalFavoriteItem.title.ilike(pattern),
            models.ExternalFavoriteItem.category_name.ilike(pattern),
        ))
    total = query.order_by(None).count()
    response.headers["X-Total-Count"] = str(total)
    response.headers["Access-Control-Expose-Headers"] = "X-Total-Count"
    favorite_items = (
        query.order_by(
            models.ExternalFavoriteItem.sync_position.is_(None),
            models.ExternalFavoriteItem.sync_position.asc(),
            models.ExternalFavoriteItem.id.desc(),
        )
        .offset(max(0, offset))
        .limit(max(1, min(limit, 200)))
        .all()
    )
    return serialize_external_favorite_items(favorite_items, db)


@router.post("/external/favorites/reconcile")
def reconcile_external_favorites(
    source_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """Explicitly repair stale/missing local links; list GETs stay read-only."""
    query = db.query(models.ExternalFavoriteItem).options(
        joinedload(models.ExternalFavoriteItem.source)
    )
    if source_id is not None:
        query = query.filter(models.ExternalFavoriteItem.source_id == source_id)
    items = query.order_by(models.ExternalFavoriteItem.id.asc()).all()
    linked = 0
    for item in items:
        if find_local_media_for_external_item(item, db) is not None:
            linked += 1
    return {"checked": len(items), "linked": linked}


@router.get("/external/favorites/{favorite_id}/cover")
def get_external_favorite_cover(favorite_id: int, db: Session = Depends(get_db)):
    item = db.query(models.ExternalFavoriteItem).filter(models.ExternalFavoriteItem.id == favorite_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="External favorite not found")
    if not item.cover_url:
        raise HTTPException(status_code=404, detail="Cover not found")

    source = get_source_or_404(item.source_id, db)
    try:
        cached_cover = ensure_external_cover_cache(item, source)
        if cached_cover and os.path.exists(cached_cover):
            return FileResponse(cached_cover, media_type=_cover_media_type(cached_cover))
        raise RuntimeError("封面缓存失败")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"读取外部封面失败：{exc}")


@router.post("/external/downloads/{job_id}/cancel", response_model=schemas.ExternalDownloadJob)
def cancel_external_download_job(job_id: str):
    job = DOWNLOAD_JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Download job not found")

    if job["status"] in {"completed", "failed", "canceled"}:
        return job

    job["cancel_requested"] = True
    job["status"] = "canceling"
    job["message"] = "正在取消下载"
    return job


@router.get("/external/downloads/{job_id}", response_model=schemas.ExternalDownloadJob)
def get_external_download_job(job_id: str):
    job = DOWNLOAD_JOBS.get(job_id) or job_lifecycle.get_job_snapshot("external_download", job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Download job not found")
    return job
