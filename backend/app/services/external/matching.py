from datetime import datetime
import hashlib
import os
from typing import List, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from ... import models, scanner
from ..thumbnails import THUMBNAIL_DIR
from .covers import (
    ensure_asmr_cover_file,
    ensure_external_cover_cache,
    external_item_download_dir,
    get_asmr_storage_dirs,
    get_external_storage_dirs,
)


def ensure_external_manga_library(source: models.ExternalFavoriteSource, download_root_path: str, db: Session) -> models.Folder:
    _, _, manga_dir = get_external_storage_dirs(source, download_root_path)
    folder = db.query(models.Folder).filter(models.Folder.path == manga_dir).first()
    if folder:
        folder.scan_mode = "manga"
        folder.status = "idle"
        db.commit()
        db.refresh(folder)
        return folder

    folder = models.Folder(
        path=manga_dir,
        scan_mode="manga",
        status="idle",
        thumbnail_enabled=True,
        thumbnail_interval=1,
    )
    db.add(folder)
    db.commit()
    db.refresh(folder)
    return folder


def ensure_external_audio_library(source: models.ExternalFavoriteSource, download_root_path: str, db: Session) -> models.Folder:
    _, audio_dir = get_asmr_storage_dirs(source, download_root_path)
    folder = db.query(models.Folder).filter(models.Folder.path == audio_dir).first()
    if folder:
        folder.scan_mode = "audio_work"
        folder.status = "idle"
        db.commit()
        db.refresh(folder)
        return folder

    folder = models.Folder(
        path=audio_dir,
        scan_mode="audio_work",
        status="idle",
        thumbnail_enabled=False,
        thumbnail_interval=1,
    )
    db.add(folder)
    db.commit()
    db.refresh(folder)
    return folder


def upsert_external_downloaded_audio_media(
    item: models.ExternalFavoriteItem,
    source: models.ExternalFavoriteSource,
    item_dir: str,
    download_root_path: str,
    db: Session,
    track_count: int,
    total_bytes: int,
) -> models.Media:
    folder = ensure_external_audio_library(source, download_root_path, db)
    rel_path = os.path.relpath(item_dir, folder.path)

    media = (
        db.query(models.Media)
        .filter(models.Media.absolute_path == item_dir, models.Media.media_type == "audio")
        .first()
    )
    if media:
        media.folder_id = folder.id
        media.title = item.title
        media.relative_path = rel_path
        media.file_size = total_bytes
        media.page_count = track_count
        media.source_url = item.url
        media.source_site = source.source_type
        media.is_missing = False
    else:
        media = models.Media(
            folder_id=folder.id,
            title=item.title,
            relative_path=rel_path,
            absolute_path=item_dir,
            media_type="audio",
            extension=".dir",
            file_size=total_bytes,
            page_count=track_count,
            source_url=item.url,
            source_site=source.source_type,
            is_missing=False,
        )
        db.add(media)
        db.flush()

    if not media.cover_path:
        cover_src = ensure_asmr_cover_file(item, item_dir)
        if cover_src:
            digest = hashlib.md5(item_dir.encode("utf-8")).hexdigest()[:12]
            thumb_name = f"thumb_audio_{digest}_{int(datetime.now().timestamp())}.jpg"
            thumb_path = os.path.join(THUMBNAIL_DIR, thumb_name)
            if scanner.make_work_thumbnail(cover_src, thumb_path):
                media.cover_path = thumb_name

    folder.last_scanned_at = datetime.now()
    db.commit()
    db.refresh(media)
    return media


def wnacg_download_is_complete(item_dir: str) -> bool:
    return os.path.isfile(os.path.join(item_dir, "source.txt"))


def ensure_wnacg_source_marker(item: models.ExternalFavoriteItem, item_dir: str) -> None:
    if not item_dir or not os.path.isdir(item_dir):
        return
    info_path = os.path.join(item_dir, "source.txt")
    if os.path.exists(info_path):
        return
    with open(info_path, "w", encoding="utf-8") as info_file:
        info_file.write(f"{item.title}\n{item.url}\n")


def find_local_media_for_external_items(
    items: List[models.ExternalFavoriteItem],
    db: Session,
) -> dict[int, models.Media]:
    """Resolve list badges in one read-only query, without filesystem repair."""
    if not items:
        return {}

    urls = {item.url for item in items if item.url}
    expected_paths: dict[int, str] = {}
    for item in items:
        source = item.source
        if source and source.download_root_path:
            expected_paths[item.id] = external_item_download_dir(item, source)

    filters = []
    if urls:
        filters.append(models.Media.source_url.in_(urls))
    if expected_paths:
        filters.append(models.Media.absolute_path.in_(set(expected_paths.values())))
    if not filters:
        return {}

    media_rows = (
        db.query(models.Media)
        .filter(
            models.Media.is_missing == False,  # noqa: E712
            or_(*filters),
        )
        .order_by(models.Media.id.desc())
        .all()
    )
    by_source: dict[tuple[str, str, str], models.Media] = {}
    by_path: dict[tuple[str, str], models.Media] = {}
    for media in media_rows:
        if media.source_url and media.source_site:
            by_source.setdefault(
                (media.source_url, media.source_site, media.media_type),
                media,
            )
        if media.absolute_path:
            by_path.setdefault((media.absolute_path, media.media_type), media)

    resolved: dict[int, models.Media] = {}
    for item in items:
        expected_type = "audio" if (item.source_type or "") == "asmr" else "manga"
        media = by_source.get((item.url, item.source_type, expected_type))
        if media is None and item.id in expected_paths:
            media = by_path.get((expected_paths[item.id], expected_type))
        if media is not None:
            resolved[item.id] = media
    return resolved


def find_local_media_for_external_item(item: models.ExternalFavoriteItem, db: Session) -> Optional[models.Media]:
    expected_media_type = "audio" if (item.source_type or "") == "asmr" else "manga"
    is_manga = expected_media_type == "manga"

    source = item.source
    item_dir = (
        external_item_download_dir(item, source)
        if source and source.download_root_path
        else None
    )
    manga_complete = bool(is_manga and item_dir and wnacg_download_is_complete(item_dir))

    media = (
        db.query(models.Media)
        .filter(
            models.Media.source_url == item.url,
            models.Media.source_site == item.source_type,
            models.Media.media_type == expected_media_type,
            models.Media.is_missing == False,
        )
        .first()
    )
    if media:
        if is_manga and not manga_complete:
            media.is_missing = True
            db.commit()
            return None
        return media

    if not source or not source.download_root_path or not item_dir:
        return None

    if not os.path.isdir(item_dir):
        return None

    media = (
        db.query(models.Media)
        .filter(
            models.Media.absolute_path == item_dir,
            models.Media.media_type == expected_media_type,
            models.Media.is_missing == False,
        )
        .first()
    )
    if media:
        if not media.source_url or not media.source_site:
            media.source_url = item.url
            media.source_site = item.source_type
            db.commit()
            db.refresh(media)
        return media

    if expected_media_type == "audio":
        return None

    if not manga_complete:
        return None

    return upsert_external_downloaded_media(item, source, item_dir, source.download_root_path, db)


def serialize_external_favorite_item(
    item: models.ExternalFavoriteItem,
    local_media_id: Optional[int] = None,
) -> dict:
    return {
        "id": item.id,
        "source_id": item.source_id,
        "source_type": item.source_type,
        "external_id": item.external_id,
        "title": item.title,
        "url": item.url,
        "cover_url": item.cover_url,
        "category_id": item.category_id,
        "category_name": item.category_name,
        "sync_position": item.sync_position,
        "last_seen_at": item.last_seen_at,
        "local_media_id": local_media_id,
    }


def serialize_external_favorite_items(
    items: List[models.ExternalFavoriteItem],
    db: Session,
) -> List[dict]:
    local_media = find_local_media_for_external_items(items, db)
    return [
        serialize_external_favorite_item(
            item,
            local_media_id=local_media[item.id].id if item.id in local_media else None,
        )
        for item in items
    ]


def upsert_external_downloaded_media(
    item: models.ExternalFavoriteItem,
    source: models.ExternalFavoriteSource,
    item_dir: str,
    download_root_path: str,
    db: Session,
) -> models.Media:
    folder = ensure_external_manga_library(source, download_root_path, db)
    page_count = scanner.count_manga_pages(item_dir, ".dir")
    rel_path = os.path.relpath(item_dir, folder.path)
    total_bytes = scanner.directory_size(item_dir)

    media = (
        db.query(models.Media)
        .filter(models.Media.absolute_path == item_dir, models.Media.media_type == "manga")
        .first()
    )
    if media:
        media.folder_id = folder.id
        media.title = item.title
        media.relative_path = rel_path
        media.file_size = total_bytes
        media.page_count = page_count
        media.source_url = item.url
        media.source_site = source.source_type
        media.is_missing = False
    else:
        media = models.Media(
            folder_id=folder.id,
            title=item.title,
            relative_path=rel_path,
            absolute_path=item_dir,
            media_type="manga",
            extension=".dir",
            file_size=total_bytes,
            page_count=page_count,
            source_url=item.url,
            source_site=source.source_type,
            is_missing=False,
        )
        db.add(media)
        db.flush()

    if not media.cover_path:
        thumb_hash = hashlib.md5(item_dir.encode("utf-8")).hexdigest()[:12]
        thumb_name = f"thumb_ext_{thumb_hash}_{datetime.now().timestamp()}.jpg"
        thumb_path = os.path.join(THUMBNAIL_DIR, thumb_name)
        cover_src = ensure_external_cover_cache(item, source)
        if cover_src and scanner.make_work_thumbnail(cover_src, thumb_path):
            media.cover_path = thumb_name
            media.cover_source = "external_cover"
        elif scanner.get_folder_thumbnail(item_dir, thumb_path):
            media.cover_path = thumb_name

    folder.last_scanned_at = datetime.now()
    db.commit()
    db.refresh(media)
    return media
