"""Private, read-only configuration with bounded parsing and safe errors."""

from __future__ import annotations
import json
import os
from pathlib import Path
from urllib.parse import urlsplit
from fastapi import HTTPException
from .schemas import ProfileBinding


def enabled() -> bool:
    return os.getenv("HE_ASSISTANT_ENABLED", "0").lower() in {"1", "true", "yes", "on"}


def require_enabled():
    if not enabled():
        raise HTTPException(503, "assistant_disabled")


def data_dir() -> Path:
    from sqlalchemy.engine import make_url
    from ..database import SQLALCHEMY_DATABASE_URL

    path = os.getenv("HE_ASSISTANT_DATA_DIR")
    if path:
        return Path(path)
    database = make_url(SQLALCHEMY_DATABASE_URL).database
    return (
        Path(database).resolve().parent
        if database and database != ":memory:"
        else Path.cwd() / "data"
    ) / "assistant"


def read_private_json(path: Path) -> dict:
    try:
        if path.is_symlink() or (os.name != "nt" and path.stat().st_mode & 0o077):
            raise ValueError
        with path.open("rb") as source:
            raw = source.read(65537)
        if len(raw) > 65536:
            raise ValueError
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise ValueError
        return result
    except (OSError, ValueError, TypeError):
        raise HTTPException(503, "assistant_unconfigured") from None


def get_profile(user_id: int) -> ProfileBinding:
    try:
        if not isinstance(user_id, int) or isinstance(user_id, bool) or user_id <= 0:
            raise ValueError
        raw = read_private_json(data_dir() / "profiles.json")
        item = raw["profiles"][str(user_id)]
        binding = ProfileBinding.model_validate(item)
        if (
            binding.user_id != user_id
            or binding.profile_name != "he-user-" + str(user_id)
            or len(binding.api_key.get_secret_value()) < 32
            or len(binding.tool_token_hash) != 64
        ):
            raise ValueError
        return binding
    except (KeyError, ValueError, TypeError):
        raise HTTPException(503, "assistant_unconfigured") from None


def load_model() -> dict:
    path = data_dir() / "hermes-model.json"
    if path.exists():
        raw = read_private_json(path)
    else:
        from ..ai_config import (
            CONFIG_PATH,
            DEFAULT_DEEPSEEK_BASE_URL,
            DEFAULT_DEEPSEEK_MODEL,
        )

        candidate = Path(CONFIG_PATH)
        stored = read_private_json(candidate) if candidate.exists() else {}
        raw = {
            "provider": "custom",
            "model": os.getenv("DEEPSEEK_MODEL")
            or stored.get("model")
            or DEFAULT_DEEPSEEK_MODEL,
            "base_url": os.getenv("DEEPSEEK_API_BASE")
            or stored.get("base_url")
            or DEFAULT_DEEPSEEK_BASE_URL,
            "api_key": os.getenv("DEEPSEEK_API_KEY") or stored.get("api_key") or "",
        }
    try:
        parts = urlsplit(raw["base_url"])
        if (
            parts.scheme != "https"
            or not parts.hostname
            or parts.username
            or parts.password
            or parts.query
            or parts.fragment
        ):
            raise ValueError
        if any(
            not isinstance(raw.get(k), str) or not raw[k] for k in ("api_key", "model")
        ):
            raise ValueError
        if any(
            "\n" in raw[k] or "\r" in raw[k] for k in ("api_key", "model", "base_url")
        ):
            raise ValueError
        if len(raw["model"]) > 200 or len(raw["api_key"]) > 1000:
            raise ValueError
        extra = raw.get("extra_body", {})
        if not isinstance(extra, dict) or set(extra) - {"thinking"}:
            raise ValueError
        if "thinking" in extra and extra["thinking"] != {"type": "disabled"}:
            raise ValueError
        return {
            "provider": "custom:he-model",
            "model": raw["model"],
            "base_url": raw["base_url"].rstrip("/"),
            "api_key": raw["api_key"],
            "extra_body": extra,
        }
    except (KeyError, TypeError, ValueError):
        raise HTTPException(503, "assistant_model_unconfigured") from None


def secure_directory(path: Path):
    if path.is_symlink():
        raise HTTPException(503, "assistant_storage_unavailable")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != "nt":
        path.chmod(0o700)


def atomic_private_write(path: Path, text: str):
    import secrets

    secure_directory(path.parent)
    if path.is_symlink():
        raise HTTPException(503, "assistant_storage_unavailable")
    temporary = path.with_name("." + path.name + "." + secrets.token_hex(8) + ".tmp")
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            output.write(text)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        if os.name != "nt":
            path.chmod(0o600)
    finally:
        temporary.unlink(missing_ok=True)


def template_dir() -> Path:
    explicit = os.getenv("HE_ASSISTANT_TEMPLATE_DIR")
    if explicit:
        return Path(explicit)
    source = Path(__file__).resolve()
    for candidate in (
        source.parents[3] / "deploy/hermes",
        source.parents[2] / "deploy/hermes",
    ):
        if candidate.is_dir():
            return candidate
    raise HTTPException(503, "assistant_template_invalid")
