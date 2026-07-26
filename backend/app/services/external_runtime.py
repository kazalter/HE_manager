from datetime import datetime
import glob
import hashlib
import json
import mimetypes
import os
import re
import shutil
import time
import uuid
import zipfile
from typing import List, Optional
from urllib.parse import urljoin, urlparse

from sqlalchemy import or_
from sqlalchemy.orm import Session

from .. import asmr_source, database, downloader_push, external_sources, models, scanner
from . import job_lifecycle
from .audio_tracks import AUDIO_TRACK_EXTS, scan_audio_tracks
from .manga_pages import get_manga_image_files
from .media_access import get_source_or_404
from .thumbnails import THUMBNAIL_DIR

DEFAULT_EXTERNAL_DOWNLOAD_DIR = os.path.join(os.getcwd(), "external_downloads")
EXTERNAL_COVERS_DIR = os.path.abspath(os.path.join(os.getcwd(), "..", "covers"))
os.makedirs(EXTERNAL_COVERS_DIR, exist_ok=True)
DOWNLOAD_JOBS = {}
HE_PUBLIC_URL = os.getenv("HE_PUBLIC_URL", "").strip().rstrip("/")
HE_CALLBACK_TOKEN = os.getenv("HE_CALLBACK_TOKEN", "").strip()

def normalize_download_root(path: Optional[str], source_type: str = "wnacg") -> str:
    raw_path = (path or "").strip()
    if not raw_path:
        raw_path = os.path.join(DEFAULT_EXTERNAL_DOWNLOAD_DIR, source_type)
    return os.path.abspath(os.path.expanduser(raw_path))


def get_external_storage_dirs(source: models.ExternalFavoriteSource, download_root_path: Optional[str] = None):
    root = normalize_download_root(
        download_root_path if download_root_path is not None else source.download_root_path,
        source.source_type or "wnacg",
    )
    covers_dir = os.path.join(EXTERNAL_COVERS_DIR, source.source_type or "wnacg")
    manga_dir = os.path.join(root, "manga")
    os.makedirs(covers_dir, exist_ok=True)
    os.makedirs(manga_dir, exist_ok=True)
    return root, covers_dir, manga_dir


def get_cover_extension(content_type: str, url: str) -> str:
    guessed = mimetypes.guess_extension((content_type or "").split(";", 1)[0].strip())
    if guessed:
        return ".jpg" if guessed == ".jpe" else guessed
    parsed_ext = os.path.splitext(urlparse(url).path)[1].lower()
    return parsed_ext if parsed_ext in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"} else ".img"


def external_cover_sidecar_rel_path(item: models.ExternalFavoriteItem) -> Optional[str]:
    cover_url = (item.cover_url or "").strip()
    if not cover_url:
        return None
    if (item.source_type or "") == "asmr":
        ext = downloader_push.url_ext(cover_url, ".jpg")
        return f"cover{ext}"
    return None


def find_external_cover_sidecar(item_dir: str) -> Optional[str]:
    image_exts = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".avif"}
    candidates = glob.glob(os.path.join(item_dir, "cover.*"))
    candidates += glob.glob(os.path.join(item_dir, ".he_cover", "cover.*"))
    for path in sorted(candidates):
        if os.path.splitext(path)[1].lower() in image_exts and os.path.isfile(path):
            return path
    return None


def ensure_asmr_cover_file(item: models.ExternalFavoriteItem, item_dir: str) -> Optional[str]:
    """Ensure item_dir has a sidecar cover.* image, downloading from
    item.cover_url when missing. Idempotent (returns the existing path if one
    is already there) and best-effort (returns None on any failure — cover is
    nice-to-have, never a download blocker).

    Called from two places so a single transient fetch_file failure doesn't
    leave a work permanently coverless:
      1. download_asmr_item — first attempt right after audio finishes.
      2. upsert_external_downloaded_audio_media — second attempt before the
         Media row's thumbnail is generated, so a retried download (or a later
         job that revisits the same work) heals the gap automatically.
    """
    if not item_dir or not os.path.isdir(item_dir):
        return None
    existing = scanner.get_work_cover_path(item_dir)
    if existing:
        return existing
    cover_url = (item.cover_url or "").strip()
    if not cover_url:
        return None
    try:
        content, content_type = asmr_source.fetch_file(cover_url)
    except Exception as exc:  # noqa: BLE001 — cover is nice-to-have
        print(f"  ! Failed to download cover for {item.title!r}: {exc}")
        return None
    ext = get_cover_extension(content_type, cover_url)
    cover_local = os.path.join(item_dir, f"cover{ext}")
    try:
        with open(cover_local, "wb") as cover_file:
            cover_file.write(content)
    except OSError as exc:
        print(f"  ! Failed to write cover for {item.title!r}: {exc}")
        return None
    return cover_local


def get_cover_cache_prefix(item: models.ExternalFavoriteItem) -> str:
    stable_id = item.external_id or str(item.id)
    digest = hashlib.sha1((item.cover_url or item.url or stable_id).encode("utf-8")).hexdigest()[:10]
    return f"{item.id}_{stable_id}_{digest}"


def find_cached_cover(covers_dir: str, item: models.ExternalFavoriteItem) -> Optional[str]:
    matches = glob.glob(os.path.join(covers_dir, f"{get_cover_cache_prefix(item)}.*"))
    return matches[0] if matches else None


def ensure_external_cover_cache(item: models.ExternalFavoriteItem, source: models.ExternalFavoriteSource) -> Optional[str]:
    if not (item.cover_url or "").strip():
        return None
    _, covers_dir, _ = get_external_storage_dirs(source)
    cached_cover = find_cached_cover(covers_dir, item)
    if cached_cover and os.path.exists(cached_cover):
        return cached_cover
    try:
        if (source.source_type or "") == "asmr":
            content, content_type = asmr_source.fetch_file(item.cover_url)
        else:
            content, content_type = external_sources.fetch_binary(
                item.cover_url,
                source.cookie or "",
                referer=item.url or source.favorites_url,
                proxy=source.proxy,
            )
    except Exception as exc:  # noqa: BLE001
        print(f"  ! Failed to cache external cover for {item.title!r}: {exc}")
        return None
    extension = get_cover_extension(content_type, item.cover_url)
    cover_path = os.path.join(covers_dir, f"{get_cover_cache_prefix(item)}{extension}")
    try:
        with open(cover_path, "wb") as cover_file:
            cover_file.write(content)
    except OSError as exc:
        print(f"  ! Failed to write external cover cache for {item.title!r}: {exc}")
        return None
    return cover_path


def safe_filename(value: str, fallback: str = "item") -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value or "").strip()
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return (cleaned or fallback)[:120]


def get_asmr_storage_dirs(source: models.ExternalFavoriteSource, download_root_path: Optional[str] = None):
    """ASMR-side counterpart to get_external_storage_dirs(): returns
    (root, audio_dir). ASMR works are audio + subtitles, not page-based
    manga, so they live under `{root}/audio/{title}_{RJ}/...` instead of
    sharing the manga folder."""
    root = normalize_download_root(
        download_root_path if download_root_path is not None else source.download_root_path,
        source.source_type or "asmr",
    )
    audio_dir = os.path.join(root, "audio")
    os.makedirs(audio_dir, exist_ok=True)
    return root, audio_dir


def external_item_download_dir(item: models.ExternalFavoriteItem, source: models.ExternalFavoriteSource, download_root_path: Optional[str] = None) -> str:
    """Compute an item path without creating directories (safe for GET paths)."""
    source_type = source.source_type or "wnacg"
    root = normalize_download_root(
        download_root_path if download_root_path is not None else source.download_root_path,
        source_type,
    )
    if source_type == "asmr":
        audio_dir = os.path.join(root, "audio")
        # external_id for ASMR is the RJ code (e.g. "RJ123456"); keep the
        # title-first naming so the directory is human-skimmable in a file
        # explorer while the RJ suffix guarantees uniqueness.
        return os.path.join(audio_dir, f"{safe_filename(item.title, 'asmr')}_{item.external_id}")
    manga_dir = os.path.join(root, "manga")
    return os.path.join(manga_dir, f"{safe_filename(item.title, 'wnacg')}_{item.external_id}")


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
    """ASMR-side counterpart to ensure_external_manga_library(): the audio
    subdir gets a Folder row with scan_mode='audio_work' so the /media endpoint's
    media_type='audio' filter can later pick up these items.

    `scan_mode='audio_work'` is the folder-of-audio-files mode (one Media per
    work folder), shared with the manual "audio work" library users can add
    in SettingsView. The scanner's audio_work branch is idempotent: it will
    skip re-creating Media rows that this function already upserted at
    download time."""
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
    """Register a freshly-downloaded ASMR work as a Media row so the UI can
    surface it under /media?media_type=audio and the 'already downloaded'
    badge in AsmrPanel can light up via find_local_media_for_external_item.

    The row is intentionally minimal: extension='.dir' (the work is a folder,
    not a single file) and page_count holds the track count so list views
    have something meaningful to show. cover_path is populated from the
    sidecar cover file dropped by download_asmr_item — using the same
    scanner helpers as audio_work scan mode so both code paths produce
    identical thumbnails."""
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

    # Pull a thumbnail from the cover file download_asmr_item dropped in the
    # work folder. Only generate when there's no cover yet (avoid orphan
    # thumb files piling up across re-runs of the same RJ). If the download
    # path's cover fetch silently failed (CDN/mirror blip), retry it here so
    # the second attempt heals the gap — same helper, same idempotency.
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
    # source.txt is written by download_wnacg_item only AFTER the page loop
    # finishes (see below), so its presence is a reliable "this download
    # actually completed" sentinel. A failed/partial download (exception mid
    # loop) never reaches that write, so its folder lacks source.txt — which is
    # exactly how we tell a half-downloaded book apart from a finished one
    # without needing to know the expected page count out-of-band.
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
    # WNACG works are manga; ASMR works are audio. The expected media_type is
    # the only branch difference — everything else (source_url/source_site
    # match, then absolute_path fallback) is identical.
    expected_media_type = "audio" if (item.source_type or "") == "asmr" else "manga"
    is_manga = expected_media_type == "manga"

    source = item.source
    item_dir = (
        external_item_download_dir(item, source)
        if source and source.download_root_path
        else None
    )
    # For manga, "downloaded" means the folder exists AND finished (has the
    # source.txt sentinel). A partial folder — or one whose folder the user
    # deleted by hand — must NOT count as downloaded, otherwise the favourite
    # gets a permanent "已下载" badge that greys it out and blocks re-download.
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
            # Stale row: a previous failed download (or the find-local fallback
            # below) registered a half-finished/now-deleted folder as a Media
            # row. Self-heal by flagging it missing so it drops out of both the
            # library and this favourite's "已下载" badge, then report
            # not-downloaded so the user can re-download (which resumes via the
            # per-page skip in download_wnacg_item).
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

    # Auto-link an existing downloaded folder back to a Media row. ASMR can't
    # safely auto-upsert here because it needs the live track count / byte
    # total that only the download path knows, so we just bail — the row gets
    # created when the user actually downloads via run_asmr_download_job.
    if expected_media_type == "audio":
        return None

    # Only auto-promote a folder that actually finished downloading; a partial
    # folder left behind by a failed job must stay re-downloadable.
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


def get_image_extension(content_type: str, url: str) -> str:
    return get_cover_extension(content_type, url)


class DownloadCancelled(Exception):
    def __init__(self, item_dir: Optional[str] = None):
        super().__init__("Download cancelled")
        self.item_dir = item_dir


def is_cancel_requested(job: dict) -> bool:
    return bool(job.get("cancel_requested"))


def find_task(job: dict, item_id: int) -> Optional[dict]:
    for task in job.get("tasks", []):
        if task.get("item_id") == item_id:
            return task
    return None


def cleanup_incomplete_download(item_dir: str, expected_pages: int):
    if not item_dir or not os.path.isdir(item_dir):
        return

    existing_pages = scanner.count_manga_pages(item_dir, ".dir") or 0
    if existing_pages >= expected_pages:
        return

    shutil.rmtree(item_dir, ignore_errors=True)


WNACG_ARCHIVE_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"}


def _natural_path_key(path: str):
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", path)]


def _write_wnacg_source_marker(item: models.ExternalFavoriteItem, item_dir: str) -> None:
    info_path = os.path.join(item_dir, "source.txt")
    with open(info_path, "w", encoding="utf-8") as info_file:
        info_file.write(f"{item.title}\n{item.url}\n")


def _advance_wnacg_job_progress(job: Optional[dict], task: Optional[dict], pages: int = 0, bytes_count: int = 0) -> None:
    if job is None:
        return
    if pages:
        job["pages_done"] += pages
        job["current_book_downloaded_pages"] += pages
        if task is not None:
            task["downloaded_pages"] += pages
    if bytes_count:
        job["downloaded_bytes"] += bytes_count


def _extract_wnacg_zip_archive(archive_path: str, item_dir: str) -> dict:
    if not zipfile.is_zipfile(archive_path):
        raise RuntimeError("压缩包不是有效 ZIP 文件")

    temp_dir = os.path.join(item_dir, f".archive_extract_{uuid.uuid4().hex}")
    os.makedirs(temp_dir, exist_ok=True)
    try:
        with zipfile.ZipFile(archive_path, "r") as archive:
            image_members = [
                info
                for info in archive.infolist()
                if not info.is_dir()
                and os.path.splitext(info.filename)[1].lower() in WNACG_ARCHIVE_IMAGE_EXTENSIONS
                and "__macosx/" not in info.filename.lower()
            ]
            image_members.sort(key=lambda info: _natural_path_key(info.filename))
            if not image_members:
                raise RuntimeError("压缩包里没有可用图片")

            staged_paths = []
            for index, info in enumerate(image_members, start=1):
                ext = os.path.splitext(info.filename)[1].lower()
                staged_path = os.path.join(temp_dir, f"{index:03d}{ext}")
                with archive.open(info, "r") as src, open(staged_path, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                staged_paths.append(staged_path)

        downloaded = 0
        skipped = 0
        for staged_path in staged_paths:
            stem = os.path.splitext(os.path.basename(staged_path))[0]
            existing = glob.glob(os.path.join(item_dir, f"{stem}.*"))
            if existing:
                skipped += 1
                continue
            shutil.move(staged_path, os.path.join(item_dir, os.path.basename(staged_path)))
            downloaded += 1

        return {
            "pages": len(staged_paths),
            "downloaded": downloaded,
            "skipped": skipped,
        }
    except zipfile.BadZipFile as exc:
        raise RuntimeError("压缩包损坏或无法读取") from exc
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def _resolve_wnacg_archive_urls(item: models.ExternalFavoriteItem, source: models.ExternalFavoriteSource, plan: dict) -> List[str]:
    urls: List[str] = []
    worker_request = plan.get("archive_worker_request")
    if worker_request is not None:
        try:
            signed_url = external_sources.resolve_wnacg_worker_archive_url(
                worker_request,
                cookie=source.cookie or "",
                referer=plan.get("download_page_url") or item.url,
                proxy=source.proxy,
            )
            if signed_url:
                urls.append(signed_url)
        except Exception as exc:  # noqa: BLE001 - fallback to static archive links / per-page download
            print(f"  ! Failed to resolve wnacg archive worker URL for {item.title!r}: {exc}")

    for url in plan.get("archive_urls") or []:
        if url and url not in urls:
            urls.append(url)
    return urls


def _try_download_wnacg_archive(
    item: models.ExternalFavoriteItem,
    source: models.ExternalFavoriteSource,
    plan: dict,
    job: Optional[dict] = None,
) -> Optional[dict]:
    archive_urls = _resolve_wnacg_archive_urls(item, source, plan)
    if not archive_urls:
        return None

    item_dir = plan["item_dir"]
    os.makedirs(item_dir, exist_ok=True)
    task = find_task(job, item.id) if job is not None else None
    expected_pages = len(plan.get("image_urls") or [])
    last_error: Optional[Exception] = None

    for archive_url in archive_urls:
        if job is not None and is_cancel_requested(job):
            raise DownloadCancelled(item_dir)

        archive_path = os.path.join(item_dir, f".wnacg_archive_{uuid.uuid4().hex}.zip")
        bytes_before_attempt = int(job.get("downloaded_bytes", 0)) if job is not None else 0
        try:
            def on_chunk(size: int) -> None:
                if job is not None and is_cancel_requested(job):
                    raise DownloadCancelled(item_dir)
                _advance_wnacg_job_progress(job, task, bytes_count=size)

            external_sources.fetch_file_to_path(
                archive_url,
                source.cookie or "",
                archive_path,
                referer=plan.get("download_page_url") or item.url,
                proxy=source.proxy,
                on_chunk=on_chunk,
            )
            extracted = _extract_wnacg_zip_archive(archive_path, item_dir)
            actual_pages = extracted["pages"]
            if job is not None:
                delta = actual_pages - expected_pages
                if delta:
                    job["pages_total"] += delta
                    job["current_book_total_pages"] = actual_pages
                    if task is not None:
                        task["total_pages"] = actual_pages
                _advance_wnacg_job_progress(job, task, pages=actual_pages)
            _write_wnacg_source_marker(item, item_dir)
            return {
                "item_id": item.id,
                "title": item.title,
                "status": "completed",
                "path": item_dir,
                "pages": actual_pages,
                "downloaded": extracted["downloaded"],
                "skipped": extracted["skipped"],
                "method": "archive",
            }
        except DownloadCancelled:
            raise
        except Exception as exc:  # noqa: BLE001 - try the next archive URL, then image fallback
            if job is not None:
                job["downloaded_bytes"] = bytes_before_attempt
            last_error = exc
            print(f"  ! WNACG archive download failed for {item.title!r}: {exc}")
        finally:
            if os.path.exists(archive_path):
                try:
                    os.remove(archive_path)
                except OSError:
                    pass

    if last_error is not None:
        print(f"  ! Falling back to per-page WNACG download for {item.title!r}")
    return None


def log_wnacg_download_failure(download_root_path: str, title: str, url: str, error: str):
    """Append one line to a durable failure log next to the downloaded books.

    DOWNLOAD_JOBS is in-memory only, so the per-job failure list evaporates on
    a page reload or a backend restart — which is exactly why the user "couldn't
    see which books failed". This file survives both, giving a permanent record
    of what failed and why."""
    try:
        root = normalize_download_root(download_root_path, "wnacg")
        manga_dir = os.path.join(root, "manga")
        os.makedirs(manga_dir, exist_ok=True)
        log_path = os.path.join(manga_dir, "_download_errors.log")
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(log_path, "a", encoding="utf-8") as log_file:
            log_file.write(f"[{timestamp}] {title} | {url} | {error}\n")
    except Exception:
        # Logging must never take down a download job.
        pass


def prepare_wnacg_download_plan(item: models.ExternalFavoriteItem, source: models.ExternalFavoriteSource, download_root_path: str):
    item_dir = external_item_download_dir(item, source, download_root_path)

    item_api_url = urljoin(item.url, f"/photos-item-aid-{item.external_id}.html")
    item_html = external_sources.fetch_html(item_api_url, source.cookie or "", proxy=source.proxy)
    image_urls = external_sources.parse_wnacg_image_urls(item_html)
    if not image_urls:
        raise RuntimeError("没有解析到图片地址")

    download_page_url = external_sources.wnacg_download_url(item.external_id)
    archive_urls: List[str] = []
    archive_worker_request = None
    try:
        download_html = external_sources.fetch_html(download_page_url, source.cookie or "", proxy=source.proxy)
        archive_worker_request = external_sources.parse_wnacg_worker_archive_request(download_html)
        archive_urls = external_sources.parse_wnacg_archive_urls(download_html, base_url=download_page_url)
    except Exception as exc:  # noqa: BLE001 - the image downloader below remains the fallback
        print(f"  ! Failed to inspect wnacg archive page for {item.title!r}: {exc}")

    return {
        "item_dir": item_dir,
        "image_urls": image_urls,
        "download_page_url": download_page_url,
        "archive_urls": archive_urls,
        "archive_worker_request": archive_worker_request,
    }


def download_wnacg_item(item: models.ExternalFavoriteItem, source: models.ExternalFavoriteSource, plan: dict, job: Optional[dict] = None):
    item_dir = plan["item_dir"]
    image_urls = plan["image_urls"]
    os.makedirs(item_dir, exist_ok=True)
    downloaded = 0
    skipped = 0
    task = find_task(job, item.id) if job is not None else None

    archive_result = _try_download_wnacg_archive(item, source, plan, job)
    if archive_result is not None:
        return archive_result

    for index, image_url in enumerate(image_urls, start=1):
        if job is not None and is_cancel_requested(job):
            raise DownloadCancelled(item_dir)

        existing = glob.glob(os.path.join(item_dir, f"{index:03d}.*"))
        if existing:
            skipped += 1
            _advance_wnacg_job_progress(job, task, pages=1)
            continue
        content, content_type = external_sources.fetch_binary(image_url, source.cookie or "", referer=item.url, proxy=source.proxy)
        extension = get_image_extension(content_type, image_url)
        image_path = os.path.join(item_dir, f"{index:03d}{extension}")
        with open(image_path, "wb") as image_file:
            image_file.write(content)
        downloaded += 1
        _advance_wnacg_job_progress(job, task, pages=1, bytes_count=len(content))
        time.sleep(0.15)

    _write_wnacg_source_marker(item, item_dir)

    return {
        "item_id": item.id,
        "title": item.title,
        "status": "completed",
        "path": item_dir,
        "pages": len(image_urls),
        "downloaded": downloaded,
        "skipped": skipped,
        "method": "images",
    }


def run_wnacg_download_job(job_id: str, item_ids: List[int], download_root_path: str):
    db = database.SessionLocal()
    job = DOWNLOAD_JOBS[job_id]
    try:
        planned_downloads = []
        job["status"] = "preparing"
        job["message"] = "正在准备下载"

        for item_id in item_ids:
            if is_cancel_requested(job):
                raise DownloadCancelled()

            task = find_task(job, item_id)
            item = db.query(models.ExternalFavoriteItem).filter(models.ExternalFavoriteItem.id == item_id).first()
            if not item:
                job["failed"] += 1
                if task is not None:
                    task["status"] = "failed"
                    task["error"] = "条目不存在"
                job["results"].append({"item_id": item_id, "status": "failed", "error": "条目不存在"})
                continue
            if task is not None:
                task["title"] = item.title
            source = get_source_or_404(item.source_id, db)
            if source.source_type != "wnacg":
                job["failed"] += 1
                if task is not None:
                    task["status"] = "failed"
                    task["error"] = "暂不支持这个站点"
                job["results"].append({"item_id": item_id, "title": item.title, "status": "failed", "error": "暂不支持这个站点"})
                continue
            if source.download_root_path != download_root_path:
                source.download_root_path = download_root_path
                db.commit()
            local_media = find_local_media_for_external_item(item, db)
            if local_media:
                job["completed"] += 1
                if task is not None:
                    task["status"] = "success"
                job["results"].append({
                    "item_id": item.id,
                    "title": item.title,
                    "status": "completed",
                    "local_media_id": local_media.id,
                    "skipped": True,
                })
                continue
            ensure_external_manga_library(source, download_root_path, db)
            try:
                job["message"] = f"正在准备：{item.title}"
                plan = prepare_wnacg_download_plan(item, source, download_root_path)
                job["pages_total"] += len(plan["image_urls"])
                if task is not None:
                    task["total_pages"] = len(plan["image_urls"])
                planned_downloads.append((item, source, plan))
            except Exception as exc:
                job["failed"] += 1
                if task is not None:
                    task["status"] = "failed"
                    task["error"] = str(exc)
                job["results"].append({"item_id": item.id, "title": item.title, "status": "failed", "error": str(exc)})
                log_wnacg_download_failure(download_root_path, item.title, item.url, str(exc))

        job["bytes_total_known"] = False
        job["status"] = "running"
        for item, source, plan in planned_downloads:
            if is_cancel_requested(job):
                raise DownloadCancelled()

            task = find_task(job, item.id)
            try:
                job["message"] = f"正在下载：{item.title}"
                job["current_book_title"] = item.title
                job["current_book_total_pages"] = len(plan["image_urls"])
                job["current_book_downloaded_pages"] = 0
                if task is not None:
                    task["status"] = "downloading"
                result = download_wnacg_item(item, source, plan, job)
                local_media = upsert_external_downloaded_media(item, source, result["path"], download_root_path, db)
                result["local_media_id"] = local_media.id
                job["completed"] += 1
                if task is not None:
                    task["status"] = "success"
                job["results"].append(result)
            except DownloadCancelled as exc:
                cleanup_incomplete_download(exc.item_dir or plan["item_dir"], len(plan["image_urls"]))
                if task is not None:
                    task["status"] = "failed"
                    task["error"] = "已取消"
                job["results"].append({"item_id": item.id, "title": item.title, "status": "canceled", "path": plan["item_dir"]})
                raise
            except Exception as exc:
                job["failed"] += 1
                if task is not None:
                    task["status"] = "failed"
                    task["error"] = str(exc)
                job["results"].append({"item_id": item.id, "title": item.title, "status": "failed", "error": str(exc)})
                log_wnacg_download_failure(download_root_path, item.title, item.url, str(exc))

        job["current_book_title"] = ""
        job["current_book_total_pages"] = 0
        job["current_book_downloaded_pages"] = 0

        job["status"] = "completed"
        job["message"] = "下载完成"
    except DownloadCancelled:
        job["status"] = "canceled"
        job["message"] = "下载已取消，未完成的漫画已删除"
    except Exception as exc:
        job["status"] = "failed"
        job["message"] = str(exc)
    finally:
        job_lifecycle.record_job("external_download", job, finished=True)
        db.close()


# ============================================================================
# ASMR download pipeline
# ============================================================================
# Mirrors the WNACG download flow above, but the unit of work is one ASMR work
# (= a folder of audio + optional subtitle files) instead of one manga (= a
# folder of page images). Key differences:
#   - tracks come from /api/tracks/{rj} as a nested folder tree
#   - format / SE-version filters are stored on the source row from sync time
#   - single files can be hundreds of MB / GB -> stream to disk, never load
#     the whole body into RAM
#   - download root layout: {root}/audio/{title}_{RJ}/{...nested folders}


def prepare_asmr_download_plan_for_item(item: models.ExternalFavoriteItem, source: models.ExternalFavoriteSource, download_root_path: str):
    """ASMR counterpart to prepare_wnacg_download_plan(): fetch the /api/tracks
    tree, apply the source's format + SE-version filters, and resolve each
    track + subtitle to a local destination under the work's folder."""
    item_dir = external_item_download_dir(item, source, download_root_path)

    token = source.cookie or ""
    if not token:
        raise RuntimeError("ASMR 来源未登录，请先同步一次以获取令牌")

    working_base = source.favorites_url or asmr_source.DEFAULT_API_BASE
    mirrors = asmr_source.parse_mirrors(source.api_mirrors) if source.api_mirrors else None
    tree = asmr_source.fetch_work_tracks(working_base, token, item.external_id, mirrors=mirrors)

    planned_files = asmr_source.prepare_asmr_download_plan(
        tree,
        audio_format=source.audio_format_filter or "all",
        audio_version=source.audio_version_filter or "all",
        include_subtitles=True,
    )
    if not planned_files:
        raise RuntimeError("没有可下载的音频文件（作品 tracks 为空）")

    files = []
    for planned in planned_files:
        local_path = os.path.join(item_dir, *planned.rel_segments)
        files.append({
            "url": planned.download_url,
            "local_path": local_path,
            "kind": planned.kind,
            "size": planned.size,
        })

    return {
        "item_dir": item_dir,
        "files": files,
    }


def download_asmr_item(item: models.ExternalFavoriteItem, source: models.ExternalFavoriteSource, plan: dict, job: Optional[dict] = None):
    """Stream every file in `plan["files"]` to disk under `plan["item_dir"]`,
    updating job counters as bytes come in. Cancellation is checked between
    files AND inside the per-chunk read loop so the user doesn't have to wait
    for a multi-GB WAV to finish before the cancel kicks in."""
    item_dir = plan["item_dir"]
    files = plan["files"]
    os.makedirs(item_dir, exist_ok=True)

    downloaded = 0
    skipped = 0
    total_bytes = 0
    audio_track_count = 0
    task = find_task(job, item.id) if job is not None else None

    for index, file_info in enumerate(files, start=1):
        if job is not None and is_cancel_requested(job):
            raise DownloadCancelled(item_dir)

        local_path = file_info["local_path"]
        if file_info["kind"] == "audio":
            audio_track_count += 1

        # Skip if the file already exists with a non-zero size (resume on rerun).
        if os.path.exists(local_path) and os.path.getsize(local_path) > 0:
            skipped += 1
            existing_size = os.path.getsize(local_path)
            total_bytes += existing_size
            if job is not None:
                job["pages_done"] += 1
                job["current_book_downloaded_pages"] += 1
                job["downloaded_bytes"] += existing_size
                if task is not None:
                    task["downloaded_pages"] += 1
            continue

        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        tmp_path = local_path + ".part"
        bytes_written = 0
        try:
            with asmr_source.open_file_stream(file_info["url"]) as response:
                with open(tmp_path, "wb") as out_file:
                    while True:
                        if job is not None and is_cancel_requested(job):
                            raise DownloadCancelled(item_dir)
                        chunk = response.read(64 * 1024)
                        if not chunk:
                            break
                        out_file.write(chunk)
                        bytes_written += len(chunk)
                        if job is not None:
                            job["downloaded_bytes"] += len(chunk)
            os.replace(tmp_path, local_path)
        except BaseException:
            # Leave any partial .part for inspection-free cleanup by
            # cleanup_incomplete_asmr_download; just don't let the tmp pollute.
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except OSError:
                pass
            raise

        downloaded += 1
        total_bytes += bytes_written
        if job is not None:
            job["pages_done"] += 1
            job["current_book_downloaded_pages"] += 1
            if task is not None:
                task["downloaded_pages"] += 1
        time.sleep(0.05)

    # Download the cover image alongside the audio so the local work folder
    # is self-contained (and audio_work scanner / upsert can pick it up as
    # the Media row's thumbnail). Failure is silently tolerated here — the
    # upsert path retries via the same helper, so a transient blip doesn't
    # leave the work permanently coverless.
    ensure_asmr_cover_file(item, item_dir)

    # Drop a small breadcrumb file so the local folder is self-describing if
    # the DB ever gets wiped. Matches WNACG's source.txt convention.
    info_path = os.path.join(item_dir, "source.txt")
    with open(info_path, "w", encoding="utf-8") as info_file:
        info_file.write(f"{item.title}\n{item.url}\n{item.external_id}\n")

    return {
        "item_id": item.id,
        "title": item.title,
        "status": "completed",
        "path": item_dir,
        "files": len(files),
        "downloaded": downloaded,
        "skipped": skipped,
        "total_bytes": total_bytes,
        "audio_track_count": audio_track_count,
    }


def cleanup_incomplete_asmr_download(item_dir: str, expected_files: int):
    """Drop a partly-downloaded work so the next run starts fresh (or, if the
    user has the same RJ in their selection again, doesn't pick up half-files).
    Counts files recursively because the work is a nested folder tree."""
    if not item_dir or not os.path.isdir(item_dir):
        return

    actual = 0
    for _, _, files in os.walk(item_dir):
        actual += len([f for f in files if not f.endswith(".part") and f != "source.txt"])
    if actual >= expected_files and expected_files > 0:
        return

    shutil.rmtree(item_dir, ignore_errors=True)


def run_asmr_download_job(job_id: str, item_ids: List[int], download_root_path: str):
    db = database.SessionLocal()
    job = DOWNLOAD_JOBS[job_id]
    try:
        planned_downloads = []
        job["status"] = "preparing"
        job["message"] = "正在准备下载"

        for item_id in item_ids:
            if is_cancel_requested(job):
                raise DownloadCancelled()

            task = find_task(job, item_id)
            item = db.query(models.ExternalFavoriteItem).filter(models.ExternalFavoriteItem.id == item_id).first()
            if not item:
                job["failed"] += 1
                if task is not None:
                    task["status"] = "failed"
                    task["error"] = "条目不存在"
                job["results"].append({"item_id": item_id, "status": "failed", "error": "条目不存在"})
                continue
            if task is not None:
                task["title"] = item.title
            source = get_source_or_404(item.source_id, db)
            if (source.source_type or "") != "asmr":
                job["failed"] += 1
                if task is not None:
                    task["status"] = "failed"
                    task["error"] = "不是 ASMR 条目"
                job["results"].append({"item_id": item_id, "title": item.title, "status": "failed", "error": "不是 ASMR 条目"})
                continue
            if source.download_root_path != download_root_path:
                source.download_root_path = download_root_path
                db.commit()
            local_media = find_local_media_for_external_item(item, db)
            if local_media:
                job["completed"] += 1
                if task is not None:
                    task["status"] = "success"
                job["results"].append({
                    "item_id": item.id,
                    "title": item.title,
                    "status": "completed",
                    "local_media_id": local_media.id,
                    "skipped": True,
                })
                continue
            ensure_external_audio_library(source, download_root_path, db)
            try:
                job["message"] = f"正在准备：{item.title}"
                plan = prepare_asmr_download_plan_for_item(item, source, download_root_path)
                job["pages_total"] += len(plan["files"])
                if task is not None:
                    task["total_pages"] = len(plan["files"])
                planned_downloads.append((item, source, plan))
            except Exception as exc:
                job["failed"] += 1
                if task is not None:
                    task["status"] = "failed"
                    task["error"] = str(exc)
                job["results"].append({"item_id": item.id, "title": item.title, "status": "failed", "error": str(exc)})

        job["bytes_total_known"] = False
        job["status"] = "running"
        for item, source, plan in planned_downloads:
            if is_cancel_requested(job):
                raise DownloadCancelled()

            task = find_task(job, item.id)
            try:
                job["message"] = f"正在下载：{item.title}"
                job["current_book_title"] = item.title
                job["current_book_total_pages"] = len(plan["files"])
                job["current_book_downloaded_pages"] = 0
                if task is not None:
                    task["status"] = "downloading"
                result = download_asmr_item(item, source, plan, job)
                local_media = upsert_external_downloaded_audio_media(
                    item,
                    source,
                    result["path"],
                    download_root_path,
                    db,
                    track_count=result["audio_track_count"],
                    total_bytes=result["total_bytes"],
                )
                result["local_media_id"] = local_media.id
                job["completed"] += 1
                if task is not None:
                    task["status"] = "success"
                job["results"].append(result)
            except DownloadCancelled as exc:
                cleanup_incomplete_asmr_download(exc.item_dir or plan["item_dir"], len(plan["files"]))
                if task is not None:
                    task["status"] = "failed"
                    task["error"] = "已取消"
                job["results"].append({"item_id": item.id, "title": item.title, "status": "canceled", "path": plan["item_dir"]})
                raise
            except Exception as exc:
                job["failed"] += 1
                if task is not None:
                    task["status"] = "failed"
                    task["error"] = str(exc)
                job["results"].append({"item_id": item.id, "title": item.title, "status": "failed", "error": str(exc)})

        job["current_book_title"] = ""
        job["current_book_total_pages"] = 0
        job["current_book_downloaded_pages"] = 0

        job["status"] = "completed"
        job["message"] = "下载完成"
    except DownloadCancelled:
        job["status"] = "canceled"
        job["message"] = "下载已取消，未完成的作品已清理"
    except Exception as exc:
        job["status"] = "failed"
        job["message"] = str(exc)
    finally:
        job_lifecycle.record_job("external_download", job, finished=True)
        db.close()


def get_url_base(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return external_sources.WNACG_BASE_URL
    return f"{parsed.scheme}://{parsed.netloc}/"
