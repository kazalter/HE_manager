"""Token-based ranking for manga recommendations.

Replaces the previous substring-on-blob matching in recommendations.py with
field-weighted token matching + IDF rarity boost. Conceptually BM25-lite:

- tokenize CJK with jieba when available, else fall back to char-unigrams +
  bigrams so two-character Chinese words still hit;
- build per-media token sets for several *named* fields (tag, meta_tag,
  profile keyword, parody, artist, title, summary) so we can weight them
  separately and never let OCR text or generative summaries dominate;
- IDF over the candidate corpus so rare terms (e.g. an obscure parody name)
  outweigh common ones (e.g. "短篇");
- avoid terms are only checked against the *high-signal* fields (tag /
  meta_tag / parody / artist / title) — never summary or AI-generated text,
  which previously caused false-positive filtering.
- cross-lingual ACG synonym expansion for common Chinese/Japanese tropes.

Public API:
    tokenize(text)           -> list[str]
    expand_query_tokens(tokens) -> list[str]
    build_field_tokens(media) -> dict[str, set[str]]
    compute_idf(by_media)    -> dict[str, float]
    score_text_match(fields, query_tokens, idf) -> (score, matched_terms)
    avoid_hit(fields, avoid_tokens) -> bool
"""
from __future__ import annotations

import json
import math
import re
from typing import Iterable, Optional

from . import models


def _json_list(value: Optional[str]) -> list[str]:
    """Permissive parse: bad JSON or non-list returns []."""
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed if str(item).strip()]

try:  # jieba is optional — install for better CJK tokenization
    import jieba  # type: ignore

    _HAS_JIEBA = True
    jieba.setLogLevel(60)  # quiet
except ImportError:
    _HAS_JIEBA = False


# Field weights. Higher = stronger evidence the manga is what the user asked
# for. Tuned so a tag hit dominates a title-only hit, but title still beats
# "the AI summary mentions the word once".
FIELD_WEIGHTS: dict[str, float] = {
    "tag": 5.0,
    "meta_tag": 3.5,
    "profile_kw": 3.0,
    "parody": 2.5,
    "artist": 2.5,
    "title": 2.0,
    "summary": 0.8,
}

# Fields consulted when filtering by avoid_terms. Deliberately excludes
# `summary` and `profile_kw` (LLM-generated, noisy) and OCR (never indexed).
AVOID_FIELDS: tuple[str, ...] = ("tag", "meta_tag", "parody", "artist", "title")

_LATIN_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9_+\-]*")

# Cross-lingual synonym and trope expansion mapping.
# Maps common user query terms (in Simplified Chinese) to Japanese doujinshi,
# kanji, katakana, and alias terms commonly present in manga titles and metadata.
ACG_SYNONYM_MAP: dict[str, list[str]] = {
    # 题材 / 人设 / 角色关系
    "青梅竹马": ["幼馴染", "幼なじみ", "青梅", "自幼"],
    "青梅": ["幼馴染", "幼なじみ", "青梅", "自幼"],
    "幼驯染": ["幼馴染", "幼なじみ", "青梅竹马"],
    "大姐姐": ["お姉さん", "お姉ちゃん", "姉", "年上", "姐姐"],
    "姐": ["お姉さん", "お姉ちゃん", "姉", "年上"],
    "姐姐": ["お姉さん", "お姉ちゃん", "姉", "年上"],
    "妹妹": ["妹", "いもうと", "義妹"],
    "学姐": ["先輩", "せんぱい", "学姐"],
    "前辈": ["先輩", "せんぱい"],
    "学妹": ["後輩", "こうはい", "学妹"],
    "后辈": ["後輩", "こうはい"],
    "同级生": ["同級生", "同学"],
    "同学": ["同級生", "同学"],
    "老师": ["先生", "女教師", "教师", "老师"],
    "教师": ["先生", "女教師", "教师"],
    "女仆": ["メイド", "女仆"],
    "女仆装": ["メイド", "女仆"],
    "兔女郎": ["バニー", "バニーガール", "兔女郎"],
    "辣妹": ["ギャル", "辣妹", "黒ギャル"],
    "纯爱": ["純愛", "恋", "愛", "好き", "カノジョ", "彼女", "恋人", "初恋"],
    "恋爱": ["純愛", "恋", "愛", "好き", "カノジョ", "彼女", "恋人"],
    "治愈": ["癒", "明亮", "温馨", "癒し", "日常", "温もり"],
    "日常": ["日常", "ほのぼの"],
    "催眠": ["催眠", "洗脳"],
    "触手": ["触手"],
    "寝取": ["寝取", "ntr", "NTR"],
    "牛头人": ["寝取", "ntr", "NTR"],
    "巨乳": ["巨乳", "爆乳", "おっぱい"],
    "贫乳": ["貧乳", "ロリ"],
    "萝莉": ["ロリ", "幼女"],
    "泳装": ["水着", "泳装", "プール", "海"],
    "温泉": ["温泉", "露天風呂"],
    "浴衣": ["浴衣", "着物", "和服"],
    "和服": ["浴衣", "着物", "和服"],
    "全彩": ["full color", "color", "カラー", "全彩", "彩色感强"],
    "彩色": ["full color", "color", "カラー", "全彩", "彩色感强"],
    "短篇": ["短篇", "length:短篇", "文字较少"],
    "中篇": ["中篇", "length:中篇"],
    "长篇": ["长篇", "length:长篇"],
    "无修": ["無修正", "无修"],
    "无修正": ["無修正"],
    # 热门 IP / 同人
    "碧蓝档案": ["ブルーアーカイブ", "ブルアカ", "blue archive", "蔚蓝档案"],
    "蔚蓝档案": ["ブルーアーカイブ", "ブルアカ", "blue archive"],
    "原神": ["原神", "genshin"],
    "明日方舟": ["アークナイツ", "明日方舟", "arknights"],
    "偶像大师": ["アイドルマスター", "アイマス"],
}


def expand_query_tokens(tokens: Iterable[str]) -> list[str]:
    """Broaden query tokens with ACG tropes and cross-lingual synonyms."""
    out: list[str] = []
    seen: set[str] = set()

    for token in tokens:
        if not token:
            continue
        t_clean = token.strip()
        t_lower = t_clean.lower()
        if t_lower not in seen:
            seen.add(t_lower)
            out.append(t_clean)

        # Direct map hit
        if t_lower in ACG_SYNONYM_MAP:
            for syn in ACG_SYNONYM_MAP[t_lower]:
                s_lower = syn.lower()
                if s_lower not in seen:
                    seen.add(s_lower)
                    out.append(syn)
        else:
            # Substring / partial key hit
            for key, syns in ACG_SYNONYM_MAP.items():
                if key in t_lower or (len(t_lower) >= 2 and t_lower in key):
                    for syn in syns:
                        s_lower = syn.lower()
                        if s_lower not in seen:
                            seen.add(s_lower)
                            out.append(syn)
    return out


# Tokens that show up as filler in free-form queries. Stripped before
# scoring so they don't drag IDF down or produce noise hits.
_STOPWORDS: frozenset[str] = frozenset({
    # zh — verbs / fillers
    "想看", "想要", "推荐", "一点", "一些", "看看", "求", "的", "了",
    "请", "帮我", "找", "类似", "类型", "看", "想", "有", "没有", "是",
    "随便", "随意", "任意", "不知道", "看点",
    # zh — generic catalog nouns
    "漫画", "作品", "本子", "本", "图", "图片", "图集", "故事",
    # zh — meta slot names (NOT content)
    "作者", "画师", "画家", "社团", "标签",
    # zh — pronouns / determiners
    "我", "你", "他", "她", "它", "这", "那", "这个", "那个", "这种", "那种",
    "哪", "哪个", "什么", "怎么", "谁",
    # ja — common fillers
    "おすすめ", "好き", "もの", "こと",
    "系", "向", "派", "型", "風", "风",
    # en
    "want", "like", "recommend", "manga", "comic", "find", "show",
    "please", "give", "looking",
    "i", "me", "my", "you", "the", "a", "an", "of", "for", "with",
})


def _is_cjk(ch: str) -> bool:
    return "぀" <= ch <= "ヿ" or "㐀" <= ch <= "鿿"


def _cjk_ngrams(s: str) -> list[str]:
    """Unigrams + bigrams over a pure-CJK run. Used when jieba is unavailable."""
    out: list[str] = []
    if len(s) >= 1:
        out.extend(s)
    for i in range(len(s) - 1):
        out.append(s[i:i + 2])
    return out


def tokenize(text: Optional[str]) -> list[str]:
    """Lowercase + tokenize. Returns a flat list (may contain duplicates)."""
    if not text:
        return []
    text = text.lower()
    tokens: list[str] = []

    # Latin / digit / hyphenated identifier
    tokens.extend(m.group(0) for m in _LATIN_TOKEN_RE.finditer(text))

    # Group consecutive CJK characters into runs, then tokenize each run
    run: list[str] = []
    for ch in text:
        if _is_cjk(ch):
            run.append(ch)
            continue
        if run:
            tokens.extend(_tokenize_cjk_run("".join(run)))
            run = []
    if run:
        tokens.extend(_tokenize_cjk_run("".join(run)))

    # Filter stopwords and 1-char Latin (CJK 1-chars are kept as anchors)
    out: list[str] = []
    for t in tokens:
        if not t or t in _STOPWORDS:
            continue
        if len(t) == 1 and not _is_cjk(t):
            continue
        out.append(t)
    return out


def _tokenize_cjk_run(run: str) -> list[str]:
    if _HAS_JIEBA:
        cut = [t.strip() for t in jieba.cut(run, HMM=True)]
        return [t for t in cut if t]
    return _cjk_ngrams(run)


def _tokens_from_items(items: Iterable[str]) -> set[str]:
    """Tokenize each item AND keep the lowercased whole as an exact-match key."""
    out: set[str] = set()
    for raw in items:
        if not raw:
            continue
        s = str(raw).strip()
        if not s:
            continue
        out.update(tokenize(s))
        out.add(s.lower())
    return out


def _tokens_from_text(text: Optional[str]) -> set[str]:
    if not text:
        return set()
    out: set[str] = set(tokenize(text))
    s = text.strip().lower()
    if s:
        out.add(s)

    # Extract Japanese Katakana words (e.g. ブルーアーカイブ, メイド, バニー)
    for k in re.findall(r"[\u30a0-\u30ffー]{2,}", text):
        out.add(k.lower())

    # Extract bracketed segments: [Circle], (Parody)
    for b in re.findall(r"\[([^\]]+)\]|\(([^)]+)\)|（([^）]+)）|【([^】]+)】", text):
        for part in b:
            if part and len(part.strip()) > 1:
                cleaned = part.strip().lower()
                out.add(cleaned)
                out.update(tokenize(cleaned))
    return out


def _tag_field(media: models.Media) -> list[str]:
    return [t.name for t in media.tags]


def _meta_tag_field(media: models.Media) -> list[str]:
    metadata = media.metadata_profile
    if not metadata:
        return []
    return _json_list(metadata.external_tags)


def _profile_kw_field(media: models.Media) -> list[str]:
    profile = media.ai_profile
    if not profile:
        return []
    out: list[str] = []
    for raw in (profile.style_tags, profile.story_tags, profile.tone_tags, profile.recommendation_keywords):
        out.extend(_json_list(raw))
    return out


def _parody_field(media: models.Media) -> str:
    parts: list[str] = []
    metadata = media.metadata_profile
    if metadata and metadata.parody:
        parts.append(metadata.parody)
    if media.title:
        for match in re.finditer(r"\(([^)]+)\)|（([^）]+)）", media.title):
            p = match.group(1) or match.group(2)
            if p and len(p.strip()) > 1:
                parts.append(p.strip())
    return " ".join(parts)


def _artist_field(media: models.Media) -> str:
    parts: list[str] = []
    if media.artist:
        parts.append(media.artist)
    metadata = media.metadata_profile
    if metadata:
        if metadata.parsed_artist:
            parts.append(metadata.parsed_artist)
        if metadata.parsed_circle:
            parts.append(metadata.parsed_circle)
    return " ".join(parts)


def _title_field(media: models.Media) -> str:
    parts: list[str] = []
    if media.title:
        parts.append(media.title)
    metadata = media.metadata_profile
    if metadata and metadata.parsed_title and metadata.parsed_title != media.title:
        parts.append(metadata.parsed_title)
    return " ".join(parts)


def _summary_field(media: models.Media) -> str:
    parts: list[str] = []
    profile = media.ai_profile
    if profile and profile.content_summary:
        parts.append(profile.content_summary)
    metadata = media.metadata_profile
    if metadata and metadata.external_summary:
        parts.append(metadata.external_summary)
    return " ".join(parts)


def build_field_tokens(media: models.Media) -> dict[str, set[str]]:
    return {
        "tag": _tokens_from_items(_tag_field(media)),
        "meta_tag": _tokens_from_items(_meta_tag_field(media)),
        "profile_kw": _tokens_from_items(_profile_kw_field(media)),
        "parody": _tokens_from_text(_parody_field(media)),
        "artist": _tokens_from_items(filter(None, _artist_field(media).split())),
        "title": _tokens_from_text(_title_field(media)),
        "summary": _tokens_from_text(_summary_field(media)),
    }


def compute_idf(field_tokens_by_media: dict[int, dict[str, set[str]]]) -> dict[str, float]:
    """Standard plus-one-smoothed IDF over the union of every field's tokens."""
    n_docs = len(field_tokens_by_media) or 1
    doc_freq: dict[str, int] = {}
    for fields in field_tokens_by_media.values():
        seen: set[str] = set()
        for tokens in fields.values():
            seen.update(tokens)
        for token in seen:
            doc_freq[token] = doc_freq.get(token, 0) + 1
    return {
        token: math.log(1 + (n_docs - df + 0.5) / (df + 0.5))
        for token, df in doc_freq.items()
    }


def score_text_match(
    fields: dict[str, set[str]],
    query_tokens: Iterable[str],
    idf: dict[str, float],
) -> tuple[float, list[str]]:
    """Sum weighted hits across fields, multiplied by per-token IDF."""
    score = 0.0
    matched: list[str] = []
    seen_terms: set[str] = set()

    for token in query_tokens:
        if not token:
            continue
        token_lower = token.lower()
        token_weight = 0.0
        hit = False

        for field, weight in FIELD_WEIGHTS.items():
            field_tokens = fields.get(field, set())
            if token in field_tokens or token_lower in field_tokens:
                token_weight += weight
                hit = True
            elif len(token_lower) >= 2:
                # Substring matching against field tokens
                for f_token in field_tokens:
                    if token_lower in f_token or (len(f_token) >= 2 and f_token in token_lower):
                        token_weight += weight * 0.75
                        hit = True
                        break

        if not hit or token_weight <= 0:
            continue

        score += token_weight * idf.get(token, 1.0)
        if token not in seen_terms:
            matched.append(token)
            seen_terms.add(token)

    return score, matched


def avoid_hit(fields: dict[str, set[str]], avoid_tokens: Iterable[str]) -> bool:
    for token in avoid_tokens:
        if not token:
            continue
        token_lower = token.lower()
        for field in AVOID_FIELDS:
            field_tokens = fields.get(field, ())
            if token in field_tokens or token_lower in field_tokens:
                return True
            if len(token_lower) >= 2:
                for f_token in field_tokens:
                    if token_lower in f_token:
                        return True
    return False
