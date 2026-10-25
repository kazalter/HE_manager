"""Cached public author directory: name/ID search and real favorite-count ranks."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import secrets
import threading
import time
import unicodedata

from . import client, provider

logger = logging.getLogger(__name__)
MOUNT_ROOT = Path('/mnt/hdd')
CACHE_FILE = MOUNT_ROOT / '.he-manager' / 'pawchive-creators' / 'catalog.json'
TTL = 3600
MAX_STALE = 7 * 86400
PAGE_SIZE = 30


def text_key(value: str) -> str:
    return unicodedata.normalize('NFKC', value).casefold()


def timestamp(value) -> str | None:
    try:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            date = datetime.fromtimestamp(value, timezone.utc)
        elif isinstance(value, str):
            date = datetime.fromisoformat(value.replace('Z', '+00:00'))
            if date.tzinfo is None:
                date = date.replace(tzinfo=timezone.utc)
        else:
            return None
        return date.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')
    except (ValueError, OverflowError, OSError):
        return None


def normalize_directory(raw: list) -> tuple[dict, ...]:
    if not isinstance(raw, list) or len(raw) > 250_000:
        raise client.PawchiveError('UPSTREAM_INVALID', 'Pawchive 作者目录格式无效', 502)
    items, seen = [], set()
    for row in raw:
        if not isinstance(row, dict):
            continue
        service, creator_id = str(row.get('service') or ''), str(row.get('id') or '')
        if not provider.ID.fullmatch(service) or not provider.ID.fullmatch(creator_id):
            continue
        key = (service, creator_id)
        if key in seen:
            continue
        seen.add(key)
        count = row.get('favorited')
        if isinstance(count, str) and count.isascii() and count.isdigit() and len(count) < 15:
            count = int(count)
        if type(count) is not int or not 0 <= count < 10**14:
            count = None
        items.append(dict(service=service, creator_id=creator_id,
            creator_name=str(row.get('name') or creator_id)[:240],
            updated_at=timestamp(row.get('updated')), favorite_count=count))
    if raw and not items:
        raise client.PawchiveError('UPSTREAM_INVALID', 'Pawchive 作者目录没有有效数据', 502)
    return tuple(items)


def disk_path() -> Path | None:
    # The metadata survives backend restarts, but never falls back to the system disk.
    if not (MOUNT_ROOT / '.mounted').is_file():
        return None
    if any(p.is_symlink() for p in (MOUNT_ROOT, CACHE_FILE.parent.parent, CACHE_FILE.parent, CACHE_FILE)):
        return None
    return CACHE_FILE


class CreatorDirectory:
    def __init__(self):
        self.items: tuple[dict, ...] | None = None
        self.fetched_at = 0.0
        self.retry_at = 0.0
        self.last_error: client.PawchiveError | None = None
        self._refresh_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._loaded_disk = False

    def _load_disk(self):
        with self._state_lock:
            if self._loaded_disk:
                return
            self._loaded_disk = True
            path = disk_path()
            if path is None:
                return
            try:
                with path.open('rb') as source:
                    body = source.read(client.CREATOR_JSON_LIMIT + 1)
                if len(body) > client.CREATOR_JSON_LIMIT:
                    return
                raw = json.loads(body)
                fetched = raw['fetched_at']
                if (raw.get('version') != 1 or type(fetched) not in (int, float)
                        or not 0 <= time.time() - fetched <= MAX_STALE):
                    return
                # Revalidate disk metadata with the same ID/count rules as the source.
                rows = [dict(id=x.get('creator_id'), service=x.get('service'), name=x.get('creator_name'),
                             updated=x.get('updated_at'), favorited=x.get('favorite_count')) for x in raw['items']]
                self.items, self.fetched_at = normalize_directory(rows), fetched
            except (OSError, ValueError, KeyError, TypeError, AttributeError, client.PawchiveError):
                return

    def _refresh(self):
        try:
            items = normalize_directory(client.get_creator_directory())
            if not items:
                raise client.PawchiveError('UPSTREAM_INVALID', 'Pawchive 作者目录暂时没有有效数据', 502)
            fetched = time.time()
            with self._state_lock:
                self.items, self.fetched_at, self.last_error = items, fetched, None
                self.retry_at = 0.0
            path = disk_path()
            if path is not None:
                try:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    body = json.dumps(dict(version=1, fetched_at=fetched, items=items), ensure_ascii=False,
                                      separators=(',', ':')).encode()
                    if len(body) <= client.CREATOR_JSON_LIMIT:
                        temp = path.with_name(f'.catalog-{secrets.token_hex(8)}.tmp')
                        try:
                            with temp.open('xb') as output:
                                output.write(body)
                            temp.replace(path)
                        finally:
                            temp.unlink(missing_ok=True)
                except OSError:
                    logger.warning('Pawchive creator directory disk cache unavailable')
        except client.PawchiveError as exc:
            try:
                retry = max(30, min(3600, int(exc.retry_after or '30')))
            except ValueError:
                retry = 30
            if exc.code == 'ACCESS_RESTRICTED':
                retry = max(retry, 300)
            with self._state_lock:
                self.last_error, self.retry_at = exc, time.time() + retry
        except Exception:
            with self._state_lock:
                self.last_error = client.PawchiveError('UPSTREAM_UNAVAILABLE', '暂时无法同步 Pawchive 作者目录', 502)
                self.retry_at = time.time() + 30
        finally:
            self._refresh_lock.release()

    def snapshot(self) -> tuple[tuple[dict, ...], float, bool]:
        self._load_disk()
        with self._state_lock:
            items, fetched = self.items, self.fetched_at
            fresh = time.time() - fetched < TTL
            retry = time.time() >= self.retry_at
        if items is not None and time.time() - fetched <= MAX_STALE:
            if not fresh and retry and self._refresh_lock.acquire(blocking=False):
                threading.Thread(target=self._refresh, name='pawchive-creators', daemon=True).start()
            return items, fetched, not fresh
        if retry and self._refresh_lock.acquire(blocking=False):
            self._refresh()
        elif not self._refresh_lock.acquire(timeout=25):
            raise client.PawchiveError('DIRECTORY_LOADING', '作者目录正在首次同步，请稍后重试', 503)
        else:
            self._refresh_lock.release()
        with self._state_lock:
            if self.items is not None and time.time() - self.fetched_at <= MAX_STALE:
                return self.items, self.fetched_at, time.time() - self.fetched_at >= TTL
            raise self.last_error or client.PawchiveError('UPSTREAM_UNAVAILABLE', '暂时无法读取 Pawchive 作者目录', 502)


directory = CreatorDirectory()


def creator_dto(item: dict) -> dict:
    return {**item, 'source_url': f"https://pawchive.pw/{item['service']}/user/{item['creator_id']}"}


def list_creators(*, query: str = '', service: str = '', sort: str = 'popular', page: int = 1) -> dict:
    query, service = query.strip(), service.strip()
    if len(query) > 200 or sort not in {'popular', 'updated', 'relevance'} or type(page) is not int or not 1 <= page <= 10000:
        raise client.PawchiveError('INVALID_REQUEST', '作者搜索条件无效', 400)
    if service:
        provider.validate_id(service)
    snapshot, fetched, stale = directory.snapshot()
    services = sorted({x['service'] for x in snapshot})
    tokens = text_key(query).split()
    items = [x for x in snapshot if (not service or x['service'] == service)
             and all(t in text_key(f"{x['creator_name']} {x['creator_id']} {x['service']}") for t in tokens)]
    popularity_available = any(x['favorite_count'] is not None for x in items)
    applied_sort = 'updated' if sort == 'popular' and not popularity_available else sort
    def stable(x):
        return text_key(x['creator_name']), x['service'], x['creator_id']
    if applied_sort == 'updated':
        items.sort(key=stable)
        items.sort(key=lambda x: x['updated_at'] or '', reverse=True)
    elif applied_sort == 'relevance' and query:
        q = text_key(query)
        items.sort(key=lambda x: (0 if q in {text_key(x['creator_name']), text_key(x['creator_id'])} else
                                 1 if text_key(x['creator_name']).startswith(q) else 2,
                                 -(x['favorite_count'] if x['favorite_count'] is not None else -1), *stable(x)))
    else:
        items.sort(key=lambda x: (-(x['favorite_count'] if x['favorite_count'] is not None else -1), *stable(x)))
    total = len(items)
    current = min(page, max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE))
    offset = (current - 1) * PAGE_SIZE
    return dict(items=[creator_dto(x) for x in items[offset:offset + PAGE_SIZE]], total=total,
                page=current, page_size=PAGE_SIZE, has_more=offset + PAGE_SIZE < total,
                services=services, applied_sort=applied_sort, popularity_available=popularity_available,
                fetched_at=datetime.fromtimestamp(fetched, timezone.utc).isoformat(), stale=stale)
