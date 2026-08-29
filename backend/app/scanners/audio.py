import json
import os
from typing import Optional
from PIL import Image

from .common import AUDIO_EXTENSIONS, IMAGE_EXTENSIONS


def has_audio_file_recursive(work_root: str) -> bool:
    """True iff `work_root` contains at least one audio file at any depth."""
    for _, _, files in os.walk(work_root):
        for file in files:
            if os.path.splitext(file)[1].lower() in AUDIO_EXTENSIONS:
                return True
    return False


def read_tracks_json(work_root: str) -> Optional[dict]:
    """Try to load the ASMR-downloader-style tracks.json sitting at the work
    root. Returns the parsed dict on success, None on missing / corrupt file.
    """
    path = os.path.join(work_root, "tracks.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:  # noqa: BLE001 - any parse / IO failure is "no manifest"
        print(f"  ! Failed to parse tracks.json at {path}: {exc}")
        return None


def count_audio_tracks(work_root: str) -> int:
    """How many audio files inside this work root (any depth)."""
    total = 0
    for _, _, files in os.walk(work_root):
        total += sum(1 for f in files if os.path.splitext(f)[1].lower() in AUDIO_EXTENSIONS)
    return total


def get_work_cover_path(work_root: str) -> Optional[str]:
    """First image directly inside the work root, used as the audio_work thumbnail source."""
    try:
        for entry in sorted(os.listdir(work_root)):
            ext = os.path.splitext(entry)[1].lower()
            if ext in IMAGE_EXTENSIONS:
                return os.path.join(work_root, entry)
    except OSError:
        pass
    return None


def make_work_thumbnail(cover_path: str, thumb_path: str) -> bool:
    """Copy/resize an existing cover file into the thumbnail cache."""
    try:
        img = Image.open(cover_path)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        img.thumbnail((400, 600))
        img.save(thumb_path, "JPEG")
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"Error generating work thumbnail: {exc}")
        return False
