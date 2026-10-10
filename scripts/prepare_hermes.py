#!/usr/bin/env python3
"""Prepare only explicitly named HE administrators. Never print credentials."""
import argparse
from pathlib import Path
import sys

_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_root / "backend" if (_root / "backend").is_dir() else _root))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--user-id", required=True, type=int)
    parser.add_argument("--profile-root", type=Path)
    args = parser.parse_args()
    from fastapi import HTTPException
    from sqlalchemy import inspect
    from app.database import SessionLocal, engine
    from app.assistant.identity import prepare_profile

    if not inspect(engine).has_table("assistant_tool_identities"):
        print("FAIL assistant_schema_not_ready")
        return 1
    try:
        with SessionLocal() as db:
            binding = prepare_profile(db, args.user_id, profile_root=args.profile_root)
        print("PASS profile_prepared " + binding.profile_name)
        return 0
    except HTTPException as error:
        print("FAIL " + str(error.detail))
        return 1
    except Exception:
        print("FAIL assistant_preparation_failed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
