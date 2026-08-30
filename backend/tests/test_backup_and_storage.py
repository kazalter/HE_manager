import os
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import database, models
from app.main import app
from app.services import backup, storage_guard
from app.scanners import runner as scanner_runner


class BackupAndStorageGuardTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp.name, "library.db")
        self.backup_dir = os.path.join(self.tmp.name, "backups")

        # Initialize real SQLite db with schema and a test folder/media
        conn = sqlite3.connect(self.db_path)
        conn.execute("CREATE TABLE test_table (id INTEGER PRIMARY KEY, name TEXT)")
        conn.execute("INSERT INTO test_table (name) VALUES ('media_item_1')")
        conn.commit()
        conn.close()

    def tearDown(self):
        self.tmp.cleanup()

    def test_backup_creates_consistent_sqlite_copy_and_rotates(self):
        # Create 5 backups with keep_count=3
        for i in range(5):
            time.sleep(0.01)
            res = backup.backup_database(self.db_path, backup_dir=self.backup_dir, keep_count=3)
            self.assertTrue(res["success"])
            self.assertTrue(os.path.isfile(res["backup_path"]))

        backups = backup.list_backups(self.backup_dir)
        self.assertEqual(len(backups), 3)

        # Verify content in the latest backup
        latest_backup = backups[0]["path"]
        b_conn = sqlite3.connect(latest_backup)
        row = b_conn.execute("SELECT name FROM test_table WHERE id=1").fetchone()
        b_conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], "media_item_1")

    def test_backup_freshness_detection(self):
        # 1. No backups
        freshness = backup.check_backup_freshness(self.backup_dir, max_age_hours=24.0)
        self.assertFalse(freshness["healthy"])
        self.assertTrue(freshness["stale"])
        self.assertEqual(freshness["total_backups"], 0)

        # 2. Fresh backup
        res = backup.backup_database(self.db_path, backup_dir=self.backup_dir, keep_count=3)
        freshness_fresh = backup.check_backup_freshness(self.backup_dir, max_age_hours=24.0)
        self.assertTrue(freshness_fresh["healthy"])
        self.assertFalse(freshness_fresh["stale"])
        self.assertIsNotNone(freshness_fresh["latest_backup"])

        # 3. Modify mtime to simulate an old backup (e.g. 48 hours ago)
        old_time = time.time() - (48 * 3600)
        os.utime(res["backup_path"], (old_time, old_time))
        freshness_stale = backup.check_backup_freshness(self.backup_dir, max_age_hours=24.0)
        self.assertFalse(freshness_stale["healthy"])
        self.assertTrue(freshness_stale["stale"])
        self.assertGreater(freshness_stale["age_hours"], 24.0)

    def test_storage_guard_sentinel_validation(self):
        mount_test_dir = os.path.join(self.tmp.name, "simulated_hdd")
        os.makedirs(mount_test_dir, exist_ok=True)
        sub_dir = os.path.join(mount_test_dir, "downloads", "manga")

        # Case A: Sentinel explicitly required but missing
        with patch.dict(os.environ, {"HE_STORAGE_SENTINEL": ".mounted"}):
            valid, reason = storage_guard.is_mount_or_sentinel_valid(sub_dir)
            self.assertFalse(valid)
            self.assertIn("Missing required storage sentinel", reason)

            with self.assertRaises(storage_guard.StorageNotMountedError):
                storage_guard.ensure_storage_available(sub_dir, purpose="test_write")

            # Case B: Sentinel created at mount root
            sentinel_path = os.path.join(mount_test_dir, ".mounted")
            with open(sentinel_path, "w") as f:
                f.write("ok")

            valid_with_sentinel, reason_ok = storage_guard.is_mount_or_sentinel_valid(sub_dir)
            self.assertTrue(valid_with_sentinel)
            self.assertEqual(reason_ok, "ok")

    def test_scanner_runner_skips_when_storage_unmounted_without_dropping_media(self):
        non_existent_folder = os.path.join(self.tmp.name, "missing_hdd_dir")
        is_scannable, reason = storage_guard.ensure_folder_scannable(non_existent_folder)
        self.assertFalse(is_scannable)
        self.assertIn("does not exist", reason)

    def test_system_backup_endpoints(self):
        # Mock admin auth
        admin_user = models.User(id=1, username="admin", is_admin=True, is_active=True)
        with patch("app.auth.authenticate_access_token", return_value=admin_user):
            client = TestClient(app)
            headers = {"Authorization": "Bearer fake-token"}

            # Test GET /system/storage/status
            resp_storage = client.get("/system/storage/status", headers=headers)
            self.assertEqual(resp_storage.status_code, 200)
            data = resp_storage.json()
            self.assertIn("configured_sentinel", data)

            # Test GET /system/backup/status
            resp_backup_status = client.get("/system/backup/status", headers=headers)
            self.assertEqual(resp_backup_status.status_code, 200)
            status_data = resp_backup_status.json()
            self.assertIn("freshness", status_data)
            self.assertIn("backups", status_data)


if __name__ == "__main__":
    unittest.main()
