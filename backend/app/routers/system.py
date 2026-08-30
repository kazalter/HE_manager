import logging
import os
from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.engine import make_url

from ..database import SQLALCHEMY_DATABASE_URL
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
