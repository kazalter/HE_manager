"""Tool identities are DB-only hashes; HE user tokens never become tool tokens."""

import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
from fastapi import HTTPException
from sqlalchemy import select
from . import config
from .models import AssistantRun, AssistantSession, AssistantToolIdentity
from .schemas import ProfileBinding, ToolPrincipal
from .store import require_admin, utcnow, write_transaction


def hash_tool_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def authenticate_tool_token(db, token: str) -> ToolPrincipal:
    config.require_enabled()
    if not isinstance(token, str) or not 32 <= len(token) <= 1000:
        raise HTTPException(401, "assistant_invalid_tool_token")
    digest = hash_tool_token(token)
    row = db.execute(
        select(AssistantToolIdentity)
        .where(AssistantToolIdentity.tool_token_hash == digest)
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()
    if (
        row is None
        or not row.enabled
        or not hmac.compare_digest(row.tool_token_hash, digest)
    ):
        raise HTTPException(401, "assistant_invalid_tool_token")
    require_admin(db, row.user_id)
    if row.profile_name != "he-user-" + str(row.user_id):
        raise HTTPException(401, "assistant_invalid_tool_token")
    return ToolPrincipal(user_id=row.user_id, profile_name=row.profile_name)


def require_tool_context(db, principal, context):
    config.require_enabled()
    require_admin(db, principal.user_id)
    identity = db.execute(
        select(AssistantToolIdentity)
        .where(AssistantToolIdentity.user_id == principal.user_id)
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()
    row = db.execute(
        select(AssistantRun)
        .where(
            AssistantRun.id == str(context.run_id),
            AssistantRun.session_id == str(context.session_id),
            AssistantRun.user_id == principal.user_id,
        )
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()
    session = db.execute(
        select(AssistantSession)
        .where(
            AssistantSession.id == str(context.session_id),
            AssistantSession.user_id == principal.user_id,
        )
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()
    if row is None or session is None:
        raise HTTPException(404, "assistant_not_found")
    if (
        not identity
        or not identity.enabled
        or identity.profile_name != principal.profile_name
        or identity.credential_generation != row.api_key_generation
    ):
        raise HTTPException(401, "assistant_invalid_tool_token")
    if (
        session.state != "active"
        or row.status not in ("submitting", "running")
        or row.stop_requested_at is not None
        or row.executor_exited_at is not None
        or (row.deadline_at and row.deadline_at <= utcnow())
    ):
        raise HTTPException(409, "assistant_run_unavailable")
    return row


def _read_env(path):
    if path.is_symlink() or (os.name != "nt" and path.stat().st_mode & 0o077):
        raise HTTPException(503, "assistant_storage_unavailable")
    with path.open("rb") as source:
        raw = source.read(65537)
    if len(raw) > 65536:
        raise HTTPException(503, "assistant_storage_unavailable")
    result = {}
    for line in raw.decode("utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        if not sep or key in result:
            raise HTTPException(503, "assistant_storage_unavailable")
        result[key] = value
    return result


def _profile_yaml(model):
    template = config.template_dir() / "config.example.yaml"
    # JSON string scalars are valid YAML and cannot inject keys/newlines.
    text = template.read_text(encoding="utf-8")
    for old, new in [
        ("default: deepseek-flash", "default: " + json.dumps(model["model"])),
        (
            "default_model: deepseek-flash",
            "default_model: " + json.dumps(model["model"]),
        ),
        (
            "base_url: https://api.deepseek.com/v1",
            "base_url: " + json.dumps(model["base_url"]),
        ),
    ]:
        if text.count(old) != 1:
            raise HTTPException(503, "assistant_template_invalid")
        text = text.replace(old, new)
    if not model["extra_body"].get("thinking"):
        text = text.replace("      thinking:\n        type: disabled\n", "")
    return text


def prepare_profile(db, user_id, *, profile_root: Path | None = None) -> ProfileBinding:
    """Create explicit administrator profiles; repeated preparation preserves keys."""
    model = config.load_model()
    root = profile_root or config.data_dir().parent / "hermes"
    name = "he-user-" + str(user_id)
    home = root / "profiles" / name
    with write_transaction(db) as local:
        require_admin(local, user_id)
        if local.execute(
            select(AssistantRun.id)
            .where(
                AssistantRun.user_id == user_id,
                AssistantRun.executor_exited_at.is_(None),
            )
            .limit(1)
        ).first():
            raise HTTPException(409, "assistant_profile_busy")
        registry_path = config.data_dir() / "profiles.json"
        registry = (
            config.read_private_json(registry_path)
            if registry_path.exists()
            else {"profiles": {}}
        )
        if not isinstance(registry.get("profiles"), dict):
            raise HTTPException(503, "assistant_unconfigured")
        config.secure_directory(root)
        config.secure_directory(root / "profiles")
        config.secure_directory(home)
        env_path = home / ".env"
        values = _read_env(env_path) if env_path.exists() else {}
        if values:
            if any(
                not values.get(k)
                for k in ("API_SERVER_KEY", "HE_TOOL_TOKEN", "HE_API_KEY_GENERATION")
            ):
                raise HTTPException(503, "assistant_unconfigured")
        else:
            values = {
                "API_SERVER_ENABLED": "true",
                "API_SERVER_HOST": "0.0.0.0",
                "API_SERVER_PORT": "8642",
                "API_SERVER_KEY": secrets.token_urlsafe(48),
                "HE_TOOL_TOKEN": secrets.token_urlsafe(48),
                "HE_API_KEY_GENERATION": "1",
                "HE_ASSISTANT_MODEL_KEY": model["api_key"],
            }
        try:
            generation = int(values["HE_API_KEY_GENERATION"])
        except ValueError:
            raise HTTPException(503, "assistant_unconfigured") from None
        token_hash = hash_tool_token(values["HE_TOOL_TOKEN"])
        binding = ProfileBinding(
            user_id=user_id,
            profile_name=name,
            api_key=values["API_SERVER_KEY"],
            api_key_generation=generation,
            tool_token_hash=token_hash,
        )
        prior = registry["profiles"].get(str(user_id))
        record = {
            "user_id": user_id,
            "profile_name": name,
            "api_key": values["API_SERVER_KEY"],
            "api_key_generation": generation,
            "tool_token_hash": token_hash,
        }
        if prior is not None and prior != record:
            raise HTTPException(409, "assistant_profile_binding_conflict")
        row = local.get(AssistantToolIdentity, user_id)
        if row is None:
            row = AssistantToolIdentity(
                user_id=user_id,
                profile_name=name,
                tool_token_hash=token_hash,
                credential_generation=generation,
                enabled=False,
            )
            local.add(row)
        else:
            row.enabled = False
        local.flush()
        if not env_path.exists():
            config.atomic_private_write(
                env_path, "\n".join(k + "=" + v for k, v in values.items()) + "\n"
            )
        if not (home / "config.yaml").exists():
            config.atomic_private_write(home / "config.yaml", _profile_yaml(model))
        if not (home / "SOUL.md").exists():
            config.atomic_private_write(
                home / "SOUL.md",
                (config.template_dir() / "SOUL.md").read_text(encoding="utf-8"),
            )
        registry["profiles"][str(user_id)] = record
        if prior is None:
            config.atomic_private_write(registry_path, json.dumps(registry, indent=2))
        row.profile_name = name
        row.tool_token_hash = token_hash
        row.credential_generation = generation
        row.enabled = True
        row.updated_at = utcnow()
        return binding
