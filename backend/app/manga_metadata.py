import json
import os
import re
from datetime import datetime
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from . import manga_artist, models
from .dedup import normalize as dedup_normalize


ANALYZER_VERSION = "metadata-v3"

LANGUAGE_HINTS = {
    "中文": "中文",
    "中国翻訳": "中文",
    "中國翻譯": "中文",
    "汉化": "中文",
    "漢化": "中文",
    "english": "English",
    "eng": "English",
    "japanese": "日本語",
    "日本語": "日本語",
}

NOISE_WORDS = {
    "dl版", "dl version", "無修正", "无修正", "digital", "カラー", "color",
    "中国翻訳", "中國翻譯", "汉化", "漢化", "中文", "english", "eng",
}

JUNK_CATEGORIES = {"後頁>", "后页>", "收藏"}

_EVENT_OR_FORMAT_PARENS_RE = re.compile(
    r"^(?:c\d+|comitia\d*|コミティア\d*|comic1.*|例大祭.*|紅楼夢.*|サンクリ.*|"
    r"air\s*comiket.*|エアコミケ\d*|ホロクル.*|ホロケット.*|gw超同人祭|コミックトレジャー.*|"
    r"同人誌|成年コミック|商業誌|単行本|雑誌|漫画|cg集|画集|イラスト集|18禁|r-?18|無修正|无修正|"
    r"前編|中編|後編|完結|ongoing|complete(?:d)?|wip|sample|\d{4}[-/年]\d*)$",
    re.I,
)

_NOISE_PARENS_RE = re.compile(
    r"(?:^\d+(?:[╱/]\d+)?$|^ex-hentai\b|汉化|漢化|翻译|翻譯|渣翻|机翻|機翻|重嵌|嵌字|扫图|掃圖|个汉|個漢|去码|去碼|疏码|疏碼)",
    re.I,
)


def _json_dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def json_loads(value, fallback):
    if not value:
        return fallback
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return fallback


def _dedupe(items: list[str]) -> list[str]:
    seen = set()
    out = []
    for item in items:
        item = str(item).strip()
        key = item.lower()
        if item and key not in seen:
            seen.add(key)
            out.append(item)
    return out


def _bracket_chunks(title: str) -> list[str]:
    chunks = []
    for pattern in [r"\[([^\]]+)\]", r"\(([^)]+)\)", r"（([^）]+)）", r"【([^】]+)】"]:
        chunks.extend(match.group(1).strip() for match in re.finditer(pattern, title))
    return [chunk for chunk in chunks if chunk]


def _strip_bracket_noise(title: str) -> str:
    cleaned = re.sub(r"^\s*\([^)]*\)\s*", "", title)
    cleaned = re.sub(r"^\s*\[[^\]]+\]\s*", "", cleaned)
    cleaned = re.sub(r"\[[^\]]*(?:汉化|漢化|中文|DL|無修正|无修正|翻訳|翻譯)[^\]]*\]", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -_｜|")
    return cleaned or title


def parse_title_metadata(
    title: str,
    relative_path: Optional[str] = None,
    *,
    known_artists: Optional[Iterable[str]] = None,
    known_circles: Optional[Iterable[str]] = None,
) -> dict:
    chunks = _bracket_chunks(title or "")
    tags = []
    language = None
    parody = None

    for chunk in chunks:
        lowered = chunk.lower()
        for key, label in LANGUAGE_HINTS.items():
            if key.lower() in lowered:
                language = language or label
        if any(word.lower() in lowered for word in NOISE_WORDS):
            tags.append(chunk)

    artist = manga_artist.parse_artist_with_path(
        title,
        relative_path,
        known_artists=known_artists,
        known_circles=known_circles,
    )
    circle = manga_artist.parse_circle_with_path(
        title,
        relative_path,
        known_artists=known_artists,
        known_circles=known_circles,
    )
    artist_lower = (artist or "").lower()
    circle_lower = (circle or "").lower()

    # Search parenthetical chunks *outside* [...] / 【...】 so `[Circle (Artist)]`
    # does not mistake `(Artist)` for the parody.
    outside_brackets = re.sub(r"\[[^\]]*\]|【[^】]*】", " ", title or "")
    paren_chunks = [
        (m.group(1) or m.group(2) or "").strip()
        for m in re.finditer(r"\(([^)]+)\)|（([^）]+)）", outside_brackets)
    ]
    for chunk in paren_chunks:
        if not chunk:
            continue
        lowered = chunk.lower()
        if lowered in {artist_lower, circle_lower}:
            continue
        if any(word.lower() in lowered for word in NOISE_WORDS):
            continue
        if _EVENT_OR_FORMAT_PARENS_RE.match(chunk) or _NOISE_PARENS_RE.search(chunk):
            continue
        parody = parody or chunk

    parsed_title = _strip_bracket_noise(title or "")
    normalized = dedup_normalize.normalize_title(parsed_title)

    return {
        "normalized_title": normalized,
        "parsed_title": parsed_title,
        "parsed_artist": artist,
        "parsed_circle": circle,
        "parody": parody,
        "language": language,
        "title_tags": _dedupe(tags),
    }


def _read_local_sidecar(media: models.Media) -> dict:
    if not media.absolute_path or not os.path.isdir(media.absolute_path):
        return {}
    sidecar_path = os.path.join(media.absolute_path, "metadata.json")
    if not os.path.isfile(sidecar_path):
        return {}
    try:
        with open(sidecar_path, "r", encoding="utf-8") as fp:
            data = json.load(fp)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _sidecar_signature(sidecar: Optional[dict]) -> str:
    if not sidecar:
        return ""
    tags = ",".join(sorted(str(t).strip() for t in (sidecar.get("tags") or []) if str(t).strip()))
    return "|".join([
        str(sidecar.get("category") or "").strip(),
        tags,
        str(sidecar.get("intro") or "").strip()[:120],
    ])


def _source_signature(media: models.Media, sidecar: Optional[dict] = None) -> str:
    if sidecar is None:
        sidecar = _read_local_sidecar(media)
    return "|".join(
        [
            str(media.id),
            media.title or "",
            media.relative_path or "",
            media.artist or "",
            media.source_site or "",
            media.source_url or "",
            str(media.page_count or ""),
            ",".join(sorted(tag.name for tag in media.tags)),
            _sidecar_signature(sidecar),
        ]
    )


def _external_item_for_media(db: Session, media: models.Media) -> Optional[models.ExternalFavoriteItem]:
    if not media.source_url:
        return None
    return (
        db.query(models.ExternalFavoriteItem)
        .filter(models.ExternalFavoriteItem.url == media.source_url)
        .first()
    )


def needs_metadata(media: models.Media, sidecar: Optional[dict] = None) -> bool:
    profile = media.metadata_profile
    if not profile:
        return media.media_type == "manga"
    return (
        profile.analyzer_version != ANALYZER_VERSION
        or profile.source_signature != _source_signature(media, sidecar=sidecar)
    )


def build_metadata_profile(
    db: Session,
    media: models.Media,
    force: bool = False,
    sidecar: Optional[dict] = None,
    external_item: Optional[models.ExternalFavoriteItem] = None,
    known_artists: Optional[Iterable[str]] = None,
    known_circles: Optional[Iterable[str]] = None,
) -> models.MangaMetadataProfile:
    if media.media_type != "manga":
        raise ValueError("Only manga media can have manga metadata")
    if sidecar is None:
        sidecar = _read_local_sidecar(media)
    if media.metadata_profile and not force and not needs_metadata(media, sidecar=sidecar):
        return media.metadata_profile

    parsed = parse_title_metadata(
        media.title or "",
        relative_path=media.relative_path,
        known_artists=known_artists,
        known_circles=known_circles,
    )
    tags = list(parsed["title_tags"])
    source_matches = []
    summary_bits = []
    confidence = 25

    parsed_artist = parsed.get("parsed_artist") or (media.artist or "").strip() or None
    parsed_circle = parsed.get("parsed_circle")

    if parsed_artist:
        tags.append(f"artist:{parsed_artist}")
        summary_bits.append(f"作者/社团：{parsed_artist}")
        confidence += 15
    if parsed_circle:
        tags.append(f"circle:{parsed_circle}")
    if parsed.get("parody"):
        tags.append(f"parody:{parsed['parody']}")
        summary_bits.append(f"原作/系列：{parsed['parody']}")
        confidence += 10
    if parsed.get("language"):
        tags.append(f"language:{parsed['language']}")
        summary_bits.append(f"语言：{parsed['language']}")
        confidence += 5

    for tag in media.tags:
        tags.append(tag.name)

    if sidecar:
        sidecar_tags = [str(t).strip() for t in (sidecar.get("tags") or []) if str(t).strip()]
        if sidecar_tags:
            tags.extend(sidecar_tags)
            confidence += 15
        sidecar_category = (sidecar.get("category") or "").strip()
        if sidecar_category and sidecar_category not in JUNK_CATEGORIES:
            tags.append(f"category:{sidecar_category}")
            summary_bits.append(f"分类：{sidecar_category}")
            confidence += 10
        sidecar_intro = (sidecar.get("intro") or "").strip()
        if sidecar_intro:
            summary_bits.append(f"简介：{sidecar_intro}")
        source_matches.append({
            "source_type": sidecar.get("source_site") or media.source_site or "sidecar",
            "external_id": sidecar.get("external_id"),
            "url": sidecar.get("source_url") or media.source_url,
            "category": sidecar_category if sidecar_category and sidecar_category not in JUNK_CATEGORIES else None,
        })

    item = external_item if external_item is not None else _external_item_for_media(db, media)
    if item:
        cat_name = (item.category_name or "").strip()
        clean_cat = cat_name if cat_name and cat_name not in JUNK_CATEGORIES else None
        source_matches.append({
            "source_type": item.source_type,
            "external_id": item.external_id,
            "url": item.url,
            "title": item.title,
            "category_id": item.category_id,
            "category_name": clean_cat,
        })
        confidence += 30
        if clean_cat:
            tags.append(f"category:{clean_cat}")
            summary_bits.append(f"来源分类：{clean_cat}")
        if item.title and item.title != media.title:
            summary_bits.append(f"来源标题：{item.title}")

    if media.source_site:
        source_matches.append({"source_type": media.source_site, "url": media.source_url})
        confidence += 10

    if media.page_count:
        if media.page_count <= 35:
            tags.append("length:短篇")
        elif media.page_count >= 100:
            tags.append("length:长篇")
        else:
            tags.append("length:中篇")
        summary_bits.append(f"页数：{media.page_count}")

    external_summary = "；".join(summary_bits) + ("。" if summary_bits else "")
    profile = media.metadata_profile
    if not profile:
        profile = models.MangaMetadataProfile(media=media)
        db.add(profile)

    profile.normalized_title = parsed["normalized_title"]
    profile.parsed_title = parsed["parsed_title"]
    profile.parsed_artist = parsed_artist
    profile.parsed_circle = parsed_circle
    profile.parody = parsed["parody"]
    profile.language = parsed["language"]
    profile.external_tags = _json_dumps(_dedupe(tags))
    profile.external_summary = external_summary
    profile.source_matches = _json_dumps(source_matches)
    profile.confidence = min(100, confidence)
    profile.analyzer_version = ANALYZER_VERSION
    profile.source_signature = _source_signature(media, sidecar=sidecar)
    profile.updated_at = datetime.utcnow()
    return profile


def serialize_profile(profile: models.MangaMetadataProfile) -> dict:
    return {
        "media_id": profile.media_id,
        "normalized_title": profile.normalized_title,
        "parsed_title": profile.parsed_title,
        "parsed_artist": profile.parsed_artist,
        "parsed_circle": profile.parsed_circle,
        "parody": profile.parody,
        "language": profile.language,
        "external_tags": json_loads(profile.external_tags, []),
        "external_summary": profile.external_summary or "",
        "source_matches": json_loads(profile.source_matches, []),
        "confidence": profile.confidence or 0,
        "updated_at": profile.updated_at,
    }


def profile_stats(db: Session) -> dict:
    total = db.query(models.Media).filter(models.Media.media_type == "manga", models.Media.is_missing == False).count()  # noqa: E712
    profiled = db.query(models.MangaMetadataProfile).count()
    stale = 0
    rows = (
        db.query(models.Media)
        .join(models.MangaMetadataProfile, models.MangaMetadataProfile.media_id == models.Media.id)
        .filter(models.Media.media_type == "manga", models.Media.is_missing == False)  # noqa: E712
        .all()
    )
    for media in rows:
        if needs_metadata(media):
            stale += 1
    return {"total_manga": total, "profiled": profiled, "stale": stale, "missing": max(0, total - profiled)}
