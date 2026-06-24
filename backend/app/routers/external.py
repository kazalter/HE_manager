from datetime import datetime
import os
import uuid
from typing import List, Optional
from urllib.parse import urlencode

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from .. import asmr_source, downloader_push, external_sources, models, schemas, scanner
from ..database import get_db
from ..services.audio_tracks import AUDIO_TRACK_EXTS, scan_audio_tracks
from ..services.external_runtime import (
    DOWNLOAD_JOBS,
    HE_CALLBACK_TOKEN,
    HE_PUBLIC_URL,
    get_external_storage_dirs,
    ensure_external_cover_cache,
    ensure_wnacg_source_marker,
    external_cover_sidecar_rel_path,
    external_item_download_dir,
    get_url_base,
    normalize_download_root,
    prepare_asmr_download_plan_for_item,
    prepare_wnacg_download_plan,
    run_asmr_download_job,
    run_wnacg_download_job,
    serialize_external_favorite_item,
    upsert_external_downloaded_audio_media,
    upsert_external_downloaded_media,
)
from ..services.media_access import get_source_or_404
from ..services.thumbnails import THUMBNAIL_DIR

router = APIRouter()


@router.get("/external/sources", response_model=List[schemas.ExternalFavoriteSource])
def list_external_sources(db: Session = Depends(get_db)):
    return db.query(models.ExternalFavoriteSource).order_by(models.ExternalFavoriteSource.id.desc()).all()


@router.patch("/external/sources/{source_id}", response_model=schemas.ExternalFavoriteSource)
def update_external_source(source_id: int, payload: schemas.ExternalFavoriteSourceUpdate, db: Session = Depends(get_db)):
    source = get_source_or_404(source_id, db)
    data = payload.dict(exclude_unset=True)
    if "name" in data and data["name"]:
        source.name = data["name"]
    if "favorites_url" in data and data["favorites_url"]:
        source.favorites_url = data["favorites_url"]
    if "download_root_path" in data:
        source.download_root_path = (data["download_root_path"] or "").strip() or None
        # download_root_path setup is wnacg-shaped (creates a manga dir).
        # Skip the side-effect for asmr sources — their root layout is handled
        # by get_asmr_storage_dirs() at download time.
        if (source.source_type or "wnacg") != "asmr":
            get_external_storage_dirs(source)
    # ASMR knobs: "all"/"no_wav"/"mp3_only" + "all"/"no_se"/"se_only". Empty
    # string falls back to "all" so the front-end can clear without nulling.
    if "audio_format_filter" in data:
        source.audio_format_filter = (data["audio_format_filter"] or "").strip() or "all"
    if "audio_version_filter" in data:
        source.audio_version_filter = (data["audio_version_filter"] or "").strip() or "all"
    if "playlist_url" in data:
        # null / empty string both mean "no playlist, use marked works"
        source.playlist_url = (data["playlist_url"] or "").strip() or None
    if "api_mirrors" in data:
        source.api_mirrors = (data["api_mirrors"] or "").strip() or None
    if "proxy" in data:
        source.proxy = (data["proxy"] or "").strip() or None
    db.commit()
    db.refresh(source)
    return source


@router.get("/external/favorites", response_model=List[schemas.ExternalFavoriteItem])
def list_external_favorites(
    source_type: Optional[str] = None,
    source_id: Optional[int] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
):
    query = db.query(models.ExternalFavoriteItem)
    if source_type:
        query = query.filter(models.ExternalFavoriteItem.source_type == source_type)
    if source_id:
        query = query.filter(models.ExternalFavoriteItem.source_id == source_id)
    if search:
        query = query.filter(models.ExternalFavoriteItem.title.ilike(f"%{search}%"))
    favorite_items = query.order_by(
        models.ExternalFavoriteItem.sync_position.is_(None),
        models.ExternalFavoriteItem.sync_position.asc(),
        models.ExternalFavoriteItem.id.desc(),
    ).all()
    return [serialize_external_favorite_item(item, db) for item in favorite_items]


@router.post("/external/wnacg/sync", response_model=schemas.ExternalFavoriteSyncResponse)
def sync_wnacg_favorites(payload: schemas.ExternalFavoriteSyncRequest, db: Session = Depends(get_db)):
    if payload.source_id:
        source = get_source_or_404(payload.source_id, db)
        source.name = payload.name or source.name
        source.favorites_url = payload.favorites_url or source.favorites_url
        if payload.download_root_path is not None:
            source.download_root_path = payload.download_root_path.strip() or None
        if payload.cookie is not None:
            source.cookie = payload.cookie.strip()
    else:
        source = (
            db.query(models.ExternalFavoriteSource)
            .filter(
                models.ExternalFavoriteSource.source_type == "wnacg",
                models.ExternalFavoriteSource.favorites_url == payload.favorites_url,
            )
            .first()
        )
        if not source:
            source = models.ExternalFavoriteSource(
                source_type="wnacg",
                name=payload.name,
                favorites_url=payload.favorites_url,
                cookie=(payload.cookie or "").strip() or None,
                download_root_path=(payload.download_root_path or "").strip() or None,
            )
            db.add(source)
            db.flush()
        else:
            source.name = payload.name or source.name
            if payload.download_root_path is not None:
                source.download_root_path = payload.download_root_path.strip() or None
            if payload.cookie is not None:
                source.cookie = payload.cookie.strip() or None

    cookie = source.cookie or ""
    if not cookie:
        raise HTTPException(status_code=400, detail="请填写你自己账号的 Cookie 后再同步收藏页")

    source.status = "syncing"
    source.last_error = None
    db.commit()

    try:
        existing_items = {
            item.external_id: item
            for item in db.query(models.ExternalFavoriteItem).filter(models.ExternalFavoriteItem.source_id == source.id).all()
        }
        existing_external_ids = set(existing_items.keys())
        base_url = get_url_base(source.favorites_url)
        first_html = external_sources.fetch_html(source.favorites_url, cookie, proxy=source.proxy)
        categories = external_sources.parse_wnacg_categories(first_html)
        parsed_items: List[external_sources.ParsedExternalFavorite] = []

        if payload.category_id:
            categories = [category for category in categories if category.id == payload.category_id]
            if not categories:
                categories = [external_sources.WnacgCategory(id=payload.category_id, name=f"分类 {payload.category_id}")]

        if categories:
            for category in categories:
                for page in range(1, payload.page_limit + 1):
                    page_url = external_sources.wnacg_category_url(category.id, page, base_url=base_url)
                    page_html = external_sources.fetch_html(page_url, cookie, proxy=source.proxy)
                    page_items = external_sources.parse_wnacg_favorites(
                        page_html,
                        base_url=base_url,
                        category_id=category.id,
                        category_name=category.name,
                    )
                    parsed_items.extend(page_items)
                    if any(item.external_id in existing_external_ids for item in page_items):
                        break
                    if not external_sources.html_has_next_page(page_html):
                        break
        else:
            parsed_items = external_sources.parse_wnacg_favorites(first_html, base_url=base_url)

        now = datetime.utcnow()
        for db_item in existing_items.values():
            db_item.sync_position = None

        deduped = {item.external_id: item for item in parsed_items}
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
        db.refresh(source)

        items = (
            db.query(models.ExternalFavoriteItem)
            .filter(models.ExternalFavoriteItem.source_id == source.id)
            .order_by(
                models.ExternalFavoriteItem.sync_position.is_(None),
                models.ExternalFavoriteItem.sync_position.asc(),
                models.ExternalFavoriteItem.id.desc(),
            )
            .all()
        )
        return {"source": source, "synced_count": len(deduped), "items": [serialize_external_favorite_item(item, db) for item in items]}
    except HTTPException:
        source.status = "error"
        source.last_error = "同步失败"
        db.commit()
        raise
    except Exception as exc:
        source.status = "error"
        source.last_error = str(exc)
        db.commit()
        raise HTTPException(status_code=502, detail=f"同步 WNACG 收藏失败：{exc}")


@router.get("/external/favorites/{favorite_id}/cover")
def get_external_favorite_cover(favorite_id: int, db: Session = Depends(get_db)):
    item = db.query(models.ExternalFavoriteItem).filter(models.ExternalFavoriteItem.id == favorite_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="External favorite not found")
    if not item.cover_url:
        raise HTTPException(status_code=404, detail="Cover not found")

    source = get_source_or_404(item.source_id, db)
    try:
        cached_cover = ensure_external_cover_cache(item, source)
        if cached_cover and os.path.exists(cached_cover):
            return FileResponse(cached_cover)
        raise RuntimeError("封面缓存失败")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"读取外部封面失败：{exc}")


@router.post("/external/wnacg/downloads", response_model=schemas.ExternalDownloadJob)
def create_wnacg_download_job(
    payload: schemas.ExternalDownloadRequest,
    background_tasks: BackgroundTasks,
):
    download_root_path = payload.download_root_path.strip()
    if not download_root_path:
        raise HTTPException(status_code=400, detail="请先设置下载位置")

    job_id = str(uuid.uuid4())
    DOWNLOAD_JOBS[job_id] = {
        "job_id": job_id,
        "status": "running",
        "total": len(payload.item_ids),
        "completed": 0,
        "failed": 0,
        "message": "准备下载",
        "pages_total": 0,
        "pages_done": 0,
        "bytes_total": 0,
        "downloaded_bytes": 0,
        "bytes_total_known": False,
        "unknown_size_files": 0,
        "cancel_requested": False,
        "current_book_title": "",
        "current_book_total_pages": 0,
        "current_book_downloaded_pages": 0,
        "tasks": [
            {
                "id": str(item_id),
                "item_id": item_id,
                "title": "",
                "status": "pending",
                "total_pages": 0,
                "downloaded_pages": 0,
                "error": None,
            }
            for item_id in payload.item_ids
        ],
        "results": [],
    }
    background_tasks.add_task(run_wnacg_download_job, job_id, payload.item_ids, download_root_path)
    return DOWNLOAD_JOBS[job_id]


@router.post("/external/downloads/{job_id}/cancel", response_model=schemas.ExternalDownloadJob)
def cancel_external_download_job(job_id: str):
    job = DOWNLOAD_JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Download job not found")

    if job["status"] in {"completed", "failed", "canceled"}:
        return job

    job["cancel_requested"] = True
    job["status"] = "canceling"
    job["message"] = "正在取消下载"
    return job


@router.get("/external/downloads/{job_id}", response_model=schemas.ExternalDownloadJob)
def get_external_download_job(job_id: str):
    job = DOWNLOAD_JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Download job not found")
    return job


# ============================================================================
# ASMR.one — mirror probe, favorites sync, downloads
# ============================================================================
# Frontend: AsmrPanel.vue. The three endpoints here form one user flow:
#   1. /external/asmr/mirrors/ping  — find a reachable mirror
#   2. /external/asmr/sync          — login + pull marked/playlist works into
#                                     the ExternalFavoriteItem table
#   3. /external/asmr/downloads     — fetch selected works to disk and
#                                     register them as audio Media rows
# Mirror probe is pure network (no DB writes); sync + downloads persist via
# ExternalFavoriteSource rows with source_type='asmr', where source.cookie
# holds the bearer token (raw password is never stored).

@router.post("/external/asmr/mirrors/ping")
def asmr_ping_mirrors(payload: dict = None):
    payload = payload or {}
    api_base = (payload.get("api_base") or "").strip()
    raw_mirrors = payload.get("api_mirrors") or ""
    bases = asmr_source.candidate_bases(
        preferred=api_base if api_base else None,
        mirrors=asmr_source.parse_mirrors(raw_mirrors) if raw_mirrors else None,
    )
    # Dedupe while keeping the preferred-first order (candidate_bases already
    # does this, but be defensive against future changes).
    seen = set()
    ordered = []
    for b in bases:
        if b not in seen:
            seen.add(b)
            ordered.append(b)
    return {"results": [asmr_source.ping_mirror(b) for b in ordered]}


@router.post("/external/asmr/recheck-covers")
def asmr_recheck_covers(db: Session = Depends(get_db)):
    """Backfill cover thumbnails for audio Media rows downloaded before the
    cover step existed in the pipeline.

    For each audio work folder without a cover_path:
      1. Look for an existing sidecar image (cover.jpg, etc.) — covers some
         users will have copied in manually.
      2. Fall back to the ExternalFavoriteItem.cover_url (paired by source_url),
         download it next to the audio, then run the same scanner helpers as
         the download pipeline does.

    Idempotent: rows that already have cover_path are skipped. Returns counts
    so the UI can show a "fixed N / M" toast."""
    rows = db.query(models.Media).filter(
        models.Media.media_type == "audio",
        models.Media.cover_path.is_(None),
    ).all()

    checked = 0
    fixed = 0
    fetched_remote = 0
    failed = 0

    for media in rows:
        if not media.absolute_path or not os.path.isdir(media.absolute_path):
            continue
        checked += 1
        item_dir = media.absolute_path

        cover_src = scanner.get_work_cover_path(item_dir)

        if not cover_src and media.source_url:
            # Reverse-link to the ExternalFavoriteItem so we know the remote
            # cover URL. ASMR items are matched by their work page URL.
            item = (
                db.query(models.ExternalFavoriteItem)
                .filter(
                    models.ExternalFavoriteItem.url == media.source_url,
                    models.ExternalFavoriteItem.source_type == "asmr",
                )
                .first()
            )
            cover_url = (item.cover_url or "").strip() if item else ""
            if cover_url:
                try:
                    content, content_type = asmr_source.fetch_file(cover_url)
                    ext = get_cover_extension(content_type, cover_url)
                    cover_dst = os.path.join(item_dir, f"cover{ext}")
                    with open(cover_dst, "wb") as cover_file:
                        cover_file.write(content)
                    cover_src = cover_dst
                    fetched_remote += 1
                except Exception as exc:  # noqa: BLE001
                    print(f"  ! recheck-covers: remote fetch failed for {media.title!r}: {exc}")
                    failed += 1
                    continue

        if not cover_src:
            continue

        digest = hashlib.md5(item_dir.encode("utf-8")).hexdigest()[:12]
        thumb_name = f"thumb_audio_{digest}_{int(datetime.now().timestamp())}.jpg"
        thumb_path = os.path.join(THUMBNAIL_DIR, thumb_name)
        if scanner.make_work_thumbnail(cover_src, thumb_path):
            media.cover_path = thumb_name
            fixed += 1
        else:
            failed += 1

    db.commit()
    return {
        "checked": checked,
        "fixed": fixed,
        "fetched_remote": fetched_remote,
        "failed": failed,
    }


@router.post("/external/asmr/sync", response_model=schemas.ExternalFavoriteSyncResponse)
def sync_asmr_favorites(payload: schemas.AsmrSyncRequest, db: Session = Depends(get_db)):
    # Mirrors WNACG's /external/wnacg/sync but with asmr.one specifics. The
    # source row is reused (source_type='asmr'); favorites_url=api_base and
    # cookie=bearer_token. We don't store the raw password — only exchange it
    # once for a token via asmr_source.login() and persist that.
    if payload.source_id:
        source = get_source_or_404(payload.source_id, db)
    else:
        # Match an existing asmr source on (source_type, api_base) to avoid
        # creating dupes when the user re-syncs with the same base.
        source = (
            db.query(models.ExternalFavoriteSource)
            .filter(
                models.ExternalFavoriteSource.source_type == "asmr",
                models.ExternalFavoriteSource.favorites_url == payload.api_base,
            )
            .first()
        )
        if not source:
            source = models.ExternalFavoriteSource(
                source_type="asmr",
                name=payload.name or "ASMR",
                favorites_url=payload.api_base,
            )
            db.add(source)
            db.flush()

    # Apply incoming config (everything except creds, which are handled below)
    source.name = payload.name or source.name
    source.favorites_url = payload.api_base or source.favorites_url
    source.api_mirrors = payload.api_mirrors if payload.api_mirrors is not None else source.api_mirrors
    source.audio_format_filter = payload.audio_format_filter or source.audio_format_filter or "all"
    source.audio_version_filter = payload.audio_version_filter or source.audio_version_filter or "all"
    source.playlist_url = payload.playlist_url if payload.playlist_url is not None else source.playlist_url
    if payload.download_root_path is not None:
        source.download_root_path = payload.download_root_path.strip() or None
    if payload.username:
        source.username = payload.username

    # Resolve token: if creds came in this request, login fresh (overwriting any
    # stale token). Otherwise reuse what's already stored.
    api_base = asmr_source.normalize_api_base(source.favorites_url)
    mirrors = asmr_source.parse_mirrors(source.api_mirrors) if source.api_mirrors else None
    token = source.cookie or ""

    if payload.password:
        # Need both for a fresh login. payload.username falls back to stored.
        login_name = (payload.username or source.username or "").strip()
        if not login_name:
            raise HTTPException(status_code=400, detail="登录需要用户名")
        try:
            # NB: login() returns (token, working_base) — token FIRST. An
            # earlier version of this call swapped the tuple, which silently
            # wrote the base URL into source.cookie (used as the bearer) and
            # the JWT into source.favorites_url. The result was every
            # subsequent /api/marks call sending `Authorization: Bearer
            # https://api.asmr-200.com`, getting back 401 + "invalid token",
            # and looping forever because the 401-handler kept clearing the
            # cookie and forcing a fresh — but still mis-stored — login.
            token, working_base = asmr_source.login(
                preferred_base=api_base,
                name=login_name,
                password=payload.password,
                mirrors=mirrors,
            )
        except asmr_source.AsmrApiError as exc:
            source.status = "error"
            source.last_error = f"登录失败：{exc}"
            db.commit()
            raise HTTPException(status_code=401, detail=f"asmr.one 登录失败：{exc}")
        # login() may have switched to a working mirror — persist the new base
        # so subsequent syncs start there.
        source.favorites_url = working_base
        source.cookie = token
        source.username = login_name
    elif not token:
        raise HTTPException(
            status_code=400,
            detail="尚未登录 asmr.one：请填写账号密码后再同步（密码只用于换取 token，不会存储）",
        )

    source.status = "syncing"
    source.last_error = None
    db.commit()

    try:
        # Choose source: explicit playlist URL takes precedence; otherwise pull
        # the user's "marked" works.
        if source.playlist_url:
            playlist_id = asmr_source.extract_playlist_id(source.playlist_url)
            parsed_works = asmr_source.fetch_playlist_works(
                preferred_base=source.favorites_url,
                token=token,
                playlist_id=playlist_id,
                page_limit=payload.page_limit,
                mirrors=mirrors,
            )
        else:
            parsed_works = asmr_source.fetch_marked_works(
                working_base=source.favorites_url,
                token=token,
                page_limit=payload.page_limit,
                mirrors=mirrors,
            )

        now = datetime.utcnow()
        existing_items = {
            item.external_id: item
            for item in db.query(models.ExternalFavoriteItem)
            .filter(models.ExternalFavoriteItem.source_id == source.id)
            .all()
        }
        # Mirror wnacg: blank all sync_positions first, then re-assign in the
        # order the API returned (newest-first marked or playlist sequence).
        # Items that fall out of the page window keep their row but lose
        # sync_position, so the UI's "currently in source" ordering reflects
        # only what we just saw.
        for db_item in existing_items.values():
            db_item.sync_position = None

        # ParsedAsmrWork attribute names (see asmr_source.py): external_id,
        # title, url, cover_url, category_name. The first cut of this code
        # used `rj_code` / `work_url` / `circle` everywhere — names that don't
        # exist on the dataclass — so the very first sync after login worked
        # blew up with AttributeError. Keeping the canonical names below.
        deduped = {w.external_id: w for w in parsed_works if w.external_id}
        for sync_position, work in enumerate(deduped.values()):
            db_item = existing_items.get(work.external_id)
            if not db_item:
                db_item = models.ExternalFavoriteItem(
                    source=source,
                    source_type="asmr",
                    external_id=work.external_id,
                    title=work.title or work.external_id,
                    url=work.url or "",
                    cover_url=work.cover_url,
                    # Reuse category_name for the circle (visible chip in UI);
                    # category_id stays NULL since asmr has no category system.
                    category_name=work.category_name or None,
                    sync_position=sync_position,
                    last_seen_at=now,
                )
                db.add(db_item)
            else:
                db_item.title = work.title or db_item.title
                db_item.url = work.url or db_item.url
                db_item.cover_url = work.cover_url or db_item.cover_url
                db_item.category_name = work.category_name or db_item.category_name
                db_item.sync_position = sync_position
                db_item.last_seen_at = now

        source.status = "ok"
        source.last_synced_at = now
        source.last_error = None
        db.commit()
        db.refresh(source)

        items = (
            db.query(models.ExternalFavoriteItem)
            .filter(models.ExternalFavoriteItem.source_id == source.id)
            .order_by(
                models.ExternalFavoriteItem.sync_position.is_(None),
                models.ExternalFavoriteItem.sync_position.asc(),
                models.ExternalFavoriteItem.id.desc(),
            )
            .all()
        )
        return {
            "source": source,
            "synced_count": len(deduped),
            "items": [serialize_external_favorite_item(item, db) for item in items],
        }
    except HTTPException:
        source.status = "error"
        source.last_error = "同步失败"
        db.commit()
        raise
    except asmr_source.AsmrApiError as exc:
        source.status = "error"
        source.last_error = f"API 错误：{exc}"
        # An expired/revoked bearer manifests as 401 + api_code='invalid token'.
        # Drop the stale token so the next sync attempt forces a fresh login
        # path instead of looping on the bad credential. The user has to enter
        # their password again — we don't store it, so this is the right cycle.
        if exc.status == 401:
            source.cookie = None
        db.commit()
        # 401 is auth, surface as 401 so the front-end can render it distinctly
        # from generic 502 network/parse errors.
        http_status = 401 if exc.status == 401 else 502
        raise HTTPException(status_code=http_status, detail=f"同步 ASMR 收藏失败：{exc}")
    except Exception as exc:
        source.status = "error"
        source.last_error = str(exc)
        db.commit()
        raise HTTPException(status_code=502, detail=f"同步 ASMR 收藏失败：{exc}")


@router.post("/external/asmr/downloads", response_model=schemas.ExternalDownloadJob)
def create_asmr_download_job(
    payload: schemas.ExternalDownloadRequest,
    background_tasks: BackgroundTasks,
):
    """ASMR sibling of /external/wnacg/downloads. Same request shape (item_ids
    + download_root_path), same shared job dict (DOWNLOAD_JOBS), so the poll
    + cancel endpoints (/external/downloads/{id}, .../cancel) work unchanged.
    Format / SE-version filters are read off the source row that sync stored,
    not from this payload — keeping the front-end's startDownload signature
    aligned with WNACG."""
    download_root_path = payload.download_root_path.strip()
    if not download_root_path:
        raise HTTPException(status_code=400, detail="请先设置下载位置")

    job_id = str(uuid.uuid4())
    DOWNLOAD_JOBS[job_id] = {
        "job_id": job_id,
        "status": "running",
        "total": len(payload.item_ids),
        "completed": 0,
        "failed": 0,
        "message": "准备下载",
        "pages_total": 0,
        "pages_done": 0,
        "bytes_total": 0,
        "downloaded_bytes": 0,
        "bytes_total_known": False,
        "unknown_size_files": 0,
        "cancel_requested": False,
        "current_book_title": "",
        "current_book_total_pages": 0,
        "current_book_downloaded_pages": 0,
        "tasks": [
            {
                "id": str(item_id),
                "item_id": item_id,
                "title": "",
                "status": "pending",
                "total_pages": 0,
                "downloaded_pages": 0,
                "error": None,
            }
            for item_id in payload.item_ids
        ],
        "results": [],
    }
    background_tasks.add_task(run_asmr_download_job, job_id, payload.item_ids, download_root_path)
    return DOWNLOAD_JOBS[job_id]


# ============================================================================
# 推给独立下载中心（HE_downloader gateway）—— 方向 B，与上面的内置下载并存
# ============================================================================
# HE 仍负责解析（cookie / 签名 URL 在这边），把文件清单作为一个分组任务 POST
# 给网关 /jobs/batch；文件落到库目录（dest_dir 走 /mnt/hdd/...），由下载中心的
# aria2 下载、续传、统一面板展示。下载中心完成后回调 HE，再复用内置下载的 upsert 入库逻辑。

def _external_downloader_callback_url(item_id: int, source_type: str) -> Optional[str]:
    if not HE_PUBLIC_URL or not HE_CALLBACK_TOKEN:
        return None
    query = urlencode({
        "item_id": item_id,
        "source_type": source_type or "wnacg",
        "token": HE_CALLBACK_TOKEN,
    })
    return f"{HE_PUBLIC_URL}/external/downloader/callback?{query}"


def _download_root_from_item_dir(item_dir: str, source: models.ExternalFavoriteSource) -> Optional[str]:
    if not item_dir:
        return source.download_root_path
    expected_bucket = "audio" if (source.source_type or "") == "asmr" else "manga"
    parent = os.path.dirname(os.path.abspath(item_dir))
    if os.path.basename(parent).lower() == expected_bucket:
        return os.path.dirname(parent)
    return source.download_root_path

def _push_external_items(payload, db, build):
    """把选中收藏逐条解析成 (item_dir, files) 并 push_batch。build(item, source, root)
    返回 (item_dir, [{url, rel_path, headers}])。"""
    if not downloader_push.is_configured():
        raise HTTPException(status_code=503, detail="未配置下载中心地址（HE_DOWNLOADER_URL）")
    root_override = (payload.download_root_path or "").strip()
    results = []
    for item_id in payload.item_ids:
        item = db.query(models.ExternalFavoriteItem).filter(models.ExternalFavoriteItem.id == item_id).first()
        if not item:
            results.append({"item_id": item_id, "status": "failed", "error": "条目不存在"})
            continue
        source = get_source_or_404(item.source_id, db)
        root = root_override or source.download_root_path
        if not root:
            results.append({"item_id": item_id, "title": item.title, "status": "failed", "error": "未设置下载位置"})
            continue
        try:
            item_dir, files = build(item, source, root)
            if not files:
                raise RuntimeError("没有可下载的文件")
            callback_url = _external_downloader_callback_url(item.id, source.source_type or "wnacg")
            job = downloader_push.push_batch(
                name=item.title,
                dest_dir=item_dir,
                files=files,
                callback_url=callback_url,
            )
            results.append({"item_id": item_id, "title": item.title, "status": "pushed",
                            "job_id": job.get("id"), "files": len(files), "dest_dir": item_dir})
        except Exception as exc:  # noqa: BLE001
            results.append({"item_id": item_id, "title": item.title, "status": "failed", "error": str(exc)})
    pushed = [r for r in results if r.get("status") == "pushed"]
    if not pushed and results:
        raise HTTPException(status_code=502, detail=results[0].get("error") or "推送失败")
    return {"pushed": len(pushed), "results": results}


@router.post("/external/downloader/callback")
def downloader_callback(
    payload: dict,
    item_id: int,
    source_type: str = "wnacg",
    token: Optional[str] = None,
    db: Session = Depends(get_db)
):
    if HE_CALLBACK_TOKEN and token != HE_CALLBACK_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized callback token")

    event = (payload or {}).get("event")
    if event != "complete":
        return {"ok": True, "skipped": event}

    item = db.query(models.ExternalFavoriteItem).filter(models.ExternalFavoriteItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="条目不存在")

    source = get_source_or_404(item.source_id, db)
    job = (payload or {}).get("job") or {}
    item_dir = job.get("dir") or external_item_download_dir(item, source)
    download_root_path = _download_root_from_item_dir(item_dir, source)
    if not download_root_path:
        raise HTTPException(status_code=400, detail="未设置下载位置")

    # Path traversal validation: ensure item_dir is within download_root_path
    real_root = os.path.realpath(download_root_path).lower()
    real_dir = os.path.realpath(item_dir).lower()
    if not (real_dir.startswith(real_root + os.sep) or real_dir == real_root):
        raise HTTPException(status_code=400, detail="非法下载路径 (Path Traversal Detected)")

    if (source.source_type or source_type or "") == "asmr":
        files = job.get("files") or []
        track_count = sum(
            1
            for file_info in files
            if os.path.splitext((file_info or {}).get("rel_path") or (file_info or {}).get("name") or "")[1].lower()
            in AUDIO_TRACK_EXTS
        )
        if track_count <= 0:
            track_count = len(scan_audio_tracks(item_dir)) if os.path.isdir(item_dir) else len(files)
        total_bytes = int(job.get("total_bytes") or job.get("completed_bytes") or 0)
        if total_bytes <= 0 and os.path.isdir(item_dir):
            total_bytes = scanner.directory_size(item_dir)
        local_media = upsert_external_downloaded_audio_media(
            item,
            source,
            item_dir,
            download_root_path,
            db,
            track_count=track_count,
            total_bytes=total_bytes,
        )
    else:
        ensure_wnacg_source_marker(item, item_dir)
        local_media = upsert_external_downloaded_media(item, source, item_dir, download_root_path, db)

    db.commit()
    return {"ok": True, "item_id": item_id, "local_media_id": local_media.id}


@router.post("/external/asmr/push")
def push_asmr_to_downloader(payload: schemas.ExternalDownloadRequest, db: Session = Depends(get_db)):
    """把选中的 ASMR 收藏推给下载中心。ASMR 是签名 CDN 直链，aria2 直接可下。"""
    def build(item, source, root):
        if (source.source_type or "") != "asmr":
            raise RuntimeError("不是 ASMR 条目")
        plan = prepare_asmr_download_plan_for_item(item, source, root)
        item_dir = plan["item_dir"]
        files = []
        for f in plan["files"]:
            rel = os.path.relpath(f["local_path"], item_dir).replace(os.sep, "/")
            files.append({
                "url": f["url"],
                "rel_path": rel,
                "headers": {
                    "User-Agent": "HE-Manager/1.0 local ASMR sync",
                    "Referer": asmr_source.WEB_WORK_BASE + "/",
                },
            })
        cover_rel = external_cover_sidecar_rel_path(item)
        if cover_rel:
            files.append({
                "url": item.cover_url,
                "rel_path": cover_rel,
                "optional": True,
                "headers": {
                    "User-Agent": "HE-Manager/1.0 local ASMR sync",
                    "Referer": asmr_source.WEB_WORK_BASE + "/",
                },
            })
        return item_dir, files

    return _push_external_items(payload, db, build)


@router.post("/external/wnacg/push")
def push_wnacg_to_downloader(payload: schemas.ExternalDownloadRequest, db: Session = Depends(get_db)):
    """把选中的 wnacg 收藏推给下载中心。⚠️ wnacg 在 Cloudflare 后、图片可能要浏览器
    TLS 指纹，aria2 或被 403；走不通就继续用内置 /external/wnacg/downloads。"""
    def build(item, source, root):
        if (source.source_type or "wnacg") != "wnacg":
            raise RuntimeError("不是 wnacg 条目")
        plan = prepare_wnacg_download_plan(item, source, root)
        item_dir = plan["item_dir"]
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": item.url or source.favorites_url or "",
        }
        if source.cookie:
            headers["Cookie"] = source.cookie
        files = [
            {"url": url, "rel_path": f"{idx:03d}{downloader_push.url_ext(url)}", "headers": headers}
            for idx, url in enumerate(plan["image_urls"], start=1)
        ]
        cover_rel = external_cover_sidecar_rel_path(item)
        if cover_rel:
            cover_headers = dict(headers)
            cover_headers["Referer"] = source.favorites_url or item.url or ""
            files.append({"url": item.cover_url, "rel_path": cover_rel, "headers": cover_headers, "optional": True})
        return item_dir, files

    return _push_external_items(payload, db, build)
