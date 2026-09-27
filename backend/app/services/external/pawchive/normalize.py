"""Convert public Pawchive posts into stable, ordered HE Manager media."""
from __future__ import annotations

import hashlib
import re
from typing import Any

from . import refs

FILE_PATH = re.compile(r"^/[0-9a-f]{2}/[0-9a-f]{2}/[0-9a-f]{64}\.[a-z0-9]{2,5}$")
IMAGE_MIME = {
    "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
    "gif": "image/gif", "webp": "image/webp", "avif": "image/avif",
}
VIDEO_MIME = {"mp4": "video/mp4", "webm": "video/webm"}


def file_type(path: str) -> tuple[str, str] | None:
    if not FILE_PATH.fullmatch(path):
        return None
    extension = path.rsplit(".", 1)[-1]
    if extension in IMAGE_MIME:
        return "image", IMAGE_MIME[extension]
    if extension in VIDEO_MIME:
        return "video", VIDEO_MIME[extension]
    return None


def normalize_post(raw: dict[str, Any], *, creator_name: str | None = None, detail: bool = False) -> dict:
    service = str(raw.get("service") or "")
    creator_id = str(raw.get("user") or "")
    post_id = str(raw.get("id") or "")
    key = f"pawchive:{service}:{creator_id}:{post_id}"
    source_url = f"https://pawchive.pw/{service}/user/{creator_id}/post/{post_id}"
    source_files = [raw.get("file")]
    source_files.extend(raw.get("attachments") or [])
    attachments = []
    seen_paths = set()
    for index, source in enumerate(source_files):
        if not isinstance(source, dict):
            continue
        path = str(source.get("path") or "")
        if not path or path in seen_paths:
            continue
        seen_paths.add(path)
        media = file_type(path)
        attachment_key = hashlib.sha256(path.encode("utf-8")).hexdigest()[:24]
        attachments.append({
            "attachment_key": attachment_key,
            "original_index": index,
            "filename": str(source.get("name") or path.rsplit("/", 1)[-1])[:240],
            "media_type": media[0] if media else "unsupported",
            "mime_type": media[1] if media else None,
            "stream_ref": refs.sign_media(path, media[0]) if media else None,
            "preview_ref": refs.sign_media(path, "preview") if media else None,
            "availability": "playable" if media else "unsupported",
        })
    preview = next((a["preview_ref"] for a in attachments if a["media_type"] == "image"), None)
    playable_count = sum(a["availability"] == "playable" for a in attachments)
    return {
        "post_key": key,
        "service": service,
        "creator_id": creator_id,
        "post_id": post_id,
        "title": str(raw.get("title") or "未命名帖子")[:500],
        "creator_name": creator_name or f"{service} · {creator_id}",
        "source_url": source_url,
        "published_at": raw.get("published"),
        "reported_attachment_count": len(raw.get("attachments") or []),
        "playable_count": playable_count if detail else None,
        "preview_ref": preview,
        "tags": [str(tag)[:100] for tag in (raw.get("tags") or []) if isinstance(tag, str)] if detail else [],
        "attachments": attachments if detail else [],
    }
