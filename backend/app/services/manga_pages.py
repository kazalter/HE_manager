import os
import zipfile

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
