"""Read-only OPDS 1.2 catalog and page-streaming endpoints for manga readers."""
from __future__ import annotations

from datetime import datetime, timezone
import io
import mimetypes
import os
from typing import Iterator, Optional
import urllib.parse
import xml.etree.ElementTree as ET
import zipfile

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from .. import auth, models
from ..database import get_db
from ..services import thumbnails
from ..services.manga_pages import get_manga_image_files
from ..services.media_access import get_media_or_404
from ..services.range_response import get_ranged_file_response
from . import media as media_routes

router = APIRouter(prefix="/opds", tags=["opds"])

ATOM_NS = "http://www.w3.org/2005/Atom"
OPDS_NS = "http://opds-spec.org/2010/catalog"
DCTERMS_NS = "http://purl.org/dc/terms/"
PSE_NS = "http://vaemalkin.org/opds/pse"
OPENSEARCH_NS = "http://a9.com/-/spec/opensearch/1.1/"

HIDDEN_DUP_STATUSES = ("dedup_excluded",)

ET.register_namespace("", ATOM_NS)
ET.register_namespace("opds", OPDS_NS)
ET.register_namespace("dcterms", DCTERMS_NS)
ET.register_namespace("pse", PSE_NS)

NAV_MIME = "application/atom+xml;profile=opds-catalog;kind=navigation;charset=utf-8"
ACQ_MIME = "application/atom+xml;profile=opds-catalog;kind=acquisition;charset=utf-8"

_ARCHIVE_MIMES = {
    ".cbz": "application/vnd.comicbook+zip",
    ".zip": "application/zip",
    ".cbr": "application/vnd.comicbook-rar",
    ".rar": "application/vnd.comicbook-rar",
    ".pdf": "application/pdf",
    ".epub": "application/epub+zip",
}


def _iso_utc(dt: Optional[datetime]) -> str:
    value = dt or datetime.utcnow()
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def _atom(tag: str, text: Optional[str] = None, **attrib: str) -> ET.Element:
    elem = ET.Element(f"{{{ATOM_NS}}}{tag}", attrib)
    if text is not None:
        elem.text = text
    return elem


def _sub_atom(parent: ET.Element, tag: str, text: Optional[str] = None, **attrib: str) -> ET.Element:
    elem = ET.SubElement(parent, f"{{{ATOM_NS}}}{tag}", attrib)
    if text is not None:
        elem.text = text
    return elem


def _xml_response(root: ET.Element, media_type: str) -> Response:
    payload = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    return Response(content=payload, media_type=media_type)


def _new_feed(feed_id: str, title: str, self_href: str, self_type: str) -> ET.Element:
    feed = _atom("feed")
    _sub_atom(feed, "id", feed_id)
    _sub_atom(feed, "title", title)
    _sub_atom(feed, "updated", _iso_utc(None))
    author = _sub_atom(feed, "author")
    _sub_atom(author, "name", "HE Manager")
    _sub_atom(feed, "link", rel="self", href=self_href, type=self_type)
    _sub_atom(feed, "link", rel="start", href="/opds", type=NAV_MIME)
    _sub_atom(
        feed,
        "link",
        rel="search",
        href="/opds/search.xml",
        type="application/opensearchdescription+xml",
    )
    return feed


def _visible_manga_query(db: Session):
    return (
        db.query(models.Media)
        .options(selectinload(models.Media.tags))
        .filter(models.Media.media_type == "manga")
        .filter(models.Media.is_missing == False)  # noqa: E712
        .filter(models.Media.duplicate_status.notin_(HIDDEN_DUP_STATUSES))
    )


def _acquisition_mime(ext: Optional[str]) -> str:
    return _ARCHIVE_MIMES.get((ext or "").lower(), "application/vnd.comicbook+zip")


def _add_nav_entry(
    feed: ET.Element,
    *,
    entry_id: str,
    title: str,
    href: str,
    rel_type: str,
    summary: str = "",
) -> None:
    entry = _sub_atom(feed, "entry")
    _sub_atom(entry, "id", entry_id)
    _sub_atom(entry, "title", title)
    _sub_atom(entry, "updated", _iso_utc(None))
    if summary:
        _sub_atom(entry, "content", summary, type="text")
    _sub_atom(entry, "link", rel="subsection", href=href, type=rel_type)


def _build_acquisition_feed(
    *,
    feed_id: str,
    title: str,
    base_path: str,
    items: list[models.Media],
    total: int,
    page: int,
    limit: int,
    extra_params: Optional[dict[str, str]] = None,
) -> Response:
    params = dict(extra_params or {})

    def page_url(target_page: int) -> str:
        qs = dict(params)
        qs["page"] = str(target_page)
        qs["limit"] = str(limit)
        return f"{base_path}?{urllib.parse.urlencode(qs)}"

    feed = _new_feed(feed_id, title, page_url(page), ACQ_MIME)
    _sub_atom(feed, "link", rel="first", href=page_url(1), type=ACQ_MIME)
    if page > 1:
        _sub_atom(feed, "link", rel="previous", href=page_url(page - 1), type=ACQ_MIME)
    if page * limit < total:
        _sub_atom(feed, "link", rel="next", href=page_url(page + 1), type=ACQ_MIME)

    for media in items:
        entry = _sub_atom(feed, "entry")
        _sub_atom(entry, "id", f"urn:he-manager:media:{media.id}")
        _sub_atom(entry, "title", media.title or f"Manga #{media.id}")
        _sub_atom(entry, "updated", _iso_utc(media.created_at))
        if media.artist:
            author = _sub_atom(entry, "author")
            _sub_atom(author, "name", media.artist)
        for tag in media.tags:
            _sub_atom(entry, "category", term=tag.name, label=tag.name)

        details: list[str] = []
        if media.page_count:
            details.append(f"{media.page_count} 页")
        if media.rating:
            details.append(f"评分 {media.rating}/5")
        if media.favorite:
            details.append("已收藏")
        if details:
            _sub_atom(entry, "summary", " · ".join(details), type="text")

        if media.cover_path:
            cover_href = f"/opds/cover/{media.id}"
            _sub_atom(entry, "link", rel="http://opds-spec.org/image", href=cover_href, type="image/jpeg")
            _sub_atom(
                entry,
                "link",
                rel="http://opds-spec.org/image/thumbnail",
                href=cover_href,
                type="image/jpeg",
            )

        acq_attrib: dict[str, str] = {
            "rel": "http://opds-spec.org/acquisition",
            "href": f"/opds/download/{media.id}",
            "type": _acquisition_mime(media.extension),
        }
        if media.extension != ".dir" and media.file_size:
            acq_attrib["length"] = str(media.file_size)
        _sub_atom(entry, "link", **acq_attrib)

        if media.page_count and media.page_count > 0:
            _sub_atom(
                entry,
                "link",
                **{
                    "rel": "http://vaemalkin.org/opds/pse/stream",
                    "href": f"/opds/page/{media.id}/{{pageNumber}}",
                    "type": "image/jpeg",
                    f"{{{PSE_NS}}}count": str(media.page_count),
                },
            )

    return _xml_response(feed, ACQ_MIME)


@router.get("")
@router.get("/")
def opds_root(_: models.User = Depends(auth.get_current_user)):
    feed = _new_feed("urn:he-manager:opds:root", "HE Manager 漫画书库", "/opds", NAV_MIME)
    _add_nav_entry(
        feed,
        entry_id="urn:he-manager:opds:books",
        title="全部漫画",
        href="/opds/books",
        rel_type=ACQ_MIME,
        summary="按最新入库顺序浏览全部漫画",
    )
    _add_nav_entry(
        feed,
        entry_id="urn:he-manager:opds:recent",
        title="最近更新",
        href="/opds/recent",
        rel_type=ACQ_MIME,
        summary="最近添加的漫画作品",
    )
    _add_nav_entry(
        feed,
        entry_id="urn:he-manager:opds:favorites",
        title="我的收藏",
        href="/opds/favorites",
        rel_type=ACQ_MIME,
        summary="已收藏的漫画",
    )
    _add_nav_entry(
        feed,
        entry_id="urn:he-manager:opds:artists",
        title="按作者浏览",
        href="/opds/artists",
        rel_type=NAV_MIME,
        summary="按解析出的漫画作者分组",
    )
    _add_nav_entry(
        feed,
        entry_id="urn:he-manager:opds:tags",
        title="按标签浏览",
        href="/opds/tags",
        rel_type=NAV_MIME,
        summary="按标签分类浏览漫画",
    )
    return _xml_response(feed, NAV_MIME)


@router.get("/search.xml")
def opds_opensearch(_: models.User = Depends(auth.get_current_user)):
    root = ET.Element(f"{{{OPENSEARCH_NS}}}OpenSearchDescription")
    ET.SubElement(root, f"{{{OPENSEARCH_NS}}}ShortName").text = "HE Manager"
    ET.SubElement(root, f"{{{OPENSEARCH_NS}}}Description").text = "Search manga in HE Manager"
    ET.SubElement(
        root,
        f"{{{OPENSEARCH_NS}}}Url",
        type="application/atom+xml",
        template="/opds/books?q={searchTerms}",
    )
    return _xml_response(root, "application/opensearchdescription+xml;charset=utf-8")


@router.get("/artists")
def opds_artists(
    _: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(models.Media.artist, func.count(models.Media.id))
        .filter(models.Media.media_type == "manga")
        .filter(models.Media.artist.isnot(None), models.Media.artist != "")
        .filter(models.Media.is_missing == False)  # noqa: E712
        .filter(models.Media.duplicate_status.notin_(HIDDEN_DUP_STATUSES))
        .group_by(models.Media.artist)
        .order_by(func.count(models.Media.id).desc(), models.Media.artist.asc())
        .limit(200)
        .all()
    )
    db.rollback()
    feed = _new_feed("urn:he-manager:opds:artists", "作者目录", "/opds/artists", NAV_MIME)
    for artist, count in rows:
        _add_nav_entry(
            feed,
            entry_id=f"urn:he-manager:opds:artist:{urllib.parse.quote(artist, safe='')}",
            title=artist,
            href=f"/opds/books?{urllib.parse.urlencode({'artist': artist})}",
            rel_type=ACQ_MIME,
            summary=f"{count} 部作品",
        )
    return _xml_response(feed, NAV_MIME)


@router.get("/tags")
def opds_tags(
    _: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(models.Tag.name, func.count(models.Media.id))
        .join(models.media_tags, models.Tag.id == models.media_tags.c.tag_id)
        .join(models.Media, models.Media.id == models.media_tags.c.media_id)
        .filter(models.Media.media_type == "manga")
        .filter(models.Media.is_missing == False)  # noqa: E712
        .filter(models.Media.duplicate_status.notin_(HIDDEN_DUP_STATUSES))
        .group_by(models.Tag.id, models.Tag.name)
        .order_by(func.count(models.Media.id).desc(), models.Tag.name.asc())
        .limit(200)
        .all()
    )
    db.rollback()
    feed = _new_feed("urn:he-manager:opds:tags", "标签目录", "/opds/tags", NAV_MIME)
    for tag_name, count in rows:
        _add_nav_entry(
            feed,
            entry_id=f"urn:he-manager:opds:tag:{urllib.parse.quote(tag_name, safe='')}",
            title=tag_name,
            href=f"/opds/books?{urllib.parse.urlencode({'tag': tag_name})}",
            rel_type=ACQ_MIME,
            summary=f"{count} 部作品",
        )
    return _xml_response(feed, NAV_MIME)


def _query_opds_books(
    db: Session,
    *,
    q: Optional[str],
    artist: Optional[str],
    tag: Optional[str],
    favorite_only: bool,
    page: int,
    limit: int,
) -> tuple[list[models.Media], int]:
    query = _visible_manga_query(db)
    if q and q.strip():
        query = media_routes._apply_media_search_filter(query, q.strip(), db=db)
    if artist and artist.strip():
        query = query.filter(models.Media.artist == artist.strip())
    if tag and tag.strip():
        query = media_routes._apply_media_tag_filters(query, tag=tag.strip())
    if favorite_only:
        query = query.filter(models.Media.favorite == True)  # noqa: E712

    total = query.order_by(None).count()
    items = (
        query.order_by(models.Media.id.desc())
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )
    db.rollback()
    return items, total


@router.get("/books")
def opds_books(
    q: Optional[str] = None,
    artist: Optional[str] = None,
    tag: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(30, ge=1, le=100),
    _: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    items, total = _query_opds_books(
        db, q=q, artist=artist, tag=tag, favorite_only=False, page=page, limit=limit
    )
    extra: dict[str, str] = {}
    if q:
        extra["q"] = q
    if artist:
        extra["artist"] = artist
    if tag:
        extra["tag"] = tag
    title = artist or tag or (f"搜索: {q}" if q else "全部漫画")
    return _build_acquisition_feed(
        feed_id="urn:he-manager:opds:books",
        title=title,
        base_path="/opds/books",
        items=items,
        total=total,
        page=page,
        limit=limit,
        extra_params=extra,
    )


@router.get("/recent")
def opds_recent(
    page: int = Query(1, ge=1),
    limit: int = Query(30, ge=1, le=100),
    _: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    items, total = _query_opds_books(
        db, q=None, artist=None, tag=None, favorite_only=False, page=page, limit=limit
    )
    return _build_acquisition_feed(
        feed_id="urn:he-manager:opds:recent",
        title="最近更新",
        base_path="/opds/recent",
        items=items,
        total=total,
        page=page,
        limit=limit,
    )


@router.get("/favorites")
def opds_favorites(
    page: int = Query(1, ge=1),
    limit: int = Query(30, ge=1, le=100),
    _: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    items, total = _query_opds_books(
        db, q=None, artist=None, tag=None, favorite_only=True, page=page, limit=limit
    )
    return _build_acquisition_feed(
        feed_id="urn:he-manager:opds:favorites",
        title="我的收藏",
        base_path="/opds/favorites",
        items=items,
        total=total,
        page=page,
        limit=limit,
    )


@router.get("/cover/{media_id}")
def opds_cover(
    media_id: int,
    request: Request,
    _: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    media = get_media_or_404(media_id, db)
    cover_name = media.cover_path
    db.rollback()
    if not cover_name:
        raise HTTPException(status_code=404, detail="Cover not found")
    safe_name = os.path.basename(cover_name)
    thumb_path = os.path.join(thumbnails.THUMBNAIL_DIR, safe_name)
    if not os.path.isfile(thumb_path):
        raise HTTPException(status_code=404, detail="Cover not found")
    return thumbnails.serve_thumbnail_file(
        thumb_path,
        request=request,
        cache_control="private, max-age=86400",
    )


@router.get("/page/{media_id}/{page_index}")
def opds_page(
    media_id: int,
    page_index: int,
    request: Request,
    _: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    return media_routes.get_manga_page(
        media_id,
        page_index,
        track_progress=False,
        thumbnail=False,
        db=db,
        request=request,
    )


class _ChunkBuffer(io.RawIOBase):
    def __init__(self) -> None:
        self.buffer = bytearray()
        self._pos = 0

    def writable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return False

    def tell(self) -> int:
        return self._pos

    def write(self, data) -> int:
        chunk = bytes(data)
        self.buffer.extend(chunk)
        self._pos += len(chunk)
        return len(chunk)

    def drain(self) -> bytes:
        if not self.buffer:
            return b""
        out = bytes(self.buffer)
        self.buffer.clear()
        return out


def _stream_directory_as_cbz(root_dir: str, files: list[str]) -> Iterator[bytes]:
    sink = _ChunkBuffer()
    with zipfile.ZipFile(sink, mode="w", compression=zipfile.ZIP_STORED) as zf:
        for file_path in files:
            rel = os.path.relpath(file_path, root_dir).replace(os.sep, "/")
            zf.write(file_path, arcname=rel)
            chunk = sink.drain()
            if chunk:
                yield chunk
    tail = sink.drain()
    if tail:
        yield tail


@router.get("/download/{media_id}")
def opds_download(
    media_id: int,
    request: Request,
    _: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    media = get_media_or_404(media_id, db)
    if media.media_type != "manga":
        raise HTTPException(status_code=404, detail="Manga not found")
    from types import SimpleNamespace

    book = SimpleNamespace(
        id=media.id,
        title=media.title,
        absolute_path=media.absolute_path,
        extension=media.extension,
    )
    db.rollback()

    if not book.absolute_path or not os.path.exists(book.absolute_path):
        raise HTTPException(status_code=404, detail="File not found on disk")

    if book.extension == ".dir":
        files = get_manga_image_files(book)
        if not files:
            raise HTTPException(status_code=404, detail="Manga folder has no pages")
        safe_title = (book.title or f"manga-{book.id}").replace("/", "_").replace("\\", "_")
        encoded_name = urllib.parse.quote(f"{safe_title}.cbz")
        return StreamingResponse(
            _stream_directory_as_cbz(book.absolute_path, files),
            media_type="application/vnd.comicbook+zip",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}"},
        )

    resp = get_ranged_file_response(request, book.absolute_path)
    filename = os.path.basename(book.absolute_path)
    resp.headers["Content-Disposition"] = f"attachment; filename*=UTF-8''{urllib.parse.quote(filename)}"
    return resp
