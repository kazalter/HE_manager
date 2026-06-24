from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import stats as stats_mod
from ..database import get_db

router = APIRouter()


@router.get("/stats/overview")
def stats_overview(db: Session = Depends(get_db)):
    return stats_mod.overview(db)


@router.get("/stats/distribution")
def stats_distribution(db: Session = Depends(get_db)):
    return stats_mod.distribution(db)


@router.get("/stats/activity")
def stats_activity(days: int = 365, db: Session = Depends(get_db)):
    # Default 365 matches StatsView's heatmap. Cap it to avoid expensive scans.
    days = max(1, min(days, 730))
    return stats_mod.activity(db, days=days)


@router.get("/stats/attention")
def stats_attention(db: Session = Depends(get_db)):
    return stats_mod.attention(db)


@router.get("/stats/highlights")
def stats_highlights(limit: int = 10, db: Session = Depends(get_db)):
    return stats_mod.highlights(db, limit=limit)
