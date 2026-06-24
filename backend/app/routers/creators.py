from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import creators as creators_mod
from ..database import get_db

router = APIRouter()


@router.get("/creators")
def list_creators(
    search: Optional[str] = None,
    sort: str = "count",
    media_type: Optional[str] = None,
    db: Session = Depends(get_db),
):
    return creators_mod.list_creators(db, search=search, sort=sort, media_type=media_type)


@router.get("/creators/{screen_name}")
def creator_detail_by_sn(screen_name: str, db: Session = Depends(get_db)):
    detail = creators_mod.creator_detail(db, f"x:{screen_name}")
    if detail is None:
        raise HTTPException(status_code=404, detail="creator not found")
    return detail


@router.get("/mobile/creators")
def mobile_list_creators(
    kind: Optional[str] = None,
    search: Optional[str] = None,
    sort: str = "count",
    db: Session = Depends(get_db),
):
    media_type = None if not kind or kind == "all" else kind
    return creators_mod.list_creators(db, search=search, sort=sort, media_type=media_type)


@router.get("/mobile/creators/detail")
def mobile_creator_detail(key: str, db: Session = Depends(get_db)):
    detail = creators_mod.creator_detail(db, key)
    if detail is None:
        raise HTTPException(status_code=404, detail="creator not found")
    return detail
