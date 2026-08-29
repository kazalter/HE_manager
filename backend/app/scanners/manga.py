import os
import zipfile
from PIL import Image

from .common import IMAGE_EXTENSIONS, SKIP_FOLDERS


def get_image_metadata(image_path: str) -> dict:
    try:
        with Image.open(image_path) as img:
            return {"width": img.width, "height": img.height}
    except Exception as e:
        print(f"Error reading image metadata: {e}")
    return {"width": None, "height": None}


def count_manga_pages(manga_path: str, extension: str) -> int | None:
    image_exts = {'.jpg', '.jpeg', '.png', '.webp', '.bmp'}
    try:
        if extension == ".dir":
            count = 0
            for _, dirs, files in os.walk(manga_path):
                dirs[:] = [d for d in dirs if d.lower() not in SKIP_FOLDERS]
                count += sum(1 for file in files if any(file.lower().endswith(ext) for ext in image_exts))
            return count
        with zipfile.ZipFile(manga_path, 'r') as z:
            return sum(1 for f in z.namelist() if any(f.lower().endswith(ext) for ext in image_exts))
    except Exception as e:
        print(f"Error counting manga pages: {e}")
    return None


def get_manga_thumbnail(manga_path: str, thumb_path: str) -> bool:
    try:
        with zipfile.ZipFile(manga_path, 'r') as z:
            images = sorted([f for f in z.namelist() if any(f.lower().endswith(ext) for ext in IMAGE_EXTENSIONS)])
            if images:
                with z.open(images[0]) as f:
                    img = Image.open(f)
                    if img.mode in ('RGBA', 'P'):
                        img = img.convert('RGB')
                    img.thumbnail((400, 600))
                    img.save(thumb_path, "JPEG")
                    return True
    except Exception as e:
        print(f"Error generating manga thumbnail: {e}")
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
        print(f"Error generating image thumbnail: {e}")
    return False


def get_folder_thumbnail(folder_path: str, thumb_path: str) -> bool:
    try:
        image_exts = {'.jpg', '.jpeg', '.png', '.webp', '.bmp'}
        files = sorted([f for f in os.listdir(folder_path) if any(f.lower().endswith(ext) for ext in image_exts)])
        if files:
            img_path = os.path.join(folder_path, files[0])
            img = Image.open(img_path)
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')
            img.thumbnail((400, 600))
            img.save(thumb_path, "JPEG")
            return True
    except Exception as e:
        print(f"Error generating folder thumbnail: {e}")
    return False
