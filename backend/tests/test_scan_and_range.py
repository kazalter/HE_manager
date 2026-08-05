import asyncio
import os
import tempfile
import unittest
from unittest import mock

from fastapi import BackgroundTasks, HTTPException
from starlette.requests import Request

from app import scanner
from app.routers import media as media_routes
from app.services.range_response import get_ranged_file_response


def make_request(range_header: str | None = None) -> Request:
    headers = []
    if range_header is not None:
        headers.append((b"range", range_header.encode("ascii")))
    return Request({"type": "http", "method": "GET", "path": "/stream/1", "headers": headers})


async def response_body(response) -> bytes:
    if hasattr(response, "body_iterator"):
        chunks = [chunk async for chunk in response.body_iterator]
        return b"".join(chunks)
    return response.body


class RangeResponseTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.file_path = os.path.join(self.temp_dir.name, "sample.mp4")
        with open(self.file_path, "wb") as file:
            file.write(b"0123456789")

    def tearDown(self):
        self.temp_dir.cleanup()

    def assert_range(self, header: str, expected_body: bytes, expected_content_range: str):
        response = get_ranged_file_response(make_request(header), self.file_path)
        self.assertEqual(response.status_code, 206)
        self.assertEqual(response.headers["accept-ranges"], "bytes")
        self.assertEqual(response.headers["content-range"], expected_content_range)
        self.assertEqual(response.headers["content-length"], str(len(expected_body)))
        self.assertEqual(asyncio.run(response_body(response)), expected_body)

    def test_full_response_without_range(self):
        response = get_ranged_file_response(make_request(), self.file_path)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-length"], "10")
        self.assertEqual(asyncio.run(response_body(response)), b"0123456789")

    def test_closed_open_and_suffix_ranges(self):
        self.assert_range("bytes=2-5", b"2345", "bytes 2-5/10")
        self.assert_range("bytes=6-", b"6789", "bytes 6-9/10")
        self.assert_range("bytes=-4", b"6789", "bytes 6-9/10")

    def test_end_and_oversized_suffix_are_clamped(self):
        self.assert_range("bytes=7-99", b"789", "bytes 7-9/10")
        self.assert_range("bytes=-99", b"0123456789", "bytes 0-9/10")

    def test_unsatisfiable_and_unsupported_ranges_return_416(self):
        for header in ("bytes=10-", "bytes=8-2", "bytes=-0", "bytes=", "items=0-1", "bytes=0-1,4-5"):
            with self.subTest(header=header):
                response = get_ranged_file_response(make_request(header), self.file_path)
                self.assertEqual(response.status_code, 416)
                self.assertEqual(response.headers["content-range"], "bytes */10")
                self.assertEqual(response.headers["content-length"], "0")
                self.assertEqual(asyncio.run(response_body(response)), b"")


class ScanConcurrencyTest(unittest.TestCase):
    def test_folder_scan_reservation_is_per_folder(self):
        first = scanner.reserve_folder_scan(41001)
        other = scanner.reserve_folder_scan(41002)
        self.assertIsNotNone(first)
        self.assertIsNotNone(other)
        try:
            self.assertIsNone(scanner.reserve_folder_scan(41001))
            self.assertIsNone(scanner.reserve_folder_scan(41002))
        finally:
            scanner.release_folder_scan(41001, first)
            scanner.release_folder_scan(41002, other)

        retry = scanner.reserve_folder_scan(41001)
        self.assertIsNotNone(retry)
        scanner.release_folder_scan(41001, retry)

    def test_duplicate_scan_queue_returns_conflict(self):
        token = scanner.reserve_folder_scan(42001)
        self.assertIsNotNone(token)
        try:
            with self.assertRaises(HTTPException) as context:
                media_routes._queue_folder_scan(42001, BackgroundTasks())
            self.assertEqual(context.exception.status_code, 409)
            self.assertIn("already queued or running", context.exception.detail)
        finally:
            scanner.release_folder_scan(42001, token)

    def test_scan_exception_before_folder_lookup_releases_reservation(self):
        session = mock.MagicMock()
        session.query.side_effect = RuntimeError("database unavailable")
        with mock.patch.object(scanner.database, "SessionLocal", return_value=session):
            self.assertFalse(scanner.scan_folder(43001))
        session.close.assert_called_once()

        retry = scanner.reserve_folder_scan(43001)
        self.assertIsNotNone(retry)
        scanner.release_folder_scan(43001, retry)

    def test_session_creation_failure_releases_reservation(self):
        with mock.patch.object(scanner.database, "SessionLocal", side_effect=RuntimeError("database unavailable")):
            self.assertFalse(scanner.scan_folder(43002))

        retry = scanner.reserve_folder_scan(43002)
        self.assertIsNotNone(retry)
        scanner.release_folder_scan(43002, retry)

    def test_thumbnail_and_vtt_share_preview_semaphore(self):
        class TrackingSemaphore:
            def __init__(self):
                self.entries = 0

            def __enter__(self):
                self.entries += 1
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                return False

        class ClosedCapture:
            def isOpened(self):
                return False

        semaphore = TrackingSemaphore()
        with (
            mock.patch.object(scanner, "VIDEO_PREVIEW_SEMAPHORE", semaphore),
            mock.patch.object(scanner.cv2, "VideoCapture", return_value=ClosedCapture()),
            mock.patch.object(scanner, "_generate_sprite_vtt", return_value=True) as generate,
        ):
            self.assertEqual(scanner.get_video_thumbnail("video.mp4", "thumb.jpg"), (False, 0, "error"))
            self.assertTrue(scanner.generate_sprite_vtt("video.mp4", "preview", ".", interval=3))

        self.assertEqual(semaphore.entries, 2)
        generate.assert_called_once_with("video.mp4", "preview", ".", 3)


if __name__ == "__main__":
    unittest.main()
