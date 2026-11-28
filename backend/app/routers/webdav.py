"""Read-only WebDAV server exposing the HE Manager media library."""
from __future__ import annotations

from datetime import datetime, timezone
from email.utils import formatdate
import hashlib
import html
import mimetypes
import os
import re
from types import SimpleNamespace
from typing import Optional
import urllib.parse
import xml.etree.ElementTree as ET

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from .. import auth, models
from ..database import get_db
from ..services.manga_pages import get_manga_image_files
from ..services.range_response import get_ranged_file_response
from .audio import _resolve_audio_tracks

router = APIRouter(tags=["webdav"])

DAV_NS = "DAV:"
ET.register_namespace("D", DAV_NS)

HIDDEN_DUP_STATUSES = ("dedup_excluded",)
_COLLECTIONS: dict[str, Optional[str]] = {
    "Videos": "video",
    "Manga": "manga",
    "Images": "image",
    "Audio": "audio",
    "Favorites": None,
}
_ENTRY_ID_RE = re.compile(r"^(\d+)\s*-")
_CHILD_INDEX_RE = re.compile(r"^(\d+)[_\s-]")
_UNSAFE_FILENAME_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')


def _sanitize_name(raw: Optional[str], fallback: str) -> str:
    text = _UNSAFE_FILENAME_RE.sub("_", (raw or "").strip())
    text = re.sub(r"\s+", " ", text).strip(" .")
    if not text:
        return fallback
    return text[:120]


def _is_dir_media(media: models.Media) -> bool:
    if media.extension == ".dir":
        return True
    if media.media_type == "audio" and media.absolute_path and os.path.isdir(media.absolute_path):
        return True
    return False


def _media_entry_name(media: models.Media) -> str:
    base = _sanitize_name(media.title, f"media_{media.id}")
    if _is_dir_media(media):
        return f"{media.id} - {base}"
    ext = (media.extension or "").strip()
    if ext and not ext.startswith("."):
        ext = f".{ext}"
    if ext and base.lower().endswith(ext.lower()):
        base = base[: -len(ext)].rstrip(" .") or f"media_{media.id}"
    return f"{media.id} - {base}{ext}"


def _encode_href(parts: list[str], *, is_dir: bool) -> str:
    encoded = "/".join(urllib.parse.quote(p, safe="") for p in parts if p)
    base = f"/webdav/{encoded}" if encoded else "/webdav"
    if is_dir and not base.endswith("/"):
        return f"{base}/"
    return base


def _http_date(dt_or_ts: Optional[datetime | float]) -> str:
    if isinstance(dt_or_ts, (int, float)):
        return formatdate(dt_or_ts, usegmt=True)
    if isinstance(dt_or_ts, datetime):
        dt = dt_or_ts if dt_or_ts.tzinfo else dt_or_ts.replace(tzinfo=timezone.utc)
        return formatdate(dt.timestamp(), usegmt=True)
    return formatdate(datetime.now(timezone.utc).timestamp(), usegmt=True)


def _visible_media_base(db: Session):
    return (
        db.query(models.Media)
        .filter(models.Media.is_missing == False)  # noqa: E712
        .filter(models.Media.duplicate_status.notin_(HIDDEN_DUP_STATUSES))
    )


def _load_collection_media(db: Session, collection: str) -> list[models.Media]:
    query = _visible_media_base(db)
    media_type = _COLLECTIONS[collection]
    if media_type is not None:
        query = query.filter(models.Media.media_type == media_type)
    else:
        query = query.filter(models.Media.favorite == True)  # noqa: E712
    items = query.order_by(models.Media.id.desc()).all()
    db.rollback()
    return items


def _resolve_media_in_collection(db: Session, collection: str, segment: str) -> models.Media:
    match = _ENTRY_ID_RE.match(segment)
    if not match:
        raise HTTPException(status_code=404, detail="Not found")
    media_id = int(match.group(1))
    media = (
        _visible_media_base(db)
        .filter(models.Media.id == media_id)
        .first()
    )
    if not media:
        raise HTTPException(status_code=404, detail="Not found")
    media_type = _COLLECTIONS[collection]
    if media_type is not None and media.media_type != media_type:
        raise HTTPException(status_code=404, detail="Not found")
    if media_type is None and not media.favorite:
        raise HTTPException(status_code=404, detail="Not found")
    if _media_entry_name(media) != segment:
        raise HTTPException(status_code=404, detail="Not found")
    return media


def _dir_media_children(media_snapshot: SimpleNamespace) -> list[tuple[str, str]]:
    """Return list of (virtual_filename, absolute_path) for a directory media item."""
    if media_snapshot.media_type == "manga":
        files = get_manga_image_files(media_snapshot)
        return [
            (f"{idx:04d}_{_sanitize_name(os.path.basename(path), f'page_{idx}')}", path)
            for idx, path in enumerate(files, start=1)
        ]
    if media_snapshot.media_type == "audio":
        tracks = _resolve_audio_tracks(media_snapshot)
        out: list[tuple[str, str]] = []
        for idx, track in enumerate(tracks, start=1):
            abs_path = track["abs_path"]
            ext = os.path.splitext(abs_path)[1]
            title = _sanitize_name(track.get("title"), f"track_{idx}")
            if ext and title.lower().endswith(ext.lower()):
                title = title[: -len(ext)].rstrip(" .") or f"track_{idx}"
            out.append((f"{idx:02d} - {title}{ext}", abs_path))
        return out
    return []


def _dav_response_element(
    *,
    href: str,
    display_name: str,
    is_dir: bool,
    size: int = 0,
    content_type: Optional[str] = None,
    last_modified: Optional[datetime | float] = None,
    etag: Optional[str] = None,
) -> ET.Element:
    resp = ET.Element(f"{{{DAV_NS}}}response")
    ET.SubElement(resp, f"{{{DAV_NS}}}href").text = href
    propstat = ET.SubElement(resp, f"{{{DAV_NS}}}propstat")
    prop = ET.SubElement(propstat, f"{{{DAV_NS}}}prop")
    ET.SubElement(prop, f"{{{DAV_NS}}}displayname").text = display_name
    res_type = ET.SubElement(prop, f"{{{DAV_NS}}}resourcetype")
    if is_dir:
        ET.SubElement(res_type, f"{{{DAV_NS}}}collection")
    else:
        ET.SubElement(prop, f"{{{DAV_NS}}}getcontentlength").text = str(max(0, size))
        ET.SubElement(prop, f"{{{DAV_NS}}}getcontenttype").text = content_type or "application/octet-stream"
    ET.SubElement(prop, f"{{{DAV_NS}}}getlastmodified").text = _http_date(last_modified)
    if etag:
        ET.SubElement(prop, f"{{{DAV_NS}}}getetag").text = etag
    ET.SubElement(propstat, f"{{{DAV_NS}}}status").text = "HTTP/1.1 200 OK"
    return resp


def _file_dav_metadata(abs_path: str, fallback_size: int = 0, fallback_dt: Optional[datetime] = None) -> tuple[int, Optional[float], str]:
    try:
        st = os.stat(abs_path)
        etag = f'"{hashlib.md5(f"{abs_path}:{st.st_size}:{st.st_mtime_ns}".encode()).hexdigest()}"'
        return st.st_size, st.st_mtime, etag
    except OSError:
        return fallback_size, (fallback_dt.timestamp() if fallback_dt else None), ""


def _parse_webdav_parts(raw_path: str) -> list[str]:
    cleaned = raw_path.strip("/")
    if not cleaned:
        return []
    parts = [part for part in cleaned.split("/") if part]
    if any(part in {".", ".."} for part in parts):
        raise HTTPException(status_code=404, detail="Invalid path")
    return parts


def _handle_propfind(parts: list[str], depth: str, db: Session) -> Response:
    if depth not in {"0", "1"}:
        raise HTTPException(status_code=403, detail="Depth infinity is not supported")

    multistatus = ET.Element(f"{{{DAV_NS}}}multistatus")

    # /webdav/
    if len(parts) == 0:
        multistatus.append(_dav_response_element(href="/webdav/", display_name="HE Manager", is_dir=True))
        if depth == "1":
            for name in _COLLECTIONS:
                multistatus.append(
                    _dav_response_element(
                        href=_encode_href([name], is_dir=True),
                        display_name=name,
                        is_dir=True,
                    )
                )
        db.rollback()
        return Response(
            status_code=207,
            content=ET.tostring(multistatus, encoding="utf-8", xml_declaration=True),
            media_type="application/xml; charset=utf-8",
        )

    collection = parts[0]
    if collection not in _COLLECTIONS:
        raise HTTPException(status_code=404, detail="Collection not found")

    # /webdav/{Collection}/
    if len(parts) == 1:
        multistatus.append(
            _dav_response_element(
                href=_encode_href([collection], is_dir=True),
                display_name=collection,
                is_dir=True,
            )
        )
        if depth == "1":
            items = _load_collection_media(db, collection)
            for media in items:
                entry_name = _media_entry_name(media)
                is_dir = _is_dir_media(media)
                if is_dir:
                    multistatus.append(
                        _dav_response_element(
                            href=_encode_href([collection, entry_name], is_dir=True),
                            display_name=entry_name,
                            is_dir=True,
                            last_modified=media.created_at,
                        )
                    )
                else:
                    size, mtime, etag = _file_dav_metadata(
                        media.absolute_path,
                        fallback_size=media.file_size or 0,
                        fallback_dt=media.created_at,
                    )
                    mime, _ = mimetypes.guess_type(entry_name)
                    multistatus.append(
                        _dav_response_element(
                            href=_encode_href([collection, entry_name], is_dir=False),
                            display_name=entry_name,
                            is_dir=False,
                            size=size,
                            content_type=mime,
                            last_modified=mtime,
                            etag=etag,
                        )
                    )
        else:
            db.rollback()
        return Response(
            status_code=207,
            content=ET.tostring(multistatus, encoding="utf-8", xml_declaration=True),
            media_type="application/xml; charset=utf-8",
        )

    # /webdav/{Collection}/{entry_name}
    entry_name = parts[1]
    media = _resolve_media_in_collection(db, collection, entry_name)
    is_dir = _is_dir_media(media)
    snapshot = SimpleNamespace(
        id=media.id,
        media_type=media.media_type,
        absolute_path=media.absolute_path,
        extension=media.extension,
        file_size=media.file_size or 0,
        created_at=media.created_at,
    )
    db.rollback()

    if len(parts) == 2:
        if is_dir:
            multistatus.append(
                _dav_response_element(
                    href=_encode_href([collection, entry_name], is_dir=True),
                    display_name=entry_name,
                    is_dir=True,
                    last_modified=snapshot.created_at,
                )
            )
            if depth == "1":
                for child_name, child_abs in _dir_media_children(snapshot):
                    size, mtime, etag = _file_dav_metadata(child_abs)
                    mime, _ = mimetypes.guess_type(child_name)
                    multistatus.append(
                        _dav_response_element(
                            href=_encode_href([collection, entry_name, child_name], is_dir=False),
                            display_name=child_name,
                            is_dir=False,
                            size=size,
                            content_type=mime,
                            last_modified=mtime,
                            etag=etag,
                        )
                    )
        else:
            size, mtime, etag = _file_dav_metadata(
                snapshot.absolute_path,
                fallback_size=snapshot.file_size,
                fallback_dt=snapshot.created_at,
            )
            mime, _ = mimetypes.guess_type(entry_name)
            multistatus.append(
                _dav_response_element(
                    href=_encode_href([collection, entry_name], is_dir=False),
                    display_name=entry_name,
                    is_dir=False,
                    size=size,
                    content_type=mime,
                    last_modified=mtime,
                    etag=etag,
                )
            )
        return Response(
            status_code=207,
            content=ET.tostring(multistatus, encoding="utf-8", xml_declaration=True),
            media_type="application/xml; charset=utf-8",
        )

    # /webdav/{Collection}/{entry_name}/{child_name}
    if len(parts) == 3 and is_dir:
        child_name = parts[2]
        children = dict(_dir_media_children(snapshot))
        child_abs = children.get(child_name)
        if not child_abs or not os.path.isfile(child_abs):
            raise HTTPException(status_code=404, detail="File not found")
        size, mtime, etag = _file_dav_metadata(child_abs)
        mime, _ = mimetypes.guess_type(child_name)
        multistatus.append(
            _dav_response_element(
                href=_encode_href([collection, entry_name, child_name], is_dir=False),
                display_name=child_name,
                is_dir=False,
                size=size,
                content_type=mime,
                last_modified=mtime,
                etag=etag,
            )
        )
        return Response(
            status_code=207,
            content=ET.tostring(multistatus, encoding="utf-8", xml_declaration=True),
            media_type="application/xml; charset=utf-8",
        )

    raise HTTPException(status_code=404, detail="Not found")


def _html_listing(title: str, entries: list[tuple[str, str, bool]]) -> Response:
    rows = "".join(
        f'<li><a href="{html.escape(href)}">{html.escape(name)}{"/" if is_dir else ""}</a></li>'
        for name, href, is_dir in entries
    )
    body = f"<!doctype html><html><meta charset='utf-8'><title>{html.escape(title)}</title><h1>{html.escape(title)}</h1><ul>{rows}</ul></html>"
    return Response(content=body, media_type="text/html; charset=utf-8")


def _handle_get_or_head(request: Request, parts: list[str], db: Session) -> Response:
    is_head = request.method == "HEAD"

    if len(parts) == 0:
        db.rollback()
        if is_head:
            return Response(status_code=200, media_type="text/html; charset=utf-8")
        return _html_listing(
            "HE Manager WebDAV",
            [(name, _encode_href([name], is_dir=True), True) for name in _COLLECTIONS],
        )

    collection = parts[0]
    if collection not in _COLLECTIONS:
        raise HTTPException(status_code=404, detail="Collection not found")

    if len(parts) == 1:
        items = _load_collection_media(db, collection)
        if is_head:
            return Response(status_code=200, media_type="text/html; charset=utf-8")
        entries = []
        for media in items:
            name = _media_entry_name(media)
            is_dir = _is_dir_media(media)
            entries.append((name, _encode_href([collection, name], is_dir=is_dir), is_dir))
        return _html_listing(f"HE Manager - {collection}", entries)

    entry_name = parts[1]
    media = _resolve_media_in_collection(db, collection, entry_name)
    is_dir = _is_dir_media(media)
    snapshot = SimpleNamespace(
        id=media.id,
        media_type=media.media_type,
        absolute_path=media.absolute_path,
        extension=media.extension,
    )
    db.rollback()

    if len(parts) == 2:
        if is_dir:
            if is_head:
                return Response(status_code=200, media_type="text/html; charset=utf-8")
            children = _dir_media_children(snapshot)
            entries = [
                (child_name, _encode_href([collection, entry_name, child_name], is_dir=False), False)
                for child_name, _ in children
            ]
            return _html_listing(entry_name, entries)
        if not snapshot.absolute_path or not os.path.isfile(snapshot.absolute_path):
            raise HTTPException(status_code=404, detail="File not found on disk")
        if is_head:
            size, mtime, etag = _file_dav_metadata(snapshot.absolute_path)
            mime, _ = mimetypes.guess_type(snapshot.absolute_path)
            headers = {
                "Accept-Ranges": "bytes",
                "Content-Length": str(size),
                "Last-Modified": _http_date(mtime),
            }
            if etag:
                headers["ETag"] = etag
            return Response(status_code=200, media_type=mime or "application/octet-stream", headers=headers)
        return get_ranged_file_response(request, snapshot.absolute_path)

    if len(parts) == 3 and is_dir:
        child_name = parts[2]
        children = dict(_dir_media_children(snapshot))
        child_abs = children.get(child_name)
        if not child_abs or not os.path.isfile(child_abs):
            raise HTTPException(status_code=404, detail="File not found")
        if is_head:
            size, mtime, etag = _file_dav_metadata(child_abs)
            mime, _ = mimetypes.guess_type(child_abs)
            headers = {
                "Accept-Ranges": "bytes",
                "Content-Length": str(size),
                "Last-Modified": _http_date(mtime),
            }
            if etag:
                headers["ETag"] = etag
            return Response(status_code=200, media_type=mime or "application/octet-stream", headers=headers)
        return get_ranged_file_response(request, child_abs)

    raise HTTPException(status_code=404, detail="Not found")


@router.options("/webdav")
@router.options("/webdav/{subpath:path}")
def webdav_options():
    return Response(
        status_code=200,
        headers={
            "DAV": "1",
            "Allow": "OPTIONS, GET, HEAD, PROPFIND",
            "MS-Author-Via": "DAV",
        },
    )


@router.api_route(
    "/webdav",
    methods=["GET", "HEAD", "PROPFIND", "PUT", "DELETE", "MKCOL", "COPY", "MOVE", "PROPPATCH", "LOCK", "UNLOCK"],
)
@router.api_route(
    "/webdav/{subpath:path}",
    methods=["GET", "HEAD", "PROPFIND", "PUT", "DELETE", "MKCOL", "COPY", "MOVE", "PROPPATCH", "LOCK", "UNLOCK"],
)
def webdav_dispatch(
    request: Request,
    subpath: str = "",
    _: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    method = request.method.upper()
    if method not in {"GET", "HEAD", "PROPFIND"}:
        return Response(
            status_code=405,
            headers={"Allow": "OPTIONS, GET, HEAD, PROPFIND"},
        )

    parts = _parse_webdav_parts(subpath)
    if method == "PROPFIND":
        depth = (request.headers.get("depth") or "1").strip().lower()
        return _handle_propfind(parts, depth, db)
    return _handle_get_or_head(request, parts, db)
