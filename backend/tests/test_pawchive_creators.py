import io
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock, patch

import pytest

from app.services.external.pawchive import client, creators


def row(number=1, **fields):
    return dict(id=str(number), service='patreon', name=f'Artist {number}',
                favorited=number, updated=1_700_000_000 + number, **fields)


@pytest.fixture
def directory(monkeypatch):
    instance = creators.CreatorDirectory()
    monkeypatch.setattr(creators, 'directory', instance)
    monkeypatch.setattr(creators, 'disk_path', lambda: None)
    return instance


def test_normalization_and_real_counts():
    items = creators.normalize_directory([
        row(), row(), {**row(2), 'favorited': '0', 'name': '猫'},
        {**row(3), 'favorited': True}, {**row(4), 'favorited': -2},
        {**row(5), 'service': '../invalid'}, None,
    ])
    assert len(items) == 4
    assert [x['favorite_count'] for x in items] == [1, 0, None, None]
    assert items[0]['updated_at'] == '2023-11-14T22:13:21Z'
    assert creators.timestamp('2023-11-14T22:13:21Z') == items[0]['updated_at']
    assert creators.timestamp(float('nan')) is None
    with pytest.raises(client.PawchiveError):
        creators.normalize_directory([{'service': '../invalid'}])


def test_search_rank_platform_and_pagination(directory, monkeypatch):
    raw = [row(i) for i in range(1, 66)] + [
        {**row(100), 'name': 'Ａｒｔｉｓｔ 1'},
        {**row(101), 'service': 'fanbox', 'name': '猫 Artist'},
    ]
    fetch = Mock(return_value=raw)
    monkeypatch.setattr(client, 'get_creator_directory', fetch)
    first = creators.list_creators()
    assert first['items'][0]['creator_id'] == '101'
    assert first['total'] == 67 and first['has_more']
    assert first['services'] == ['fanbox', 'patreon']
    last = creators.list_creators(page=900)
    assert last['page'] == 3 and len(last['items']) == 7 and not last['has_more']
    exact = creators.list_creators(query='Artist 1', sort='relevance')
    assert exact['items'][0]['creator_id'] == '100'  # NFKC + exact name before substring
    assert exact['items'][1]['creator_id'] == '1'
    assert creators.list_creators(query='猫', service='patreon')['total'] == 0
    assert creators.list_creators(query='101')['items'][0]['service'] == 'fanbox'
    assert creators.list_creators(sort='updated')['items'][0]['creator_id'] == '101'
    assert first['items'][0]['source_url'].startswith('https://pawchive.pw/')
    fetch.assert_called_once()
    for invalid in [dict(sort='unknown'), dict(page=0), dict(page=True), dict(query='a' * 201)]:
        with pytest.raises(client.PawchiveError):
            creators.list_creators(**invalid)


def test_missing_counts_fall_back_to_updated(directory, monkeypatch):
    monkeypatch.setattr(client, 'get_creator_directory', lambda: [
        {**row(1), 'favorited': None}, {**row(2), 'favorited': None}])
    page = creators.list_creators()
    assert not page['popularity_available'] and page['applied_sort'] == 'updated'
    assert page['items'][0]['creator_id'] == '2'


def test_empty_refresh_does_not_discard_previous_directory(directory, monkeypatch):
    directory.items = creators.normalize_directory([row()])
    directory.fetched_at = time.time() - creators.TTL - 1
    monkeypatch.setattr(client, 'get_creator_directory', lambda: [])
    previous = directory.items
    assert directory.snapshot()[0] == previous
    assert directory._refresh_lock.acquire(timeout=3)
    directory._refresh_lock.release()
    assert directory.items == previous
    assert directory.last_error.code == 'UPSTREAM_INVALID'


def test_concurrent_cold_requests_share_one_fetch(directory, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    def fetch():
        entered.set()
        assert release.wait(3)
        return [row()]
    fetcher = Mock(side_effect=fetch)
    monkeypatch.setattr(client, 'get_creator_directory', fetcher)
    with ThreadPoolExecutor(max_workers=3) as pool:
        first = pool.submit(directory.snapshot)
        assert entered.wait(3)
        second = pool.submit(directory.snapshot)
        release.set()
        assert first.result()[0] == second.result()[0]
    fetcher.assert_called_once()


def test_stale_directory_served_during_failure_and_backoff(directory, monkeypatch):
    directory.items = creators.normalize_directory([row()])
    directory.fetched_at = time.time() - creators.TTL - 1
    failure = Mock(side_effect=client.PawchiveError('UPSTREAM_UNAVAILABLE', 'offline', 502))
    monkeypatch.setattr(client, 'get_creator_directory', failure)
    items, fetched, stale = directory.snapshot()
    assert items and stale
    assert directory._refresh_lock.acquire(timeout=3)
    directory._refresh_lock.release()
    assert directory.snapshot() == (items, fetched, True)
    failure.assert_called_once()
    directory.fetched_at = time.time() - creators.MAX_STALE - 1
    with pytest.raises(client.PawchiveError, match='offline'):
        directory.snapshot()


def test_disk_cache_restored_and_requires_real_mount(tmp_path, monkeypatch):
    root = tmp_path / 'hdd'
    root.mkdir()
    path = root / '.he-manager/pawchive-creators/catalog.json'
    monkeypatch.setattr(creators, 'MOUNT_ROOT', root)
    monkeypatch.setattr(creators, 'CACHE_FILE', path)
    assert creators.disk_path() is None
    (root / '.mounted').touch()
    with patch.object(client, 'get_creator_directory', return_value=[row()]):
        original = creators.CreatorDirectory().snapshot()
    assert path.is_file()
    with patch.object(client, 'get_creator_directory', side_effect=AssertionError('should use disk')):
        assert creators.CreatorDirectory().snapshot() == original
    path.unlink()
    path.symlink_to(tmp_path / 'outside')
    assert creators.disk_path() is None


@pytest.mark.parametrize('body,content_type,declared', [
    (b'<html>blocked</html>', 'text/html', None),
    (b'{}', 'application/json', None),
    (b'[', 'application/json', None),
    (b'[]', 'application/json', str(client.CREATOR_JSON_LIMIT + 1)),
])
def test_bounded_directory_client_rejects_bad_source(body, content_type, declared):
    connection, response = Mock(), Mock()
    response.status = 200
    response.getheader.side_effect = lambda key: {'Content-Type': content_type, 'Content-Length': declared}.get(key)
    response.read.side_effect = io.BytesIO(body).read
    with patch.object(client, '_request', return_value=(connection, response)), patch.object(client, '_throttle_api'):
        with pytest.raises(client.PawchiveError):
            client.get_creator_directory()
    connection.close.assert_called_once()


def test_directory_client_uses_fixed_public_host():
    connection, response = Mock(), Mock()
    response.status = 200
    response.getheader.side_effect = lambda key: {'Content-Type': 'application/json'}.get(key)
    response.read.side_effect = io.BytesIO(json.dumps([row()]).encode()).read
    with patch.object(client, '_request', return_value=(connection, response)) as request, patch.object(client, '_throttle_api'):
        assert client.get_creator_directory()[0]['id'] == '1'
    request.assert_called_once_with(client.API_HOST, '/api/v1/creators')
    connection.close.assert_called_once()
