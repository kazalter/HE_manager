import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import BackgroundTasks
from PIL import Image

from app import database, models
from app.services.external.pawchive import client, downloader, normalize, provider

PATH = "/ab/cd/" + "a" * 64 + ".png"


class FakeConnection:
    def close(self):
        pass


class FakeResponse:
    status = 200

    def __init__(self, content):
        self.content = io.BytesIO(content)
        self.length = len(content)

    def getheader(self, name):
        return {"Content-Type": "image/png", "Content-Length": str(self.length)}.get(name)

    def read(self, size):
        return self.content.read(size)


class DownloadTests(unittest.TestCase):
    def test_rate_limit_stops_remaining_attachments(self):
        models.Base.metadata.create_all(database.engine)
        raw = {"id": "rate123", "user": "456", "service": "fanbox", "title": "Rate test",
               "file": {"name": "one.png", "path": PATH},
               "attachments": [{"name": "two.png", "path": "/ab/cd/" + "b" * 64 + ".png"}]}
        detail = normalize.normalize_post(raw, detail=True)
        selection = [{"service": "fanbox", "creator_id": "456", "post_id": "rate123"}]
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"HE_PAWCHIVE_DOWNLOAD_ROOT": directory}
        ):
            db = database.SessionLocal()
            try:
                with patch.object(provider, "post_detail", return_value=detail), patch.object(
                    client, "open_media", side_effect=client.PawchiveError("RATE_LIMITED", "请求过快", 429, "120")
                ) as opened:
                    created = downloader.create_download(selection, db, BackgroundTasks())
                    downloader.run_download_job(created["job_id"])
                db.expire_all()
                self.assertEqual(opened.call_count, 1)
                self.assertEqual([row.status for row in db.query(models.PawchiveAttachment).filter_by(
                    job_id=created["job_id"]
                ).order_by(models.PawchiveAttachment.original_index)], ["failed", "interrupted"])
                self.assertEqual(downloader.DOWNLOAD_JOBS[created["job_id"]]["retry_after"], "120")
            finally:
                db.close()

    def test_download_dedup_and_recover_existing_file(self):
        models.Base.metadata.create_all(database.engine)
        raw = {"id": "123", "user": "456", "service": "fanbox", "title": "Example",
               "file": {"name": "page.png", "path": PATH}, "attachments": []}
        detail = normalize.normalize_post(raw, detail=True)
        selection = [{"service": "fanbox", "creator_id": "456", "post_id": "123",
                      "attachment_keys": [detail["attachments"][0]["attachment_key"]]}]
        output = io.BytesIO()
        Image.new("RGB", (2, 2), color="red").save(output, format="PNG")
        content = output.getvalue()
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"HE_PAWCHIVE_DOWNLOAD_ROOT": directory}):
                db = database.SessionLocal()
                try:
                    with patch.object(provider, "post_detail", return_value=detail), patch.object(
                        client, "open_media", side_effect=lambda *args, **kwargs: (FakeConnection(), FakeResponse(content))
                    ) as opened:
                        result = downloader.create_download(selection, db, BackgroundTasks())
                        downloader.run_download_job(result["job_id"])
                        self.assertEqual(opened.call_count, 1)
                    db.expire_all()
                    self.assertEqual(db.query(models.Media).filter_by(source_site="pawchive").count(), 1)
                    attachment = db.query(models.PawchiveAttachment).one()
                    self.assertEqual(attachment.status, "completed")
                    self.assertTrue(Path(attachment.local_path).is_file())
                    with patch.object(provider, "post_detail", return_value=detail):
                        repeated = downloader.create_download(selection, db, BackgroundTasks())
                    self.assertEqual(repeated["status"], "already_downloaded")
                    self.assertEqual(db.query(models.Media).filter_by(source_site="pawchive").count(), 1)

                    # Simulate a crash after the atomic file move but before a
                    # durable Media association. The manifest verifies reuse.
                    media = db.get(models.Media, attachment.media_id)
                    db.delete(media)
                    attachment.status = "interrupted"
                    attachment.media_id = None
                    db.commit()
                    with patch.object(provider, "post_detail", return_value=detail), patch.object(
                        client, "open_media", side_effect=AssertionError("recovery must not redownload")
                    ):
                        retried = downloader.create_download(selection, db, BackgroundTasks())
                        downloader.run_download_job(retried["job_id"])
                    db.expire_all()
                    self.assertEqual(db.query(models.Media).filter_by(source_site="pawchive").count(), 1)
                    self.assertEqual(db.query(models.PawchiveAttachment).one().status, "completed")
                finally:
                    db.close()

    def test_missing_root_blocks_before_record_creation(self):
        models.Base.metadata.create_all(database.engine)
        db = database.SessionLocal()
        try:
            with patch.dict(os.environ, {"HE_PAWCHIVE_DOWNLOAD_ROOT": "/does-not-exist/pawchive"}):
                with self.assertRaises(client.PawchiveError):
                    downloader.create_download([{"service": "fanbox", "creator_id": "1", "post_id": "1"}], db, BackgroundTasks())
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
