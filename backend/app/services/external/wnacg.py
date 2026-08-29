from datetime import datetime
import glob
import os
import re
import shutil
import time
import uuid
import zipfile
from typing import List, Optional
from urllib.parse import urljoin

from ... import database, external_sources, models, scanner
from .. import job_lifecycle
from ..media_access import get_source_or_404
from .covers import (
    external_item_download_dir,
    get_image_extension,
    normalize_download_root,
)
from .jobs import DOWNLOAD_JOBS, DownloadCancelled, find_task, is_cancel_requested
from .matching import (
    ensure_external_manga_library,
    find_local_media_for_external_item,
    upsert_external_downloaded_media,
)

WNACG_ARCHIVE_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"}


def cleanup_incomplete_download(item_dir: str, expected_pages: int):
    if not item_dir or not os.path.isdir(item_dir):
        return

    existing_pages = scanner.count_manga_pages(item_dir, ".dir") or 0
    if existing_pages >= expected_pages:
        return

    shutil.rmtree(item_dir, ignore_errors=True)


def _natural_path_key(path: str):
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", path)]


def _write_wnacg_source_marker(item: models.ExternalFavoriteItem, item_dir: str) -> None:
    info_path = os.path.join(item_dir, "source.txt")
    with open(info_path, "w", encoding="utf-8") as info_file:
        info_file.write(f"{item.title}\n{item.url}\n")


def _advance_wnacg_job_progress(job: Optional[dict], task: Optional[dict], pages: int = 0, bytes_count: int = 0) -> None:
    if job is None:
        return
    if pages:
        job["pages_done"] += pages
        job["current_book_downloaded_pages"] += pages
        if task is not None:
            task["downloaded_pages"] += pages
    if bytes_count:
        job["downloaded_bytes"] += bytes_count


def _extract_wnacg_zip_archive(archive_path: str, item_dir: str) -> dict:
    if not zipfile.is_zipfile(archive_path):
        raise RuntimeError("压缩包不是有效 ZIP 文件")

    temp_dir = os.path.join(item_dir, f".archive_extract_{uuid.uuid4().hex}")
    os.makedirs(temp_dir, exist_ok=True)
    try:
        with zipfile.ZipFile(archive_path, "r") as archive:
            image_members = [
                info
                for info in archive.infolist()
                if not info.is_dir()
                and os.path.splitext(info.filename)[1].lower() in WNACG_ARCHIVE_IMAGE_EXTENSIONS
                and "__macosx/" not in info.filename.lower()
            ]
            image_members.sort(key=lambda info: _natural_path_key(info.filename))
            if not image_members:
                raise RuntimeError("压缩包里没有可用图片")

            staged_paths = []
            for index, info in enumerate(image_members, start=1):
                ext = os.path.splitext(info.filename)[1].lower()
                staged_path = os.path.join(temp_dir, f"{index:03d}{ext}")
                with archive.open(info, "r") as src, open(staged_path, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                staged_paths.append(staged_path)

        downloaded = 0
        skipped = 0
        for staged_path in staged_paths:
            stem = os.path.splitext(os.path.basename(staged_path))[0]
            existing = glob.glob(os.path.join(item_dir, f"{stem}.*"))
            if existing:
                skipped += 1
                continue
            shutil.move(staged_path, os.path.join(item_dir, os.path.basename(staged_path)))
            downloaded += 1

        return {
            "pages": len(staged_paths),
            "downloaded": downloaded,
            "skipped": skipped,
        }
    except zipfile.BadZipFile as exc:
        raise RuntimeError("压缩包损坏或无法读取") from exc
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def _resolve_wnacg_archive_urls(item: models.ExternalFavoriteItem, source: models.ExternalFavoriteSource, plan: dict) -> List[str]:
    urls: List[str] = []
    worker_request = plan.get("archive_worker_request")
    if worker_request is not None:
        try:
            signed_url = external_sources.resolve_wnacg_worker_archive_url(
                worker_request,
                cookie=source.cookie or "",
                referer=plan.get("download_page_url") or item.url,
                proxy=source.proxy,
            )
            if signed_url:
                urls.append(signed_url)
        except Exception as exc:  # noqa: BLE001 - fallback to static archive links / per-page download
            print(f"  ! Failed to resolve wnacg archive worker URL for {item.title!r}: {exc}")

    for url in plan.get("archive_urls") or []:
        if url and url not in urls:
            urls.append(url)
    return urls


def _try_download_wnacg_archive(
    item: models.ExternalFavoriteItem,
    source: models.ExternalFavoriteSource,
    plan: dict,
    job: Optional[dict] = None,
) -> Optional[dict]:
    archive_urls = _resolve_wnacg_archive_urls(item, source, plan)
    if not archive_urls:
        return None

    item_dir = plan["item_dir"]
    os.makedirs(item_dir, exist_ok=True)
    task = find_task(job, item.id) if job is not None else None
    expected_pages = len(plan.get("image_urls") or [])
    last_error: Optional[Exception] = None

    for archive_url in archive_urls:
        if job is not None and is_cancel_requested(job):
            raise DownloadCancelled(item_dir)

        archive_path = os.path.join(item_dir, f".wnacg_archive_{uuid.uuid4().hex}.zip")
        bytes_before_attempt = int(job.get("downloaded_bytes", 0)) if job is not None else 0
        try:
            def on_chunk(size: int) -> None:
                if job is not None and is_cancel_requested(job):
                    raise DownloadCancelled(item_dir)
                _advance_wnacg_job_progress(job, task, bytes_count=size)

            external_sources.fetch_file_to_path(
                archive_url,
                source.cookie or "",
                archive_path,
                referer=plan.get("download_page_url") or item.url,
                proxy=source.proxy,
                on_chunk=on_chunk,
            )
            extracted = _extract_wnacg_zip_archive(archive_path, item_dir)
            actual_pages = extracted["pages"]
            if job is not None:
                delta = actual_pages - expected_pages
                if delta:
                    job["pages_total"] += delta
                    job["current_book_total_pages"] = actual_pages
                    if task is not None:
                        task["total_pages"] = actual_pages
                _advance_wnacg_job_progress(job, task, pages=actual_pages)
            _write_wnacg_source_marker(item, item_dir)
            return {
                "item_id": item.id,
                "title": item.title,
                "status": "completed",
                "path": item_dir,
                "pages": actual_pages,
                "downloaded": extracted["downloaded"],
                "skipped": extracted["skipped"],
                "method": "archive",
            }
        except DownloadCancelled:
            raise
        except Exception as exc:  # noqa: BLE001 - try the next archive URL, then image fallback
            if job is not None:
                job["downloaded_bytes"] = bytes_before_attempt
            last_error = exc
            print(f"  ! WNACG archive download failed for {item.title!r}: {exc}")
        finally:
            if os.path.exists(archive_path):
                try:
                    os.remove(archive_path)
                except OSError:
                    pass

    if last_error is not None:
        print(f"  ! Falling back to per-page WNACG download for {item.title!r}")
    return None


def log_wnacg_download_failure(download_root_path: str, title: str, url: str, error: str):
    try:
        root = normalize_download_root(download_root_path, "wnacg")
        manga_dir = os.path.join(root, "manga")
        os.makedirs(manga_dir, exist_ok=True)
        log_path = os.path.join(manga_dir, "_download_errors.log")
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(log_path, "a", encoding="utf-8") as log_file:
            log_file.write(f"[{timestamp}] {title} | {url} | {error}\n")
    except Exception:
        pass


def prepare_wnacg_download_plan(item: models.ExternalFavoriteItem, source: models.ExternalFavoriteSource, download_root_path: str):
    item_dir = external_item_download_dir(item, source, download_root_path)

    item_api_url = urljoin(item.url, f"/photos-item-aid-{item.external_id}.html")
    item_html = external_sources.fetch_html(item_api_url, source.cookie or "", proxy=source.proxy)
    image_urls = external_sources.parse_wnacg_image_urls(item_html)
    if not image_urls:
        raise RuntimeError("没有解析到图片地址")

    download_page_url = external_sources.wnacg_download_url(item.external_id)
    archive_urls: List[str] = []
    archive_worker_request = None
    try:
        download_html = external_sources.fetch_html(download_page_url, source.cookie or "", proxy=source.proxy)
        archive_worker_request = external_sources.parse_wnacg_worker_archive_request(download_html)
        archive_urls = external_sources.parse_wnacg_archive_urls(download_html, base_url=download_page_url)
    except Exception as exc:  # noqa: BLE001 - the image downloader below remains the fallback
        print(f"  ! Failed to inspect wnacg archive page for {item.title!r}: {exc}")

    return {
        "item_dir": item_dir,
        "image_urls": image_urls,
        "download_page_url": download_page_url,
        "archive_urls": archive_urls,
        "archive_worker_request": archive_worker_request,
    }


def download_wnacg_item(item: models.ExternalFavoriteItem, source: models.ExternalFavoriteSource, plan: dict, job: Optional[dict] = None):
    item_dir = plan["item_dir"]
    image_urls = plan["image_urls"]
    os.makedirs(item_dir, exist_ok=True)
    downloaded = 0
    skipped = 0
    task = find_task(job, item.id) if job is not None else None

    archive_result = _try_download_wnacg_archive(item, source, plan, job)
    if archive_result is not None:
        return archive_result

    for index, image_url in enumerate(image_urls, start=1):
        if job is not None and is_cancel_requested(job):
            raise DownloadCancelled(item_dir)

        existing = glob.glob(os.path.join(item_dir, f"{index:03d}.*"))
        if existing:
            skipped += 1
            _advance_wnacg_job_progress(job, task, pages=1)
            continue
        content, content_type = external_sources.fetch_binary(image_url, source.cookie or "", referer=item.url, proxy=source.proxy)
        extension = get_image_extension(content_type, image_url)
        image_path = os.path.join(item_dir, f"{index:03d}{extension}")
        with open(image_path, "wb") as image_file:
            image_file.write(content)
        downloaded += 1
        _advance_wnacg_job_progress(job, task, pages=1, bytes_count=len(content))
        time.sleep(0.15)

    _write_wnacg_source_marker(item, item_dir)

    return {
        "item_id": item.id,
        "title": item.title,
        "status": "completed",
        "path": item_dir,
        "pages": len(image_urls),
        "downloaded": downloaded,
        "skipped": skipped,
        "method": "images",
    }


def run_wnacg_download_job(job_id: str, item_ids: List[int], download_root_path: str):
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
            if source.source_type != "wnacg":
                job["failed"] += 1
                if task is not None:
                    task["status"] = "failed"
                    task["error"] = "暂不支持这个站点"
                job["results"].append({"item_id": item_id, "title": item.title, "status": "failed", "error": "暂不支持这个站点"})
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
            ensure_external_manga_library(source, download_root_path, db)
            try:
                job["message"] = f"正在准备：{item.title}"
                plan = prepare_wnacg_download_plan(item, source, download_root_path)
                job["pages_total"] += len(plan["image_urls"])
                if task is not None:
                    task["total_pages"] = len(plan["image_urls"])
                planned_downloads.append((item, source, plan))
            except Exception as exc:
                job["failed"] += 1
                if task is not None:
                    task["status"] = "failed"
                    task["error"] = str(exc)
                job["results"].append({"item_id": item.id, "title": item.title, "status": "failed", "error": str(exc)})
                log_wnacg_download_failure(download_root_path, item.title, item.url, str(exc))

        job["bytes_total_known"] = False
        job["status"] = "running"
        for item, source, plan in planned_downloads:
            if is_cancel_requested(job):
                raise DownloadCancelled()

            task = find_task(job, item.id)
            try:
                job["message"] = f"正在下载：{item.title}"
                job["current_book_title"] = item.title
                job["current_book_total_pages"] = len(plan["image_urls"])
                job["current_book_downloaded_pages"] = 0
                if task is not None:
                    task["status"] = "downloading"
                result = download_wnacg_item(item, source, plan, job)
                local_media = upsert_external_downloaded_media(item, source, result["path"], download_root_path, db)
                result["local_media_id"] = local_media.id
                job["completed"] += 1
                if task is not None:
                    task["status"] = "success"
                job["results"].append(result)
            except DownloadCancelled as exc:
                cleanup_incomplete_download(exc.item_dir or plan["item_dir"], len(plan["image_urls"]))
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
                log_wnacg_download_failure(download_root_path, item.title, item.url, str(exc))

        job["current_book_title"] = ""
        job["current_book_total_pages"] = 0
        job["current_book_downloaded_pages"] = 0

        job["status"] = "completed"
        job["message"] = "下载完成"
    except DownloadCancelled:
        job["status"] = "canceled"
        job["message"] = "下载已取消，未完成的漫画已删除"
    except Exception as exc:
        job["status"] = "failed"
        job["message"] = str(exc)
    finally:
        job_lifecycle.record_job("external_download", job, finished=True)
        db.close()
