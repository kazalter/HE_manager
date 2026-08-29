import os
import shutil
import time
from typing import List, Optional

from ... import asmr_source, database, models
from .. import job_lifecycle
from ..media_access import get_source_or_404
from .covers import (
    ensure_asmr_cover_file,
    external_item_download_dir,
)
from .jobs import DOWNLOAD_JOBS, DownloadCancelled, find_task, is_cancel_requested
from .matching import (
    ensure_external_audio_library,
    find_local_media_for_external_item,
    upsert_external_downloaded_audio_media,
)


def prepare_asmr_download_plan_for_item(item: models.ExternalFavoriteItem, source: models.ExternalFavoriteSource, download_root_path: str):
    """Fetch the /api/tracks tree, apply the source's format + SE-version filters,
    and resolve each track + subtitle to a local destination under the work's folder.
    """
    item_dir = external_item_download_dir(item, source, download_root_path)

    token = source.cookie or ""
    if not token:
        raise RuntimeError("ASMR 来源未登录，请先同步一次以获取令牌")

    working_base = source.favorites_url or asmr_source.DEFAULT_API_BASE
    mirrors = asmr_source.parse_mirrors(source.api_mirrors) if source.api_mirrors else None
    tree = asmr_source.fetch_work_tracks(working_base, token, item.external_id, mirrors=mirrors)

    planned_files = asmr_source.prepare_asmr_download_plan(
        tree,
        audio_format=source.audio_format_filter or "all",
        audio_version=source.audio_version_filter or "all",
        include_subtitles=True,
    )
    if not planned_files:
        raise RuntimeError("没有可下载的音频文件（作品 tracks 为空）")

    files = []
    for planned in planned_files:
        local_path = os.path.join(item_dir, *planned.rel_segments)
        files.append({
            "url": planned.download_url,
            "local_path": local_path,
            "kind": planned.kind,
            "size": planned.size,
        })

    return {
        "item_dir": item_dir,
        "files": files,
    }


def download_asmr_item(item: models.ExternalFavoriteItem, source: models.ExternalFavoriteSource, plan: dict, job: Optional[dict] = None):
    """Stream every file in `plan["files"]` to disk under `plan["item_dir"]`,
    updating job counters as bytes come in.
    """
    item_dir = plan["item_dir"]
    files = plan["files"]
    os.makedirs(item_dir, exist_ok=True)

    downloaded = 0
    skipped = 0
    total_bytes = 0
    audio_track_count = 0
    task = find_task(job, item.id) if job is not None else None

    for index, file_info in enumerate(files, start=1):
        if job is not None and is_cancel_requested(job):
            raise DownloadCancelled(item_dir)

        local_path = file_info["local_path"]
        if file_info["kind"] == "audio":
            audio_track_count += 1

        # Skip if the file already exists with a non-zero size (resume on rerun).
        if os.path.exists(local_path) and os.path.getsize(local_path) > 0:
            skipped += 1
            existing_size = os.path.getsize(local_path)
            total_bytes += existing_size
            if job is not None:
                job["pages_done"] += 1
                job["current_book_downloaded_pages"] += 1
                job["downloaded_bytes"] += existing_size
                if task is not None:
                    task["downloaded_pages"] += 1
            continue

        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        tmp_path = local_path + ".part"
        bytes_written = 0
        try:
            with asmr_source.open_file_stream(file_info["url"]) as response:
                with open(tmp_path, "wb") as out_file:
                    while True:
                        if job is not None and is_cancel_requested(job):
                            raise DownloadCancelled(item_dir)
                        chunk = response.read(64 * 1024)
                        if not chunk:
                            break
                        out_file.write(chunk)
                        bytes_written += len(chunk)
                        if job is not None:
                            job["downloaded_bytes"] += len(chunk)
            os.replace(tmp_path, local_path)
        except BaseException:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except OSError:
                pass
            raise

        downloaded += 1
        total_bytes += bytes_written
        if job is not None:
            job["pages_done"] += 1
            job["current_book_downloaded_pages"] += 1
            if task is not None:
                task["downloaded_pages"] += 1
        time.sleep(0.05)

    ensure_asmr_cover_file(item, item_dir)

    info_path = os.path.join(item_dir, "source.txt")
    with open(info_path, "w", encoding="utf-8") as info_file:
        info_file.write(f"{item.title}\n{item.url}\n{item.external_id}\n")

    return {
        "item_id": item.id,
        "title": item.title,
        "status": "completed",
        "path": item_dir,
        "files": len(files),
        "downloaded": downloaded,
        "skipped": skipped,
        "total_bytes": total_bytes,
        "audio_track_count": audio_track_count,
    }


def cleanup_incomplete_asmr_download(item_dir: str, expected_files: int):
    if not item_dir or not os.path.isdir(item_dir):
        return

    actual = 0
    for _, _, files in os.walk(item_dir):
        actual += len([f for f in files if not f.endswith(".part") and f != "source.txt"])
    if actual >= expected_files and expected_files > 0:
        return

    shutil.rmtree(item_dir, ignore_errors=True)


def run_asmr_download_job(job_id: str, item_ids: List[int], download_root_path: str):
    db = database.SessionLocal()
    job = DOWNLOAD_JOBS[job_id]
    try:
        planned_downloads = []
        job["status"] = "preparing"
        job["message"] = "正在准备下载"

        for item_id in item_ids:
            if is_cancel_requested(job):
                raise DownloadCancelled()

            task = find_task(job, item_id)
            item = db.query(models.ExternalFavoriteItem).filter(models.ExternalFavoriteItem.id == item_id).first()
            if not item:
                job["failed"] += 1
                if task is not None:
                    task["status"] = "failed"
                    task["error"] = "条目不存在"
                job["results"].append({"item_id": item_id, "status": "failed", "error": "条目不存在"})
                continue
            if task is not None:
                task["title"] = item.title
            source = get_source_or_404(item.source_id, db)
            if (source.source_type or "") != "asmr":
                job["failed"] += 1
                if task is not None:
                    task["status"] = "failed"
                    task["error"] = "不是 ASMR 条目"
                job["results"].append({"item_id": item_id, "title": item.title, "status": "failed", "error": "不是 ASMR 条目"})
                continue
            if source.download_root_path != download_root_path:
                source.download_root_path = download_root_path
                db.commit()
            local_media = find_local_media_for_external_item(item, db)
            if local_media:
                job["completed"] += 1
                if task is not None:
                    task["status"] = "success"
                job["results"].append({
                    "item_id": item.id,
                    "title": item.title,
                    "status": "completed",
                    "local_media_id": local_media.id,
                    "skipped": True,
                })
                continue
            ensure_external_audio_library(source, download_root_path, db)
            try:
                job["message"] = f"正在准备：{item.title}"
                plan = prepare_asmr_download_plan_for_item(item, source, download_root_path)
                job["pages_total"] += len(plan["files"])
                if task is not None:
                    task["total_pages"] = len(plan["files"])
                planned_downloads.append((item, source, plan))
            except Exception as exc:
                job["failed"] += 1
                if task is not None:
                    task["status"] = "failed"
                    task["error"] = str(exc)
                job["results"].append({"item_id": item.id, "title": item.title, "status": "failed", "error": str(exc)})

        job["bytes_total_known"] = False
        job["status"] = "running"
        for item, source, plan in planned_downloads:
            if is_cancel_requested(job):
                raise DownloadCancelled()

            task = find_task(job, item.id)
            try:
                job["message"] = f"正在下载：{item.title}"
                job["current_book_title"] = item.title
                job["current_book_total_pages"] = len(plan["files"])
                job["current_book_downloaded_pages"] = 0
                if task is not None:
                    task["status"] = "downloading"
                result = download_asmr_item(item, source, plan, job)
                local_media = upsert_external_downloaded_audio_media(
                    item,
                    source,
                    result["path"],
                    download_root_path,
                    db,
                    track_count=result["audio_track_count"],
                    total_bytes=result["total_bytes"],
                )
                result["local_media_id"] = local_media.id
                job["completed"] += 1
                if task is not None:
                    task["status"] = "success"
                job["results"].append(result)
            except DownloadCancelled as exc:
                cleanup_incomplete_asmr_download(exc.item_dir or plan["item_dir"], len(plan["files"]))
                if task is not None:
                    task["status"] = "failed"
                    task["error"] = "已取消"
                job["results"].append({"item_id": item.id, "title": item.title, "status": "canceled", "path": plan["item_dir"]})
                raise
            except Exception as exc:
                job["failed"] += 1
                if task is not None:
                    task["status"] = "failed"
                    task["error"] = str(exc)
                job["results"].append({"item_id": item.id, "title": item.title, "status": "failed", "error": str(exc)})

        job["current_book_title"] = ""
        job["current_book_total_pages"] = 0
        job["current_book_downloaded_pages"] = 0

        job["status"] = "completed"
        job["message"] = "下载完成"
    except DownloadCancelled:
        job["status"] = "canceled"
        job["message"] = "下载已取消，未完成的作品已清理"
    except Exception as exc:
        job["status"] = "failed"
        job["message"] = str(exc)
    finally:
        job_lifecycle.record_job("external_download", job, finished=True)
        db.close()
