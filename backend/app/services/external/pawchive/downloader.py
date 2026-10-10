"""Explicit per-attachment Pawchive downloads into ordinary Media rows."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import threading
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from .... import database, models, scanner
from ... import job_lifecycle, storage_guard
from ...thumbnails import THUMBNAIL_DIR
from . import client, normalize, provider, refs

logger = logging.getLogger(__name__)
JOB_KIND = "pawchive"
DOWNLOAD_JOBS: dict[str, dict] = {}
_CANCEL: dict[str, threading.Event] = {}
_ADMISSION_LOCK = threading.Lock()
_TRANSFER_LIMIT = threading.Semaphore(2)
MAX_SELECTIONS = 20
MAX_ATTACHMENTS = 500
MAX_BYTES = max(1, int(os.getenv("HE_PAWCHIVE_MAX_BYTES", str(2 * 1024 ** 3))))
RESERVE_BYTES = 256 * 1024 ** 2


class DownloadCanceled(Exception):
    pass


def _ensure_download_storage(root: Path) -> None:
    sentinel = os.getenv("HE_PAWCHIVE_STORAGE_SENTINEL", "").strip() or None
    try:
        storage_guard.ensure_storage_available(str(root), purpose="pawchive_download", sentinel_name=sentinel)
    except storage_guard.StorageNotMountedError as exc:
        raise client.PawchiveError("STORAGE_UNAVAILABLE", "Pawchive 存储不可用", 503) from exc


def download_root() -> Path:
    configured = os.getenv("HE_PAWCHIVE_DOWNLOAD_ROOT", "").strip()
    if not configured or not os.path.isabs(configured):
        raise client.PawchiveError("STORAGE_UNAVAILABLE", "未配置 Pawchive 下载根目录", 503)
    root = Path(configured).resolve()
    if not root.is_dir():
        raise client.PawchiveError("STORAGE_UNAVAILABLE", "Pawchive 下载根目录不存在", 503)
    _ensure_download_storage(root)
    if not os.access(root, os.W_OK):
        raise client.PawchiveError("STORAGE_UNAVAILABLE", "Pawchive 下载根目录不可写", 503)
    return root


def _healthy_attachment(row: models.PawchiveAttachment, db: Session) -> bool:
    if row.status != "completed" or not row.local_path or not row.media_id:
        return False
    media = db.get(models.Media, row.media_id)
    if not media or media.absolute_path != row.local_path or not os.path.isfile(row.local_path):
        return False
    size, digest = _hash_file(Path(row.local_path))
    return bool(row.file_size == size and row.sha256 == digest)


def _serialize_attachment(row: models.PawchiveAttachment) -> dict:
    return {"attachment_key": row.attachment_key, "filename": row.filename,
            "status": row.status, "error": row.error, "media_id": row.media_id,
            "file_size": row.file_size}


def preview_download(selections: list[dict], db: Session) -> dict:
    download_root()
    if not selections or len(selections) > MAX_SELECTIONS:
        raise client.PawchiveError("INVALID_REQUEST", "每次请选择 1～20 篇帖子", 400)
    seen = set()
    supported = 0
    unsupported = 0
    already = 0
    for selection in selections:
        detail = provider.post_detail(selection["service"], selection["creator_id"], selection["post_id"])
        available = {a["attachment_key"]: a for a in detail["attachments"]}
        keys = selection.get("attachment_keys")
        if keys is not None and (not keys or any(key not in available for key in keys)):
            raise client.PawchiveError("INVALID_REQUEST", "附件不属于所选帖子", 400)
        chosen = [available[key] for key in keys] if keys is not None else list(available.values())
        post = db.query(models.PawchivePost).filter_by(
            service=detail["service"], creator_id=detail["creator_id"], post_id=detail["post_id"]
        ).first()
        for item in chosen:
            identity = (detail["service"], detail["creator_id"], detail["post_id"], item["attachment_key"])
            if identity in seen:
                continue
            seen.add(identity)
            if item["availability"] != "playable":
                unsupported += 1
                continue
            supported += 1
            if post:
                row = db.query(models.PawchiveAttachment).filter_by(
                    post_id=post.id, attachment_key=item["attachment_key"]
                ).first()
                if row and _healthy_attachment(row, db):
                    already += 1
    return {"selected_posts": len(selections), "supported": supported,
            "unsupported": unsupported, "already_downloaded": already,
            "unknown_size": supported - already}


def create_download(selections: list[dict], db: Session, background_tasks) -> dict:
    download_root()
    if not selections or len(selections) > MAX_SELECTIONS:
        raise client.PawchiveError("INVALID_REQUEST", "每次请选择 1～20 篇帖子", 400)
    # Resolve every requested attachment against fresh public detail before
    # reserving any database state. Caller-provided URLs/filenames are ignored.
    requested = []
    seen_requested = set()
    for selection in selections:
        detail = provider.post_detail(selection["service"], selection["creator_id"], selection["post_id"])
        available = {a["attachment_key"]: a for a in detail["attachments"] if a["availability"] == "playable"}
        keys = selection.get("attachment_keys")
        if keys is not None and not keys:
            raise client.PawchiveError("INVALID_REQUEST", "未选择附件", 400)
        chosen = [available[key] for key in keys] if keys is not None and all(key in available for key in keys) else (
            list(available.values()) if keys is None else None)
        if chosen is None:
            raise client.PawchiveError("INVALID_REQUEST", "附件不属于所选帖子或格式不支持", 400)
        for attachment in chosen:
            identity = (detail["service"], detail["creator_id"], detail["post_id"], attachment["attachment_key"])
            if identity not in seen_requested:
                seen_requested.add(identity)
                requested.append((detail, attachment))
    if not requested or len(requested) > MAX_ATTACHMENTS:
        raise client.PawchiveError("MEDIA_UNSUPPORTED", "没有可下载的图片或视频，或附件数量超出限制", 400)
    with _ADMISSION_LOCK:
        job_id = uuid.uuid4().hex
        pending_ids = []
        already = []
        active_job_id = None
        for detail, attachment in requested:
            post = (db.query(models.PawchivePost).filter_by(
                service=detail["service"], creator_id=detail["creator_id"], post_id=detail["post_id"]
            ).first())
            if not post:
                post = models.PawchivePost(service=detail["service"], creator_id=detail["creator_id"],
                                           post_id=detail["post_id"])
                db.add(post)
                db.flush()
            post.title = detail["title"]
            post.creator_name = detail["creator_name"]
            post.source_url = detail["source_url"]
            row = db.query(models.PawchiveAttachment).filter_by(
                post_id=post.id, attachment_key=attachment["attachment_key"]
            ).first()
            if not row:
                row = models.PawchiveAttachment(
                    post_id=post.id, attachment_key=attachment["attachment_key"],
                    original_index=attachment["original_index"], filename=attachment["filename"],
                    media_type=attachment["media_type"],
                )
                db.add(row)
            row.original_index = attachment["original_index"]
            row.filename = attachment["filename"]
            row.media_type = attachment["media_type"]
            if _healthy_attachment(row, db):
                already.append(_serialize_attachment(row))
                continue
            if row.status in {"queued", "downloading"} and row.job_id and row.job_id in DOWNLOAD_JOBS:
                active_job_id = row.job_id
                continue
            row.status = "queued"
            row.job_id = job_id
            row.error = None
            db.flush()
            pending_ids.append(row.id)
        if pending_ids:
            try:
                job_lifecycle.admit_new_job(JOB_KIND, DOWNLOAD_JOBS)
            except job_lifecycle.JobCapacityError as exc:
                db.rollback()
                raise client.PawchiveError("JOB_CAPACITY", "下载任务过多，请稍后再试", 429) from exc
        db.commit()
        if not pending_ids:
            return {"job_id": active_job_id, "status": "already_downloaded" if already else "already_queued",
                    "queued": 0, "already_downloaded": already}
        job = {"job_id": job_id, "status": "queued", "total": len(pending_ids),
               "completed": 0, "failed": 0, "canceled": 0, "attachment_ids": pending_ids,
               "attachments": [], "message": "等待下载"}
        DOWNLOAD_JOBS[job_id] = job
        _CANCEL[job_id] = threading.Event()
        job_lifecycle.record_job(JOB_KIND, job)
        background_tasks.add_task(run_download_job, job_id)
        return {"job_id": job_id, "status": "queued", "queued": len(pending_ids),
                "already_downloaded": already}


def _target(root: Path, post: models.PawchivePost, row: models.PawchiveAttachment, path: str) -> tuple[Path, Path]:
    for value in (post.service, post.creator_id, post.post_id):
        provider.validate_id(value)
    extension = "." + path.rsplit(".", 1)[-1]
    filename = f"{row.original_index:03d}_{row.attachment_key[:16]}{extension}"
    directory = root / "pawchive" / post.service / post.creator_id / post.post_id
    _ensure_download_storage(root)
    if os.path.commonpath((str(root), str(directory.resolve()))) != str(root):
        raise client.PawchiveError("INVALID_PATH", "下载路径越界", 400)
    directory.mkdir(parents=True, exist_ok=True)
    if os.path.commonpath((str(root), str(directory.resolve()))) != str(root):
        raise client.PawchiveError("INVALID_PATH", "下载路径越界", 400)
    target = directory / filename
    manifest = directory / f".{filename}.json"
    return target, manifest


def _magic_matches(path: Path, media_type: str, extension: str | None = None) -> bool:
    with path.open("rb") as file:
        head = file.read(32)
    ext = (extension or path.suffix).lower()
    if media_type == "video":
        return (ext == ".mp4" and len(head) >= 12 and head[4:8] == b"ftyp") or (
            ext == ".webm" and head.startswith(b"\x1a\x45\xdf\xa3"))
    return (
        (ext in {".jpg", ".jpeg"} and head.startswith(b"\xff\xd8\xff"))
        or (ext == ".png" and head.startswith(b"\x89PNG\r\n\x1a\n"))
        or (ext == ".gif" and head.startswith((b"GIF87a", b"GIF89a")))
        or (ext == ".webp" and head[:4] == b"RIFF" and head[8:12] == b"WEBP")
        or (ext == ".avif" and head[4:12] in {b"ftypavif", b"ftypavis"})
    )


def _hash_file(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    count = 0
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            count += len(chunk)
            digest.update(chunk)
    return count, digest.hexdigest()


def _reusable(target: Path, manifest: Path, key: str, media_type: str) -> tuple[int, str] | None:
    if not target.is_file() or not manifest.is_file():
        return None
    try:
        record = json.loads(manifest.read_text())
        size, digest = _hash_file(target)
        if (record.get("attachment_key") == key and record.get("size") == size
                and record.get("sha256") == digest and size > 0 and _magic_matches(target, media_type)):
            return size, digest
    except (OSError, ValueError, TypeError):
        pass
    return None


def _fetch_file(path: str, target: Path, manifest: Path, row: models.PawchiveAttachment,
                stop: threading.Event, root: Path) -> tuple[int, str]:
    existing = _reusable(target, manifest, row.attachment_key, row.media_type)
    if existing:
        return existing
    _ensure_download_storage(root)
    temp = target.with_name(f".{target.name}.{uuid.uuid4().hex}.part")
    connection = None
    try:
        connection, response = client.open_media(path)
        content_type = (response.getheader("Content-Type") or "").lower()
        if response.status != 200 or not content_type.startswith(row.media_type + "/"):
            raise client.PawchiveError("UPSTREAM_INVALID", "来源返回了无效文件", 502)
        declared = response.getheader("Content-Length")
        expected = int(declared) if declared and declared.isdigit() else None
        if expected is not None and expected > MAX_BYTES:
            raise client.PawchiveError("MEDIA_TOO_LARGE", "文件超出下载大小限制", 413)
        if expected and shutil.disk_usage(root).free < expected + RESERVE_BYTES:
            raise client.PawchiveError("STORAGE_UNAVAILABLE", "磁盘剩余空间不足", 503)
        size = 0
        digest = hashlib.sha256()
        with temp.open("xb") as output:
            while chunk := response.read(1024 * 1024):
                if stop.is_set():
                    raise DownloadCanceled()
                size += len(chunk)
                if size > MAX_BYTES:
                    raise client.PawchiveError("MEDIA_TOO_LARGE", "文件超出下载大小限制", 413)
                output.write(chunk)
                digest.update(chunk)
            output.flush()
            os.fsync(output.fileno())
        if not size or (expected is not None and size != expected) or not _magic_matches(temp, row.media_type, target.suffix):
            raise client.PawchiveError("UPSTREAM_INVALID", "文件校验失败", 502)
        if stop.is_set():
            raise DownloadCanceled()
        _ensure_download_storage(root)
        if shutil.disk_usage(root).free < RESERVE_BYTES:
            raise client.PawchiveError("STORAGE_UNAVAILABLE", "磁盘剩余空间不足", 503)
        record = {"attachment_key": row.attachment_key, "size": size, "sha256": digest.hexdigest()}
        manifest_temp = manifest.with_name(manifest.name + "." + uuid.uuid4().hex + ".tmp")
        with manifest_temp.open("x", encoding="utf-8") as output:
            json.dump(record, output, separators=(",", ":"))
            output.flush()
            os.fsync(output.fileno())
        os.replace(manifest_temp, manifest)
        os.replace(temp, target)
        return size, digest.hexdigest()
    finally:
        if connection:
            connection.close()
        temp.unlink(missing_ok=True)
        if "manifest_temp" in locals():
            manifest_temp.unlink(missing_ok=True)


def _ensure_folder(root: Path, db: Session) -> models.Folder:
    folder_path = str(root / "pawchive")
    folder = db.query(models.Folder).filter_by(path=folder_path).first()
    if not folder:
        folder = models.Folder(path=folder_path, scan_mode="auto", status="idle",
                               thumbnail_enabled=True, thumbnail_interval=1)
        db.add(folder)
        db.flush()
    return folder


def _admit_media(root: Path, row: models.PawchiveAttachment, target: Path,
                 size: int, digest: str, db: Session) -> int:
    folder = _ensure_folder(root, db)
    media = db.query(models.Media).filter_by(absolute_path=str(target)).first()
    if not media:
        media = models.Media(absolute_path=str(target))
        db.add(media)
    media.folder_id = folder.id
    media.relative_path = os.path.relpath(target, folder.path)
    media.title = f"{row.post.title} · {row.filename}"[:500]
    media.media_type = row.media_type
    media.extension = target.suffix
    media.file_size = size
    media.source_url = row.post.source_url
    media.source_site = "pawchive"
    media.artist = row.post.creator_name
    media.is_missing = False
    db.flush()
    row.media_id = media.id
    row.local_path = str(target)
    row.file_size = size
    row.sha256 = digest
    row.status = "completed"
    row.error = None
    db.commit()
    if not media.cover_path:
        thumbnail_name = "pawchive_" + hashlib.sha256(str(target).encode()).hexdigest()[:24] + ".jpg"
        thumbnail_path = os.path.join(THUMBNAIL_DIR, thumbnail_name)
        try:
            success = scanner.get_image_thumbnail(str(target), thumbnail_path) if row.media_type == "image" else scanner.get_video_thumbnail(str(target), thumbnail_path)
            if success:
                media.cover_path = thumbnail_name
                db.commit()
        except Exception as exc:
            logger.warning("Pawchive thumbnail generation failed for media %s: %s", media.id, type(exc).__name__)
    return media.id


def _download_one(row_id: int, job_id: str, stop: threading.Event, root: Path, db: Session) -> dict:
    row = db.get(models.PawchiveAttachment, row_id)
    if not row or row.job_id != job_id:
        return {"attachment_id": row_id, "status": "interrupted", "error": "任务附件状态已变化"}
    if stop.is_set():
        row.status = "canceled"
        db.commit()
        return {"attachment_id": row_id, **_serialize_attachment(row)}
    row.status = "downloading"
    db.commit()
    failure: client.PawchiveError | None = None
    try:
        detail = provider.post_detail(row.post.service, row.post.creator_id, row.post.post_id)
        item = next((a for a in detail["attachments"] if a["attachment_key"] == row.attachment_key), None)
        if not item or item["availability"] != "playable" or item["media_type"] != row.media_type:
            raise client.PawchiveError("MEDIA_UNSUPPORTED", "来源附件已变化或不可下载", 415)
        path, _ = refs.read_media(item["stream_ref"])
        target, manifest = _target(root, row.post, row, path)
        size, digest = _fetch_file(path, target, manifest, row, stop, root)
        media_id = _admit_media(root, row, target, size, digest, db)
        return {"attachment_id": row_id, **_serialize_attachment(row), "media_id": media_id}
    except DownloadCanceled:
        row.status = "canceled"
        row.error = "用户已取消"
    except (client.PawchiveError, storage_guard.StorageNotMountedError, OSError, ValueError) as exc:
        failure = exc if isinstance(exc, client.PawchiveError) else None
        db.rollback()
        row = db.get(models.PawchiveAttachment, row_id)
        row.status = "failed"
        row.error = str(exc) if isinstance(exc, client.PawchiveError) else "下载或存储失败"
        logger.warning("Pawchive attachment %s failed: %s", row_id, type(exc).__name__)
    db.commit()
    result = {"attachment_id": row_id, **_serialize_attachment(row)}
    if failure:
        result["error_code"] = failure.code
        result["retry_after"] = failure.retry_after
    return result


def run_download_job(job_id: str) -> None:
    job = DOWNLOAD_JOBS.get(job_id)
    if not job:
        return
    stop = _CANCEL[job_id]
    db = database.SessionLocal()
    try:
        try:
            with __import__("app.services.media_operation_guard",fromlist=["project_mutation"]).project_mutation():
                root = download_root()
                job["status"] = "running"
                job["message"] = "下载中"
                job_lifecycle.record_job(JOB_KIND, job)
                for row_id in job["attachment_ids"]:
                    with _TRANSFER_LIMIT:
                        result = _download_one(row_id, job_id, stop, root, db)
                    job["attachments"].append(result)
                    job["completed"] = sum(a["status"] == "completed" for a in job["attachments"])
                    job["failed"] = sum(a["status"] == "failed" for a in job["attachments"])
                    job["canceled"] = sum(a["status"] == "canceled" for a in job["attachments"])
                    job_lifecycle.record_job(JOB_KIND, job)
                    if stop.is_set() or result.get("error_code") in {"RATE_LIMITED", "ACCESS_RESTRICTED"}:
                        if result.get("error_code") == "RATE_LIMITED":
                            job["message"] = "来源请求过快；已停止后续附件，请稍后重试"
                            job["retry_after"] = result.get("retry_after")
                        elif result.get("error_code") == "ACCESS_RESTRICTED":
                            job["message"] = "来源限制访问；已停止后续附件"
                        break
                for row_id in job["attachment_ids"][len(job["attachments"]):]:
                    row = db.get(models.PawchiveAttachment, row_id)
                    if row and row.job_id == job_id and row.status == "queued":
                        row.status = "canceled" if stop.is_set() else "interrupted"
                        row.error = "用户已取消" if stop.is_set() else "任务已中断"
                        job["attachments"].append({"attachment_id": row_id, **_serialize_attachment(row)})
                db.commit()
                job["canceled"] = sum(a["status"] == "canceled" for a in job["attachments"])
                job["status"] = "canceled" if stop.is_set() else "completed" if job["completed"] == job["total"] else "failed"
                if not job.get("retry_after") and not job["message"].startswith("来源"):
                    job["message"] = f"完成 {job['completed']} / 失败 {job['failed']} / 取消 {job['canceled']}"
        except Exception as exc:
            logger.exception("Pawchive job %s aborted: %s", job_id, type(exc).__name__)
            db.rollback()
            job["status"] = "failed"
            job["message"] = "下载任务失败"
            for row_id in job["attachment_ids"]:
                row = db.get(models.PawchiveAttachment, row_id)
                if row and row.job_id == job_id and row.status in {"queued", "downloading"}:
                    row.status = "interrupted"
                    row.error = "任务中断，可安全重试"
            db.commit()
        finally:
            job_lifecycle.record_job(JOB_KIND, job, finished=True)
    finally:
        db.close()
        _CANCEL.pop(job_id, None)


def cancel_download(job_id: str) -> dict:
    job = DOWNLOAD_JOBS.get(job_id)
    event = _CANCEL.get(job_id)
    if not job or not event or job["status"] not in {"queued", "running", "canceling"}:
        raise client.PawchiveError("INVALID_REQUEST", "任务已结束或不在当前进程", 409)
    event.set()
    job["status"] = "canceling"
    job["message"] = "正在取消"
    job_lifecycle.record_job(JOB_KIND, job)
    return job


def recover_interrupted_attachments() -> None:
    db = database.SessionLocal()
    try:
        rows = db.query(models.PawchiveAttachment).filter(models.PawchiveAttachment.status.in_(("queued", "downloading"))).all()
        for row in rows:
            row.status = "interrupted"
            row.error = "服务重启，可安全重试"
        if rows:
            db.commit()
    finally:
        db.close()
