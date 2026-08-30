from __future__ import annotations

from datetime import datetime, timedelta
import logging
import threading
import time
import traceback
from typing import Optional

from ... import database, models
from .locks import (
    _active,
    _lock,
    _release_lock_file,
    _release_scheduler_lock,
    _release_source,
    _scheduler_lock_path,
    _source_key,
    _try_acquire_scheduler_lock,
    _try_acquire_source,
    _try_lock_file,
)
from .policy import TICK_INTERVAL, _prune_auto_sync_logs
from .wnacg import _run_wnacg
from .x_worker import _run_x

logger = logging.getLogger(__name__)

_running = False
_ticker_thread: Optional[threading.Thread] = None


def _run_source_worker(source_type: str, source_id: int) -> None:
    try:
        if source_type == "wnacg":
            _run_wnacg(source_id)
        elif source_type == "x":
            _run_x(source_id)
    finally:
        _release_source(source_type, source_id)


def _tick() -> None:
    """Called every TICK_INTERVAL seconds. Checks all auto-sync-enabled sources
    and fires off workers for any that are overdue.
    """
    now = datetime.utcnow()
    db = database.SessionLocal()
    try:
        # --- WNACG sources ---
        wnacg_sources = (
            db.query(models.ExternalFavoriteSource)
            .filter(
                models.ExternalFavoriteSource.auto_sync_enabled == True,  # noqa: E712
                models.ExternalFavoriteSource.source_type == "wnacg",
            )
            .all()
        )
        for source in wnacg_sources:
            if source.auto_sync_next_run_at and source.auto_sync_next_run_at > now:
                continue
            if not _try_acquire_source("wnacg", source.id):
                continue
            threading.Thread(
                target=_run_source_worker,
                args=("wnacg", source.id),
                daemon=True,
                name=f"auto-sync-wnacg-{source.id}",
            ).start()

        # --- X sources ---
        x_sources = (
            db.query(models.XImportSource)
            .filter(models.XImportSource.auto_sync_enabled == True)  # noqa: E712
            .all()
        )
        for source in x_sources:
            if source.auto_sync_next_run_at and source.auto_sync_next_run_at > now:
                continue
            if not _try_acquire_source("x", source.id):
                continue
            threading.Thread(
                target=_run_source_worker,
                args=("x", source.id),
                daemon=True,
                name=f"auto-sync-x-{source.id}",
            ).start()
    except Exception as exc:
        logger.error("[auto-sync] ticker error: %s", exc)
    finally:
        db.close()


def _ticker_loop() -> None:
    """Background loop that fires _tick() periodically."""
    while _running:
        try:
            _tick()
        except Exception as exc:
            logger.exception("[auto-sync] unhandled exception in ticker loop: %s", exc)
        for _ in range(int(TICK_INTERVAL / 0.5)):
            if not _running:
                return
            time.sleep(0.5)


def init() -> None:
    """Start the scheduler. Called once from app startup (main.py)."""
    global _running, _ticker_thread
    with _lock:
        if _running:
            return
        if not _try_acquire_scheduler_lock():
            logger.info("[auto-sync] scheduler already active in another process")
            return
        _running = True
        _restore_schedules()
        _ticker_thread = threading.Thread(
            target=_ticker_loop, daemon=True, name="auto-sync-ticker"
        )
        _ticker_thread.start()
        logger.info("[auto-sync] scheduler started")


def stop() -> None:
    """Stop the scheduler."""
    global _running
    _running = False
    _release_scheduler_lock()


def is_running() -> bool:
    if _running:
        return True
    lock_file = _try_lock_file(_scheduler_lock_path())
    if lock_file:
        _release_lock_file(lock_file)
        return False
    return True


def is_source_active(source_type: str, source_id: int) -> bool:
    with _lock:
        return _source_key(source_type, source_id) in _active


def trigger_now(source_type: str, source_id: int) -> bool:
    """Immediately trigger an auto-sync run for the given source."""
    if not _try_acquire_source(source_type, source_id):
        return False
    if source_type == "wnacg":
        threading.Thread(
            target=_run_source_worker,
            args=("wnacg", source_id),
            daemon=True,
            name=f"auto-sync-wnacg-{source_id}-manual",
        ).start()
    elif source_type == "x":
        threading.Thread(
            target=_run_source_worker,
            args=("x", source_id),
            daemon=True,
            name=f"auto-sync-x-{source_id}-manual",
        ).start()
    else:
        _release_source(source_type, source_id)
        return False
    return True


def update_schedule(
    source_type: str,
    source_id: int,
    enabled: bool,
    interval_hours: int,
) -> None:
    """Persist auto-sync configuration and compute next_run_at."""
    db = database.SessionLocal()
    try:
        if source_type == "wnacg":
            source = (
                db.query(models.ExternalFavoriteSource)
                .filter(models.ExternalFavoriteSource.id == source_id)
                .first()
            )
        elif source_type == "x":
            source = (
                db.query(models.XImportSource)
                .filter(models.XImportSource.id == source_id)
                .first()
            )
        else:
            return

        if not source:
            return

        source.auto_sync_enabled = enabled
        source.auto_sync_interval_hours = interval_hours
        if enabled:
            last_run = source.auto_sync_last_run_at or datetime.utcnow()
            source.auto_sync_next_run_at = last_run + timedelta(
                hours=interval_hours
            )
        else:
            source.auto_sync_next_run_at = None
        db.commit()
    finally:
        db.close()


def _restore_schedules() -> None:
    """On startup, ensure next_run_at is set for any enabled source that has
    a stale / NULL next_run_at.
    """
    db = database.SessionLocal()
    try:
        now = datetime.utcnow()
        for source in (
            db.query(models.ExternalFavoriteSource)
            .filter(models.ExternalFavoriteSource.source_type == "wnacg")
            .all()
        ):
            if source.auto_sync_last_status == "running":
                source.auto_sync_last_status = "failed"
                source.auto_sync_last_message = "上次自动同步在服务重启前中断"
            if not source.auto_sync_enabled:
                continue
            if not source.auto_sync_next_run_at or source.auto_sync_next_run_at < now:
                source.auto_sync_next_run_at = now + timedelta(seconds=60)

        for source in db.query(models.XImportSource).all():
            if source.auto_sync_last_status == "running":
                source.auto_sync_last_status = "failed"
                source.auto_sync_last_message = "上次自动同步在服务重启前中断"
            if not source.auto_sync_enabled:
                continue
            if not source.auto_sync_next_run_at or source.auto_sync_next_run_at < now:
                source.auto_sync_next_run_at = now + timedelta(seconds=60)
        _prune_auto_sync_logs(db)
        db.commit()
    except Exception:
        traceback.print_exc()
    finally:
        db.close()
