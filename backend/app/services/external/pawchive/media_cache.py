"""Restart-scoped, bounded disk cache for Pawchive image responses."""
from __future__ import annotations

import hashlib
import logging
import os
import shutil
import threading
import uuid
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)
MOUNT_ROOT = Path("/mnt/hdd")
CACHE_ROOT = MOUNT_ROOT / ".he-manager" / "pawchive-cache"
KINDS = ("image", "preview")


def _quota(name: str, default: int) -> int:
    try:
        return max(0, int(os.getenv(name, str(default))))
    except ValueError:
        return default


def _discard(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        logger.warning("Pawchive cache file cleanup failed", exc_info=True)


@dataclass
class _Entry:
    path: Path
    content_type: str
    size: int
    leases: int = 0


class CacheLease:
    def __init__(self, cache: "RestartMediaCache", kind: str, key: str, entry: _Entry):
        self._cache = cache
        self._kind = kind
        self._key = key
        self._released = False
        self.path = entry.path
        self.content_type = entry.content_type

    def release(self) -> None:
        if self._released:
            return
        self._released = True
        self._cache._release(self._kind, self._key)


class CacheWriter:
    def __init__(
        self, cache: "RestartMediaCache", kind: str, key: str,
        path: Path, content_type: str, expected_size: int | None,
    ):
        self.cache = cache
        self.kind = kind
        self.key = key
        self.path = path
        self.content_type = content_type
        self.expected_size = expected_size
        self.size = 0
        self.file = path.open("xb")

    def write(self, chunk: bytes) -> None:
        if self.file is None:
            return
        if self.size + len(chunk) > self.cache.limits[self.kind]:
            self.close(False)
            return
        try:
            self.file.write(chunk)
            self.size += len(chunk)
        except OSError:
            logger.warning("Pawchive cache write failed", exc_info=True)
            self.close(False)

    def close(self, complete: bool) -> None:
        if self.file is None:
            return
        try:
            self.file.close()
        except OSError:
            complete = False
            logger.warning("Pawchive cache file close failed", exc_info=True)
        finally:
            self.file = None
        if not complete or not self.size or (
            self.expected_size is not None and self.size != self.expected_size
        ):
            _discard(self.path)
            return
        self.cache._commit(self)


class RestartMediaCache:
    def __init__(self) -> None:
        self.limits = {
            "image": _quota("HE_PAWCHIVE_IMAGE_CACHE_BYTES", 10 * 1024 ** 3),
            "preview": _quota("HE_PAWCHIVE_PREVIEW_CACHE_BYTES", 1024 ** 3),
        }
        self._lock = threading.Lock()
        self._enabled = False
        self._entries: dict[str, OrderedDict[str, _Entry]] = {
            kind: OrderedDict() for kind in KINDS
        }
        self._sizes = {kind: 0 for kind in KINDS}

    def reset_for_startup(self) -> None:
        """Remove only this app's cache after verifying the external disk."""
        with self._lock:
            self._enabled = False
            for kind in KINDS:
                self._entries[kind].clear()
                self._sizes[kind] = 0
        try:
            if not MOUNT_ROOT.is_dir() or not (MOUNT_ROOT / ".mounted").is_file():
                logger.warning("Pawchive image cache disabled: /mnt/hdd is unavailable")
                return
            if CACHE_ROOT.is_symlink() or not CACHE_ROOT.resolve().is_relative_to(MOUNT_ROOT.resolve()):
                logger.warning("Pawchive image cache disabled: unsafe cache directory")
                return
            if CACHE_ROOT.exists():
                shutil.rmtree(CACHE_ROOT)
            for kind in KINDS:
                (CACHE_ROOT / kind).mkdir(parents=True, mode=0o700, exist_ok=True)
            with self._lock:
                self._enabled = True
            logger.info("Pawchive image cache initialized on /mnt/hdd")
        except OSError:
            logger.warning("Pawchive image cache disabled: startup cleanup failed", exc_info=True)

    @staticmethod
    def _key(path: str) -> str:
        return hashlib.sha256(path.encode("utf-8")).hexdigest()

    def lookup(self, path: str, kind: str) -> CacheLease | None:
        if kind not in KINDS:
            return None
        key = self._key(path)
        with self._lock:
            if not self._enabled:
                return None
            entries = self._entries[kind]
            entry = entries.get(key)
            if entry is None:
                return None
            if not entry.path.is_file():
                self._sizes[kind] -= entry.size
                del entries[key]
                return None
            entry.leases += 1
            entries.move_to_end(key)
            return CacheLease(self, kind, key, entry)

    def begin_write(
        self, path: str, kind: str, content_type: str, expected_size: int | None,
    ) -> CacheWriter | None:
        if kind not in KINDS:
            return None
        key = self._key(path)
        with self._lock:
            if not self._enabled or self.limits[kind] == 0 or key in self._entries[kind]:
                return None
        temporary = CACHE_ROOT / kind / f".{key}.{uuid.uuid4().hex}.part"
        try:
            return CacheWriter(self, kind, key, temporary, content_type, expected_size)
        except OSError:
            logger.warning("Pawchive cache temporary file unavailable", exc_info=True)
            return None

    def _commit(self, writer: CacheWriter) -> None:
        with self._lock:
            if not self._enabled or writer.key in self._entries[writer.kind]:
                _discard(writer.path)
                return
            destination = CACHE_ROOT / writer.kind / writer.key
            try:
                os.replace(writer.path, destination)
            except OSError:
                _discard(writer.path)
                logger.warning("Pawchive cache commit failed", exc_info=True)
                return
            self._entries[writer.kind][writer.key] = _Entry(
                destination, writer.content_type, writer.size
            )
            self._sizes[writer.kind] += writer.size
            self._evict(writer.kind)

    def _release(self, kind: str, key: str) -> None:
        with self._lock:
            entry = self._entries[kind].get(key)
            if entry is not None:
                entry.leases = max(0, entry.leases - 1)
            self._evict(kind)

    def _evict(self, kind: str) -> None:
        entries = self._entries[kind]
        while self._sizes[kind] > self.limits[kind]:
            victim = next(((key, entry) for key, entry in entries.items() if entry.leases == 0), None)
            if victim is None:
                return
            key, entry = victim
            try:
                entry.path.unlink(missing_ok=True)
            except OSError:
                logger.warning("Pawchive cache eviction failed", exc_info=True)
                return
            del entries[key]
            self._sizes[kind] -= entry.size


media_cache = RestartMediaCache()
