"""Durable discard identities, explicit deletion previews, and retryable cleanup.

The tombstone and reference removals commit BEFORE deleting bytes. Failed or
interrupted cleanup stays visible and retryable; scans/downloads remain blocked.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import stat
import uuid

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session, object_session

from .. import database, media_cleanup, models
from .media_operation_guard import acquire_media_operation
from .thumbnails import remove_cover_thumbnails, remove_manga_page_thumbnails

logger = logging.getLogger(__name__)
MAX_CLEANUP_ENTRIES_BYTES = 16 * 1024 * 1024
_DIRECTORY_FDS = (
    all(fn in os.supports_dir_fd for fn in (os.open, os.stat, os.unlink, os.rmdir))
    and hasattr(os, 'O_DIRECTORY') and hasattr(os, 'O_NOFOLLOW')
)

def path_key(path):
    return 'path:' + hashlib.sha256(os.path.normcase(os.path.abspath(path)).encode()).hexdigest()

def external_key(item):
    return f'{item.source_type or "wnacg"}:{item.external_id}'

def has_identity(db, key):
    return db.get(models.DiscardedIdentity, key) is not None

def external_discarded_ids(items, db):
    keys = {external_key(item) for item in items}
    if not keys:
        return set()
    found = {row[0] for row in db.query(models.DiscardedIdentity.key).filter(models.DiscardedIdentity.key.in_(keys)).all()}
    return {item.id for item in items if external_key(item) in found}

def ensure_external_download_allowed(item):
    db = object_session(item)
    if db is not None and has_identity(db, external_key(item)):
        raise HTTPException(409, '此内容已丢弃；请先在丢弃记录中允许重新下载')

def discarded_paths(db):
    paths = set()
    for row in db.query(models.DiscardedContent.targets_json).all():
        for target in json.loads(row[0]):
            paths.add(os.path.normcase(os.path.abspath(target['path'])))
    return paths

def path_is_discarded(path, paths):
    current = os.path.normcase(os.path.abspath(path))
    while True:
        if current in paths:
            return True
        parent = os.path.dirname(current)
        if parent == current:
            return False
        current = parent

def discarded_source_files(root, files, identities):
    """Recognize persisted source markers even after files are relocated."""
    blocked = set()
    for marker in ('source.txt', 'tracks.json', 'info.json'):
        if marker not in files:
            continue
        path = os.path.join(root, marker)
        if os.path.islink(path):
            continue
        try:
            with open(path, encoding='utf-8', errors='replace') as fp:
                text = fp.read(262145)
            if len(text) > 262144:
                continue
            if marker == 'source.txt':
                aid = re.search(r'(?:photos-(?:index|item|download)-aid-|[?&]aid=)(\d+)', text)
                if aid and f'wnacg:{aid.group(1)}' in identities:
                    return True, set()
            else:
                data = json.loads(text)
                if not isinstance(data, dict):
                    continue
                if marker == 'tracks.json':
                    work = re.search(r'/work/(?:RJ)?(\d+)', data.get('url') or '')
                    if work and f'asmr:{work.group(1)}' in identities:
                        return True, set()
                else:
                    tweet_id = str(data.get('tweet_id') or '')
                    if f'x:{tweet_id}:*' in identities:
                        return True, set()
                    for media in data.get('media') or []:
                        if isinstance(media, dict) and f'x:{tweet_id}:{media.get("media_index")}' in identities:
                            blocked.add(os.path.basename(media.get('local_path') or ''))
        except (OSError, ValueError, TypeError):
            continue
    return False, blocked

def _inside(path, root):
    try:
        return os.path.commonpath([path, root]) == root and path != root
    except ValueError:
        return False

def _entry_fingerprint(info):
    return [stat.S_IFMT(info.st_mode), info.st_dev, info.st_ino, info.st_mtime_ns, info.st_size]

def _same_entry(expected, actual):
    if not isinstance(expected, list) or len(expected) != 5:
        return False
    # Removing children changes directory timestamps/size. Its identity must
    # remain stable, while every remaining file must still match in full.
    if expected[0] == stat.S_IFDIR:
        return expected[:3] == actual[:3]
    return expected == actual

def _safe_target(path, root):
    if not path or not root or not os.path.isabs(path) or not os.path.isabs(root):
        raise HTTPException(409, '删除目标没有可验证的媒体库目录')
    path, root = os.path.abspath(path), os.path.abspath(root)
    from .storage_guard import ensure_folder_scannable
    valid, _ = ensure_folder_scannable(root)
    if not valid or not os.path.isdir(root):
        raise HTTPException(409, '媒体存储不可用，请连接或挂载媒体目录后再删除')
    if not _inside(path, root) or os.path.realpath(root) != root or os.path.realpath(path) != path:
        raise HTTPException(409, '拒绝删除媒体库根目录、范围外路径或符号链接')
    current = path
    while current != root:
        if os.path.islink(current):
            raise HTTPException(409, '拒绝删除符号链接或含符号链接的路径')
        current = os.path.dirname(current)
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        info = None
    if info and not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):
        raise HTTPException(409, '只能删除普通文件或媒体目录')
    tree_hash = None
    total_size = 0
    file_count = 0
    entries = {}
    entries_bytes = 0
    if info and stat.S_ISDIR(info.st_mode):
        digest = hashlib.sha256()
        for directory, dirs, files in os.walk(path, followlinks=False):
            dirs.sort()
            for name in sorted(dirs + files):
                child = os.path.join(directory, name)
                child_stat = os.lstat(child)
                relative = os.path.relpath(child, path)
                fingerprint = _entry_fingerprint(child_stat)
                entries_bytes += len(json.dumps([relative, fingerprint], ensure_ascii=False).encode())
                if entries_bytes > MAX_CLEANUP_ENTRIES_BYTES:
                    raise HTTPException(409, '目录清理快照超过预览上限，请分批处理')
                entries[relative] = fingerprint
                file_count += 1
                if file_count > 100000:
                    raise HTTPException(409, '目录项目超过删除预览上限，请分批处理')
                digest.update(json.dumps([os.path.relpath(child, path), child_stat.st_dev, child_stat.st_ino,
                    child_stat.st_mode, child_stat.st_size, child_stat.st_mtime_ns]).encode())
                if stat.S_ISREG(child_stat.st_mode):
                    total_size += child_stat.st_size
        tree_hash = digest.hexdigest()
    elif info:
        total_size, file_count = info.st_size, 1
    return {'tree_hash': tree_hash, 'entries': entries, 'total_size': total_size, 'file_count': file_count, 'path': path, 'root': root, 'relative_path': os.path.relpath(path, root),
            'exists': info is not None, 'is_directory': bool(info and stat.S_ISDIR(info.st_mode)),
            'fingerprint': None if info is None else [info.st_dev, info.st_ino, info.st_mtime_ns, info.st_size]}

def _media_source_keys(media, db):
    keys = {path_key(media.absolute_path)}
    url = media.source_url or ''
    if not url and os.path.isdir(media.absolute_path or ''):
        marker = os.path.join(media.absolute_path, 'source.txt')
        if os.path.isfile(marker) and not os.path.islink(marker):
            with open(marker, encoding='utf-8', errors='replace') as fp:
                url = fp.read(4096)
    aid = re.search(r'(?:photos-(?:index|item|download)-aid-|[?&]aid=)(\d+)', url)
    if aid:
        keys.add('wnacg:' + aid.group(1))
    if media.source_site == 'asmr':
        work = re.search(r'/work/(\d+)', url)
        if work:
            keys.add('asmr:' + work.group(1))
    for item in db.query(models.XMediaItem).filter(or_(
            models.XMediaItem.library_media_id == media.id,
            models.XMediaItem.local_path == media.absolute_path)).all():
        keys.add(f'x:{item.post.tweet_id}:{item.media_index}')
    for item in db.query(models.PawchiveAttachment).filter(models.PawchiveAttachment.media_id == media.id).all():
        keys.add(f'pawchive:{item.post.service}:{item.post.creator_id}:{item.post.post_id}:{item.attachment_key}')
    return keys

def build_plan(db, kind, target_id):
    media_rows, paths, keys, x_post_ids = [], [], set(), []
    source_type = 'local'
    if kind == 'media':
        media = db.get(models.Media, target_id)
        if media is None:
            raise HTTPException(404, '媒体不存在或已删除')
        media_rows = [media]
        title, source_type = media.title or media.relative_path or str(media.id), media.source_site or 'local'
    elif kind == 'external':
        item = db.get(models.ExternalFavoriteItem, target_id)
        if item is None:
            raise HTTPException(404, '收藏不存在')
        ensure_external_download_allowed(item)
        title, source_type = item.title or str(item.id), item.source_type or 'wnacg'
        keys.add(external_key(item))
        from .external.covers import external_item_download_dir, external_item_legacy_wnacg_download_dir
        if item.source and item.source.download_root_path:
            root = os.path.abspath(os.path.expanduser(item.source.download_root_path))
            candidates = [external_item_download_dir(item, item.source)]
            if source_type != 'asmr':
                candidates.append(external_item_legacy_wnacg_download_dir(item, item.source))
            for path in set(candidates):
                paths.append(_safe_target(path, root))
        media_rows = db.query(models.Media).filter(or_(
            (models.Media.source_url == item.url) & (models.Media.source_site == item.source_type),
            models.Media.absolute_path.in_([p['path'] for p in paths]))).all()
    elif kind == 'x_post':
        post = db.get(models.XPost, target_id)
        if post is None:
            raise HTTPException(404, 'X 帖子不存在')
        if has_identity(db, f'x:{post.tweet_id}:*'):
            raise HTTPException(409, '这条 X 帖子已丢弃')
        title, source_type = (post.full_text or f'@{post.author_screen_name or "x"} · {post.tweet_id}')[:200], 'x'
        keys.add(f'x:{post.tweet_id}:*')
        posts = db.query(models.XPost).filter(models.XPost.tweet_id == post.tweet_id).all()
        from ..x_import.storage import x_root_dir
        ids = set()
        for copy in posts:
            x_post_ids.append(copy.id)
            for item in copy.media_items:
                keys.add(f'x:{copy.tweet_id}:{item.media_index}')
                if item.library_media_id:
                    ids.add(item.library_media_id)
                if item.local_path:
                    linked = db.get(models.Media, item.library_media_id) if item.library_media_id else None
                    if linked and linked.folder and linked.absolute_path == item.local_path:
                        root = linked.folder.path
                    else:
                        root = x_root_dir(copy.source.download_root_path) if copy.source.download_root_path else None
                    paths.append(_safe_target(item.local_path, root))
        media_rows = db.query(models.Media).filter(or_(models.Media.id.in_(ids),
            models.Media.absolute_path.in_([p['path'] for p in paths]))).all()
    else:
        raise HTTPException(400, '未知删除类型')

    for media in media_rows:
        if not media.folder:
            raise HTTPException(409, '媒体没有可验证的媒体库目录')
        paths.append(_safe_target(media.absolute_path, media.folder.path))
        keys.update(_media_source_keys(media, db))
    by_path = {p['path']: p for p in paths}
    targets = [p for p in by_path.values() if not any(
        other['is_directory'] and _inside(p['path'], other['path']) for other in by_path.values())]
    targets.sort(key=lambda p: p['path'])
    for target in targets:
        keys.add(path_key(target['path']))
    if source_type == 'local' and any(k.startswith('wnacg:') for k in keys):
        source_type = 'wnacg'
    if source_type == 'local' and any(k.startswith('x:') for k in keys):
        source_type = 'x'
    ids = {media.id for media in media_rows}
    # Never let deleting a work folder silently remove another library entry.
    for row in db.query(models.Media.id, models.Media.absolute_path).all():
        if not row.absolute_path:
            continue
        if row.id not in ids and any(row.absolute_path == p['path'] or _inside(os.path.abspath(row.absolute_path), p['path']) for p in targets):
            raise HTTPException(409, '目录内还有其他媒体记录，请先分别处理；未删除任何内容')
    plan = {'kind': kind, 'target_id': target_id, 'title': title, 'source_type': source_type,
            'media': [{'id': m.id, 'path': m.absolute_path, 'source_url': m.source_url,
                       'source_site': m.source_site, 'cover_path': m.cover_path} for m in media_rows],
            'targets': targets, 'keys': sorted(keys), 'x_post_ids': x_post_ids,
            'file_size': sum(int(p['total_size']) for p in targets)}
    plan['preview_hash'] = hashlib.sha256(json.dumps(plan, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    return plan

def public_preview(plan):
    return {'title': plan['title'], 'source_type': plan['source_type'], 'preview_hash': plan['preview_hash'],
            'media_count': len(plan['media']), 'file_size': plan['file_size'],
            'files': [{k: p[k] for k in ('relative_path', 'exists', 'is_directory')} for p in plan['targets']],
            'scope': '整条 X 帖子的本地附件' if plan['kind'] == 'x_post' else '当前内容',
            'message': '删除本地文件，保留丢弃记录；以后扫描、同步和下载会跳过此内容。不会取消网站上的收藏。'}

def serialize_record(record):
    return {'id': record.id, 'title': record.title, 'source_type': record.source_type,
            'status': 'discarded', 'discarded_at': record.discarded_at,
            'media_count': record.media_count, 'file_size': record.file_size,
            'media_ids': json.loads(record.media_ids_json),
            'cleanup_status': record.cleanup_status, 'cleanup_error': record.cleanup_error}

def _cleanup_directory(target, current):
    expected = target.get('entries')
    if expected is None:
        # Old records have no per-entry evidence. Only an unchanged tree can
        # establish the allowlist; never approve today's contents on a retry.
        if current['tree_hash'] != target.get('tree_hash'):
            raise HTTPException(409, '删除目录已变化，拒绝清理未确认的内容')
    elif not isinstance(expected, dict) or any(
        not _same_entry(expected.get(name), fingerprint)
        for name, fingerprint in current['entries'].items()
    ):
        raise HTTPException(409, '删除目录已变化，拒绝清理新增或修改的文件')

    children = {}
    for relative, fingerprint in current['entries'].items():
        children.setdefault(os.path.dirname(relative), []).append(
            (os.path.basename(relative), relative, fingerprint))

    def remove(base, name, relative, fingerprint, parent_fd=None):
        path = os.path.join(base, name)
        location = name if parent_fd is not None else path

        def check():
            info = os.stat(location, dir_fd=parent_fd, follow_symlinks=False)
            if not _same_entry(fingerprint, _entry_fingerprint(info)):
                raise HTTPException(409, '删除目标已变化，拒绝清理新文件')

        try:
            if not _DIRECTORY_FDS and os.path.realpath(base) != base:
                raise HTTPException(409, '拒绝清理符号链接或目录连接内的文件')
            check()
        except FileNotFoundError:
            return  # An earlier attempt (or the user) already removed it.
        if fingerprint[0] == stat.S_IFDIR:
            if not _DIRECTORY_FDS:
                if os.path.realpath(path) != path:
                    raise HTTPException(409, '拒绝清理符号链接或目录连接')
                for child, rel, entry in children.get(relative, []):
                    remove(path, child, rel, entry)
            else:
                fd = os.open(
                    location, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                    dir_fd=parent_fd,
                )
                try:
                    if not _same_entry(fingerprint, _entry_fingerprint(os.fstat(fd))):
                        raise HTTPException(409, '删除目录已变化')
                    for child, rel, entry in children.get(relative, []):
                        remove(path, child, rel, entry, fd)
                finally:
                    os.close(fd)
            check()
            # New names are never visited. A concurrent addition leaves the
            # directory non-empty and makes cleanup retryable instead of lost.
            os.rmdir(location, dir_fd=parent_fd)
        else:
            os.unlink(location, dir_fd=parent_fd)

    path = target['path']
    root_entry = [stat.S_IFDIR, *target['fingerprint']]
    if not _DIRECTORY_FDS:
        remove(os.path.dirname(path), os.path.basename(path), '', root_entry)
    else:
        parent = os.open(os.path.dirname(path), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            remove(os.path.dirname(path), os.path.basename(path), '', root_entry, parent)
        finally:
            os.close(parent)

def _cleanup(db, record):
    targets = json.loads(record.targets_json)
    failed = False
    for target in targets:
        try:
            current = _safe_target(target['path'], target['root'])
            if not current['exists']:
                continue
            expected = target['fingerprint']
            actual = current['fingerprint']
            if expected is None or current['is_directory'] != target['is_directory'] or actual[:2] != expected[:2] or (not target['is_directory'] and actual != expected):
                raise HTTPException(409, '删除目标已变化，拒绝清理新文件')
            if current['is_directory']:
                _cleanup_directory(target, current)
            else:
                os.remove(target['path'])
        except (OSError, HTTPException):
            logger.warning('Discard cleanup failed: record=%s', record.id, exc_info=True)
            failed = True
    record.cleanup_status = 'failed' if failed else 'completed'
    record.cleanup_error = '部分文件未能删除或目标已变化；丢弃标记已保留，可重试清理' if failed else None
    db.commit()
    return serialize_record(record)

def discard(db, kind, target_id, preview_hash):
    with acquire_media_operation([], []):
        db.expire_all()
        plan = build_plan(db, kind, target_id)
        if preview_hash != plan['preview_hash']:
            raise HTTPException(409, '内容或文件已变化，请重新确认删除范围')
        record = models.DiscardedContent(id=str(uuid.uuid4()), title=plan['title'],
            source_type=plan['source_type'], media_count=len(plan['media']), file_size=plan['file_size'],
            targets_json=json.dumps(plan['targets'], ensure_ascii=False),
            media_ids_json=json.dumps([m['id'] for m in plan['media']]), cleanup_status='pending')
        db.add(record)
        db.flush()
        for key in plan['keys']:
            if not has_identity(db, key):
                db.add(models.DiscardedIdentity(key=key, discard_id=record.id))
        ids = [m['id'] for m in plan['media']]
        paths = [m['path'] for m in plan['media']] + [p['path'] for p in plan['targets']]
        for item in db.query(models.XMediaItem).filter(or_(models.XMediaItem.library_media_id.in_(ids), models.XMediaItem.local_path.in_(paths))).all():
            item.status, item.library_media_id = 'discarded', None
        for post_id in plan['x_post_ids']:
            post = db.get(models.XPost, post_id)
            post.status, post.error_message = 'discarded', None
            for item in post.media_items:
                item.status, item.library_media_id = 'discarded', None
        for item in db.query(models.PawchiveAttachment).filter(models.PawchiveAttachment.media_id.in_(ids)).all():
            item.status, item.media_id = 'discarded', None
        media_cleanup.detach_media_references(db, ids)
        for media in plan['media']:
            row = db.get(models.Media, media['id'])
            if row:
                db.delete(row)
        # This transaction is the durable barrier against rediscovery, even if
        # the process dies during filesystem cleanup below.
        db.commit()
        for media in plan['media']:
            try:
                remove_cover_thumbnails(media['cover_path'])
                remove_manga_page_thumbnails(media['id'])
            except OSError:
                logger.warning('Discard thumbnail cleanup failed: record=%s', record.id)
        return _cleanup(db, record)

def retry_cleanup(db, record_id):
    with acquire_media_operation([], []):
        record = db.get(models.DiscardedContent, record_id)
        if record is None:
            raise HTTPException(404, '丢弃记录不存在')
        if record.cleanup_status == 'completed':
            return serialize_record(record)
        return _cleanup(db, record)

def allow_download(db, record_id):
    with acquire_media_operation([], []):
        record = db.get(models.DiscardedContent, record_id)
        if record is None:
            raise HTTPException(404, '丢弃记录不存在')
        if record.cleanup_status != 'completed':
            raise HTTPException(409, '请先完成文件清理，再允许重新下载')
        keys = [row.key for row in db.query(models.DiscardedIdentity).filter(models.DiscardedIdentity.discard_id == record_id).all()]
        for key in keys:
            match = re.fullmatch(r'x:(\d+):(\d+|\*)', key)
            if match:
                posts = db.query(models.XPost).filter(models.XPost.tweet_id == match.group(1)).all()
                for post in posts:
                    if post.status in ('completed', 'discarded'):
                        post.status = 'pending'
                    for item in post.media_items:
                        if item.status == 'discarded' and (match.group(2) == '*' or item.media_index == int(match.group(2))):
                            item.status = 'pending'
        # Pawchive retries also rely on identity removal; reset retained rows.
        for key in keys:
            if key.startswith('pawchive:'):
                for row in db.query(models.PawchiveAttachment).filter(models.PawchiveAttachment.status == 'discarded').all():
                    if key == f'pawchive:{row.post.service}:{row.post.creator_id}:{row.post.post_id}:{row.attachment_key}':
                        row.status = 'failed'
        db.query(models.DiscardedIdentity).filter(models.DiscardedIdentity.discard_id == record_id).delete(synchronize_session=False)
        db.delete(record)
        db.commit()
        return {'allowed': True, 'message': '已允许重新下载，已删除的文件不会自动恢复'}

def recover_pending_cleanup():
    db = database.SessionLocal()
    try:
        for record in db.query(models.DiscardedContent).filter(models.DiscardedContent.cleanup_status == 'pending').all():
            try:
                retry_cleanup(db, record.id)
            except HTTPException:
                db.rollback()
                logger.warning('Discard cleanup deferred: record=%s', record.id)
    finally:
        db.close()
