"""Shared upstream downloads for Pawchive images and previews.

One upstream download per file feeds every concurrent request and keeps going
for a short grace period after the last reader leaves. A viewer that retries a
slow image, or a preload that races the visible image, therefore reads the
bytes already fetched instead of starting over. Finished files are committed to
the restart-scoped media cache. Without a usable cache, callers stream directly.

Originals and thumbnails use separate upstream concurrency lanes. A page of
covers therefore cannot occupy every proxy connection while the viewer waits
for the original it is showing, and a few large originals cannot block covers.
"""
from __future__ import annotations

import logging
import os
import threading
import time

from . import client
from .media_cache import CacheLease, CacheWriter, media_cache

logger = logging.getLogger(__name__)
CHUNK_SIZE = 64 * 1024
# Upper bound for queueing plus the upstream response headers.
HEADER_TIMEOUT = 45.0
# An unfinished download with no reader stops after this many seconds.
ABANDON_GRACE = 15.0


def _lane_size(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except ValueError:
        return default


_lanes = {
    "image": threading.BoundedSemaphore(_lane_size("HE_PAWCHIVE_IMAGE_CONCURRENCY", 4)),
    "preview": threading.BoundedSemaphore(_lane_size("HE_PAWCHIVE_PREVIEW_CONCURRENCY", 6)),
}
_lock = threading.Lock()
_downloads: dict[tuple[str, str], "SharedDownload"] = {}


class SharedDownload:
    def __init__(self, kind: str, path: str, writer: CacheWriter):
        self.kind = kind
        self.path = path
        self.file_path = writer.path
        self._writer = writer
        self._cond = threading.Condition()
        self._readers = 0
        self._idle_since: float | None = None
        self.ready = False
        self.done = False
        self.error: client.PawchiveError | None = None
        self.content_type = ""
        self.expected_size: int | None = None
        self.size = 0

    # Reader bookkeeping -------------------------------------------------
    def attach(self) -> None:
        with self._cond:
            self._readers += 1
            self._idle_since = None

    def detach(self) -> None:
        with self._cond:
            self._readers = max(0, self._readers - 1)
            if not self._readers:
                self._idle_since = time.monotonic()

    def _abandoned(self) -> bool:
        with self._cond:
            return (not self._readers and self._idle_since is not None
                    and time.monotonic() - self._idle_since > ABANDON_GRACE)

    # Download side ------------------------------------------------------
    def _publish(self, **changes) -> None:
        with self._cond:
            for name, value in changes.items():
                setattr(self, name, value)
            self._cond.notify_all()

    def run(self) -> None:
        connection = None
        complete = False
        error: client.PawchiveError | None = None
        lane = _lanes[self.kind]
        acquired = False
        try:
            while not (acquired := lane.acquire(timeout=1.0)):
                if self._abandoned():
                    raise client.PawchiveError("CANCELED", "已无读取者", 499)
            if self._abandoned():
                raise client.PawchiveError("CANCELED", "已无读取者", 499)
            connection, response = client.open_media(self.path, preview=self.kind == "preview")
            content_type = (response.getheader("Content-Type") or "").split(";", 1)[0].strip().lower()
            if response.status != 200 or not content_type.startswith("image/"):
                raise client.PawchiveError("UPSTREAM_INVALID", "来源返回了无效的媒体响应", 502)
            length = response.getheader("Content-Length")
            expected = int(length) if length and length.isdigit() else None
            self._writer.content_type = content_type
            self._writer.expected_size = expected
            self._publish(ready=True, content_type=content_type, expected_size=expected)
            while chunk := response.read(CHUNK_SIZE):
                if self._abandoned():
                    raise client.PawchiveError("CANCELED", "已无读取者", 499)
                self._writer.write(chunk)
                if self._writer.file is None:
                    raise client.PawchiveError("CACHE_FAILED", "媒体缓存写入失败", 502)
                self._publish(size=self.size + len(chunk))
            complete = expected is None or self.size == expected
            if not complete:
                raise client.PawchiveError("UPSTREAM_UNAVAILABLE", "Pawchive 媒体传输中断", 502)
        except client.PawchiveError as exc:
            error = exc
        except Exception as exc:  # noqa: BLE001 - surfaced to every waiting reader
            logger.warning("Pawchive shared download failed", exc_info=True)
            error = client.PawchiveError("UPSTREAM_UNAVAILABLE", "Pawchive 暂时不可用", 502)
            error.__cause__ = exc
        finally:
            if connection is not None:
                connection.close()
            if acquired:
                lane.release()
            # Commit before leaving the registry so a new request finds the cache entry.
            self._writer.close(complete)
            self._publish(done=True, error=error)
            with _lock:
                if _downloads.get((self.kind, self.path)) is self:
                    del _downloads[(self.kind, self.path)]

    # Reader side --------------------------------------------------------
    def wait_ready(self, timeout: float = HEADER_TIMEOUT) -> None:
        deadline = time.monotonic() + timeout
        with self._cond:
            while not self.ready and not self.done:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise client.PawchiveError("UPSTREAM_UNAVAILABLE", "等待 Pawchive 媒体超时", 504)
                self._cond.wait(remaining)
            if not self.ready:
                raise self.error or client.PawchiveError("UPSTREAM_UNAVAILABLE", "Pawchive 暂时不可用", 502)

    def reader(self) -> "_Reader":
        """Stream the file as it grows; takes over the caller's attachment."""
        return _Reader(self)


class _Reader:
    """Byte iterator that detaches exactly once, even if never started.

    A generator that is closed before its first ``next`` never runs its
    ``finally`` block, which would leak the reader count and keep an abandoned
    download alive until it finished.
    """

    def __init__(self, download: SharedDownload):
        self._download = download
        self._handle = None
        self._offset = 0
        self._closed = False

    def __iter__(self):
        return self

    def __next__(self) -> bytes:
        if self._closed:
            raise StopIteration
        download = self._download
        try:
            if self._handle is None:
                self._handle = open(download.file_path, "rb")
            with download._cond:
                while download.size <= self._offset and not download.done:
                    download._cond.wait(1.0)
                available, error = download.size, download.error
            if available > self._offset:
                data = self._handle.read(min(available - self._offset, CHUNK_SIZE * 4))
                if not data:
                    raise client.PawchiveError("CACHE_FAILED", "媒体缓存读取失败", 502)
                self._offset += len(data)
                return data
            if error is not None:
                # Raising lets the server abort the response, so the browser
                # sees a failed load instead of a silently truncated image.
                raise error
        except BaseException:
            self.close()
            raise
        self.close()
        raise StopIteration

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._handle is not None:
            self._handle.close()
        self._download.detach()

    def __del__(self):
        self.close()


def open_shared(path: str, kind: str) -> CacheLease | SharedDownload | None:
    """Return a cache hit, an attached shared download, or None to stream directly.

    The lookup and registry check share one lock with registry removal, so a
    finished download is always visible either as a cache entry or in flight.
    """
    with _lock:
        cached = media_cache.lookup(path, kind)
        if cached is not None:
            return cached
        download = _downloads.get((kind, path))
        if download is None:
            writer = media_cache.begin_write(path, kind, "", None, in_place=True)
            if writer is None:
                return None
            download = SharedDownload(kind, path, writer)
            _downloads[(kind, path)] = download
            download.attach()
            threading.Thread(target=download.run, name="pawchive-media", daemon=True).start()
            return download
        download.attach()
        return download
