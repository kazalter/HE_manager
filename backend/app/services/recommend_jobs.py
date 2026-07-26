from .. import database, manga_metadata, manga_profiles, models
from . import job_lifecycle

MANGA_PROFILE_JOBS = {}
MANGA_METADATA_JOBS = {}


def run_manga_profile_job(job_id: str, media_ids: list[int], sample_count: int, force: bool):
    db = database.SessionLocal()
    job = MANGA_PROFILE_JOBS[job_id]
    try:
        job["status"] = "running"
        for media_id in media_ids:
            media = db.query(models.Media).filter(models.Media.id == media_id).first()
            if not media:
                job["failed"] += 1
                job["errors"].append(f"Media {media_id} not found")
                continue
            job["current_title"] = media.title or str(media.id)
            try:
                manga_profiles.analyze_media(db, media, sample_count=sample_count, force=force)
                db.commit()
                job["completed"] += 1
                job["message"] = f"已分析 {job['completed']} / {job['total']}"
            except Exception as exc:  # noqa: BLE001 - batch job should continue
                db.rollback()
                job["failed"] += 1
                job["errors"].append(f"{media.title or media.id}: {exc}")
        job["status"] = "completed"
        job["current_title"] = ""
        job["message"] = f"完成：{job['completed']} 个，失败 {job['failed']} 个"
    except Exception as exc:  # noqa: BLE001
        job["status"] = "failed"
        job["message"] = str(exc)
    finally:
        job_lifecycle.record_job("manga_profile", job, finished=True)
        db.close()


def run_manga_metadata_job(job_id: str, media_ids: list[int], force: bool):
    db = database.SessionLocal()
    job = MANGA_METADATA_JOBS[job_id]
    try:
        job["status"] = "running"
        for media_id in media_ids:
            media = db.query(models.Media).filter(models.Media.id == media_id).first()
            if not media:
                job["failed"] += 1
                job["errors"].append(f"Media {media_id} not found")
                continue
            job["current_title"] = media.title or str(media.id)
            try:
                manga_metadata.build_metadata_profile(db, media, force=force)
                db.commit()
                job["completed"] += 1
                job["message"] = f"已补全 {job['completed']} / {job['total']}"
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                job["failed"] += 1
                job["errors"].append(f"{media.title or media.id}: {exc}")
        job["status"] = "completed"
        job["current_title"] = ""
        job["message"] = f"完成：{job['completed']} 个，失败 {job['failed']} 个"
    except Exception as exc:  # noqa: BLE001
        job["status"] = "failed"
        job["message"] = str(exc)
    finally:
        job_lifecycle.record_job("manga_metadata", job, finished=True)
        db.close()
