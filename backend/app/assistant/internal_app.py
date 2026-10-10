"""Private tool app: no main lifespan, schedulers, public routes or migrations."""

import json
from uuid import uuid4
from fastapi import FastAPI, Depends, HTTPException, Request
from pydantic import ValidationError
from sqlalchemy import inspect
from starlette.concurrency import run_in_threadpool
from ..database import get_db
from . import schemas
from .identity import authenticate_tool_token, require_tool_context
from .readonly import execute_read_tool, READ_TOOLS
from .store import canonical_json, write_transaction

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
MAX_RESULTS = 65536


class ToolRequest(schemas.DTO):
    context: schemas.ToolContext
    args: dict


def record_tool_result(db, principal, context, name, result):
    try:
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
    if name not in READ_TOOLS:
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
    return await run_in_threadpool(execute_and_record, db, header[7:], body, name)
