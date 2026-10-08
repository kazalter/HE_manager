import asyncio
import os
import queue
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import pawchive as router
from app.services.external.pawchive import client, media_cache as cache_module, media_fetch, refs

IMAGE = "/ab/cd/" + "a" * 64 + ".png"


class FakeConnection:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class GatedResponse:
    """Upstream body whose chunks are released one at a time by the test."""

    def __init__(self, chunks, status=200, content_type="image/png"):
        self.status = status
        self._chunks = queue.Queue()
        self._pending = list(chunks)
        self.headers = {"Content-Type": content_type,
                        "Content-Length": str(sum(len(chunk) for chunk in chunks))}

    def getheader(self, name):
        return self.headers.get(name)

    def release(self, count=1):
        for _ in range(count):
            self._chunks.put(self._pending.pop(0) if self._pending else b"")

    def release_all(self):
        self.release(len(self._pending) + 1)

    def read(self, size):
        return self._chunks.get(timeout=5)


def collect(response):
    async def read():
        return b"".join([part async for part in response.body_iterator])
    return asyncio.run(read())


def wait_until(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


class SharedDownloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        (root / ".mounted").write_text("")
        self.cache = cache_module.RestartMediaCache()
        self.patches = [
            patch.object(cache_module, "MOUNT_ROOT", root),
            patch.object(cache_module, "CACHE_ROOT", root / ".he-manager" / "pawchive-cache"),
            patch.object(media_fetch, "media_cache", self.cache),
            patch.object(router, "media_cache", self.cache),
        ]
        for item in self.patches:
            item.start()
        self.cache.reset_for_startup()
        self.opens = 0

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        media_fetch._downloads.clear()
        self.temp.cleanup()

    def fake_open(self, response):
        connection = FakeConnection()

        def open_media(path, *, preview=False, range_header=None):
            self.opens += 1
            if isinstance(response, Exception):
                raise response
            return connection, response
        return patch.object(client, "open_media", side_effect=open_media), connection

    def test_concurrent_readers_share_one_upstream_download(self):
        upstream = GatedResponse([b"aa", b"bb", b"cc"])
        opener, connection = self.fake_open(upstream)
        with opener:
            first = media_fetch.open_shared(IMAGE, "image")
            second = media_fetch.open_shared(IMAGE, "image")
            self.assertIs(first, second)
            first.wait_ready()
            readers = [first.reader(), second.reader()]
            upstream.release_all()
            bodies = [b"".join(reader) for reader in readers]
        self.assertEqual(bodies, [b"aabbcc", b"aabbcc"])
        self.assertEqual(self.opens, 1)
        self.assertTrue(wait_until(lambda: connection.closed))
        hit = media_fetch.open_shared(IMAGE, "image")
        self.assertIsInstance(hit, cache_module.CacheLease)
        self.assertEqual(Path(hit.path).read_bytes(), b"aabbcc")
        self.assertEqual(hit.content_type, "image/png")
        hit.release()

    def test_download_finishes_into_cache_after_reader_leaves(self):
        upstream = GatedResponse([b"12", b"34", b"56"])
        opener, _ = self.fake_open(upstream)
        with opener:
            download = media_fetch.open_shared(IMAGE, "image")
            download.wait_ready()
            reader = download.reader()
            upstream.release()
            self.assertEqual(next(reader), b"12")
            reader.close()
            upstream.release_all()
            self.assertTrue(wait_until(lambda: download.done))
        self.assertIsNone(download.error)
        retry = media_fetch.open_shared(IMAGE, "image")
        self.assertIsInstance(retry, cache_module.CacheLease)
        retry.release()

    def test_retry_during_download_reuses_fetched_bytes(self):
        upstream = GatedResponse([b"ab", b"cd"])
        opener, _ = self.fake_open(upstream)
        with opener:
            download = media_fetch.open_shared(IMAGE, "image")
            download.wait_ready()
            upstream.release()
            self.assertTrue(wait_until(lambda: download.size == 2))
            download.reader().close()
            again = media_fetch.open_shared(IMAGE, "image")
            self.assertIs(again, download)
            reader = again.reader()
            self.assertEqual(next(reader), b"ab")
            upstream.release_all()
            self.assertEqual(b"".join(reader), b"cd")
        self.assertEqual(self.opens, 1)

    def test_abandoned_download_stops_without_caching(self):
        upstream = GatedResponse([b"x" * 4, b"y" * 4, b"z" * 4])
        opener, connection = self.fake_open(upstream)
        with opener, patch.object(media_fetch, "ABANDON_GRACE", 0):
            download = media_fetch.open_shared(IMAGE, "image")
            download.wait_ready()
            download.reader().close()
            time.sleep(0.01)
            upstream.release_all()
            self.assertTrue(wait_until(lambda: download.done))
        self.assertEqual(download.error.code, "CANCELED")
        self.assertTrue(connection.closed)
        self.assertNotIn(("image", IMAGE), media_fetch._downloads)
        self.assertIsNone(self.cache.lookup(IMAGE, "image"))

    def test_upstream_error_reaches_every_waiter(self):
        opener, _ = self.fake_open(client.PawchiveError("NOT_FOUND", "来源内容不存在", 404))
        with opener:
            download = media_fetch.open_shared(IMAGE, "image")
            with self.assertRaises(client.PawchiveError) as raised:
                download.wait_ready()
            self.assertEqual(raised.exception.status, 404)
            self.assertTrue(wait_until(lambda: ("image", IMAGE) not in media_fetch._downloads))
            with self.assertRaises(client.PawchiveError) as routed:
                router.stream_media_response(refs.sign_media(IMAGE, "image"))
        self.assertEqual(routed.exception.status, 404)
        self.assertEqual(self.opens, 2)

    def test_truncated_upstream_fails_the_response(self):
        upstream = GatedResponse([b"ab", b"cd"])
        upstream.headers["Content-Length"] = "10"
        opener, _ = self.fake_open(upstream)
        with opener:
            download = media_fetch.open_shared(IMAGE, "image")
            download.wait_ready()
            reader = download.reader()
            upstream.release_all()
            with self.assertRaises(client.PawchiveError):
                b"".join(reader)
        self.assertIsNone(self.cache.lookup(IMAGE, "image"))

    def test_router_streams_shared_download(self):
        upstream = GatedResponse([b"png-", b"bytes"])
        opener, _ = self.fake_open(upstream)
        with opener:
            upstream.release_all()
            response = router.stream_media_response(refs.sign_media(IMAGE, "image"))
            self.assertEqual(response.headers["x-pawchive-cache"], "SHARED")
            self.assertEqual(response.headers["content-length"], "9")
            self.assertEqual(collect(response), b"png-bytes")
            hit = router.stream_media_response(refs.sign_media(IMAGE, "image"))
        self.assertEqual(hit.headers["x-pawchive-cache"], "HIT")
        hit.background.func()

    def test_endpoint_streams_through_media_threads(self):
        app = FastAPI()
        app.include_router(router.router)
        upstream = GatedResponse([b"ab", b"cd"])
        upstream.release_all()
        opener, _ = self.fake_open(upstream)
        with opener, patch.dict(os.environ, {"HE_PAWCHIVE_ENABLED": "1"}):
            url = f"/external/pawchive/media/{refs.sign_media(IMAGE, 'image')}"
            response = TestClient(app).get(url)
            missing = TestClient(app).get("/external/pawchive/media/expired.ref")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"abcd")
        self.assertEqual(response.headers["x-pawchive-cache"], "SHARED")
        self.assertEqual(missing.status_code, 400)
        self.assertEqual(missing.json()["detail"]["code"], "INVALID_REF")

    def test_range_requests_bypass_shared_download(self):
        opener, _ = self.fake_open(GatedResponse([b"ab"]))
        with opener, patch.object(media_fetch, "open_shared") as shared:
            response = router.stream_media_response(refs.sign_media(IMAGE, "image"), "bytes=0-1")
        shared.assert_not_called()
        response.background.func()


class ConcurrencyTests(unittest.TestCase):
    def test_reader_threads_see_bytes_as_they_arrive(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / ".mounted").write_text("")
            cache = cache_module.RestartMediaCache()
            upstream = GatedResponse([b"1", b"2", b"3"])
            with patch.object(cache_module, "MOUNT_ROOT", root), \
                    patch.object(cache_module, "CACHE_ROOT", root / "cache"), \
                    patch.object(media_fetch, "media_cache", cache), \
                    patch.object(client, "open_media", return_value=(FakeConnection(), upstream)):
                cache.reset_for_startup()
                download = media_fetch.open_shared(IMAGE, "preview")
                download.wait_ready()
                received = []
                thread = threading.Thread(target=lambda: received.extend(download.reader()))
                thread.start()
                for expected in (1, 2, 3):
                    upstream.release()
                    self.assertTrue(wait_until(lambda: len(received) == expected))
                upstream.release()
                thread.join(5)
            media_fetch._downloads.clear()
        self.assertEqual(received, [b"1", b"2", b"3"])


if __name__ == "__main__":
    unittest.main()
