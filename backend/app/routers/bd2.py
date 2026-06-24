import os

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from .. import auth, models
from ..database import get_db
from ..services.bd2_runtime import (
    _BD2_DOWNLOAD_STATE,
    _bd2_asset_root,
    _bd2_atlas_with_spine41_aliases,
    _bd2_char_info,
    _bd2_collect_spine_assets,
    _bd2_run_download,
    _bd2_spine_dir,
)

router = APIRouter()


@router.get("/bd2/spine")
def list_bd2_spine_assets(db: Session = Depends(get_db)):
    root = _bd2_asset_root(db)
    char_info, spine_to_char = _bd2_char_info(root)
    assets = [
        *_bd2_collect_spine_assets(root, char_info, spine_to_char, kind="char", folder="char"),
        *_bd2_collect_spine_assets(root, char_info, spine_to_char, kind="cutscene", folder="cutscenes"),
        *_bd2_collect_spine_assets(root, char_info, spine_to_char, kind="illust", folder="illust"),
    ]
    return {"root": root, "assets": assets}


@router.get("/bd2/spine/download/status")
def bd2_download_status():
    return dict(_BD2_DOWNLOAD_STATE)


@router.post("/bd2/spine/download/cancel")
def bd2_download_cancel(_: models.User = Depends(auth.require_admin)):
    status = _BD2_DOWNLOAD_STATE.get("status")
    if status not in {"checking", "cloning", "pulling"}:
        raise HTTPException(status_code=409, detail="No download in progress")
    _BD2_DOWNLOAD_STATE["cancel_requested"] = True
    # Best-effort hard stop the git subprocess so progress unblocks; the
    # worker loop will see the flag and exit cleanly on its own.
    proc = _BD2_DOWNLOAD_STATE.get("proc")
    if proc is not None:
        try:
            proc.terminate()
        except Exception:
            pass
    return {"status": "cancelling"}


@router.get("/bd2/spine/{kind}/{asset_id}/{filename}")
def get_bd2_spine_file_by_kind(kind: str, asset_id: str, filename: str, db: Session = Depends(get_db)):
    if kind not in {"char", "cutscene", "illust"}:
        raise HTTPException(status_code=400, detail="Invalid Spine asset kind")
    return _bd2_spine_file_response(asset_id, filename, kind=kind, db=db)


@router.get("/bd2/spine/{asset_id}/{filename}")
def get_bd2_spine_file(asset_id: str, filename: str, db: Session = Depends(get_db)):
    return _bd2_spine_file_response(asset_id, filename, kind="char", db=db)


def _bd2_spine_file_response(asset_id: str, filename: str, *, kind: str, db: Session):
    root = _bd2_asset_root(db)
    asset_dir = _bd2_spine_dir(root, asset_id, kind=kind)
    safe_name = os.path.basename(filename)
    if safe_name != filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    target = os.path.realpath(os.path.join(asset_dir, safe_name))
    real_asset_dir = os.path.realpath(asset_dir)
    if not (target == real_asset_dir or target.startswith(real_asset_dir + os.sep)):
        raise HTTPException(status_code=400, detail="Invalid file path")
    if not os.path.exists(target) or not os.path.isfile(target):
        raise HTTPException(status_code=404, detail="Spine file not found")
    if safe_name.lower().endswith(".atlas"):
        with open(target, "r", encoding="utf-8", errors="replace") as file:
            atlas_text = file.read()
        return Response(
            content=_bd2_atlas_with_spine41_aliases(atlas_text),
            media_type="text/plain; charset=utf-8",
            headers={"Cache-Control": "no-store"},
        )
    return FileResponse(target)


@router.post("/bd2/spine/download")
def bd2_download(
    payload: dict,
    background_tasks: BackgroundTasks,
    _: models.User = Depends(auth.require_admin),
):
    target_dir = str(payload.get("target_dir") or "").strip()
    if not target_dir:
        raise HTTPException(status_code=400, detail="target_dir is required")
    if _BD2_DOWNLOAD_STATE.get("status") in {"checking", "cloning", "pulling"}:
        raise HTTPException(status_code=409, detail="Download already in progress")
    target_dir = os.path.abspath(target_dir)
    background_tasks.add_task(_bd2_run_download, target_dir)
    return {"status": "started", "target_dir": target_dir}
