"""Typed immutable operations: preview first, administrator confirmation only."""
import json
from dataclasses import dataclass
from datetime import timedelta
from uuid import uuid4
from fastapi import HTTPException
from . import schemas as s
from .models import AssistantProposal,AssistantAudit
from .identity import require_tool_context
from .store import write_transaction,input_hash,canonical_json,utcnow,require_owned_session,require_owned_run
from .proposals import owned,ack,proposal_dto,media_snapshot,public_snapshot,full_tags
from .. import models,tagging

@dataclass(frozen=True)
class OperationSpec:
    kind: str
    args_type: type[s.DTO]
    async_job: bool=False

OPERATION_REGISTRY={k:OperationSpec(k,t,async_job=k in ("maintenance","file_move")) for k,t in {"media_batch_update":s.BatchUpdateArgs,"tag_rename":s.TagRenameArgs,"tag_merge":s.TagMergeArgs,"maintenance":s.MaintenanceArgs,"file_move":s.FileMoveArgs}.items()}

def patch_preview(row,patch):
    before=media_snapshot(row,patch);after={**before,"tags":[dict(t) for t in before['tags']]}
    remove=set(patch.get('remove_tag_ids',[]));added={(x['name'],x['namespace']) for x in patch.get('add_tags',[])}
    if not remove.issubset({x['id'] for x in before['tags']}) or any(x['id'] in remove and (x['name'],x['namespace']) in added for x in before['tags']):raise HTTPException(422,'assistant_conflicting_tags')
    for key in ('rating','favorite','source_url','title','artist','view_status'):
        if key in patch:after[key]=patch[key]
    after['tags']=[x for x in after['tags'] if x['id'] not in remove]
    old={(x['name'],x['namespace']) for x in after['tags']}
    after['tags'] += [dict(id=None,name=n,namespace=ns) for n,ns in sorted(added-old)]
    display=public_snapshot(after);display['add_tags']=patch.get('add_tags',[]);display['remove_tags']=[x for x in before['tags'] if x['id'] in remove]
    return before,public_snapshot(before),display

def preview_operation(db,kind,payload):
    q=OPERATION_REGISTRY[kind].args_type.model_validate(payload)
    targets=[];raw={};before={};after={};target_id=0;label='HE 项目';reversibility='需重新审批'
    if kind=='media_batch_update':
        raw_items=[];before_items=[];after_items=[]
        for item in sorted(q.items,key=lambda x:x.media_id):
            row=db.get(models.Media,item.media_id)
            if not row:raise HTTPException(404,'assistant_media_not_found')
            patch=item.patch.model_dump(exclude_unset=True)
            if not patch:raise HTTPException(422,'assistant_empty_change')
            snapshot,b,a=patch_preview(row,patch)
            targets.append(dict(type='media',id=row.id,label=row.title or '媒体'))
            raw_items.append(dict(media_id=row.id,snapshot=snapshot));before_items.append({'media_id':row.id,'title':row.title,**b});after_items.append({'media_id':row.id,'title':row.title,**a})
        raw={'items':raw_items};before={'items':before_items};after={'items':after_items};target_id=q.items[0].media_id;label=f'修改 {len(q.items)} 项媒体资料'
    elif kind in ('tag_rename','tag_merge'):
        ids=[q.tag_id] if kind=='tag_rename' else [q.source_tag_id,q.target_tag_id]
        if len(ids)!=len(set(ids)):raise HTTPException(422,'assistant_empty_change')
        tags=[db.get(models.Tag,i) for i in ids]
        if any(t is None for t in tags):raise HTTPException(404,'assistant_not_found')
        relations={str(t.id):sorted(x[0] for x in db.query(models.media_tags.c.media_id).filter(models.media_tags.c.tag_id==t.id)) for t in tags}
        raw={'tags':[dict(id=t.id,name=t.name,namespace=t.namespace or 'general') for t in tags],'relations':relations}
        target_id=ids[0];affected=sorted({x for values in relations.values() for x in values});targets=[dict(type='media',id=x.id,label=x.title or '媒体') for x in db.query(models.Media).filter(models.Media.id.in_(affected)).order_by(models.Media.id)]
        before={'tags':raw['tags'],'affected_media_count':len(affected),'affected_media_ids':affected[:50],'affected_list_truncated':len(affected)>50}
        if kind=='tag_rename':
            name=q.name.strip();namespace=(q.namespace or tags[0].namespace or 'general').strip()
            if not name or not namespace:raise HTTPException(422,'assistant_invalid_proposal')
            collision=db.query(models.Tag).filter(models.Tag.name==name,models.Tag.namespace==namespace,models.Tag.id!=q.tag_id).first()
            if collision:raise HTTPException(409,'assistant_tag_exists')
            after={'name':name,'namespace':namespace,'affected_media_count':len(affected)};label='标签改名：'+(tags[0].name or '')
            if (name,namespace)==(tags[0].name,tags[0].namespace or 'general'):raise HTTPException(422,'assistant_empty_change')
        else:
            after={'source_tag':tags[0].name,'target_tag':tags[1].name,'affected_media_count':len(affected),'notice':'原标签关联将合并至目标标签，原标签删除；不会删除媒体文件。'};label='标签合并'
            reversibility='合并后无法自动撤回'
    elif kind=='maintenance':
        if q.action=='backup_database':
            if q.media_ids or q.all_media:raise HTTPException(422,'assistant_invalid_proposal')
            raw={'action':q.action};before={'action':'数据库备份'};after={'action':'创建新备份','notice':'不清理旧备份'};targets=[dict(type='project',id=None,label='HE 数据库')];label='创建数据库备份'
        else:
            if q.all_media and q.media_ids:raise HTTPException(422,'assistant_invalid_proposal')
            if not q.all_media and not q.media_ids:raise HTTPException(422,'assistant_invalid_proposal')
            rows=db.query(models.Media).order_by(models.Media.id)
            if q.all_media:
                if q.action=='recheck_missing':rows=rows.filter(models.Media.is_missing==True)
                if q.action=='regenerate_thumbnail':rows=rows.filter(models.Media.media_type=='video')
            else:rows=rows.filter(models.Media.id.in_(q.media_ids))
            media=rows.all()
            if not media or (not q.all_media and len(media)!=len(set(q.media_ids))):raise HTTPException(404,'assistant_media_not_found')
            if len(media)>10000:raise HTTPException(413,'assistant_content_too_large')
            if q.action=='regenerate_thumbnail' and any(x.media_type!='video' for x in media):raise HTTPException(422,'assistant_invalid_proposal')
            raw={'action':q.action,'media':[dict(id=x.id,path=x.absolute_path,missing=bool(x.is_missing),duplicate=x.duplicate_status,cover=x.cover_path) for x in media]}
            requested_ids=[x.id for x in media]
            if q.action=='recheck_duplicates':
                media=db.query(models.Media).order_by(models.Media.id).all()
                if len(media)>10000:raise HTTPException(413,'assistant_content_too_large')
                pairs=db.query(models.DuplicateCandidate).filter((models.DuplicateCandidate.existing_media_id.in_(requested_ids)) | (models.DuplicateCandidate.candidate_media_id.in_(requested_ids))).order_by(models.DuplicateCandidate.id).all()
                raw={'action':q.action,'media':[dict(id=x.id,title=x.title,path=x.absolute_path,missing=bool(x.is_missing),duplicate=x.duplicate_status,cover=x.cover_path) for x in media],'pairs':[dict(id=x.id,left=x.existing_media_id,right=x.candidate_media_id,status=x.status,level=x.level) for x in pairs]}
            before={'action':q.action,'media_count':len(media),'media_ids':[x.id for x in media[:50]],'list_truncated':len(media)>50}
            after={**before,'requested_media_ids':requested_ids[:50],'requested_count':len(requested_ids),'notice':'重复复查可能更新对比媒体与重复关系，全部潜在影响对象见完整清单；任务失败可能已有部分结果，不自动重放。' if q.action=='recheck_duplicates' else '任务可能逐项处理；失败时可能已有部分结果，不自动重放。'};targets=[dict(type='media',id=x.id,label=x.title or '媒体') for x in media];label={'recheck_missing':'复查缺失文件','recheck_duplicates':'复查重复媒体','regenerate_thumbnail':'重建视频缩略图'}[q.action]
            reversibility='任务结果不可自动撤回'
    else:
        from .file_actions import preview_file_move
        return preview_file_move(db,q.media_id,q.destination_folder_id,q.destination_relative_path)
    impact=len(raw.get('media',raw.get('items',[]))) or before.get('affected_media_count',1)
    return s.OperationPreviewDTO(kind=kind,target_id=target_id,label=label[:500],targets=targets,before=before,after=after,fingerprint=input_hash(raw),impact_count=impact,reversibility=reversibility)

def insert_operation(local,user_id,session_id,run_id,kind,payload,preview,expires_at):
    digest=input_hash(dict(version=2,user_id=user_id,session_id=session_id,run_id=run_id,kind=kind,payload=payload))
    existing=local.query(AssistantProposal).filter_by(run_id=run_id,kind=kind,normalized_payload_hash=digest).first()
    if existing:return existing
    row=AssistantProposal(id=str(uuid4()),user_id=user_id,session_id=session_id,run_id=run_id,kind=kind,target_id=preview.target_id,target_label=preview.label,reason=payload.get('reason',''),impact_count=preview.impact_count,reversibility=preview.reversibility,targets_json=canonical_json(preview.targets),normalized_payload_hash=digest,payload_json=canonical_json(payload),before_json=canonical_json(preview.before),after_json=canonical_json(preview.after),target_fingerprint=preview.fingerprint,state='pending',created_at=utcnow(),expires_at=expires_at)
    local.add(row);local.flush();return row

def create_operation_proposal(db,principal,context,kind,args):
    if kind not in OPERATION_REGISTRY:raise HTTPException(404,'assistant_unknown_tool')
    payload=OPERATION_REGISTRY[kind].args_type.model_validate(args).model_dump(mode='json',exclude_unset=True)
    with write_transaction(db) as local:
        require_tool_context(local,principal,context)
        preview=preview_operation(local,kind,payload)
        row=insert_operation(local,principal.user_id,str(context.session_id),str(context.run_id),kind,payload,preview,utcnow()+timedelta(seconds=300))
        return ack(row)

def revalidate_preview(db,row,payload):
    try:return preview_operation(db,row.kind,payload)
    except HTTPException as exc:
        if exc.status_code in (404,409,403,422):return None
        raise

def ensure_approvable(local,row):
    session=require_owned_session(local,row.user_id,row.session_id);run=require_owned_run(local,row.user_id,row.run_id)
    if session.state!='active' or run.stop_requested_at is not None or run.status not in ('submitting','running','completed') or (run.status!='completed' and run.deadline_at and run.deadline_at<=utcnow()):raise HTTPException(409,'assistant_proposal_unavailable')
    if row.expires_at<=utcnow():raise HTTPException(409,'assistant_proposal_expired')
    if row.state!='pending':raise HTTPException(409,'assistant_proposal_consumed')

def apply_media_patch(local,row,patch):
    for key in ('rating','favorite','source_url','title','artist','view_status'):
        if key in patch:setattr(row,key,patch[key])
    if 'title' in patch:
        from ..dedup.normalize import normalize_title
        row.normalized_title=normalize_title(row.title)
    remove=set(patch.get('remove_tag_ids',[]));row.tags=[t for t in row.tags if t.id not in remove]
    for tag in patch.get('add_tags',[]):tagging.attach_tag(local,row,tag['name'],tag['namespace'])

def execute_sync(local,row,payload):
    if row.kind=='media_batch_update':
        for item in payload['items']:apply_media_patch(local,local.get(models.Media,item['media_id']),item['patch'])
        results=[dict(media_id=x['media_id'],status='applied') for x in payload['items']]
    elif row.kind=='tag_rename':
        tag=local.get(models.Tag,payload['tag_id']);tag.name=payload['name'].strip();tag.namespace=(payload.get('namespace') or tag.namespace or 'general').strip();results=[]
    else:
        source=local.get(models.Tag,payload['source_tag_id']);target=local.get(models.Tag,payload['target_tag_id'])
        for media in list(source.media_items):
            if target not in media.tags:media.tags.append(target)
            media.tags.remove(source)
        local.delete(source);results=[]
    from ..creators import clear_creator_cache
    clear_creator_cache()
    return s.ActionResultDTO(proposal_id=row.id,state='applied',items=results)

def confirm_operation(db,user_id,proposal_id,payload_hash):
    initial=owned(db,user_id,proposal_id)
    if initial.normalized_payload_hash!=payload_hash:raise HTTPException(409,'assistant_proposal_hash_mismatch')
    queued=False;stale=False
    with write_transaction(db) as local:
        row=owned(local,user_id,proposal_id)
        if row.normalized_payload_hash!=payload_hash:raise HTTPException(409,'assistant_proposal_hash_mismatch')
        if row.state in ('applied','queued'):return s.ActionResultDTO.model_validate_json(row.result_json)
        ensure_approvable(local,row)
        payload=json.loads(row.payload_json);preview=revalidate_preview(local,row,payload)
        if preview is None or preview.fingerprint!=row.target_fingerprint:
            row.state='stale';row.consumed_at=utcnow();stale=True
        else:
            if OPERATION_REGISTRY[row.kind].async_job:
                from .operation_jobs import reserve_operation_job
                result=reserve_operation_job(local,row);row.state='queued';queued=True
            else:
                result=execute_sync(local,row,payload);row.state='applied'
            row.result_json=result.model_dump_json();row.consumed_at=utcnow()
            local.add(AssistantAudit(proposal_id=row.id,user_id=user_id,kind=row.kind,changes_json=canonical_json(dict(before=preview.before,after=preview.after)),result_json=row.result_json))
    if stale:raise HTTPException(409,'assistant_proposal_stale')
    if queued:
        from .operation_jobs import enqueue_operation_job
        enqueue_operation_job(proposal_id)
    return result

def derive_selected_proposal(db,user_id,proposal_id,selected_target_ids):
    selected=set(selected_target_ids)
    if len(selected)!=len(selected_target_ids):raise HTTPException(422,'assistant_invalid_proposal')
    with write_transaction(db) as local:
        old=owned(local,user_id,proposal_id);ensure_approvable(local,old)
        if old.kind!='media_batch_update':raise HTTPException(422,'assistant_invalid_proposal')
        payload=json.loads(old.payload_json)
        if not selected.issubset({x['media_id'] for x in payload['items']}):raise HTTPException(422,'assistant_invalid_proposal')
        if len(selected)==len(payload['items']):return proposal_dto(old)
        if preview_operation(local,old.kind,payload).fingerprint!=old.target_fingerprint:raise HTTPException(409,'assistant_proposal_stale')
        payload['items']=[x for x in payload['items'] if x['media_id'] in selected]
        preview=preview_operation(local,old.kind,payload)
        row=insert_operation(local,user_id,old.session_id,old.run_id,old.kind,payload,preview,old.expires_at)
        old.state='stale';old.consumed_at=utcnow()
        return proposal_dto(row)
