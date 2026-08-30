from datetime import datetime
import hashlib
import logging
import mimetypes
import os
import string
from typing import List, Optional
import zipfile

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from .. import auth, database, media_cleanup, models, scanner, schemas, tagging
from ..database import get_db
from ..services.manga_pages import get_manga_image_files
from ..services.media_access import get_media_or_404
from ..services.range_response import get_ranged_file_response
from ..services.thumbnails import THUMBNAIL_DIR, remove_cover_thumbnails

logger = logging.getLogger(__name__)

router = APIRouter()


def _queue_folder_scan(folder_id: int, background_tasks: BackgroundTasks) -> None:
    reservation = scanner.reserve_folder_scan(folder_id)
    if reservation is None:
        raise HTTPException(status_code=409, detail="Folder scan already queued or running")
    try:
        background_tasks.add_task(scanner.scan_folder, folder_id, reservation)
    except Exception:
        scanner.release_folder_scan(folder_id, reservation)
        raise


@router.get("/search-folder")
def search_folder(name: str):
    results = []
    search_roots = []

    for letter in string.ascii_uppercase:
        drive = f"{letter}:\\"
        if os.path.exists(drive):
            search_roots.append(drive)

    search_roots.append(os.path.expanduser("~"))

    for root in search_roots:
        try:
            for entry in os.listdir(root):
                full = os.path.join(root, entry)
                if os.path.isdir(full) and entry.lower() == name.lower():
                    results.append(full)
        except (PermissionError, OSError):
            continue

    return {"results": results}


@router.post("/folders", response_model=schemas.Folder)
def create_folder(folder: schemas.FolderCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    if not os.path.exists(folder.path):
        raise HTTPException(status_code=400, detail="指定的文件夹路径不存在，请检查路径是否正确。")

    if not os.path.isdir(folder.path):
        raise HTTPException(status_code=400, detail="指定的路径不是一个目录。")

    db_folder = db.query(models.Folder).filter(models.Folder.path == folder.path).first()
    if db_folder:
        db_folder.scan_mode = folder.scan_mode
        db_folder.thumbnail_enabled = folder.thumbnail_enabled
        db_folder.thumbnail_interval = folder.thumbnail_interval
        db.commit()
        db.refresh(db_folder)
        _queue_folder_scan(db_folder.id, background_tasks)
        return db_folder

    new_folder = models.Folder(
        path=folder.path,
        scan_mode=folder.scan_mode,
        thumbnail_enabled=folder.thumbnail_enabled,
        thumbnail_interval=folder.thumbnail_interval,
    )
    db.add(new_folder)
    db.commit()
    db.refresh(new_folder)

    _queue_folder_scan(new_folder.id, background_tasks)
    return new_folder


@router.post("/folders/{folder_id}/scan", response_model=schemas.Folder)
def scan_folder(folder_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    db_folder = db.query(models.Folder).filter(models.Folder.id == folder_id).first()
    if not db_folder:
        raise HTTPException(status_code=404, detail="Folder not found")

    _queue_folder_scan(folder_id, background_tasks)
    return db_folder


@router.get("/folders", response_model=List[schemas.Folder])
def list_folders(db: Session = Depends(get_db)):
    return db.query(models.Folder).all()


@router.delete("/folders/{folder_id}")
def delete_folder(folder_id: int, db: Session = Depends(get_db)):
    db_folder = db.query(models.Folder).filter(models.Folder.id == folder_id).first()
    if not db_folder:
        raise HTTPException(status_code=404, detail="Folder not found")

    associated_media = db.query(models.Media).filter(models.Media.folder_id == folder_id).all()
    media_cleanup.detach_media_references(db, [media.id for media in associated_media])
    for media in associated_media:
        remove_cover_thumbnails(media.cover_path)

    db.delete(db_folder)
    db.commit()
    return {"message": "Folder and associated media deleted from library"}


@router.get("/media", response_model=List[schemas.Media])
def list_media(
    response: Response,
    media_type: Optional[str] = None,
    search: Optional[str] = None,
    tag: Optional[str] = None,
    favorite: Optional[bool] = None,
    view_status: Optional[str] = None,
    is_missing: Optional[bool] = None,
    duplicate_status: Optional[str] = None,
    include_hidden_duplicates: bool = False,
    source_site: Optional[str] = None,
    sort: str = "date",
    limit: Optional[int] = None,
    offset: Optional[int] = None,
    db: Session = Depends(get_db),
):
    query = db.query(models.Media).options(selectinload(models.Media.tags))
    if media_type:
        query = query.filter(models.Media.media_type == media_type)
    if search:
        query = query.filter(models.Media.title.ilike(f"%{search}%"))
    if tag:
        query = query.join(models.Media.tags).filter(models.Tag.name == tag)
    if favorite is not None:
        query = query.filter(models.Media.favorite == favorite)
    if view_status:
        query = query.filter(models.Media.view_status == view_status)
    if is_missing is not None:
        query = query.filter(models.Media.is_missing == is_missing)
    if source_site:
        if source_site == "local":
            query = query.filter(models.Media.source_site.is_(None))
        else:
            query = query.filter(models.Media.source_site == source_site)
    if duplicate_status:
        query = query.filter(models.Media.duplicate_status == duplicate_status)
    elif not include_hidden_duplicates:
        query = query.filter(
            models.Media.duplicate_status.notin_(["checking", "strong_duplicate", "suspected_duplicate", "dedup_excluded"])
        )

    # Preserve the array response for existing clients while exposing the
    # filtered total needed by the web library's server-side pagination.
    total = query.order_by(None).count()
    response.headers["X-Total-Count"] = str(total)
    response.headers["Access-Control-Expose-Headers"] = "X-Total-Count"

    if sort == "title":
        query = query.order_by(models.Media.title.asc())
    elif sort == "rating":
        query = query.order_by(models.Media.rating.desc(), models.Media.id.desc())
    elif sort == "opened":
        query = query.order_by(models.Media.last_opened_at.desc(), models.Media.id.desc())
    else:
        query = query.order_by(models.Media.id.desc())

    effective_limit = 200 if limit is None else max(1, min(limit, 200))
    query = query.limit(effective_limit)
    if offset is not None:
        query = query.offset(max(0, offset))

    return query.all()


@router.get("/mobile/media", response_model=List[schemas.Media])
def list_mobile_media(
    response: Response,
    media_type: Optional[str] = None,
    search: Optional[str] = None,
    sort: str = "date",
    limit: Optional[int] = None,
    offset: Optional[int] = None,
    _: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    query = (
        db.query(models.Media)
        .filter(models.Media.is_missing == False)
        .filter(models.Media.duplicate_status.notin_(["checking", "strong_duplicate", "suspected_duplicate", "dedup_excluded"]))
        .options(selectinload(models.Media.tags))
    )
    if media_type:
        query = query.filter(models.Media.media_type == media_type)
    if search:
        query = query.filter(models.Media.title.ilike(f"%{search}%"))

    total = query.order_by(None).count()
    response.headers["X-Total-Count"] = str(total)
    response.headers["Access-Control-Expose-Headers"] = "X-Total-Count"

    if sort == "title":
        query = query.order_by(models.Media.title.asc())
    elif sort == "rating":
        query = query.order_by(models.Media.rating.desc(), models.Media.id.desc())
    elif sort == "opened":
        query = query.order_by(models.Media.last_opened_at.desc(), models.Media.id.desc())
    else:
        query = query.order_by(models.Media.id.desc())

    # Omitted pagination remains a full array for released Android clients.
    # New clients can page with a bounded limit and the total response header.
    if limit is not None:
        query = query.limit(max(1, min(limit, 200)))
    if offset is not None:
        query = query.offset(max(0, offset))
    return query.all()


@router.get("/mobile/media/{media_id}", response_model=schemas.Media)
def get_mobile_media(media_id: int, _: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    return get_media_or_404(media_id, db)


@router.get("/mobile/thumbnails/{filename}")
def get_mobile_thumbnail(filename: str, _: models.User = Depends(auth.get_current_user)):
    safe_name = os.path.basename(filename)
    thumb_path = os.path.join(THUMBNAIL_DIR, safe_name)
    if not os.path.exists(thumb_path):
        raise HTTPException(status_code=404, detail="Thumbnail not found")
    return FileResponse(thumb_path)


@router.get("/media/{media_id}", response_model=schemas.Media)
def get_media(media_id: int, db: Session = Depends(get_db)):
    media = get_media_or_404(media_id, db)

    if media.is_missing and os.path.exists(media.absolute_path):
        media.is_missing = False
        media.missing_since = None

    media.last_opened_at = datetime.utcnow()
    if media.view_status == "unviewed":
        media.view_status = "viewing"
    db.commit()
    db.refresh(media)
    return media


@router.patch("/media/{media_id}", response_model=schemas.Media)
def update_media(media_id: int, payload: schemas.MediaUpdate, db: Session = Depends(get_db)):
    media = get_media_or_404(media_id, db)
    data = payload.dict(exclude_unset=True)
    if "view_status" in data and data["view_status"] not in {"unviewed", "viewing", "viewed"}:
        raise HTTPException(status_code=400, detail="view_status must be unviewed, viewing, or viewed")

    for key, value in data.items():
        setattr(media, key, value)

    if "progress" in data:
        progress = int(media.progress or 0)
        if media.media_type == "video":
            if progress <= 0:
                media.view_status = "unviewed"
            elif media.duration:
                ratio = progress / max(1, int(media.duration))
                media.view_status = "viewed" if ratio >= 0.95 else "viewing"
            else:
                media.view_status = "viewing"
        elif media.media_type == "manga" and media.page_count:
            if progress >= int(media.page_count) - 1:
                media.view_status = "viewed"
            elif progress > 0:
                media.view_status = "viewing"
            else:
                media.view_status = "unviewed"

    db.commit()
    db.refresh(media)
    return media


@router.delete("/media/{media_id}")
def delete_media(media_id: int, db: Session = Depends(get_db)):
    media = get_media_or_404(media_id, db)
    remove_cover_thumbnails(media.cover_path)

    media_cleanup.detach_media_references(db, [media.id])

    db.delete(media)
    db.commit()
    return {"message": "Media removed from library"}


@router.post("/media/{media_id}/recheck", response_model=schemas.Media)
def recheck_media(media_id: int, db: Session = Depends(get_db)):
    media = get_media_or_404(media_id, db)

    if os.path.exists(media.absolute_path):
        media.is_missing = False
        media.missing_since = None
        media.last_opened_at = datetime.utcnow()
        try:
            media.file_size = os.path.getsize(media.absolute_path)
        except OSError:
            pass
        db.commit()
        db.refresh(media)
        return media

    if not media.is_missing:
        media.is_missing = True
        media.missing_since = datetime.utcnow()
        db.commit()
        db.refresh(media)
    raise HTTPException(status_code=404, detail="File still missing")


@router.post("/system/recheck-missing")
def recheck_all_missing(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    missing_items = db.query(models.Media).filter(models.Media.is_missing == True).all()
    recovered_count = 0
    for media in missing_items:
        if os.path.exists(media.absolute_path):
            media.is_missing = False
            media.missing_since = None
            recovered_count += 1

    if recovered_count > 0:
        db.commit()

    return {"message": "Recheck completed", "total_missing_checked": len(missing_items), "recovered": recovered_count}


@router.get("/tags", response_model=List[schemas.Tag])
def list_tags(db: Session = Depends(get_db)):
    rows = (
        db.query(
            models.Tag.id,
            models.Tag.name,
            models.Tag.namespace,
            func.count(models.media_tags.c.media_id).label("count"),
        )
        .outerjoin(models.media_tags, models.Tag.id == models.media_tags.c.tag_id)
        .group_by(models.Tag.id, models.Tag.name, models.Tag.namespace)
        .order_by(models.Tag.name.asc())
        .all()
    )
    return [
        schemas.Tag(
            id=r.id,
            name=r.name,
            namespace=r.namespace or "general",
            count=int(r.count or 0),
        )
        for r in rows
    ]


@router.patch("/tags/{tag_id}", response_model=schemas.Tag)
def update_tag(tag_id: int, payload: schemas.TagUpdate, db: Session = Depends(get_db)):
    tag = db.query(models.Tag).filter(models.Tag.id == tag_id).first()
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")

    new_name = payload.name.strip() if payload.name is not None else tag.name
    if not new_name:
        raise HTTPException(status_code=400, detail="Tag name cannot be empty")

    new_ns = (payload.namespace or "general").strip() if payload.namespace is not None else (tag.namespace or "general")

    existing = (
        db.query(models.Tag)
        .filter(models.Tag.name == new_name, models.Tag.namespace == new_ns, models.Tag.id != tag.id)
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="Tag with this name and namespace already exists")

    tag.name = new_name
    tag.namespace = new_ns
    db.commit()
    db.refresh(tag)

    count = db.query(models.media_tags).filter(models.media_tags.c.tag_id == tag.id).count()
    return schemas.Tag(
        id=tag.id,
        name=tag.name,
        namespace=tag.namespace or "general",
        count=count,
    )


@router.post("/tags/{tag_id}/merge")
def merge_tag(tag_id: int, payload: schemas.TagMergeRequest, db: Session = Depends(get_db)):
    if tag_id == payload.target_id:
        raise HTTPException(status_code=400, detail="Cannot merge a tag into itself")

    source_tag = db.query(models.Tag).filter(models.Tag.id == tag_id).first()
    if not source_tag:
        raise HTTPException(status_code=404, detail="Source tag not found")

    target_tag = db.query(models.Tag).filter(models.Tag.id == payload.target_id).first()
    if not target_tag:
        raise HTTPException(status_code=404, detail="Target tag not found")

    for media in list(source_tag.media_items):
        if target_tag not in media.tags:
            media.tags.append(target_tag)
        if source_tag in media.tags:
            media.tags.remove(source_tag)

    db.delete(source_tag)
    db.commit()
    return {"message": "Merged successfully", "source_id": tag_id, "target_id": payload.target_id}


@router.delete("/tags/{tag_id}")
def delete_tag(tag_id: int, db: Session = Depends(get_db)):
    tag = db.query(models.Tag).filter(models.Tag.id == tag_id).first()
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")

    for media in list(tag.media_items):
        if tag in media.tags:
            media.tags.remove(tag)

    db.delete(tag)
    db.commit()
    return {"message": "Tag deleted successfully", "id": tag_id}


@router.post("/media/{media_id}/tags", response_model=schemas.Media)
def add_media_tag(media_id: int, payload: schemas.TagCreate, db: Session = Depends(get_db)):
    media = get_media_or_404(media_id, db)
    tag_name = payload.name.strip()
    if not tag_name:
        raise HTTPException(status_code=400, detail="Tag name cannot be empty")

    namespace = (payload.namespace or "general").strip() or "general"
    tag = tagging.attach_tag(db, media, tag_name, namespace)
    db.commit()
    db.refresh(media)
    return media


@router.delete("/media/{media_id}/tags/{tag_id}", response_model=schemas.Media)
def remove_media_tag(media_id: int, tag_id: int, db: Session = Depends(get_db)):
    media = get_media_or_404(media_id, db)
    tag = db.query(models.Tag).filter(models.Tag.id == tag_id).first()
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")
    if tag in media.tags:
        media.tags.remove(tag)
    db.commit()
    db.refresh(media)
    return media


@router.get("/stream/{media_id}")
def stream_media(request: Request, media_id: int, db: Session = Depends(get_db)):
    media = get_media_or_404(media_id, db)

    if not os.path.exists(media.absolute_path):
        if not media.is_missing:
            media.is_missing = True
            media.missing_since = datetime.utcnow()
            db.commit()
        raise HTTPException(status_code=404, detail="File not found on disk")
    elif media.is_missing:
        media.is_missing = False
        media.missing_since = None
        db.commit()

    return get_ranged_file_response(request, media.absolute_path)


@router.get("/mobile/stream/{media_id}")
def stream_mobile_media(
    request: Request,
    media_id: int,
    _: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    media = get_media_or_404(media_id, db)
    if not os.path.exists(media.absolute_path):
        if not media.is_missing:
            media.is_missing = True
            media.missing_since = datetime.utcnow()
            db.commit()
        raise HTTPException(status_code=404, detail="File not found on disk")
    elif media.is_missing:
        media.is_missing = False
        media.missing_since = None
        db.commit()

    return get_ranged_file_response(request, media.absolute_path)


@router.get("/manga/{media_id}/pages")
def get_manga_pages_count(media_id: int, db: Session = Depends(get_db)):
    media = get_media_or_404(media_id, db)
    if media.media_type != "manga":
        return {"total_pages": 0}

    try:
        total_pages = len(get_manga_image_files(media))
        media.page_count = total_pages
        db.commit()
        return {"total_pages": total_pages}
    except Exception:
        return {"total_pages": media.page_count or 0}


@router.get("/mobile/manga/{media_id}/pages")
def get_mobile_manga_pages_count(
    media_id: int,
    _: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    return get_manga_pages_count(media_id, db)


@router.get("/manga/{media_id}/page/{page_index}")
def get_manga_page(
    media_id: int,
    page_index: int,
    track_progress: bool = False,
    db: Session = Depends(get_db),
):
    media = get_media_or_404(media_id, db)
    if media.media_type != "manga":
        raise HTTPException(status_code=404, detail="Manga not found")

    if media.is_missing and os.path.exists(media.absolute_path):
        media.is_missing = False
        media.missing_since = None
        db.commit()

    try:
        files = get_manga_image_files(media)
        if not 0 <= page_index < len(files):
            raise HTTPException(status_code=404, detail="Page not found")

        if track_progress:
            media.last_opened_at = datetime.utcnow()
            media.progress = page_index
            if page_index >= len(files) - 1:
                media.view_status = "viewed"
            elif page_index > 0:
                media.view_status = "viewing"
            elif media.view_status == "unviewed":
                media.view_status = "viewing"
            db.commit()

        if media.extension == ".dir":
            img_path = files[page_index]
            with open(img_path, "rb") as f:
                content = f.read()
            mime, _ = mimetypes.guess_type(img_path)
            return Response(content=content, media_type=mime or "application/octet-stream")

        with zipfile.ZipFile(media.absolute_path, "r") as archive:
            filename = files[page_index]
            with archive.open(filename) as f:
                content = f.read()
            mime, _ = mimetypes.guess_type(filename)
            return Response(content=content, media_type=mime or "application/octet-stream")
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("Failed to serve manga page %s/%s: %s", media_id, page_index, e)
        raise HTTPException(status_code=500, detail="Failed to read page")


@router.post("/media/{media_id}/regenerate-thumbnail")
def regenerate_thumbnail(media_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    media = get_media_or_404(media_id, db)
    if media.media_type != "video":
        raise HTTPException(status_code=400, detail="Only videos support thumbnail regeneration")

    background_tasks.add_task(do_regenerate_thumbnail, media.id)
    return {"message": "Thumbnail regeneration task started"}


def do_regenerate_thumbnail(media_id: int):
    db = database.SessionLocal()
    try:
        media = db.query(models.Media).filter(models.Media.id == media_id).first()
        if not media:
            return

        file_hash = hashlib.md5(media.absolute_path.encode()).hexdigest()[:12]
        base_name = f"thumb_v_{file_hash}_{datetime.now().timestamp()}".replace(" ", "_")
        thumb_name = f"{base_name}.jpg"
        thumb_path = os.path.join(THUMBNAIL_DIR, thumb_name)

        success, t_ms, source = scanner.get_video_thumbnail(media.absolute_path, thumb_path)
        if success:
            if media.cover_path:
                old_path = os.path.join(THUMBNAIL_DIR, media.cover_path)
                if os.path.exists(old_path):
                    try:
                        os.remove(old_path)
                    except Exception:
                        pass

            media.cover_path = thumb_name
            media.cover_time_ms = t_ms
            media.cover_source = source
            db.commit()
    finally:
        db.close()


@router.get("/mobile/manga/{media_id}/page/{page_index}")
def get_mobile_manga_page(
    media_id: int,
    page_index: int,
    track_progress: bool = False,
    _: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    return get_manga_page(media_id, page_index, track_progress, db)
