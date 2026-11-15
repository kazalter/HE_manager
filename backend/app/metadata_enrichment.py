"""Unified media metadata & tag enrichment across scan, download, X import, and backfill."""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from . import manga_artist, manga_metadata, models, tagging

logger = logging.getLogger(__name__)

METADATA_SIDECAR_NAME = "metadata.json"

_URL_RE = re.compile(r"https?://\S+", re.I)
_HASHTAG_RE = re.compile(
    r"(?:^|[\s\u3000.,!?:;()\[\]【】「」『』、。！？])#([^\s#@.,!?:;()\[\]【】「」『』、。！？/\\]{1,50})"
)
_WNACG_AID_RE = re.compile(r"photos-index-aid-(\d+)\.html", re.I)
_ASMR_RJ_RE = re.compile(r"\b(RJ\d{6,8})\b", re.I)


def extract_hashtags(text: Optional[str]) -> list[str]:
    if not text:
        return []
    cleaned_text = _URL_RE.sub(" ", text)
    seen: set[str] = set()
    tags: list[str] = []
    for match in _HASHTAG_RE.finditer(cleaned_text):
        raw = match.group(1).strip("_-~'\"")
        if not raw or raw.isdigit():
            continue
        key = raw.lower()
        if key not in seen:
            seen.add(key)
            tags.append(raw)
    return tags


def read_source_txt(dir_path: Optional[str]) -> dict[str, Optional[str]]:
    result: dict[str, Optional[str]] = {
        "title": None,
        "source_url": None,
        "source_site": None,
        "external_id": None,
    }
    if not dir_path or not os.path.isdir(dir_path):
        return result
    path = os.path.join(dir_path, "source.txt")
    if not os.path.isfile(path):
        return result
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fp:
            lines = [line.strip() for line in fp.read().splitlines() if line.strip()]
    except OSError:
        return result

    if not lines:
        return result
    if lines[0].startswith(("http://", "https://")):
        url = lines[0]
    else:
        result["title"] = lines[0]
        url = next((line for line in lines[1:] if line.startswith(("http://", "https://"))), None)

    if url:
        result["source_url"] = url
        aid_match = _WNACG_AID_RE.search(url)
        if aid_match or "wnacg" in url.lower():
            result["source_site"] = "wnacg"
            if aid_match:
                result["external_id"] = aid_match.group(1)
        elif "asmr.one" in url.lower() or _ASMR_RJ_RE.search(url):
            result["source_site"] = "asmr"
            rj_match = _ASMR_RJ_RE.search(url)
            if rj_match:
                result["external_id"] = rj_match.group(1).upper()

    if len(lines) >= 3 and not result["external_id"]:
        rj_match = _ASMR_RJ_RE.search(lines[2])
        if rj_match:
            result["external_id"] = rj_match.group(1).upper()
            result["source_site"] = result["source_site"] or "asmr"

    return result


def read_metadata_json(dir_path: Optional[str]) -> Optional[dict[str, Any]]:
    if not dir_path or not os.path.isdir(dir_path):
        return None
    path = os.path.join(dir_path, METADATA_SIDECAR_NAME)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fp:
            data = json.load(fp)
            return data if isinstance(data, dict) else None
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to read metadata sidecar %s: %s", path, exc)
        return None


def write_metadata_json(dir_path: str, payload: dict[str, Any]) -> str:
    os.makedirs(dir_path, exist_ok=True)
    path = os.path.join(dir_path, METADATA_SIDECAR_NAME)
    existing = read_metadata_json(dir_path) or {}
    merged = dict(existing)
    for key, value in payload.items():
        if value is not None:
            merged[key] = value
    tmp_path = os.path.join(dir_path, f".{METADATA_SIDECAR_NAME}.tmp.{os.getpid()}")
    try:
        with open(tmp_path, "w", encoding="utf-8") as fp:
            json.dump(merged, fp, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
    return path


def read_x_info_json(path: Optional[str]) -> Optional[dict[str, Any]]:
    if not path:
        return None
    dir_path = path if os.path.isdir(path) else os.path.dirname(path)
    if not dir_path:
        return None
    info_path = os.path.join(dir_path, "info.json")
    if not os.path.isfile(info_path):
        return None
    try:
        with open(info_path, "r", encoding="utf-8") as fp:
            data = json.load(fp)
            return data if isinstance(data, dict) else None
    except Exception:
        return None


def _read_tracks_json(dir_path: Optional[str]) -> Optional[dict[str, Any]]:
    if not dir_path or not os.path.isdir(dir_path):
        return None
    path = os.path.join(dir_path, "tracks.json")
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fp:
            data = json.load(fp)
            return data if isinstance(data, dict) else None
    except Exception:
        return None


def _attach_unique_tag(
    db: Session,
    media: models.Media,
    name: Optional[str],
    namespace: str = "general",
) -> bool:
    clean = (name or "").strip()
    if not clean:
        return False
    ns = (namespace or "general").strip() or "general"
    for existing in media.tags:
        if existing.name == clean and (existing.namespace or "general") == ns:
            return False
    before = len(media.tags)
    tag = tagging.attach_tag(db, media, clean, namespace=ns)
    return tag is not None and len(media.tags) > before


_NOISE_TAG_EXACT = {
    "dl版", "dl", "汉化", "漢化", "中国翻訳", "中國翻譯", "无修正", "無修正",
    "category:後頁>", "後頁>", "后页>", "收藏", "僅",
}
_NOISE_TAG_SUFFIXES = ("汉化组", "漢化組", "翻译组", "翻譯組", "汉化社", "漢化社")
_SCANLATION_NOISE_SUBSTRINGS = (
    "汉化", "漢化", "翻译", "翻譯", "渣翻", "机翻", "機翻",
    "重嵌", "嵌字", "扫图", "掃圖", "个汉", "個漢",
    "去码", "去碼", "疏码", "疏碼",
)
_HAS_WORD_CHAR_RE = re.compile(r"[0-9a-zA-Z\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]")
_PARODY_NOISE_RE = re.compile(
    r"^(?:\d+(?:[╱/]\d+)?|ex-hentai\b.*|ongoing|complete(?:d)?|前編|中編|後編|完結|"
    r"c\d+|comitia\d*|コミティア\d*|comic1.*|エアコミケ\d*|gw超同人祭|ホロクル.*|ホロケット.*)$",
    re.I,
)


def _is_noise_tag(name: Optional[str], namespace: Optional[str] = None) -> bool:
    raw = (name or "").strip()
    if not raw:
        return True
    if not _HAS_WORD_CHAR_RE.search(raw):
        return True
    lowered = raw.lower()
    ns = (namespace or "general").strip().lower()
    if lowered in _NOISE_TAG_EXACT:
        return True
    if lowered.endswith(_NOISE_TAG_SUFFIXES):
        return True
    if ns in ("general", "artist", "parody", "circle"):
        if any(sub in lowered for sub in _SCANLATION_NOISE_SUBSTRINGS):
            return True
    if ns == "category" and lowered in {"後頁>", "后页>", "收藏", "category:後頁>"}:
        return True
    if ns == "parody" and _PARODY_NOISE_RE.match(raw):
        return True
    if ns == "general":
        if raw.isdigit() and raw != "69":
            return True
        if lowered.startswith("ex-hentai "):
            return True
    return False


def purge_noise_tags(db: Session) -> dict[str, int]:
    """Remove ingested scanlation/pagination/duplicate noise tags from DB."""
    removed_links = 0
    deleted_tags = 0

    all_tags = db.query(models.Tag).all()
    noise_ids = [t.id for t in all_tags if _is_noise_tag(t.name, t.namespace)]
    if noise_ids:
        removed_links += (
            db.query(models.media_tags)
            .filter(models.media_tags.c.tag_id.in_(noise_ids))
            .delete(synchronize_session=False)
        )
        deleted_tags += (
            db.query(models.Tag)
            .filter(models.Tag.id.in_(noise_ids))
            .delete(synchronize_session=False)
        )

    # Clear scanlation noise stuck in media.artist column
    artist_rows = (
        db.query(models.Media)
        .filter(models.Media.artist.isnot(None), models.Media.artist != "")
        .all()
    )
    for m in artist_rows:
        if _is_noise_tag(m.artist, "artist"):
            m.artist = None

    # Remove `general` tags on manga that duplicate the same media's `artist` or `circle`
    db.flush()
    manga_rows = (
        db.query(models.Media)
        .options(selectinload(models.Media.tags))
        .filter(models.Media.media_type == "manga")
        .all()
    )
    candidate_orphan_ids: set[int] = set()
    for m in manga_rows:
        creator_names = {
            (m.artist or "").strip().lower(),
        }
        for t in m.tags:
            if (t.namespace or "general") in ("artist", "circle") and t.name:
                creator_names.add(t.name.strip().lower())
        creator_names.discard("")
        if not creator_names:
            continue
        to_unlink = [
            t for t in m.tags
            if (t.namespace or "general") == "general" and t.name.strip().lower() in creator_names
        ]
        if to_unlink:
            for t in to_unlink:
                m.tags.remove(t)
                candidate_orphan_ids.add(t.id)
                removed_links += 1

    db.flush()
    if candidate_orphan_ids:
        used_ids = {
            row[0]
            for row in db.query(models.media_tags.c.tag_id)
            .filter(models.media_tags.c.tag_id.in_(candidate_orphan_ids))
            .distinct()
            .all()
        }
        orphan_ids = list(candidate_orphan_ids - used_ids)
        if orphan_ids:
            deleted_tags += (
                db.query(models.Tag)
                .filter(models.Tag.id.in_(orphan_ids))
                .delete(synchronize_session=False)
            )

    return {"noise_links_removed": int(removed_links), "noise_tags_deleted": int(deleted_tags)}


def _clean_string_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    seen: set[str] = set()
    out: list[str] = []
    for item in values:
        text = str(item or "").strip()
        key = text.lower()
        if text and key not in seen:
            seen.add(key)
            out.append(text)
    return out


def enrich_manga_media(
    db: Session,
    media: models.Media,
    *,
    item: Optional[models.ExternalFavoriteItem] = None,
    sidecar: Optional[dict[str, Any]] = None,
    external_item_lookup: Optional[dict[str, models.ExternalFavoriteItem]] = None,
    known_artists: Optional[set[str]] = None,
    known_circles: Optional[set[str]] = None,
    force: bool = False,
) -> dict[str, int]:
    if media.media_type != "manga":
        return {}

    metrics = {"updated": 0, "artist_filled": 0, "tags_attached": 0, "profiles_created": 0}
    source_info = read_source_txt(media.absolute_path)
    if sidecar is None:
        sidecar = read_metadata_json(media.absolute_path) or {}

    if not media.source_url and (sidecar.get("source_url") or source_info.get("source_url")):
        media.source_url = sidecar.get("source_url") or source_info.get("source_url")
        metrics["updated"] = 1
    if not media.source_site and (sidecar.get("source_site") or source_info.get("source_site")):
        media.source_site = sidecar.get("source_site") or source_info.get("source_site")
        metrics["updated"] = 1

    if item is None and media.source_url:
        if external_item_lookup is not None:
            item = external_item_lookup.get(media.source_url)
        else:
            item = (
                db.query(models.ExternalFavoriteItem)
                .filter(models.ExternalFavoriteItem.url == media.source_url)
                .first()
            )

    if media.artist and _is_noise_tag(media.artist, "artist"):
        media.artist = None
        metrics["updated"] = 1

    parsed = manga_metadata.parse_title_metadata(
        media.title or "",
        relative_path=media.relative_path,
        known_artists=known_artists,
        known_circles=known_circles,
    )
    sidecar_artist = (sidecar.get("artist") or "").strip()
    if sidecar_artist and _is_noise_tag(sidecar_artist, "artist"):
        sidecar_artist = ""
    candidate_artist = (
        sidecar_artist
        or parsed.get("parsed_artist")
        or manga_artist.parse_artist_with_path(
            media.title,
            media.relative_path,
            known_artists=known_artists,
            known_circles=known_circles,
        )
    )
    if candidate_artist and (not media.artist or force):
        if media.artist != candidate_artist:
            media.artist = candidate_artist
            metrics["artist_filled"] = 1
            metrics["updated"] = 1

    parsed_artist = parsed.get("parsed_artist")
    parsed_circle = parsed.get("parsed_circle")
    if parsed_artist and not _is_noise_tag(parsed_artist, "artist"):
        if _attach_unique_tag(db, media, parsed_artist, "artist"):
            metrics["tags_attached"] += 1
    elif media.artist and not _is_noise_tag(media.artist, "artist"):
        if _attach_unique_tag(db, media, media.artist, "artist"):
            metrics["tags_attached"] += 1

    if parsed_circle and not _is_noise_tag(parsed_circle, "circle"):
        if _attach_unique_tag(db, media, parsed_circle, "circle"):
            metrics["tags_attached"] += 1
    if parsed.get("parody") and not _is_noise_tag(parsed["parody"], "parody"):
        if _attach_unique_tag(db, media, parsed["parody"], "parody"):
            metrics["tags_attached"] += 1
    if parsed.get("language") and _attach_unique_tag(db, media, parsed["language"], "language"):
        metrics["tags_attached"] += 1

    categories = _clean_string_list([
        sidecar.get("category"),
        item.category_name if item else None,
    ])
    for cat in categories:
        if _is_noise_tag(cat, "category"):
            continue
        if _attach_unique_tag(db, media, cat, "category"):
            metrics["tags_attached"] += 1

    skip_general_lower = {
        str(val).strip().lower()
        for val in (media.artist, parsed_artist, parsed_circle, sidecar_artist)
        if val and str(val).strip()
    }
    for tag_name in _clean_string_list(sidecar.get("tags")):
        if _is_noise_tag(tag_name, "general") or tag_name.strip().lower() in skip_general_lower:
            continue
        if _attach_unique_tag(db, media, tag_name, "general"):
            metrics["tags_attached"] += 1

    had_profile = media.metadata_profile is not None
    if force or manga_metadata.needs_metadata(media, sidecar=sidecar):
        manga_metadata.build_metadata_profile(
            db,
            media,
            force=force,
            sidecar=sidecar,
            external_item=item,
            known_artists=known_artists,
            known_circles=known_circles,
        )
        metrics["updated"] = 1
        if not had_profile:
            metrics["profiles_created"] = 1

    if metrics["tags_attached"] > 0:
        metrics["updated"] = 1
    return metrics


def enrich_x_media(
    db: Session,
    media: models.Media,
    *,
    post: Optional[models.XPost] = None,
    force: bool = False,
) -> dict[str, int]:
    metrics = {"updated": 0, "artist_filled": 0, "tags_attached": 0}
    info: Optional[dict[str, Any]] = None

    if post is None:
        x_item = (
            db.query(models.XMediaItem)
            .options(selectinload(models.XMediaItem.post))
            .filter(models.XMediaItem.library_media_id == media.id)
            .first()
        )
        if x_item and x_item.post:
            post = x_item.post

    if post is not None:
        author_screen_name = (post.author_screen_name or "").strip() or None
        source_url = (post.url or "").strip() or None
        full_text = post.full_text
    else:
        info = read_x_info_json(media.absolute_path)
        if not info:
            return metrics
        author_screen_name = (info.get("author_screen_name") or "").strip() or None
        source_url = (info.get("url") or "").strip() or None
        full_text = info.get("full_text")

    if not media.source_site:
        media.source_site = "x"
        metrics["updated"] = 1
    if not media.source_url and source_url:
        media.source_url = source_url
        metrics["updated"] = 1
    if author_screen_name and (not media.artist or force):
        if media.artist != author_screen_name:
            media.artist = author_screen_name
            metrics["artist_filled"] = 1
            metrics["updated"] = 1

    if author_screen_name and _attach_unique_tag(db, media, author_screen_name, "artist"):
        metrics["tags_attached"] += 1
        metrics["updated"] = 1

    for hashtag in extract_hashtags(full_text):
        if _attach_unique_tag(db, media, hashtag, "general"):
            metrics["tags_attached"] += 1
            metrics["updated"] = 1

    return metrics


def enrich_audio_media(
    db: Session,
    media: models.Media,
    *,
    item: Optional[models.ExternalFavoriteItem] = None,
    manifest: Optional[dict[str, Any]] = None,
    sidecar: Optional[dict[str, Any]] = None,
    external_item_lookup: Optional[dict[str, models.ExternalFavoriteItem]] = None,
    force: bool = False,
) -> dict[str, int]:
    if media.media_type != "audio":
        return {}

    metrics = {"updated": 0, "artist_filled": 0, "tags_attached": 0}
    dir_path = media.absolute_path if media.absolute_path and os.path.isdir(media.absolute_path) else None
    source_info = read_source_txt(dir_path)
    if sidecar is None:
        sidecar = read_metadata_json(dir_path) or {}
    if manifest is None:
        manifest = _read_tracks_json(dir_path) or {}

    if not media.source_url and (sidecar.get("source_url") or manifest.get("url") or source_info.get("source_url")):
        media.source_url = sidecar.get("source_url") or manifest.get("url") or source_info.get("source_url")
        metrics["updated"] = 1
    if not media.source_site and (sidecar.get("source_site") or source_info.get("source_site")):
        media.source_site = sidecar.get("source_site") or source_info.get("source_site")
        metrics["updated"] = 1
    if not media.source_site and media.source_url and "asmr.one" in media.source_url.lower():
        media.source_site = "asmr"
        metrics["updated"] = 1

    if item is None and media.source_url:
        if external_item_lookup is not None:
            item = external_item_lookup.get(media.source_url)
        else:
            item = (
                db.query(models.ExternalFavoriteItem)
                .filter(
                    models.ExternalFavoriteItem.url == media.source_url,
                    models.ExternalFavoriteItem.source_type == "asmr",
                )
                .first()
            )

    vas = _clean_string_list(sidecar.get("vas") or manifest.get("vas") or [])
    circle = (
        (sidecar.get("circle") or "").strip()
        or (manifest.get("circle") or "").strip()
        or ((item.category_name or "").strip() if item else "")
    ) or None
    general_tags = _clean_string_list(sidecar.get("tags") or manifest.get("tags") or [])

    artist_display = ", ".join(vas) if vas else circle
    if artist_display and (not media.artist or force):
        if media.artist != artist_display:
            media.artist = artist_display
            metrics["artist_filled"] = 1
            metrics["updated"] = 1

    for va in vas:
        if _attach_unique_tag(db, media, va, "artist"):
            metrics["tags_attached"] += 1
    if circle and _attach_unique_tag(db, media, circle, "circle"):
        metrics["tags_attached"] += 1
    for tag_name in general_tags:
        if _attach_unique_tag(db, media, tag_name, "general"):
            metrics["tags_attached"] += 1

    if metrics["tags_attached"] > 0:
        metrics["updated"] = 1
    return metrics


def enrich_media_metadata(
    db: Session,
    media: models.Media,
    *,
    item: Optional[models.ExternalFavoriteItem] = None,
    post: Optional[models.XPost] = None,
    manifest: Optional[dict[str, Any]] = None,
    sidecar: Optional[dict[str, Any]] = None,
    external_item_lookup: Optional[dict[str, models.ExternalFavoriteItem]] = None,
    x_post_lookup: Optional[dict[int, models.XPost]] = None,
    known_artists: Optional[set[str]] = None,
    known_circles: Optional[set[str]] = None,
    force: bool = False,
) -> dict[str, int]:
    if media.media_type == "manga":
        return enrich_manga_media(
            db,
            media,
            item=item,
            sidecar=sidecar,
            external_item_lookup=external_item_lookup,
            known_artists=known_artists,
            known_circles=known_circles,
            force=force,
        )
    if media.media_type == "audio":
        return enrich_audio_media(
            db,
            media,
            item=item,
            manifest=manifest,
            sidecar=sidecar,
            external_item_lookup=external_item_lookup,
            force=force,
        )

    resolved_post = post
    if resolved_post is None and x_post_lookup is not None:
        resolved_post = x_post_lookup.get(media.id)

    if media.source_site == "x" or resolved_post is not None:
        return enrich_x_media(db, media, post=resolved_post, force=force)

    # Check if an image/video was re-scanned from an X post directory containing info.json
    if media.absolute_path and os.path.isfile(os.path.join(os.path.dirname(media.absolute_path), "info.json")):
        info = read_x_info_json(media.absolute_path)
        if info and info.get("tweet_id"):
            return enrich_x_media(db, media, force=force)

    return {}


def metadata_coverage_stats(db: Session) -> dict[str, int]:
    active_q = db.query(models.Media).filter(models.Media.is_missing == False)  # noqa: E712
    total_media = active_q.count()
    with_artist = active_q.filter(models.Media.artist.isnot(None), models.Media.artist != "").count()
    tagged_media = (
        db.query(func.count(func.distinct(models.media_tags.c.media_id)))
        .join(models.Media, models.Media.id == models.media_tags.c.media_id)
        .filter(models.Media.is_missing == False)  # noqa: E712
        .scalar()
        or 0
    )
    total_tags = (
        db.query(func.count(func.distinct(models.media_tags.c.tag_id)))
        .join(models.Media, models.Media.id == models.media_tags.c.media_id)
        .filter(models.Media.is_missing == False)  # noqa: E712
        .scalar()
        or 0
    )

    manga_q = active_q.filter(models.Media.media_type == "manga")
    manga_total = manga_q.count()
    manga_profiled = (
        db.query(func.count(models.MangaMetadataProfile.id))
        .join(models.Media, models.Media.id == models.MangaMetadataProfile.media_id)
        .filter(models.Media.media_type == "manga", models.Media.is_missing == False)  # noqa: E712
        .scalar()
        or 0
    )

    wnacg_rows = (
        manga_q.filter(models.Media.source_site == "wnacg")
        .with_entities(models.Media.absolute_path)
        .all()
    )
    manga_wnacg_total = len(wnacg_rows)
    manga_wnacg_with_sidecar = sum(
        1
        for (path,) in wnacg_rows
        if path and os.path.isfile(os.path.join(path, METADATA_SIDECAR_NAME))
    )

    audio_rows = (
        active_q.filter(models.Media.media_type == "audio")
        .with_entities(models.Media.absolute_path)
        .all()
    )
    audio_total = len(audio_rows)
    audio_with_sidecar = sum(
        1
        for (path,) in audio_rows
        if path and os.path.isfile(os.path.join(path, METADATA_SIDECAR_NAME))
    )

    return {
        "total_media": int(total_media),
        "tagged_media": int(tagged_media),
        "total_tags": int(total_tags),
        "with_artist": int(with_artist),
        "manga_total": int(manga_total),
        "manga_profiled": int(manga_profiled),
        "manga_wnacg_total": int(manga_wnacg_total),
        "manga_wnacg_with_sidecar": int(manga_wnacg_with_sidecar),
        "audio_total": int(audio_total),
        "audio_with_sidecar": int(audio_with_sidecar),
    }


def backfill_media_metadata(
    db: Session,
    *,
    limit: int = 5000,
    force: bool = False,
    clean_noise: bool = True,
) -> dict[str, int]:
    safe_limit = max(1, min(int(limit), 20000))
    noise_stats = purge_noise_tags(db) if clean_noise else {"noise_links_removed": 0, "noise_tags_deleted": 0}
    if clean_noise:
        db.flush()

    known_artists = {
        name.strip().lower()
        for (name,) in db.query(models.Tag.name).filter(models.Tag.namespace == "artist").all()
        if name and not _is_noise_tag(name, "artist")
    }
    known_circles = {
        name.strip().lower()
        for (name,) in db.query(models.Tag.name).filter(models.Tag.namespace == "circle").all()
        if name and not _is_noise_tag(name, "circle")
    }

    rows = (
        db.query(models.Media)
        .options(
            selectinload(models.Media.tags),
            selectinload(models.Media.metadata_profile),
        )
        .filter(models.Media.is_missing == False)  # noqa: E712
        .order_by(models.Media.id.asc())
        .limit(safe_limit)
        .all()
    )

    external_item_lookup = {
        item.url: item
        for item in db.query(models.ExternalFavoriteItem).filter(models.ExternalFavoriteItem.url.isnot(None)).all()
        if item.url
    }
    x_links = (
        db.query(models.XMediaItem.library_media_id, models.XPost)
        .join(models.XPost, models.XPost.id == models.XMediaItem.post_id)
        .filter(models.XMediaItem.library_media_id.isnot(None))
        .all()
    )
    x_post_lookup = {media_id: post for media_id, post in x_links if media_id}

    totals = {
        "checked": 0,
        "updated": 0,
        "artist_filled": 0,
        "tags_attached": 0,
        "manga_profiles_created": 0,
        "manga_enriched": 0,
        "x_enriched": 0,
        "audio_enriched": 0,
        "noise_links_removed": noise_stats["noise_links_removed"],
        "noise_tags_deleted": noise_stats["noise_tags_deleted"],
    }

    for idx, media in enumerate(rows, start=1):
        totals["checked"] += 1
        res = enrich_media_metadata(
            db,
            media,
            external_item_lookup=external_item_lookup,
            x_post_lookup=x_post_lookup,
            known_artists=known_artists,
            known_circles=known_circles,
            force=force,
        )
        if res.get("updated"):
            totals["updated"] += 1
            if media.media_type == "manga":
                totals["manga_enriched"] += 1
            elif media.media_type == "audio":
                totals["audio_enriched"] += 1
            elif media.source_site == "x" or media.id in x_post_lookup:
                totals["x_enriched"] += 1
        totals["artist_filled"] += res.get("artist_filled", 0)
        totals["tags_attached"] += res.get("tags_attached", 0)
        totals["manga_profiles_created"] += res.get("profiles_created", 0)
        if idx % 200 == 0:
            db.flush()

    if clean_noise:
        post_noise = purge_noise_tags(db)
        totals["noise_links_removed"] += post_noise["noise_links_removed"]
        totals["noise_tags_deleted"] += post_noise["noise_tags_deleted"]

    db.commit()
    return totals
