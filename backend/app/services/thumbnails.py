import logging
import os
import re

from .. import database, models

logger = logging.getLogger(__name__)

THUMBNAIL_DIR = os.path.join(os.getcwd(), ".thumbnails")
os.makedirs(THUMBNAIL_DIR, exist_ok=True)

_MANGA_PAGE_THUMB_RE = re.compile(r"^manga_page_(\d+)_\d+_v2\.jpg$")
_SPRITE_SHEET_STEM_RE = re.compile(r"^(.+)_\d+$")


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
                        continue
                    try:
                        os.remove(entry.path)
                    except OSError:
                        pass
    except Exception as e:
        logger.warning("Error cleaning up thumbnails: %s", e)
    finally:
        db.close()
