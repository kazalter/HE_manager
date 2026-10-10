"""Explicit business projections, never raw ORM/provider configuration."""
import os
import shutil
from sqlalchemy import func, literal, select, or_
from sqlalchemy.engine import make_url
from fastapi import HTTPException
from .. import models
from ..services import backup
from . import schemas as s
from .identity import require_tool_context
from .models import AssistantProposal
from .readonly import media_dto, page
from .tool_catalog import TOOL_CATALOG

PROJECT_TOOLS = frozenset(("list_creators", "get_creator_detail", "list_tasks", "get_task_detail", "get_project_status", "get_project_settings", "read_logs"))

def project_status(db):
    storage = []
    roots = db.query(models.Folder).order_by(models.Folder.id).limit(50).all()
    for row in roots:
        data = dict(folder_id=row.id, path=row.path or "", available=False)
        try:
            usage = shutil.disk_usage(row.path)
            data.update(available=os.path.isdir(row.path), total_bytes=usage.total, free_bytes=usage.free)
        except OSError:
            pass
        storage.append(data)
    path = make_url(str(db.get_bind().url)).database
    entries = backup.list_backups(backup.get_default_backup_dir(path)) if path else []
    safe = [{k: x[k] for k in ("name", "size_bytes", "modified_at")} for x in entries[:50]]
    return dict(health="ok", storage=storage, backup=safe, backup_count=len(entries), truncated=db.query(models.Folder).count()>50 or len(entries)>50)

def task_visible(db, row, user_id):
    if not (row.kind or "").startswith("assistant_"):
        return True
    prefix = "assistant-scan-" if row.kind == "assistant_scan" else "assistant-operation-"
    pid = row.job_id.removeprefix(prefix)
    return db.query(AssistantProposal.id).filter(AssistantProposal.id == pid, AssistantProposal.user_id == user_id).first() is not None

def task_dto(row):
    labels = {"queued":"等待中", "running":"执行中", "completed":"已完成", "failed":"失败", "interrupted":"已中断", "needs_recovery":"需要恢复"}
    return dict(task_id=row.job_id, kind=row.kind or "unknown", status=row.status or "unknown", progress=None, created_at=row.created_at, finished_at=row.finished_at, summary=labels.get(row.status,"状态待核实"))

def execute_project_read(db, principal, context, name, args):
    require_tool_context(db, principal, context)
    q = TOOL_CATALOG[name].args_type.model_validate(args)
    if name == "read_logs":
        from ..services.assistant_runtime_logs import read_events
        from .models import AssistantToolEvent
        result=read_events(q.source,q.cursor,q.limit).model_dump(mode="json")
        if q.source in ("all","assistant"):
            rows=db.query(AssistantToolEvent).filter(AssistantToolEvent.user_id==principal.user_id)
            if q.cursor:
                from datetime import datetime
                from uuid import UUID
                try:
                    stamp,tail=q.cursor.split("-",1);at=datetime.strptime(stamp,"%Y%m%d%H%M%S%f");eid=str(UUID(tail))
                    rows=rows.filter(or_(AssistantToolEvent.created_at<at,(AssistantToolEvent.created_at==at)&(AssistantToolEvent.id<eid)))
                except ValueError:raise HTTPException(422,"assistant_invalid_tool_args") from None
            events=rows.order_by(AssistantToolEvent.created_at.desc(),AssistantToolEvent.id.desc()).limit(q.limit+1).all()
            from .tool_errors import MESSAGES
            for e in events:
                cursor=e.created_at.strftime("%Y%m%d%H%M%S%f")+'-'+e.id.replace('-','')
                if q.cursor and cursor>=q.cursor:continue
                result['items'].append(dict(timestamp=e.created_at.isoformat()+'Z',service="assistant",level="WARNING",code=e.error_code,object_id=e.tool_name,summary=MESSAGES.get(e.error_code,"工具调用未成功"),request_id=e.request_id,cursor=cursor))
            result['items'].sort(key=lambda x:x['timestamp'],reverse=True)
            result['has_more']=result['has_more'] or len(result['items'])>q.limit
            result['items']=result['items'][:q.limit]
            result['next_cursor']=result['items'][-1]['cursor'] if result['items'] else None
    elif name == "get_project_status":
        result = project_status(db)
    elif name == "get_project_settings":
        rows = db.query(models.Folder).order_by(models.Folder.id)
        result = page([dict(id=x.id, scan_mode=x.scan_mode or "auto", thumbnail_enabled=bool(x.thumbnail_enabled), thumbnail_interval=max(0,x.thumbnail_interval or 1)) for x in rows.offset(q.offset).limit(q.limit)], rows.count(), q)
    elif name in ("list_tasks","get_task_detail"):
        rows = db.query(models.BackgroundJob).order_by(models.BackgroundJob.created_at.desc(), models.BackgroundJob.job_id)
        if name == "get_task_detail":
            row = rows.filter(models.BackgroundJob.job_id == q.task_id).first()
            if not row or not task_visible(db,row,principal.user_id):
                raise HTTPException(404,"assistant_not_found")
            result = task_dto(row)
        else:
            if q.kind:
                rows = rows.filter(models.BackgroundJob.kind == q.kind)
            allowed = [x for x in rows if task_visible(db,x,principal.user_id)]
            result = page([task_dto(x) for x in allowed[q.offset:q.offset+q.limit]],len(allowed),q)
    elif name == "list_creators":
        artists = select((literal("a:")+models.Media.artist).label("key"),models.Media.artist.label("name"),func.count(models.Media.id).label("media_count")).where(models.Media.artist.isnot(None),models.Media.artist != "").group_by(models.Media.artist)
        authors = select((literal("x:")+models.XPost.author_screen_name).label("key"),models.XPost.author_screen_name.label("name"),func.count(func.distinct(models.Media.id)).label("media_count")).join(models.XMediaItem,models.XMediaItem.post_id==models.XPost.id).join(models.Media,models.Media.id==models.XMediaItem.library_media_id).where(models.XPost.author_screen_name.isnot(None)).group_by(models.XPost.author_screen_name)
        combined = artists.union_all(authors).subquery()
        rows = db.query(combined)
        if q.search:
            rows=rows.filter(combined.c.name.icontains(q.search,autoescape=True))
        result=page([dict(x._mapping) for x in rows.order_by(combined.c.name,combined.c.key).offset(q.offset).limit(q.limit)],rows.count(),q)
    else:
        rows=db.query(models.Media)
        if q.key.startswith("a:"):
            rows=rows.filter(models.Media.artist==q.key[2:])
        elif q.key.startswith("x:"):
            rows=rows.join(models.XMediaItem,models.XMediaItem.library_media_id==models.Media.id).join(models.XPost,models.XPost.id==models.XMediaItem.post_id).filter(models.XPost.author_screen_name==q.key[2:]).distinct()
        else:
            raise HTTPException(422,"assistant_invalid_tool_args")
        result={**page([media_dto(x) for x in rows.order_by(models.Media.id.desc()).offset(q.offset).limit(q.limit)],rows.count(),q),"key":q.key,"name":q.key[2:]}
    return s.RESULT_TYPES[name].model_validate(result).model_dump(mode="json")
