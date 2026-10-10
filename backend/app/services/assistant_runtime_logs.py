"""Structured, allowlisted runtime events. Never copies log messages/tracebacks."""
import json
import logging
import os
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from ..assistant.schemas import LogPageDTO

_LOCK=threading.Lock()
LABELS={"runtime_error":"运行错误", "runtime_warning":"运行提醒", "runtime_info":"运行事件", "file_missing":"文件不存在", "permission_denied":"目录或文件权限不足", "storage_unavailable":"存储不可用", "operation_started":"审批任务开始", "operation_completed":"审批任务完成", "operation_failed":"审批任务失败", "operation_recovery":"文件操作需要恢复", "tool_rejected":"工具调用未成功", "scan_started":"目录扫描开始", "scan_completed":"目录扫描结束", "scan_failed":"目录扫描失败"}
SOURCES={"assistant","scan","download","auto_sync","import","runtime"}

def log_dir():
    return Path(os.getenv("HE_ASSISTANT_LOG_DIR","/data/assistant-logs" if os.name!="nt" else "data/assistant-logs"))

def emit_event(service,level,code,object_id=None,summary_fields=None):
    if service not in SOURCES or code not in LABELS:return
    fields=summary_fields or {}
    safe_id=str(object_id) if object_id is not None else None
    if safe_id and not re.fullmatch(r"[A-Za-z0-9_-]{1,150}",safe_id):safe_id=None
    rid=str(fields.get("request_id", ""))
    if not re.fullmatch(r"[0-9a-f-]{36}",rid):rid=None
    event=dict(timestamp=datetime.now(timezone.utc).isoformat(),service=service,level=level if level in ("INFO","WARNING","ERROR") else "INFO",code=code,object_id=safe_id,summary=LABELS[code],request_id=rid,cursor=datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")+"-"+uuid4().hex)
    try:
        with _LOCK:
            root=log_dir();root.mkdir(parents=True,exist_ok=True,mode=0o700);file=root/'events.jsonl'
            if file.is_symlink():return
            if file.exists() and file.stat().st_size>5*1024*1024:
                for i in (2,1):
                    src=root/('events.jsonl' if i==1 else f'events.jsonl.{i-1}');dst=root/f'events.jsonl.{i}'
                    if src.exists():os.replace(src,dst)
            with file.open('a',encoding='utf-8') as out:out.write(json.dumps(event,ensure_ascii=False)+'\n')
            if os.name!="nt":
                file.chmod(0o640)
                if os.geteuid()==0:os.chown(file,0,1000)
    except OSError:
        pass

class SafeEventHandler(logging.Handler):
    def emit(self,record):
        if not record.name.startswith('app.') or record.name.startswith('app.services.assistant_runtime_logs'):return
        service='assistant' if '.assistant' in record.name else 'scan' if '.scan' in record.name else 'auto_sync' if 'auto_sync' in record.name else 'download' if 'download' in record.name else 'import' if 'import' in record.name else 'runtime'
        code='runtime_error' if record.levelno>=logging.ERROR else 'runtime_warning' if record.levelno>=logging.WARNING else 'runtime_info'
        if record.exc_info:
            kind=record.exc_info[0]
            if issubclass(kind,FileNotFoundError):code='file_missing'
            elif issubclass(kind,PermissionError):code='permission_denied'
        emit_event(service,'ERROR' if record.levelno>=40 else 'WARNING' if record.levelno>=30 else 'INFO',code)

def install_collector():
    root=logging.getLogger()
    if not any(isinstance(x,SafeEventHandler) for x in root.handlers):root.addHandler(SafeEventHandler())

def read_events(source,cursor,limit):
    events=[]
    for name in ('events.jsonl','events.jsonl.1','events.jsonl.2'):
        path=log_dir()/name
        if path.is_symlink():continue
        try:
            with path.open(encoding='utf-8') as file:
                for line in file:
                    if len(line)>8192:continue
                    try:
                        item=json.loads(line)
                        if item.get('service') not in SOURCES or item.get('code') not in LABELS:continue
                        if source!='all' and item['service']!=source:continue
                        if cursor and item['cursor']>=cursor:continue
                        item['summary']=LABELS[item['code']]
                        events.append(item)
                    except (ValueError,KeyError,TypeError):continue
        except OSError:pass
    events.sort(key=lambda x:x['cursor'],reverse=True)
    selected=events[:limit]
    return LogPageDTO(items=selected,cursor=cursor,next_cursor=selected[-1]['cursor'] if selected else None,has_more=len(events)>len(selected))
