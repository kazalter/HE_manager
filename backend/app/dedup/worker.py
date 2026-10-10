"""Background fingerprint + classification worker.

Single thread + a queue: scanner enqueues media ids that need fingerprinting; the worker
computes the fingerprint, finds candidate pairs, classifies, persists. UI is never
blocked — scans return as soon as basic insertion finishes.
"""
from __future__ import annotations

import logging
import queue
import threading
from datetime import datetime
from typing import Iterable, List, Optional

from sqlalchemy import and_, case, or_
from sqlalchemy.orm import Session

from .. import database, models
from . import classify, fingerprint, normalize

logger = logging.getLogger(__name__)

_QUEUE: "queue.Queue[int]" = queue.Queue()
_WORKER_THREAD: Optional[threading.Thread] = None
_WORKER_LOCK = threading.Lock()
_QUEUE_LOCK = threading.Lock()
_QUEUED_IDS: set[int] = set()


# ----- public API -----

def enqueue(media_ids: Iterable[int]) -> int:
    count = 0
    for media_id in media_ids:
        if media_id is None:
            continue
        media_id = int(media_id)
        with _QUEUE_LOCK:
            if media_id in _QUEUED_IDS:
                continue
            _QUEUED_IDS.add(media_id)
            _QUEUE.put(media_id)
            count += 1
    if count:
        _ensure_worker()
    return count


def queue_size() -> int:
    return _QUEUE.qsize()


def is_running() -> bool:
    return bool(_WORKER_THREAD and _WORKER_THREAD.is_alive())


def recover_checking_jobs() -> int:
    """Requeue work that was persisted as checking before a process restart."""
    db = database.SessionLocal()
    try:
        media_ids = [
            row[0]
            for row in db.query(models.Media.id)
            .filter(models.Media.duplicate_status.in_(["checking", "dedup_pending"]))
            .order_by(models.Media.id.asc())
            .all()
        ]
    finally:
        db.close()
    return enqueue(media_ids)


# ----- internals -----

def _ensure_worker() -> None:
    global _WORKER_THREAD
    with _WORKER_LOCK:
        if _WORKER_THREAD and _WORKER_THREAD.is_alive():
            return
        thread = threading.Thread(target=_run, name="dedup-worker", daemon=True)
        _WORKER_THREAD = thread
        thread.start()


def _run() -> None:
    global _WORKER_THREAD
    while True:
        try:
            media_id = _QUEUE.get(timeout=30)
        except queue.Empty:
            # Enqueue and worker shutdown must agree under the same lock, or an
            # item arriving just as this thread exits can remain stranded.
            with _WORKER_LOCK:
                if not _QUEUE.empty():
                    continue
                _WORKER_THREAD = None
                return
        try:
            # Track waiting jobs only. A recheck arriving while this item is
            # running must be allowed to schedule one additional pass.
            with _QUEUE_LOCK:
                _QUEUED_IDS.discard(media_id)
            _process_one(media_id)
        except Exception as exc:
            _mark_processing_error(media_id, exc)
            logger.exception("[dedup] worker error processing media %s: %s", media_id, exc)
        finally:
            _QUEUE.task_done()


def _mark_processing_error(media_id: int, exc: Exception) -> None:
    """Expose failed work again; the explicit recheck endpoint can retry it."""
    db = database.SessionLocal()
    try:
        db.query(models.Media).filter(
            models.Media.id == media_id,
            models.Media.duplicate_status != "dedup_excluded",
        ).update({"duplicate_status": "dedup_error"}, synchronize_session=False)
        db.commit()
    except Exception:
        db.rollback()
        logger.error("[dedup] failed to persist error state for media %s: %s", media_id, exc)
    finally:
        db.close()


@__import__("app.services.media_operation_guard",fromlist=["guarded_mutation"]).guarded_mutation
def _process_one(media_id: int, *, allowed_media_ids: Optional[List[int]] = None) -> None:
    db = database.SessionLocal()
    try:
        media = db.query(models.Media).filter(models.Media.id == media_id).first()
        if not media or media.is_missing or media.duplicate_status == "dedup_excluded":
            return
        media.normalized_title = normalize.normalize_title(media.title or "")

        # Compute (or reuse cached) fingerprint for the new entry.
        new_fp = _ensure_fingerprint(db, media)
        if new_fp is None or not any((new_fp.hash_first, new_fp.hash_middle, new_fp.hash_last)):
            db.query(models.Media).filter(
                models.Media.id == media.id,
                models.Media.duplicate_status != "dedup_excluded",
            ).update({"duplicate_status": "dedup_error"}, synchronize_session=False)
            db.commit()
            return

        candidates = _candidates_for(db, media, new_fp)
        allowed=set(allowed_media_ids) if allowed_media_ids is not None else None
        if allowed is not None:candidates=[x for x in candidates if x.id in allowed]
        new_lite = _lite_from_record(media, new_fp)
        matched_pair_ids: set[int] = set()
        affected_ids = {media.id}
        for existing in candidates:
            existing_fp = _ensure_fingerprint(db, existing)
            if existing_fp is None or not any((existing_fp.hash_first, existing_fp.hash_middle, existing_fp.hash_last)):
                continue
            existing_lite = _lite_from_record(existing, existing_fp)
            same_title = bool(media.normalized_title and media.normalized_title == existing.normalized_title)
            content_matches = any(
                getattr(existing_fp, field) and getattr(existing_fp, field) == getattr(new_fp, field)
                for field in ("hash_first", "hash_middle", "hash_last")
            )
            # An old indexed hash may have selected a now-changed file. Size and
            # dimensions alone are evidence only within the same-title group.
            if not same_title and not content_matches:
                continue
            level, similarity, reasons = classify.classify(existing_lite, new_lite)
            if level == classify.LEVEL_UNIQUE:
                continue
            left_id, right_id = sorted((existing.id, media.id))
            pair = _upsert_candidate(db, left_id, right_id, level, similarity, reasons)
            matched_pair_ids.add(pair.id)
            affected_ids.update((pair.existing_media_id, pair.candidate_media_id))

        # Retire outdated warnings after a file changes instead of leaving old
        # results pending forever. Historical/manual resolutions stay intact.
        for pair in db.query(models.DuplicateCandidate).filter(
            models.DuplicateCandidate.status == "pending",
            or_(models.DuplicateCandidate.existing_media_id == media.id,
                models.DuplicateCandidate.candidate_media_id == media.id),
        ).all():
            if allowed is not None and (pair.existing_media_id not in allowed or pair.candidate_media_id not in allowed):continue
            if pair.id not in matched_pair_ids:
                db.query(models.DuplicateCandidate).filter(
                    models.DuplicateCandidate.id == pair.id,
                    models.DuplicateCandidate.status == "pending",
                ).update({"status": "stale", "resolved_at": datetime.utcnow(),
                          "resolution_note": "重新检测后，当前文件不再符合重复条件"},
                         synchronize_session=False)
                affected_ids.update((pair.existing_media_id, pair.candidate_media_id))
        db.flush()
        for affected_id in affected_ids:
            with _QUEUE_LOCK:
                waiting_again = affected_id in _QUEUED_IDS
            _refresh_media_status(db, affected_id, preserve_pending=affected_id != media.id or waiting_again)
        db.commit()
    finally:
        db.close()


def _refresh_media_status(db: Session, media_id: int, *, preserve_pending: bool = True) -> None:
    media = db.get(models.Media, media_id)
    if not media or media.duplicate_status == "dedup_excluded":
        return
    if preserve_pending and media.duplicate_status in {"checking", "dedup_pending", "dedup_error"}:
        return
    levels = [row[0] for row in db.query(models.DuplicateCandidate.level).filter(
        models.DuplicateCandidate.candidate_media_id == media_id,
        models.DuplicateCandidate.status == "pending",
    ).all()]
    ranks = {classify.LEVEL_UNIQUE: 0, classify.LEVEL_WEAK: 1,
             classify.LEVEL_SUSPECTED: 2, classify.LEVEL_STRONG: 3}
    status = max(levels, key=lambda level: ranks.get(level, 0)) if levels else "unique"
    query = db.query(models.Media).filter(
        models.Media.id == media_id,
        models.Media.duplicate_status != "dedup_excluded",
    )
    if preserve_pending:
        query = query.filter(models.Media.duplicate_status.notin_(["checking", "dedup_pending", "dedup_error"]))
    # Conditional SQL protects a manual merge performed in another session
    # while fingerprint computation was using cached ORM objects.
    query.update({"duplicate_status": status}, synchronize_session=False)


def _candidates_for(db: Session, media: models.Media,
                    record: Optional[models.MediaFingerprint] = None) -> List[models.Media]:
    norm = (media.normalized_title or normalize.normalize_title(media.title or "")).strip()
    matches = [models.Media.normalized_title == norm] if norm else []
    if record:
        for field in ("hash_first", "hash_middle", "hash_last"):
            value = getattr(record, field)
            if value:
                matches.append(getattr(models.MediaFingerprint, field) == value)
    if not matches:
        return []
    return (
        db.query(models.Media)
        .outerjoin(models.MediaFingerprint, models.MediaFingerprint.media_id == models.Media.id)
        .filter(models.Media.id != media.id)
        .filter(models.Media.media_type == media.media_type)
        .filter(models.Media.is_missing == False)  # noqa: E712
        .filter(models.Media.duplicate_status != "dedup_excluded")
        .filter(or_(*matches))
        .order_by(models.Media.id.asc())
        .all()
    )


def _ensure_fingerprint(db: Session, media: models.Media) -> Optional[models.MediaFingerprint]:
    record = (
        db.query(models.MediaFingerprint)
        .filter(models.MediaFingerprint.media_id == media.id)
        .first()
    )
    if record and any((record.hash_first, record.hash_middle, record.hash_last)) and fingerprint.fingerprint_cache_is_fresh(record, media):
        return record

    result = fingerprint.fingerprint_for_media(media)
    if result is None:
        return None

    if not record:
        record = models.MediaFingerprint(media_id=media.id)
        db.add(record)
    record.media_type = result.media_type
    record.file_size = result.file_size
    record.page_count = result.page_count
    record.duration = result.duration
    record.width = result.width
    record.height = result.height
    record.hash_first = result.hash_first
    record.hash_middle = result.hash_middle
    record.hash_last = result.hash_last
    record.source_path = result.source_path
    record.source_mtime = result.source_mtime
    record.computed_at = datetime.utcnow()
    db.commit()
    db.refresh(record)
    return record


def _lite_from_record(
    media: models.Media,
    record: models.MediaFingerprint,
) -> classify.FingerprintLite:
    return classify.FingerprintLite(
        media_type=record.media_type or media.media_type,
        file_size=record.file_size or media.file_size,
        page_count=record.page_count or media.page_count,
        duration=record.duration or media.duration,
        width=record.width or media.width,
        height=record.height or media.height,
        hash_first=record.hash_first,
        hash_middle=record.hash_middle,
        hash_last=record.hash_last,
    )


def _upsert_candidate(
    db: Session,
    existing_media_id: int,
    candidate_media_id: int,
    level: str,
    similarity: int,
    reasons: List[str],
) -> models.DuplicateCandidate:
    existing_pair = (
        db.query(models.DuplicateCandidate)
        .filter(or_(
            and_(models.DuplicateCandidate.existing_media_id == existing_media_id,
                 models.DuplicateCandidate.candidate_media_id == candidate_media_id),
            and_(models.DuplicateCandidate.existing_media_id == candidate_media_id,
                 models.DuplicateCandidate.candidate_media_id == existing_media_id),
        ))
        .order_by(case((models.DuplicateCandidate.status.in_([
            "merged", "kept_both", "ignored", "replaced",
        ]), 0), else_=1), models.DuplicateCandidate.id.asc())
        .first()
    )
    reason = "；".join(reasons) if reasons else None
    if existing_pair:
        db.query(models.DuplicateCandidate).filter(
            models.DuplicateCandidate.id == existing_pair.id,
            models.DuplicateCandidate.status.notin_(["merged", "kept_both", "ignored", "replaced"]),
        ).update({"level": level, "similarity": similarity, "reason": reason,
                  "status": "pending", "resolved_at": None, "resolution_note": None},
                 synchronize_session=False)
        db.refresh(existing_pair)
        return existing_pair
    pair = models.DuplicateCandidate(
        existing_media_id=existing_media_id,
        candidate_media_id=candidate_media_id,
        level=level,
        similarity=similarity,
        reason=reason,
        status="pending",
    )
    db.add(pair)
    db.flush()
    return pair
