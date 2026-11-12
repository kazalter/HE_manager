import json
import os
import re
import shutil
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request, Response, UploadFile, File, Depends
from .. import auth
from fastapi.responses import FileResponse


router = APIRouter(prefix="/l2d/models", tags=["live2d"])

@router.post("/import/{skin_id}", status_code=201)
def import_model(skin_id: str, archive: UploadFile = File(...), _user=Depends(auth.require_admin)):
    if not re.fullmatch(r"[a-z0-9]+(?:_[a-z0-9]+)*", skin_id):
        raise HTTPException(400, "Invalid skin id")
    root = _models_root()
    if not root.is_dir():
        raise HTTPException(503, "Live2D models are not installed")
    character = re.sub(r"_\d+$", "", re.sub(r"_hx$", "", skin_id))
    # Keep staging on the same filesystem for an atomic rename.
    with tempfile.TemporaryDirectory(prefix=".l2d-import-", dir=root) as temporary:
        stage = Path(temporary) / "skin"
        stage.mkdir()
        try:
            with zipfile.ZipFile(archive.file) as z:
                entries = z.infolist()
                if len(entries) > 10000 or sum(i.file_size for i in entries) > 1024**3:
                    raise ValueError("Archive too large")
                seen = set()
                for item in entries:
                    parts = item.filename.split('/')
                    if (not item.filename or '\\' in item.filename or any(p in ('', '.', '..') for p in parts)
                            or item.filename in seen or item.is_dir() or (item.external_attr >> 16) & 0o170000 == 0o120000):
                        raise ValueError("Invalid archive entry")
                    seen.add(item.filename)
                    dest = stage.joinpath(*parts)
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    with z.open(item) as source, dest.open('xb') as out:
                        shutil.copyfileobj(source, out)
                if f"{skin_id}.model3.json" not in seen or f"{skin_id}.moc3" not in seen:
                    raise ValueError("Incomplete model")
                json.loads((stage / f"{skin_id}.model3.json").read_text(encoding="utf-8"))
        except (ValueError, OSError, zipfile.BadZipFile, json.JSONDecodeError) as exc:
            raise HTTPException(400, f"Invalid model archive: {exc}") from None
        parent = root / character
        parent.mkdir(exist_ok=True)
        target = parent / skin_id
        if target.exists():
            raise HTTPException(409, "Model already exists")
        try:
            stage.rename(target)
        except OSError as exc:
            raise HTTPException(409 if target.exists() else 500, "Could not install model") from exc
    return {"id": skin_id}


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
