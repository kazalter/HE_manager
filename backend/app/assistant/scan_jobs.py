"""Main-process scan wrapper. Retry bookkeeping, never replay media work."""

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from fastapi import HTTPException
from sqlalchemy.exc import OperationalError
from .. import database, models, scanner
from ..services import job_lifecycle, storage_guard
from . import schemas
from .models import AssistantProposal, AssistantAudit
from .proposals import owned, folder_snapshot
from .store import input_hash, utcnow, write_transaction, uuid_text

logger = logging.getLogger(__name__)
_POOL = None
_POOL_LOCK = threading.Lock()
_STATUS_FAILURES = set()


def job_id_for(proposal_id):
    return "assistant-scan-" + str(proposal_id)


def preflight_scan(db, proposal):
    folder = db.get(models.Folder, proposal.target_id)
    if (
        folder is None
        or input_hash(folder_snapshot(folder)) != proposal.target_fingerprint
    ):
        return
    allowed, _ = storage_guard.ensure_folder_scannable(folder.path)
    if not allowed:
        raise HTTPException(503, "assistant_storage_unavailable")


def reserve_scan(local, folder_id):
    now = utcnow()
    cutoff = now - timedelta(hours=job_lifecycle.JOB_TTL_HOURS)
    rows = local.query(models.BackgroundJob).filter(
        models.BackgroundJob.kind == "assistant_scan"
    )
    if rows.filter(
        models.BackgroundJob.status.in_(job_lifecycle.ACTIVE_STATUSES)
    ).first():
        raise HTTPException(409, "assistant_scan_busy")
    rows.filter(
        models.BackgroundJob.status.in_(job_lifecycle.TERMINAL_STATUSES),
        models.BackgroundJob.finished_at < cutoff,
    ).delete(synchronize_session=False)
    local.flush()
    entries = rows.order_by(models.BackgroundJob.updated_at).all()
    while len(entries) >= job_lifecycle.JOB_MAX_ENTRIES:
        victim = next(
            (r for r in entries if r.status in job_lifecycle.TERMINAL_STATUSES), None
        )
        if victim is None:
            raise HTTPException(409, "assistant_scan_capacity")
        local.delete(victim)
        entries.remove(victim)
    reservation = scanner.reserve_folder_scan(folder_id)
    if reservation is None:
        raise HTTPException(409, "assistant_folder_scan_busy")
    return reservation


def insert_job(local, proposal):
    now = utcnow()
    job = schemas.JobDTO(
        job_id=job_id_for(proposal.id),
        folder_id=proposal.target_id,
        status="queued",
        message="扫描可能有部分结果；不自动重放。",
        created_at=now,
    )
    local.add(
        models.BackgroundJob(
            job_id=job.job_id,
            kind="assistant_scan",
            status="queued",
            payload_json=job.model_dump_json(),
            created_at=now,
            updated_at=now,
        )
    )
    return schemas.ActionResultDTO(
        proposal_id=proposal.id, state="queued", job_id=job.job_id, job=job
    )


def persist_scan_status(job_id, status, message):
    with database.SessionLocal() as db:
        with write_transaction(db) as local:
            row = local.get(models.BackgroundJob, job_id)
            if row is None or row.kind != "assistant_scan":
                raise HTTPException(503, "job_status_unavailable")
            terminal = status in job_lifecycle.TERMINAL_STATUSES
            payload = schemas.JobDTO.model_validate_json(row.payload_json)
            updated = payload.model_copy(
                update={
                    "status": status,
                    "message": message[:500],
                    "finished_at": utcnow() if terminal else None,
                }
            )
            row.status = status
            row.payload_json = updated.model_dump_json()
            row.updated_at = utcnow()
            row.finished_at = updated.finished_at
            proposal = local.get(
                AssistantProposal, job_id.removeprefix("assistant-scan-")
            )
            if proposal is None:
                raise HTTPException(503, "job_status_unavailable")
            result = schemas.ActionResultDTO(
                proposal_id=proposal.id, state=status, job_id=job_id, job=updated
            )
            proposal.result_json = result.model_dump_json()
            audit = (
                local.query(AssistantAudit)
                .filter(AssistantAudit.proposal_id == proposal.id)
                .first()
            )
            if audit:
                audit.result_json = proposal.result_json
        _STATUS_FAILURES.discard(job_id)
        return result


def save_scan_status(job_id, status, message):
    for attempt in range(3):
        try:
            return persist_scan_status(job_id, status, message)
        except OperationalError as exc:
            if (
                "locked" not in str(exc.orig).lower()
                and "busy" not in str(exc.orig).lower()
            ):
                break
            if attempt < 2:
                time.sleep(0.05 * (attempt + 1))
        except Exception:
            break
    _STATUS_FAILURES.add(job_id)
    logger.error(
        "assistant scan state persistence failed: job_id=%s code=job_status_unavailable",
        job_id,
    )
    raise HTTPException(503, "job_status_unavailable")


def run_scan_job(job_id, folder_id, reservation):
    try:
        save_scan_status(job_id, "running", "正在扫描；停止聊天不会回滚已确认的扫描。")
        try:
            success = scanner.scan_folder(folder_id, reservation)
            status = "completed" if success else "failed"
        except Exception:
            logger.error("assistant scan failed: job_id=%s", job_id)
            status = "failed"
        save_scan_status(
            job_id,
            status,
            (
                "扫描完成。"
                if status == "completed"
                else "扫描失败，可能已有部分结果；请检查后重新发起，不自动重放。"
            ),
        )
    except HTTPException:
        # State availability is exposed by get_owned_scan_job. Do not re-scan.
        pass
    finally:
        scanner.release_folder_scan(folder_id, reservation)


def enqueue_scan_job(job_id, folder_id, reservation):
    global _POOL
    with _POOL_LOCK:
        if _POOL is None:
            _POOL = ThreadPoolExecutor(
                max_workers=1, thread_name_prefix="assistant-scan"
            )
        _POOL.submit(run_scan_job, job_id, folder_id, reservation)


def get_owned_scan_job(db, user_id, job_id):
    if not job_id.startswith("assistant-scan-"):
        raise HTTPException(404, "assistant_not_found")
    proposal = owned(db, user_id, uuid_text(job_id.removeprefix("assistant-scan-")))
    if proposal.kind != "scan" or not proposal.result_json:
        raise HTTPException(404, "assistant_not_found")
    if job_id in _STATUS_FAILURES:
        raise HTTPException(503, "job_status_unavailable")
    result = schemas.ActionResultDTO.model_validate_json(proposal.result_json)
    if result.job_id != job_id or result.job is None:
        raise HTTPException(404, "assistant_not_found")
    row = db.get(models.BackgroundJob, job_id, populate_existing=True)
    if row is None:
        if result.job.status not in job_lifecycle.TERMINAL_STATUSES:
            raise HTTPException(503, "job_status_unavailable")
        return result.job
    if row.kind != "assistant_scan":
        raise HTTPException(404, "assistant_not_found")
    return schemas.JobDTO.model_validate_json(row.payload_json)


def recover_scan_jobs():
    # Main lifespan invokes this BEFORE generic recovery/pruning, so the
    # authoritative proposal snapshot is written even when history is expired.
    with database.SessionLocal() as db:
        ids = [
            r[0]
            for r in db.query(models.BackgroundJob.job_id).filter(
                models.BackgroundJob.kind == "assistant_scan",
                models.BackgroundJob.status.in_(job_lifecycle.ACTIVE_STATUSES),
            )
        ]
    for job_id in ids:
        save_scan_status(
            job_id,
            "interrupted",
            "服务重启，扫描已中断，可能已有部分结果；请检查后重新发起，不自动重放。",
        )
    return len(ids)
