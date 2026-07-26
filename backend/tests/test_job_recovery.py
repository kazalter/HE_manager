import os
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.dedup import worker as dedup_worker
from app.services import job_lifecycle


class JobRecoveryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.engine = create_engine(
            f"sqlite:///{os.path.join(self.tmp.name, 'jobs.db')}",
            connect_args={"check_same_thread": False},
        )
        models.Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.session_patches = [
            patch.object(job_lifecycle.database, "SessionLocal", self.Session),
            patch.object(dedup_worker.database, "SessionLocal", self.Session),
        ]
        for item in self.session_patches:
            item.start()
        job_lifecycle.reset_for_tests()

    def tearDown(self):
        for item in reversed(self.session_patches):
            item.stop()
        job_lifecycle.reset_for_tests()
        self.engine.dispose()
        self.tmp.cleanup()

    def test_active_snapshot_becomes_interrupted_after_restart(self):
        job = {
            "job_id": "running-job",
            "status": "running",
            "total": 2,
            "message": "working",
        }
        job_lifecycle.record_job("test", job)

        self.assertEqual(job_lifecycle.recover_interrupted_jobs(), 1)
        snapshot = job_lifecycle.get_job_snapshot("test", "running-job")
        self.assertEqual(snapshot["status"], "interrupted")
        self.assertIn("重新发起", snapshot["message"])

    def test_terminal_history_and_memory_entries_are_bounded(self):
        now = datetime.utcnow()
        db = self.Session()
        try:
            db.add(models.BackgroundJob(
                job_id="expired",
                kind="test",
                status="completed",
                payload_json='{"job_id":"expired","status":"completed"}',
                created_at=now - timedelta(days=10),
                updated_at=now - timedelta(days=10),
                finished_at=now - timedelta(hours=job_lifecycle.JOB_TTL_HOURS + 1),
            ))
            db.commit()
        finally:
            db.close()
        self.assertEqual(job_lifecycle.cleanup_job_history(now=now), 1)
        self.assertIsNone(job_lifecycle.get_job_snapshot("test", "expired"))

        old_max = job_lifecycle.JOB_MAX_ENTRIES
        try:
            job_lifecycle.JOB_MAX_ENTRIES = 3
            registry = {
                str(index): {"job_id": str(index), "status": "completed"}
                for index in range(3)
            }
            with job_lifecycle._LOCK:
                for index in range(3):
                    job_lifecycle._MEMORY_TIMESTAMPS[("test", str(index))] = now - timedelta(minutes=3 - index)
            job_lifecycle.admit_new_job("test", registry, now=now)
            self.assertEqual(len(registry), 2)
            self.assertNotIn("0", registry)
        finally:
            job_lifecycle.JOB_MAX_ENTRIES = old_max

    def test_checking_media_is_requeued_and_errors_are_visible(self):
        db = self.Session()
        try:
            folder = models.Folder(path="/library", scan_mode="manga")
            media = models.Media(
                folder=folder,
                title="pending",
                relative_path="pending.cbz",
                absolute_path="/library/pending.cbz",
                media_type="manga",
                extension=".cbz",
                file_size=1,
                duplicate_status="checking",
            )
            db.add(folder)
            db.commit()
            media_id = media.id
        finally:
            db.close()

        with patch.object(dedup_worker, "enqueue", side_effect=lambda ids: len(list(ids))) as enqueue:
            self.assertEqual(dedup_worker.recover_checking_jobs(), 1)
            self.assertEqual(list(enqueue.call_args.args[0]), [media_id])

        dedup_worker._mark_processing_error(media_id, RuntimeError("boom"))
        db = self.Session()
        try:
            self.assertEqual(db.get(models.Media, media_id).duplicate_status, "dedup_error")
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
