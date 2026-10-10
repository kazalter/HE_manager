"""Durable one-shot approved tasks; never replay on restart or failed enqueue."""
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from fastapi import HTTPException
from .. import database,models
from ..services.assistant_runtime_logs import emit_event
from . import schemas as s
from .models import AssistantProposal,AssistantAudit
from .store import write_transaction,utcnow,canonical_json
from .proposals import owned

_POOL=ThreadPoolExecutor(max_workers=1,thread_name_prefix="he-approved")
_SUBMITTED=set();_LOCK=threading.Lock()

def job_id_for(proposal_id):return 'assistant-operation-'+proposal_id

def reserve_operation_job(local,proposal):
    from ..services.job_lifecycle import ACTIVE_STATUSES,JOB_MAX_ENTRIES
    rows=local.query(models.BackgroundJob).filter(models.BackgroundJob.kind=='assistant_operation')
    if rows.filter(models.BackgroundJob.status.in_(ACTIVE_STATUSES|{'needs_recovery'})).first():raise HTTPException(409,'assistant_operation_busy')
    if rows.count()>=JOB_MAX_ENTRIES:
        old=rows.filter(models.BackgroundJob.status.in_(('completed','failed','interrupted'))).order_by(models.BackgroundJob.created_at).first()
        if old:local.delete(old)
        else:raise HTTPException(409,'assistant_operation_busy')
    payload=json.loads(proposal.payload_json)
    execution=dict(payload)
    if proposal.kind=='maintenance' and payload.get('action')!='backup_database':
        query=local.query(models.Media).order_by(models.Media.id)
        if payload.get('all_media'):
            if payload['action']=='recheck_missing':query=query.filter(models.Media.is_missing==True)
            if payload['action']=='regenerate_thumbnail':query=query.filter(models.Media.media_type=='video')
        else:query=query.filter(models.Media.id.in_(payload.get('media_ids',[])))
        execution['media_ids']=[x[0] for x in query.with_entities(models.Media.id)]
        execution['all_media']=False
    job=s.JobDTO(job_id=job_id_for(proposal.id),kind=proposal.kind,folder_id=None,status='queued',progress=0,message='已批准，等待执行；失败时不自动重放。',created_at=utcnow())
    local.add(models.BackgroundJob(job_id=job.job_id,kind='assistant_operation',status='queued',payload_json=canonical_json({'job':job.model_dump(mode='json'),'execution':execution}),created_at=utcnow(),updated_at=utcnow()))
    return s.ActionResultDTO(proposal_id=proposal.id,state='queued',job_id=job.job_id,job=job)

def update_job(proposal_id,status,message,progress=None,items=None):
    with database.SessionLocal() as db:
        with write_transaction(db) as local:
            row=local.get(models.BackgroundJob,job_id_for(proposal_id));proposal=local.get(AssistantProposal,proposal_id)
            if not row or not proposal:raise HTTPException(503,'assistant_tool_unavailable')
            payload=json.loads(row.payload_json);job=s.JobDTO.model_validate(payload['job'])
            terminal=status in ('completed','failed','interrupted','needs_recovery')
            job=job.model_copy(update=dict(status=status,message=message[:500],progress=progress,finished_at=utcnow() if terminal else None))
            payload['job']=job.model_dump(mode='json');row.status=status;row.payload_json=canonical_json(payload);row.updated_at=utcnow();row.finished_at=job.finished_at
            result=s.ActionResultDTO(proposal_id=proposal_id,state=status,job_id=job.job_id,job=job,items=items or [])
            proposal.result_json=result.model_dump_json()
            audit=local.query(AssistantAudit).filter_by(proposal_id=proposal_id).first()
            if audit:audit.result_json=proposal.result_json
    return result

def execute_maintenance(proposal_id,execution):
    action=execution['action'];ids=execution.get('media_ids',[]);results=[]
    if action=='backup_database':
        from ..routers.system import _get_live_db_path
        from ..services.backup import backup_database
        reply=backup_database(_get_live_db_path(),rotate=False)
        return [dict(backup_name=reply['backup_name'],size_bytes=reply['size_bytes'],status='completed')]
    for index,media_id in enumerate(ids):
        with database.SessionLocal() as db:
            media=db.get(models.Media,media_id)
            if not media:raise HTTPException(409,'assistant_proposal_stale')
            if action=='recheck_missing':
                from .file_reads import root_path,resolve_project_path
                from pathlib import Path
                root=root_path(db,media.folder_id)
                try:relative=Path(media.absolute_path).absolute().relative_to(root).as_posix()
                except ValueError:raise HTTPException(403,'assistant_path_outside_root') from None
                path=resolve_project_path(db,media.folder_id,relative,must_exist=False)
                exists=path.exists();media.is_missing=not exists;media.missing_since=None if exists else media.missing_since or utcnow()
                if exists and path.is_file():media.file_size=path.stat().st_size
                db.commit();results.append(dict(media_id=media_id,status='recovered' if exists else 'missing'))
            elif action=='regenerate_thumbnail':
                from ..routers.media import do_regenerate_thumbnail
                from .file_reads import media_location
                media_location(db,media_id);before=media.cover_path
                do_regenerate_thumbnail(media_id);db.expire_all();after=db.get(models.Media,media_id).cover_path
                if not after or after==before:raise HTTPException(503,'assistant_tool_unavailable')
                results.append(dict(media_id=media_id,status='completed'))
            else:
                from .file_reads import media_location
                media_location(db,media_id)
                from ..dedup.worker import _process_one
                _process_one(media_id)
                db.expire_all();state=db.get(models.Media,media_id).duplicate_status
                if state=='dedup_error':raise HTTPException(503,'assistant_tool_unavailable')
                results.append(dict(media_id=media_id,status=state))
        update_job(proposal_id,'running',f'已处理 {index+1}/{len(ids)} 项',round((index+1)/len(ids)*100,1),results[-50:])
    return results[-50:]

def run_operation_job(proposal_id):
    try:
        with database.SessionLocal() as db:
            proposal=db.get(AssistantProposal,proposal_id);row=db.get(models.BackgroundJob,job_id_for(proposal_id))
            if not proposal or not row or row.status!='queued':return
            kind=proposal.kind;execution=json.loads(row.payload_json)['execution']
        update_job(proposal_id,'running','正在执行已批准的操作',0)
        emit_event('assistant','INFO','operation_started',proposal_id)
        if kind=='file_move':
            from .file_actions import execute_file_move
            result=execute_file_move(proposal_id)
            update_job(proposal_id,'completed','文件移动和媒体路径更新完成。',100,result.items)
        else:
            from ..services.media_operation_guard import project_mutation
            with project_mutation():
                with database.SessionLocal() as db:
                    from .operation_registry import preview_operation
                    p=db.get(AssistantProposal,proposal_id)
                    if preview_operation(db,p.kind,json.loads(p.payload_json)).fingerprint!=p.target_fingerprint:raise HTTPException(409,'assistant_proposal_stale')
                items=execute_maintenance(proposal_id,execution)
                update_job(proposal_id,'completed','任务完成；结果清单最多显示最近 50 项。',100,items)
        emit_event('assistant','INFO','operation_completed',proposal_id)
    except Exception as exc:
        from .tool_errors import MESSAGES
        code=exc.detail if isinstance(exc,HTTPException) and isinstance(exc.detail,str) else 'assistant_tool_unavailable'
        status='needs_recovery' if code=='assistant_file_needs_recovery' else 'failed'
        try:update_job(proposal_id,status,MESSAGES.get(code,'操作失败，可能已有部分结果；不会自动重放。'))
        except Exception:emit_event('assistant','ERROR','operation_recovery',proposal_id)
        emit_event('assistant','ERROR','operation_failed',proposal_id)
    finally:
        with _LOCK:_SUBMITTED.discard(proposal_id)

def enqueue_operation_job(proposal_id):
    with _LOCK:
        if proposal_id in _SUBMITTED:return job_id_for(proposal_id)
        _SUBMITTED.add(proposal_id)
    try:_POOL.submit(run_operation_job,proposal_id)
    except Exception:
        with _LOCK:_SUBMITTED.discard(proposal_id)
        update_job(proposal_id,'failed','任务排队失败，不自动重放。')
    return job_id_for(proposal_id)

def get_owned_operation_job(db,user_id,job_id):
    pid=job_id.removeprefix('assistant-operation-');owned(db,user_id,pid)
    row=db.get(models.BackgroundJob,job_id)
    if not row or row.kind!='assistant_operation':raise HTTPException(404,'assistant_not_found')
    return s.JobDTO.model_validate(json.loads(row.payload_json)['job'])

def recover_operation_jobs():
    with database.SessionLocal() as db:
        ids=[x.job_id.removeprefix('assistant-operation-') for x in db.query(models.BackgroundJob).filter(models.BackgroundJob.kind=='assistant_operation',models.BackgroundJob.status.in_(('queued','running')))]
    for pid in ids:update_job(pid,'interrupted','服务重启，任务中断；不会自动重放。')
