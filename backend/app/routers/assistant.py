"""Administrator-only assistant sessions, streaming, confirmation and job views."""

import asyncio

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import Field
from .. import auth
from ..database import get_db
from ..assistant import actions, proposals, scan_jobs, schemas, sessions, store, config
from ..assistant.models import AssistantRun, AssistantSession, AssistantProposal

router = APIRouter(prefix="/assistant")


class Confirmation(schemas.DTO):
    payload_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


@router.get("/proposals/{proposal_id}", response_model=schemas.ProposalDTO)
def preview(proposal_id: str, user=Depends(auth.require_admin), db=Depends(get_db)):
    return proposals.get_owned_proposal(db, user.id, proposal_id)


@router.post("/proposals/{proposal_id}/confirm", response_model=schemas.ActionResultDTO)
def confirm(
    proposal_id: str,
    body: Confirmation,
    user=Depends(auth.require_admin),
    db=Depends(get_db),
):
    return actions.confirm_proposal(db, user.id, proposal_id, body.payload_hash)


@router.post("/proposals/{proposal_id}/reject", response_model=schemas.ProposalDTO)
def reject(proposal_id: str, user=Depends(auth.require_admin), db=Depends(get_db)):
    return proposals.reject_proposal(db, user.id, proposal_id)


@router.get("/jobs/{job_id}", response_model=schemas.JobDTO)
def job(job_id: str, user=Depends(auth.require_admin), db=Depends(get_db)):
    if job_id.startswith("assistant-operation-"):
        from ..assistant.operation_jobs import get_owned_operation_job
        return get_owned_operation_job(db,user.id,job_id)
    return scan_jobs.get_owned_scan_job(db, user.id, job_id)


@router.get("/status", response_model=schemas.AvailabilityDTO)
def availability(user=Depends(auth.require_admin), db=Depends(get_db)):
    store.require_admin(db, user.id)
    active = db.query(AssistantRun).filter(AssistantRun.executor_exited_at.is_(None))
    own = active.filter(AssistantRun.user_id == user.id).first()
    return schemas.AvailabilityDTO(
        enabled=config.enabled(),
        busy=active.first() is not None,
        active_run_id=own.id if own else None,
        error_code=own.error_code if own else None,
    )


@router.get("/sessions", response_model=schemas.SessionPageDTO)
def list_sessions(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user=Depends(auth.require_admin),
    db=Depends(get_db),
):
    store.require_admin(db, user.id)
    rows = db.query(AssistantSession).filter(
        AssistantSession.user_id == user.id, AssistantSession.state != "cleared"
    )
    total = rows.count()
    items = store.session_dtos(
        db,
        rows.order_by(
            AssistantSession.updated_at.desc(), AssistantSession.id
        ).offset(offset).limit(limit).all(),
    )
    return schemas.SessionPageDTO(
        items=items, total=total, offset=offset, has_more=offset + len(items) < total
    )


@router.post("/sessions", response_model=schemas.SessionDTO)
async def new_session(
    body: schemas.SessionRequest, user=Depends(auth.require_admin), db=Depends(get_db)
):
    return await sessions.create_session(db, user.id, body.title)


@router.get("/sessions/{session_id}/messages", response_model=schemas.HistoryPageDTO)
def messages(
    session_id: str,
    limit: int = Query(100, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user=Depends(auth.require_admin),
    db=Depends(get_db),
):
    return sessions.get_history(db, user.id, session_id, limit=limit, offset=offset)


@router.get("/sessions/{session_id}/proposals", response_model=schemas.ProposalPageDTO)
def session_proposals(
    session_id: str,
    limit: int = Query(50, ge=1, le=50),
    offset: int = Query(0, ge=0),
    user=Depends(auth.require_admin),
    db=Depends(get_db),
):
    session = store.require_owned_session(db, user.id, session_id)
    rows = db.query(AssistantProposal).filter(
        AssistantProposal.session_id == session.id, AssistantProposal.user_id == user.id
    )
    total = rows.count()
    items = [
        proposals.proposal_dto(r)
        for r in rows.order_by(
            AssistantProposal.created_at.desc(), AssistantProposal.id
        )
        .offset(offset)
        .limit(limit)
    ]
    return schemas.ProposalPageDTO(
        items=items, total=total, offset=offset, has_more=offset + len(items) < total
    )


@router.post("/sessions/{session_id}/runs", response_model=schemas.RunDTO)
async def run(
    session_id: str,
    body: schemas.RunRequest,
    user=Depends(auth.require_admin),
    db=Depends(get_db),
):
    return await sessions.submit_run(db, user.id, session_id, body)


@router.get("/runs/{run_id}", response_model=schemas.RunDTO)
def run_status(run_id: str, user=Depends(auth.require_admin), db=Depends(get_db)):
    return sessions.get_status(db, user.id, run_id)


@router.get("/runs/{run_id}/results", response_model=schemas.ToolResultsDTO)
def run_results(run_id: str, user=Depends(auth.require_admin), db=Depends(get_db)):
    return sessions.get_results(db, user.id, run_id)


@router.post("/runs/{run_id}/stop", response_model=schemas.RunDTO)
async def stop(run_id: str, user=Depends(auth.require_admin), db=Depends(get_db)):
    return await sessions.stop_run(db, user.id, run_id)


@router.delete("/sessions/{session_id}", response_model=schemas.SessionDTO)
async def clear(session_id: str, user=Depends(auth.require_admin), db=Depends(get_db)):
    return await sessions.clear_session(db, user.id, session_id)


async def encode_events(events):
    """Keep browser transport alive without cancelling a quiet upstream read."""
    iterator = events.__aiter__()
    pending = None
    try:
        yield ": open\n\n"
        while True:
            if pending is None:
                pending = asyncio.create_task(anext(iterator))
            done, _ = await asyncio.wait({pending}, timeout=10)
            if not done:
                yield ": keepalive\n\n"
                continue
            try:
                value = pending.result()
            except StopAsyncIteration:
                return
            pending = None
            # Synthetic result/state events do not overwrite the upstream cursor.
            prefix = (
                ("id: " + value.event_id + "\n") if value.event_id.isdecimal() else ""
            )
            yield prefix + "data: " + value.model_dump_json() + "\n\n"
    finally:
        if pending is not None:
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)
        if hasattr(iterator, "aclose"):
            await iterator.aclose()


@router.get("/runs/{run_id}/events")
async def events(
    run_id: str,
    last_event_id: str | None = Header(None),
    user=Depends(auth.require_admin),
    db=Depends(get_db),
):
    # Validate before sending HTTP 200; no authorization through a URL token.
    sessions.validate_stream(db, user.id, run_id, last_event_id)
    return StreamingResponse(
        encode_events(
            sessions.stream_events(db, user.id, run_id, last_event_id=last_event_id)
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class ProjectStateRequest(schemas.DTO):
    context: schemas.ToolContext

@router.post("/internal/project-state", response_model=schemas.ProjectStatusDTO, include_in_schema=False)
def internal_project_state(body: ProjectStateRequest, authorization: str = Header(default=""), db=Depends(get_db)):
    from ..assistant.identity import authenticate_tool_token, require_tool_context
    from ..assistant.project_reads import project_status
    if not authorization.startswith("Bearer "):
        raise HTTPException(401,"assistant_invalid_tool_token")
    principal=authenticate_tool_token(db,authorization[7:])
    require_tool_context(db,principal,body.context)
    return project_status(db)


@router.get("/media/{media_id}/preview")
def media_preview(media_id: int, page_index: int = Query(0, ge=0), user=Depends(auth.require_admin), db=Depends(get_db)):
    from ..assistant.file_reads import preview_payload
    from fastapi.responses import Response
    store.require_admin(db,user.id)
    payload,mime=preview_payload(db,media_id,page_index)
    return Response(payload,media_type=mime,headers={"Cache-Control":"no-store","X-Content-Type-Options":"nosniff"})
