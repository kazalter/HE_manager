from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..database import get_db

router = APIRouter()


@router.get("/healthz")
def healthz(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1")).scalar_one()
    return {"status": "ok", "database": "ok"}


@router.get("/")
def read_root():
    return {"message": "Welcome to HE Manager API"}
