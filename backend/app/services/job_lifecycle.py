"""Bounded in-memory job registries with persistent status tombstones.

Background work still runs in process, but a compact public snapshot is persisted so a
restart can turn abandoned active jobs into an explicit ``interrupted`` state instead
of leaving clients polling an unknown or apparently running job forever.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timedelta
from typing import Any, MutableMapping, Optional

from .. import database, models

JOB_TTL_HOURS = max(1, int(os.getenv("HE_JOB_TTL_HOURS", "72")))
JOB_MAX_ENTRIES = max(10, int(os.getenv("HE_JOB_MAX_ENTRIES", "200")))
ACTIVE_STATUSES = {"queued", "preparing", "running", "paused", "canceling"}
TERMINAL_STATUSES = {"completed", "failed", "canceled", "interrupted"}

_MEMORY_TIMESTAMPS: dict[tuple[str, str], datetime] = {}
_LOCK = threading.Lock()


class JobCapacityError(RuntimeError):
    pass


def public_payload(job: Any) -> dict:
    if hasattr(job, "to_dict"):
        return dict(job.to_dict())
    return dict(job)


def _status(job: Any) -> str:
    if isinstance(job, dict):
        return str(job.get("status") or "")
    return str(getattr(job, "status", "") or "")


def _job_id(job: Any) -> str:
    if isinstance(job, dict):
        return str(job.get("job_id") or "")
    return str(getattr(job, "job_id", "") or "")


def admit_new_job(kind: str, registry: MutableMapping[str, Any], now: datetime | None = None) -> None:
    prune_memory_jobs(kind, registry, now=now)
    if len(registry) >= JOB_MAX_ENTRIES:
        raise JobCapacityError(f"{kind} job capacity reached ({JOB_MAX_ENTRIES})")


def record_job(kind: str, job: Any, *, finished: bool = False) -> None:
    payload = public_payload(job)
    job_id = str(payload.get("job_id") or "")
    if not job_id:
        return
    now = datetime.utcnow()
    status = str(payload.get("status") or "queued")
    db = database.SessionLocal()
    persisted = False
    try:
        row = db.query(models.BackgroundJob).filter(models.BackgroundJob.job_id == job_id).first()
        if not row:
            row = models.BackgroundJob(job_id=job_id, kind=kind, created_at=now)
            db.add(row)
        row.kind = kind
        row.status = status
        row.payload_json = json.dumps(payload, ensure_ascii=False, default=str)
        row.updated_at = now
        if finished or status in TERMINAL_STATUSES:
            row.finished_at = now
        db.commit()
        persisted = True
    except Exception as exc:  # Job bookkeeping must not abort the actual work.
        db.rollback()
        print(f"[jobs] failed to persist {kind}/{job_id}: {exc}")
    finally:
        db.close()
    with _LOCK:
        _MEMORY_TIMESTAMPS[(kind, job_id)] = now
    if persisted:
        try:
            cleanup_job_history()
        except Exception as exc:
            print(f"[jobs] cleanup failed: {exc}")


def get_job_snapshot(kind: str, job_id: str) -> Optional[dict]:
    db = database.SessionLocal()
    try:
        row = (
            db.query(models.BackgroundJob)
            .filter(models.BackgroundJob.job_id == job_id, models.BackgroundJob.kind == kind)
            .first()
        )
        if not row:
            return None
        try:
            payload = json.loads(row.payload_json or "{}")
        except (TypeError, json.JSONDecodeError):
            payload = {}
        payload["job_id"] = row.job_id
        payload["status"] = row.status
        return payload
    finally:
        db.close()


def recover_interrupted_jobs(now: datetime | None = None) -> int:
    now = now or datetime.utcnow()
    db = database.SessionLocal()
    recovered = 0
    try:
        rows = db.query(models.BackgroundJob).filter(models.BackgroundJob.status.in_(ACTIVE_STATUSES)).all()
        for row in rows:
            try:
                payload = json.loads(row.payload_json or "{}")
            except (TypeError, json.JSONDecodeError):
                payload = {}
            payload.update({
                "job_id": row.job_id,
                "status": "interrupted",
                "message": "服务重启，任务已中断；请重新发起任务",
                "finished_at": now.isoformat(),
            })
            row.status = "interrupted"
            row.payload_json = json.dumps(payload, ensure_ascii=False, default=str)
            row.updated_at = now
            row.finished_at = now
            recovered += 1
        if recovered:
            db.commit()
        return recovered
    finally:
        db.close()


def cleanup_job_history(now: datetime | None = None) -> int:
    now = now or datetime.utcnow()
    cutoff = now - timedelta(hours=JOB_TTL_HOURS)
    db = database.SessionLocal()
    deleted = 0
    try:
        deleted += (
            db.query(models.BackgroundJob)
            .filter(
                models.BackgroundJob.status.in_(TERMINAL_STATUSES),
                models.BackgroundJob.finished_at != None,  # noqa: E711
                models.BackgroundJob.finished_at < cutoff,
            )
            .delete(synchronize_session=False)
        )
        kinds = [row[0] for row in db.query(models.BackgroundJob.kind).distinct().all()]
        for kind in kinds:
            overflow = (
                db.query(models.BackgroundJob)
                .filter(
                    models.BackgroundJob.kind == kind,
                    models.BackgroundJob.status.in_(TERMINAL_STATUSES),
                )
                .order_by(models.BackgroundJob.updated_at.desc())
                .offset(JOB_MAX_ENTRIES)
                .all()
            )
            for row in overflow:
                db.delete(row)
                deleted += 1
        if deleted:
            db.commit()
        return int(deleted)
    finally:
        db.close()


def prune_memory_jobs(
    kind: str,
    registry: MutableMapping[str, Any],
    *,
    now: datetime | None = None,
) -> int:
    now = now or datetime.utcnow()
    cutoff = now - timedelta(hours=JOB_TTL_HOURS)
    removed = 0
    with _LOCK:
        terminal = []
        for key, job in list(registry.items()):
            if _status(job) not in TERMINAL_STATUSES:
                continue
            timestamp = _MEMORY_TIMESTAMPS.get((kind, str(key)), now)
            terminal.append((timestamp, str(key), key))
            if timestamp < cutoff:
                registry.pop(key, None)
                _MEMORY_TIMESTAMPS.pop((kind, str(key)), None)
                removed += 1
        terminal = [item for item in terminal if item[2] in registry]
        terminal.sort()
        while len(registry) >= JOB_MAX_ENTRIES and terminal:
            _, string_key, key = terminal.pop(0)
            registry.pop(key, None)
            _MEMORY_TIMESTAMPS.pop((kind, string_key), None)
            removed += 1
    return removed


def reset_for_tests() -> None:
    with _LOCK:
        _MEMORY_TIMESTAMPS.clear()
