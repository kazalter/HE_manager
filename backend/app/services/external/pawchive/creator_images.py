"""Persistent creator icon/banner cache and MIME validation for Pawchive."""
from __future__ import annotations

from collections import deque
import io
import json
import logging
from pathlib import Path
import secrets
import threading
import time

from PIL import Image

from . import client, provider

logger = logging.getLogger(__name__)
MOUNT_ROOT = Path("/mnt/hdd")
ARTWORK_ROOT = MOUNT_ROOT / ".he-manager" / "pawchive-creators" / "artwork"
ALLOWED_KINDS = frozenset({"icons", "banners"})
ALLOWED_MIMES = frozenset({"image/jpeg", "image/png", "image/webp", "image/gif", "image/avif"})
_SNIFFABLE_MIMES = frozenset({"", "application/octet-stream", "binary/octet-stream"})
_PIL_MIME = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
    "GIF": "image/gif",
    "AVIF": "image/avif",
}
MAX_BYTES = 4 * 1024 * 1024
_META_LIMIT = 4096
_FAVORITES_LIMIT = 1024 * 1024
MISSING_TTL = 7 * 86400
PREFETCH_INTERVAL = 0.25

_state_lock = threading.Lock()
_scopes: dict[str, set[tuple[str, str]]] = {}
_loaded_root: Path | None = None

_inflight_guard = threading.Lock()
_inflight_locks: dict[tuple[str, str, str], threading.Lock] = {}

_queue_lock = threading.Lock()
_queue: deque[tuple[str, str, str]] = deque()
_queued: set[tuple[str, str, str]] = set()
_worker: threading.Thread | None = None


def _disk_root() -> Path | None:
    if not (MOUNT_ROOT / ".mounted").is_file():
        return None
    try:
        mount_resolved = MOUNT_ROOT.resolve()
        artwork_resolved = ARTWORK_ROOT.resolve()
    except OSError:
        return None
    if (
        MOUNT_ROOT.is_symlink()
        or ARTWORK_ROOT.is_symlink()
        or ARTWORK_ROOT.parent.is_symlink()
        or ARTWORK_ROOT.parent.parent.is_symlink()
        or not artwork_resolved.is_relative_to(mount_resolved)
    ):
        return None
    return ARTWORK_ROOT


def _key_lock(key: tuple[str, str, str]) -> threading.Lock:
    with _inflight_guard:
        lock = _inflight_locks.get(key)
        if lock is None:
            lock = threading.Lock()
            _inflight_locks[key] = lock
        return lock


def _resolve_image_mime(raw_content_type: str | None, body: bytes) -> str:
    if not body or len(body) > MAX_BYTES:
        raise client.PawchiveError("UPSTREAM_INVALID", "来源图片大小无效", 502)
    content_type = (raw_content_type or "").split(";", 1)[0].strip().lower()
    if content_type in ALLOWED_MIMES:
        return content_type
    if content_type in _SNIFFABLE_MIMES:
        try:
            with Image.open(io.BytesIO(body)) as image:
                fmt = (image.format or "").upper()
        except (OSError, ValueError, Image.DecompressionBombError):
            fmt = ""
        resolved = _PIL_MIME.get(fmt)
        if resolved:
            return resolved
    raise client.PawchiveError("UPSTREAM_INVALID", "来源返回了无效的图片", 502)


def _entry_paths(root: Path, kind: str, service: str, creator_id: str) -> tuple[Path, Path, Path, Path]:
    kind_dir = root / kind
    service_dir = kind_dir / service
    return (
        kind_dir,
        service_dir,
        service_dir / f"{creator_id}.img",
        service_dir / f"{creator_id}.json",
    )


def _has_symlink(paths: tuple[Path, ...]) -> bool:
    return any(path.is_symlink() for path in paths)


def _atomic_write(path: Path, data: bytes) -> None:
    temp = path.with_name(f".{path.name}.{secrets.token_hex(6)}.tmp")
    try:
        with temp.open("xb") as handle:
            handle.write(data)
        temp.chmod(0o600)
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def _ensure_dirs(root: Path, *dirs: Path) -> bool:
    mount_resolved = MOUNT_ROOT.resolve()
    for directory in (*reversed(root.parents), root, *dirs):
        if directory == MOUNT_ROOT or not directory.resolve().is_relative_to(mount_resolved):
            continue
        if directory.is_symlink():
            return False
        directory.mkdir(mode=0o700, exist_ok=True)
    return True


def _read_disk(root: Path | None, kind: str, service: str, creator_id: str) -> tuple[str, bytes | None, str | None] | None:
    if root is None:
        return None
    kind_dir, service_dir, img_path, meta_path = _entry_paths(root, kind, service, creator_id)
    if _has_symlink((kind_dir, service_dir, img_path, meta_path)):
        return None
    if not meta_path.is_file():
        return None
    try:
        with meta_path.open("rb") as handle:
            raw = handle.read(_META_LIMIT + 1)
        if len(raw) > _META_LIMIT:
            return None
        meta = json.loads(raw)
        if not isinstance(meta, dict) or meta.get("version") != 1:
            return None
        status = meta.get("status")
        if status == "missing":
            fetched_at = meta.get("fetched_at")
            if type(fetched_at) in (int, float) and 0 <= time.time() - fetched_at <= MISSING_TTL:
                return ("missing", None, None)
            return None
        if status == "ok":
            content_type = meta.get("content_type")
            if content_type not in ALLOWED_MIMES or not img_path.is_file():
                return None
            size = img_path.stat().st_size
            if size <= 0 or size > MAX_BYTES:
                return None
            with img_path.open("rb") as handle:
                body = handle.read(MAX_BYTES + 1)
            if not body or len(body) > MAX_BYTES:
                return None
            return ("ok", body, content_type)
    except (OSError, ValueError, TypeError):
        return None
    return None


def _write_disk_image(root: Path, kind: str, service: str, creator_id: str, body: bytes, content_type: str) -> None:
    kind_dir, service_dir, img_path, meta_path = _entry_paths(root, kind, service, creator_id)
    try:
        if not _ensure_dirs(root, kind_dir, service_dir) or _has_symlink((img_path, meta_path)):
            return
        _atomic_write(img_path, body)
        meta = json.dumps(
            {"version": 1, "status": "ok", "content_type": content_type, "fetched_at": time.time()},
            separators=(",", ":"),
        ).encode("utf-8")
        _atomic_write(meta_path, meta)
    except OSError:
        logger.warning("Pawchive creator image write failed for %s/%s/%s", kind, service, creator_id, exc_info=True)


def _write_disk_missing(root: Path, kind: str, service: str, creator_id: str) -> None:
    kind_dir, service_dir, img_path, meta_path = _entry_paths(root, kind, service, creator_id)
    try:
        if not _ensure_dirs(root, kind_dir, service_dir) or _has_symlink((img_path, meta_path)):
            return
        img_path.unlink(missing_ok=True)
        meta = json.dumps(
            {"version": 1, "status": "missing", "fetched_at": time.time()},
            separators=(",", ":"),
        ).encode("utf-8")
        _atomic_write(meta_path, meta)
    except OSError:
        logger.warning("Pawchive creator image missing marker write failed for %s/%s/%s", kind, service, creator_id, exc_info=True)


def _delete_disk(root: Path | None, service: str, creator_id: str) -> None:
    if root is None:
        return
    for kind in ALLOWED_KINDS:
        kind_dir, service_dir, img_path, meta_path = _entry_paths(root, kind, service, creator_id)
        if _has_symlink((kind_dir, service_dir, img_path, meta_path)):
            continue
        for target in (meta_path, img_path):
            try:
                target.unlink(missing_ok=True)
            except OSError:
                pass


def _load_favorites_locked(root: Path | None) -> None:
    global _loaded_root
    if root is None:
        _loaded_root = None
        return
    if _loaded_root == root:
        return
    _scopes.clear()
    _loaded_root = root
    fav_file = root / "favorites.json"
    if root.is_symlink() or fav_file.is_symlink() or not fav_file.is_file():
        return
    try:
        with fav_file.open("rb") as handle:
            raw = handle.read(_FAVORITES_LIMIT + 1)
        if len(raw) > _FAVORITES_LIMIT:
            return
        data = json.loads(raw)
        if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("scopes"), dict):
            return
        for scope, entries in data["scopes"].items():
            if not isinstance(scope, str) or not isinstance(entries, list):
                continue
            parsed: set[tuple[str, str]] = set()
            for pair in entries:
                if (
                    isinstance(pair, list)
                    and len(pair) == 2
                    and isinstance(pair[0], str)
                    and isinstance(pair[1], str)
                    and provider.ID.fullmatch(pair[0])
                    and provider.ID.fullmatch(pair[1])
                ):
                    parsed.add((pair[0], pair[1]))
            if parsed:
                _scopes[scope] = parsed
    except (OSError, ValueError, TypeError):
        logger.warning("Pawchive favorite artwork index unavailable", exc_info=True)


def _persist_favorites_locked(root: Path | None) -> None:
    if root is None:
        return
    fav_file = root / "favorites.json"
    try:
        if not _ensure_dirs(root) or fav_file.is_symlink():
            return
        payload = {
            "version": 1,
            "scopes": {
                scope: sorted([[svc, cid] for svc, cid in pairs])
                for scope, pairs in _scopes.items()
                if pairs
            },
        }
        _atomic_write(fav_file, json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    except OSError:
        logger.warning("Pawchive favorite artwork index write failed", exc_info=True)


def _is_favorite(root: Path | None, service: str, creator_id: str) -> bool:
    if root is None:
        return False
    with _state_lock:
        _load_favorites_locked(root)
        return any((service, creator_id) in pairs for pairs in _scopes.values())


def get_image(kind: str, service: str, creator_id: str, *, persist: bool = False) -> tuple[bytes, str, str]:
    if kind not in ALLOWED_KINDS:
        raise client.PawchiveError("INVALID_REQUEST", "非法图片类型", 400)
    service = provider.validate_id(service)
    creator_id = provider.validate_id(creator_id)

    root = _disk_root()
    cached = _read_disk(root, kind, service, creator_id)
    if cached is not None:
        status, body, content_type = cached
        if status == "missing":
            raise client.PawchiveError("NOT_FOUND", "来源内容不存在", 404)
        assert body is not None and content_type is not None
        return body, content_type, "HIT"

    with _key_lock((kind, service, creator_id)):
        root = _disk_root()
        cached = _read_disk(root, kind, service, creator_id)
        if cached is not None:
            status, body, content_type = cached
            if status == "missing":
                raise client.PawchiveError("NOT_FOUND", "来源内容不存在", 404)
            assert body is not None and content_type is not None
            return body, content_type, "HIT"

        should_persist = root is not None and (persist or _is_favorite(root, service, creator_id))
        connection, upstream = client._request(client.API_HOST, f"/{kind}/{service}/{creator_id}")
        try:
            try:
                client._raise_for_status(upstream)
            except client.PawchiveError as exc:
                if exc.code == "NOT_FOUND" and should_persist and root is not None:
                    _write_disk_missing(root, kind, service, creator_id)
                raise
            body = upstream.read(MAX_BYTES + 1)
            if len(body) > MAX_BYTES:
                raise client.PawchiveError("UPSTREAM_INVALID", "来源图片过大", 502)
            content_type = _resolve_image_mime(upstream.getheader("Content-Type"), body)
        finally:
            connection.close()

        if should_persist and root is not None:
            _write_disk_image(root, kind, service, creator_id, body, content_type)
        return body, content_type, "MISS"


def _prefetch_worker() -> None:
    global _worker
    while True:
        with _queue_lock:
            if not _queue:
                _worker = None
                return
            item = _queue.popleft()
            _queued.discard(item)
        kind, service, creator_id = item
        root = _disk_root()
        if root is None:
            with _queue_lock:
                _queue.clear()
                _queued.clear()
                _worker = None
            return
        if not _is_favorite(root, service, creator_id):
            continue
        if _read_disk(root, kind, service, creator_id) is not None:
            continue
        try:
            get_image(kind, service, creator_id, persist=True)
        except client.PawchiveError as exc:
            if exc.code in {"RATE_LIMITED", "ACCESS_RESTRICTED", "UPSTREAM_UNAVAILABLE"}:
                logger.warning("Pawchive creator artwork prefetch paused (%s)", exc.code)
                with _queue_lock:
                    _queue.clear()
                    _queued.clear()
                    _worker = None
                return
            if exc.code != "NOT_FOUND":
                logger.warning("Pawchive creator artwork prefetch failed for %s/%s/%s (%s)", kind, service, creator_id, exc.code)
        except Exception:
            logger.warning("Pawchive creator artwork prefetch error for %s/%s/%s", kind, service, creator_id, exc_info=True)
        with _queue_lock:
            has_more = bool(_queue)
        if has_more and PREFETCH_INTERVAL > 0:
            time.sleep(PREFETCH_INTERVAL)


def enqueue_favorites(creators: list[tuple[str, str]]) -> None:
    root = _disk_root()
    if root is None or not creators:
        return
    # Queue icons before banners so creator avatars become ready first.
    candidates: list[tuple[str, str, str]] = []
    for kind in ("icons", "banners"):
        for service, creator_id in creators:
            if _read_disk(root, kind, service, creator_id) is None:
                candidates.append((kind, service, creator_id))
    if not candidates:
        return
    global _worker
    with _queue_lock:
        for item in candidates:
            if item not in _queued:
                _queued.add(item)
                _queue.append(item)
        if _worker is None or not _worker.is_alive():
            _worker = threading.Thread(target=_prefetch_worker, name="pawchive-creator-artwork", daemon=True)
            _worker.start()


def sync_favorites(scope: str, items: list[dict]) -> None:
    pairs: set[tuple[str, str]] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        service = str(item.get("service") or "")
        creator_id = str(item.get("creator_id") or "")
        if provider.ID.fullmatch(service) and provider.ID.fullmatch(creator_id):
            pairs.add((service, creator_id))
    root = _disk_root()
    with _state_lock:
        _load_favorites_locked(root)
        previous = _scopes.get(scope, set())
        if pairs:
            _scopes[scope] = pairs
        else:
            _scopes.pop(scope, None)
        removed = [
            key
            for key in (previous - pairs)
            if not any(key in scoped for scoped in _scopes.values())
        ]
        _persist_favorites_locked(root)
    if root is not None:
        for service, creator_id in removed:
            _delete_disk(root, service, creator_id)
        if pairs:
            enqueue_favorites(sorted(pairs))


def mark_favorite(scope: str, service: str, creator_id: str, favorite: bool) -> None:
    service = provider.validate_id(service)
    creator_id = provider.validate_id(creator_id)
    key = (service, creator_id)
    root = _disk_root()
    with _state_lock:
        _load_favorites_locked(root)
        current = set(_scopes.get(scope, ()))
        if favorite:
            current.add(key)
        else:
            current.discard(key)
        if current:
            _scopes[scope] = current
        else:
            _scopes.pop(scope, None)
        still_favorite = any(key in scoped for scoped in _scopes.values())
        _persist_favorites_locked(root)
    if root is not None:
        if favorite:
            enqueue_favorites([key])
        elif not still_favorite:
            _delete_disk(root, service, creator_id)


def warm_persisted_favorites() -> None:
    root = _disk_root()
    if root is None:
        return
    with _state_lock:
        _load_favorites_locked(root)
        pairs = sorted({key for scoped in _scopes.values() for key in scoped})
    if pairs:
        enqueue_favorites(pairs)
