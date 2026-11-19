"""SQLite FTS5 index maintenance and query pre-filtering for media search."""
from __future__ import annotations

import logging
import re
from typing import Iterable, Optional
from weakref import WeakSet

from sqlalchemy import event, inspect as sa_inspect, text
from sqlalchemy.orm import Session, selectinload

from .. import manga_search, models, zh_conv

logger = logging.getLogger(__name__)

_LATIN_RE = re.compile(r"[a-z0-9]+")
_CJK_RUN_RE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]+")
_MEDIA_SEARCH_ATTRS = ("title", "artist", "relative_path", "tags")
_XPOST_SEARCH_ATTRS = ("author_screen_name", "author_name", "full_text")

_HOOKS_INSTALLED = False
_FTS_ENGINES: WeakSet = WeakSet()


def _has_fts_table(bind) -> bool:
    if bind is None:
        return False
    if bind in _FTS_ENGINES:
        return True
    try:
        with bind.connect() as conn:
            row = conn.execute(
                text("SELECT 1 FROM sqlite_master WHERE type='table' AND name='media_fts'")
            ).first()
            if row is not None:
                _FTS_ENGINES.add(bind)
                return True
    except Exception:
        return False
    return False


def ensure_fts_table(bind) -> None:
    """Idempotently create the SQLite FTS5 virtual table for media search."""
    if bind is None:
        return
    with bind.begin() as conn:
        conn.execute(
            text(
                "CREATE VIRTUAL TABLE IF NOT EXISTS media_fts "
                "USING fts5(media_id UNINDEXED, content, tokenize='unicode61 remove_diacritics 2')"
            )
        )
    _FTS_ENGINES.add(bind)


def build_index_tokens(parts: Iterable[Optional[str]]) -> str:
    """Expand raw strings into CJK unigrams/bigrams and Latin tokens/trigrams."""
    tokens: list[str] = []
    seen: set[str] = set()

    def add(tok: str) -> None:
        if tok and tok not in seen:
            seen.add(tok)
            tokens.append(tok)

    for raw in parts:
        if not raw:
            continue
        lowered = raw.lower()
        for word in _LATIN_RE.findall(lowered):
            add(word)
            if len(word) >= 3:
                for i in range(len(word) - 2):
                    add(word[i : i + 3])
        for run in _CJK_RUN_RE.findall(lowered):
            for i, ch in enumerate(run):
                add(ch)
                if i + 1 < len(run):
                    add(run[i : i + 2])
    return " ".join(tokens)


def _fts_quote(token: str) -> str:
    escaped = token.replace('"', '""')
    return f'"{escaped}"'


def _variant_fts_clause(variant: str) -> Optional[str]:
    """Return an FTS5 AND-clause for one expanded search variant, or None if unsafe."""
    lowered = variant.strip().lower()
    if not lowered:
        return None
    required: list[str] = []
    covered_chars = 0

    for word in _LATIN_RE.findall(lowered):
        covered_chars += len(word)
        if len(word) < 3:
            # Trigrams only cover >=3-char ASCII words; short ASCII tokens fall back to LIKE.
            return None
        if len(word) == 3:
            required.append(_fts_quote(word))
        else:
            for i in range(len(word) - 2):
                required.append(_fts_quote(word[i : i + 3]))

    for run in _CJK_RUN_RE.findall(lowered):
        covered_chars += len(run)
        if len(run) == 1:
            required.append(_fts_quote(run))
        else:
            for i in range(len(run) - 1):
                required.append(_fts_quote(run[i : i + 2]))

    # If the variant is only punctuation / whitespace / unsupported script, skip FTS.
    if not required or covered_chars == 0:
        return None
    if len(required) == 1:
        return required[0]
    return "(" + " AND ".join(required) + ")"


def build_fts_match_expression(search: Optional[str]) -> Optional[str]:
    """Build a lossless FTS5 MATCH expression matching _apply_media_search_filter."""
    raw = (search or "").strip()
    if not raw:
        return None
    terms = [t for t in raw.split() if t][:6]
    term_clauses: list[str] = []
    for term in terms:
        seed_variants = zh_conv.expand_zh_variants(term) or [term]
        variants = manga_search.expand_query_tokens(seed_variants)[:14] or seed_variants
        variant_clauses: list[str] = []
        for variant in variants:
            clause = _variant_fts_clause(variant)
            if clause is None:
                # One unsafe variant in this term means FTS cannot prove non-match for this term.
                variant_clauses = []
                break
            if clause not in variant_clauses:
                variant_clauses.append(clause)
        if not variant_clauses:
            return None
        if len(variant_clauses) == 1:
            term_clauses.append(variant_clauses[0])
        else:
            term_clauses.append("(" + " OR ".join(variant_clauses) + ")")
    if not term_clauses:
        return None
    return " AND ".join(term_clauses)


def _documents_for_media_ids(db: Session, media_ids: list[int]) -> dict[int, str]:
    if not media_ids:
        return {}
    rows = (
        db.query(models.Media)
        .options(
            selectinload(models.Media.tags),
            selectinload(models.Media.metadata_profile),
        )
        .execution_options(populate_existing=True)
        .filter(models.Media.id.in_(media_ids))
        .all()
    )
    x_rows = (
        db.query(
            models.XMediaItem.library_media_id,
            models.XPost.author_screen_name,
            models.XPost.author_name,
            models.XPost.full_text,
        )
        .join(models.XPost, models.XPost.id == models.XMediaItem.post_id)
        .filter(models.XMediaItem.library_media_id.in_(media_ids))
        .all()
    )
    x_by_media: dict[int, list[str]] = {}
    for media_id, sn, author_name, full_text in x_rows:
        if media_id is None:
            continue
        bucket = x_by_media.setdefault(media_id, [])
        for val in (sn, author_name, full_text):
            if val:
                bucket.append(val)

    docs: dict[int, str] = {}
    for media in rows:
        parts: list[Optional[str]] = [
            media.title,
            media.artist,
            media.relative_path,
            *(tag.name for tag in media.tags),
        ]
        profile = media.metadata_profile
        if profile is not None:
            parts.extend([
                profile.parsed_title,
                profile.parsed_artist,
                profile.parsed_circle,
                profile.parody,
                profile.external_tags,
            ])
        parts.extend(x_by_media.get(media.id, ()))
        docs[media.id] = build_index_tokens(parts)
    return docs


def _session_has_fts_table(session: Session) -> bool:
    bind = session.get_bind()
    if bind is None:
        return False
    if bind in _FTS_ENGINES:
        return True
    try:
        row = session.execute(
            text("SELECT 1 FROM sqlite_master WHERE type='table' AND name='media_fts'")
        ).first()
        if row is not None:
            _FTS_ENGINES.add(bind)
            return True
    except Exception:
        return False
    return False


def sync_media_fts(db: Session, media_ids: Iterable[int]) -> None:
    """Update or remove FTS5 entries for the given media IDs."""
    ids = sorted({int(mid) for mid in media_ids if mid is not None})
    if not ids or not _session_has_fts_table(db):
        return

    for start in range(0, len(ids), 200):
        chunk = ids[start : start + 200]
        docs = _documents_for_media_ids(db, chunk)
        for mid in chunk:
            db.execute(text("DELETE FROM media_fts WHERE media_id = :mid"), {"mid": mid})
            content = docs.get(mid)
            if content is not None:
                db.execute(
                    text("INSERT INTO media_fts(media_id, content) VALUES (:mid, :content)"),
                    {"mid": mid, "content": content},
                )


def rebuild_media_fts(db: Session, *, force: bool = False) -> int:
    """Ensure media_fts exists and matches all rows in media."""
    bind = db.get_bind()
    ensure_fts_table(bind)
    if not force:
        media_count = db.execute(text("SELECT COUNT(*) FROM media")).scalar() or 0
        fts_count = db.execute(text("SELECT COUNT(*) FROM media_fts")).scalar() or 0
        if media_count == fts_count:
            return 0

    db.execute(text("DELETE FROM media_fts"))
    all_ids = [row[0] for row in db.query(models.Media.id).order_by(models.Media.id.asc()).all()]
    for start in range(0, len(all_ids), 200):
        chunk = all_ids[start : start + 200]
        docs = _documents_for_media_ids(db, chunk)
        for mid in chunk:
            content = docs.get(mid)
            if content is not None:
                db.execute(
                    text("INSERT INTO media_fts(media_id, content) VALUES (:mid, :content)"),
                    {"mid": mid, "content": content},
                )
    db.commit()
    return len(all_ids)


def rebuild_media_fts_background(session_factory) -> None:
    """Run incremental/initial FTS backfill in a background startup thread."""
    db = session_factory()
    try:
        synced = rebuild_media_fts(db)
        if synced:
            logger.info("Indexed %d media rows into media_fts", synced)
    except Exception as exc:
        logger.warning("Failed to backfill media_fts: %s", exc)
    finally:
        db.close()


def fts_is_ready(db: Session) -> bool:
    """True when media_fts exists and appears populated."""
    if not _session_has_fts_table(db):
        return False
    try:
        has_fts_rows = db.execute(text("SELECT 1 FROM media_fts LIMIT 1")).first() is not None
        if has_fts_rows:
            return True
        has_media_rows = db.execute(text("SELECT 1 FROM media LIMIT 1")).first() is not None
        return not has_media_rows
    except Exception:
        return False


def _has_attr_changes(obj, attr_names: tuple[str, ...]) -> bool:
    state = sa_inspect(obj)
    for attr_name in attr_names:
        if state.attrs[attr_name].history.has_changes():
            return True
    return False


def install_fts_session_hooks() -> None:
    """Keep media_fts synchronized when ORM models change inside a Session."""
    global _HOOKS_INSTALLED
    if _HOOKS_INSTALLED:
        return

    @event.listens_for(Session, "before_flush")
    def _collect_fts_dirty_ids(session: Session, _flush_context, _instances) -> None:
        if session.info.get("_fts_syncing"):
            return
        if not _session_has_fts_table(session):
            return
        dirty_ids: set[int] = session.info.setdefault("_fts_dirty_ids", set())
        dirty_objs: list[models.Media] = session.info.setdefault("_fts_dirty_objs", [])

        def mark_media(media_obj: models.Media) -> None:
            if media_obj.id is not None:
                dirty_ids.add(media_obj.id)
            else:
                dirty_objs.append(media_obj)

        for obj in session.new:
            if isinstance(obj, models.Media):
                mark_media(obj)
            elif isinstance(obj, models.MangaMetadataProfile) and obj.media_id is not None:
                dirty_ids.add(obj.media_id)
            elif isinstance(obj, models.MangaMetadataProfile) and obj.media is not None:
                mark_media(obj.media)
            elif isinstance(obj, models.XMediaItem) and obj.library_media_id is not None:
                dirty_ids.add(obj.library_media_id)
            elif isinstance(obj, models.Tag):
                for media in obj.media_items:
                    mark_media(media)

        for obj in session.deleted:
            if isinstance(obj, models.Media) and obj.id is not None:
                dirty_ids.add(obj.id)
            elif isinstance(obj, models.MangaMetadataProfile) and obj.media_id is not None:
                dirty_ids.add(obj.media_id)
            elif isinstance(obj, models.XMediaItem) and obj.library_media_id is not None:
                dirty_ids.add(obj.library_media_id)

        for obj in session.dirty:
            if isinstance(obj, models.Media) and _has_attr_changes(obj, _MEDIA_SEARCH_ATTRS):
                mark_media(obj)
            elif isinstance(obj, models.MangaMetadataProfile):
                if obj.media_id is not None:
                    dirty_ids.add(obj.media_id)
                elif obj.media is not None:
                    mark_media(obj.media)
            elif isinstance(obj, models.XMediaItem) and obj.library_media_id is not None:
                dirty_ids.add(obj.library_media_id)
            elif isinstance(obj, models.Tag) and _has_attr_changes(obj, ("name",)):
                for media in obj.media_items:
                    mark_media(media)
            elif isinstance(obj, models.XPost) and obj.id is not None and _has_attr_changes(obj, _XPOST_SEARCH_ATTRS):
                linked = (
                    session.query(models.XMediaItem.library_media_id)
                    .filter(
                        models.XMediaItem.post_id == obj.id,
                        models.XMediaItem.library_media_id.isnot(None),
                    )
                    .all()
                )
                for (mid,) in linked:
                    dirty_ids.add(mid)

        # Collection appends/removals (e.g. media.tags.append(existing_tag)) can
        # mark `media` as having attribute history without putting it in dirty if
        # only the association table changed; check dirty collections via identity_map.
        for obj in list(session.identity_map.values()):
            if isinstance(obj, models.Media) and _has_attr_changes(obj, ("tags",)):
                mark_media(obj)

    @event.listens_for(Session, "after_flush_postexec")
    def _flush_fts_dirty_ids(session: Session, _flush_context) -> None:
        if session.info.get("_fts_syncing"):
            return
        dirty_ids = session.info.pop("_fts_dirty_ids", None) or set()
        dirty_objs = session.info.pop("_fts_dirty_objs", None) or []
        for media_obj in dirty_objs:
            if media_obj.id is not None:
                dirty_ids.add(media_obj.id)
        if not dirty_ids:
            return
        session.info["_fts_syncing"] = True
        try:
            sync_media_fts(session, dirty_ids)
        finally:
            session.info["_fts_syncing"] = False

    @event.listens_for(Session, "after_rollback")
    def _clear_fts_dirty_ids(session: Session) -> None:
        session.info.pop("_fts_dirty_ids", None)
        session.info.pop("_fts_dirty_objs", None)

    _HOOKS_INSTALLED = True
