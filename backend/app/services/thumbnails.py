import logging
import mimetypes
import os
import re
import urllib.parse

from fastapi import Request, Response
from fastapi.responses import FileResponse

from .. import database, models

logger = logging.getLogger(__name__)

THUMBNAIL_DIR = os.path.join(os.getcwd(), ".thumbnails")
os.makedirs(THUMBNAIL_DIR, exist_ok=True)

_MANGA_PAGE_THUMB_RE = re.compile(r"^manga_page_(\d+)_\d+_v2\.jpg$")
_SPRITE_SHEET_STEM_RE = re.compile(r"^(.+)_\d+$")


def thumbnail_accel_prefix() -> str:
    """Return configured Nginx internal redirect prefix, or empty when disabled."""
    return os.getenv("HE_THUMBNAIL_ACCEL_PREFIX", "").strip().rstrip("/")


def should_accel_thumbnail(headers) -> bool:
    """True when Nginx internal redirect is enabled and the request came through it."""
    if not thumbnail_accel_prefix():
        return False
    if hasattr(headers, "get"):
        return headers.get("x-he-accel-thumbnails") == "1"
    for key, value in headers:
        if key.lower() == b"x-he-accel-thumbnails":
            return value == b"1"
    return False


def _ensure_world_readable(path: str) -> bool:
    """Ensure thumbnail files are readable by the non-root Nginx worker on POSIX."""
    if os.name == "nt":
        return True
    try:
        mode = os.stat(path).st_mode & 0o777
        if mode & 0o004:
            return True
        os.chmod(path, mode | 0o644)
        return bool(os.stat(path).st_mode & 0o004)
    except OSError:
        return False


def accel_thumbnail_response(
    thumb_path: str,
    *,
    base_dir: str | None = None,
    media_type: str | None = None,
    cache_control: str = "private, max-age=86400",
) -> Response | None:
    """Build an X-Accel-Redirect response when thumb_path is a file inside base_dir."""
    prefix = thumbnail_accel_prefix()
    if not prefix:
        return None
    root_dir = os.path.realpath(base_dir or THUMBNAIL_DIR)
    real_file = os.path.realpath(thumb_path)
    try:
        if os.path.commonpath([root_dir, real_file]) != root_dir or not os.path.isfile(real_file):
            return None
    except ValueError:
        return None
    if not _ensure_world_readable(real_file):
        return None
    rel_path = os.path.relpath(real_file, root_dir).replace(os.sep, "/")
    encoded_rel = urllib.parse.quote(rel_path, safe="/")
    guessed = media_type or mimetypes.guess_type(real_file)[0]
    if not guessed and real_file.lower().endswith(".vtt"):
        guessed = "text/vtt; charset=utf-8"
    return Response(
        status_code=200,
        media_type=guessed or "application/octet-stream",
        headers={
            "X-Accel-Redirect": f"{prefix}/{encoded_rel}",
            "Cache-Control": cache_control,
        },
    )


def serve_thumbnail_file(
    thumb_path: str,
    *,
    request: Request | None = None,
    base_dir: str | None = None,
    media_type: str | None = None,
    cache_control: str = "private, max-age=86400",
) -> Response:
    """Serve a thumbnail via Nginx X-Accel-Redirect when proxied, else FileResponse."""
    if request is not None and should_accel_thumbnail(request.headers):
        accel = accel_thumbnail_response(
            thumb_path,
            base_dir=base_dir,
            media_type=media_type,
            cache_control=cache_control,
        )
        if accel is not None:
            return accel
    return FileResponse(
        thumb_path,
        media_type=media_type,
        headers={"Cache-Control": cache_control},
    )


def remove_cover_thumbnails(cover_path: str | None) -> None:
    if not cover_path or not os.path.isdir(THUMBNAIL_DIR):
        return
    thumb_base = cover_path.rsplit(".", 1)[0]
    sprite_prefix = f"{thumb_base}_"
    vtt_name = f"{thumb_base}.vtt"
    try:
        with os.scandir(THUMBNAIL_DIR) as entries:
            for entry in entries:
                if not entry.is_file(follow_symlinks=False):
                    continue
                name = entry.name
                if name != cover_path and name != vtt_name and not name.startswith(sprite_prefix):
                    continue
                try:
                    os.remove(entry.path)
                except OSError:
                    pass
    except FileNotFoundError:
        pass


def remove_manga_page_thumbnails(media_id: int) -> None:
    if not os.path.isdir(THUMBNAIL_DIR):
        return
    prefix = f"manga_page_{media_id}_"
    try:
        with os.scandir(THUMBNAIL_DIR) as entries:
            for entry in entries:
                if not entry.is_file(follow_symlinks=False):
                    continue
                if entry.name.startswith(prefix):
                    try:
                        os.remove(entry.path)
                    except OSError:
                        pass
    except OSError:
        pass


def _is_valid_thumbnail(filename: str, valid_bases: set[str], valid_manga_ids: set[int]) -> bool:
    manga_match = _MANGA_PAGE_THUMB_RE.match(filename)
    if manga_match:
        return int(manga_match.group(1)) in valid_manga_ids

    stem = filename.rsplit(".", 1)[0]
    if stem in valid_bases:
        return True

    sprite_match = _SPRITE_SHEET_STEM_RE.match(stem)
    if sprite_match and sprite_match.group(1) in valid_bases:
        return True

    return False


def cleanup_orphaned_thumbnails():
    db = database.SessionLocal()
    try:
        valid_bases = {
            row[0].rsplit(".", 1)[0]
            for row in db.query(models.Media.cover_path).filter(models.Media.cover_path != None).all()
            if row[0]
        }
        valid_manga_ids = {
            row[0]
            for row in db.query(models.Media.id).filter(models.Media.media_type == "manga").all()
        }

        if os.path.isdir(THUMBNAIL_DIR):
            with os.scandir(THUMBNAIL_DIR) as entries:
                for entry in entries:
                    if not entry.is_file(follow_symlinks=False):
                        continue
                    if _is_valid_thumbnail(entry.name, valid_bases, valid_manga_ids):
                        _ensure_world_readable(entry.path)
                        continue
                    try:
                        os.remove(entry.path)
                    except OSError:
                        pass
    except Exception as e:
        logger.warning("Error cleaning up thumbnails: %s", e)
    finally:
        db.close()
