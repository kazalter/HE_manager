"""Regression coverage for originals served outside the legacy file host."""
import asyncio
import io
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from app import models
from app.routers import pawchive as router
from app.services.external.pawchive import client, creator_images, downloader, media_fetch, normalize, refs, sources
from app.services.external.pawchive import media_cache as cache_module

PATH = "/ab/cd/" + "a" * 64 + ".jpg"
TEMP_URL = "https://t1.pawchive.pw/f/0123456789abcdef/original.png?e=1999999999&s=" + "a" * 32


def detail(file):
    return normalize.normalize_post({"id": "123", "user": "456", "service": "patreon",
                                     "file": file, "attachments": []}, detail=True)


class Response:
    def __init__(self, status=200, body=b"original", mime="image/png"):
        self.status = status
        self.body = io.BytesIO(body)
        self.headers = {"Content-Type": mime, "Content-Length": str(len(body))}
        if status == 206:
            self.headers["Content-Range"] = f"bytes 0-{len(body)-1}/100"

    def getheader(self, name):
        return self.headers.get(name)

    def read(self, size):
        return self.body.read(size)


class Connection:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class SourceTests(unittest.TestCase):
    def test_temporary_original_and_preview_have_separate_locations(self):
        post = detail({"path": PATH, "name": "original.png", "preview_only": True, "temp_url": TEMP_URL})
        self.assertEqual(post["source_url"], "https://pawchive.pw/patreon/user/456/post/123")
        item = post["attachments"][0]
        self.assertEqual(item["mime_type"], "image/png")
        self.assertEqual(refs.read_media_source(item["stream_ref"]), (PATH, "image", TEMP_URL))
        self.assertEqual(refs.read_media_source(item["preview_ref"]), (PATH, "preview", None))
        legacy = detail({"path": PATH})["attachments"][0]
        self.assertEqual(item["attachment_key"], legacy["attachment_key"])
        self.assertEqual(refs.read_media_source(legacy["stream_ref"]), (PATH, "image", None))

    def test_creator_images_use_validated_paths_and_check_content(self):
        connection = Connection()
        with patch.dict("os.environ", {"HE_PAWCHIVE_ENABLED": "1"}), \
                patch.object(client, "_request", return_value=(connection, Response(body=b"image"))) as request:
            result = router.get_creator_image("icons", "patreon", "456")
            self.assertEqual(result.body, b"image")
            request.assert_called_once_with("pawchive.pw", "/icons/patreon/456")
            self.assertTrue(connection.closed)
            with self.assertRaises(Exception):
                router.get_creator_image("icons", "patreon", "../bad")
            self.assertEqual(request.call_count, 1)

    def test_t3_original_round_trips_and_fetches(self):
        for host in ("t2.pawchive.pw", "t3.pawchive.pw", "t4.pawchive.pw"):
            with self.subTest(host=host):
                url = TEMP_URL.replace("t1.pawchive.pw", host)
                item = detail({"path": PATH, "temp_url": url})["attachments"][0]
                with patch.object(client, "_request", return_value=(Connection(), Response(206))) as request:
                    response = router.stream_media_response(item["stream_ref"], "bytes=0-7")
                self.assertEqual(request.call_args.args[0], host)
                self.assertEqual(response.status_code, 206)
                response.background.func()

    def test_node_original_uses_node_host_and_preserves_range(self):
        item = detail({"path": PATH, "node": 2})["attachments"][0]
        connection = Connection()
        with patch.object(client, "_request", return_value=(connection, Response(206))) as request:
            response = router.stream_media_response(item["stream_ref"], "bytes=0-7")
        request.assert_called_once_with("n2.pawchive.pw", "/data" + PATH, range_header="bytes=0-7")
        self.assertEqual(response.status_code, 206)
        self.assertEqual(response.headers["content-range"], "bytes 0-7/100")
        response.background.func()

    def test_preview_jpeg_can_point_to_original_video(self):
        url = TEMP_URL.replace("original.png", "clip.mp4")
        item = detail({"path": PATH, "temp_url": url})["attachments"][0]
        self.assertEqual(item["media_type"], "video")
        with patch.object(client, "_request", return_value=(Connection(), Response(206, mime="video/mp4"))) as request:
            response = router.stream_media_response(item["stream_ref"], "bytes=0-7")
        self.assertEqual(request.call_args.args[0], "t1.pawchive.pw")
        self.assertEqual(response.media_type, "video/mp4")
        response.background.func()

    def test_shared_image_cache_fetches_original_not_preview(self):
        item = detail({"path": PATH, "preview_only": True, "temp_url": TEMP_URL})["attachments"][0]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / ".mounted").touch()
            cache = cache_module.RestartMediaCache()
            with patch.object(cache_module, "MOUNT_ROOT", root), \
                    patch.object(cache_module, "CACHE_ROOT", root / "cache"), \
                    patch.object(media_fetch, "media_cache", cache), patch.object(router, "media_cache", cache), \
                    patch.object(client, "_request", return_value=(Connection(), Response())) as request:
                cache.reset_for_startup()
                response = router.stream_media_response(item["stream_ref"])

                async def collect():
                    return b"".join([chunk async for chunk in response.body_iterator])

                self.assertEqual(asyncio.run(collect()), b"original")
                response.background.func()
                cached = router.stream_media_response(item["stream_ref"])
                self.assertEqual(cached.headers["x-pawchive-cache"], "HIT")
                cached.background.func()
            request.assert_called_once_with("t1.pawchive.pw", sources.validate_source(TEMP_URL)[1], range_header=None)

    def test_download_uses_temporary_original_with_correct_suffix(self):
        output = io.BytesIO()
        Image.new("RGB", (2, 2), "red").save(output, format="PNG")
        item = detail({"path": PATH, "temp_url": TEMP_URL})["attachments"][0]
        path, _, source_url = refs.read_media_source(item["stream_ref"])
        post = models.PawchivePost(service="patreon", creator_id="456", post_id="123")
        row = models.PawchiveAttachment(original_index=0, attachment_key=item["attachment_key"], media_type="image")
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(client, "_request", return_value=(Connection(), Response(body=output.getvalue()))) as request:
            root = Path(directory).resolve()
            target, manifest = downloader._target(root, post, row, sources.original_path(path, source_url))
            size, _ = downloader._fetch_file(path, target, manifest, row, threading.Event(), root, source_url=source_url)
            self.assertEqual(target.suffix, ".png")
            self.assertEqual(size, len(output.getvalue()))
            self.assertEqual(target.read_bytes(), output.getvalue())
        self.assertEqual(request.call_args.args[0], "t1.pawchive.pw")

    def test_expired_temporary_link_does_not_report_missing_original(self):
        for status in (401, 403, 404, 410):
            with self.subTest(status=status):
                connection = Connection()
                with patch.object(client, "_request", return_value=(connection, Response(status))):
                    with self.assertRaises(client.PawchiveError) as raised:
                        client.open_media(PATH, source_url=TEMP_URL)
                self.assertEqual(raised.exception.code, "MEDIA_LINK_EXPIRED")
                self.assertEqual(raised.exception.status, 502)
                self.assertTrue(connection.closed)

    def test_unsafe_source_urls_are_rejected_before_network_access(self):
        unsafe = [TEMP_URL.replace("t1.pawchive.pw", host) for host in (
            "127.0.0.1", "t1.pawchive.pw.evil.com", "user@t1.pawchive.pw", "t1.pawchive.pw:444", "t99.pawchive.pw")]
        unsafe += [TEMP_URL.replace("https:", "http:"), TEMP_URL + "&s=" + "b" * 32,
                   TEMP_URL + "#fragment", TEMP_URL.replace("original.png", "%2e%2e%2fsecret.png"),
                   TEMP_URL.replace("original.png", "%0d%0aX-Test.png"), TEMP_URL + "\n"]
        with patch.object(client, "_request") as request:
            for url in unsafe:
                with self.subTest(url=url), self.assertRaises(client.PawchiveError):
                    client.open_media(PATH, source_url=url)
            request.assert_not_called()

    def test_redirect_is_not_followed(self):
        connection = unittest.mock.Mock()
        connection.getresponse.return_value = Response(302)
        with patch.object(client, "_new_connection", return_value=connection), \
                patch("app.external_config.get_external_favorites_proxy", return_value=None):
            with self.assertRaises(client.PawchiveError) as raised:
                client.open_media(PATH, source_url=TEMP_URL)
        self.assertEqual(raised.exception.code, "UPSTREAM_REDIRECT")
        connection.close.assert_called_once()


THREE_HEX_PATH = "/1f5/4a/" + "b" * 64 + ".png"


class ExtendedSourceAndCreatorArtworkTests(unittest.TestCase):
    def _reset_creator_image_state(self):
        with creator_images._state_lock:
            creator_images._scopes.clear()
            creator_images._loaded_root = None
        with creator_images._queue_lock:
            creator_images._queue.clear()
            creator_images._queued.clear()

    def test_three_hex_path_and_server_field_work_end_to_end(self):
        post = normalize.normalize_post(
            {
                "id": "999",
                "user": "19469841",
                "service": "fanbox",
                "file": {"name": "art.png", "path": THREE_HEX_PATH, "server": "https://n3.pawchive.pw"},
                "attachments": [],
            },
            detail=True,
        )
        item = post["attachments"][0]
        self.assertEqual(item["media_type"], "image")
        self.assertEqual(item["mime_type"], "image/png")
        expected_url = f"https://n3.pawchive.pw/data{THREE_HEX_PATH}"
        self.assertEqual(refs.read_media_source(item["stream_ref"]), (THREE_HEX_PATH, "image", expected_url))
        self.assertEqual(refs.read_media_source(item["preview_ref"]), (THREE_HEX_PATH, "preview", None))

        connection = Connection()
        with patch.object(client, "_request", return_value=(connection, Response(206))) as request:
            response = router.stream_media_response(item["stream_ref"], "bytes=0-7")
        request.assert_called_once_with("n3.pawchive.pw", "/data" + THREE_HEX_PATH, range_header="bytes=0-7")
        self.assertEqual(response.status_code, 206)
        response.background.func()

    def test_untrusted_server_field_is_rejected(self):
        for bad_server in ("https://evil.com", "https://n99.pawchive.pw", "http://n3.pawchive.pw", "https://n3.pawchive.pw/extra"):
            with self.subTest(bad_server=bad_server):
                with self.assertRaises(client.PawchiveError) as raised:
                    detail({"path": THREE_HEX_PATH, "server": bad_server})
                self.assertEqual(raised.exception.code, "UPSTREAM_INVALID")

    def test_creator_image_sniffs_octet_stream_images_and_rejects_invalid_bytes(self):
        jpeg_bytes = io.BytesIO()
        Image.new("RGB", (4, 4), "blue").save(jpeg_bytes, format="JPEG")
        raw_jpeg = jpeg_bytes.getvalue()

        connection = Connection()
        with patch.dict("os.environ", {"HE_PAWCHIVE_ENABLED": "1"}),                 patch.object(creator_images, "_disk_root", return_value=None),                 patch.object(client, "_request", return_value=(connection, Response(body=raw_jpeg, mime="application/octet-stream"))):
            result = router.get_creator_image("icons", "fanbox", "19469841")
        self.assertEqual(result.media_type, "image/jpeg")
        self.assertEqual(result.body, raw_jpeg)
        self.assertTrue(connection.closed)

        bad_connection = Connection()
        with patch.dict("os.environ", {"HE_PAWCHIVE_ENABLED": "1"}),                 patch.object(creator_images, "_disk_root", return_value=None),                 patch.object(client, "_request", return_value=(bad_connection, Response(body=b"not-an-image", mime="application/octet-stream"))):
            with self.assertRaises(Exception) as raised:
                router.get_creator_image("banners", "fanbox", "19469841")
        self.assertEqual(raised.exception.status_code, 502)
        self.assertTrue(bad_connection.closed)

    def test_favorite_creator_artwork_persists_across_restarts_and_negative_caches_404(self):
        webp_bytes = io.BytesIO()
        Image.new("RGB", (8, 4), "green").save(webp_bytes, format="WEBP")
        raw_webp = webp_bytes.getvalue()

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / ".mounted").touch()
            artwork_root = root / ".he-manager" / "pawchive-creators" / "artwork"
            self._reset_creator_image_state()
            with patch.dict("os.environ", {"HE_PAWCHIVE_ENABLED": "1"}),                     patch.object(creator_images, "MOUNT_ROOT", root),                     patch.object(creator_images, "ARTWORK_ROOT", artwork_root),                     patch.object(creator_images, "PREFETCH_INTERVAL", 0):
                # Mark favorite without triggering background worker during first assertion
                with patch.object(creator_images, "enqueue_favorites"):
                    creator_images.sync_favorites("account:5", [{"service": "fanbox", "creator_id": "19469841"}])

                with patch.object(
                    client,
                    "_request",
                    side_effect=[
                        (Connection(), Response(body=raw_webp, mime="application/octet-stream")),
                        (Connection(), Response(404, body=b"", mime="text/plain")),
                    ],
                ) as request:
                    first = router.get_creator_image("banners", "fanbox", "19469841")
                    self.assertEqual(first.media_type, "image/webp")
                    self.assertEqual(first.headers["x-pawchive-creator-cache"], "MISS")

                    # Simulate process restart by clearing in-memory favorite state
                    self._reset_creator_image_state()
                    second = router.get_creator_image("banners", "fanbox", "19469841")
                    self.assertEqual(second.body, raw_webp)
                    self.assertEqual(second.media_type, "image/webp")
                    self.assertEqual(second.headers["x-pawchive-creator-cache"], "HIT")

                    # 404 is negative-cached for favorited creators
                    with self.assertRaises(Exception) as missing_first:
                        router.get_creator_image("icons", "fanbox", "19469841")
                    self.assertEqual(missing_first.exception.status_code, 404)

                    with self.assertRaises(Exception) as missing_second:
                        router.get_creator_image("icons", "fanbox", "19469841")
                    self.assertEqual(missing_second.exception.status_code, 404)

                self.assertEqual(request.call_count, 2)

                # Non-favorite creator is NOT saved to disk
                with patch.object(
                    client,
                    "_request",
                    side_effect=lambda *a, **kw: (Connection(), Response(body=raw_webp, mime="image/webp")),
                ) as non_fav_req:
                    res1 = router.get_creator_image("banners", "patreon", "99999")
                    res2 = router.get_creator_image("banners", "patreon", "99999")
                self.assertEqual(res1.headers["x-pawchive-creator-cache"], "MISS")
                self.assertEqual(res2.headers["x-pawchive-creator-cache"], "MISS")
                self.assertEqual(non_fav_req.call_count, 2)

    def test_favorite_sync_prefetches_artwork_and_removes_unfavorited(self):
        png_bytes = io.BytesIO()
        Image.new("RGB", (4, 4), "red").save(png_bytes, format="PNG")
        raw_png = png_bytes.getvalue()

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / ".mounted").touch()
            artwork_root = root / ".he-manager" / "pawchive-creators" / "artwork"
            self._reset_creator_image_state()
            with patch.object(creator_images, "MOUNT_ROOT", root),                     patch.object(creator_images, "ARTWORK_ROOT", artwork_root),                     patch.object(creator_images, "PREFETCH_INTERVAL", 0):
                with patch.object(
                    client,
                    "_request",
                    side_effect=[
                        (Connection(), Response(body=raw_png, mime="application/octet-stream")),
                        (Connection(), Response(body=raw_png, mime="image/png")),
                    ],
                ) as request:
                    creator_images.sync_favorites("account:5", [{"service": "patreon", "creator_id": "456"}])
                    worker = creator_images._worker
                    if worker is not None:
                        worker.join(timeout=5)
                    self.assertEqual(request.call_count, 2)

                self.assertTrue((artwork_root / "icons" / "patreon" / "456.img").is_file())
                self.assertTrue((artwork_root / "banners" / "patreon" / "456.img").is_file())

                # Subsequent sync skips already cached artwork with 0 upstream calls
                with patch.object(client, "_request") as second_req:
                    creator_images.sync_favorites("account:5", [{"service": "patreon", "creator_id": "456"}])
                    worker = creator_images._worker
                    if worker is not None:
                        worker.join(timeout=5)
                    second_req.assert_not_called()

                # Unfavoriting cleans up cached artwork when no scope retains it
                creator_images.mark_favorite("account:5", "patreon", "456", False)
                self.assertFalse((artwork_root / "icons" / "patreon" / "456.img").exists())
                self.assertFalse((artwork_root / "banners" / "patreon" / "456.img").exists())
