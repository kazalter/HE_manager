"""Scheduled auto-sync+download for WNACG and X external favourites.

Facade module providing full backward compatibility for the modular
`app.services.auto_sync` implementation.
"""
from __future__ import annotations

from datetime import datetime, timedelta
import os
import threading
import time
import traceback
from typing import IO, List, Optional, Set

from . import database, models
from .services import auto_sync as _auto_sync_service
from .services.auto_sync import (
    LOCK_DIR,
    LOG_RETENTION_DAYS,
    LOG_RETENTION_PER_SOURCE,
    RETRY_DELAYS_MINUTES,
    TICK_INTERVAL,
    WNACG_DOWNLOAD_LIMIT,
    _active,
    _lock,
    _lock_file_name,
    _next_run_after_status,
    _prune_auto_sync_logs,
    _release_lock_file,
    _release_scheduler_lock,
    _release_source,
    _restore_schedules,
    _retry_delays,
    _run_source_worker,
    _run_wnacg,
    _run_x,
    _running,
    _scheduler_lock_file,
    _scheduler_lock_path,
    _source_key,
    _source_lock_files,
    _tick,
    _ticker_loop,
    _ticker_thread,
    _try_acquire_scheduler_lock,
    _try_acquire_source,
    _try_lock_file,
    init,
    is_running,
    is_source_active,
    stop,
    update_schedule,
)


def trigger_now(source_type: str, source_id: int) -> bool:
    """Immediately trigger an auto-sync run for the given source.
    Returns False if the source is already running.
    """
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


__all__ = [
    "LOCK_DIR",
    "LOG_RETENTION_DAYS",
    "LOG_RETENTION_PER_SOURCE",
    "RETRY_DELAYS_MINUTES",
    "TICK_INTERVAL",
    "WNACG_DOWNLOAD_LIMIT",
    "_active",
    "_lock",
    "_lock_file_name",
    "_next_run_after_status",
    "_prune_auto_sync_logs",
    "_release_lock_file",
    "_release_scheduler_lock",
    "_release_source",
    "_restore_schedules",
    "_retry_delays",
    "_run_source_worker",
    "_run_wnacg",
    "_run_x",
    "_running",
    "_scheduler_lock_file",
    "_scheduler_lock_path",
    "_source_key",
    "_source_lock_files",
    "_tick",
    "_ticker_loop",
    "_ticker_thread",
    "_try_acquire_scheduler_lock",
    "_try_acquire_source",
    "_try_lock_file",
    "database",
    "datetime",
    "init",
    "is_running",
    "is_source_active",
    "models",
    "os",
    "stop",
    "threading",
    "time",
    "timedelta",
    "traceback",
    "trigger_now",
    "update_schedule",
]
