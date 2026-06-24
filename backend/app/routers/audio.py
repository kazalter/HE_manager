from datetime import datetime
import os
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .. import models, scanner
from ..database import get_db
from ..services.audio_tracks import LYRIC_EXTS, parse_lyrics_file, scan_audio_tracks
from ..services.media_access import get_media_or_404
from ..services.range_response import get_ranged_file_response

router = APIRouter()


def _get_audio_media_or_404(media_id: int, db: Session) -> models.Media:
    media = get_media_or_404(media_id, db)
    if media.media_type != "audio":
        raise HTTPException(status_code=400, detail="This media is not an audio work")
    if not os.path.exists(media.absolute_path):
        if not media.is_missing:
            media.is_missing = True
            media.missing_since = datetime.utcnow()
            db.commit()
        raise HTTPException(status_code=404, detail="Audio file/folder not found on disk")
    return media


def _resolve_audio_tracks(media: models.Media) -> List[dict]:
    """Return the in-display-order track list for an audio Media row."""
    if os.path.isdir(media.absolute_path):
        manifest = scanner.read_tracks_json(media.absolute_path)
        if manifest and isinstance(manifest.get("tracks"), list):
            work_root_abs = os.path.realpath(media.absolute_path)
            out: List[dict] = []
            for entry in manifest["tracks"]:
                if not isinstance(entry, dict):
                    continue
                rel = entry.get("rel") or ""
                if not rel:
                    continue
                abs_path = os.path.realpath(os.path.join(media.absolute_path, *rel.split("/")))
                if not (abs_path == work_root_abs or abs_path.startswith(work_root_abs + os.sep)):
                    continue
                if not os.path.exists(abs_path):
                    continue
                stem, _ = os.path.splitext(abs_path)
                lyrics_abs = None
                for lyric_ext in LYRIC_EXTS:
                    candidate = stem + lyric_ext
                    if os.path.exists(candidate):
                        lyrics_abs = candidate
                        break
                out.append({
                    "index": entry.get("index") if isinstance(entry.get("index"), int) else (len(out) + 1),
                    "title": entry.get("title") or os.path.basename(abs_path),
                    "rel": rel,
                    "abs_path": abs_path,
                    "lyrics_abs": lyrics_abs,
                    "duration": entry.get("duration") if isinstance(entry.get("duration"), (int, float)) else None,
                })
            if out:
                return out
        return scan_audio_tracks(media.absolute_path)

    parent = os.path.dirname(media.absolute_path)
    stem = os.path.splitext(os.path.basename(media.absolute_path))[0]
    lyrics_abs = None
    for lyric_ext in LYRIC_EXTS:
        candidate = os.path.join(parent, stem + lyric_ext)
        if os.path.exists(candidate):
            lyrics_abs = candidate
            break
    return [{
        "index": 1,
        "title": os.path.basename(media.absolute_path),
        "rel": os.path.basename(media.absolute_path),
        "abs_path": media.absolute_path,
        "lyrics_abs": lyrics_abs,
        "duration": None,
    }]


def _audio_lyrics_rel(track: dict, media: models.Media) -> Optional[str]:
    if not track.get("lyrics_abs"):
        return None
    anchor = media.absolute_path if os.path.isdir(media.absolute_path) else os.path.dirname(media.absolute_path)
    return os.path.relpath(track["lyrics_abs"], anchor).replace(os.sep, "/")


@router.get("/audio/{media_id}/tracks")
def get_audio_tracks(media_id: int, db: Session = Depends(get_db)):
    media = _get_audio_media_or_404(media_id, db)
    tracks = _resolve_audio_tracks(media)
    return {
        "tracks": [
            {
                "index": t["index"],
                "title": t["title"],
                "rel": t["rel"],
                "duration": t.get("duration"),
                "lyrics": _audio_lyrics_rel(t, media),
            }
            for t in tracks
        ],
    }


@router.get("/audio/{media_id}/track/{index}")
def stream_audio_track(media_id: int, index: int, request: Request, db: Session = Depends(get_db)):
    media = _get_audio_media_or_404(media_id, db)
    tracks = _resolve_audio_tracks(media)
    if index < 1 or index > len(tracks):
        raise HTTPException(status_code=404, detail="Track index out of range")
    return get_ranged_file_response(request, tracks[index - 1]["abs_path"])


@router.get("/audio/{media_id}/track/{index}/lyrics")
def get_audio_track_lyrics(media_id: int, index: int, db: Session = Depends(get_db)):
    media = _get_audio_media_or_404(media_id, db)
    tracks = _resolve_audio_tracks(media)
    if index < 1 or index > len(tracks):
        raise HTTPException(status_code=404, detail="Track index out of range")
    lyrics_path = tracks[index - 1]["lyrics_abs"]
    return {"lines": parse_lyrics_file(lyrics_path) if lyrics_path else []}
