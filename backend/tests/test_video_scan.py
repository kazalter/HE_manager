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


    def test_video_metadata_uses_ffprobe_fallback_when_cv2_misses_fields(self):
        from app.scanners import video as video_scanner

        fake_cap = mock.MagicMock()
        fake_cap.get.return_value = 0
        fake_proc = mock.Mock(
            returncode=0,
            stdout='{"streams": [{"width": 1080, "height": 1920, "duration": "12.4", "tags": {"rotate": "90"}}], "format": {"duration": "12.4"}}',
        )
        with mock.patch.object(video_scanner.cv2, "VideoCapture", return_value=fake_cap),              mock.patch.object(video_scanner.subprocess, "run", return_value=fake_proc):
            meta = video_scanner.get_video_metadata(str(self.video))
        self.assertEqual(meta, {"width": 1920, "height": 1080, "duration": 12})

    def test_rescan_and_backfill_and_x_storage_populate_video_metadata(self):
        from fastapi import Response
        from app.routers import media as media_routes, system as system_routes
        from app.x_import import storage as x_storage

        # 1. Rescan repairs existing video missing dimensions & duration
        media = self.scan()
        media.width = None
        media.height = None
        media.duration = None
        self.db.commit()
        self.scan()
        self.db.expire_all()
        repaired = self.db.get(models.Media, media.id)
        self.assertEqual((repaired.width, repaired.height, repaired.duration), (160, 96, 8))

        # 2. list_media lazily repairs video metadata
        repaired.width = None
        repaired.height = None
        repaired.duration = None
        self.db.commit()
        items = media_routes.list_media(Response(), media_type="video", db=self.db)
        self.assertEqual((items[0].width, items[0].height, items[0].duration), (160, 96, 8))

        # 3. system backfill repairs video metadata
        items[0].width = None
        items[0].height = None
        items[0].duration = None
        self.db.commit()
        res = system_routes.backfill_missing_video_metadata(self.db)
        self.assertEqual(res["updated"], 1)
        self.db.expire_all()
        self.assertEqual((self.db.get(models.Media, media.id).width, self.db.get(models.Media, media.id).duration), (160, 8))

        # 4. x_import storage populates video metadata for new imports
        src_row = models.XImportSource(name="tester")
        self.db.add(src_row)
        self.db.flush()
        post = models.XPost(source_id=src_row.id, tweet_id="999", url="https://x.com/t/999", author_screen_name="tester")
        self.db.add(post)
        self.db.flush()
        x_item = models.XMediaItem(post_id=post.id, media_index=0, media_type="video", remote_url="https://v.mp4")
        self.db.add(x_item)
        self.db.flush()

        other_video = self.library / "x_clip.avi"
        other_video.write_bytes(self.video.read_bytes())
        thumb_dir = self.root / ".thumbnails"
        thumb_dir.mkdir(exist_ok=True)
        imported = x_storage.upsert_library_media(
            x_item, post, self.folder, str(other_video), other_video.stat().st_size, str(thumb_dir), self.db
        )
        self.assertEqual((imported.width, imported.height, imported.duration), (160, 96, 8))


if __name__ == "__main__":
    unittest.main()
