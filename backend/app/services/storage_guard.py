import os
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class StorageNotMountedError(RuntimeError):
    """Raised when an operation targets an unmounted storage path or missing sentinel."""
    pass


def get_configured_sentinel_name() -> Optional[str]:
    """Returns the globally configured sentinel filename from env, if any."""
    sentinel = os.getenv("HE_STORAGE_SENTINEL", "").strip()
    return sentinel if sentinel else None


def _find_mount_root(path: str) -> str:
    """Find the highest existing parent directory or mount root for a given path."""
    current = os.path.abspath(os.path.expanduser(path))
    while current and current != os.path.dirname(current):
        if os.path.ismount(current):
            return current
        parent = os.path.dirname(current)
        # On linux /mnt/xxx or /media/xxx is typical mount target
        if parent in {"/mnt", "/media"} and os.path.exists(current):
            return current
        current = parent
    return os.path.abspath(os.path.expanduser(path))


def is_mount_or_sentinel_valid(path: str, sentinel_name: Optional[str] = None) -> Tuple[bool, str]:
    """
    Validates whether the given path is a valid and mounted storage path.
    
    Checks:
    1. If sentinel_name (or HE_STORAGE_SENTINEL) is set, verifies that the sentinel
       file exists either in `path` or in the nearest mount root / ancestor directory.
    2. If on Linux/POSIX and path starts with /mnt/ or /media/, verifies that the mount
       target is an actual mountpoint or contains a sentinel file (.mounted/.sentinel).
    3. If HE_REQUIRE_STORAGE_MOUNT is set to '1', enforces mountpoint/sentinel validation.
    """
    if not path:
        return False, "Empty path provided"

    abs_path = os.path.abspath(os.path.expanduser(path))
    effective_sentinel = sentinel_name or get_configured_sentinel_name()
    require_mount = os.getenv("HE_REQUIRE_STORAGE_MOUNT", "0").strip().lower() in {"1", "true", "yes"}

    # Check 1: Explicit sentinel check
    if effective_sentinel:
        curr = abs_path
        found_sentinel = False
        while curr and curr != os.path.dirname(curr):
            sentinel_path = os.path.join(curr, effective_sentinel)
            if os.path.exists(sentinel_path):
                found_sentinel = True
                break
            curr = os.path.dirname(curr)
        if not found_sentinel:
            return False, f"Missing required storage sentinel '{effective_sentinel}' along path '{abs_path}'"

    # Check 2: Linux /mnt/ or /media/ guard to prevent writing to root filesystem
    if os.name != "nt" and (abs_path.startswith("/mnt/") or abs_path.startswith("/media/") or require_mount):
        # Extract mount base, e.g. /mnt/hdd from /mnt/hdd/videos/manga
        parts = [p for p in abs_path.split(os.sep) if p]
        if len(parts) >= 2 and parts[0] in {"mnt", "media"}:
            mount_root = f"/{parts[0]}/{parts[1]}"
        else:
            mount_root = _find_mount_root(abs_path)

        if not os.path.exists(mount_root):
            return False, f"Storage mount path '{mount_root}' does not exist on host"

        is_mounted = os.path.ismount(mount_root)
        # Check standard default sentinel files if not explicitly ismount
        has_default_sentinel = any(
            os.path.exists(os.path.join(mount_root, marker))
            for marker in (".mounted", ".sentinel", ".mount_sentinel")
        )

        if not is_mounted and not has_default_sentinel and not effective_sentinel:
            # If neither ismount nor sentinel found for /mnt/* path:
            # If require_mount is strict or it's a bare mount point on root filesystem
            if require_mount or not os.path.exists(abs_path):
                return False, f"Path '{abs_path}' is on unmounted storage '{mount_root}' (no mountpoint or sentinel found)"

    return True, "ok"


def ensure_storage_available(path: str, purpose: str = "write", sentinel_name: Optional[str] = None) -> None:
    """
    Raises StorageNotMountedError if the storage path is not safely mounted or accessible.
    """
    valid, reason = is_mount_or_sentinel_valid(path, sentinel_name=sentinel_name)
    if not valid:
        logger.error("Storage guard blocked %s operation on %s: %s", purpose, path, reason)
        raise StorageNotMountedError(f"Storage unavailable for {purpose}: {reason}")


def ensure_folder_scannable(folder_path: str) -> Tuple[bool, str]:
    """
    Verifies that a folder path is valid and mounted before scanning.
    Prevents empty-folder scans from accidentally marking all media as is_missing.
    """
    if not os.path.exists(folder_path):
        return False, f"Folder path does not exist: {folder_path}"

    valid, reason = is_mount_or_sentinel_valid(folder_path)
    if not valid:
        return False, f"Folder path failed storage guard check: {reason}"

    return True, "ok"
