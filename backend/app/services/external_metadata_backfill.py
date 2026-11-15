"""Rate-limited background backfill for WNACG and ASMR work detail metadata."""
from __future__ import annotations

import logging
import os
import re
import time
import uuid
from datetime import datetime
from typing import Any, Optional

from fastapi import BackgroundTasks, HTTPException
from sqlalchemy.orm import Session, selectinload

from .. import asmr_source, database, external_sources, metadata_enrichment, models
from . import job_lifecycle
from .media_operation_guard import project_mutation

logger = logging.getLogger(__name__)

BACKFILL_JOB_KIND = "external_metadata_backfill"
BACKFILL_JOBS: dict[str, dict[str, Any]] = {}

_RJ_RE = re.compile(r"\b(RJ\d{6,8})\b", re.I)


def _needs_external_sidecar(media: models.Media, *, force: bool = False) -> bool:
    if not media.absolute_path or not os.path.isdir(media.absolute_path):
        return False
    if force:
        return True
    sidecar = metadata_enrichment.read_metadata_json(media.absolute_path)
    if not sidecar:
        return True
    return not bool(sidecar.get("scraped"))


def _resolve_wnacg_aid(media: models.Media) -> Optional[str]:
    if media.source_url:
        aid = external_sources.extract_wnacg_aid(media.source_url)
        if aid:
            return aid
    info = metadata_enrichment.read_source_txt(media.absolute_path)
    if info.get("external_id") and info.get("source_site") == "wnacg":
        return info["external_id"]
    return None


def _resolve_asmr_rj(media: models.Media) -> Optional[str]:
    for text in (media.source_url, media.title):
        if text:
            m = _RJ_RE.search(text)
            if m:
                return m.group(1).upper()
    info = metadata_enrichment.read_source_txt(media.absolute_path)
    if info.get("external_id") and info.get("source_site") == "asmr":
        return info["external_id"]
    return None


def _sleep_cancelable(seconds: float, job: Optional[dict[str, Any]]) -> bool:
    remaining = max(0.0, float(seconds))
    while remaining > 0:
        if job is not None and job.get("cancel_requested"):
            return False
        step = min(0.25, remaining)
        time.sleep(step)
        remaining -= step
    return not (job is not None and job.get("cancel_requested"))


def run_external_details_batch(
    db: Session,
    *,
    limit: int = 100,
    delay_seconds: float = 1.0,
    include_wnacg: bool = True,
    include_asmr: bool = True,
    force: bool = False,
    job: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit), 2000))
    safe_delay = max(0.0, min(float(delay_seconds), 10.0))

    wnacg_source = (
        db.query(models.ExternalFavoriteSource)
        .filter(models.ExternalFavoriteSource.source_type == "wnacg")
        .order_by(models.ExternalFavoriteSource.id.desc())
        .first()
    )
    wnacg_cookie = (wnacg_source.cookie or "") if wnacg_source else ""

    asmr_source_row = (
        db.query(models.ExternalFavoriteSource)
        .filter(models.ExternalFavoriteSource.source_type == "asmr")
        .order_by(models.ExternalFavoriteSource.id.desc())
        .first()
    )
    asmr_base = (asmr_source_row.favorites_url if asmr_source_row else None) or asmr_source.DEFAULT_API_BASE
    asmr_token = asmr_source_row.cookie if asmr_source_row else None
    asmr_mirrors = (
        asmr_source.parse_mirrors(asmr_source_row.api_mirrors)
        if asmr_source_row and asmr_source_row.api_mirrors
        else None
    )

    candidates: list[tuple[str, models.Media, str]] = []
    if include_wnacg:
        wnacg_rows = (
            db.query(models.Media)
            .options(selectinload(models.Media.tags), selectinload(models.Media.metadata_profile))
            .filter(
                models.Media.media_type == "manga",
                models.Media.source_site == "wnacg",
                models.Media.is_missing == False,  # noqa: E712
            )
            .order_by(models.Media.id.asc())
            .all()
        )
        for media in wnacg_rows:
            if not _needs_external_sidecar(media, force=force):
                continue
            aid = _resolve_wnacg_aid(media)
            if aid:
                candidates.append(("wnacg", media, aid))

    if include_asmr:
        asmr_rows = (
            db.query(models.Media)
            .options(selectinload(models.Media.tags))
            .filter(
                models.Media.media_type == "audio",
                models.Media.is_missing == False,  # noqa: E712
            )
            .order_by(models.Media.id.asc())
            .all()
        )
        for media in asmr_rows:
            if not _needs_external_sidecar(media, force=force):
                continue
            rj = _resolve_asmr_rj(media)
            if rj:
                candidates.append(("asmr", media, rj))

    selected = candidates[:safe_limit]
    if job is not None:
        job["total"] = len(selected)
        job["status"] = "running"
        job["message"] = f"待抓取 {len(selected)} 项详情元数据" if selected else "没有需要补充详情的作品"
        job_lifecycle.record_job(BACKFILL_JOB_KIND, job)

    summary = {
        "total": len(selected),
        "completed": 0,
        "failed": 0,
        "tags_attached": 0,
        "errors": [],
        "canceled": False,
    }

    for idx, (kind, media, ext_id) in enumerate(selected):
        if job is not None and job.get("cancel_requested"):
            summary["canceled"] = True
            break

        if job is not None:
            job["current_title"] = media.title
            job["message"] = f"正在抓取 ({idx + 1}/{len(selected)})：{media.title}"

        try:
            if kind == "wnacg":
                detail_url = media.source_url or external_sources.wnacg_detail_url(ext_id)
                detail = external_sources.fetch_wnacg_work_detail(detail_url, cookie=wnacg_cookie)
                payload = detail.to_sidecar_dict(source_url=detail_url)
                payload["scraped"] = True
                if not payload.get("title"):
                    payload["title"] = media.title
                metadata_enrichment.write_metadata_json(media.absolute_path, payload)
                with project_mutation():
                    res = metadata_enrichment.enrich_manga_media(db, media, sidecar=payload, force=True)
                    db.commit()
            else:
                detail = asmr_source.fetch_work_detail(asmr_base, asmr_token, ext_id, mirrors=asmr_mirrors)
                payload = detail.to_sidecar_dict()
                payload["scraped"] = True
                metadata_enrichment.write_metadata_json(media.absolute_path, payload)
                with project_mutation():
                    res = metadata_enrichment.enrich_audio_media(db, media, sidecar=payload, force=True)
                    db.commit()

            attached = int(res.get("tags_attached", 0))
            summary["completed"] += 1
            summary["tags_attached"] += attached
            if job is not None:
                job["completed"] = summary["completed"]
                job["tags_attached"] = summary["tags_attached"]
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            err_msg = str(exc)
            logger.warning("External metadata backfill failed for media=%s (%s): %s", media.id, kind, err_msg)
            summary["failed"] += 1
            entry = {"media_id": media.id, "title": media.title, "error": err_msg}
            summary["errors"].append(entry)
            if job is not None:
                job["failed"] = summary["failed"]
                if len(job["errors"]) < 20:
                    job["errors"].append(entry)

        if idx + 1 < len(selected) and safe_delay > 0:
            if not _sleep_cancelable(safe_delay, job):
                summary["canceled"] = True
                break

    return summary


def _run_job_thread(
    job_id: str,
    limit: int,
    delay_seconds: float,
    include_wnacg: bool,
    include_asmr: bool,
    force: bool,
) -> None:
    job = BACKFILL_JOBS[job_id]
    db = database.SessionLocal()
    try:
        summary = run_external_details_batch(
            db,
            limit=limit,
            delay_seconds=delay_seconds,
            include_wnacg=include_wnacg,
            include_asmr=include_asmr,
            force=force,
            job=job,
        )
        job["current_title"] = ""
        job["finished_at"] = datetime.utcnow().isoformat()
        if summary["canceled"] or job.get("cancel_requested"):
            job["status"] = "canceled"
            job["message"] = f"已取消（已完成 {summary['completed']}/{summary['total']}）"
        else:
            job["status"] = "completed"
            job["message"] = (
                f"抓取完成：成功 {summary['completed']}，失败 {summary['failed']}，新增标签 {summary['tags_attached']} 条"
            )
    except Exception as exc:  # noqa: BLE001
        logger.exception("External metadata backfill job %s crashed: %s", job_id, exc)
        job["status"] = "failed"
        job["message"] = str(exc)
        job["finished_at"] = datetime.utcnow().isoformat()
    finally:
        job_lifecycle.record_job(BACKFILL_JOB_KIND, job, finished=True)
        db.close()


def start_external_metadata_backfill_job(
    background_tasks: BackgroundTasks,
    *,
    limit: int = 100,
    delay_seconds: float = 1.0,
    include_wnacg: bool = True,
    include_asmr: bool = True,
    force: bool = False,
) -> dict[str, Any]:
    for existing in BACKFILL_JOBS.values():
        if existing.get("status") in job_lifecycle.ACTIVE_STATUSES:
            return {**existing, "already_running": True}

    try:
        job_lifecycle.admit_new_job(BACKFILL_JOB_KIND, BACKFILL_JOBS)
    except job_lifecycle.JobCapacityError as exc:
        raise HTTPException(status_code=429, detail=str(exc))

    job_id = f"extmeta_{uuid.uuid4().hex[:12]}"
    job: dict[str, Any] = {
        "job_id": job_id,
        "status": "queued",
        "total": 0,
        "completed": 0,
        "failed": 0,
        "tags_attached": 0,
        "current_title": "",
        "message": "任务已入队",
        "cancel_requested": False,
        "errors": [],
        "started_at": datetime.utcnow().isoformat(),
        "finished_at": None,
    }
    BACKFILL_JOBS[job_id] = job
    job_lifecycle.record_job(BACKFILL_JOB_KIND, job)
    background_tasks.add_task(
        _run_job_thread,
        job_id,
        limit,
        delay_seconds,
        include_wnacg,
        include_asmr,
        force,
    )
    return dict(job)


def get_external_metadata_backfill_job(job_id: str) -> Optional[dict[str, Any]]:
    job = BACKFILL_JOBS.get(job_id)
    if job is not None:
        return dict(job)
    return job_lifecycle.get_job_snapshot(BACKFILL_JOB_KIND, job_id)


def cancel_external_metadata_backfill_job(job_id: str) -> Optional[dict[str, Any]]:
    job = BACKFILL_JOBS.get(job_id)
    if job is None:
        return job_lifecycle.get_job_snapshot(BACKFILL_JOB_KIND, job_id)
    if job.get("status") in job_lifecycle.ACTIVE_STATUSES:
        job["cancel_requested"] = True
        job["message"] = "正在取消…"
        job_lifecycle.record_job(BACKFILL_JOB_KIND, job)
    return dict(job)
