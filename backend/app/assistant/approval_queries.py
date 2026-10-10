"""Current administrator's effective proposals and actual HE capabilities."""
import json
from sqlalchemy import or_,and_
from fastapi import HTTPException
from . import schemas as s
from .models import AssistantProposal,AssistantRun,AssistantSession
from .proposals import proposal_dto,owned
from .store import require_admin,utcnow
from .tool_catalog import TOOL_CATALOG
from .. import models

def approval_rows(db,user_id):
    return db.query(AssistantProposal,AssistantSession,AssistantRun).join(AssistantSession,AssistantSession.id==AssistantProposal.session_id).join(AssistantRun,AssistantRun.id==AssistantProposal.run_id).filter(AssistantProposal.user_id==user_id)

def pending_condition():
    return and_(AssistantProposal.state=='pending',AssistantProposal.expires_at>utcnow(),AssistantSession.state=='active',AssistantRun.stop_requested_at.is_(None),AssistantRun.status.in_(('submitting','running','completed')),or_(AssistantRun.status=='completed',AssistantRun.deadline_at.is_(None),AssistantRun.deadline_at>utcnow()))

def list_approvals(db,user_id,tab,limit,offset):
    require_admin(db,user_id)
    rows=approval_rows(db,user_id);pending_count=rows.filter(pending_condition()).count()
    if tab=='pending':rows=rows.filter(pending_condition())
    total=rows.count();items=[]
    for row,session,run in rows.order_by(AssistantProposal.created_at.desc(),AssistantProposal.id).offset(offset).limit(limit):
        dto=proposal_dto(row);state=row.state
        if state=='pending':
            if row.expires_at<=utcnow():state='expired'
            elif session.state!='active' or run.stop_requested_at or run.status not in ('submitting','running','completed') or (run.status!='completed' and run.deadline_at and run.deadline_at<=utcnow()):state='stale'
        items.append(dto.model_copy(update={'session_title':session.title,'state':state}))
    return s.ApprovalPageDTO(items=items,total=total,offset=offset,has_more=offset+len(items)<total,pending_count=pending_count)

def capabilities(db,user_id):
    require_admin(db,user_id)
    from .file_reads import root_path
    roots=[]
    for row in db.query(models.Folder).order_by(models.Folder.id).limit(50):
        readable=True
        try:root_path(db,row.id)
        except HTTPException:readable=False
        roots.append(s.FolderDTO(id=row.id,display_name=row.path.replace('\\','/').rstrip('/').split('/')[-1] or '媒体目录',path=row.path,status=row.status or 'idle',readable=readable))
    return s.CapabilitiesDTO(read_tools=[k for k,v in TOOL_CATALOG.items() if v.mode=='read'],proposal_tools=[k for k,v in TOOL_CATALOG.items() if v.mode=='proposal'],file_roots=roots)

def proposal_targets(db,user_id,proposal_id,limit,offset):
    row=owned(db,user_id,proposal_id)
    all_items=json.loads(row.targets_json or '[]')
    if row.kind=='file_move':
        from .models import AssistantFileOperation
        journal=db.get(AssistantFileOperation,row.id)
        if journal:
            changes=json.loads(journal.relationships_json)
            all_items=[dict(id=x['id'],type=x['model'],label=f"{x['model']} #{x['id']}",before=x['before'],after=x['after']) for x in changes]
    total=len(all_items);items=all_items[offset:offset+limit]
    return dict(items=items,total=total,offset=offset,has_more=offset+len(items)<total)
