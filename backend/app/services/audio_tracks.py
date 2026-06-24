import os
import re
from typing import List

AUDIO_TRACK_EXTS = {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".opus"}
LYRIC_EXTS = (".lrc", ".vtt", ".srt")


def scan_audio_tracks(item_dir: str) -> List[dict]:
    """Walk an ASMR work folder and return tracks in stable display order."""
    if not item_dir or not os.path.isdir(item_dir):
        return []

    tracks: List[dict] = []
    for root, dirs, files in os.walk(item_dir):
        dirs.sort()
        for fname in sorted(files):
            ext = os.path.splitext(fname)[1].lower()
            if ext not in AUDIO_TRACK_EXTS:
                continue
            abs_path = os.path.join(root, fname)
            rel_path = os.path.relpath(abs_path, item_dir).replace(os.sep, "/")
            stem = os.path.splitext(fname)[0]
            lyrics_abs = None
            for lyric_ext in LYRIC_EXTS:
                candidate = os.path.join(root, stem + lyric_ext)
                if os.path.exists(candidate):
                    lyrics_abs = candidate
                    break
            tracks.append({
                "title": fname,
                "rel": rel_path,
                "abs_path": abs_path,
                "lyrics_abs": lyrics_abs,
            })

    for index, track in enumerate(tracks, start=1):
        track["index"] = index
    return tracks


_LRC_LINE_RE = re.compile(r"\[(\d+):(\d+(?:\.\d+)?)\](.*)")
_VTT_SRT_TIME_RE = re.compile(r"(\d+):(\d+):(\d+(?:[.,]\d+)?)")


def _hms_to_seconds(h: str, m: str, s: str) -> float:
    return int(h) * 3600 + int(m) * 60 + float(s.replace(",", "."))


def _parse_lrc(text: str) -> List[dict]:
    """LRC: one or more `[mm:ss.xx]` tags followed by lyric text per line."""
    lines: List[dict] = []
    for raw in text.splitlines():
        stamps = []
        rest = raw
        while True:
            m = _LRC_LINE_RE.match(rest)
            if not m:
                break
            stamps.append(int(m.group(1)) * 60 + float(m.group(2)))
            rest = m.group(3)
            if not rest.startswith("["):
                break
        if not stamps:
            continue
        body = rest.strip()
        if not body:
            continue
        for t in stamps:
            lines.append({"t": t, "text": body})
    return lines


def _parse_vtt_or_srt(text: str) -> List[dict]:
    lines: List[dict] = []
    blocks = re.split(r"\r?\n\s*\r?\n", text.strip())
    for block in blocks:
        block_lines = [ln for ln in block.splitlines() if ln.strip()]
        time_line = None
        body_lines: List[str] = []
        for ln in block_lines:
            if "-->" in ln and time_line is None:
                time_line = ln
            elif time_line is not None:
                body_lines.append(ln)
        if time_line is None or not body_lines:
            continue
        m = _VTT_SRT_TIME_RE.search(time_line)
        if not m:
            continue
        start = _hms_to_seconds(m.group(1), m.group(2), m.group(3))
        body = " ".join(body_lines).strip()
        if body:
            lines.append({"t": start, "text": body})
    return lines


def parse_lyrics_file(path: str) -> List[dict]:
    """Normalise an LRC/VTT/SRT file to [{t: seconds, text: str}], sorted."""
    if not path or not os.path.exists(path):
        return []
    ext = os.path.splitext(path)[1].lower()
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        return []
    if ext == ".lrc":
        lines = _parse_lrc(text)
    elif ext in (".vtt", ".srt"):
        lines = _parse_vtt_or_srt(text)
    else:
        lines = []
    lines.sort(key=lambda item: item["t"])
    return lines
