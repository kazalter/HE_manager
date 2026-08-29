from __future__ import annotations

from datetime import datetime
import errno
import os
import re
import threading
from typing import IO, Optional, Set

LOCK_DIR = os.getenv("HE_AUTO_SYNC_LOCK_DIR", "/tmp/he-manager-auto-sync")

_lock = threading.Lock()
_active: Set[str] = set()
_source_lock_files: dict[str, IO[str]] = {}
_scheduler_lock_file: Optional[IO[str]] = None


def get_lock_dir() -> str:
    try:
        from ... import auto_sync
        return getattr(auto_sync, "LOCK_DIR", LOCK_DIR)
    except Exception:
        return LOCK_DIR


def _source_key(source_type: str, source_id: int) -> str:
    return f"{source_type}:{source_id}"


def _lock_file_name(key: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", key)


def _try_lock_file(path: str) -> Optional[IO[str]]:
    """Acquire a non-blocking process lock, returning the held file handle."""
    lock_dir = os.path.dirname(path)
    if lock_dir:
        os.makedirs(lock_dir, exist_ok=True)
    lock_file = open(path, "a+", encoding="utf-8")
    try:
        if os.name == "nt":
            import msvcrt

            lock_file.seek(0)
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (BlockingIOError, PermissionError):
        lock_file.close()
        return None
    except OSError as exc:
        lock_file.close()
        if os.name == "nt" and exc.errno in (errno.EACCES, errno.EDEADLK):
            return None
        raise
    except Exception:
        lock_file.close()
        raise
    lock_file.seek(0)
    lock_file.truncate()
    lock_file.write(f"{os.getpid()} {datetime.utcnow().isoformat()}\n")
    lock_file.flush()
    return lock_file


def _release_lock_file(lock_file: IO[str]) -> None:
    try:
        if os.name == "nt":
            import msvcrt

            lock_file.seek(0)
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
    finally:
        lock_file.close()


def _scheduler_lock_path() -> str:
    return os.getenv(
        "HE_AUTO_SYNC_SCHEDULER_LOCK_PATH",
        os.path.join(get_lock_dir(), "scheduler.lock"),
    )


def _try_acquire_scheduler_lock() -> bool:
    global _scheduler_lock_file
    lock_file = _try_lock_file(_scheduler_lock_path())
    if not lock_file:
        return False
    _scheduler_lock_file = lock_file
    return True


def _release_scheduler_lock() -> None:
    global _scheduler_lock_file
    if _scheduler_lock_file:
        _release_lock_file(_scheduler_lock_file)
        _scheduler_lock_file = None


def _try_acquire_source(source_type: str, source_id: int) -> bool:
    key = _source_key(source_type, source_id)
    with _lock:
        if key in _active:
            return False
        lock_path = os.path.join(get_lock_dir(), f"{_lock_file_name(key)}.lock")
        lock_file = _try_lock_file(lock_path)
        if not lock_file:
            return False
        _active.add(key)
        _source_lock_files[key] = lock_file
        return True


def _release_source(source_type: str, source_id: int) -> None:
    key = _source_key(source_type, source_id)
    with _lock:
        _active.discard(key)
        lock_file = _source_lock_files.pop(key, None)
    if lock_file:
        _release_lock_file(lock_file)
