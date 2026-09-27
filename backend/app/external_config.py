import json
import os
from typing import Optional
from urllib.parse import urlsplit

def _get_config_path() -> str:
    db_url = os.getenv("HE_DATABASE_URL")
    if db_url and db_url.startswith("sqlite:///"):
        db_path = db_url[len("sqlite:///"):].lstrip("/")
        if db_url.startswith("sqlite:////"):
            db_path = "/" + db_path
        db_dir = os.path.dirname(db_path)
        if os.path.isdir(db_dir):
            return os.path.join(db_dir, "external_config.json")
    
    backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    config_dir = os.path.join(backend_dir, "instance")
    os.makedirs(config_dir, exist_ok=True)
    return os.path.join(config_dir, "external_config.json")

CONFIG_PATH = _get_config_path()


def _read_config() -> dict:
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _write_config(data: dict) -> None:
    config_dir = os.path.dirname(CONFIG_PATH) or "."
    os.makedirs(config_dir, mode=0o700, exist_ok=True)
    temp_path = f"{CONFIG_PATH}.tmp"
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    if os.name != "nt":
        os.chmod(temp_path, 0o600)
    os.replace(temp_path, CONFIG_PATH)


def get_external_favorites_proxy() -> Optional[str]:
    """Get the shared WNACG, X, and Pawchive proxy URL.

    The Pawchive environment variable is retained as a migration fallback for
    installations that configured its file CDN proxy before this setting was
    unified. Once the Settings page saves a value (including blank), the
    persisted value takes precedence.
    """
    config = _read_config()
    if "proxy" in config:
        proxy = config.get("proxy")
        if isinstance(proxy, str):
            return proxy.strip() or None
        return None
    return os.getenv("HE_PAWCHIVE_PROXY", "").strip() or None


def validate_external_favorites_proxy(proxy: Optional[str]) -> Optional[str]:
    """Normalize a proxy URL supported consistently by all external clients."""
    value = (proxy or "").strip()
    if not value:
        return None
    parsed = urlsplit(value)
    if (parsed.scheme != "http" or not parsed.hostname or parsed.username or parsed.password
            or parsed.path not in {"", "/"} or parsed.query or parsed.fragment):
        raise ValueError("代理地址需为不带账号密码的 HTTP 代理，例如 http://127.0.0.1:7890")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("代理端口无效") from exc
    if port is not None and not 1 <= port <= 65535:
        raise ValueError("代理端口无效")
    return value


def update_external_favorites_proxy(proxy: Optional[str]) -> Optional[str]:
    """Persist the shared external favorites proxy, including an explicit clear."""
    config = _read_config()
    val = (proxy or "").strip()
    config["proxy"] = val
    _write_config(config)
    return get_external_favorites_proxy()


# Retain the old helper names for internal extensions that may still import them.
get_global_proxy = get_external_favorites_proxy
update_global_proxy = update_external_favorites_proxy
