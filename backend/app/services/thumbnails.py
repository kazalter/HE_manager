import os

from .. import database, models

THUMBNAIL_DIR = os.path.join(os.getcwd(), ".thumbnails")
os.makedirs(THUMBNAIL_DIR, exist_ok=True)


def remove_cover_thumbnails(cover_path: str | None) -> None:
    if not cover_path:
        return
    thumb_base = cover_path.rsplit(".", 1)[0]
    try:
        for filename in os.listdir(THUMBNAIL_DIR):
            if not filename.startswith(thumb_base):
                continue
            thumb_path = os.path.join(THUMBNAIL_DIR, filename)
            if os.path.exists(thumb_path):
                try:
                    os.remove(thumb_path)
                except Exception:
                    pass
    except FileNotFoundError:
        pass


def cleanup_orphaned_thumbnails():
    db = database.SessionLocal()
    try:
        valid_bases = [
            row[0].rsplit(".", 1)[0]
            for row in db.query(models.Media.cover_path).filter(models.Media.cover_path != None).all()
            if row[0]
        ]

        if os.path.exists(THUMBNAIL_DIR):
            for filename in os.listdir(THUMBNAIL_DIR):
                if any(filename.startswith(base) for base in valid_bases):
                    continue
                try:
                    os.remove(os.path.join(THUMBNAIL_DIR, filename))
                except Exception:
                    pass
    except Exception as e:
        print(f"Error cleaning up thumbnails: {e}")
    finally:
        db.close()
