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
from app.services.external.pawchive import client, downloader, media_fetch, normalize, refs, sources
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
