import http.client
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services.external.pawchive import client, media_cache as cache_module, media_fetch

IMAGE_A = "/ab/cd/" + "a" * 64 + ".png"
IMAGE_B = "/ab/cd/" + "b" * 64 + ".png"


class FakeResponse:
    def __init__(self, body=b"data", status=200, will_close=False):
        self.status = status
        self.will_close = will_close
        self._body = body
        self._closed = False

    def getheader(self, name):
        return {"Content-Type": "image/png", "Content-Length": str(len(self._body))}.get(name)

    def read(self, size=-1):
        data, self._body = self._body, b""
        if not data:
            self._closed = True
        return data

    def isclosed(self):
        return self._closed


class FakeConnection:
    created = 0

    def __init__(self, stale=False, **response):
        FakeConnection.created += 1
        self.sock = object()
        self.stale = stale
        self.closed = False
        self.requests = 0
        self.response = response

    def request(self, method, target, headers=None):
        self.requests += 1

    def getresponse(self):
        if self.stale:
            raise http.client.RemoteDisconnected("idle connection closed")
        return FakeResponse(**self.response)

    def close(self):
        self.closed = True
        self.sock = None


class PoolTests(unittest.TestCase):
    def setUp(self):
        client.clear_pool()
        FakeConnection.created = 0
        self.proxy = patch("app.external_config.get_external_favorites_proxy", return_value=None)
        self.proxy.start()

    def tearDown(self):
        self.proxy.stop()
        client.clear_pool()

    def test_fully_read_connection_is_reused(self):
        with patch.object(client, "_new_connection", side_effect=lambda host: FakeConnection()):
            first, response = client.open_media(IMAGE_A)
            while response.read(64):
                pass
            first.close()
            second, _ = client.open_media(IMAGE_B)
        self.assertIs(second.connection, first.connection)
        self.assertEqual(FakeConnection.created, 1)

    def test_partially_read_connection_is_closed(self):
        with patch.object(client, "_new_connection", side_effect=lambda host: FakeConnection()):
            first, _ = client.open_media(IMAGE_A)
            first.close()
            first.close()
            second, _ = client.open_media(IMAGE_B)
        self.assertTrue(first.connection.closed)
        self.assertIsNot(second.connection, first.connection)

    def test_server_closing_connection_is_not_pooled(self):
        with patch.object(client, "_new_connection", side_effect=lambda host: FakeConnection(will_close=True)):
            first, response = client.open_media(IMAGE_A)
            response.read()
            response.read()
            first.close()
        self.assertTrue(first.connection.closed)
        self.assertEqual(client._pool, {})

    def test_stale_pooled_connection_is_replaced_transparently(self):
        stale = FakeConnection(stale=True)
        client._pool[(client.FILE_HOST, "")] = [(time.monotonic(), stale)]
        with patch.object(client, "_new_connection", side_effect=lambda host: FakeConnection()):
            handle, response = client.open_media(IMAGE_A)
        self.assertTrue(stale.closed)
        self.assertIsNot(handle.connection, stale)
        self.assertEqual(response.status, 200)

    def test_fresh_connection_failure_is_reported(self):
        with patch.object(client, "_new_connection", side_effect=lambda host: FakeConnection(stale=True)):
            with self.assertRaises(client.PawchiveError) as raised:
                client.open_media(IMAGE_A)
        self.assertEqual(raised.exception.code, "UPSTREAM_UNAVAILABLE")

    def test_idle_connections_expire(self):
        old = FakeConnection()
        client._pool[(client.FILE_HOST, "")] = [(time.monotonic() - client.POOL_IDLE_SECONDS - 1, old)]
        with patch.object(client, "_new_connection", side_effect=lambda host: FakeConnection()):
            handle, _ = client.open_media(IMAGE_A)
        self.assertTrue(old.closed)
        self.assertIsNot(handle.connection, old)

    def test_pool_is_separated_by_host_and_proxy(self):
        pooled = FakeConnection()
        client._pool[(client.FILE_HOST, "http://old-proxy:7890")] = [(time.monotonic(), pooled)]
        client._pool[(client.IMAGE_HOST, "")] = [(time.monotonic(), FakeConnection())]
        with patch.object(client, "_new_connection", side_effect=lambda host: FakeConnection()):
            handle, _ = client.open_media(IMAGE_A)
        self.assertIsNot(handle.connection, pooled)


class LaneTests(unittest.TestCase):
    def test_lane_limits_concurrent_upstream_downloads(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / ".mounted").write_text("")
            cache = cache_module.RestartMediaCache()
            active = 0
            peak = 0
            gate = threading.Event()
            lock = threading.Lock()

            class Body:
                def __init__(self):
                    self.status = 200
                    self.sent = False

                def getheader(self, name):
                    return {"Content-Type": "image/png", "Content-Length": "1"}.get(name)

                def read(self, size):
                    nonlocal active
                    if self.sent:
                        with lock:
                            active -= 1
                        return b""
                    gate.wait(5)
                    self.sent = True
                    return b"x"

            def open_media(path, *, preview=False, range_header=None):
                nonlocal active, peak
                with lock:
                    active += 1
                    peak = max(peak, active)
                return FakeConnection(), Body()

            with patch.object(cache_module, "MOUNT_ROOT", root), \
                    patch.object(cache_module, "CACHE_ROOT", root / "cache"), \
                    patch.object(media_fetch, "media_cache", cache), \
                    patch.dict(media_fetch._lanes, {"image": threading.BoundedSemaphore(1)}), \
                    patch.object(client, "open_media", side_effect=open_media):
                cache.reset_for_startup()
                first = media_fetch.open_shared(IMAGE_A, "image")
                second = media_fetch.open_shared(IMAGE_B, "image")
                first.wait_ready()
                time.sleep(0.2)
                self.assertFalse(second.ready)
                gate.set()
                second.wait_ready(5)
                for download in (first, second):
                    self.assertEqual(b"".join(download.reader()), b"x")
            media_fetch._downloads.clear()
        self.assertEqual(peak, 1)


if __name__ == "__main__":
    unittest.main()
