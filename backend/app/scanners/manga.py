import logging
import zipfile
from PIL import Image

from ..media_files import archive_image_files, directory_image_files, manga_image_files

logger = logging.getLogger(__name__)


def get_image_metadata(image_path: str) -> dict:
    try:
        with Image.open(image_path) as img:
            return {"width": img.width, "height": img.height}
    except Exception as e:
        logger.warning("Error reading image metadata for %s: %s", image_path, e)
    return {"width": None, "height": None}


def count_manga_pages(manga_path: str, extension: str) -> int | None:
    try:
        return len(manga_image_files(manga_path, extension))
    except Exception as e:
        logger.warning("Error counting manga pages for %s: %s", manga_path, e)
    return None


def get_manga_thumbnail(manga_path: str, thumb_path: str) -> bool:
    try:
        with zipfile.ZipFile(manga_path, 'r') as z:
            images = archive_image_files(z)
            if images:
                with z.open(images[0]) as f, Image.open(f) as img:
                    if img.mode in ('RGBA', 'P'):
                        img = img.convert('RGB')
                    img.thumbnail((400, 600))
                    img.save(thumb_path, "JPEG")
                    return True
    except Exception as e:
        logger.warning("Error generating manga thumbnail for %s: %s", manga_path, e)
    return False


def get_image_thumbnail(image_path: str, thumb_path: str) -> bool:
    try:
        img = Image.open(image_path)
        if img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')
        img.thumbnail((400, 600))
        img.save(thumb_path, "JPEG")
        return True
    except Exception as e:
        logger.warning("Error generating image thumbnail for %s: %s", image_path, e)
    return False


def get_folder_thumbnail(folder_path: str, thumb_path: str) -> bool:
    try:
        files = directory_image_files(folder_path)
        if files:
            with Image.open(files[0]) as img:
                if img.mode in ('RGBA', 'P'):
                    img = img.convert('RGB')
                img.thumbnail((400, 600))
                img.save(thumb_path, "JPEG")
            return True
    except Exception as e:
        logger.warning("Error generating folder thumbnail for %s: %s", folder_path, e)
    return False
