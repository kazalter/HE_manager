"""Safely prepare persistent game copies on the designated game disk.

This module does not run a game.  A future runner can use the resulting copy
without granting the game write access to the original media library.
"""

import hashlib
import os
from pathlib import Path
import shutil
import uuid


class GameWorkspaceError(RuntimeError):
    pass


def _is_system_filesystem(mount: Path) -> bool:
    system_root = Path(os.environ.get("SystemDrive", "C:") + os.sep) if os.name == "nt" else Path(os.sep)
    return mount.stat().st_dev == system_root.stat().st_dev


def _contained_directory(root: Path, source: Path) -> tuple[Path, Path]:
    if source.is_symlink():
        raise GameWorkspaceError("游戏目录不能是符号链接")
    root = root.resolve(strict=True)
    source = source.resolve(strict=True)
    if not root.is_dir() or not source.is_dir() or source == root or root not in source.parents:
        raise GameWorkspaceError("游戏目录必须位于指定游戏库内")
    return root, source


def _tree_size_and_validate(source: Path) -> int:
    total = 0
    for current, directories, filenames in os.walk(source, followlinks=False):
        for name in directories + filenames:
            item = Path(current, name)
            if item.is_symlink():
                raise GameWorkspaceError("游戏目录包含符号链接，无法安全复制")
        for name in filenames:
            item = Path(current, name)
            if not item.is_file():
                raise GameWorkspaceError("游戏目录包含不支持的文件类型")
            total += item.stat().st_size
    return total


def prepare_game_copy(library_root: Path, source: Path, storage_mount: Path,
                      workspace_root: Path, *, reserve_bytes: int = 4 * 1024**3) -> Path:
    """Copy once and retain the copy; require the designated disk to be mounted.

    Copies are staged beside their final destination and renamed only after a
    successful copy. Failed staging is left in place for explicit recovery;
    an existing workspace is never overwritten or removed.
    """
    if reserve_bytes < 0:
        raise ValueError("reserve_bytes must not be negative")
    mount = storage_mount.resolve(strict=True)
    if not os.path.ismount(mount):
        raise GameWorkspaceError("游戏存储磁盘未挂载")
    if _is_system_filesystem(mount):
        raise GameWorkspaceError("游戏工作目录不能使用系统磁盘")
    _root, source = _contained_directory(library_root, source)
    workspace_root = workspace_root.resolve(strict=False)
    if workspace_root == mount or mount not in workspace_root.parents:
        raise GameWorkspaceError("游戏工作目录必须位于指定磁盘内")
    if source == workspace_root or source in workspace_root.parents or workspace_root in source.parents:
        raise GameWorkspaceError("游戏库和工作目录不能相互包含")
    workspace_root.mkdir(parents=True, exist_ok=True)
    identity = hashlib.sha256(os.fsencode(str(source))).hexdigest()[:24]
    target = workspace_root / identity
    lock = workspace_root / f".lock-{identity}"
    try:
        lock.mkdir()
    except FileExistsError as exc:
        raise GameWorkspaceError("该游戏的工作目录正在准备中") from exc
    try:
        if target.exists() or target.is_symlink():
            if target.is_symlink() or not target.is_dir():
                raise GameWorkspaceError("现有游戏工作目录无效")
            return target
        size = _tree_size_and_validate(source)
        if shutil.disk_usage(workspace_root).free < size + reserve_bytes:
            raise GameWorkspaceError("游戏磁盘空间不足，已保留安全余量")
        staged = workspace_root / f".staging-{identity}-{uuid.uuid4().hex}"
        shutil.copytree(source, staged, symlinks=True)
        if _tree_size_and_validate(staged) != size:
            raise GameWorkspaceError("复制期间游戏文件发生变化，请检查暂存目录")
        os.rename(staged, target)
        return target
    finally:
        lock.rmdir()
