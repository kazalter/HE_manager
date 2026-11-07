import json
import os
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request, Response
from .. import auth
from fastapi.responses import FileResponse


router = APIRouter(prefix="/l2d/models", tags=["live2d"])


def _models_root() -> Path:
    return Path(os.getenv("HE_L2D_MODELS_DIR", "/mnt/hdd/azurlane-l2dviewer/models")).expanduser()


def _model_file(relative_path: str) -> Path:
    root = _models_root().resolve()
    if not root.is_dir():
        raise HTTPException(status_code=503, detail="Live2D models are not installed")

    try:
        target = (root / relative_path).resolve(strict=True)
        target.relative_to(root)
    except (OSError, ValueError):
        raise HTTPException(status_code=404, detail="Model file not found") from None

    if not target.is_file():
        raise HTTPException(status_code=404, detail="Model file not found")
    return target


@router.post("/session", status_code=204)
def create_model_session(request: Request, response: Response):
    token = auth.token_from_authorization(request.headers.get("authorization"))
    if not token:
        raise HTTPException(status_code=401, detail="Missing access token")
    response.set_cookie("he_l2d_token", token, httponly=True, samesite="strict", secure=request.headers.get("x-forwarded-proto", request.url.scheme) == "https", path="/l2d/models/", max_age=2592000)


@router.get("/manifest.json")
def list_live2d_models():
    root = _models_root()
    if not root.is_dir():
        raise HTTPException(status_code=503, detail="Live2D models are not installed")

    models = []
    for character in root.iterdir():
        if not character.is_dir():
            continue
        for skin in character.iterdir():
            if not skin.is_dir():
                continue
            model_file = skin / f"{skin.name}.model3.json"
            if not model_file.is_file():
                continue

            name = skin.name
            try:
                metadata = json.loads((skin / f"{skin.name}.l2d.json").read_text(encoding="utf-8"))
                name = metadata.get("name") or name
            except (OSError, ValueError, AttributeError):
                pass

            path = "/".join(quote(part, safe="") for part in (character.name, skin.name, model_file.name))
            models.append({
                "id": skin.name,
                "name": name,
                "url": f"/l2d/models/{path}",
            })

    return models


@router.get("/{relative_path:path}")
def get_live2d_model_file(relative_path: str):
    return FileResponse(_model_file(relative_path))
