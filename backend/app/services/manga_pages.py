from collections import OrderedDict
import os
import threading
import zipfile

from PIL import Image

from .. import models
from ..media_files import manga_image_files

MANGA_FILES_CACHE_MAX_SIZE = 256
PAGE_DIMENSIONS_CACHE_MAX_SIZE = 32
_MANGA_FILES_CACHE: OrderedDict[int, tuple[float, list[str]]] = OrderedDict()
_PAGE_DIMENSIONS_CACHE: OrderedDict[int, tuple[float, list[tuple[int, int] | None]]] = OrderedDict()
_CACHE_LOCK = threading.Lock()


def _lru_set(cache: OrderedDict, max_size: int, key: int, value) -> None:
    with _CACHE_LOCK:
        cache[key] = value
        cache.move_to_end(key)
        while len(cache) > max_size:
            cache.popitem(last=False)


def get_manga_image_files(media: models.Media):
    try:
        mtime = os.path.getmtime(media.absolute_path)
    except OSError:
        mtime = 0.0
    with _CACHE_LOCK:
        cached = _MANGA_FILES_CACHE.get(media.id)
        if cached and cached[0] == mtime:
            _MANGA_FILES_CACHE.move_to_end(media.id)
            return cached[1]

    result = manga_image_files(media.absolute_path, media.extension)

    _lru_set(_MANGA_FILES_CACHE, MANGA_FILES_CACHE_MAX_SIZE, media.id, (mtime, result))
    return result


def get_manga_page_dimensions(media: models.Media, files: list[str]) -> list[tuple[int, int] | None]:
    """Read image headers once so the web reader can reserve each page's height."""
    mtime = os.path.getmtime(media.absolute_path)
    with _CACHE_LOCK:
        cached = _PAGE_DIMENSIONS_CACHE.get(media.id)
        if cached and cached[0] == mtime and len(cached[1]) == len(files):
            _PAGE_DIMENSIONS_CACHE.move_to_end(media.id)
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

    _lru_set(_PAGE_DIMENSIONS_CACHE, PAGE_DIMENSIONS_CACHE_MAX_SIZE, media.id, (mtime, dimensions))
    return dimensions
