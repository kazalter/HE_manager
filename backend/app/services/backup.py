import glob
import logging
import os
import re
import sqlite3
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_BACKUP_KEEP = 7
DEFAULT_MAX_AGE_HOURS = 24.0


def get_default_backup_dir(db_path: Optional[str] = None) -> str:
    """
    Derives standard backup directory:
    - If db is in /data/library.db -> /data/backups
    - Otherwise -> <db_dir>/../backups or <db_dir>/backups
    """
    if db_path:
        db_dir = os.path.dirname(os.path.abspath(db_path))
        if os.path.basename(db_dir) == "data" or db_dir == "/data":
            return os.path.join(db_dir, "backups")
        return os.path.abspath(os.path.join(db_dir, "..", "backups"))
    return os.path.abspath(os.path.join(os.getcwd(), "backups"))


def backup_database(
    db_path: str,
    backup_dir: Optional[str] = None,
    keep_count: int = DEFAULT_BACKUP_KEEP,
) -> Dict[str, Any]:
    """
    Performs a live, transaction-consistent SQLite hot backup using SQLite's
    online backup API, then rotates older backups.
    """
    if not db_path or not os.path.isfile(db_path):
        raise FileNotFoundError(f"Database file not found at: {db_path}")

    target_backup_dir = backup_dir or get_default_backup_dir(db_path)
    os.makedirs(target_backup_dir, exist_ok=True)
    if os.name != "nt":
        try:
            os.chmod(target_backup_dir, 0o700)
        except OSError:
            pass

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    dest_filename = f"library-{stamp}.db"
    dest_path = os.path.join(target_backup_dir, dest_filename)

    logger.info("Starting online SQLite hot backup: %s -> %s", db_path, dest_path)
    
    # Use standard sqlite3 online backup API
    src_conn = sqlite3.connect(db_path, timeout=30.0)
    dst_conn = sqlite3.connect(dest_path)
    try:
        with dst_conn:
            src_conn.backup(dst_conn, pages=100)
    finally:
        dst_conn.close()
        src_conn.close()

    if os.name != "nt":
        try:
            os.chmod(dest_path, 0o600)
        except OSError:
            pass

    size_bytes = os.path.getsize(dest_path) if os.path.exists(dest_path) else 0

    # Rotate old backups
    cleanup_result = rotate_backups(target_backup_dir, keep_count=keep_count)

    logger.info(
        "Backup completed: %s (%.2f MB). Rotated %d old backups.",
        dest_filename,
        size_bytes / (1024 * 1024),
        cleanup_result["removed_count"],
    )

    return {
        "success": True,
        "backup_name": dest_filename,
        "backup_path": dest_path,
        "size_bytes": size_bytes,
        "timestamp": stamp,
        "kept_backups": cleanup_result["kept_count"],
    }


def list_backups(backup_dir: str) -> List[Dict[str, Any]]:
    """Returns a list of backup files sorted newest first."""
    if not os.path.isdir(backup_dir):
        return []

    pattern = os.path.join(backup_dir, "library-*.db")
    files = glob.glob(pattern)
    results = []
    now = time.time()

    for path in sorted(files, reverse=True):
        try:
            stat = os.stat(path)
            raw_age_hours = max(0.0, (now - stat.st_mtime) / 3600.0)
            age_hours = round(raw_age_hours, 2)
            results.append({
                "name": os.path.basename(path),
                "path": path,
                "size_bytes": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                "age_hours": age_hours,
                "_raw_age_hours": raw_age_hours,
            })
        except OSError:
            continue

    return results


def rotate_backups(backup_dir: str, keep_count: int = DEFAULT_BACKUP_KEEP) -> Dict[str, int]:
    """Removes older backups beyond `keep_count`."""
    if not os.path.isdir(backup_dir):
        return {"kept_count": 0, "removed_count": 0}

    pattern = os.path.join(backup_dir, "library-*.db")
    files = sorted(glob.glob(pattern), reverse=True)
    
    removed = 0
    kept = 0
    for idx, path in enumerate(files):
        if idx < keep_count:
            kept += 1
        else:
            try:
                os.remove(path)
                removed += 1
                for sidecar in (f"{path}-wal", f"{path}-shm"):
                    if os.path.exists(sidecar):
                        os.remove(sidecar)
            except OSError as exc:
                logger.warning("Failed to remove old backup %s: %s", path, exc)

    return {"kept_count": kept, "removed_count": removed}


def check_backup_freshness(
    backup_dir: str,
    max_age_hours: float = DEFAULT_MAX_AGE_HOURS,
) -> Dict[str, Any]:
    """
    Inspects existing backups and checks if the newest backup is within max_age_hours.
    Returns structured status dict.
    """
    backups = list_backups(backup_dir)
    if not backups:
        return {
            "healthy": False,
            "stale": True,
            "total_backups": 0,
            "latest_backup": None,
            "latest_backup_time": None,
            "age_hours": None,
            "max_age_hours": max_age_hours,
            "message": f"No database backups found in '{backup_dir}'",
        }

    latest = backups[0]
    raw_age_hours = latest.get("_raw_age_hours", latest["age_hours"])
    age_hours = latest["age_hours"]
    is_fresh = raw_age_hours <= max_age_hours

    message = (
        f"Latest backup '{latest['name']}' is {age_hours:.1f}h old (threshold: {max_age_hours:.1f}h)"
        if is_fresh
        else f"Backup is stale: latest backup '{latest['name']}' is {age_hours:.1f}h old (exceeds {max_age_hours:.1f}h threshold)"
    )

    return {
        "healthy": is_fresh,
        "stale": not is_fresh,
        "total_backups": len(backups),
        "latest_backup": latest["name"],
        "latest_backup_path": latest["path"],
        "latest_backup_time": latest["modified_at"],
        "age_hours": age_hours,
        "max_age_hours": max_age_hours,
        "message": message,
    }
