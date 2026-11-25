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


def _validate_model_record(raw: dict) -> dict:
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
        if len(raw["model"]) > 200 or len(raw["api_key"]) > 1000 or len(raw["base_url"]) > 500:
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


def _raw_model_source() -> tuple[dict, bool]:
    path = data_dir() / "hermes-model.json"
    if path.exists():
        return read_private_json(path), True
    from ..ai_config import (
        CONFIG_PATH,
        DEFAULT_DEEPSEEK_BASE_URL,
        DEFAULT_DEEPSEEK_MODEL,
    )

    candidate = Path(CONFIG_PATH)
    stored = read_private_json(candidate) if candidate.exists() else {}
    return {
        "provider": "custom",
        "model": os.getenv("DEEPSEEK_MODEL")
        or stored.get("model")
        or DEFAULT_DEEPSEEK_MODEL,
        "base_url": os.getenv("DEEPSEEK_API_BASE")
        or stored.get("base_url")
        or DEFAULT_DEEPSEEK_BASE_URL,
        "api_key": os.getenv("DEEPSEEK_API_KEY") or stored.get("api_key") or "",
    }, False


def load_model() -> dict:
    raw, _ = _raw_model_source()
    return _validate_model_record(raw)


def _builtin_presets(base_url: str, key_configured: bool) -> list[dict]:
    host = (urlsplit(base_url).hostname or "").lower()
    if "deepseek" not in host:
        return []
    normalized = base_url.rstrip("/")
    v1_url = normalized if normalized.endswith("/v1") else normalized + "/v1"
    return [
        {
            "id": "deepseek-flash",
            "label": "DeepSeek-V4.1-Flash",
            "model": "deepseek-flash",
            "base_url": v1_url,
            "key_configured": key_configured,
            "thinking_disabled": True,
            "custom": False,
        },
        {
            "id": "deepseek-chat",
            "label": "DeepSeek Chat",
            "model": "deepseek-chat",
            "base_url": v1_url,
            "key_configured": key_configured,
            "thinking_disabled": True,
            "custom": False,
        },
        {
            "id": "deepseek-reasoner",
            "label": "DeepSeek Reasoner",
            "model": "deepseek-reasoner",
            "base_url": v1_url,
            "key_configured": key_configured,
            "thinking_disabled": False,
            "custom": False,
        },
    ]


def _stored_presets(raw: dict, fallback_key: str) -> list[dict]:
    items = raw.get("presets")
    if not isinstance(items, list):
        return []
    result = []
    for item in items:
        if not isinstance(item, dict):
            continue
        pid = item.get("id")
        model = item.get("model")
        base_url = item.get("base_url")
        if not all(isinstance(v, str) and v.strip() for v in (pid, model, base_url)):
            continue
        label = item.get("label")
        has_key = bool((isinstance(item.get("api_key"), str) and item["api_key"]) or fallback_key)
        result.append(
            {
                "id": pid.strip()[:120],
                "label": (label.strip() if isinstance(label, str) and label.strip() else model.strip())[:120],
                "model": model.strip()[:200],
                "base_url": base_url.strip().rstrip("/")[:500],
                "key_configured": has_key,
                "thinking_disabled": bool(item.get("thinking_disabled", False)),
                "custom": True,
            }
        )
    return result


def get_model_config_summary() -> dict:
    raw, from_file = _raw_model_source()
    validated = _validate_model_record(raw)
    display = raw.get("display_model")
    thinking_disabled = validated["extra_body"].get("thinking") == {"type": "disabled"}
    presets: list[dict] = []
    seen_ids: set[str] = set()
    for item in _stored_presets(raw, validated["api_key"]) + _builtin_presets(
        validated["base_url"], bool(validated["api_key"])
    ):
        if item["id"] not in seen_ids:
            seen_ids.add(item["id"])
            presets.append(item)
    if not any(
        p["model"] == validated["model"] and p["base_url"].rstrip("/") == validated["base_url"]
        for p in presets
    ):
        presets.insert(
            0,
            {
                "id": f"active:{validated['model']}",
                "label": display.strip() if isinstance(display, str) and display.strip() else validated["model"],
                "model": validated["model"],
                "base_url": validated["base_url"],
                "key_configured": bool(validated["api_key"]),
                "thinking_disabled": thinking_disabled,
                "custom": from_file,
            },
        )
    matched = next(
        (
            p
            for p in presets
            if p["model"] == validated["model"] and p["base_url"].rstrip("/") == validated["base_url"]
        ),
        None,
    )
    label = (
        display.strip()
        if isinstance(display, str) and display.strip()
        else (matched["label"] if matched else validated["model"])
    )
    return {
        "model": validated["model"],
        "display_model": label,
        "base_url": validated["base_url"],
        "key_configured": bool(validated["api_key"]),
        "thinking_disabled": thinking_disabled,
        "presets": presets,
    }


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
    owner_uid = owner_gid = None
    if os.name != "nt":
        try:
            ref_stat = path.stat() if path.exists() else path.parent.stat()
            if hasattr(os, "geteuid") and os.geteuid() == 0 and ref_stat.st_uid != 0:
                owner_uid, owner_gid = ref_stat.st_uid, ref_stat.st_gid
        except OSError:
            pass
    temporary = path.with_name("." + path.name + "." + secrets.token_hex(8) + ".tmp")
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            output.write(text)
            output.flush()
            os.fsync(output.fileno())
        if owner_uid is not None and owner_gid is not None:
            try:
                os.chown(temporary, owner_uid, owner_gid)
            except OSError:
                pass
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
