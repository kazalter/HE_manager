import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import ai_config, manga_metadata, manga_profiles, models, recommendations, schemas
from ..database import get_db
from ..services import job_lifecycle
from ..services.media_access import get_media_or_404
from ..services.recommend_jobs import (
    MANGA_METADATA_JOBS,
    MANGA_PROFILE_JOBS,
    run_manga_metadata_job,
    run_manga_profile_job,
)

router = APIRouter()


@router.get("/ai/recommendations/status", response_model=schemas.AiRecommendationStatus)
def ai_recommendation_status():
    config = ai_config.get_deepseek_config()
    return {
        "deepseek_configured": bool(config["api_key"]),
        "model": config["model"],
        "base_url": config["base_url"],
        "key_saved": config["key_saved"],
        "env_key_present": config["env_key_present"],
    }


@router.put("/ai/recommendations/config", response_model=schemas.AiRecommendationStatus)
def update_ai_recommendation_config(payload: schemas.DeepSeekConfigUpdate):
    config = ai_config.update_deepseek_config(
        api_key=payload.api_key,
        model=payload.model,
        base_url=payload.base_url,
        clear_api_key=payload.clear_api_key,
    )
    return {
        "deepseek_configured": bool(config["api_key"]),
        "model": config["model"],
        "base_url": config["base_url"],
        "key_saved": config["key_saved"],
        "env_key_present": config["env_key_present"],
    }


@router.get("/recommend/manga-profiles/stats", response_model=schemas.MangaProfileStats)
def manga_profile_stats(db: Session = Depends(get_db)):
    return manga_profiles.profile_stats(db)


@router.post("/recommend/manga-profiles/analyze", response_model=schemas.MangaProfileJob)
def analyze_manga_profiles(
    payload: schemas.MangaProfileAnalyzeRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    if payload.media_id:
        media = get_media_or_404(payload.media_id, db)
        if media.media_type != "manga":
            raise HTTPException(status_code=400, detail="只能分析漫画")
        media_ids = [media.id]
    else:
        query = db.query(models.Media).filter(
            models.Media.media_type == "manga",
            models.Media.is_missing == False,  # noqa: E712
            models.Media.duplicate_status.notin_(["checking", "strong_duplicate", "suspected_duplicate", "dedup_excluded"]),
        )
        rows = query.order_by(models.Media.id.desc()).all()
        media_ids = [
            media.id for media in rows
            if payload.force or manga_profiles.needs_profile(media)
        ][: payload.limit]

    try:
        job_lifecycle.admit_new_job("manga_profile", MANGA_PROFILE_JOBS)
    except job_lifecycle.JobCapacityError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    job_id = str(uuid.uuid4())
    MANGA_PROFILE_JOBS[job_id] = {
        "job_id": job_id,
        "status": "queued",
        "total": len(media_ids),
        "completed": 0,
        "failed": 0,
        "message": "准备分析内容画像",
        "current_title": "",
        "errors": [],
    }
    job_lifecycle.record_job("manga_profile", MANGA_PROFILE_JOBS[job_id])
    background_tasks.add_task(run_manga_profile_job, job_id, media_ids, payload.sample_count, payload.force)
    return MANGA_PROFILE_JOBS[job_id]


@router.get("/recommend/manga-profiles/jobs/{job_id}", response_model=schemas.MangaProfileJob)
def get_manga_profile_job(job_id: str):
    job = MANGA_PROFILE_JOBS.get(job_id) or job_lifecycle.get_job_snapshot("manga_profile", job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return job


@router.get("/recommend/manga-metadata/stats", response_model=schemas.MangaMetadataStats)
def manga_metadata_stats(db: Session = Depends(get_db)):
    return manga_metadata.profile_stats(db)


@router.post("/recommend/manga-metadata/analyze", response_model=schemas.MangaMetadataJob)
def analyze_manga_metadata(
    payload: schemas.MangaMetadataAnalyzeRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    if payload.media_id:
        media = get_media_or_404(payload.media_id, db)
        if media.media_type != "manga":
            raise HTTPException(status_code=400, detail="只能补全漫画元数据")
        media_ids = [media.id]
    else:
        rows = (
            db.query(models.Media)
            .filter(
                models.Media.media_type == "manga",
                models.Media.is_missing == False,  # noqa: E712
            )
            .order_by(models.Media.id.desc())
            .all()
        )
        media_ids = [
            media.id for media in rows
            if payload.force or manga_metadata.needs_metadata(media)
        ][: payload.limit]

    try:
        job_lifecycle.admit_new_job("manga_metadata", MANGA_METADATA_JOBS)
    except job_lifecycle.JobCapacityError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    job_id = str(uuid.uuid4())
    MANGA_METADATA_JOBS[job_id] = {
        "job_id": job_id,
        "status": "queued",
        "total": len(media_ids),
        "completed": 0,
        "failed": 0,
        "message": "准备补全元数据",
        "current_title": "",
        "errors": [],
    }
    job_lifecycle.record_job("manga_metadata", MANGA_METADATA_JOBS[job_id])
    background_tasks.add_task(run_manga_metadata_job, job_id, media_ids, payload.force)
    return MANGA_METADATA_JOBS[job_id]


@router.get("/recommend/manga-metadata/jobs/{job_id}", response_model=schemas.MangaMetadataJob)
def get_manga_metadata_job(job_id: str):
    job = MANGA_METADATA_JOBS.get(job_id) or job_lifecycle.get_job_snapshot("manga_metadata", job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return job


@router.post("/recommend/manga", response_model=schemas.MangaRecommendationResponse)
def recommend_manga(payload: schemas.MangaRecommendationRequest, db: Session = Depends(get_db)):
    return recommendations.recommend_manga(
        db=db,
        query=payload.query,
        limit=payload.limit,
        avoid_tags=payload.avoid_tags,
        preferred_tags=payload.preferred_tags,
    )
