import os
import zipfile

from PIL import Image

from .. import models

_MANGA_FILES_CACHE: dict[int, tuple[float, list[str]]] = {}


def get_manga_image_files(media: models.Media):
    image_exts = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".avif"}
    try:
        mtime = os.path.getmtime(media.absolute_path)
    except OSError:
        mtime = 0.0
    cached = _MANGA_FILES_CACHE.get(media.id)
    if cached and cached[0] == mtime:
        return cached[1]

    if media.extension == ".dir":
        files = []
        for root, _, filenames in os.walk(media.absolute_path):
            for filename in filenames:
                if any(filename.lower().endswith(ext) for ext in image_exts):
                    files.append(os.path.join(root, filename))
        result = sorted(files)
    else:
        with zipfile.ZipFile(media.absolute_path, "r") as archive:
            result = sorted(
                name for name in archive.namelist()
                if any(name.lower().endswith(ext) for ext in image_exts)
            )

    _MANGA_FILES_CACHE[media.id] = (mtime, result)
    return result


_PAGE_DIMENSIONS_CACHE: dict[int, tuple[float, list[tuple[int, int] | None]]] = {}


def get_manga_page_dimensions(media: models.Media, files: list[str]) -> list[tuple[int, int] | None]:
    """Read image headers once so the web reader can reserve each page's height."""
    mtime = os.path.getmtime(media.absolute_path)
    cached = _PAGE_DIMENSIONS_CACHE.get(media.id)
    if cached and cached[0] == mtime and len(cached[1]) == len(files):
        return cached[1]

    dimensions: list[tuple[int, int] | None] = []
    if media.extension == ".dir":
        for path in files:
            try:
                with Image.open(path) as image:
                    dimensions.append(image.size)
            except (OSError, ValueError):
                dimensions.append(None)
    else:
        with zipfile.ZipFile(media.absolute_path, "r") as archive:
            for name in files:
                try:
                    with archive.open(name) as source, Image.open(source) as image:
                        dimensions.append(image.size)
                except (OSError, ValueError):
                    dimensions.append(None)

    if len(_PAGE_DIMENSIONS_CACHE) >= 32 and media.id not in _PAGE_DIMENSIONS_CACHE:
        _PAGE_DIMENSIONS_CACHE.pop(next(iter(_PAGE_DIMENSIONS_CACHE)))
    _PAGE_DIMENSIONS_CACHE[media.id] = (mtime, dimensions)
    return dimensions
