"""Deletion tests use only disposable databases and files, never production data."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app import models
from app.services import media_discard as service
from app.services.media_operation_guard import project_mutation
from app.services.external import matching, wnacg
from app.x_import import importer


class MediaDiscardTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.engine = create_engine('sqlite:///' + str(self.root / 'test.db'))
        @event.listens_for(self.engine, 'connect')
        def foreign_keys(conn, _):
            conn.execute('PRAGMA foreign_keys=ON')
        models.Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False)
        self.db = self.Session()
        self.folder = models.Folder(path=str(self.root / 'library'), scan_mode='image')
        Path(self.folder.path).mkdir()
        self.db.add(self.folder); self.db.commit()
        self.guard = patch('app.services.storage_guard.ensure_folder_scannable', return_value=(True, ''))
        self.guard.start()

    def tearDown(self):
        self.db.close(); self.engine.dispose(); self.guard.stop(); self.temp.cleanup()

    def media(self, name='one.jpg', source_url=None, source_site=None):
        path = Path(self.folder.path) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'disposable media')
        row = models.Media(folder_id=self.folder.id, title=name, absolute_path=str(path),
            relative_path=name, media_type='image', extension='.jpg', file_size=path.stat().st_size,
            source_url=source_url, source_site=source_site)
        self.db.add(row); self.db.commit(); return row, path

    def discard(self, kind, target_id):
        preview = service.build_plan(self.db, kind, target_id)
        return service.discard(self.db, kind, target_id, preview['preview_hash'])

    def x_post(self):
        source = models.XImportSource(download_root_path=str(self.root))
        post = models.XPost(source=source, tweet_id='123456', url='https://x.com/u/status/123456', status='completed')
        self.db.add(post); self.db.commit()
        rows = []
        for i in range(2):
            media, path = self.media(f'x-{i}.jpg', post.url, 'x')
            item = models.XMediaItem(post=post, media_index=i, media_type='image', local_path=str(path),
                status='downloaded', library_media_id=media.id)
            self.db.add(item); rows.append((media, path, item))
        self.db.commit(); return post, rows

    def test_delete_bytes_and_keep_tombstone_after_new_session(self):
        media, path = self.media()
        sibling, sibling_path = self.media('two.jpg')
        media_id = media.id
        result = self.discard('media', media_id)
        self.assertEqual(result['cleanup_status'], 'completed')
        self.assertEqual(result['media_ids'], [media_id])
        self.assertFalse(path.exists()); self.assertTrue(sibling_path.exists())
        self.db.close(); self.db = self.Session()
        self.assertIsNone(self.db.get(models.Media, media_id))
        self.assertTrue(service.has_identity(self.db, service.path_key(str(path))))
        self.assertEqual(self.db.query(models.DiscardedContent).count(), 1)

    def test_preview_never_deletes_and_stale_confirmation_is_rejected(self):
        media, path = self.media()
        preview = service.build_plan(self.db, 'media', media.id)
        self.assertTrue(path.exists())
        path.write_bytes(b'changed content with different size')
        with self.assertRaises(HTTPException) as exc:
            service.discard(self.db, 'media', media.id, preview['preview_hash'])
        self.assertEqual(exc.exception.status_code, 409)
        self.assertTrue(path.exists()); self.assertEqual(self.db.query(models.DiscardedContent).count(), 0)

    def test_folder_root_outside_and_symlink_are_refused(self):
        media, path = self.media()
        for target in [self.folder.path, str(self.root / 'outside.jpg')]:
            media.absolute_path = target; self.db.commit()
            with self.assertRaises(HTTPException): service.build_plan(self.db, 'media', media.id)
        link = Path(self.folder.path) / 'link.jpg'
        link.symlink_to(path)
        media.absolute_path = str(link); self.db.commit()
        with self.assertRaises(HTTPException): service.build_plan(self.db, 'media', media.id)
        self.assertTrue(path.exists())

    def test_shared_work_folder_cannot_delete_unselected_media(self):
        parent, _ = self.media('parent.jpg')
        child, path = self.media('work/child.jpg')
        parent.absolute_path = str(path.parent); parent.extension = '.dir'
        self.db.commit()
        with self.assertRaises(HTTPException): service.build_plan(self.db, 'media', parent.id)
        self.assertTrue(path.exists())

    def test_directory_cleanup_deletes_entire_work(self):
        media, path = self.media('work/page.jpg')
        media.absolute_path = str(path.parent); media.extension = '.dir'
        self.db.commit()
        result = self.discard('media', media.id)
        self.assertEqual(result['cleanup_status'], 'completed')
        self.assertFalse(path.parent.exists())

    def test_failure_keeps_discard_and_retry_cleans_original_file(self):
        media, path = self.media()
        with patch.object(service.os, 'remove', side_effect=PermissionError('test only')):
            result = self.discard('media', media.id)
        self.assertEqual(result['cleanup_status'], 'failed')
        self.assertTrue(path.exists())
        self.assertTrue(service.has_identity(self.db, service.path_key(str(path))))
        with self.assertRaises(HTTPException): service.allow_download(self.db, result['id'])
        result = service.retry_cleanup(self.db, result['id'])
        self.assertEqual(result['cleanup_status'], 'completed'); self.assertFalse(path.exists())
        self.assertEqual(service.retry_cleanup(self.db, result['id'])['cleanup_status'], 'completed')

    def test_retry_will_not_delete_replaced_file(self):
        media, path = self.media()
        with patch.object(service.os, 'remove', side_effect=PermissionError('test only')):
            result = self.discard('media', media.id)
        path.write_bytes(b'a replacement file')
        self.assertEqual(service.retry_cleanup(self.db, result['id'])['cleanup_status'], 'failed')
        self.assertEqual(path.read_bytes(), b'a replacement file')

    def test_delete_is_blocked_while_downloader_holds_mutation_lease(self):
        media, path = self.media()
        with project_mutation():
            with self.assertRaises(HTTPException) as exc: self.discard('media', media.id)
        self.assertEqual(exc.exception.status_code, 409); self.assertTrue(path.exists())

    def test_wnacg_source_identity_blocks_new_url_host_and_download_root(self):
        media, path = self.media(source_url='https://www.wnacg.com/photos-index-aid-99.html', source_site='wnacg')
        self.discard('media', media.id)
        source = models.ExternalFavoriteSource(source_type='wnacg', favorites_url='https://another.test/', download_root_path=str(self.root / 'another'))
        item = models.ExternalFavoriteItem(source=source, source_type='wnacg', external_id='99', title='Changed title', url='https://another.test/photos-index-aid-99.html')
        self.db.add(item); self.db.commit()
        self.assertEqual(matching.serialize_external_favorite_items([item], self.db)[0]['status'], 'discarded')
        with patch('app.external_sources.fetch_html') as fetch:
            with self.assertRaises(HTTPException): wnacg.prepare_wnacg_download_plan(item, source, str(self.root))
            fetch.assert_not_called()
        self.assertIsNone(matching.find_local_media_for_external_item(item, self.db))

    def test_undownloaded_favorite_can_be_discarded_and_resync_keeps_it(self):
        source = models.ExternalFavoriteSource(source_type='wnacg')
        item = models.ExternalFavoriteItem(source=source, source_type='wnacg', external_id='99', title='Book', url='https://www.wnacg.com/photos-index-aid-99.html')
        self.db.add(item); self.db.commit()
        result = self.discard('external', item.id)
        self.assertEqual(result['media_count'], 0)
        item.title = 'Title after next sync'; self.db.commit()
        self.assertEqual(matching.serialize_external_favorite_items([item], self.db)[0]['status'], 'discarded')

    def test_single_x_attachment_does_not_delete_other_attachment(self):
        post, rows = self.x_post()
        result = self.discard('media', rows[0][0].id)
        self.db.expire_all()
        self.assertEqual(rows[0][2].status, 'discarded')
        self.assertIsNone(rows[0][2].library_media_id)
        self.assertFalse(rows[0][1].exists()); self.assertTrue(rows[1][1].exists())
        self.assertTrue(service.has_identity(self.db, f'x:{post.tweet_id}:0'))
        self.assertFalse(service.has_identity(self.db, f'x:{post.tweet_id}:*'))
        self.assertEqual(post.status, 'completed')
        service.allow_download(self.db, result['id'])
        self.assertEqual(post.status, 'pending')

    def test_whole_x_post_discards_all_attachments_and_never_fetches(self):
        post, rows = self.x_post()
        result = self.discard('x_post', post.id)
        self.assertEqual(result['media_count'], 2)
        self.db.expire_all()
        self.assertEqual(post.status, 'discarded')
        self.assertTrue(all(not path.exists() for _, path, _ in rows))
        post.status = 'pending'; self.db.commit()  # Even accidental reset is blocked by identity.
        self.assertEqual(importer.select_pending_post_ids(self.db, post.source_id), [])
        job = importer.ImportJob(job_id='test', source_id=post.source_id, download_root=str(self.root), thumbnail_dir=str(self.root))
        with patch.object(importer.client, 'fetch_tweet') as fetch:
            importer._process_post(job, post.id, self.db, self.folder)
            fetch.assert_not_called()

    def test_local_scan_skips_discarded_path_if_file_reappears(self):
        media, path = self.media()
        self.discard('media', media.id)
        path.write_bytes(b'recreated by an external program')
        from app.scanners import runner
        with patch.object(runner.database, 'SessionLocal', self.Session), patch.object(runner.dedup_worker, 'enqueue'):
            self.assertTrue(runner.scan_folder(self.folder.id))
        self.db.expire_all()
        self.assertEqual(self.db.query(models.Media).count(), 0)

    def test_restart_recovers_committed_pending_cleanup(self):
        media, path = self.media()
        with patch.object(service, '_cleanup', side_effect=RuntimeError('simulated crash')):
            with self.assertRaises(RuntimeError): self.discard('media', media.id)
        self.assertTrue(path.exists()); self.assertEqual(self.db.query(models.DiscardedContent).one().cleanup_status, 'pending')
        with patch.object(service.database, 'SessionLocal', self.Session): service.recover_pending_cleanup()
        self.db.expire_all()
        self.assertFalse(path.exists()); self.assertEqual(self.db.query(models.DiscardedContent).one().cleanup_status, 'completed')

    def test_allow_download_removes_source_block_but_does_not_restore_bytes(self):
        media, path = self.media(source_url='https://www.wnacg.com/photos-index-aid-99.html', source_site='wnacg')
        result = self.discard('media', media.id)
        service.allow_download(self.db, result['id'])
        self.assertFalse(service.has_identity(self.db, 'wnacg:99'))
        self.assertFalse(path.exists()); self.assertEqual(self.db.query(models.DiscardedContent).count(), 0)

    def test_nested_file_change_invalidates_directory_preview(self):
        media, path = self.media('work/nested/page.jpg')
        media.absolute_path = str(path.parent.parent); self.db.commit()
        preview = service.build_plan(self.db, 'media', media.id)
        path.write_bytes(b'nested replacement')
        with self.assertRaises(HTTPException):
            service.discard(self.db, 'media', media.id, preview['preview_hash'])
        self.assertTrue(path.exists())

    def test_wnacg_source_marker_blocks_import_at_another_path(self):
        media, _ = self.media(source_url='https://www.wnacg.com/photos-index-aid-99.html', source_site='wnacg')
        self.discard('media', media.id)
        root = Path(self.folder.path) / 'relocated-book'; root.mkdir()
        (root / 'source.txt').write_text('Book\nhttps://other.test/photos-index-aid-99.html')
        (root / 'page.jpg').write_bytes(b'page')
        self.folder.scan_mode = 'manga'; self.db.commit()
        from app.scanners import runner
        with patch.object(runner.database, 'SessionLocal', self.Session), patch.object(runner.dedup_worker, 'enqueue'):
            self.assertTrue(runner.scan_folder(self.folder.id))
        self.db.expire_all(); self.assertEqual(self.db.query(models.Media).count(), 0)

    def test_x_retry_does_not_download_discarded_attachment(self):
        from types import SimpleNamespace
        post, rows = self.x_post()
        self.discard('media', rows[0][0].id)
        post.status = 'failed'; self.db.commit()
        tweet = SimpleNamespace(author_screen_name='u', author_name='User', full_text='text', posted_at=None,
            media=[SimpleNamespace(media_index=i) for i in range(2)])
        job = importer.ImportJob(job_id='test', source_id=post.source_id, download_root=str(self.root), thumbnail_dir=str(self.root))
        with patch.object(importer.client, 'fetch_tweet', return_value=tweet), patch.object(importer.client, 'download_media') as download:
            importer._process_post(job, post.id, self.db, self.folder)
            download.assert_not_called()
        self.db.expire_all(); self.assertEqual(rows[0][2].status, 'discarded')
        self.assertTrue(rows[1][1].exists())

    def test_http_requires_admin_explicit_confirmation_and_preview_hash(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app import auth
        from app.database import get_db
        from app.routers.discard import router
        app = FastAPI(); app.include_router(router)
        app.dependency_overrides[get_db] = lambda: self.db
        app.dependency_overrides[auth.get_current_user] = lambda: models.User(id=1, is_admin=False)
        media, path = self.media()
        with TestClient(app) as client:
            self.assertEqual(client.post('/discard/preview', json={'kind':'media', 'target_id':media.id}).status_code, 403)
            app.dependency_overrides[auth.get_current_user] = lambda: models.User(id=1, is_admin=True)
            preview = client.post('/discard/preview', json={'kind':'media', 'target_id':media.id})
            self.assertEqual(preview.status_code, 200)
            payload={'kind':'media', 'target_id':media.id, 'preview_hash':preview.json()['preview_hash']}
            self.assertEqual(client.post('/discard', json=payload).status_code, 400)
            payload['confirm']=True; payload.pop('preview_hash')
            self.assertEqual(client.post('/discard', json=payload).status_code, 422)
        self.assertTrue(path.exists()); self.assertEqual(self.db.query(models.DiscardedContent).count(), 0)

    def test_downloader_callback_cannot_reimport_discarded_favorite(self):
        from app.routers.external import downloader
        source = models.ExternalFavoriteSource(source_type='wnacg')
        item = models.ExternalFavoriteItem(source=source, source_type='wnacg', external_id='99', title='Book', url='https://wnacg.test/photos-index-aid-99.html')
        self.db.add(item); self.db.commit(); self.discard('external', item.id)
        with patch.object(downloader, 'HE_CALLBACK_TOKEN', None), patch.object(downloader, 'upsert_external_downloaded_media') as upsert:
            with self.assertRaises(HTTPException) as exc:
                downloader.downloader_callback({'event':'complete'}, item.id, db=self.db)
            self.assertEqual(exc.exception.status_code, 409); upsert.assert_not_called()

    def test_wnacg_auto_sync_does_not_schedule_discarded_favorite(self):
        from app.services.auto_sync import wnacg as worker
        from app import external_sources
        from app.services import external_runtime
        source = models.ExternalFavoriteSource(source_type='wnacg', cookie='test-only',
            favorites_url='https://wnacg.test/favorites', download_root_path=str(self.root))
        item = models.ExternalFavoriteItem(source=source, source_type='wnacg', external_id='99', title='Book', url='https://wnacg.test/photos-index-aid-99.html')
        self.db.add(item); self.db.commit(); self.discard('external', item.id)
        with patch.object(worker.database, 'SessionLocal', self.Session), patch.object(worker, 'is_mount_or_sentinel_valid', return_value=(True, '')):
            with patch.object(external_sources, 'fetch_html', return_value=''), patch.object(external_sources, 'parse_wnacg_categories', return_value=[]), patch.object(external_sources, 'parse_wnacg_favorites', return_value=[]):
                with patch.object(external_runtime, 'download_wnacg_item') as download:
                    worker._run_wnacg(source.id)
                    download.assert_not_called()
        self.db.expire_all()
        self.assertEqual(source.auto_sync_last_status, 'success')
        self.assertEqual(self.db.query(models.AutoSyncLog).one().downloaded_count, 0)

if __name__ == '__main__': unittest.main()
