import os
import queue
import shutil
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.dedup import worker
from app.dedup import merge
from app.routers import dedup
from app.scanners.common import apply_local_dedup_precheck


class DedupDetectionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.engine = create_engine(f"sqlite:///{self.tmp.name}/test.db")
        models.Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.session_patch = patch.object(worker.database, "SessionLocal", self.Session)
        self.session_patch.start()
        self.db = self.Session()
        self.folder = models.Folder(path=self.tmp.name, scan_mode="image")
        self.db.add(self.folder)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.session_patch.stop()
        self.engine.dispose()
        self.tmp.cleanup()

    def image(self, name, title=None, status="unique", color="red"):
        path = os.path.join(self.tmp.name, name)
        Image.new("RGB", (32, 24), color=color).save(path)
        media = models.Media(
            folder_id=self.folder.id, title=title or name,
            normalized_title=title or name, absolute_path=path, relative_path=name,
            media_type="image", extension=".png", file_size=os.path.getsize(path),
            duplicate_status=status,
        )
        self.db.add(media)
        self.db.commit()
        return media.id

    def test_renamed_identical_images_are_detected_and_recheck_is_idempotent(self):
        left = self.image("original.png")
        right = self.image("renamed.png")
        shutil.copyfile(self.db.get(models.Media, left).absolute_path,
                        self.db.get(models.Media, right).absolute_path)
        for media_id in (left, right, left, right):
            worker._process_one(media_id)
        self.db.expire_all()
        pairs = self.db.query(models.DuplicateCandidate).all()
        self.assertEqual(len(pairs), 1)
        self.assertEqual((pairs[0].existing_media_id, pairs[0].candidate_media_id), (left, right))
        self.assertEqual(pairs[0].level, "strong_duplicate")
        self.assertEqual(self.db.get(models.Media, left).duplicate_status, "unique")
        self.assertEqual(self.db.get(models.Media, right).duplicate_status, "strong_duplicate")

    def test_manual_not_duplicate_decision_survives_rechecks_from_either_side(self):
        left = self.image("left.png", title="same")
        right = self.image("right.png", title="same")
        self.db.add(models.DuplicateCandidate(
            existing_media_id=left, candidate_media_id=right, level="strong_duplicate",
            similarity=99, status="kept_both",
        ))
        self.db.commit()
        worker._process_one(left)
        worker._process_one(right)
        self.db.expire_all()
        self.assertEqual(self.db.query(models.DuplicateCandidate).count(), 1)
        self.assertEqual(self.db.get(models.Media, left).duplicate_status, "unique")
        self.assertEqual(self.db.get(models.Media, right).duplicate_status, "unique")

    def test_legacy_reversed_pending_pair_cannot_override_a_manual_decision(self):
        left = self.image("left.png", title="same")
        right = self.image("right.png", title="same")
        self.db.add_all([
            models.DuplicateCandidate(existing_media_id=left, candidate_media_id=right,
                                      level="strong_duplicate", similarity=99, status="pending"),
            models.DuplicateCandidate(existing_media_id=right, candidate_media_id=left,
                                      level="strong_duplicate", similarity=99, status="kept_both"),
        ])
        self.db.commit()
        worker._process_one(left)
        worker._process_one(right)
        self.db.expire_all()
        self.assertEqual(self.db.query(models.DuplicateCandidate).filter_by(status="pending").count(), 0)
        self.assertEqual(self.db.query(models.DuplicateCandidate).filter_by(status="kept_both").count(), 1)
        self.assertEqual(self.db.get(models.Media, left).duplicate_status, "unique")
        self.assertEqual(self.db.get(models.Media, right).duplicate_status, "unique")

    def test_changed_content_retires_old_pending_pair(self):
        left = self.image("left.png", title="same")
        right = self.image("right.png", title="same", color="blue")
        self.db.add(models.DuplicateCandidate(
            existing_media_id=left, candidate_media_id=right, level="strong_duplicate",
            similarity=99, status="pending",
        ))
        self.db.commit()
        # Different title and content should remove the old duplicate warning.
        self.db.get(models.Media, right).title = "different"
        self.db.get(models.Media, right).normalized_title = "different"
        self.db.commit()
        worker._process_one(left)
        worker._process_one(right)
        self.db.expire_all()
        self.assertEqual(self.db.query(models.DuplicateCandidate).filter_by(status="pending").count(), 0)
        self.assertEqual(self.db.get(models.Media, right).duplicate_status, "unique")

    def test_unreadable_media_is_reported_as_failure(self):
        media_id = self.image("missing.png", status="checking")
        os.unlink(self.db.get(models.Media, media_id).absolute_path)
        worker._process_one(media_id)
        self.db.expire_all()
        self.assertEqual(self.db.get(models.Media, media_id).duplicate_status, "dedup_error")

    def test_new_unique_title_is_also_queued_for_fingerprinting(self):
        media_id = self.image("new.png")
        media = self.db.get(models.Media, media_id)
        pending = []
        apply_local_dedup_precheck(media, set(), pending)
        self.assertEqual(pending, [media.absolute_path])
        self.assertEqual(media.duplicate_status, "dedup_pending")

    def test_comparing_a_queued_counterpart_preserves_its_restart_recovery(self):
        left = self.image("left.png", title="same", status="dedup_pending")
        right = self.image("right.png", title="same", status="dedup_pending")
        worker._process_one(left)
        self.db.expire_all()
        self.assertEqual(self.db.get(models.Media, right).duplicate_status, "dedup_pending")
        with patch.object(worker, "enqueue", side_effect=lambda ids: len(list(ids))) as enqueue:
            self.assertEqual(worker.recover_checking_jobs(), 1)
            self.assertEqual(list(enqueue.call_args.args[0]), [right])

    def test_failed_empty_fingerprint_is_recomputed_on_retry(self):
        media_id = self.image("retry.png", status="dedup_error")
        media = self.db.get(models.Media, media_id)
        self.db.add(models.MediaFingerprint(
            media_id=media_id, media_type="image", file_size=media.file_size,
            source_path=media.absolute_path, source_mtime=int(os.path.getmtime(media.absolute_path)),
        ))
        self.db.commit()
        worker._process_one(media_id)
        self.db.expire_all()
        self.assertEqual(self.db.get(models.Media, media_id).duplicate_status, "unique")
        self.assertIsNotNone(self.db.query(models.MediaFingerprint).filter_by(media_id=media_id).one().hash_first)

    def test_manual_merge_during_detection_cannot_resurrect_the_hidden_file(self):
        left = self.image("left.png", title="same")
        right = self.image("right.png", title="same", status="checking")
        worker._process_one(right)
        original = worker._candidates_for

        def resolve_after_selection(db, media, record=None):
            candidates = original(db, media, record)
            with self.Session() as other:
                pair = other.query(models.DuplicateCandidate).one()
                merge.apply_action(other, pair, "keep_existing")
            return candidates

        with patch.object(worker, "_candidates_for", side_effect=resolve_after_selection):
            worker._process_one(right)
        self.db.expire_all()
        self.assertEqual(self.db.query(models.DuplicateCandidate).one().status, "merged")
        self.assertEqual(self.db.get(models.Media, right).duplicate_status, "dedup_excluded")

    def test_stale_hash_index_does_not_trigger_cross_title_metadata_match(self):
        left = self.image("left.bmp", title="old work")
        right = self.image("right.bmp", title="different work")
        worker._process_one(left)
        path = self.db.get(models.Media, left).absolute_path
        old_mtime = os.path.getmtime(path)
        Image.new("RGB", (32, 24), color="blue").save(path)
        os.utime(path, (old_mtime + 2, old_mtime + 2))
        worker._process_one(right)
        self.db.expire_all()
        self.assertEqual(self.db.query(models.DuplicateCandidate).filter_by(status="pending").count(), 0)
        self.assertEqual(self.db.get(models.Media, right).duplicate_status, "unique")

    def test_recheck_at_worker_completion_is_processed_instead_of_stranded(self):
        media_id = self.image("again.png", status="dedup_pending")

        class ImmediateQueue(queue.Queue):
            def get(self, block=True, timeout=None):
                return super().get(block=False)

        pending = ImmediateQueue()
        pending.put(media_id)
        original = worker._process_one
        processed = []

        def process_and_recheck(item_id):
            original(item_id)
            processed.append(item_id)
            if len(processed) == 1:
                with self.Session() as other:
                    dedup.recheck_media_dedup(item_id, db=other)

        with patch.object(worker, "_QUEUE", pending), \
             patch.object(worker, "_QUEUED_IDS", {media_id}), \
             patch.object(worker, "_WORKER_THREAD", None), \
             patch.object(worker, "_ensure_worker"), \
             patch.object(worker, "_process_one", side_effect=process_and_recheck):
            worker._run()
        self.db.expire_all()
        self.assertEqual(processed, [media_id, media_id])
        self.assertEqual(self.db.get(models.Media, media_id).duplicate_status, "unique")

    def test_full_recheck_keeps_library_visible_and_skips_excluded_missing_media(self):
        left = self.image("left.png")
        right = self.image("right.png")
        self.image("excluded.png", status="dedup_excluded")
        missing = self.image("missing.png")
        self.db.get(models.Media, missing).is_missing = True
        self.db.commit()
        with patch.object(worker, "enqueue", side_effect=lambda ids: len(list(ids))):
            result = dedup.recheck_library_dedup(db=self.db)
        self.assertEqual(result["queued"], 2)
        for media_id in (left, right):
            self.assertEqual(self.db.get(models.Media, media_id).duplicate_status, "dedup_pending")

    def test_summary_counts_pending_pairs_and_reports_coverage(self):
        left = self.image("left.png")
        right = self.image("right.png", status="unique")
        self.db.add(models.DuplicateCandidate(
            existing_media_id=left, candidate_media_id=right, level="strong_duplicate",
            similarity=99, status="pending",
        ))
        self.db.commit()
        result = dedup.dedup_summary(db=self.db)
        self.assertEqual(result["strong_duplicate"], 1)
        self.assertEqual(result["total_media"], 2)
        self.assertEqual(result["fingerprinted"], 0)
        self.assertEqual(result["unchecked"], 2)
