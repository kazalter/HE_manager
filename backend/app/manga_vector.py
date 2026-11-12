"""Read historical manga vectors without loading an embedding model.

New profiles no longer generate embeddings. Existing vectors remain available
for similarity lookup; keyword retrieval handles ordinary recommendations.
"""
from __future__ import annotations

import logging
import threading
from typing import Iterable, Optional

import numpy as np

from . import models

log = logging.getLogger(__name__)

# A multilingual model that handles the JP/ZH/EN mix typical of doujin
# titles. 384 dims, ~117MB on disk. If you ever swap this:
#   1) bump the constant
#   2) every row's `embedding_model` will then disagree -> it's effectively a
#      cache invalidation; backfill_embeddings.py re-encodes everything.
MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
VECTOR_DIM = 384

_model = None
_model_failed = False
_model_lock = threading.Lock()


def is_model_cached() -> bool:
    """Check if the embedding model weights exist in local cache directory."""
    import os
    for env_var in ("HF_HOME", "SENTENCE_TRANSFORMERS_HOME"):
        path = os.environ.get(env_var)
        if path and os.path.isdir(path):
            for root, dirs, files in os.walk(path):
                if any("MiniLM" in d or "model.safetensors" in f or "pytorch_model.bin" in f for d in dirs for f in files):
                    return True
                if any("model.safetensors" in f or "pytorch_model.bin" in f for f in files):
                    return True
    return False


def get_model():
    """Dense encoding is disabled; retain existing vectors for similarity lookup."""
    return _model


# --- text composition ------------------------------------------------------

def _json_list(value: Optional[str]) -> list[str]:
    """Permissive JSON-array parse — matches manga_search's helper."""
    import json

    if not value:
        return []
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed if str(item).strip()]


def compose_doc_text(media: models.Media) -> str:
    """Build the canonical text we embed for a single manga."""
    parts: list[str] = []

    if media.title:
        parts.append(media.title)

    metadata = media.metadata_profile
    if metadata:
        if metadata.parsed_title and metadata.parsed_title != media.title:
            parts.append(metadata.parsed_title)
        if metadata.parsed_artist:
            parts.append(f"作者：{metadata.parsed_artist}")
        if metadata.parsed_circle:
            parts.append(f"社团：{metadata.parsed_circle}")
        if metadata.parody:
            parts.append(f"原作：{metadata.parody}")
        if metadata.language:
            parts.append(f"语言：{metadata.language}")
        external_tags = _json_list(metadata.external_tags)
        if external_tags:
            parts.append("标签：" + "、".join(external_tags[:20]))
    elif media.artist:
        parts.append(f"作者：{media.artist}")

    tag_names = [t.name for t in media.tags]
    if tag_names:
        parts.append("标签：" + "、".join(tag_names[:20]))

    profile = media.ai_profile
    if profile:
        if profile.content_summary:
            parts.append(profile.content_summary[:300])
        style = _json_list(profile.style_tags)
        if style:
            parts.append("画风：" + "、".join(style[:8]))
        story = _json_list(profile.story_tags)
        if story:
            parts.append("题材：" + "、".join(story[:8]))
        tone = _json_list(profile.tone_tags)
        if tone:
            parts.append("氛围：" + "、".join(tone[:8]))

    return "  ".join(parts).strip()


# --- encoding / serialisation ---------------------------------------------

def encode_text(text: str) -> Optional[np.ndarray]:
    """Encode one string to a normalised float32 vector of shape (VECTOR_DIM,)."""
    model = get_model()
    if model is None:
        return None
    try:
        vec = model.encode(text or "", normalize_embeddings=True)
        return np.asarray(vec, dtype=np.float32).reshape(-1)
    except Exception as exc:
        log.warning("encode_text failed: %s", exc)
        return None


def encode_batch(texts: list[str]) -> np.ndarray:
    """Encode many strings; returns shape (N, VECTOR_DIM), normalised."""
    model = get_model()
    if model is None or not texts:
        return np.zeros((0, VECTOR_DIM), dtype=np.float32)
    try:
        vecs = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return np.asarray(vecs, dtype=np.float32)
    except Exception as exc:
        log.warning("encode_batch failed: %s", exc)
        return np.zeros((0, VECTOR_DIM), dtype=np.float32)


def encode_query(query: str) -> Optional[np.ndarray]:
    """Alias of encode_text — returns None when model is unavailable."""
    return encode_text(query)


def serialize_vec(vec: np.ndarray) -> bytes:
    """ndarray -> bytes for storage in the embedding BLOB column."""
    return np.asarray(vec, dtype=np.float32).reshape(-1).tobytes()


def deserialize_vec(blob: bytes, dim: int = VECTOR_DIM) -> Optional[np.ndarray]:
    """Bytes -> ndarray. Returns None if the blob is wrong size for `dim`."""
    if not blob:
        return None
    arr = np.frombuffer(blob, dtype=np.float32)
    if arr.shape[0] != dim:
        return None
    return arr


# --- retrieval -------------------------------------------------------------

def rank_by_query(
    query_vec: np.ndarray,
    candidates: Iterable[tuple[int, np.ndarray]],
    top_k: int = 80,
) -> list[tuple[int, float]]:
    """Cosine top-K over (media_id, vec) candidates."""
    items = list(candidates)
    if not items or query_vec is None:
        return []
    ids = np.array([mid for mid, _ in items], dtype=np.int64)
    matrix = np.stack([vec for _, vec in items], axis=0)
    sims = matrix @ query_vec.astype(np.float32).reshape(-1)
    order = np.argsort(-sims)[: max(1, top_k)]
    return [(int(ids[i]), float(sims[i])) for i in order]


def load_candidate_vectors(
    profiles: Iterable[models.MangaAIProfile],
    dim: int = VECTOR_DIM,
    model_name: str = MODEL_NAME,
) -> list[tuple[int, np.ndarray]]:
    """Pull (media_id, vec) pairs from MangaAIProfile rows with valid embedding."""
    out: list[tuple[int, np.ndarray]] = []
    for profile in profiles:
        if not profile.embedding:
            continue
        if profile.embedding_model and profile.embedding_model != model_name:
            continue
        vec = deserialize_vec(profile.embedding, dim=dim)
        if vec is None:
            continue
        out.append((profile.media_id, vec))
    return out
