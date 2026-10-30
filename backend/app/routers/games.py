from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..scanners.game import game_launchers, suggested_launcher
from ..services import game_runtime
from ..services.game_runtime import GameRuntimeError
from ..services.media_access import get_media_or_404
from ..services.storage_guard import ensure_folder_scannable

router = APIRouter(prefix="/games", tags=["games"])


class StartSessionRequest(BaseModel):
    launcher: str = Field(min_length=1, max_length=255)


def _runtime_call(fn, *args):
    try:
        return fn(*args)
    except GameRuntimeError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.get("/session")
def get_game_session(request: Request, response: Response):
    try:
        return game_runtime.status(request, response)
    except GameRuntimeError as exc:
        if exc.status_code == 503 and "尚未配置" in str(exc):
            return {"active": False, "configured": False}
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post("/stop")
def stop_game_session(response: Response):
    result = _runtime_call(game_runtime.stop)
    response.delete_cookie(game_runtime.stream_cookie_name(), path="/games/session/")
    return result


@router.get("/stream-auth")
def authorize_game_stream(request: Request):
    if not game_runtime.authorize_stream(request):
        raise HTTPException(status_code=401, detail="游戏串流会话已失效")
    return Response(status_code=204)


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


@router.post("/{media_id}/session")
def start_game_session(
    media_id: int,
    payload: StartSessionRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    media = get_media_or_404(media_id, db)
    if media.media_type != "game" or media.extension != ".dir":
        raise HTTPException(status_code=400, detail="该媒体不是游戏文件夹")
    if media.is_missing:
        raise HTTPException(status_code=404, detail="游戏文件夹不可用")
    available, _reason = ensure_folder_scannable(media.absolute_path)
    if not available:
        raise HTTPException(status_code=503, detail="游戏存储暂时不可用")
    launchers = game_launchers(media.absolute_path)
    result, token = _runtime_call(game_runtime.start, media, payload.launcher, launchers)
    game_runtime.set_stream_cookie(response, token, request=request)
    return result
