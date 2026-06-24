from fastapi import HTTPException
from sqlalchemy.orm import Session

from .. import models


def get_media_or_404(media_id: int, db: Session) -> models.Media:
    media = db.query(models.Media).filter(models.Media.id == media_id).first()
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")
    return media


def get_source_or_404(source_id: int, db: Session) -> models.ExternalFavoriteSource:
    source = (
        db.query(models.ExternalFavoriteSource)
        .filter(models.ExternalFavoriteSource.id == source_id)
        .first()
    )
    if not source:
        raise HTTPException(status_code=404, detail="External source not found")
    return source


def get_x_source_or_404(source_id: int, db: Session) -> models.XImportSource:
    source = db.query(models.XImportSource).filter(models.XImportSource.id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="X 导入数据源不存在")
    return source
