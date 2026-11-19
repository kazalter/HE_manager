import base64
from io import BytesIO
import os
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
import zipfile

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import auth, database, main, models
from app.routers import media as media_routes
from app.services import login_throttle, thumbnails


def _basic_header(username: str, password: str) -> dict[str, str]:
    token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    return {"Authorization": f"Basic {token}"}


class OpdsAndWebdavTest(unittest.TestCase):
    def setUp(self):
        auth.invalidate_auth_cache()
        login_throttle.LOGIN_FAILURES.clear()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.addCleanup(self.engine.dispose)
        models.Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

        db = self.Session()
        self.user = models.User(
            username="reader",
            password_hash=auth.hash_password("secret123"),
            is_admin=False,
            is_active=True,
        )
        db.add(self.user)
        db.commit()
        db.refresh(self.user)
        self.user_id = self.user.id
        self.api_token = auth.create_access_token(db, self.user)

        # Build test media assets on disk
        img_buf = BytesIO()
        Image.new("RGB", (32, 48), color="blue").save(img_buf, format="PNG")
        self.png_bytes = img_buf.getvalue()

        self.thumb_dir = os.path.join(self.tmp.name, "thumbs")
        os.makedirs(self.thumb_dir, exist_ok=True)
        with open(os.path.join(self.thumb_dir, "cover1.jpg"), "wb") as fp:
            fp.write(b"\xff\xd8\xff\xd9")

        self.cbz_path = os.path.join(self.tmp.name, "cbz_book.cbz")
        with zipfile.ZipFile(self.cbz_path, "w") as zf:
            zf.writestr("001.png", self.png_bytes)

        self.dir_manga_path = os.path.join(self.tmp.name, "dir_book")
        os.makedirs(self.dir_manga_path, exist_ok=True)
        with open(os.path.join(self.dir_manga_path, "001.png"), "wb") as fp:
            fp.write(self.png_bytes)

        self.video_path = os.path.join(self.tmp.name, "sample.mp4")
        with open(self.video_path, "wb") as fp:
            fp.write(b"0123456789abcdef")

        self.audio_dir = os.path.join(self.tmp.name, "asmr_work")
        os.makedirs(self.audio_dir, exist_ok=True)
        with open(os.path.join(self.audio_dir, "01 track.mp3"), "wb") as fp:
            fp.write(b"ID3AUDIOBYTES")

        folder = models.Folder(path=self.tmp.name, scan_mode="auto")
        db.add(folder)
        db.flush()

        tag = models.Tag(name="纯爱", namespace="general")
        db.add(tag)
        db.flush()

        self.cbz_manga = models.Media(
            folder_id=folder.id,
            title="[Alice] CBZ Book",
            artist="Alice",
            relative_path="cbz_book.cbz",
            absolute_path=self.cbz_path,
            media_type="manga",
            extension=".cbz",
            file_size=os.path.getsize(self.cbz_path),
            page_count=1,
            cover_path="cover1.jpg",
            favorite=True,
            rating=5,
        )
        self.cbz_manga.tags.append(tag)

        self.dir_manga = models.Media(
            folder_id=folder.id,
            title="[Bob] Dir Book",
            artist="Bob",
            relative_path="dir_book",
            absolute_path=self.dir_manga_path,
            media_type="manga",
            extension=".dir",
            file_size=len(self.png_bytes),
            page_count=1,
            favorite=False,
        )

        self.video = models.Media(
            folder_id=folder.id,
            title="Sample Clip",
            relative_path="sample.mp4",
            absolute_path=self.video_path,
            media_type="video",
            extension=".mp4",
            file_size=16,
            favorite=True,
        )

        self.audio = models.Media(
            folder_id=folder.id,
            title="ASMR Set",
            relative_path="asmr_work",
            absolute_path=self.audio_dir,
            media_type="audio",
            extension=".dir",
            file_size=13,
        )

        db.add_all([self.cbz_manga, self.dir_manga, self.video, self.audio])
        db.commit()
        db.refresh(self.cbz_manga)
        db.refresh(self.dir_manga)
        db.refresh(self.video)
        db.refresh(self.audio)
        self.cbz_id = self.cbz_manga.id
        self.dir_id = self.dir_manga.id
        self.video_id = self.video.id
        self.audio_id = self.audio.id
        db.close()

        def override_get_db():
            session = self.Session()
            try:
                yield session
            finally:
                session.close()

        main.app.dependency_overrides[database.get_db] = override_get_db
        self.addCleanup(main.app.dependency_overrides.pop, database.get_db, None)
        self.addCleanup(auth.invalidate_auth_cache)
        self.addCleanup(login_throttle.LOGIN_FAILURES.clear)

    def test_basic_auth_challenge_caching_and_throttling(self):
        with patch.object(database, "SessionLocal", self.Session):
            client = TestClient(main.app)

            # Protocol endpoints advertise Basic challenge; regular JSON API does not.
            opds_unauth = client.get("/opds")
            self.assertEqual(opds_unauth.status_code, 401)
            self.assertEqual(opds_unauth.headers.get("www-authenticate"), 'Basic realm="HE Manager"')

            webdav_unauth = client.request("PROPFIND", "/webdav/")
            self.assertEqual(webdav_unauth.status_code, 401)
            self.assertEqual(webdav_unauth.headers.get("www-authenticate"), 'Basic realm="HE Manager"')

            api_unauth = client.get("/media")
            self.assertEqual(api_unauth.status_code, 401)
            self.assertIsNone(api_unauth.headers.get("www-authenticate"))

            # First Basic Auth verifies password and caches snapshot; second hits memory cache.
            headers = _basic_header("reader", "secret123")
            first = client.get("/opds", headers=headers)
            self.assertEqual(first.status_code, 200)
            with patch("app.auth.verify_password", side_effect=AssertionError("should hit basic auth cache")):
                second = client.get("/opds", headers=headers)
                self.assertEqual(second.status_code, 200)

            # Access token works as Basic password too.
            auth.invalidate_user_auth_cache(self.user_id)
            tok_basic = client.get("/opds", headers=_basic_header("reader", self.api_token))
            self.assertEqual(tok_basic.status_code, 200)

            # Repeated failures hit login_throttle (429).
            bad = _basic_header("reader", "wrongpass")
            for _ in range(login_throttle.LOGIN_MAX_FAILURES):
                self.assertEqual(client.get("/opds", headers=bad).status_code, 401)
            self.assertEqual(client.get("/opds", headers=bad).status_code, 429)

    def test_opds_feeds_cover_pse_pages_and_downloads(self):
        with (
            patch.object(database, "SessionLocal", self.Session),
            patch.object(thumbnails, "THUMBNAIL_DIR", self.thumb_dir),
            patch.object(media_routes, "THUMBNAIL_DIR", self.thumb_dir),
            patch.dict(os.environ, {"HE_THUMBNAIL_ACCEL_PREFIX": "/_internal_thumbnails"}),
        ):
            client = TestClient(main.app)
            headers = _basic_header("reader", "secret123")

            root = client.get("/opds", headers=headers)
            self.assertEqual(root.status_code, 200)
            self.assertIn("application/atom+xml", root.headers["content-type"])
            root_xml = ET.fromstring(root.content)
            titles = [e.text for e in root_xml.findall("{http://www.w3.org/2005/Atom}entry/{http://www.w3.org/2005/Atom}title")]
            self.assertIn("全部漫画", titles)
            self.assertIn("我的收藏", titles)

            search_desc = client.get("/opds/search.xml", headers=headers)
            self.assertEqual(search_desc.status_code, 200)
            self.assertIn("/opds/books?q={searchTerms}", search_desc.text)

            books = client.get("/opds/books?q=Alice", headers=headers)
            self.assertEqual(books.status_code, 200)
            books_xml = ET.fromstring(books.content)
            entries = books_xml.findall("{http://www.w3.org/2005/Atom}entry")
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0].find("{http://www.w3.org/2005/Atom}title").text, "[Alice] CBZ Book")

            favs = client.get("/opds/favorites", headers=headers)
            self.assertEqual(favs.status_code, 200)
            fav_entries = ET.fromstring(favs.content).findall("{http://www.w3.org/2005/Atom}entry")
            self.assertEqual(len(fav_entries), 1)

            artists = client.get("/opds/artists", headers=headers)
            self.assertEqual(artists.status_code, 200)
            self.assertIn("Alice", artists.text)

            tags = client.get("/opds/tags", headers=headers)
            self.assertEqual(tags.status_code, 200)
            self.assertIn("纯爱", tags.text)

            # Cover supports both direct FileResponse and X-Accel-Redirect when proxied.
            cover_direct = client.get(f"/opds/cover/{self.cbz_id}", headers=headers)
            self.assertEqual(cover_direct.status_code, 200)
            self.assertEqual(cover_direct.content, b"\xff\xd8\xff\xd9")

            cover_accel = client.get(
                f"/opds/cover/{self.cbz_id}",
                headers={**headers, "X-HE-Accel-Thumbnails": "1"},
            )
            self.assertEqual(cover_accel.status_code, 200)
            self.assertEqual(cover_accel.content, b"")
            self.assertEqual(cover_accel.headers.get("x-accel-redirect"), "/_internal_thumbnails/cover1.jpg")

            # OPDS-PSE page stream returns page bytes.
            page0 = client.get(f"/opds/page/{self.dir_id}/0", headers=headers)
            self.assertEqual(page0.status_code, 200)
            self.assertEqual(page0.content, self.png_bytes)

            # Archive download supports Range; .dir download streams a valid CBZ zip.
            dl_cbz = client.get(f"/opds/download/{self.cbz_id}", headers={**headers, "Range": "bytes=0-3"})
            self.assertEqual(dl_cbz.status_code, 206)
            self.assertEqual(dl_cbz.content[:2], b"PK")

            dl_dir = client.get(f"/opds/download/{self.dir_id}", headers=headers)
            self.assertEqual(dl_dir.status_code, 200)
            self.assertEqual(dl_dir.headers["content-type"], "application/vnd.comicbook+zip")
            with zipfile.ZipFile(BytesIO(dl_dir.content), "r") as zf:
                self.assertEqual(zf.namelist(), ["001.png"])
                self.assertEqual(zf.read("001.png"), self.png_bytes)

    def test_webdav_readonly_propfind_range_get_and_method_restrictions(self):
        with patch.object(database, "SessionLocal", self.Session):
            client = TestClient(main.app)
            headers = _basic_header("reader", "secret123")

            opts = client.options("/webdav/")
            self.assertEqual(opts.status_code, 200)
            self.assertEqual(opts.headers.get("dav"), "1")
            self.assertIn("PROPFIND", opts.headers.get("allow", ""))

            # Root PROPFIND lists virtual folders
            root_prop = client.request("PROPFIND", "/webdav/", headers={**headers, "Depth": "1"})
            self.assertEqual(root_prop.status_code, 207)
            root_xml = ET.fromstring(root_prop.content)
            hrefs = [el.text for el in root_xml.findall("{DAV:}response/{DAV:}href")]
            self.assertIn("/webdav/Videos/", hrefs)
            self.assertIn("/webdav/Manga/", hrefs)
            self.assertIn("/webdav/Audio/", hrefs)
            self.assertIn("/webdav/Favorites/", hrefs)

            # Depth infinity is rejected
            self.assertEqual(
                client.request("PROPFIND", "/webdav/", headers={**headers, "Depth": "infinity"}).status_code,
                403,
            )

            # Videos collection + Range GET + HEAD
            vid_prop = client.request("PROPFIND", "/webdav/Videos/", headers={**headers, "Depth": "1"})
            self.assertEqual(vid_prop.status_code, 207)
            vid_name = f"{self.video_id} - Sample Clip.mp4"
            self.assertIn(vid_name, vid_prop.text)

            vid_url = f"/webdav/Videos/{self.video_id}%20-%20Sample%20Clip.mp4"
            vid_head = client.head(vid_url, headers=headers)
            self.assertEqual(vid_head.status_code, 200)
            self.assertEqual(vid_head.headers.get("content-length"), "16")

            vid_range = client.get(vid_url, headers={**headers, "Range": "bytes=0-3"})
            self.assertEqual(vid_range.status_code, 206)
            self.assertEqual(vid_range.content, b"0123")

            # Directory manga exposes pages as files inside a collection
            dir_prop = client.request(
                "PROPFIND",
                f"/webdav/Manga/{self.dir_id}%20-%20%5BBob%5D%20Dir%20Book/",
                headers={**headers, "Depth": "1"},
            )
            self.assertEqual(dir_prop.status_code, 207)
            self.assertIn("0001_001.png", dir_prop.text)
            page_get = client.get(
                f"/webdav/Manga/{self.dir_id}%20-%20%5BBob%5D%20Dir%20Book/0001_001.png",
                headers=headers,
            )
            self.assertEqual(page_get.status_code, 200)
            self.assertEqual(page_get.content, self.png_bytes)

            # Directory audio exposes tracks
            audio_prop = client.request(
                "PROPFIND",
                f"/webdav/Audio/{self.audio_id}%20-%20ASMR%20Set/",
                headers={**headers, "Depth": "1"},
            )
            self.assertEqual(audio_prop.status_code, 207)
            self.assertIn("01%20-%2001%20track.mp3", audio_prop.text)
            audio_get = client.get(
                f"/webdav/Audio/{self.audio_id}%20-%20ASMR%20Set/01%20-%2001%20track.mp3",
                headers=headers,
            )
            self.assertEqual(audio_get.status_code, 200)
            self.assertEqual(audio_get.content, b"ID3AUDIOBYTES")

            # Read-only enforcement: write methods return 405
            for method in ("PUT", "DELETE", "MKCOL"):
                resp = client.request(method, vid_url, headers=headers)
                self.assertEqual(resp.status_code, 405)


if __name__ == "__main__":
    unittest.main()
