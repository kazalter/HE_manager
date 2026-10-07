"""Title normalization for finding duplicate candidates.

The normalized form is *only* used as a candidate filter — never to merge directly.
Aggressive enough to bring together obvious near-matches, conservative enough to
not collapse different works.
"""
from __future__ import annotations

import os
import re
import unicodedata


# Common bracketed metadata that is usually decorative: language tags, group/release tags,
# resolution flags, page counts, etc. We strip these so titles like
# "[Group] Title (English) [DL Version]" collapse to "title".
_BRACKETED = re.compile(r"[\[\(【「『〈《][^\[\]\(\)【】「」『』〈〉《》]{0,80}[\]\)】」』〉》]")
_RUNS = re.compile(r"[\s_\-·•・~～]+")
_PUNCT = re.compile(r"[!\"#$%&'()*+,\-./:;<=>?@\[\\\]^_`{|}~。、，；：！？…—『』「」【】《》〈〉]+")
_MEDIA_EXTENSIONS = {
    '.zip', '.cbz', '.mp4', '.mkv', '.avi', '.mov', '.wmv', '.webm', '.flv', '.ts', '.m4v',
    '.png', '.jpg', '.jpeg', '.webp', '.bmp', '.gif', '.avif',
    '.mp3', '.wav', '.flac', '.m4a', '.aac', '.ogg', '.opus', '.wma',
}


def normalize_title(value: str) -> str:
    """Return a lowercase, punctuation-stripped key suitable for candidate lookup.

    Empty string when the input is empty or normalization throws away everything.
    """
    if not value:
        return ""

    # A date or dotted title is not a file extension. Unconditionally splitting
    # '[2023.01] ...' used to discard the work title and collapse a whole year.
    stem, extension = os.path.splitext(value)
    base = stem if extension.lower() in _MEDIA_EXTENSIONS else value

    # NFKC folds full-width / half-width CJK punctuation to a canonical form so the
    # punctuation strip below catches them too.
    text = unicodedata.normalize("NFKC", base)

    # Repeated bracketed-metadata stripping; some titles nest two or three layers.
    for _ in range(3):
        new = _BRACKETED.sub(" ", text)
        if new == text:
            break
        text = new

    text = _PUNCT.sub(" ", text)
    text = _RUNS.sub(" ", text).strip()
    return text.lower()
