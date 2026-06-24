import os
import shutil
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import media_cleanup, models, schemas
from ..database import get_db
from ..dedup import merge as dedup_merge
from ..dedup import worker as dedup_worker

router = APIRouter()


def _serialize_dedup_media(media: models.Media) -> dict:
    return {
        "id": media.id,
        "title": media.title,
        "display_path": media.relative_path or media.title,
        "media_type": media.media_type,
        "extension": media.extension,
        "file_size": media.file_size,
        "cover_path": media.cover_path,
        "duration": media.duration,
        "width": media.width,
        "height": media.height,
        "page_count": media.page_count,
        "is_missing": bool(media.is_missing),
        "duplicate_status": media.duplicate_status or "unique",
        "favorite": bool(media.favorite),
        "rating": media.rating or 0,
        "source_url": media.source_url,
        "source_site": media.source_site,
    }


def _serialize_pair(pair: models.DuplicateCandidate, db: Session) -> Optional[dict]:
    existing = db.query(models.Media).filter(models.Media.id == pair.existing_media_id).first()
    candidate = db.query(models.Media).filter(models.Media.id == pair.candidate_media_id).first()
    if not existing or not candidate:
        return None
    return {
        "id": pair.id,
        "level": pair.level,
        "similarity": pair.similarity or 0,
        "reason": pair.reason,
        "status": pair.status,
        "created_at": pair.created_at,
        "resolved_at": pair.resolved_at,
        "resolution_note": pair.resolution_note,
        "existing": _serialize_dedup_media(existing),
        "candidate": _serialize_dedup_media(candidate),
    }


@router.get("/dedup/summary", response_model=schemas.DedupSummary)
def dedup_summary(db: Session = Depends(get_db)):
    pending_pairs = (
        db.query(models.DuplicateCandidate)
        .filter(models.DuplicateCandidate.status == "pending")
        .count()
    )
    base = db.query(models.Media)
    return {
        "pending_pairs": pending_pairs,
        "strong_duplicate": base.filter(models.Media.duplicate_status == "strong_duplicate").count(),
        "suspected_duplicate": base.filter(models.Media.duplicate_status == "suspected_duplicate").count(),
        "weak_suspected": base.filter(models.Media.duplicate_status == "weak_suspected").count(),
        "checking": base.filter(models.Media.duplicate_status == "checking").count(),
        "queue_size": dedup_worker.queue_size(),
        "worker_running": dedup_worker.is_running(),
    }


@router.get("/dedup/candidates", response_model=List[schemas.DuplicateCandidatePair])
def list_duplicate_candidates(
    level: Optional[str] = None,
    status: str = "pending",
    media_type: Optional[str] = None,
    limit: int = 200,
    db: Session = Depends(get_db),
):
    query = db.query(models.DuplicateCandidate)
    if status and status != "all":
        query = query.filter(models.DuplicateCandidate.status == status)
    if level:
        query = query.filter(models.DuplicateCandidate.level == level)
    pairs = (
        query.order_by(
            models.DuplicateCandidate.status.asc(),
            models.DuplicateCandidate.similarity.desc(),
            models.DuplicateCandidate.id.desc(),
        )
        .limit(max(1, min(limit, 500)))
        .all()
    )
    out: List[dict] = []
    for pair in pairs:
        serialized = _serialize_pair(pair, db)
        if not serialized:
            continue
        if media_type and serialized["existing"]["media_type"] != media_type:
            continue
        out.append(serialized)
    return out


@router.get("/dedup/candidates/{pair_id}", response_model=schemas.DuplicateCandidatePair)
def get_duplicate_candidate(pair_id: int, db: Session = Depends(get_db)):
    pair = db.query(models.DuplicateCandidate).filter(models.DuplicateCandidate.id == pair_id).first()
    if not pair:
        raise HTTPException(status_code=404, detail="重复条目不存在")
    serialized = _serialize_pair(pair, db)
    if not serialized:
        raise HTTPException(status_code=404, detail="对应媒体已不存在")
    return serialized


_DEDUP_ACTIONS = {
    dedup_merge.ACTION_KEEP_EXISTING,
    dedup_merge.ACTION_REPLACE_PATH,
    dedup_merge.ACTION_KEEP_BOTH,
    dedup_merge.ACTION_IGNORE,
}


@router.post("/dedup/candidates/{pair_id}/resolve", response_model=schemas.DuplicateCandidatePair)
def resolve_duplicate_candidate(
    pair_id: int,
    payload: schemas.DedupActionRequest,
    db: Session = Depends(get_db),
):
    if payload.action not in _DEDUP_ACTIONS:
        raise HTTPException(status_code=400, detail="不支持的合并动作")
    pair = db.query(models.DuplicateCandidate).filter(models.DuplicateCandidate.id == pair_id).first()
    if not pair:
        raise HTTPException(status_code=404, detail="重复条目不存在")
    if pair.status != "pending":
        raise HTTPException(status_code=409, detail="该条目已被处理过")

    pair = dedup_merge.apply_action(db, pair, payload.action, note=payload.note)
    db.refresh(pair)
    serialized = _serialize_pair(pair, db)
    if not serialized:
        raise HTTPException(status_code=404, detail="处理后媒体已不存在")
    return serialized


@router.post("/dedup/media/{media_id}/recheck")
def recheck_media_dedup(media_id: int, db: Session = Depends(get_db)):
    media = db.query(models.Media).filter(models.Media.id == media_id).first()
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")
    media.duplicate_status = "checking"
    db.commit()
    dedup_worker.enqueue([media.id])
    return {"queued": True, "media_id": media.id}


@router.delete("/dedup/media/{media_id}/file")
def delete_media_file(
    media_id: int,
    payload: schemas.DedupDeleteFileRequest,
    db: Session = Depends(get_db),
):
    if not payload.confirm:
        raise HTTPException(status_code=400, detail="请通过 confirm=true 二次确认")
    media = db.query(models.Media).filter(models.Media.id == media_id).first()
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")

    file_deleted = False
    target_path = media.absolute_path
    if target_path and os.path.exists(target_path):
        try:
            if os.path.isdir(target_path):
                shutil.rmtree(target_path)
            else:
                os.remove(target_path)
            file_deleted = True
        except OSError as exc:
            raise HTTPException(status_code=500, detail=f"文件删除失败：{exc}")

    media_cleanup.detach_media_references(db, [media.id])

    fp = db.query(models.MediaFingerprint).filter(models.MediaFingerprint.media_id == media.id).first()
    if fp:
        db.delete(fp)
    db.delete(media)
    db.commit()
    return {"file_deleted": file_deleted, "media_id": media_id}
