import glob
import hashlib
import mimetypes
import os
import re
from typing import Optional
from urllib.parse import urlparse

from ... import asmr_source, downloader_push, external_sources, models, scanner

DEFAULT_EXTERNAL_DOWNLOAD_DIR = os.path.join(os.getcwd(), "external_downloads")
EXTERNAL_COVERS_DIR = os.path.abspath(os.path.join(os.getcwd(), "..", "covers"))
os.makedirs(EXTERNAL_COVERS_DIR, exist_ok=True)

HE_PUBLIC_URL = os.getenv("HE_PUBLIC_URL", "").strip().rstrip("/")
HE_CALLBACK_TOKEN = os.getenv("HE_CALLBACK_TOKEN", "").strip()


def normalize_download_root(path: Optional[str], source_type: str = "wnacg") -> str:
    raw_path = (path or "").strip()
    if not raw_path:
        raw_path = os.path.join(DEFAULT_EXTERNAL_DOWNLOAD_DIR, source_type)
    return os.path.abspath(os.path.expanduser(raw_path))


def get_external_storage_dirs(source: models.ExternalFavoriteSource, download_root_path: Optional[str] = None):
    root = normalize_download_root(
        download_root_path if download_root_path is not None else source.download_root_path,
        source.source_type or "wnacg",
    )
    covers_dir = os.path.join(EXTERNAL_COVERS_DIR, source.source_type or "wnacg")
    manga_dir = os.path.join(root, "manga")
    os.makedirs(covers_dir, exist_ok=True)
    os.makedirs(manga_dir, exist_ok=True)
    return root, covers_dir, manga_dir


def get_cover_extension(content_type: str, url: str) -> str:
    guessed = mimetypes.guess_extension((content_type or "").split(";", 1)[0].strip())
    if guessed:
        return ".jpg" if guessed == ".jpe" else guessed
    parsed_ext = os.path.splitext(urlparse(url).path)[1].lower()
    return parsed_ext if parsed_ext in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"} else ".img"


def get_image_extension(content_type: str, url: str) -> str:
    return get_cover_extension(content_type, url)


def external_cover_sidecar_rel_path(item: models.ExternalFavoriteItem) -> Optional[str]:
    cover_url = (item.cover_url or "").strip()
    if not cover_url:
        return None
    if (item.source_type or "") == "asmr":
        ext = downloader_push.url_ext(cover_url, ".jpg")
        return f"cover{ext}"
    return None


def find_external_cover_sidecar(item_dir: str) -> Optional[str]:
    image_exts = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".avif"}
    candidates = glob.glob(os.path.join(item_dir, "cover.*"))
    candidates += glob.glob(os.path.join(item_dir, ".he_cover", "cover.*"))
    for path in sorted(candidates):
        if os.path.splitext(path)[1].lower() in image_exts and os.path.isfile(path):
            return path
    return None


def ensure_asmr_cover_file(item: models.ExternalFavoriteItem, item_dir: str) -> Optional[str]:
    """Ensure item_dir has a sidecar cover.* image, downloading from
    item.cover_url when missing. Idempotent (returns the existing path if one
    is already there) and best-effort (returns None on any failure — cover is
    nice-to-have, never a download blocker).
    """
    if not item_dir or not os.path.isdir(item_dir):
        return None
    existing = scanner.get_work_cover_path(item_dir)
    if existing:
        return existing
    cover_url = (item.cover_url or "").strip()
    if not cover_url:
        return None
    try:
        content, content_type = asmr_source.fetch_file(cover_url)
    except Exception as exc:  # noqa: BLE001 — cover is nice-to-have
        print(f"  ! Failed to download cover for {item.title!r}: {exc}")
        return None
    ext = get_cover_extension(content_type, cover_url)
    cover_local = os.path.join(item_dir, f"cover{ext}")
    try:
        with open(cover_local, "wb") as cover_file:
            cover_file.write(content)
    except OSError as exc:
        print(f"  ! Failed to write cover for {item.title!r}: {exc}")
        return None
    return cover_local


def get_cover_cache_prefix(item: models.ExternalFavoriteItem) -> str:
    stable_id = item.external_id or str(item.id)
    digest = hashlib.sha1((item.cover_url or item.url or stable_id).encode("utf-8")).hexdigest()[:10]
    return f"{item.id}_{stable_id}_{digest}"


def find_cached_cover(covers_dir: str, item: models.ExternalFavoriteItem) -> Optional[str]:
    matches = glob.glob(os.path.join(covers_dir, f"{get_cover_cache_prefix(item)}.*"))
    return matches[0] if matches else None


def ensure_external_cover_cache(item: models.ExternalFavoriteItem, source: models.ExternalFavoriteSource) -> Optional[str]:
    if not (item.cover_url or "").strip():
        return None
    _, covers_dir, _ = get_external_storage_dirs(source)
    cached_cover = find_cached_cover(covers_dir, item)
    if cached_cover and os.path.exists(cached_cover):
        return cached_cover
    try:
        if (source.source_type or "") == "asmr":
            content, content_type = asmr_source.fetch_file(item.cover_url)
        else:
            content, content_type = external_sources.fetch_binary(
                item.cover_url,
                source.cookie or "",
                referer=item.url or source.favorites_url,
                proxy=source.proxy,
            )
    except Exception as exc:  # noqa: BLE001
        print(f"  ! Failed to cache external cover for {item.title!r}: {exc}")
        return None
    extension = get_cover_extension(content_type, item.cover_url)
    cover_path = os.path.join(covers_dir, f"{get_cover_cache_prefix(item)}{extension}")
    try:
        with open(cover_path, "wb") as cover_file:
            cover_file.write(content)
    except OSError as exc:
        print(f"  ! Failed to write external cover cache for {item.title!r}: {exc}")
        return None
    return cover_path


def safe_filename(value: str, fallback: str = "item") -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value or "").strip()
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return (cleaned or fallback)[:120]


def get_asmr_storage_dirs(source: models.ExternalFavoriteSource, download_root_path: Optional[str] = None):
    root = normalize_download_root(
        download_root_path if download_root_path is not None else source.download_root_path,
        source.source_type or "asmr",
    )
    audio_dir = os.path.join(root, "audio")
    os.makedirs(audio_dir, exist_ok=True)
    return root, audio_dir


def external_item_download_dir(item: models.ExternalFavoriteItem, source: models.ExternalFavoriteSource, download_root_path: Optional[str] = None) -> str:
    """Compute an item path without creating directories (safe for GET paths)."""
    source_type = source.source_type or "wnacg"
    root = normalize_download_root(
        download_root_path if download_root_path is not None else source.download_root_path,
        source_type,
    )
    if source_type == "asmr":
        audio_dir = os.path.join(root, "audio")
        return os.path.join(audio_dir, f"{safe_filename(item.title, 'asmr')}_{item.external_id}")
    manga_dir = os.path.join(root, "manga")
    return os.path.join(manga_dir, f"{safe_filename(item.title, 'wnacg')}_{item.external_id}")


def get_url_base(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return external_sources.WNACG_BASE_URL
    return f"{parsed.scheme}://{parsed.netloc}/"
