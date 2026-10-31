"""Legacy image imports need geometry before the web strip is laid out."""
import os
import tempfile
import unittest
from unittest import mock

from fastapi import Response
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.routers import media as routes
from app.scanners import runner


class ImageGeometryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.engine = create_engine('sqlite:///:memory:')
        self.addCleanup(self.engine.dispose)
        models.Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.addCleanup(self.db.close)
        self.folder = models.Folder(path=self.temp.name, scan_mode='image')
        self.db.add(self.folder)
        self.db.commit()

    def image(self, name='page.jpg', missing=False):
        path = os.path.join(self.temp.name, name)
        if not missing:
            Image.new('RGB', (480, 260), 'white').save(path)
        item = models.Media(folder_id=self.folder.id, title=name, relative_path=name,
            absolute_path=path, media_type='image', extension='.jpg', file_size=100,
            width=None, height=None, is_missing=False)
        self.db.add(item)
        self.db.commit()
        return item

    def test_list_repairs_and_persists_header_dimensions_before_returning(self):
        item = self.image()
        result = routes.list_media(Response(), media_type='image', db=self.db)
        self.assertEqual((result[0].width, result[0].height), (480, 260))
        self.db.expire_all()
        self.assertEqual((self.db.get(models.Media, item.id).width, self.db.get(models.Media, item.id).height), (480, 260))
        with mock.patch.object(routes.scanner, 'get_image_metadata') as read:
            routes.list_media(Response(), media_type='image', db=self.db)
            read.assert_not_called()

    def test_bad_file_does_not_break_the_list_or_invent_geometry(self):
        self.image('offline.jpg', missing=True)
        result = routes.list_media(Response(), media_type='image', db=self.db)
        self.assertEqual(len(result), 1)
        self.assertIsNone(result[0].width)
        self.assertIsNone(result[0].height)

    def test_rescan_repairs_existing_records_without_recreating_them(self):
        item = self.image()
        original_id = item.id
        with mock.patch.object(runner.database, 'SessionLocal', self.Session), \
             mock.patch.object(runner.os, 'getcwd', return_value=self.temp.name), \
             mock.patch.object(runner.dedup_worker, 'enqueue'), \
             mock.patch('app.services.assistant_runtime_logs.emit_event'):
            self.assertTrue(runner.scan_folder(self.folder.id))
        self.db.expire_all()
        result = self.db.get(models.Media, original_id)
        self.assertEqual((result.width, result.height), (480, 260))
        self.assertEqual(self.db.query(models.Media).count(), 1)


class ImageGeometryBackfillTest(unittest.TestCase):
    def test_backfill_is_backed_up_and_does_not_change_known_geometry_or_user_metadata(self):
        import sqlite3
        from scripts.backfill_image_dimensions import backfill
        with tempfile.TemporaryDirectory() as root:
            image_path = os.path.join(root, 'page.jpg')
            Image.new('RGB', (480, 260), 'white').save(image_path)
            db_path, backup_path = os.path.join(root, 'db.sqlite'), os.path.join(root, 'backup.sqlite')
            with sqlite3.connect(db_path) as db:
                db.execute('CREATE TABLE media (id INTEGER PRIMARY KEY, absolute_path TEXT, media_type TEXT, is_missing INTEGER, width INTEGER, height INTEGER, progress INTEGER, favorite INTEGER)')
                db.executemany('INSERT INTO media VALUES (?, ?, ?, 0, ?, ?, 7, 1)', [(1, image_path, 'image', None, None), (2, image_path, 'image', 100, 200)])
            self.assertEqual(backfill(db_path)['readable'], 1)
            self.assertFalse(os.path.exists(backup_path))
            self.assertEqual(backfill(db_path, True, backup_path)['updated'], 1)
            with sqlite3.connect(db_path) as db:
                self.assertEqual(db.execute('SELECT width,height,progress,favorite FROM media ORDER BY id').fetchall(), [(480, 260, 7, 1), (100, 200, 7, 1)])
            with sqlite3.connect(backup_path) as db:
                self.assertEqual(db.execute('SELECT width,height FROM media WHERE id=1').fetchone(), (None, None))
