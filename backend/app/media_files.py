"""Shared page selection for manga indexing, covers, and the reader.

Keep this module independent of scanner/services packages to avoid import cycles.
Archive member names stay unchanged for ZipFile.open; only their classification
normalizes separators used by older Windows-created ZIP files.
"""
import os
import zipfile

IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.bmp', '.gif', '.avif'}
SKIP_FOLDERS = {
    'mask', 'result', 'inpainted', '.thumbnails', '.he_cover',
    'node_modules', '.git', '.vite', '__macosx',
}


def is_manga_page(name: str) -> bool:
    parts = name.replace('\\', '/').split('/')
    filename = parts[-1]
    return (
        not filename.startswith('._')
        and os.path.splitext(filename)[1].lower() in IMAGE_EXTENSIONS
        and not any(part.lower() in SKIP_FOLDERS for part in parts[:-1])
    )


def directory_image_files(path: str) -> list[str]:
    files = []
    for root, dirs, filenames in os.walk(path):
        dirs[:] = [name for name in dirs if name.lower() not in SKIP_FOLDERS]
        files.extend(os.path.join(root, name) for name in filenames if is_manga_page(name))
    return sorted(files)


def archive_image_files(archive: zipfile.ZipFile) -> list[str]:
    return sorted(
        entry.filename for entry in archive.infolist()
        if not entry.is_dir() and is_manga_page(entry.filename)
    )


def manga_image_files(path: str, extension: str) -> list[str]:
    if extension == '.dir':
        return directory_image_files(path)
    with zipfile.ZipFile(path, 'r') as archive:
        return archive_image_files(archive)
