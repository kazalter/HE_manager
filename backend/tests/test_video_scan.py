"""Exercise the real scanner/decoder contract using disposable media and SQLite."""
from contextlib import ExitStack
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import cv2
import numpy as np
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.scanners import runner


class VideoScanTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.library = self.root / "library with spaces"
        self.library.mkdir()
        self.video = self.library / "sample.avi"
        writer = cv2.VideoWriter(
            str(self.video), cv2.VideoWriter_fourcc(*"MJPG"), 10, (160, 96),
        )
        self.assertTrue(writer.isOpened(), "OpenCV MJPEG encoder is required")
        try:
            frame = np.random.default_rng(42).integers(0, 256, (96, 160, 3), dtype=np.uint8)
            for _ in range(80):
                writer.write(frame)
        finally:
            writer.release()

        self.engine = create_engine(f"sqlite:///{self.root / 'test.db'}")
        self.addCleanup(self.engine.dispose)
        models.Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.addCleanup(self.db.close)
        self.folder = models.Folder(
            path=str(self.library), scan_mode="video",
            thumbnail_enabled=True, thumbnail_interval=3,
        )
        self.db.add(self.folder)
        self.db.commit()
        self.folder_id = self.folder.id

        self.patches = ExitStack()
        self.addCleanup(self.patches.close)
        self.patches.enter_context(mock.patch.object(runner.database, "SessionLocal", self.Session))
        self.patches.enter_context(mock.patch.object(runner.os, "getcwd", return_value=str(self.root)))
        self.enqueue = self.patches.enter_context(mock.patch.object(runner.dedup_worker, "enqueue"))
        self.patches.enter_context(mock.patch("app.services.assistant_runtime_logs.emit_event"))

    def scan(self):
        self.assertTrue(runner.scan_folder(self.folder_id))
        self.db.expire_all()
        folder = self.db.get(models.Folder, self.folder_id)
        self.assertEqual(folder.status, "idle")
        self.assertIsNotNone(folder.last_scanned_at)
        return self.db.query(models.Media).filter_by(media_type="video").one()

    def assert_cover(self, media):
        self.assertIsNotNone(media.cover_path)
        with Image.open(self.root / ".thumbnails" / media.cover_path) as image:
            self.assertEqual(image.size, (160, 96))
        self.assertGreaterEqual(media.cover_time_ms, 0)
        self.assertTrue(media.cover_source)

    def assert_preview(self, media):
        # The web player derives the VTT URL directly from cover_path.
        vtt = (self.root / ".thumbnails" / media.cover_path).with_suffix(".vtt")
        content = vtt.read_text(encoding="utf-8")
        self.assertTrue(content.startswith("WEBVTT"))
        self.assertIn("00:00:00.000 --> 00:00:03.000", content)
        self.assertIn("00:00:03.000 --> 00:00:06.000", content)
        images = [line.split("#xywh=")[0] for line in content.splitlines() if "#xywh=" in line]
        self.assertEqual(len(images), 2)
        for name in images:
            self.assertEqual(Path(name).name, name)
            with Image.open(vtt.parent / name) as sheet:
                self.assertGreater(sheet.width, 0)

    def test_video_scan_persists_media_cover_and_player_preview(self):
        media = self.scan()
        self.assertEqual(media.duration, 8)
        self.assertEqual((media.width, media.height), (160, 96))
        self.assertEqual(media.file_size, self.video.stat().st_size)
        self.assertFalse(media.is_missing)
        self.assert_cover(media)
        self.assert_preview(media)
        self.enqueue.assert_called_once_with([media.id])

        media_id = media.id
        cover_path = media.cover_path
        self.assertEqual(self.scan().id, media_id)
        self.assertEqual(self.db.query(models.Media).count(), 1)
        self.assertEqual(media.cover_path, cover_path)
        self.enqueue.assert_called_once()

    def test_auto_scan_imports_video_and_other_media(self):
        self.folder.scan_mode = "auto"
        self.db.commit()
        Image.new("RGB", (20, 30), color="blue").save(self.library / "photo.png")
        media = self.scan()
        self.assert_cover(media)
        self.assert_preview(media)
        self.assertEqual(self.db.query(models.Media).count(), 2)
        self.assertEqual(self.db.query(models.Media).filter_by(media_type="image").count(), 1)

    def test_disabling_timeline_preview_keeps_video_and_cover(self):
        self.folder.thumbnail_enabled = False
        self.db.commit()
        with mock.patch.object(runner, "generate_sprite_vtt") as generate:
            media = self.scan()
        self.assert_cover(media)
        self.assertEqual(list((self.root / ".thumbnails").glob("*.vtt")), [])
        generate.assert_not_called()

    def test_undecodable_video_is_imported_without_a_false_cover(self):
        self.video.write_bytes(b"not a decodable video")
        media = self.scan()
        self.assertIsNone(media.cover_path)
        self.assertIsNone(media.cover_time_ms)
        self.assertIsNone(media.cover_source)
        self.assertIsNone(media.duration)
        self.assertEqual(media.file_size, self.video.stat().st_size)

    def test_failed_cover_result_does_not_discard_video(self):
        with mock.patch.object(runner, "get_video_thumbnail", return_value=(False, 0, "failed")):
            media = self.scan()
        self.assertIsNone(media.cover_path)
        self.assertIsNone(media.cover_source)
        self.assertEqual(media.duration, 8)

    def test_cover_exception_does_not_discard_video(self):
        with mock.patch.object(runner, "get_video_thumbnail", side_effect=OSError("cover disk full")):
            media = self.scan()
        self.assertIsNone(media.cover_path)
        self.assertEqual(media.duration, 8)

    def test_preview_failure_does_not_discard_video_or_cover(self):
        with mock.patch.object(runner, "generate_sprite_vtt", side_effect=OSError("preview disk full")):
            media = self.scan()
        self.assert_cover(media)
        self.assertEqual(media.duration, 8)


if __name__ == "__main__":
    unittest.main()
