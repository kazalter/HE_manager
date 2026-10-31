"""Repair legacy image geometry from headers; originals and other metadata stay intact."""
import argparse
import json
from pathlib import Path
import sqlite3

from PIL import Image


def backfill(database: str, apply: bool = False, backup: str | None = None) -> dict:
    path = Path(database).resolve(strict=True)
    connection = sqlite3.connect(f'{path.as_uri()}?mode={"rw" if apply else "ro"}', uri=True, timeout=10)
    try:
        rows = connection.execute("SELECT id, absolute_path FROM media WHERE media_type='image' AND is_missing=0 AND (width IS NULL OR width<=0 OR height IS NULL OR height<=0)").fetchall()
        updates, unreadable = [], 0
        for media_id, image_path in rows:
            try:
                with Image.open(image_path) as image:
                    width, height = image.size
                if width <= 0 or height <= 0:
                    raise ValueError('invalid dimensions')
                updates.append((width, height, media_id, image_path))
            except (OSError, ValueError):
                unreadable += 1
        changed = 0
        if apply and updates:
            if not backup:
                raise ValueError('--backup is required when applying changes')
            backup_path = Path(backup)
            if backup_path.exists():
                raise ValueError('backup already exists')
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(str(backup_path)) as destination:
                connection.backup(destination)
            with connection:
                before = connection.total_changes
                connection.executemany("UPDATE media SET width=?, height=? WHERE id=? AND absolute_path=? AND (width IS NULL OR width<=0 OR height IS NULL OR height<=0)", updates)
                changed = connection.total_changes - before
        return {'missing': len(rows), 'readable': len(updates), 'unreadable': unreadable, 'updated': changed, 'dry_run': not apply}
    finally:
        connection.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', required=True)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--backup')
    args = parser.parse_args()
    print(json.dumps(backfill(args.database, args.apply, args.backup)))
