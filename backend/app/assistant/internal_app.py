"""Private tool app: no main lifespan, schedulers, public routes or migrations."""

import json
from uuid import uuid4
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
import logging
from .tool_catalog import TOOL_CATALOG
from .project_reads import PROJECT_TOOLS, execute_project_read
from .file_reads import FILE_TOOLS, execute_file_read
from .tool_errors import safe_tool_error
from .models import AssistantToolEvent
from .store import utcnow
from pydantic import ValidationError
from sqlalchemy import inspect
from starlette.concurrency import run_in_threadpool
from ..database import get_db
from . import schemas
from .identity import authenticate_tool_token, require_tool_context
from .readonly import execute_read_tool, READ_TOOLS
from .proposals import create_proposal, PROPOSAL_TOOLS
from .store import canonical_json, write_transaction

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
MAX_RESULTS = 1024 * 1024
logger = logging.getLogger(__name__)

@app.exception_handler(HTTPException)
async def safe_http_error(request, exc):
    error = safe_tool_error(exc.status_code, exc.detail if isinstance(exc.detail, str) else "", str(uuid4()))
    logger.warning("HE tool error code=%s request_id=%s status=%s", error.code, error.request_id, exc.status_code)
    return JSONResponse(error.model_dump(), status_code=exc.status_code)


class ToolRequest(schemas.DTO):
    context: schemas.ToolContext
    args: dict


def bounded_result(name, result):
    result = schemas.RESULT_TYPES[name].model_validate(result).model_dump(mode="json")
    while len(canonical_json(result).encode("utf-8")) > 48 * 1024:
        if isinstance(result.get("items"), list) and result["items"]:
            result["items"].pop()
            result["has_more"] = True
            if "offset" in result:
                result["next_offset"] = result["offset"] + len(result["items"])
            elif "next_cursor" in result:
                result["next_cursor"] = result["items"][-1]["cursor"] if result["items"] else result.get("cursor")
        else:
            raise HTTPException(413, "assistant_content_too_large")
    return result


def record_tool_result(db, principal, context, name, result):
    try:
        result = bounded_result(name, result)
        validated = schemas.ToolResultDTO(
            tool_call_id=uuid4(), tool_name=name, result=result
        ).model_dump(mode="json")
    except (ValidationError, ValueError, TypeError):
        raise HTTPException(502, "assistant_invalid_tool_result") from None
    with write_transaction(db) as local:
        run = require_tool_context(local, principal, context)
        try:
            previous = json.loads(run.tool_results_json)
        except (ValueError, TypeError):
            raise HTTPException(503, "assistant_result_storage_invalid") from None
        raw = canonical_json(previous + [validated])
        if len(raw.encode("utf-8")) > MAX_RESULTS:
            run.tool_results_truncated = True
            validated = schemas.ToolResultDTO(
                tool_call_id=validated["tool_call_id"],
                tool_name=name,
                result=schemas.TruncatedDTO().model_dump(),
            ).model_dump(mode="json")
        else:
            run.tool_results_json = raw
        return validated


def execute_and_record(db, token, body, name):
    principal = authenticate_tool_token(db, token)
    require_tool_context(db, principal, body.context)
    try:
        TOOL_CATALOG[name].args_type.model_validate(body.args)
    except ValidationError:
        raise HTTPException(422, "assistant_invalid_tool_args") from None
    if name == "get_project_status":
        import urllib.request
        request = urllib.request.Request("http://backend:8010/assistant/internal/project-state", data=canonical_json({"context": body.context.model_dump(mode="json")}).encode(), headers={"Authorization":"Bearer "+token, "Content-Type":"application/json"})
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                raw=response.read(131073)
            if len(raw)>131072:
                raise ValueError
            result=json.loads(raw)
        except Exception:
            raise HTTPException(503,"assistant_tool_unavailable") from None
    elif name in FILE_TOOLS:
        result=execute_file_read(db,principal,body.context,name,body.args)
    elif name in PROJECT_TOOLS:
        try:
            result=execute_project_read(db,principal,body.context,name,body.args)
        except ValidationError:
            raise HTTPException(422,"assistant_invalid_tool_args") from None
    elif name in PROPOSAL_TOOLS:
        result = create_proposal(
            db, principal, body.context, PROPOSAL_TOOLS[name], body.args
        ).model_dump(mode="json")
    else:
        result = execute_read_tool(db, principal, body.context, name, body.args)
    return record_tool_result(db, principal, body.context, name, result)


@app.get("/healthz")
def health(db=Depends(get_db)):
    inspector = inspect(db.get_bind())
    required = {
        "assistant_tool_identities",
        "assistant_sessions",
        "assistant_runs",
        "assistant_proposals",
        "assistant_audits",
    }
    if not required.issubset(
        inspector.get_table_names()
    ) or "tool_results_truncated" not in {
        c["name"] for c in inspector.get_columns("assistant_runs")
    }:
        raise HTTPException(503, "assistant_schema_unavailable")
    return {"status": "ok"}


@app.post("/tools/{name}")
async def tool(name: str, request: Request, db=Depends(get_db)):
    if name not in TOOL_CATALOG:
        raise HTTPException(404, "assistant_unknown_tool")
    header = request.headers.get("authorization", "")
    if not header.startswith("Bearer ") or not 32 <= len(header[7:]) <= 1000:
        raise HTTPException(401, "assistant_invalid_tool_token")
    payload = bytearray()
    async for chunk in request.stream():
        if len(payload) + len(chunk) > 65536:
            raise HTTPException(413, "assistant_request_too_large")
        payload.extend(chunk)
    try:
        body = ToolRequest.model_validate_json(payload)
    except (ValidationError, ValueError):
        raise HTTPException(422, "assistant_invalid_tool_args") from None
    try:
        return await run_in_threadpool(execute_and_record, db, header[7:], body, name)
    except HTTPException as exc:
        error = safe_tool_error(exc.status_code, str(exc.detail), str(uuid4()))
        try:
            db.rollback()
            principal = authenticate_tool_token(db, header[7:])
            require_tool_context(db, principal, body.context)
            with write_transaction(db) as local:
                local.add(AssistantToolEvent(user_id=principal.user_id, run_id=str(body.context.run_id), tool_name=name, error_code=error.code, request_id=error.request_id))
                cutoff = utcnow() - __import__('datetime').timedelta(days=7)
                local.query(AssistantToolEvent).filter(AssistantToolEvent.created_at < cutoff).delete(synchronize_session=False)
        except Exception:
            db.rollback()
        return JSONResponse(error.model_dump(), status_code=exc.status_code)
