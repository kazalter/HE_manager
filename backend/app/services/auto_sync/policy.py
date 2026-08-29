from __future__ import annotations

from datetime import datetime, timedelta
import os
from typing import List

from ... import models

TICK_INTERVAL = 30
RETRY_DELAYS_MINUTES = [5, 15, 60]
WNACG_DOWNLOAD_LIMIT = max(1, int(os.getenv("HE_AUTO_SYNC_WNACG_DOWNLOAD_LIMIT", "20")))
LOG_RETENTION_DAYS = max(1, int(os.getenv("HE_AUTO_SYNC_LOG_RETENTION_DAYS", "90")))
LOG_RETENTION_PER_SOURCE = max(1, int(os.getenv("HE_AUTO_SYNC_LOG_RETENTION_PER_SOURCE", "500")))


def _retry_delays() -> List[timedelta]:
    raw = os.getenv("HE_AUTO_SYNC_RETRY_DELAYS_MINUTES")
    if not raw:
        return [timedelta(minutes=value) for value in RETRY_DELAYS_MINUTES]
    values = []
    for part in raw.split(","):
        part = part.strip()
        if part:
            values.append(max(1, int(part)))
    return [timedelta(minutes=value) for value in (values or RETRY_DELAYS_MINUTES)]


def _next_run_after_status(
    db,
    source_type: str,
    source_id: int,
    status: str,
    finished_at: datetime,
    interval_hours: int,
) -> datetime:
    if status == "success":
        return finished_at + timedelta(hours=interval_hours)

    delays = _retry_delays()
    previous_failures = 0
    recent_logs = (
        db.query(models.AutoSyncLog)
        .filter(
            models.AutoSyncLog.source_type == source_type,
            models.AutoSyncLog.source_id == source_id,
        )
        .order_by(models.AutoSyncLog.id.desc())
        .limit(len(delays))
        .all()
    )
    for log in recent_logs:
        if log.status == "success":
            break
        previous_failures += 1
    delay = delays[min(previous_failures, len(delays) - 1)]
    return finished_at + delay


def _prune_auto_sync_logs(db) -> None:
    cutoff = datetime.utcnow() - timedelta(days=LOG_RETENTION_DAYS)
    db.query(models.AutoSyncLog).filter(models.AutoSyncLog.started_at < cutoff).delete(
        synchronize_session=False
    )

    pairs = (
        db.query(models.AutoSyncLog.source_type, models.AutoSyncLog.source_id)
        .distinct()
        .all()
    )
    for source_type, source_id in pairs:
        keep_ids = [
            row[0]
            for row in (
                db.query(models.AutoSyncLog.id)
                .filter(
                    models.AutoSyncLog.source_type == source_type,
                    models.AutoSyncLog.source_id == source_id,
                )
                .order_by(models.AutoSyncLog.id.desc())
                .limit(LOG_RETENTION_PER_SOURCE)
                .all()
            )
        ]
        if keep_ids:
            db.query(models.AutoSyncLog).filter(
                models.AutoSyncLog.source_type == source_type,
                models.AutoSyncLog.source_id == source_id,
                ~models.AutoSyncLog.id.in_(keep_ids),
            ).delete(synchronize_session=False)
