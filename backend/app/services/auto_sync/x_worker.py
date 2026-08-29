from __future__ import annotations

from datetime import datetime
import time
import traceback
import uuid

from ... import database, models
from ..thumbnails import THUMBNAIL_DIR
from .locks import _release_source
from .policy import _next_run_after_status, _prune_auto_sync_logs


def _run_x(source_id: int) -> None:
    """Sync X likes via GraphQL then download all pending posts."""
    db = database.SessionLocal()
    started_at = datetime.utcnow()
    synced_count = 0
    downloaded_count = 0
    failed_count = 0
    status = "success"
    message = ""

    try:
        source = (
            db.query(models.XImportSource)
            .filter(models.XImportSource.id == source_id)
            .first()
        )
        if not source:
            status = "failed"
            message = "数据源不存在"
            return
        if not source.cookie:
            status = "failed"
            message = "Cookie 未配置，无法自动同步"
            return
        if not source.download_root_path:
            status = "failed"
            message = "下载路径未配置"
            return

        source.auto_sync_last_status = "running"
        source.auto_sync_last_message = "正在自动同步"
        source.auto_sync_last_run_at = started_at
        db.commit()

        from ...x_import import importer as x_importer, sync as x_sync

        # --- Phase 1: GraphQL sync ---
        # Check for existing running sync
        existing_sync = x_sync.latest_sync_for_source(source.id)
        if existing_sync and existing_sync.status in ("queued", "running"):
            status = "failed"
            message = "已有同步任务在进行，跳过本次自动同步"
            return

        sync_job = x_sync.start_sync(
            source_id=source.id, cookie=source.cookie
        )

        # Wait for sync to complete (poll every 2s, timeout 10min)
        timeout = 600
        elapsed = 0
        while sync_job.status in ("queued", "running") and elapsed < timeout:
            time.sleep(2)
            elapsed += 2

        if sync_job.status == "completed":
            synced_count = sync_job.new_posts
        elif sync_job.status == "failed":
            status = "failed"
            message = f"同步失败：{sync_job.message}"
            return
        else:
            status = "failed"
            message = f"同步超时（{timeout}s）"
            x_sync.request_cancel(sync_job.job_id)
            return

        # --- Phase 2: download pending posts ---
        existing_import = x_importer.latest_job_for_source(source.id)
        if existing_import and existing_import.status in (
            "queued",
            "preparing",
            "running",
            "paused",
        ):
            status = "partial"
            message = (
                f"同步新增 {synced_count} 条，"
                "但已有下载任务在进行，跳过下载"
            )
            return

        post_ids = x_importer.select_pending_post_ids(db, source.id)
        if not post_ids:
            status = "success"
            message = f"同步新增 {synced_count} 条，无需下载"
            return

        job_id = str(uuid.uuid4())
        import_job = x_importer.start_job(
            job_id=job_id,
            source_id=source.id,
            download_root=source.download_root_path,
            thumbnail_dir=THUMBNAIL_DIR,
            post_ids=post_ids,
            cookie=source.cookie,
        )

        # Wait for import to complete (poll every 5s, timeout 4h for large backlogs)
        timeout = 14400
        elapsed = 0
        while import_job.status in (
            "queued",
            "preparing",
            "running",
        ) and elapsed < timeout:
            time.sleep(5)
            elapsed += 5

        if import_job.status in ("completed", "canceled"):
            downloaded_count = import_job.completed_posts
            failed_count = import_job.failed_posts
            if failed_count > 0:
                status = "partial"
                message = (
                    f"同步新增 {synced_count}，"
                    f"下载 {downloaded_count} 个，"
                    f"失败 {failed_count} 个"
                )
            else:
                status = "success"
                message = (
                    f"同步新增 {synced_count}，"
                    f"下载 {downloaded_count} 个"
                )
        elif import_job.status == "failed":
            status = "failed"
            downloaded_count = import_job.completed_posts
            failed_count = import_job.failed_posts
            message = f"下载失败：{import_job.message}"
        else:
            status = "partial"
            downloaded_count = import_job.completed_posts
            failed_count = import_job.failed_posts
            message = f"下载超时（{timeout}s），已完成 {downloaded_count} 个"
            x_importer.request_cancel(job_id)

    except Exception as exc:
        status = "failed"
        message = f"自动同步失败：{exc}"
        traceback.print_exc()
    finally:
        finished_at = datetime.utcnow()
        duration = int((finished_at - started_at).total_seconds())
        try:
            source = (
                db.query(models.XImportSource)
                .filter(models.XImportSource.id == source_id)
                .first()
            )
            if source:
                source.auto_sync_last_status = status
                source.auto_sync_last_message = message
                source.auto_sync_last_run_at = started_at
                interval = source.auto_sync_interval_hours or 24
                source.auto_sync_next_run_at = _next_run_after_status(
                    db, "x", source_id, status, finished_at, interval
                )
                source.last_sync_at = datetime.utcnow()
                db.commit()

            log = models.AutoSyncLog(
                source_type="x",
                source_id=source_id,
                action="sync+download",
                status=status,
                synced_count=synced_count,
                downloaded_count=downloaded_count,
                failed_count=failed_count,
                message=message,
                started_at=started_at,
                finished_at=finished_at,
                duration_seconds=duration,
            )
            db.add(log)
            _prune_auto_sync_logs(db)
            db.commit()
        except Exception:
            traceback.print_exc()
        finally:
            db.close()
            _release_source("x", source_id)
            print(
                f"  [auto-sync] x #{source_id} finished: "
                f"{status} — synced={synced_count} downloaded={downloaded_count} "
                f"failed={failed_count} ({duration}s)"
            )
