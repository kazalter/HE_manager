"""Long names must be importable without renaming the user's files."""
from contextlib import ExitStack
import os
from pathlib import Path
import tempfile
from unittest import mock
import zipfile

from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.routers import media as media_routes
from app.scanners import runner
from starlette.responses import Response


def test_long_directory_names_and_repair_cover_on_rescan():
    with tempfile.TemporaryDirectory() as temp, ExitStack() as patches:
        root = Path(temp)
        library = root / 'library'
        library.mkdir()
        # Each title fits the source filesystem, but the old generated thumbnail
        # name adds a prefix, timestamp and extension and exceeds NAME_MAX.
        names = ['漫' * 78 + '甲', '漫' * 78 + '乙']
        # A near-255-character ASCII component plus the temporary parent path
        # can exceed Windows' total path limit before the scanner sees it.
        if os.name != 'nt':
            names.append('a' * 240)
        for name in names:
            work = library / name
            work.mkdir()
            Image.new('RGB', (10, 15), 'blue').save(work / '001.png')
        engine = create_engine(f"sqlite:///{root / 'library.db'}")
        try:
            models.Base.metadata.create_all(engine)
            Session = sessionmaker(bind=engine)
            with Session() as db:
                folder = models.Folder(path=str(library), scan_mode='manga')
                db.add(folder)
                db.commit()
                folder_id = folder.id
            patches.enter_context(mock.patch.object(runner.database, 'SessionLocal', Session))
            patches.enter_context(mock.patch.object(runner.os, 'getcwd', return_value=str(root)))
            patches.enter_context(mock.patch.object(runner.dedup_worker, 'enqueue'))
            patches.enter_context(mock.patch('app.services.assistant_runtime_logs.emit_event'))
            assert runner.scan_folder(folder_id)
            with Session() as db:
                rows = db.query(models.Media).order_by(models.Media.title).all()
                assert {m.title for m in rows} == set(names)
                assert all(m.page_count == 1 and m.absolute_path == str(library / m.title) for m in rows)
                assert all(m.cover_path and (root / '.thumbnails' / m.cover_path).is_file() for m in rows)
                assert len({m.cover_path for m in rows}) == len(names)
                original_ids = {m.title: m.id for m in rows}
                unchanged_covers = {m.title: m.cover_path for m in rows[1:]}
                # Simulate an earlier scan whose overly long thumbnail failed.
                rows[0].cover_path = None
                db.commit()
            assert runner.scan_folder(folder_id)
            with Session() as db:
                rows = db.query(models.Media).all()
                assert {m.title: m.id for m in rows} == original_ids
                assert all(m.cover_path and (root / '.thumbnails' / m.cover_path).is_file() for m in rows)
                assert all(m.cover_path == unchanged_covers[m.title] for m in rows if m.title in unchanged_covers)
                assert all((library / m.title / '001.png').is_file() for m in rows)
                visible = media_routes.list_media(Response(), media_type='manga', db=db)
                assert {m.title for m in visible} == set(names)
        finally:
            engine.dispose()


def test_long_archive_name_is_indexed_and_readable():
    with tempfile.TemporaryDirectory() as temp, ExitStack() as patches:
        root = Path(temp)
        library = root / 'library'
        library.mkdir()
        title = '本' * 78 + '.cbz'
        archive = library / title
        image = root / 'page.png'
        Image.new('RGB', (10, 15), 'red').save(image)
        with zipfile.ZipFile(archive, 'w') as zf:
            zf.write(image, '001.png')
        engine = create_engine(f"sqlite:///{root / 'library.db'}")
        try:
            models.Base.metadata.create_all(engine)
            Session = sessionmaker(bind=engine)
            with Session() as db:
                folder = models.Folder(path=str(library), scan_mode='auto')
                db.add(folder)
                db.commit()
                folder_id = folder.id
            patches.enter_context(mock.patch.object(runner.database, 'SessionLocal', Session))
            patches.enter_context(mock.patch.object(runner.os, 'getcwd', return_value=str(root)))
            patches.enter_context(mock.patch.object(runner.dedup_worker, 'enqueue'))
            patches.enter_context(mock.patch('app.services.assistant_runtime_logs.emit_event'))
            assert runner.scan_folder(folder_id)
            with Session() as db:
                media = db.query(models.Media).one()
                assert media.title == title and media.absolute_path == str(archive)
                assert media.page_count == 1 and media.cover_path
                assert (root / '.thumbnails' / media.cover_path).is_file()
                with zipfile.ZipFile(media.absolute_path) as zf:
                    assert zf.read('001.png') == image.read_bytes()
        finally:
            engine.dispose()


def test_cover_failure_does_not_abort_scan_and_can_recover():
    with tempfile.TemporaryDirectory() as temp, ExitStack() as patches:
        root = Path(temp)
        library = root / 'library'
        work = library / ('長' * 78)
        work.mkdir(parents=True)
        Image.new('RGB', (10, 15), 'blue').save(work / '001.png')
        engine = create_engine(f"sqlite:///{root / 'library.db'}")
        try:
            models.Base.metadata.create_all(engine)
            Session = sessionmaker(bind=engine)
            with Session() as db:
                folder = models.Folder(path=str(library), scan_mode='manga')
                db.add(folder)
                db.commit()
                folder_id = folder.id
            patches.enter_context(mock.patch.object(runner.database, 'SessionLocal', Session))
            patches.enter_context(mock.patch.object(runner.os, 'getcwd', return_value=str(root)))
            patches.enter_context(mock.patch.object(runner.dedup_worker, 'enqueue'))
            patches.enter_context(mock.patch('app.services.assistant_runtime_logs.emit_event'))
            with mock.patch.object(runner, 'get_folder_thumbnail', side_effect=OSError('cache unavailable')):
                assert runner.scan_folder(folder_id)
            with Session() as db:
                media = db.query(models.Media).one()
                media_id = media.id
                assert media.cover_path is None and media.page_count == 1
            assert runner.scan_folder(folder_id)
            with Session() as db:
                media = db.query(models.Media).one()
                assert media.id == media_id and (root / '.thumbnails' / media.cover_path).is_file()
        finally:
            engine.dispose()
