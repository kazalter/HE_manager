import os
import shutil
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, aliased

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


def _filtered_candidate_query(
    db: Session,
    *,
    level: Optional[str],
    status: str,
    media_type: Optional[str],
):
    existing_media = aliased(models.Media)
    candidate_media = aliased(models.Media)
    query = (
        db.query(models.DuplicateCandidate)
        .join(existing_media, existing_media.id == models.DuplicateCandidate.existing_media_id)
        .join(candidate_media, candidate_media.id == models.DuplicateCandidate.candidate_media_id)
    )
    if status and status != "all":
        query = query.filter(models.DuplicateCandidate.status == status)
    if level:
        query = query.filter(models.DuplicateCandidate.level == level)
    if media_type:
        query = query.filter(
            existing_media.media_type == media_type,
            candidate_media.media_type == media_type,
        )
    return query


def _ordered_candidate_query(query, sort: str):
    if sort == "newest":
        return query.order_by(models.DuplicateCandidate.id.desc())
    if sort == "oldest":
        return query.order_by(models.DuplicateCandidate.id.asc())
    return query.order_by(
        models.DuplicateCandidate.status.asc(),
        models.DuplicateCandidate.similarity.desc(),
        models.DuplicateCandidate.id.desc(),
    )


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
    offset: int = 0,
    sort: str = "confidence",
    db: Session = Depends(get_db),
):
    query = _filtered_candidate_query(
        db, level=level, status=status, media_type=media_type
    )
    pairs = (
        _ordered_candidate_query(query, sort)
        .offset(max(0, offset))
        .limit(max(1, min(limit, 500)))
        .all()
    )
    out: List[dict] = []
    for pair in pairs:
        serialized = _serialize_pair(pair, db)
        if not serialized:
            continue
        out.append(serialized)
    return out


@router.get("/dedup/candidates-page", response_model=schemas.DedupCandidatePage)
def paged_duplicate_candidates(
    level: Optional[str] = None,
    status: str = "pending",
    media_type: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
    sort: str = "confidence",
    db: Session = Depends(get_db),
):
    safe_limit = max(1, min(limit, 100))
    safe_offset = max(0, offset)
    query = _filtered_candidate_query(
        db, level=level, status=status, media_type=media_type
    )
    total = query.count()
    rows = (
        _ordered_candidate_query(query, sort)
        .offset(safe_offset)
        .limit(safe_limit)
        .all()
    )
    items = []
    for pair in rows:
        serialized = _serialize_pair(pair, db)
        if serialized:
            items.append(serialized)
    return {
        "items": items,
        "total": total,
        "limit": safe_limit,
        "offset": safe_offset,
    }


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

    try:
        pair = dedup_merge.apply_action(db, pair, payload.action, note=payload.note)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.refresh(pair)
    serialized = _serialize_pair(pair, db)
    if not serialized:
        raise HTTPException(status_code=404, detail="处理后媒体已不存在")
    return serialized


@router.post("/dedup/candidates-batch-resolve", response_model=schemas.DedupBatchActionResponse)
def batch_resolve_duplicate_candidates(
    payload: schemas.DedupBatchActionRequest,
    db: Session = Depends(get_db),
):
    if payload.action not in {dedup_merge.ACTION_KEEP_BOTH, dedup_merge.ACTION_IGNORE}:
        raise HTTPException(status_code=400, detail="批量处理只支持‘两者不是重复’或‘忽略’")
    pair_ids = list(dict.fromkeys(payload.pair_ids))
    if not pair_ids or len(pair_ids) > 100:
        raise HTTPException(status_code=400, detail="每次请选择 1 到 100 组重复条目")

    pairs = (
        db.query(models.DuplicateCandidate)
        .filter(models.DuplicateCandidate.id.in_(pair_ids))
        .all()
    )
    processed = 0
    skipped = len(pair_ids) - len(pairs)
    for pair in pairs:
        if pair.status != "pending":
            skipped += 1
            continue
        dedup_merge.apply_action(
            db,
            pair,
            payload.action,
            note=payload.note,
            commit=False,
        )
        processed += 1
    db.commit()
    return {"processed": processed, "skipped": skipped}


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

    if not media.folder or not media.folder.path:
        raise HTTPException(status_code=409, detail="媒体条目没有可验证的媒体库根目录")

    raw_value = (media.absolute_path or "").strip()
    if not raw_value or not os.path.isabs(raw_value):
        raise HTTPException(status_code=409, detail="拒绝删除无效或非绝对媒体路径")
    raw_target = os.path.abspath(raw_value)
    root_path = os.path.realpath(os.path.abspath(media.folder.path))
    target_path = os.path.realpath(raw_target)
    try:
        is_inside_root = os.path.commonpath([root_path, target_path]) == root_path
    except ValueError:
        is_inside_root = False
    if not raw_target or not is_inside_root or target_path == root_path:
        raise HTTPException(status_code=409, detail="拒绝删除媒体库范围外或媒体库根目录本身")
    if os.path.islink(raw_target):
        raise HTTPException(status_code=409, detail="拒绝删除符号链接，请手动确认目标")

    file_deleted = False
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
