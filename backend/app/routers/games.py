from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..scanners.game import game_launchers, suggested_launcher
from ..services.media_access import get_media_or_404
from ..services.storage_guard import ensure_folder_scannable

router = APIRouter(prefix="/games", tags=["games"])


@router.get("/{media_id}/launchers")
def list_game_launchers(media_id: int, db: Session = Depends(get_db)):
    media = get_media_or_404(media_id, db)
    if media.media_type != "game" or media.extension != ".dir":
        raise HTTPException(status_code=400, detail="该媒体不是游戏文件夹")
    if media.is_missing:
        raise HTTPException(status_code=404, detail="游戏文件夹不可用")
    available, _reason = ensure_folder_scannable(media.absolute_path)
    if not available:
        raise HTTPException(status_code=503, detail="游戏存储暂时不可用")
    launchers = game_launchers(media.absolute_path)
    return {"launchers": launchers, "suggested": suggested_launcher(launchers)}
