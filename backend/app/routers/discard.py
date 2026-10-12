from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import auth, models
from ..database import get_db
from ..services import media_discard

router = APIRouter(prefix='/discard', dependencies=[Depends(auth.require_admin)])

class DiscardTarget(BaseModel):
    kind: Literal['media', 'external', 'x_post']
    target_id: int = Field(ge=1)

class DiscardRequest(DiscardTarget):
    confirm: bool = False
    preview_hash: str = Field(min_length=64, max_length=64)

class ConfirmRequest(BaseModel):
    confirm: bool = False

@router.post('/preview')
def preview(payload: DiscardTarget, db: Session = Depends(get_db)):
    return media_discard.public_preview(media_discard.build_plan(db, payload.kind, payload.target_id))

@router.post('')
def discard(payload: DiscardRequest, db: Session = Depends(get_db)):
    if not payload.confirm:
        raise HTTPException(400, '请明确确认删除')
    return media_discard.discard(db, payload.kind, payload.target_id, payload.preview_hash)

@router.get('')
def list_discarded(search: str = '', limit: int = 50, offset: int = 0, db: Session = Depends(get_db)):
    query = db.query(models.DiscardedContent)
    if search:
        query = query.filter(models.DiscardedContent.title.ilike(f'%{search}%'))
    return {'total': query.count(), 'items': [media_discard.serialize_record(row) for row in query.order_by(
        models.DiscardedContent.discarded_at.desc(), models.DiscardedContent.id).offset(max(0, offset)).limit(max(1, min(limit, 100))).all()]}

@router.post('/{record_id}/retry')
def retry(record_id: str, db: Session = Depends(get_db)):
    return media_discard.retry_cleanup(db, record_id)

@router.post('/{record_id}/allow-download')
def allow_download(record_id: str, payload: ConfirmRequest, db: Session = Depends(get_db)):
    if not payload.confirm:
        raise HTTPException(400, '请明确确认允许重新下载')
    return media_discard.allow_download(db, record_id)
