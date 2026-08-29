import os
from typing import Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ... import downloader_push, models, scanner
from ...database import get_db
from ...services.audio_tracks import AUDIO_TRACK_EXTS, scan_audio_tracks
from ...services.external import (
    HE_CALLBACK_TOKEN,
    HE_PUBLIC_URL,
    ensure_wnacg_source_marker,
    external_item_download_dir,
    upsert_external_downloaded_audio_media,
    upsert_external_downloaded_media,
)
from ...services.media_access import get_source_or_404

router = APIRouter()


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


def _push_external_items(payload, db: Session, build):
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
