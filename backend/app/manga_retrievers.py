"""Per-intent retrievers for the RAG router (Phase 3).

Each retriever returns a ranked list of (media_id, score) pairs over the
non-avoided candidate set. The score is meaningful **within** a retriever
but not comparable across retrievers — that's why the caller fuses them
by rank (RRF) instead of by raw score.

Strategies
==========
* by_author   — SQL exact / LIKE against media.artist, metadata.parsed_artist
                and metadata.parsed_circle.
* by_style    — BM25 with cross-lingual ACG synonym expansion + dense vector
                cosine with adaptive threshold.
* similar_to  — Look up the referenced title with fuzzy matching against
                media.title / metadata.parsed_title, then rank neighbours
                using local metadata (artist, circle, parody, IDF-weighted
                tags, title/summary tokens) plus optional cached vectors.
* browse      — Smart discovery blending favorites, ratings, user reading affinity
                (boosting unread works from frequently-read artists), and jitter
                for serendipitous "换一批" exploration.
"""
from __future__ import annotations

import logging
import math
import random
import re
from collections import Counter
from typing import Iterable, Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session, selectinload

from . import manga_search, manga_vector, metadata_enrichment, models, zh_conv

log = logging.getLogger(__name__)

HIDDEN_DUPLICATE_STATUSES = {"checking", "strong_duplicate", "suspected_duplicate", "dedup_excluded"}

VECTOR_POOL = 60
VECTOR_MIN_SIMILARITY = 0.30
VECTOR_GAP_OVER_P90 = 0.10
VECTOR_MIN_MAX_OVER_P90 = 0.05


def visible_manga(db: Session) -> list[models.Media]:
    """All manga rows the recommender is allowed to consider."""
    return (
        db.query(models.Media)
        .options(
            selectinload(models.Media.tags),
            selectinload(models.Media.ai_profile),
            selectinload(models.Media.metadata_profile),
        )
        .filter(
            models.Media.media_type == "manga",
            models.Media.is_missing == False,  # noqa: E712
            models.Media.duplicate_status.notin_(list(HIDDEN_DUPLICATE_STATUSES)),
        )
        .all()
    )


# --- by_author --------------------------------------------------------------

def by_author(
    db: Session,
    artists: Iterable[str],
    candidates: list[models.Media],
) -> list[tuple[int, float]]:
    """Match candidates against any of the user-named artists."""
    targets = [str(a).strip().lower() for a in artists if str(a).strip()]
    if not targets:
        return []

    out: list[tuple[int, float, float]] = []  # (id, score, tiebreak_prior)
    for media in candidates:
        stored_names = _all_artist_aliases(media)
        if not stored_names:
            continue
        best = 0.0
        for target in targets:
            for name in stored_names:
                if not name:
                    continue
                if name == target:
                    best = max(best, 1.0)
                    break
                if target in name or name in target:
                    best = max(best, 0.8)
            if best >= 1.0:
                break
        if best <= 0:
            continue
        tiebreak = float(media.rating or 0) + (1.0 if media.favorite else 0.0)
        out.append((media.id, best, tiebreak))

    out.sort(key=lambda x: (x[1], x[2], x[0]), reverse=True)
    return [(mid, s) for mid, s, _ in out]


def _all_artist_aliases(media: models.Media) -> list[str]:
    """Every artist/circle string we have for a manga, lowercased."""
    names: list[str] = []
    if media.artist:
        names.append(media.artist.strip().lower())
    metadata = media.metadata_profile
    if metadata:
        if metadata.parsed_artist:
            names.append(metadata.parsed_artist.strip().lower())
        if metadata.parsed_circle:
            names.append(metadata.parsed_circle.strip().lower())
    # dedupe preserving order
    seen: set[str] = set()
    out: list[str] = []
    for n in names:
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return out


def _compute_reading_affinity(candidates: list[models.Media]) -> dict[str, float]:
    """Compute affinity score for artists based on user's read history."""
    read_counts = Counter()
    for m in candidates:
        if m.view_status in ("viewed", "viewing"):
            for a in _all_artist_aliases(m):
                read_counts[a] += 1
    # 1 work read -> +6.0, 2 works -> +12.0, max +24.0
    return {a: min(c * 6.0, 24.0) for a, c in read_counts.items()}


# --- by_style ---------------------------------------------------------------

def by_style(
    candidates: list[models.Media],
    query_terms: Iterable[str],
    avoid_tokens: list[str],
) -> tuple[list[tuple[int, float]], list[tuple[int, float]], dict[int, list[str]]]:
    """Hybrid BM25 + dense vector retrieval for theme / vibe queries."""
    tokens: list[str] = []
    for term in query_terms:
        tokens.extend(manga_search.tokenize(term))

    # Expand query tokens with ACG tropes and cross-lingual synonyms
    tokens = manga_search.expand_query_tokens(tokens)

    seen: set[str] = set()
    positive_tokens: list[str] = []
    for t in tokens:
        if t and t not in seen:
            seen.add(t)
            positive_tokens.append(t)

    if not positive_tokens:
        return [], [], {}

    # Build field tokens + IDF over the candidate set
    field_tokens_by_id = {m.id: manga_search.build_field_tokens(m) for m in candidates}
    idf = manga_search.compute_idf(field_tokens_by_id)

    # BM25 pass (with avoid filter)
    bm25_scored: list[tuple[int, float]] = []
    matched_tags: dict[int, list[str]] = {}
    for media in candidates:
        fields = field_tokens_by_id[media.id]
        if avoid_tokens and manga_search.avoid_hit(fields, avoid_tokens):
            continue
        text_score, matched = manga_search.score_text_match(fields, positive_tokens, idf)
        if text_score > 0:
            bm25_scored.append((media.id, text_score))
            matched_tags[media.id] = matched
    bm25_scored.sort(key=lambda x: x[1], reverse=True)

    # Vector pass — gated on BM25 finding *something*
    if not bm25_scored:
        return [], [], {}

    surviving_ids = {m.id for m in candidates}
    if avoid_tokens:
        avoided_ids = {
            m.id for m in candidates
            if manga_search.avoid_hit(field_tokens_by_id[m.id], avoid_tokens)
        }
        surviving_ids -= avoided_ids
    vec_ranks = _vector_pass(candidates, positive_tokens, surviving_ids)

    return bm25_scored, vec_ranks, matched_tags


def _vector_pass(
    candidates: list[models.Media],
    positive_tokens: list[str],
    surviving_ids: set[int],
) -> list[tuple[int, float]]:
    """Dense embedding retrieval with adaptive threshold."""
    try:
        import numpy as np
        query_text = " ".join(positive_tokens)[:512]
        query_vec = manga_vector.encode_query(query_text)
        if query_vec is None:
            return []

        profiles = [m.ai_profile for m in candidates
                    if m.ai_profile and m.id in surviving_ids]
        pairs = manga_vector.load_candidate_vectors(profiles)
        if not pairs:
            return []

        all_ranked = manga_vector.rank_by_query(query_vec, pairs, top_k=len(pairs))
        if not all_ranked:
            return []

        sims = np.array([sim for _, sim in all_ranked])
        if len(sims) >= 10:
            top_sim = float(sims.max())
            p90 = float(np.percentile(sims, 90))
            if top_sim - p90 < VECTOR_MIN_MAX_OVER_P90:
                log.debug("by_style vector: weak signal (gap=%.3f < %.3f), skipping",
                          top_sim - p90, VECTOR_MIN_MAX_OVER_P90)
                return []
            threshold = max(VECTOR_MIN_SIMILARITY, p90 + VECTOR_GAP_OVER_P90)
        else:
            threshold = VECTOR_MIN_SIMILARITY

        return [(mid, sim) for mid, sim in all_ranked[:VECTOR_POOL] if sim >= threshold]
    except Exception as exc:  # noqa: BLE001
        log.warning("by_style vector retrieval failed: %s", exc)
        return []


# --- similar_to -------------------------------------------------------------

SIMILAR_MIN_SCORE = 0.12
_GENERIC_PARODIES = {"original", "オリジナル", "原创", "原創", "none", "n/a"}
_SIMILAR_IGNORED_NAMESPACES = {"artist", "circle", "parody", "language", "length"}
_SIMILAR_NOISE_TAGS = {
    "dl版", "中文", "汉化", "漢化", "无修正", "無修正", "chinese", "translated",
    "digital", "中国翻訳", "中国語", "日本語", "japanese", "english",
}


def _artist_set(media: models.Media) -> set[str]:
    out: set[str] = set()
    if media.artist and media.artist.strip():
        out.add(media.artist.strip().lower())
    metadata = media.metadata_profile
    if metadata and metadata.parsed_artist and metadata.parsed_artist.strip():
        out.add(metadata.parsed_artist.strip().lower())
    for tag in media.tags or ():
        if (tag.namespace or "").strip().lower() == "artist" and tag.name and tag.name.strip():
            out.add(tag.name.strip().lower())
    return out


def _circle_set(media: models.Media) -> set[str]:
    out: set[str] = set()
    metadata = media.metadata_profile
    if metadata and metadata.parsed_circle and metadata.parsed_circle.strip():
        out.add(metadata.parsed_circle.strip().lower())
    for tag in media.tags or ():
        if (tag.namespace or "").strip().lower() == "circle" and tag.name and tag.name.strip():
            out.add(tag.name.strip().lower())
    return out


def _parody_set(media: models.Media) -> set[str]:
    raw: list[str] = []
    metadata = media.metadata_profile
    if metadata and metadata.parody and metadata.parody.strip():
        raw.append(metadata.parody)
    for tag in media.tags or ():
        if (tag.namespace or "").strip().lower() == "parody" and tag.name and tag.name.strip():
            raw.append(tag.name)
    out: set[str] = set()
    for entry in raw:
        for part in re.split(r"[,/、&]+", entry):
            cleaned = zh_conv.to_simplified(part.strip()).lower()
            if cleaned and cleaned not in _GENERIC_PARODIES:
                out.add(cleaned)
    return out


def _is_noise_similar_tag(name: str, namespace: Optional[str] = None) -> bool:
    ns = (namespace or "").strip().lower()
    if ns in _SIMILAR_IGNORED_NAMESPACES:
        return True
    cleaned = name.strip().lower()
    if not cleaned or cleaned in _SIMILAR_NOISE_TAGS:
        return True
    if cleaned.startswith(("language:", "length:", "artist:", "circle:", "parody:", "category:")):
        return True
    if metadata_enrichment._is_noise_tag(cleaned, ns or "general"):
        return True
    return False


def _content_tag_set(media: models.Media) -> set[str]:
    out: set[str] = set()
    for tag in media.tags or ():
        if tag.name and not _is_noise_similar_tag(tag.name, tag.namespace):
            out.add(zh_conv.to_simplified(tag.name.strip()).lower())
    metadata = media.metadata_profile
    if metadata and metadata.external_tags:
        for item in manga_search._json_list(metadata.external_tags):
            if not _is_noise_similar_tag(item):
                out.add(zh_conv.to_simplified(item.strip()).lower())
    profile = media.ai_profile
    if profile:
        for raw in (profile.style_tags, profile.story_tags, profile.tone_tags):
            for item in manga_search._json_list(raw):
                if not _is_noise_similar_tag(item):
                    out.add(zh_conv.to_simplified(item.strip()).lower())
    return out


def _similar_text_tokens(media: models.Media) -> set[str]:
    tokens = (
        manga_search._tokens_from_text(manga_search._title_field(media))
        | manga_search._tokens_from_text(manga_search._summary_field(media))
    )
    return {t for t in tokens if t and not _is_noise_similar_tag(t)}


def _compute_set_idf(sets_by_id: dict[int, set[str]]) -> dict[str, float]:
    n_docs = len(sets_by_id) or 1
    df: dict[str, int] = {}
    for tokens in sets_by_id.values():
        for token in tokens:
            df[token] = df.get(token, 0) + 1
    return {
        token: math.log(1.0 + (n_docs - count + 0.5) / (count + 0.5))
        for token, count in df.items()
    }


def _weighted_cosine(left: set[str], right: set[str], idf: dict[str, float]) -> tuple[float, int]:
    if not left or not right:
        return 0.0, 0
    shared = left & right
    if not shared:
        return 0.0, 0
    num = sum(idf.get(t, 1.0) for t in shared)
    den_left = sum(idf.get(t, 1.0) for t in left)
    den_right = sum(idf.get(t, 1.0) for t in right)
    if den_left <= 0 or den_right <= 0:
        return 0.0, 0
    return num / math.sqrt(den_left * den_right), len(shared)


def similar_to(
    db: Session,
    referenced_title: str,
    candidates: list[models.Media],
    surviving_ids: Optional[set[int]] = None,
) -> tuple[Optional[models.Media], list[tuple[int, float]]]:
    """Find a referenced manga, then rank neighbours by local metadata + optional cached vectors."""
    if not referenced_title or not referenced_title.strip():
        return None, []

    # Resolve the referenced manga via fuzzy SQL LIKE on title/parsed_title
    target_variants = [v.lower() for v in zh_conv.expand_zh_variants(referenced_title) if v.strip()]
    if not target_variants:
        target_variants = [referenced_title.strip().lower()]
    title_clauses = []
    for variant in target_variants[:4]:
        title_clauses.append(func.lower(models.Media.title).like(f"%{variant}%"))
        title_clauses.append(func.lower(models.MangaMetadataProfile.parsed_title).like(f"%{variant}%"))
    referenced = (
        db.query(models.Media)
        .options(
            selectinload(models.Media.tags),
            selectinload(models.Media.ai_profile),
            selectinload(models.Media.metadata_profile),
        )
        .outerjoin(models.MangaMetadataProfile)
        .filter(
            models.Media.media_type == "manga",
            models.Media.is_missing == False,  # noqa: E712
            or_(*title_clauses),
        )
        .order_by(models.Media.id.asc())
        .first()
    )
    if not referenced:
        log.debug("similar_to: no manga matches title hint %r", referenced_title)
        return None, []

    pool = [
        m for m in candidates
        if m.id != referenced.id and (surviving_ids is None or m.id in surviving_ids)
    ]
    if not pool:
        return referenced, []

    ref_artists = _artist_set(referenced)
    ref_circles = _circle_set(referenced)
    ref_parodies = _parody_set(referenced)

    all_docs = [referenced] + pool
    tag_sets = {m.id: _content_tag_set(m) for m in all_docs}
    text_sets = {m.id: _similar_text_tokens(m) for m in all_docs}
    tag_idf = _compute_set_idf(tag_sets)
    text_idf = _compute_set_idf(text_sets)

    ref_tags = tag_sets[referenced.id]
    ref_text = text_sets[referenced.id]

    vec_sims: dict[int, float] = {}
    if referenced.ai_profile and referenced.ai_profile.embedding:
        target_vec = manga_vector.deserialize_vec(referenced.ai_profile.embedding)
        if target_vec is not None:
            profiles = [m.ai_profile for m in pool if m.ai_profile and m.ai_profile.embedding]
            pairs = manga_vector.load_candidate_vectors(profiles)
            if pairs:
                for mid, vsim in manga_vector.rank_by_query(target_vec, pairs, top_k=len(pairs)):
                    if vsim >= 0.40:
                        vec_sims[mid] = vsim

    scored: list[tuple[int, float, float]] = []
    for media in pool:
        sim = 0.0
        if ref_artists and (_artist_set(media) & ref_artists):
            sim += 0.40
        if ref_circles and (_circle_set(media) & ref_circles):
            sim += 0.25
        if ref_parodies and (_parody_set(media) & ref_parodies):
            sim += 0.30

        tag_cos, shared_tag_count = _weighted_cosine(ref_tags, tag_sets[media.id], tag_idf)
        if tag_cos > 0 and shared_tag_count > 0:
            sim += 0.55 * tag_cos * min(1.0, shared_tag_count / 2.0)

        text_cos, shared_text_count = _weighted_cosine(ref_text, text_sets[media.id], text_idf)
        if text_cos > 0 and shared_text_count > 0:
            sim += 0.25 * text_cos

        vsim = vec_sims.get(media.id)
        if vsim is not None:
            sim += 0.45 * vsim

        sim = min(1.0, sim)
        if sim < SIMILAR_MIN_SCORE:
            continue

        tiebreak = float(media.rating or 0) + (1.0 if media.favorite else 0.0)
        scored.append((media.id, round(sim, 4), tiebreak))

    scored.sort(key=lambda item: (item[1], item[2], item[0]), reverse=True)
    return referenced, [(mid, s) for mid, s, _ in scored[:VECTOR_POOL]]


# --- browse -----------------------------------------------------------------

def browse(
    candidates: list[models.Media],
    avoid_tokens: list[str],
    seed: Optional[int] = None,
) -> list[tuple[int, float]]:
    """Smart discovery ranking blending favorites, ratings, and user reading affinity.

    Scores are boosted for:
      - favorite: +50
      - rating: rating * 10 (0..50)
      - unread works by user's top-read artists: up to +24 affinity bonus
      - unviewed vs viewing vs viewed status: prioritizing unread discoveries
      - jitter: pseudo-random noise to shuffle candidates on "换一批"
    """
    if avoid_tokens:
        field_tokens_by_id = {m.id: manga_search.build_field_tokens(m) for m in candidates}
        candidates = [
            m for m in candidates
            if not manga_search.avoid_hit(field_tokens_by_id[m.id], avoid_tokens)
        ]

    artist_affinity = _compute_reading_affinity(candidates)
    rng = random.Random(seed) if seed is not None else random.Random()

    scored: list[tuple[int, float]] = []
    for media in candidates:
        score = 0.0
        if media.favorite:
            score += 50.0
        score += (media.rating or 0) * 10.0

        aliases = _all_artist_aliases(media)
        best_affinity = max([artist_affinity.get(a, 0.0) for a in aliases] or [0.0])

        if media.view_status == "unviewed":
            score += 15.0 + best_affinity
        elif media.view_status == "viewing":
            score += 8.0 + (best_affinity * 0.5)
        else:  # viewed
            score -= 10.0

        # Jitter so rerolling shuffles while respecting score strata
        score += rng.uniform(0.0, 10.0)

        # Freshness tiebreak: tiny bump for higher id
        score += min((media.id or 0) / 1_000_000.0, 0.001)
        scored.append((media.id, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored
