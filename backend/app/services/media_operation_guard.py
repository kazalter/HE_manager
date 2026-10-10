"""Shared HE mutations coexist; approved file moves require exclusive access."""
import threading
import time
from contextlib import contextmanager
from functools import wraps
from fastapi import HTTPException

_CONDITION=threading.Condition(threading.RLock());_READERS=0;_OWNER=None;_BLOCKED=False
_LOCAL=threading.local()

def block_unresolved(value=True):
    global _BLOCKED
    with _CONDITION:_BLOCKED=value;_CONDITION.notify_all()

@contextmanager
def project_mutation():
    global _READERS
    ident=threading.get_ident()
    if getattr(_LOCAL,'depth',0) or _OWNER==ident:
        _LOCAL.depth=getattr(_LOCAL,'depth',0)+1
        try:yield
        finally:_LOCAL.depth-=1
        return
    deadline=time.monotonic()+10
    with _CONDITION:
        while _OWNER is not None:
            remaining=deadline-time.monotonic()
            if remaining<=0:raise HTTPException(409,'assistant_operation_busy')
            _CONDITION.wait(remaining)
        if _BLOCKED:raise HTTPException(409,'assistant_file_needs_recovery')
        _READERS+=1;_LOCAL.depth=1
    try:yield
    finally:
        with _CONDITION:_LOCAL.depth=0;_READERS-=1;_CONDITION.notify_all()

@contextmanager
def acquire_media_operation(folder_ids,media_ids):
    global _OWNER
    ident=threading.get_ident()
    with _CONDITION:
        if _BLOCKED:raise HTTPException(409,'assistant_file_needs_recovery')
        if _READERS or _OWNER is not None:raise HTTPException(409,'assistant_operation_busy')
        _OWNER=ident
    try:yield
    finally:
        with _CONDITION:_OWNER=None;_CONDITION.notify_all()

def guarded_mutation(fn):
    @wraps(fn)
    def wrapped(*args,**kwargs):
        if fn.__name__ == 'confirm_proposal' and args:
            from ..assistant.models import AssistantProposal
            proposal_id=args[2] if len(args)>2 else kwargs.get('proposal_id')
            row=args[0].get(AssistantProposal,proposal_id)
            if row and row.kind in ('file_move','maintenance','scan'):
                return fn(*args,**kwargs)  # Enqueue first; executor owns the mutation lease.
        with project_mutation():return fn(*args,**kwargs)
    return wrapped
