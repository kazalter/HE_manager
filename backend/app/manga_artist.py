"""Extract canonical artist and circle names from manga titles and paths.

Many manga titles follow the standard doujin naming convention::

    (C105) [Circle (Artist)] Work Title (Parody) [Chinese] [DL版]
    [Artist] Work Title [English]
    [ScanlationGroup] (C93) [Circle (Artist)] Work Title

where a leading `(event)` is followed by `[Circle (Artist)]` or `[Artist]`,
sometimes prefixed by `[Date]`, `[ScanlationGroup]`, `[無修正]`, or a
numeric ID prefix like `3757416_[ie] ...`. When a title has no author bracket
(for instance works organized inside an artist folder like `mignon/...` or
`7623-[まかろん大帝 (がおう)]/...`), `parse_artist_with_path` /
`parse_circle_with_path` fall back to ancestor folder names.
"""
from __future__ import annotations

import re
from typing import Iterable, Optional

# Bracket contents that are language / status / scanlation markers, never an
# author. Compared case-insensitively after stripping spaces.
_META_TAGS = {
    "無修正", "無修", "無修正版", "無碼", "无修正", "无码", "疏码", "疏碼",
    "dl版", "dl", "dl version", "中国翻訳", "中國翻訳", "中国翻译", "中國翻譯", "翻訳", "翻譯",
    "中文", "中国語", "中国语", "中国", "chinese", "english", "japanese", "日本語",
    "decensored", "digital", "個人漢化", "漢化", "汉化", "个人汉化",
    "r18", "r-18", "18禁", "全彩", "彩圖", "color", "full color",
    # Archive / compilation labels that sit where the author bracket would be.
    "汉化汇总", "汉化合集", "漢化彙總", "汉化杂图集",
    "pixiv fanbox", "fanbox", "pixiv",
    "洨五組", "洨五组",
}

_SCANLATION_SUBSTRINGS = (
    "汉化", "漢化", "翻译", "翻譯", "渣翻", "机翻", "機翻",
    "重嵌", "嵌字", "扫图", "掃圖", "个汉", "個漢",
    "去码", "去碼", "疏码", "疏碼", "無修正", "无修正", "無碼", "无码",
    "英訳", "日訳", "出资", "出資", "个人重嵌", "個人重嵌",
)

# Date-style archive prefixes like "[2022.08]" / "[2024-05-24]" — never authors.
_DATE_BRACKET = re.compile(r"^\d{4}[.\-_/]\d{1,2}([.\-_/]\d{1,2})?$")
_EVENT_BRACKET = re.compile(
    r"^(?:c\d+|comitia\d*|comic1.*|例大祭.*|紅楼夢.*|サンクリ.*|エアコミケ\d*|"
    r"コミティア\d*|ホロクル.*|ホロケット.*|gw超同人祭)$",
    re.I,
)

_LEADING_ID_PREFIX = re.compile(r"^\s*\d{3,}_(?=[［\[【])")
_EVENT_PREFIX = re.compile(r"^\s*[（(][^（）()]*[）)]\s*")
# Accept ASCII [...], full-width ［...］ and Chinese 【...】.
_LEADING_BRACKET = re.compile(r"^\s*[［\[【]([^［\]\[］【】]+)[］\]】]\s*")
_ANY_BRACKET = re.compile(r"[［\[【]([^［\]\[］【】]+)[］\]】]")
# "Circle (Artist)" — the artist is the trailing parenthesised group.
_CIRCLE_ARTIST = re.compile(r"^(?P<circle>.+?)\s*[（(](?P<artist>[^（）()]+)[）)]\s*$")
_ARTIST_PREFIX_RE = re.compile(r"^\s*Artist--\s*([^（(\[【]+)", re.I)
_DELIM_PREFIX_RE = re.compile(r"^\s*([^（(\[【·\-/|]+?)\s*(?:-|·|•)\s+\S")

_GENERIC_FOLDERS = {
    "manga", "mangas", "comic", "comics", "doujin", "doujinshi", "wnacg",
    "downloads", "download", "local", "library", "import", "imported",
    "未分类", "未分類", "合集", "短篇", "本子", "其他", "杂图", "雜圖",
}


def is_meta_bracket(content: Optional[str]) -> bool:
    """Return True if a bracketed token is a meta/scanlation/date/event marker."""
    if not content:
        return True
    cleaned = content.strip()
    if not cleaned:
        return True
    lowered = cleaned.lower()
    if lowered in _META_TAGS or _DATE_BRACKET.match(cleaned) or _EVENT_BRACKET.match(cleaned):
        return True
    if any(sub in lowered for sub in _SCANLATION_SUBSTRINGS):
        return True
    if cleaned.isdigit():
        return True
    return False


def _author_bracket(title: Optional[str]) -> Optional[str]:
    """Return the contents of the first non-meta `[...]` bracket, or None."""
    if not title:
        return None
    s = _LEADING_ID_PREFIX.sub("", title.strip())
    skipped_prefix = False
    while True:
        stripped = _EVENT_PREFIX.sub("", s)
        if stripped != s:
            s = stripped
            skipped_prefix = True
            continue
        m = _LEADING_BRACKET.match(s)
        if not m:
            break
        content = m.group(1).strip()
        if is_meta_bracket(content):
            s = s[m.end():]
            skipped_prefix = True
            continue
        return content

    # Fallback: `魅力的代價 無修正版 [轟媽無修正][沒有漢化漢化組][原崎]魅惑の代償`
    # or `[洨五組[ピジャ]投げ銭￥交際` (unclosed leading bracket or text before brackets)
    for m in _ANY_BRACKET.finditer(s):
        content = m.group(1).strip()
        if is_meta_bracket(content):
            skipped_prefix = True
            continue
        trailing = s[m.end():].strip()
        prefix = s[:m.start()]
        # Only trust a non-leading bracket if real title text follows it OR it
        # came right after a skipped meta/unclosed bracket.
        if trailing and (skipped_prefix or "[" in prefix or not prefix.strip()):
            return content
        if "[" in prefix and prefix.strip().startswith("["):
            return content
    return None


def parse_artist(title: Optional[str]) -> Optional[str]:
    """Return the canonical artist name for a manga title, or None."""
    if not title:
        return None
    inner = _author_bracket(title)
    if inner:
        cm = _CIRCLE_ARTIST.match(inner)
        name = (cm.group("artist") if cm else inner).strip()
        if name and not is_meta_bracket(name):
            return name

    # Explicit `Artist--Name(8/8)` prefix
    am = _ARTIST_PREFIX_RE.match(title)
    if am:
        name = am.group(1).strip()
        if name and not is_meta_bracket(name):
            return name
    return None


def parse_circle(title: Optional[str]) -> Optional[str]:
    """Return the circle (社团) for a `[Circle (Artist)]` title, or None.

    A bare `[Artist]` bracket has no circle — we return None rather than
    fabricating one from the artist.
    """
    inner = _author_bracket(title)
    if not inner:
        return None
    cm = _CIRCLE_ARTIST.match(inner)
    if not cm:
        return None
    circle = (cm.group("circle") or "").strip()
    if not circle or is_meta_bracket(circle):
        return None
    return circle


def parse_artist_and_circle_from_path(
    relative_path: Optional[str],
    *,
    known_artists: Optional[Iterable[str]] = None,
    known_circles: Optional[Iterable[str]] = None,
) -> tuple[Optional[str], Optional[str]]:
    """Inspect ancestor folders of `relative_path` for `(artist, circle)`."""
    if not relative_path:
        return None, None
    parts = [p.strip() for p in re.split(r"[\\/]+", relative_path) if p.strip()]
    if len(parts) <= 1:
        return None, None

    artist_set = {a.strip().lower() for a in (known_artists or ()) if a and a.strip()}
    circle_set = {c.strip().lower() for c in (known_circles or ()) if c and c.strip()}

    for seg in reversed(parts[:-1]):
        lowered = seg.lower()
        if lowered in _GENERIC_FOLDERS or _DATE_BRACKET.match(seg) or _EVENT_BRACKET.match(seg):
            continue

        # Prefer `[Circle (Artist)]` or `[Artist]` embedded inside folder name
        brackets = [m.group(1).strip() for m in _ANY_BRACKET.finditer(seg)]
        clean_brackets = [
            b for b in brackets
            if b and not b.startswith("@") and not is_meta_bracket(b)
        ]
        if clean_brackets:
            for b in clean_brackets:
                cm = _CIRCLE_ARTIST.match(b)
                if cm:
                    c_name = (cm.group("circle") or "").strip() or None
                    a_name = (cm.group("artist") or "").strip() or None
                    if a_name and not is_meta_bracket(a_name):
                        return a_name, (c_name if c_name and not is_meta_bracket(c_name) else None)
            first = clean_brackets[0]
            return first, None

        # Folder formatted directly as `Circle (Artist)` (e.g. `合衆国ネタメコル (ねこめたる)`)
        cm = _CIRCLE_ARTIST.match(seg)
        if cm:
            c_name = (cm.group("circle") or "").strip() or None
            a_name = (cm.group("artist") or "").strip() or None
            if a_name and not is_meta_bracket(a_name):
                return a_name, (c_name if c_name and not is_meta_bracket(c_name) else None)

        if lowered in circle_set and lowered not in artist_set:
            return None, seg

        return seg, None

    return None, None


def parse_artist_with_path(
    title: Optional[str],
    relative_path: Optional[str] = None,
    *,
    known_artists: Optional[Iterable[str]] = None,
    known_circles: Optional[Iterable[str]] = None,
) -> Optional[str]:
    """Parse artist from title first, then safe known-artist/folder fallbacks."""
    artist = parse_artist(title)
    if artist:
        return artist

    artist_set = {a.strip().lower() for a in (known_artists or ()) if a and a.strip()}
    if title and artist_set:
        dm = _DELIM_PREFIX_RE.match(title)
        if dm:
            prefix = dm.group(1).strip()
            if prefix.lower() in artist_set:
                return prefix

    path_artist, _ = parse_artist_and_circle_from_path(
        relative_path,
        known_artists=known_artists,
        known_circles=known_circles,
    )
    return path_artist


def parse_circle_with_path(
    title: Optional[str],
    relative_path: Optional[str] = None,
    *,
    known_artists: Optional[Iterable[str]] = None,
    known_circles: Optional[Iterable[str]] = None,
) -> Optional[str]:
    """Parse circle from title first, falling back to ancestor folder metadata."""
    circle = parse_circle(title)
    if circle:
        return circle
    _, path_circle = parse_artist_and_circle_from_path(
        relative_path,
        known_artists=known_artists,
        known_circles=known_circles,
    )
    return path_circle
