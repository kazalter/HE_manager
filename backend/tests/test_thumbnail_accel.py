import os
import tempfile
import unittest
import zipfile
from io import BytesIO
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import auth, database, main, models
from app.routers import media as media_routes
from app.services import thumbnails


class ThumbnailAccelRedirectTest(unittest.TestCase):
    def setUp(self):
        auth.invalidate_auth_cache()
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        models.Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        db = self.Session()
        user = models.User(
            username="admin",
            password_hash="not-used",
            is_admin=True,
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        self.token = auth.create_access_token(db, user)
        db.close()

    def tearDown(self):
        auth.invalidate_auth_cache()
        main.app.dependency_overrides.pop(database.get_db, None)
        self.engine.dispose()

    def test_thumbnails_and_manga_pages_use_x_accel_redirect_when_proxied(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sample_jpg = os.path.join(tmpdir, "cover #1.jpg")
            with open(sample_jpg, "wb") as fp:
                fp.write(b"\xff\xd8\xff\xd9")

            book_path = os.path.join(tmpdir, "book.cbz")
            buf = BytesIO()
            Image.new("RGB", (32, 48), color="red").save(buf, format="PNG")
            with zipfile.ZipFile(book_path, "w") as zf:
                zf.writestr("001.png", buf.getvalue())

            db = self.Session()
            folder = models.Folder(path=tmpdir, scan_mode="manga")
            db.add(folder)
            db.flush()
            manga = models.Media(
                folder_id=folder.id,
                title="book",
                relative_path="book.cbz",
                absolute_path=book_path,
                media_type="manga",
                extension=".cbz",
                file_size=os.path.getsize(book_path),
                page_count=1,
            )
            db.add(manga)
            db.commit()
            db.refresh(manga)
            manga_id = manga.id
            db.close()

            thumbnails_mount = next(
                route for route in main.app.routes if getattr(route, "name", None) == "thumbnails"
            )
            orig_app = thumbnails_mount.app
            thumbnails_mount.app = main.CachedThumbnailStaticFiles(directory=tmpdir)

            def override_get_db():
                session = self.Session()
                try:
                    yield session
                finally:
                    session.close()

            main.app.dependency_overrides[database.get_db] = override_get_db
            try:
                with (
                    patch.object(database, "SessionLocal", self.Session),
                    patch.object(thumbnails, "THUMBNAIL_DIR", tmpdir),
                    patch.object(media_routes, "THUMBNAIL_DIR", tmpdir),
                    patch.dict(os.environ, {"HE_THUMBNAIL_ACCEL_PREFIX": "/_internal_thumbnails"}),
                ):
                    client = TestClient(main.app)

                    # Without proxy header, direct access serves actual file bytes.
                    direct = client.get(f"/thumbnails/cover%20%231.jpg?token={self.token}")
                    self.assertEqual(direct.status_code, 200)
                    self.assertEqual(direct.content, b"\xff\xd8\xff\xd9")
                    self.assertNotIn("x-accel-redirect", direct.headers)

                    # With Nginx proxy header, /thumbnails/ returns X-Accel-Redirect and empty body.
                    accel_headers = {"X-HE-Accel-Thumbnails": "1"}
                    proxied = client.get(
                        f"/thumbnails/cover%20%231.jpg?token={self.token}",
                        headers=accel_headers,
                    )
                    self.assertEqual(proxied.status_code, 200)
                    self.assertEqual(proxied.content, b"")
                    self.assertEqual(
                        proxied.headers.get("x-accel-redirect"),
                        "/_internal_thumbnails/cover%20%231.jpg",
                    )
                    self.assertEqual(proxied.headers.get("cache-control"), "private, max-age=86400")
                    self.assertEqual(proxied.headers.get("content-type"), "image/jpeg")

                    # /mobile/thumbnails/{filename} also uses X-Accel-Redirect when proxied.
                    mob_thumb = client.get(
                        f"/mobile/thumbnails/cover%20%231.jpg?token={self.token}",
                        headers=accel_headers,
                    )
                    self.assertEqual(mob_thumb.status_code, 200)
                    self.assertEqual(mob_thumb.content, b"")
                    self.assertEqual(
                        mob_thumb.headers.get("x-accel-redirect"),
                        "/_internal_thumbnails/cover%20%231.jpg",
                    )

                    # Manga page thumbnail generates on first hit and redirects via X-Accel-Redirect.
                    page_thumb = client.get(
                        f"/manga/{manga_id}/page/0?thumbnail=true&token={self.token}",
                        headers=accel_headers,
                    )
                    self.assertEqual(page_thumb.status_code, 200)
                    self.assertEqual(page_thumb.content, b"")
                    self.assertEqual(
                        page_thumb.headers.get("x-accel-redirect"),
                        f"/_internal_thumbnails/manga_page_{manga_id}_0_v2.jpg",
                    )
                    self.assertEqual(
                        page_thumb.headers.get("cache-control"),
                        "public, max-age=604800, immutable",
                    )
            finally:
                thumbnails_mount.app = orig_app


if __name__ == "__main__":
    unittest.main()
