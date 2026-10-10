"""Approved, no-overwrite file moves with durable intent and path recovery."""
import ctypes
import errno
import json
import os
import stat
from pathlib import Path
from fastapi import HTTPException
from .. import database,models
from ..services.media_operation_guard import acquire_media_operation,block_unresolved
from . import schemas as s
from .models import AssistantProposal,AssistantFileOperation
from .file_reads import root_path,resolve_project_path,media_location
from .store import input_hash,canonical_json,write_transaction,utcnow

PATH_FIELDS=((models.Media,'absolute_path'),(models.Media,'cover_path'),(models.MediaFingerprint,'source_path'),(models.XMediaItem,'local_path'),(models.PawchiveAttachment,'local_path'))

def manifest(path):
    entries=[]
    def add(p):
        st=p.lstat()
        if stat.S_ISLNK(st.st_mode) or not (stat.S_ISREG(st.st_mode) or stat.S_ISDIR(st.st_mode)):raise HTTPException(403,'assistant_path_outside_root')
        if stat.S_ISREG(st.st_mode) and st.st_nlink!=1:raise HTTPException(409,'assistant_file_relationship_unsupported')
        entries.append(dict(path='.' if p==path else p.relative_to(path).as_posix(),size=st.st_size,mtime=st.st_mtime_ns,mode=st.st_mode,inode=st.st_ino,device=st.st_dev))
        if len(entries)>10000:raise HTTPException(413,'assistant_content_too_large')
    add(path)
    if path.is_dir():
        for base,dirs,files in os.walk(path,followlinks=False):
            for name in sorted(dirs+files):add(Path(base,name))
    return sorted(entries,key=lambda x:x['path'])

def replacement(value,source,destination):
    if not value or not Path(value).is_absolute():return None
    try:return str(destination/Path(value).relative_to(source))
    except ValueError:return None

def relationships(db,source,destination,destination_folder_id):
    changes={}
    for cls,field in PATH_FIELDS:
        attr=getattr(cls,field)
        rows=db.query(cls).filter((attr==str(source))|attr.startswith(str(source)+os.sep,autoescape=True)).all()
        for row in rows:
            before=getattr(row,field);after=replacement(before,source,destination)
            if after is None:continue
            key=(cls.__name__,row.id)
            item=changes.setdefault(key,dict(model=cls.__name__,id=row.id,before={},after={}))
            item['before'][field]=before;item['after'][field]=after
            if cls is models.Media and field=='absolute_path':
                item['before'].update(folder_id=row.folder_id,relative_path=row.relative_path)
                item['after'].update(folder_id=destination_folder_id,relative_path=Path(after).relative_to(root_path(db,destination_folder_id)).as_posix())
    if not changes or len(changes)>10000:raise HTTPException(409,'assistant_file_relationship_unsupported')
    # Moving a registered root or configured download root would change its subsystem contract.
    roots=[x.path for x in db.query(models.Folder)]
    roots += [x[0] for x in db.query(models.ExternalFavoriteSource.download_root_path) if x[0]]
    roots += [x[0] for x in db.query(models.XImportSource.download_root_path) if x[0]]
    if any(replacement(x,source,destination) is not None for x in roots):raise HTTPException(409,'assistant_file_relationship_unsupported')
    # A destination cannot collide with an existing library row, including missing entries.
    moved={x['id'] for x in changes.values() if x['model']=='Media'}
    for x in changes.values():
        if x['model']=='Media' and 'absolute_path' in x['after']:
            collision=db.query(models.Media.id).filter(models.Media.absolute_path==x['after']['absolute_path'],models.Media.id.notin_(moved)).first()
            if collision:raise HTTPException(409,'assistant_file_destination_exists')
    return sorted(changes.values(),key=lambda x:(x['model'],x['id']))

def move_details(db,media_id,destination_folder_id,destination_relative_path):
    media,relative=media_location(db,media_id);source=resolve_project_path(db,media.folder_id,relative)
    target=resolve_project_path(db,destination_folder_id,destination_relative_path,must_exist=False)
    if source==root_path(db,media.folder_id) or source==target or target.is_relative_to(source):raise HTTPException(409,'assistant_file_relationship_unsupported')
    if target.exists():raise HTTPException(409,'assistant_file_destination_exists')
    if not target.parent.is_dir():raise HTTPException(404,'assistant_file_unavailable')
    if source.stat().st_dev!=target.parent.stat().st_dev:raise HTTPException(409,'assistant_cross_device_move')
    changes=relationships(db,source,target,destination_folder_id)
    data=manifest(source);parent=target.parent.stat()
    return media,source,target,data,changes,dict(device=parent.st_dev,inode=parent.st_ino,mtime=parent.st_mtime_ns)

def preview_file_move(db,media_id,destination_folder_id,destination_relative_path):
    media,source,target,data,changes,parent=move_details(db,media_id,destination_folder_id,destination_relative_path)
    fingerprint=input_hash(dict(source=str(source),destination=str(target),manifest=data,relationships=changes,parent=parent))
    return s.OperationPreviewDTO(kind='file_move',target_id=media.id,label=media.title or source.name,targets=[dict(type='media',id=media.id,label=media.title or source.name)],before=dict(source_path=str(source),file_count=len(data),path_changes=[dict(model=x['model'],id=x['id'],fields=x['before']) for x in changes[:50]],changes_truncated=len(changes)>50),after=dict(destination_path=str(target),path_changes=[dict(model=x['model'],id=x['id'],fields=x['after']) for x in changes[:50]],changes_truncated=len(changes)>50,notice='同盘移动，不覆盖；同步关联媒体路径。'),fingerprint=fingerprint,impact_count=len(changes),reversibility='可以提出反向移动，需重新审批')

def rename_no_replace(source,target):
    if os.name=='nt':os.rename(source,target);return
    import sys
    if not sys.platform.startswith('linux'):raise HTTPException(503,'assistant_file_relationship_unsupported')
    libc=ctypes.CDLL(None,use_errno=True)
    try:fn=libc.renameat2
    except AttributeError:raise HTTPException(503,'assistant_file_relationship_unsupported') from None
    fn.argtypes=[ctypes.c_int,ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,ctypes.c_uint];fn.restype=ctypes.c_int
    # Anchored parent descriptors also prevent ancestor swaps during rename.
    def parent_fd(path):
        fd=os.open(path.anchor,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:
            for name in path.parent.parts[1:]:
                next_fd=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd);os.close(fd);fd=next_fd
            return fd
        except BaseException:os.close(fd);raise
    source_fd=parent_fd(source);target_fd=None
    try:
        target_fd=parent_fd(target)
        if fn(source_fd,os.fsencode(source.name),target_fd,os.fsencode(target.name),1)!=0:
            number=ctypes.get_errno()
            if number==errno.EEXIST:raise HTTPException(409,'assistant_file_destination_exists')
            if number==errno.EXDEV:raise HTTPException(409,'assistant_cross_device_move')
            raise OSError(number,os.strerror(number))
    finally:
        os.close(source_fd)
        if target_fd is not None:os.close(target_fd)

def update_paths(local,changes,direction):
    before='before' if direction=='after' else 'after'
    for item in changes:
        row=local.get(getattr(models,item['model']),item['id'])
        if not row or any(getattr(row,k)!=v for k,v in item[before].items()):raise HTTPException(409,'assistant_proposal_stale')
    for item in changes:
        row=local.get(getattr(models,item['model']),item['id'])
        for key,value in item[direction].items():setattr(row,key,value)

def clear_path_caches():
    from ..services.manga_pages import _MANGA_FILES_CACHE,_PAGE_DIMENSIONS_CACHE
    _MANGA_FILES_CACHE.clear();_PAGE_DIMENSIONS_CACHE.clear()
    from ..creators import clear_creator_cache
    clear_creator_cache()

def execute_file_move(proposal_id):
    with database.SessionLocal() as db:
        proposal=db.get(AssistantProposal,proposal_id);payload=json.loads(proposal.payload_json)
        media=db.get(models.Media,payload['media_id']);folders=[media.folder_id,payload['destination_folder_id']]
    with acquire_media_operation(folders,[payload['media_id']]):
        from ..scanners.common import _FOLDER_SCAN_RESERVATIONS,_FOLDER_SCAN_RESERVATIONS_LOCK
        with _FOLDER_SCAN_RESERVATIONS_LOCK:
            if any(i in _FOLDER_SCAN_RESERVATIONS for i in folders):raise HTTPException(409,'assistant_operation_busy')
        with database.SessionLocal() as db:
            proposal=db.get(AssistantProposal,proposal_id)
            preview=preview_file_move(db,payload['media_id'],payload['destination_folder_id'],payload['destination_relative_path'])
            if preview.fingerprint!=proposal.target_fingerprint:raise HTTPException(409,'assistant_proposal_stale')
            _,source,target,data,changes,_=move_details(db,payload['media_id'],payload['destination_folder_id'],payload['destination_relative_path'])
            with write_transaction(db) as local:
                if local.get(AssistantFileOperation,proposal_id):raise HTTPException(409,'assistant_file_needs_recovery')
                local.add(AssistantFileOperation(proposal_id=proposal_id,user_id=proposal.user_id,state='intended',source_path=str(source),destination_path=str(target),manifest_json=canonical_json(data),relationships_json=canonical_json(changes)))
        moved=False;committed=False
        try:
            if manifest(source)!=data:raise HTTPException(409,'assistant_proposal_stale')
            rename_no_replace(source,target);moved=True
            with database.SessionLocal() as db:
                with write_transaction(db) as local:
                    journal=local.get(AssistantFileOperation,proposal_id);journal.state='moved';journal.updated_at=utcnow()
            if manifest(target)!=data:raise HTTPException(409,'assistant_file_needs_recovery')
            with database.SessionLocal() as db:
                with write_transaction(db) as local:
                    update_paths(local,changes,'after');journal=local.get(AssistantFileOperation,proposal_id);journal.state='db_committed';journal.updated_at=utcnow()
            committed=True
            with database.SessionLocal() as db:
                with write_transaction(db) as local:
                    journal=local.get(AssistantFileOperation,proposal_id);journal.state='completed';journal.updated_at=utcnow()
            clear_path_caches()
            return s.ActionResultDTO(proposal_id=proposal_id,state='completed',items=[dict(media_id=payload['media_id'],source_path=str(source),destination_path=str(target),status='completed')])
        except Exception:
            recoverable=not moved
            if moved and not committed:
                try:
                    with database.SessionLocal() as check:
                        before_ok=all((obj:=check.get(getattr(models,x['model']),x['id'])) is not None and all(getattr(obj,k)==v for k,v in x['before'].items()) for x in changes)
                    if before_ok and not source.exists() and manifest(target)==data:
                        rename_no_replace(target,source);recoverable=True
                except Exception:pass
            try:
                with database.SessionLocal() as db:
                    with write_transaction(db) as local:
                        journal=local.get(AssistantFileOperation,proposal_id);journal.state='rolled_back' if recoverable else 'needs_recovery';journal.error_code='assistant_file_needs_recovery' if not recoverable else 'assistant_file_unavailable';journal.updated_at=utcnow()
            except Exception:recoverable=False
            if not recoverable:block_unresolved();raise HTTPException(409,'assistant_file_needs_recovery') from None
            raise

def recover_file_operations():
    from .operation_jobs import update_job
    unresolved=False
    with database.SessionLocal() as db:
        ids=[x.proposal_id for x in db.query(AssistantFileOperation).filter(AssistantFileOperation.state.notin_(('completed','rolled_back')))]
    for pid in ids:
        state='needs_recovery'
        try:
            with database.SessionLocal() as db:
                row=db.get(AssistantFileOperation,pid);source=Path(row.source_path);target=Path(row.destination_path);data=json.loads(row.manifest_json);changes=json.loads(row.relationships_json)
                # Validate stored paths through their registered source/destination roots before inspection.
                proposal=db.get(AssistantProposal,pid);payload=json.loads(proposal.payload_json)
                target_checked=resolve_project_path(db,payload['destination_folder_id'],payload['destination_relative_path'],must_exist=False)
                source_media_change=next(x for x in changes if x['model']=='Media' and x['id']==payload['media_id'])
                old_folder=source_media_change['before']['folder_id'];old_relative=Path(row.source_path).relative_to(root_path(db,old_folder)).as_posix()
                if resolve_project_path(db,old_folder,old_relative,must_exist=False)!=source or target_checked!=target:raise ValueError
                db_before=all((obj:=db.get(getattr(models,x['model']),x['id'])) is not None and all(getattr(obj,k)==v for k,v in x['before'].items()) for x in changes)
                db_after=all((obj:=db.get(getattr(models,x['model']),x['id'])) is not None and all(getattr(obj,k)==v for k,v in x['after'].items()) for x in changes)
                if source.exists() and not target.exists() and manifest(source)==data and db_before:state='rolled_back'
                elif target.exists() and not source.exists() and manifest(target)==data:
                    if db_before:
                        with write_transaction(db) as local:update_paths(local,changes,'after')
                        db_after=True
                    if db_after:state='completed'
                with write_transaction(db) as local:
                    row=local.get(AssistantFileOperation,pid);row.state=state;row.updated_at=utcnow()
            update_job(pid,'completed' if state=='completed' else 'failed' if state=='rolled_back' else 'needs_recovery','启动时核实文件和数据库一致。' if state=='completed' else '操作已回滚，未重放。' if state=='rolled_back' else '文件操作状态不明确，请核对源/目标及关联资料后恢复。')
        except Exception:
            state='needs_recovery'
            try:update_job(pid,'needs_recovery','文件操作需要人工核对，相关写入已暂停。')
            except Exception:pass
        unresolved=unresolved or state=='needs_recovery'
    block_unresolved(unresolved);clear_path_caches()
