from __future__ import annotations

from datetime import datetime
import traceback

from ... import database, models
from .locks import _release_source
from .policy import WNACG_DOWNLOAD_LIMIT, _next_run_after_status, _prune_auto_sync_logs


def _run_wnacg(source_id: int) -> None:
    """Sync WNACG favourites then download all new (un-downloaded) items."""
    db = database.SessionLocal()
    started_at = datetime.utcnow()
    synced_count = 0
    downloaded_count = 0
    failed_count = 0
    status = "success"
    message = ""

    try:
        source = (
            db.query(models.ExternalFavoriteSource)
            .filter(models.ExternalFavoriteSource.id == source_id)
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

        # --- Phase 1: sync favourites list ---
        from ... import external_sources
        from .. import external_runtime

        cookie = source.cookie
        base_url = external_runtime.get_url_base(source.favorites_url)
        first_html = external_sources.fetch_html(source.favorites_url, cookie, proxy=source.proxy)
        categories = external_sources.parse_wnacg_categories(first_html)

        existing_items = {
            item.external_id: item
            for item in db.query(models.ExternalFavoriteItem)
            .filter(models.ExternalFavoriteItem.source_id == source.id)
            .all()
        }
        existing_ids = set(existing_items.keys())
        page_limit = 30
        parsed_items = []

        if categories:
            for category in categories:
                for page in range(1, page_limit + 1):
                    page_url = external_sources.wnacg_category_url(
                        category.id, page, base_url=base_url
                    )
                    page_html = external_sources.fetch_html(page_url, cookie, proxy=source.proxy)
                    page_items = external_sources.parse_wnacg_favorites(
                        page_html,
                        base_url=base_url,
                        category_id=category.id,
                        category_name=category.name,
                    )
                    parsed_items.extend(page_items)
                    if any(
                        item.external_id in existing_ids
                        for item in page_items
                    ):
                        break
                    if not external_sources.html_has_next_page(page_html):
                        break
        else:
            parsed_items = external_sources.parse_wnacg_favorites(
                first_html, base_url=base_url
            )

        now = datetime.utcnow()
        for db_item in existing_items.values():
            db_item.sync_position = None

        deduped = {item.external_id: item for item in parsed_items}
        new_count = 0
        for sync_position, item in enumerate(deduped.values()):
            db_item = existing_items.get(item.external_id)
            if not db_item:
                db_item = models.ExternalFavoriteItem(
                    source=source,
                    source_type="wnacg",
                    external_id=item.external_id,
                    title=item.title,
                    url=item.url,
                    cover_url=item.cover_url,
                    category_id=item.category_id,
                    category_name=item.category_name,
                    sync_position=sync_position,
                    last_seen_at=now,
                )
                db.add(db_item)
                new_count += 1
            else:
                db_item.title = item.title
                db_item.url = item.url
                db_item.cover_url = item.cover_url or db_item.cover_url
                db_item.category_id = item.category_id
                db_item.category_name = item.category_name
                db_item.sync_position = sync_position
                db_item.last_seen_at = now

        source.status = "ok"
        source.last_synced_at = now
        source.last_error = None
        db.commit()
        synced_count = new_count

        # --- Phase 2: download un-downloaded items ---
        all_items = (
            db.query(models.ExternalFavoriteItem)
            .filter(models.ExternalFavoriteItem.source_id == source.id)
            .all()
        )
        all_items.sort(
            key=lambda item: (
                item.sync_position is None,
                item.sync_position if item.sync_position is not None else 0,
                item.id or 0,
            )
        )
        download_root = source.download_root_path
        to_download = []
        for fav_item in all_items:
            local_media = external_runtime.find_local_media_for_external_item(fav_item, db)
            if not local_media:
                to_download.append(fav_item)

        if to_download:
            remaining_count = max(0, len(to_download) - WNACG_DOWNLOAD_LIMIT)
            download_batch = to_download[:WNACG_DOWNLOAD_LIMIT]
            if remaining_count:
                message = (
                    f"同步完成（新增 {synced_count}），"
                    f"本轮下载 {len(download_batch)} 本，剩余 {remaining_count} 本待后续自动同步"
                )
            else:
                message = f"同步完成（新增 {synced_count}），开始下载 {len(download_batch)} 本"
            source.auto_sync_last_message = message
            db.commit()

            external_runtime.ensure_external_manga_library(source, download_root, db)

            for fav_item in download_batch:
                try:
                    plan = external_runtime.prepare_wnacg_download_plan(
                        fav_item, source, download_root
                    )
                    result = external_runtime.download_wnacg_item(
                        fav_item, source, plan, job=None
                    )
                    external_runtime.upsert_external_downloaded_media(
                        fav_item, source, result["path"], download_root, db
                    )
                    downloaded_count += 1
                except Exception as exc:
                    failed_count += 1
                    external_runtime.log_wnacg_download_failure(
                        download_root,
                        fav_item.title,
                        fav_item.url,
                        str(exc),
                    )

        if failed_count > 0:
            status = "partial"
            message = (
                f"同步新增 {synced_count}，"
                f"下载 {downloaded_count} 本，"
                f"失败 {failed_count} 本"
            )
        else:
            status = "success"
            message = (
                f"同步新增 {synced_count}，"
                f"下载 {downloaded_count} 本"
            )
        if len(to_download) > WNACG_DOWNLOAD_LIMIT:
            remaining_count = len(to_download) - WNACG_DOWNLOAD_LIMIT
            status = "partial" if status == "success" else status
            message += f"，剩余 {remaining_count} 本待后续自动同步"

    except Exception as exc:
        status = "failed"
        message = f"自动同步失败：{exc}"
        traceback.print_exc()
    finally:
        finished_at = datetime.utcnow()
        duration = int((finished_at - started_at).total_seconds())
        try:
            # Refresh source from DB (it may have been modified during long runs)
            source = (
                db.query(models.ExternalFavoriteSource)
                .filter(models.ExternalFavoriteSource.id == source_id)
                .first()
            )
            if source:
                source.auto_sync_last_status = status
                source.auto_sync_last_message = message
                source.auto_sync_last_run_at = started_at
                interval = source.auto_sync_interval_hours or 24
                source.auto_sync_next_run_at = _next_run_after_status(
                    db, "wnacg", source_id, status, finished_at, interval
                )
                db.commit()

            log = models.AutoSyncLog(
                source_type="wnacg",
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
            _release_source("wnacg", source_id)
            print(
                f"  [auto-sync] wnacg #{source_id} finished: "
                f"{status} — synced={synced_count} downloaded={downloaded_count} "
                f"failed={failed_count} ({duration}s)"
            )
