#!/usr/bin/env python3
"""
Database backup and freshness verification utility for HE Manager.

Usage:
  python scripts/backup_db.py --backup
  python scripts/backup_db.py --check-freshness --max-age-hours 24
  python scripts/backup_db.py --list
"""

import argparse
import os
import sys

# Ensure backend package is importable both on host and in container
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for candidate in (
    os.path.join(REPO_ROOT, "backend"),
    REPO_ROOT,
    "/srv",
    os.getcwd(),
):
    if os.path.isdir(candidate) and candidate not in sys.path:
        sys.path.insert(0, candidate)

from app.services import backup
from app.database import SQLALCHEMY_DATABASE_URL
from sqlalchemy.engine import make_url


def resolve_db_path(override_path: str = None) -> str:
    if override_path:
        return os.path.abspath(override_path)
    
    url_str = os.getenv("HE_DATABASE_URL", SQLALCHEMY_DATABASE_URL)
    try:
        url = make_url(url_str)
        if url.drivername == "sqlite" and url.database and url.database != ":memory:":
            return os.path.abspath(url.database)
    except Exception:
        pass

    # Common fallbacks
    for candidate in ("/data/library.db", os.path.join(BACKEND_DIR, "app", "library.db")):
        if os.path.exists(candidate):
            return os.path.abspath(candidate)
    return os.path.abspath(os.path.join(BACKEND_DIR, "app", "library.db"))


def resolve_backup_dir(db_path: str, override_dir: str = None) -> str:
    if override_dir:
        return os.path.abspath(override_dir)
    return backup.get_default_backup_dir(db_path)


def main():
    parser = argparse.ArgumentParser(description="HE Manager SQLite Backup & Monitoring Utility")
    parser.add_argument("--backup", action="store_true", help="Perform online hot backup now")
    parser.add_argument("--check-freshness", action="store_true", help="Check if backups are fresh (exits 1 if stale/missing)")
    parser.add_argument("--list", action="store_true", help="List existing backups and metadata")
    parser.add_argument("--db-path", type=str, default=None, help="Custom path to live library.db")
    parser.add_argument("--backup-dir", type=str, default=None, help="Custom backup directory")
    parser.add_argument("--max-age-hours", type=float, default=24.0, help="Freshness threshold in hours (default: 24)")
    parser.add_argument("--keep", type=int, default=7, help="Number of backups to keep (default: 7)")

    args = parser.parse_args()

    db_path = resolve_db_path(args.db_path)
    backup_dir = resolve_backup_dir(db_path, args.backup_dir)

    # Default action if none specified is listing status and checking freshness
    if not (args.backup or args.check_freshness or args.list):
        args.list = True
        args.check_freshness = True

    if args.backup:
        print(f"==> Initiating SQLite backup for: {db_path}")
        print(f"    Backup target directory: {backup_dir}")
        try:
            res = backup.backup_database(db_path, backup_dir=backup_dir, keep_count=args.keep)
            print(f"[OK] Backup created: {res['backup_name']} ({res['size_bytes'] / (1024*1024):.2f} MB)")
            print(f"     Total backups retained: {res['kept_backups']}")
        except Exception as e:
            print(f"[ERROR] Backup failed: {e}", file=sys.stderr)
            sys.exit(1)

    if args.list:
        backups = backup.list_backups(backup_dir)
        print(f"\n==> Backups in {backup_dir} (Total: {len(backups)}):")
        if not backups:
            print("    (No backups found)")
        else:
            for b in backups:
                mb = b["size_bytes"] / (1024 * 1024)
                print(f"  - {b['name']:<28} {mb:>6.2f} MB  (Age: {b['age_hours']:.1f}h, Date: {b['modified_at']})")

    if args.check_freshness:
        freshness = backup.check_backup_freshness(backup_dir, max_age_hours=args.max_age_hours)
        print(f"\n==> Freshness check (Threshold: {args.max_age_hours}h):")
        print(f"    Status:  {'HEALTHY' if freshness['healthy'] else 'STALE / WARNING'}")
        print(f"    Detail:  {freshness['message']}")
        if not freshness["healthy"]:
            sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
