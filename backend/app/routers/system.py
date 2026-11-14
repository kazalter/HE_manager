import logging
import os
from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from .. import models, scanner
from ..database import SQLALCHEMY_DATABASE_URL, get_db
from ..services import backup, storage_guard

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/system", tags=["system"])


def _get_live_db_path() -> str:
    url_str = os.getenv("HE_DATABASE_URL", SQLALCHEMY_DATABASE_URL)
    try:
        url = make_url(url_str)
        if url.drivername == "sqlite" and url.database and url.database != ":memory:":
            return os.path.abspath(url.database)
    except Exception:
        pass
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "library.db"))


@router.get("/backup/status")
def get_backup_status(max_age_hours: float = 24.0) -> Dict[str, Any]:
    """Returns database backup status and freshness diagnostics."""
    db_path = _get_live_db_path()
    backup_dir = backup.get_default_backup_dir(db_path)
    freshness = backup.check_backup_freshness(backup_dir, max_age_hours=max_age_hours)
    backups = backup.list_backups(backup_dir)
    return {
        "db_path": db_path,
        "backup_dir": backup_dir,
        "freshness": freshness,
        "backups": backups,
    }


@router.post("/backup/run")
def trigger_backup(keep_count: int = 7) -> Dict[str, Any]:
    """Executes an online SQLite hot backup."""
    db_path = _get_live_db_path()
    try:
        result = backup.backup_database(db_path, keep_count=keep_count)
        return result
    except Exception as exc:
        logger.exception("Failed to execute system backup: %s", exc)
        raise HTTPException(status_code=500, detail=f"Backup failed: {exc}")


@router.get("/storage/status")
def get_storage_status() -> Dict[str, Any]:
    """Returns storage guard and sentinel configuration diagnostics."""
    sentinel = storage_guard.get_configured_sentinel_name()
    return {
        "configured_sentinel": sentinel,
        "require_mount": os.getenv("HE_REQUIRE_STORAGE_MOUNT", "0"),
        "platform": os.name,
    }


def backfill_missing_video_metadata(db: Session, limit: int = 500) -> Dict[str, int]:
    """Backfills missing width/height/duration for non-missing video entries."""
    safe_limit = max(1, min(int(limit), 5000))
    rows = (
        db.query(models.Media)
        .filter(
            models.Media.media_type == "video",
            models.Media.is_missing == False,  # noqa: E712
            or_(
                models.Media.width.is_(None),
                models.Media.width <= 0,
                models.Media.height.is_(None),
                models.Media.height <= 0,
                models.Media.duration.is_(None),
                models.Media.duration <= 0,
            ),
        )
        .order_by(models.Media.id.asc())
        .limit(safe_limit)
        .all()
    )
    checked = 0
    updated = 0
    skipped_missing = 0
    for item in rows:
        checked += 1
        if not item.absolute_path or not os.path.exists(item.absolute_path):
            skipped_missing += 1
            continue
        meta = scanner.get_video_metadata(item.absolute_path)
        changed = False
        if (not item.width or item.width <= 0) and meta.get("width"):
            item.width = meta["width"]
            changed = True
        if (not item.height or item.height <= 0) and meta.get("height"):
            item.height = meta["height"]
            changed = True
        if (not item.duration or item.duration <= 0) and meta.get("duration"):
            item.duration = meta["duration"]
            changed = True
        if changed:
            updated += 1
    if updated > 0:
        db.commit()
    return {"checked": checked, "updated": updated, "skipped_missing": skipped_missing}


@router.post("/backfill-video-metadata")
@__import__("app.services.media_operation_guard",fromlist=["guarded_mutation"]).guarded_mutation
def run_video_metadata_backfill(limit: int = 500, db: Session = Depends(get_db)) -> Dict[str, int]:
    return backfill_missing_video_metadata(db, limit=limit)
