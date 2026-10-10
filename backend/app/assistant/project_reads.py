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
from .readonly import folder_label, media_dto, page
from .tool_catalog import TOOL_CATALOG

PROJECT_TOOLS = frozenset(("list_creators", "get_creator_detail", "list_tasks", "get_task_detail", "get_project_status", "get_project_settings", "read_logs"))

def project_status(db):
    storage = []
    roots = db.query(models.Folder).order_by(models.Folder.id).limit(50).all()
    for row in roots:
        data = dict(folder_id=row.id, display_name=folder_label(row.path, "目录 " + str(row.id)), available=False)
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

def execute_project_read(db, principal, context, name, args):
    require_tool_context(db, principal, context)
    q = TOOL_CATALOG[name].args_type.model_validate(args)
    if name == "read_logs":
        from ..services.assistant_runtime_logs import read_events
        from .models import AssistantToolEvent
        result=read_events(q.source,q.cursor,q.limit).model_dump(mode="json")
        if q.source in ('all','auto_sync'):
            from datetime import datetime
            from ..services.assistant_runtime_logs import event_summary
            logs=db.query(models.AutoSyncLog)
            if q.cursor:
                try:
                    stamp,tail=q.cursor.split('-',1);at=datetime.strptime(stamp,'%Y%m%d%H%M%S%f');numeric=int(tail,16)
                    logs=logs.filter(or_(models.AutoSyncLog.started_at<at,(models.AutoSyncLog.started_at==at)&(models.AutoSyncLog.id<numeric)))
                except ValueError:raise HTTPException(422,'assistant_invalid_tool_args') from None
            for log in logs.order_by(models.AutoSyncLog.started_at.desc(),models.AutoSyncLog.id.desc()).limit(q.limit+1):
                state=log.status if log.status in ('success','failed','partial') else 'failed'
                event=dict(timestamp=log.started_at.isoformat()+'Z',service='auto_sync',level='INFO' if state=='success' else 'WARNING',code='auto_sync_'+state,object_id='source-'+str(log.source_id),request_id=None,cursor=log.started_at.strftime('%Y%m%d%H%M%S%f')+'-'+format(log.id,'032x'),status=state,progress_count=max(0,log.downloaded_count or 0),total_count=max(0,(log.downloaded_count or 0)+(log.failed_count or 0)))
                from .task_reads import safe_reason
                event['summary']=event_summary(event)+('；'+safe_reason(log.message) if state!='success' else '');result['items'].append(event)
            result['has_more']=result['has_more'] or len(result['items'])>q.limit
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
        result['items'].sort(key=lambda x:x['cursor'],reverse=True)
        result['has_more']=result['has_more'] or len(result['items'])>q.limit
        result['items']=result['items'][:q.limit]
        result['next_cursor']=result['items'][-1]['cursor'] if result['items'] else None
    elif name == "get_project_status":
        result = project_status(db)
    elif name == "get_project_settings":
        settings=[dict(id=x.id,scan_mode=x.scan_mode or 'auto',thumbnail_enabled=bool(x.thumbnail_enabled),thumbnail_interval=max(0,x.thumbnail_interval or 1)) for x in db.query(models.Folder).order_by(models.Folder.id)]
        for cls,typ in ((models.ExternalFavoriteSource,None),(models.XImportSource,'x')):
            for x in db.query(cls).order_by(cls.id):settings.append(dict(kind='source',id=x.id,name=x.name or '数据源',source_type=typ or x.source_type or 'wnacg',download_root_name=folder_label(x.download_root_path, None),auto_sync_enabled=bool(x.auto_sync_enabled),auto_sync_interval_hours=max(0,x.auto_sync_interval_hours or 24),next_run_at=x.auto_sync_next_run_at))
        result=page(settings[q.offset:q.offset+q.limit],len(settings),q)
    elif name in ("list_tasks","get_task_detail"):
        from .task_reads import all_tasks
        tasks=all_tasks(db,principal.user_id,task_visible)
        if name=='get_task_detail':
            result=next((x for x in tasks if x['task_id']==q.task_id),None)
            if result is None:raise HTTPException(404,'assistant_not_found')
        else:
            if q.kind:tasks=[x for x in tasks if x['kind']==q.kind]
            result=page(tasks[q.offset:q.offset+q.limit],len(tasks),q)
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
