import os
import tempfile
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app import creators, database, migrations, models
from app.routers import audio as audio_routes
from app.routers import media as media_routes


class DbAndCreatorsPerfTest(unittest.TestCase):
    def test_sqlite_pragmas_and_migration_indexes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            test_engine = create_engine(
                f"sqlite:///{db_path}",
                connect_args={"check_same_thread": False},
            )
            event.listen(test_engine, "connect", database.set_sqlite_pragma)
            models.Base.metadata.create_all(bind=test_engine)

            with patch.object(migrations, "engine", test_engine):
                migrations.ensure_media_indexes()
                migrations.ensure_dedup_indexes()
                # Verify idempotency when run a second time.
                migrations.ensure_media_indexes()
                migrations.ensure_dedup_indexes()

            with test_engine.connect() as conn:
                cache_size = conn.execute(text("PRAGMA cache_size")).scalar()
                temp_store = conn.execute(text("PRAGMA temp_store")).scalar()
                mmap_size = conn.execute(text("PRAGMA mmap_size")).scalar()
                self.assertEqual(cache_size, -32768)
                self.assertEqual(temp_store, 2)
                self.assertGreaterEqual(mmap_size, 0)

                media_indexes = {
                    row[0]
                    for row in conn.execute(
                        text("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='media'")
                    ).fetchall()
                }
                self.assertTrue(
                    {"ix_media_last_opened_at", "ix_media_dup_type_id"}.issubset(media_indexes)
                )

                fp_indexes = {
                    row[0]
                    for row in conn.execute(
                        text(
                            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='media_fingerprints'"
                        )
                    ).fetchall()
                }
                self.assertTrue(
                    {
                        "ix_media_fingerprints_hash_first",
                        "ix_media_fingerprints_hash_middle",
                        "ix_media_fingerprints_hash_last",
                    }.issubset(fp_indexes)
                )

            test_engine.dispose()

    def test_creator_detail_queries_only_target_creator(self):
        engine = create_engine("sqlite:///:memory:")
        models.Base.metadata.create_all(bind=engine)
        Session = sessionmaker(bind=engine)
        db = Session()
        try:
            folder = models.Folder(path="/tmp/lib", scan_mode="auto")
            db.add(folder)
            db.flush()

            manga_a = models.Media(
                folder_id=folder.id,
                title="[Alice] Book 1",
                relative_path="a1.cbz",
                absolute_path="/tmp/lib/a1.cbz",
                media_type="manga",
                extension=".cbz",
                file_size=100,
                artist="Alice",
                cover_path="alice.jpg",
                duplicate_status="unique",
            )
            manga_b = models.Media(
                folder_id=folder.id,
                title="[Bob] Book 2",
                relative_path="b1.cbz",
                absolute_path="/tmp/lib/b1.cbz",
                media_type="manga",
                extension=".cbz",
                file_size=100,
                artist="Bob",
                cover_path="bob.jpg",
                duplicate_status="unique",
            )
            x_img_1 = models.Media(
                folder_id=folder.id,
                title="X1",
                relative_path="x1.jpg",
                absolute_path="/tmp/lib/x1.jpg",
                media_type="image",
                extension=".jpg",
                file_size=50,
                cover_path="x1.jpg",
                duplicate_status="unique",
            )
            x_img_2 = models.Media(
                folder_id=folder.id,
                title="X2",
                relative_path="x2.jpg",
                absolute_path="/tmp/lib/x2.jpg",
                media_type="image",
                extension=".jpg",
                file_size=50,
                cover_path="x2.jpg",
                duplicate_status="unique",
            )
            db.add_all([manga_a, manga_b, x_img_1, x_img_2])
            db.flush()

            source = models.XImportSource(name="src", download_root_path="/tmp/x")
            db.add(source)
            db.flush()

            post_carol_1 = models.XPost(
                source_id=source.id,
                tweet_id="1",
                author_screen_name="carol",
                author_name="Carol Display",
                status="downloaded",
            )
            post_carol_2 = models.XPost(
                source_id=source.id,
                tweet_id="2",
                author_screen_name="carol",
                author_name="Carol Display",
                status="pending",
            )
            post_dave = models.XPost(
                source_id=source.id,
                tweet_id="3",
                author_screen_name="dave",
                author_name="Dave Display",
                status="downloaded",
            )
            db.add_all([post_carol_1, post_carol_2, post_dave])
            db.flush()

            db.add_all([
                models.XMediaItem(
                    post_id=post_carol_1.id,
                    media_index=0,
                    media_type="photo",
                    remote_url="https://example.test/1.jpg",
                    library_media_id=x_img_1.id,
                    status="downloaded",
                ),
                models.XMediaItem(
                    post_id=post_dave.id,
                    media_index=0,
                    media_type="photo",
                    remote_url="https://example.test/2.jpg",
                    library_media_id=x_img_2.id,
                    status="downloaded",
                ),
            ])
            db.commit()

            with patch.object(creators, "_artist_covers", side_effect=AssertionError("should not scan all artists")):
                artist_detail = creators.creator_detail(db, "a:Alice")
            self.assertIsNotNone(artist_detail)
            self.assertEqual(artist_detail["creator"]["cover_path"], "alice.jpg")
            self.assertEqual(artist_detail["creator"]["media_count"], 1)

            x_detail = creators.creator_detail(db, "x:carol")
            self.assertIsNotNone(x_detail)
            self.assertEqual(x_detail["creator"]["display_name"], "Carol Display")
            self.assertEqual(x_detail["creator"]["posts_known"], 2)
            self.assertEqual(x_detail["creator"]["posts_pending"], 1)
            self.assertEqual(x_detail["creator"]["cover_path"], "x1.jpg")
            self.assertEqual(len(x_detail["media"]), 1)

            # Targeted helper calls should return only the requested screen_name.
            self.assertEqual(creators._display_names(db, screen_name="carol"), {"carol": "Carol Display"})
            self.assertEqual(creators._posts_known(db, screen_name="carol"), {"carol": 2})
            self.assertEqual(creators._posts_in_library(db, screen_name="carol"), {"carol": 1})
        finally:
            db.close()
            engine.dispose()

    def test_streaming_and_audio_routes_release_db_before_io(self):
        engine = create_engine("sqlite:///:memory:")
        models.Base.metadata.create_all(bind=engine)
        Session = sessionmaker(bind=engine)
        db = Session()
        with tempfile.TemporaryDirectory() as tmpdir:
            video_path = os.path.join(tmpdir, "clip.mp4")
            audio_path = os.path.join(tmpdir, "track.mp3")
            with open(video_path, "wb") as f:
                f.write(b"video-bytes")
            with open(audio_path, "wb") as f:
                f.write(b"audio-bytes")

            folder = models.Folder(path=tmpdir, scan_mode="auto")
            db.add(folder)
            db.flush()
            video = models.Media(
                folder_id=folder.id,
                title="clip",
                relative_path="clip.mp4",
                absolute_path=video_path,
                media_type="video",
                extension=".mp4",
                file_size=11,
            )
            audio = models.Media(
                folder_id=folder.id,
                title="track",
                relative_path="track.mp3",
                absolute_path=audio_path,
                media_type="audio",
                extension=".mp3",
                file_size=11,
            )
            db.add_all([video, audio])
            db.commit()
            db.refresh(video)
            db.refresh(audio)

            req = Request({"type": "http", "method": "GET", "path": "/stream/1", "headers": []})
            with patch.object(db, "rollback", wraps=db.rollback) as rollback_spy:
                resp = media_routes.stream_media(req, video.id, db=db)
                self.assertEqual(resp.status_code, 200)
                self.assertEqual(rollback_spy.call_count, 1)

                resp_mob = media_routes.stream_mobile_media(req, video.id, _=None, db=db)
                self.assertEqual(resp_mob.status_code, 200)
                self.assertEqual(rollback_spy.call_count, 2)

                tracks_payload = audio_routes.get_audio_tracks(audio.id, db=db)
                self.assertEqual(len(tracks_payload["tracks"]), 1)
                self.assertEqual(rollback_spy.call_count, 3)

                audio_resp = audio_routes.stream_audio_track(audio.id, 1, req, db=db)
                self.assertEqual(audio_resp.status_code, 200)
                self.assertEqual(rollback_spy.call_count, 4)

        db.close()
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
