"""Scanner and reader must agree on which files are actual manga pages."""
from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import zipfile

from fastapi import HTTPException
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models, scanner
from app.routers import media as routes
from app.scanners import runner
from app.services import manga_pages


class MangaPagesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.engine = create_engine(f"sqlite:///{self.root / 'test.db'}")
        self.addCleanup(self.engine.dispose)
        models.Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.addCleanup(self.db.close)
        manga_pages._MANGA_FILES_CACHE.clear()
        manga_pages._PAGE_DIMENSIONS_CACHE.clear()
        self.addCleanup(manga_pages._MANGA_FILES_CACHE.clear)
        self.addCleanup(manga_pages._PAGE_DIMENSIONS_CACHE.clear)

    def picture(self, color="red", size=(24, 36), format="PNG"):
        output = BytesIO()
        Image.new("RGB", size, color=color).save(output, format=format)
        return output.getvalue()

    def make_book(self, extension, entries):
        if extension == ".dir":
            path = self.root / f"book-{self.db.query(models.Media).count()}"
            path.mkdir()
            for name, payload in entries.items():
                target = path / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(payload)
        else:
            path = self.root / f"book-{self.db.query(models.Media).count()}{extension}"
            with zipfile.ZipFile(path, "w") as archive:
                for name, payload in entries.items():
                    archive.writestr(name, payload)
        media = models.Media(
            title=path.name, relative_path=path.name, absolute_path=str(path),
            media_type="manga", extension=extension,
            page_count=scanner.count_manga_pages(str(path), extension),
        )
        self.db.add(media)
        self.db.commit()
        return media

    def names(self, media):
        pages = manga_pages.get_manga_image_files(media)
        if media.extension == ".dir":
            return [Path(page).relative_to(media.absolute_path).as_posix() for page in pages]
        return pages

    def test_directory_reader_excludes_generated_and_processing_images(self):
        entries = {"001.png": self.picture(), "chapter/002.png": self.picture("blue")}
        for name in (".he_cover", ".THUMBNAILS", "mask", "result", "inpainted", "node_modules", ".git", ".vite"):
            entries[f"{name}/000.png"] = self.picture("green")
        media = self.make_book(".dir", entries)
        self.assertEqual(media.page_count, 2)
        self.assertEqual(self.names(media), ["001.png", "chapter/002.png"])

    def test_directory_reader_excludes_macos_resource_forks(self):
        media = self.make_book(".dir", {
            "001.png": self.picture(),
            "._001.png": b"AppleDouble metadata, not an image",
            "__MACOSX/._002.jpg": b"AppleDouble metadata",
        })
        self.assertEqual(self.names(media), ["001.png"])
        self.assertEqual(media.page_count, 1)

    def test_archive_reader_and_count_exclude_non_page_images(self):
        media = self.make_book(".cbz", {
            "pages/001.png": self.picture(),
            "pages/002.png": self.picture("blue"),
            "__MACOSX/._001.png": b"AppleDouble metadata",
            "pages/._001.png": b"AppleDouble metadata",
            ".he_cover/cover.jpg": self.picture("green"),
            "result/output.png": self.picture("yellow"),
        })
        self.assertEqual(self.names(media), ["pages/001.png", "pages/002.png"])
        self.assertEqual(media.page_count, 2)

    def test_supported_image_extensions_have_identical_scan_and_reader_counts(self):
        entries = {f"{index:03d}{ext}": self.picture() for index, ext in enumerate(
            (".jpg", ".JPEG", ".png", ".webp", ".bmp", ".GIF", ".avif"), start=1
        )}
        # Page selection is extension based; these samples only exercise the
        # inventory contract. Actual GIF decoding is checked separately below.
        for extension in (".dir", ".cbz"):
            with self.subTest(extension=extension):
                media = self.make_book(extension, entries)
                self.assertEqual(media.page_count, 7)
                self.assertEqual(self.names(media), sorted(entries))

    def test_folder_cover_uses_the_first_readable_gif_page(self):
        media = self.make_book(".dir", {
            "001.gif": self.picture(format="GIF"), "002.png": self.picture("blue"),
        })
        target = self.root / "cover.jpg"
        self.assertTrue(scanner.get_folder_thumbnail(media.absolute_path, str(target)))
        with Image.open(target) as cover:
            red, green, blue = cover.convert("RGB").getpixel((0, 0))
            self.assertGreater(red, 200)
            self.assertLess(blue, 50)

    def test_folder_cover_can_use_a_nested_page(self):
        media = self.make_book(".dir", {"chapter/001.png": self.picture()})
        target = self.root / "nested-cover.jpg"
        self.assertTrue(scanner.get_folder_thumbnail(media.absolute_path, str(target)))
        self.assertTrue(target.is_file())

    def test_archive_cover_ignores_macos_resource_forks(self):
        media = self.make_book(".cbz", {
            "__MACOSX/._001.png": b"AppleDouble metadata",
            "pages/001.png": self.picture(),
        })
        target = self.root / "archive-cover.jpg"
        self.assertTrue(scanner.get_manga_thumbnail(media.absolute_path, str(target)))
        with Image.open(target) as cover:
            self.assertEqual(cover.size, (24, 36))

    def test_archive_windows_separators_keep_member_names_but_filter_metadata(self):
        media = self.make_book(".cbz", {
            "pages\\001.png": self.picture(),
            "__MACOSX\\._001.png": b"AppleDouble metadata",
            ".he_cover\\cover.png": self.picture("green"),
        })
        self.assertEqual(self.names(media), ["pages\\001.png"])
        self.assertEqual(media.page_count, 1)
        response = routes.get_manga_page(media.id, 0, db=self.db)
        with Image.open(BytesIO(response.body)) as image:
            self.assertEqual(image.size, (24, 36))

    def test_legacy_thumbnail_cannot_override_the_filtered_first_page(self):
        media = self.make_book(".dir", {
            "001.png": self.picture(), ".he_cover/000.png": self.picture("green"),
        })
        thumbs = self.root / "thumbs"
        thumbs.mkdir()
        Image.new("RGB", (24, 36), "green").save(thumbs / f"manga_page_{media.id}_0.jpg")
        with mock.patch.object(routes, "THUMBNAIL_DIR", str(thumbs)):
            response = routes.get_manga_page(media.id, 0, db=self.db, thumbnail=True)
        with Image.open(response.path) as image:
            red, green, blue = image.getpixel((0, 0))
            self.assertGreater(red, 200)
            self.assertLess(green, 50)

    def test_metadata_only_directories_are_not_indexed_as_manga(self):
        library = self.root / "metadata-library"
        (library / "__MACOSX").mkdir(parents=True)
        (library / "__MACOSX" / "._001.png").write_bytes(b"AppleDouble")
        (library / "._001.png").write_bytes(b"AppleDouble")
        folder = models.Folder(path=str(library), scan_mode="manga")
        self.db.add(folder)
        self.db.commit()
        with (
            mock.patch.object(runner.database, "SessionLocal", self.Session),
            mock.patch.object(runner.os, "getcwd", return_value=str(self.root)),
            mock.patch.object(runner.dedup_worker, "enqueue"),
            mock.patch("app.services.assistant_runtime_logs.emit_event"),
        ):
            self.assertTrue(runner.scan_folder(folder.id))
        self.assertEqual(self.db.query(models.Media).count(), 0)

    def test_pages_dimensions_and_page_endpoints_use_the_same_inventory(self):
        for extension in (".dir", ".cbz"):
            with self.subTest(extension=extension):
                media = self.make_book(extension, {
                    "001.png": self.picture(),
                    "002.gif": self.picture("blue", (48, 60), "GIF"),
                    ".he_cover/000.png": self.picture("green"),
                    "__MACOSX/._001.png": b"AppleDouble metadata",
                })
                self.assertEqual(media.page_count, 2)
                result = routes.get_manga_pages_count(media.id, db=self.db, include_dimensions=True)
                self.assertEqual(result, {"total_pages": 2, "page_dimensions": [(24, 36), (48, 60)]})
                first = routes.get_manga_page(media.id, 0, db=self.db)
                with Image.open(BytesIO(first.body)) as image:
                    self.assertEqual(image.convert("RGB").getpixel((0, 0)), (255, 0, 0))
                last = routes.get_manga_page(media.id, 1, db=self.db, track_progress=True)
                with Image.open(BytesIO(last.body)) as image:
                    self.assertEqual(image.size, (48, 60))
                self.assertEqual(media.view_status, "viewed")
                with self.assertRaises(HTTPException) as error:
                    routes.get_manga_page(media.id, 2, db=self.db)
                self.assertEqual(error.exception.status_code, 404)

    def test_real_folder_scan_indexes_gif_only_book_and_generates_cover(self):
        library = self.root / "library"
        book = library / "gif-only"
        book.mkdir(parents=True)
        (book / "001.gif").write_bytes(self.picture(format="GIF"))
        folder = models.Folder(path=str(library), scan_mode="manga")
        self.db.add(folder)
        self.db.commit()
        with (
            mock.patch.object(runner.database, "SessionLocal", self.Session),
            mock.patch.object(runner.os, "getcwd", return_value=str(self.root)),
            mock.patch.object(runner.dedup_worker, "enqueue"),
            mock.patch("app.services.assistant_runtime_logs.emit_event"),
        ):
            self.assertTrue(runner.scan_folder(folder.id))
        media = self.db.query(models.Media).one()
        self.assertEqual(media.page_count, 1)
        self.assertIsNotNone(media.cover_path)
        self.assertTrue((self.root / ".thumbnails" / media.cover_path).is_file())


if __name__ == "__main__":
    unittest.main()
