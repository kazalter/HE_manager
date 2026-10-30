import tempfile
import unittest
from collections import namedtuple
from pathlib import Path
from unittest.mock import patch

from app.services.game_workspace import GameWorkspaceError, prepare_game_copy


class GameWorkspaceTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.mount = Path(self.temp.name)
        self.library = self.mount / "library"
        self.source = self.library / "game"
        self.source.mkdir(parents=True)
        (self.source / "game.exe").write_bytes(b"game")
        self.workspaces = self.mount / "workspaces"

    def tearDown(self):
        self.temp.cleanup()

    def prepare(self):
        with patch("app.services.game_workspace._is_system_filesystem", return_value=False):
            return prepare_game_copy(self.library, self.source, self.mount, self.workspaces, reserve_bytes=10)

    def test_unmounted_disk_is_rejected_before_creating_a_directory(self):
        with patch("app.services.game_workspace.os.path.ismount", return_value=False):
            with self.assertRaises(GameWorkspaceError):
                self.prepare()
        self.assertFalse(self.workspaces.exists())

    def test_low_space_is_rejected_without_a_partial_copy(self):
        usage = namedtuple("usage", "total used free")(100, 90, 10)
        with patch("app.services.game_workspace.os.path.ismount", return_value=True), \
             patch("app.services.game_workspace.shutil.disk_usage", return_value=usage):
            with self.assertRaises(GameWorkspaceError):
                self.prepare()
        self.assertEqual(list(self.workspaces.iterdir()), [])

    def test_system_disk_is_rejected(self):
        with patch("app.services.game_workspace.os.path.ismount", return_value=True):
            with self.assertRaises(GameWorkspaceError):
                prepare_game_copy(self.library, self.source, self.mount, self.workspaces, reserve_bytes=0)

    def test_copy_is_reused_and_never_overwrites_player_changes(self):
        with patch("app.services.game_workspace.os.path.ismount", return_value=True):
            result = self.prepare()
            (result / "save.dat").write_bytes(b"save")
            (self.source / "game.exe").write_bytes(b"new source")
            self.assertEqual(self.prepare(), result)
        self.assertEqual((result / "game.exe").read_bytes(), b"game")
        self.assertEqual((result / "save.dat").read_bytes(), b"save")

    def test_symlinked_content_is_rejected(self):
        try:
            (self.source / "link").symlink_to(self.mount)
        except OSError:
            self.skipTest("symlinks unavailable on this platform")
        with patch("app.services.game_workspace.os.path.ismount", return_value=True):
            with self.assertRaises(GameWorkspaceError):
                self.prepare()

    def test_source_outside_library_and_workspace_outside_mount_are_rejected(self):
        with patch("app.services.game_workspace.os.path.ismount", return_value=True), \
             patch("app.services.game_workspace._is_system_filesystem", return_value=False):
            with self.assertRaises(GameWorkspaceError):
                prepare_game_copy(self.library, self.mount, self.mount, self.workspaces, reserve_bytes=0)
            with self.assertRaises(GameWorkspaceError):
                prepare_game_copy(self.library, self.source, self.mount, self.mount.parent / "outside", reserve_bytes=0)


if __name__ == "__main__":
    unittest.main()
