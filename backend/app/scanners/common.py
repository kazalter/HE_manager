import os
import threading
from typing import Optional

from ..dedup import normalize as dedup_normalize

# Supported extensions
VIDEO_EXTENSIONS = {'.mp4', '.mkv', '.avi', '.mov', '.wmv', '.webm', '.flv', '.ts', '.m4v'}
MANGA_EXTENSIONS = {'.zip', '.cbz'}
IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.bmp', '.gif', '.avif'}
AUDIO_EXTENSIONS = {'.mp3', '.wav', '.flac', '.m4a', '.aac', '.ogg', '.opus'}

# Folders to skip (case-insensitive)
SKIP_FOLDERS = {'mask', 'result', 'inpainted', '.thumbnails', '.he_cover', 'node_modules', '.git', '.vite'}

# Thumbnail extraction and sprite/VTT generation both decode video. Sharing one
# semaphore caps their combined CPU and disk pressure instead of limiting each
# operation independently.
VIDEO_PREVIEW_SEMAPHORE = threading.BoundedSemaphore(value=2)

# A single uvicorn worker serves the production container. Reservations are
# claimed by the request handler before the BackgroundTask starts, closing the
# duplicate-click race where two scans could otherwise be queued together.
_FOLDER_SCAN_RESERVATIONS: dict[int, object] = {}
_FOLDER_SCAN_RESERVATIONS_LOCK = threading.Lock()


def reserve_folder_scan(folder_id: int) -> object | None:
    """Reserve a folder scan, returning an opaque token or ``None`` if busy."""
    folder_id = int(folder_id)
    with _FOLDER_SCAN_RESERVATIONS_LOCK:
        if folder_id in _FOLDER_SCAN_RESERVATIONS:
            return None
        token = object()
        _FOLDER_SCAN_RESERVATIONS[folder_id] = token
        return token


def release_folder_scan(folder_id: int, token: object) -> None:
    """Release only the reservation represented by *token*."""
    folder_id = int(folder_id)
    with _FOLDER_SCAN_RESERVATIONS_LOCK:
        if _FOLDER_SCAN_RESERVATIONS.get(folder_id) is token:
            del _FOLDER_SCAN_RESERVATIONS[folder_id]


def _owns_folder_scan_reservation(folder_id: int, token: object) -> bool:
    with _FOLDER_SCAN_RESERVATIONS_LOCK:
        return _FOLDER_SCAN_RESERVATIONS.get(int(folder_id)) is token


def directory_size(root: str) -> int:
    """Sum of file sizes under `root`, recursively, in bytes."""
    total = 0
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d.lower() not in SKIP_FOLDERS]
        for name in files:
            try:
                total += os.path.getsize(os.path.join(dirpath, name))
            except OSError:
                continue
    return total


def should_skip_dir(path: str) -> bool:
    parts = {part.lower() for part in path.split(os.sep)}
    return bool(parts & SKIP_FOLDERS)


def has_image_file(files: list[str]) -> bool:
    return any(os.path.splitext(file)[1].lower() in IMAGE_EXTENSIONS for file in files)


def media_type_for_extension(scan_mode: str, ext: str) -> Optional[str]:
    if scan_mode == "video" and ext in VIDEO_EXTENSIONS:
        return "video"
    if scan_mode == "image" and ext in IMAGE_EXTENSIONS:
        return "image"
    if scan_mode == "audio" and ext in AUDIO_EXTENSIONS:
        return "audio"
    if scan_mode == "auto":
        if ext in VIDEO_EXTENSIONS:
            return "video"
        if ext in MANGA_EXTENSIONS:
            return "manga"
        if ext in IMAGE_EXTENSIONS:
            return "image"
        if ext in AUDIO_EXTENSIONS:
            return "audio"
    return None


def apply_local_dedup_precheck(
    media: object,
    library_title_index: set,
    pending_dedup_paths: list,
) -> None:
    """Compute the normalized title and decide whether this entry needs the dedup worker."""
    norm = dedup_normalize.normalize_title(getattr(media, "title", "") or "")
    setattr(media, "normalized_title", norm)
    if norm and norm in library_title_index:
        setattr(media, "duplicate_status", "checking")
        pending_dedup_paths.append(getattr(media, "absolute_path", ""))
    else:
        setattr(media, "duplicate_status", "unique")
    if norm:
        library_title_index.add(norm)
