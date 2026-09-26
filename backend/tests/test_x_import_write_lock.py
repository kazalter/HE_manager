"""X downloads must leave SQLite writable while waiting on remote I/O and thumbnails."""

import sqlite3

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.x_import import client, importer, storage


def test_x_import_releases_writer_lock_during_download_and_thumbnail(tmp_path, monkeypatch):
    db_path = tmp_path / "library.db"
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA journal_mode=WAL")
    models.Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False)
    db = Session()
    try:
        source = models.XImportSource(name="X", download_root_path=str(tmp_path))
        folder = models.Folder(path=storage.x_root_dir(str(tmp_path)), scan_mode="image")
        post = models.XPost(source=source, tweet_id="123", url="https://x.com/example/status/123")
        db.add_all([source, folder, post])
        db.commit()

        def assert_writer_available():
            with sqlite3.connect(db_path, timeout=0.2) as probe:
                probe.execute("BEGIN IMMEDIATE")
                probe.rollback()

        monkeypatch.setattr(
            client,
            "fetch_tweet",
            lambda *args, **kwargs: client.TweetData(
                tweet_id="123",
                author_screen_name="example",
                author_name="Example",
                posted_at=None,
                full_text="test",
                media=[client.TweetMedia(media_index=0, media_type="video", url="https://example.com/1.mp4")],
            ),
        )

        def download_media(*args, **kwargs):
            assert_writer_available()
            return b"video", "video/mp4"

        def make_thumbnail(*args, **kwargs):
            assert_writer_available()
            return False, 0, "failed"

        monkeypatch.setattr(client, "download_media", download_media)
        monkeypatch.setattr(storage.scanner, "get_video_thumbnail", make_thumbnail)

        job = importer.ImportJob(
            job_id="test",
            source_id=source.id,
            download_root=str(tmp_path),
            thumbnail_dir=str(tmp_path),
        )
        importer._process_post(job, post.id, db, folder)

        db.refresh(post)
        assert post.status == "completed"
        assert db.query(models.XMediaItem).filter_by(post_id=post.id, status="downloaded").count() == 1
        assert db.query(models.Media).filter_by(source_site="x").count() == 1
    finally:
        db.close()
        engine.dispose()
