import os
import tempfile
import unittest
import zipfile
from datetime import datetime

from PIL import Image
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from fastapi import HTTPException

from app import media_cleanup, models, scanner, schemas
from app.dedup import classify as dedup_classify
from app.dedup import fingerprint as dedup_fingerprint
from app.dedup import merge as dedup_merge
from app.routers import dedup as dedup_routes


class MediaCoreTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        event.listen(self.engine, "connect", self._enable_foreign_keys)
        models.Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

    @staticmethod
    def _enable_foreign_keys(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    def test_media_metadata_and_tags_are_persisted(self):
        db = self.Session()
        try:
            folder = models.Folder(path="D:\\Library", scan_mode="auto")
            media = models.Media(
                folder=folder,
                title="chapter.cbz",
                relative_path="chapter.cbz",
                absolute_path="D:\\Library\\chapter.cbz",
                media_type="manga",
                extension=".cbz",
                file_size=1024,
                page_count=24,
                rating=4,
                favorite=True,
                view_status="viewing",
                progress=3,
                last_opened_at=datetime.utcnow(),
                source_site="example",
                source_url="https://example.test/item/1",
            )
            media.tags.append(models.Tag(name="作者A"))
            media.tags.append(models.Tag(name="已整理"))
            db.add(folder)
            db.commit()

            saved = db.query(models.Media).one()
            self.assertEqual(saved.page_count, 24)
            self.assertEqual(saved.rating, 4)
            self.assertTrue(saved.favorite)
            self.assertEqual(saved.view_status, "viewing")
            self.assertEqual(saved.progress, 3)
            self.assertEqual({tag.name for tag in saved.tags}, {"作者A", "已整理"})
        finally:
            db.close()

    def test_image_metadata_reads_dimensions(self):
        with tempfile.TemporaryDirectory() as tmp:
            image_path = os.path.join(tmp, "cover.jpg")
            Image.new("RGB", (320, 480), color=(20, 40, 60)).save(image_path)

            metadata = scanner.get_image_metadata(image_path)

            self.assertEqual(metadata["width"], 320)
            self.assertEqual(metadata["height"], 480)

    def test_manga_page_count_supports_directory_and_cbz(self):
        with tempfile.TemporaryDirectory() as tmp:
            Image.new("RGB", (10, 10)).save(os.path.join(tmp, "001.jpg"))
            Image.new("RGB", (10, 10)).save(os.path.join(tmp, "002.png"))
            os.makedirs(os.path.join(tmp, ".he_cover"))
            Image.new("RGB", (10, 10)).save(os.path.join(tmp, ".he_cover", "cover.jpg"))
            with open(os.path.join(tmp, "notes.txt"), "w", encoding="utf-8") as f:
                f.write("not a page")

            self.assertEqual(scanner.count_manga_pages(tmp, ".dir"), 2)

            cbz_path = os.path.join(tmp, "book.cbz")
            with zipfile.ZipFile(cbz_path, "w") as archive:
                archive.write(os.path.join(tmp, "001.jpg"), "001.jpg")
                archive.write(os.path.join(tmp, "002.png"), "002.png")
                archive.write(os.path.join(tmp, "notes.txt"), "notes.txt")

            self.assertEqual(scanner.count_manga_pages(cbz_path, ".cbz"), 2)

    def test_video_progress_can_drive_view_status(self):
        db = self.Session()
        try:
            folder = models.Folder(path="D:\\Videos", scan_mode="video")
            media = models.Media(
                folder=folder,
                title="clip.mp4",
                relative_path="clip.mp4",
                absolute_path="D:\\Videos\\clip.mp4",
                media_type="video",
                extension=".mp4",
                file_size=2048,
                duration=100,
                progress=0,
                view_status="unviewed",
            )
            db.add(folder)
            db.commit()

            saved = db.query(models.Media).one()
            saved.progress = 40
            ratio = saved.progress / saved.duration
            saved.view_status = "viewed" if ratio >= 0.95 else "viewing"
            db.commit()

            self.assertEqual(saved.view_status, "viewing")

            saved.progress = 96
            ratio = saved.progress / saved.duration
            saved.view_status = "viewed" if ratio >= 0.95 else "viewing"
            db.commit()

            self.assertEqual(saved.view_status, "viewed")
        finally:
            db.close()

    def test_folder_media_delete_detaches_cross_table_references(self):
        db = self.Session()
        try:
            folder = models.Folder(path="D:\\Imported", scan_mode="image")
            media_a = models.Media(
                folder=folder,
                title="a.jpg",
                relative_path="a.jpg",
                absolute_path="D:\\Imported\\a.jpg",
                media_type="image",
                extension=".jpg",
                file_size=100,
            )
            media_b = models.Media(
                folder=folder,
                title="b.jpg",
                relative_path="b.jpg",
                absolute_path="D:\\Imported\\b.jpg",
                media_type="image",
                extension=".jpg",
                file_size=100,
            )
            source = models.XImportSource(name="X")
            post = models.XPost(source=source, tweet_id="1", url="https://x.test/1")
            post.media_items.append(
                models.XMediaItem(
                    media_index=0,
                    media_type="photo",
                    remote_url="https://x.test/a.jpg",
                    status="downloaded",
                )
            )
            db.add_all([folder, source])
            db.commit()

            media_ids = [media_a.id, media_b.id]
            x_item = db.query(models.XMediaItem).one()
            x_item.library_media_id = media_a.id
            db.add(
                models.DuplicateCandidate(
                    existing_media_id=media_a.id,
                    candidate_media_id=media_b.id,
                    level="suspected_duplicate",
                    similarity=90,
                )
            )
            db.commit()

            db.delete(folder)
            with self.assertRaises(IntegrityError):
                db.commit()
            db.rollback()

            media_cleanup.detach_media_references(db, media_ids)
            db.delete(folder)
            db.commit()

            self.assertEqual(db.query(models.Media).count(), 0)
            self.assertIsNone(db.query(models.XMediaItem).one().library_media_id)
            self.assertEqual(db.query(models.DuplicateCandidate).count(), 0)
        finally:
            db.close()

    def test_dedup_merge_transfers_x_media_reference_to_surviving_media(self):
        db = self.Session()
        try:
            folder = models.Folder(path="D:\\Imported", scan_mode="image")
            existing = models.Media(
                folder=folder,
                title="keep.jpg",
                relative_path="keep.jpg",
                absolute_path="D:\\Imported\\keep.jpg",
                media_type="image",
                extension=".jpg",
                file_size=100,
            )
            candidate = models.Media(
                folder=folder,
                title="candidate.jpg",
                relative_path="candidate.jpg",
                absolute_path="D:\\Imported\\candidate.jpg",
                media_type="image",
                extension=".jpg",
                file_size=100,
            )
            source = models.XImportSource(name="X")
            post = models.XPost(source=source, tweet_id="1", url="https://x.test/1")
            x_item = models.XMediaItem(
                post=post,
                media_index=0,
                media_type="photo",
                remote_url="https://x.test/candidate.jpg",
                status="downloaded",
            )
            db.add_all([folder, source, existing, candidate, x_item])
            db.flush()
            x_item.library_media_id = candidate.id
            pair = models.DuplicateCandidate(
                existing_media_id=existing.id,
                candidate_media_id=candidate.id,
                level="suspected_duplicate",
                similarity=90,
            )
            db.add(pair)
            db.commit()

            dedup_merge.apply_action(db, pair, dedup_merge.ACTION_KEEP_EXISTING)

            self.assertEqual(db.query(models.Media).count(), 2)
            self.assertEqual(db.query(models.XMediaItem).one().library_media_id, existing.id)
            saved_candidate = db.query(models.Media).filter(models.Media.id == candidate.id).one()
            self.assertEqual(saved_candidate.duplicate_status, "dedup_excluded")
            self.assertEqual(pair.status, "merged")
            self.assertEqual(pair.candidate_media_id, candidate.id)
        finally:
            db.close()

    def test_dedup_replace_path_requires_missing_existing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            existing_path = os.path.join(tmp, "existing.jpg")
            candidate_path = os.path.join(tmp, "candidate.jpg")
            Image.new("RGB", (10, 10)).save(existing_path)
            Image.new("RGB", (10, 10)).save(candidate_path)

            db = self.Session()
            try:
                folder = models.Folder(path=tmp, scan_mode="image")
                existing = models.Media(
                    folder=folder,
                    title="existing.jpg",
                    relative_path="existing.jpg",
                    absolute_path=existing_path,
                    media_type="image",
                    extension=".jpg",
                    file_size=100,
                )
                candidate = models.Media(
                    folder=folder,
                    title="candidate.jpg",
                    relative_path="candidate.jpg",
                    absolute_path=candidate_path,
                    media_type="image",
                    extension=".jpg",
                    file_size=100,
                )
                pair = models.DuplicateCandidate(
                    existing_media_id=1,
                    candidate_media_id=2,
                    level="strong_duplicate",
                    similarity=99,
                )
                db.add_all([folder, existing, candidate])
                db.flush()
                pair.existing_media_id = existing.id
                pair.candidate_media_id = candidate.id
                db.add(pair)
                db.commit()

                with self.assertRaisesRegex(ValueError, "已有文件丢失"):
                    dedup_merge.apply_action(db, pair, dedup_merge.ACTION_REPLACE_PATH)

                self.assertEqual(existing.absolute_path, existing_path)
                self.assertEqual(pair.status, "pending")
            finally:
                db.close()

    def test_dedup_delete_rejects_path_outside_library_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            library_root = os.path.join(tmp, "library")
            os.makedirs(library_root)
            outside_path = os.path.join(tmp, "outside.jpg")
            Image.new("RGB", (10, 10)).save(outside_path)

            db = self.Session()
            try:
                folder = models.Folder(path=library_root, scan_mode="image")
                media = models.Media(
                    folder=folder,
                    title="outside.jpg",
                    relative_path="../outside.jpg",
                    absolute_path=outside_path,
                    media_type="image",
                    extension=".jpg",
                    file_size=os.path.getsize(outside_path),
                )
                db.add(folder)
                db.commit()

                with self.assertRaises(HTTPException) as ctx:
                    dedup_routes.delete_media_file(
                        media.id,
                        schemas.DedupDeleteFileRequest(confirm=True),
                        db,
                    )
                self.assertEqual(ctx.exception.status_code, 409)
                self.assertTrue(os.path.exists(outside_path))
            finally:
                db.close()

    def test_audio_fingerprint_and_classification(self):
        with tempfile.TemporaryDirectory() as tmp:
            left_path = os.path.join(tmp, "left.mp3")
            right_path = os.path.join(tmp, "right.mp3")
            payload = (b"ID3" + bytes(range(256))) * 1024
            with open(left_path, "wb") as fp:
                fp.write(payload)
            with open(right_path, "wb") as fp:
                fp.write(payload)

            left = models.Media(
                title="left.mp3",
                relative_path="left.mp3",
                absolute_path=left_path,
                media_type="audio",
                extension=".mp3",
                file_size=len(payload),
            )
            right = models.Media(
                title="right.mp3",
                relative_path="right.mp3",
                absolute_path=right_path,
                media_type="audio",
                extension=".mp3",
                file_size=len(payload),
            )
            left_fp = dedup_fingerprint.fingerprint_for_media(left)
            right_fp = dedup_fingerprint.fingerprint_for_media(right)
            self.assertIsNotNone(left_fp)
            self.assertIsNotNone(right_fp)

            level, similarity, reasons = dedup_classify.classify(
                dedup_classify.FingerprintLite(**{
                    key: getattr(left_fp, key)
                    for key in dedup_classify.FingerprintLite.__dataclass_fields__
                }),
                dedup_classify.FingerprintLite(**{
                    key: getattr(right_fp, key)
                    for key in dedup_classify.FingerprintLite.__dataclass_fields__
                }),
            )
            self.assertEqual(level, dedup_classify.LEVEL_STRONG)
            self.assertEqual(similarity, 95)
            self.assertTrue(reasons)

    def test_dedup_page_filters_before_limit_and_batch_resolves(self):
        db = self.Session()
        try:
            folder = models.Folder(path="D:\\Library", scan_mode="auto")
            media_rows = []
            for index, media_type in enumerate(("video", "video", "image", "image"), start=1):
                media_rows.append(models.Media(
                    folder=folder,
                    title=f"item-{index}",
                    relative_path=f"item-{index}",
                    absolute_path=f"D:\\Library\\item-{index}",
                    media_type=media_type,
                    extension=".mp4" if media_type == "video" else ".jpg",
                    file_size=100 + index,
                ))
            db.add(folder)
            db.flush()
            video_pair = models.DuplicateCandidate(
                existing_media_id=media_rows[0].id,
                candidate_media_id=media_rows[1].id,
                level="strong_duplicate",
                similarity=99,
            )
            image_pair = models.DuplicateCandidate(
                existing_media_id=media_rows[2].id,
                candidate_media_id=media_rows[3].id,
                level="suspected_duplicate",
                similarity=75,
            )
            db.add_all([video_pair, image_pair])
            db.commit()

            page = dedup_routes.paged_duplicate_candidates(
                media_type="image",
                limit=1,
                offset=0,
                db=db,
            )
            self.assertEqual(page["total"], 1)
            self.assertEqual(len(page["items"]), 1)
            self.assertEqual(page["items"][0]["id"], image_pair.id)

            result = dedup_routes.batch_resolve_duplicate_candidates(
                schemas.DedupBatchActionRequest(
                    pair_ids=[video_pair.id, image_pair.id],
                    action="keep_both",
                ),
                db,
            )
            self.assertEqual(result, {"processed": 2, "skipped": 0})
            self.assertEqual(
                db.query(models.DuplicateCandidate)
                .filter(models.DuplicateCandidate.status == "pending")
                .count(),
                0,
            )
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
