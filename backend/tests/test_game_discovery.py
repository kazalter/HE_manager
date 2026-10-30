import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.scanners import runner
from app.scanners.game import game_launchers, suggested_launcher
from app.routers import games


class GameDiscoveryTest(unittest.TestCase):
    def test_discovery_filters_utilities_and_never_follows_executable_symlinks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("startup.exe", "dohnadohna.exe", "ResetConfig.exe", "UnityCrashHandler64.exe"):
                (root / name).touch()
            try:
                (root / "linked.exe").symlink_to(root / "dohnadohna.exe")
            except OSError:
                # Windows often requires an extra privilege to create symlinks.
                pass
            self.assertEqual(game_launchers(tmp), ["dohnadohna.exe", "startup.exe"])
            self.assertEqual(suggested_launcher(game_launchers(tmp)), "startup.exe")
            self.assertIsNone(suggested_launcher(["a.exe", "b.exe"]))

    def test_game_scan_indexes_one_directory_without_executing_files(self):
        engine = create_engine("sqlite:///:memory:")
        models.Base.metadata.create_all(bind=engine)
        Session = sessionmaker(bind=engine)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game = root / "Game A" / "release"
            game.mkdir(parents=True)
            (game / "startup.exe").write_bytes(b"not executable during scanning")
            (game / "ResetConfig.exe").write_bytes(b"helper")
            nested = game / "data"
            nested.mkdir()
            (nested / "helper.exe").write_bytes(b"not a second game")
            db = Session()
            folder = models.Folder(path=tmp, scan_mode="game")
            db.add(folder)
            db.commit()
            folder_id = folder.id
            with patch.object(runner.database, "SessionLocal", Session), \
                 patch.object(runner, "ensure_folder_scannable", return_value=(True, "")), \
                 patch.object(runner.os, "getcwd", return_value=tmp):
                self.assertTrue(runner.scan_folder(folder_id))
                self.assertTrue(runner.scan_folder(folder_id))
            db.expire_all()
            items = db.query(models.Media).all()
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0].absolute_path, str(game))
            self.assertEqual(items[0].media_type, "game")
            self.assertEqual(items[0].duplicate_status, "unique")
            self.assertFalse(items[0].is_missing)
            with patch.object(games, "ensure_folder_scannable", return_value=(True, "")):
                result = games.list_game_launchers(items[0].id, db=db)
            self.assertEqual(result, {"launchers": ["startup.exe"], "suggested": "startup.exe"})
            db.close()
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
