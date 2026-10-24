"""Assistant previews use reader page ordering without weakening file boundaries."""

import io
import os
import unittest
import zipfile
from unittest.mock import patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from PIL import Image

from app import auth, models
from app.assistant.file_reads import preview_payload
from app.routers import assistant
from tests.assistant_fixtures import assistant_fixture


def picture(color):
    output = io.BytesIO()
    Image.new("RGB", (16, 16), color).save(output, format="PNG")
    return output.getvalue()


class AssistantPreviewTests(unittest.TestCase):
    def setUp(self):
        self.f = assistant_fixture(self)
        self.library = self.f.root.resolve() / "library"
        self.library.mkdir()
        self.f.db.get(models.Folder, 1).path = str(self.library)
        environment = patch.dict(
            os.environ, {"HE_ASSISTANT_MEDIA_ROOTS": str(self.library)}
        )
        environment.start()
        self.addCleanup(environment.stop)

    def media_at(self, path):
        media = self.f.db.get(models.Media, 1)
        media.absolute_path = str(path)
        media.extension = ".dir" if path.is_dir() else ".cbz"
        self.f.db.commit()

    def assert_pages(self):
        for index, expected in enumerate(((255, 0, 0), (0, 0, 255))):
            with self.subTest(page_index=index):
                raw, mime = preview_payload(self.f.db, 1, index)
                self.assertEqual(mime, "image/jpeg")
                with Image.open(io.BytesIO(raw)) as image:
                    actual = image.getpixel((0, 0))
                self.assertTrue(
                    all(abs(a - b) <= 3 for a, b in zip(actual, expected)), actual
                )
        with self.assertRaises(HTTPException) as error:
            preview_payload(self.f.db, 1, 2)
        self.assertEqual(error.exception.status_code, 404)

    def test_directory_preview_ignores_generated_images_and_appledouble(self):
        book = self.library / "book"
        for relative, raw in {
            "01.png": picture("red"),
            "chapter/02.png": picture("blue"),
            ".he_cover/00.png": picture("green"),
            ".thumbnails/00.png": picture("green"),
            "result/00.png": picture("green"),
            "__MACOSX/00.png": picture("green"),
            "._01.png": b"AppleDouble metadata is not an image",
        }.items():
            file = book / relative
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(raw)
        self.media_at(book)
        self.assert_pages()

    def test_archive_preview_uses_the_same_page_selection(self):
        book = self.library / "book.cbz"
        with zipfile.ZipFile(book, "w") as archive:
            archive.writestr("01.png", picture("red"))
            archive.writestr("chapter\\02.png", picture("blue"))
            archive.writestr(".he_cover/00.png", picture("green"))
            archive.writestr("result/00.png", picture("green"))
            archive.writestr("__MACOSX/._01.png", b"AppleDouble")
            archive.writestr("._01.png", b"AppleDouble")
        self.media_at(book)
        self.assert_pages()

    def test_directory_preview_does_not_follow_file_or_directory_symlinks(self):
        book = self.library / "book"
        book.mkdir()
        outside = self.f.root / "outside"
        outside.mkdir()
        (outside / "01.png").write_bytes(picture("red"))
        try:
            (book / "file.png").symlink_to(outside / "01.png")
            (book / "directory").symlink_to(outside, target_is_directory=True)
        except OSError as error:
            self.skipTest(f"Symlinks unavailable: {error}")
        self.media_at(book)
        with self.assertRaises(HTTPException) as error:
            preview_payload(self.f.db, 1)
        self.assertEqual(error.exception.status_code, 404)

    def test_archive_preview_rejects_path_traversal(self):
        book = self.library / "book.cbz"
        with zipfile.ZipFile(book, "w") as archive:
            archive.writestr("../01.png", picture("red"))
        self.media_at(book)
        with self.assertRaises(HTTPException) as error:
            preview_payload(self.f.db, 1)
        self.assertEqual(error.exception.status_code, 403)

    def test_http_preview_requires_admin_and_returns_uncached_body_page(self):
        app = FastAPI()
        app.include_router(assistant.router)

        def get_db():
            with self.f.factory() as db:
                yield db

        app.dependency_overrides[assistant.get_db] = get_db
        admin = self.f.db.get(models.User, 1)
        reader = self.f.db.get(models.User, 2)
        reader.is_admin = False
        self.f.db.commit()
        admin_token = auth.create_access_token(self.f.db, admin)
        reader_token = auth.create_access_token(self.f.db, reader)
        url = "/assistant/media/1/preview"
        headers = {"Authorization": "Bearer " + admin_token}
        with TestClient(app) as client:
            self.assertEqual(client.get(url).status_code, 401)
            self.assertEqual(
                client.get(
                    url, headers={"Authorization": "Bearer " + reader_token}
                ).status_code,
                403,
            )
            for kind in ("directory", "archive"):
                with self.subTest(kind=kind):
                    book = self.library / (
                        "book" if kind == "directory" else "book.cbz"
                    )
                    if kind == "directory":
                        (book / ".he_cover").mkdir(parents=True)
                        (book / ".he_cover/00.png").write_bytes(picture("green"))
                        (book / "01.png").write_bytes(picture("red"))
                    else:
                        with zipfile.ZipFile(book, "w") as archive:
                            archive.writestr(".he_cover/00.png", picture("green"))
                            archive.writestr("01.png", picture("red"))
                    self.media_at(book)
                    response = client.get(url, headers=headers)
                    self.assertEqual(
                        response.status_code,
                        200,
                        response.text if response.status_code != 200 else "",
                    )
                    self.assertEqual(response.headers["content-type"], "image/jpeg")
                    self.assertEqual(response.headers["cache-control"], "no-store")
                    with Image.open(io.BytesIO(response.content)) as image:
                        red, green, blue = image.getpixel((0, 0))
                        self.assertGreater(red, 250)
                        self.assertLess(max(green, blue), 3)
                    self.assertEqual(
                        client.get(url + "?page_index=1", headers=headers).status_code,
                        404,
                    )
                    self.assertEqual(
                        client.get(url + "?page_index=-1", headers=headers).status_code,
                        422,
                    )
