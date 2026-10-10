"""Safe domain snapshots for jobs, scans, synchronization and owned Agent runs."""
import json
from .. import models
from .models import AssistantRun,AssistantProposal
from .store import utcnow

def number(value):return value if type(value) is int and 0<=value<=10**12 else None

def safe_reason(value):
    text=str(value or '').lower()
    if not text:return ''
    if any(x in text for x in ('401','403','unauthor','authentication','cookie','登录','鉴权')):return '来源身份不可用，请检查来源登录配置。'
    if any(x in text for x in ('timeout','timed out','超时')):return '请求超时，请稍后重试。'
    if any(x in text for x in ('not found','no such file','不存在','缺失')):return '文件或来源条目不存在。'
    if any(x in text for x in ('permission','权限')):return '文件或目录权限不足。'
    if any(x in text for x in ('space','storage','mount','空间','挂载')):return '存储不可用或空间不足。'
    return '任务失败；原始错误已隐藏，可查看脱敏运行日志。'

def task_dto(row):
    try:payload=json.loads(row.payload_json) if len(row.payload_json or '')<=2*1024*1024 else {}
    except (ValueError,TypeError):payload={}
    if not isinstance(payload,dict):payload={}
    public=payload.get('job',payload)
    if not isinstance(public,dict):public={}
    total=next((number(public[k]) for k in ('total','total_posts','total_media') if k in public and number(public[k]) is not None),None)
    completed=next((number(public[k]) for k in ('completed','completed_posts','completed_media') if k in public and number(public[k]) is not None),None)
    failed=next((number(public[k]) for k in ('failed','failed_posts','failed_media') if k in public and number(public[k]) is not None),None)
    progress=public.get('progress')
    if type(progress) not in (int,float) or not 0<=progress<=100:progress=round(100*(completed or 0)/total,1) if total else None
    labels={'queued':'等待中','preparing':'准备中','running':'执行中','paused':'已暂停','completed':'已完成','failed':'失败','canceled':'已取消','interrupted':'已中断','needs_recovery':'需要恢复'}
    summary=labels.get(row.status,'状态待核实')
    if total is not None:summary+=f'；完成 {completed or 0}/{total}，失败 {failed or 0}'
    if row.status in ('failed','interrupted','needs_recovery'):summary+='；'+safe_reason(public.get('message') or public.get('error') or summary)
    return dict(task_id=row.job_id,kind=row.kind or 'unknown',status=row.status or 'unknown',progress=progress,created_at=row.created_at,finished_at=row.finished_at,summary=summary,total_count=total,completed_count=completed,failed_count=failed)

def all_tasks(db,user_id,visible):
    result=[task_dto(x) for x in db.query(models.BackgroundJob) if visible(db,x,user_id)]
    for f in db.query(models.Folder):
        state='running' if f.status=='scanning' else 'failed' if f.status=='error' else 'completed' if f.last_scanned_at else 'idle'
        result.append(dict(task_id=f'scan-folder-{f.id}',kind='scan',status=state,progress=None,created_at=f.last_scanned_at,finished_at=f.last_scanned_at if state=='completed' else None,summary='目录扫描：'+{'running':'执行中','failed':'失败，请查看扫描日志','completed':'最近扫描已完成','idle':'尚未扫描'}[state]))
    for cls,source_type in ((models.ExternalFavoriteSource,None),(models.XImportSource,'x')):
        for source in db.query(cls):
            typ=source_type or source.source_type or 'wnacg'
            state=source.auto_sync_last_status or 'idle'
            result.append(dict(task_id=f'auto-sync-{typ}-{source.id}',kind='auto_sync',status='completed' if state=='success' else 'failed' if state=='failed' else 'running' if state=='running' else 'idle',progress=None,created_at=source.auto_sync_last_run_at,finished_at=None,summary='自动同步：'+{'success':'最近运行成功','failed':safe_reason(source.auto_sync_last_message),'running':'执行中'}.get(state,'尚未运行')))
    for run in db.query(AssistantRun).filter(AssistantRun.user_id==user_id):
        result.append(dict(task_id='assistant-run-'+run.id,kind='assistant_run',status=run.status,progress=None,created_at=run.created_at,finished_at=run.executor_exited_at,summary='管家运行：'+{'completed':'已完成','running':'执行中','submitting':'提交中','cancelled':'已停止','interrupted':'已中断','failed':'失败'}.get(run.status,'状态待核实')+('；'+safe_reason(run.error_code) if run.error_code else '')))
    return sorted(result,key=lambda x:(x['created_at'].isoformat() if x.get('created_at') else '',x['task_id']),reverse=True)
