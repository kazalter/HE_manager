"""Short SQLite write transactions serialize admission with stop/confirmation."""

from contextlib import contextmanager
from datetime import datetime, timedelta
import hashlib
import json
from uuid import UUID, uuid4
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from ..models import User
from . import config
from .models import AssistantRun, AssistantSession
from .schemas import SessionDTO, SessionRequest, SubmissionEnvelope


def utcnow():
    return datetime.utcnow()


def canonical_json(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def input_hash(value):
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


@contextmanager
def write_transaction(db: Session):
    """Always use a clean connection, never a caller's pre-read ORM snapshot."""
    with db.get_bind().connect() as connection:
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        local = Session(bind=connection, expire_on_commit=False)
        try:
            yield local
            local.flush()
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            local.close()


def require_admin(db, user_id):
    user = db.execute(
        select(User).where(User.id == user_id).execution_options(populate_existing=True)
    ).scalar_one_or_none()
    if user is None or not user.is_admin or not user.is_active:
        raise HTTPException(403, "assistant_admin_required")
    return user


def uuid_text(value):
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(404, "assistant_not_found") from None


def require_owned_session(db, user_id, session_id):
    require_admin(db, user_id)
    row = db.execute(
        select(AssistantSession)
        .where(
            AssistantSession.id == uuid_text(session_id),
            AssistantSession.user_id == user_id,
        )
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "assistant_not_found")
    return row


def require_owned_run(db, user_id, run_id):
    require_admin(db, user_id)
    row = db.execute(
        select(AssistantRun)
        .where(AssistantRun.id == uuid_text(run_id), AssistantRun.user_id == user_id)
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "assistant_not_found")
    return row



DEFAULT_SESSION_TITLES = {"新对话", "恢复的对话"}


def title_from_input(text):
    """A local first-question preview: no extra model call or private-data export."""
    clean = " ".join(text.split()) if isinstance(text, str) else ""
    return (clean[:36].rstrip() + "…") if len(clean) > 36 else (clean or "新对话")


def title_from_envelope(raw):
    try:
        return title_from_input(json.loads(raw)["input"])
    except (ValueError, TypeError, KeyError):
        return "新对话"


def session_dtos(db, rows):
    """Name legacy untitled chats from their first input without writes on GET."""
    untitled = [row.id for row in rows if row.title in DEFAULT_SESSION_TITLES]
    titles = {}
    if untitled:
        first_runs = select(
            AssistantRun.session_id,
            AssistantRun.submission_envelope_json,
            func.row_number().over(
                partition_by=AssistantRun.session_id,
                order_by=(AssistantRun.created_at, AssistantRun.id),
            ).label("position"),
        ).where(AssistantRun.session_id.in_(untitled)).subquery()
        titles = {
            sid: title_from_envelope(raw)
            for sid, raw in db.execute(
                select(first_runs.c.session_id, first_runs.c.submission_envelope_json)
                .where(first_runs.c.position == 1)
            )
        }
    return [
        SessionDTO.model_validate(row).model_copy(
            update={"title": titles.get(row.id, row.title)}
        )
        for row in rows
    ]


def create_session(db, user_id, title="新对话"):
    config.require_enabled()
    title = SessionRequest(title=title).title
    with write_transaction(db) as local:
        require_admin(local, user_id)
        sid = str(uuid4())
        row = AssistantSession(
            id=sid,
            user_id=user_id,
            upstream_session_id="he-" + sid,
            title=title,
            state="creating",
        )
        local.add(row)
        local.flush()
        return row


def reserve_run(
    db,
    user_id,
    session_id,
    client_request_id,
    input_hash,
    submission_envelope: SubmissionEnvelope,
):
    config.require_enabled()
    sid = uuid_text(session_id)
    request_id = uuid_text(client_request_id)
    with write_transaction(db) as local:
        require_admin(local, user_id)
        existing = local.execute(
            select(AssistantRun).where(
                AssistantRun.user_id == user_id,
                AssistantRun.client_request_id == request_id,
            )
        ).scalar_one_or_none()
        if existing:
            if existing.session_id != sid or existing.input_hash != input_hash:
                raise HTTPException(409, "assistant_request_conflict")
            return existing
        session = require_owned_session(local, user_id, sid)
        if session.state != "active":
            raise HTTPException(409, "assistant_session_unavailable")
        if local.execute(
            select(AssistantRun.id)
            .where(AssistantRun.executor_exited_at.is_(None))
            .limit(1)
        ).first():
            raise HTTPException(409, "assistant_busy")
        envelope = SubmissionEnvelope.model_validate(submission_envelope)
        if envelope.session_id != session.upstream_session_id:
            raise HTTPException(409, "assistant_context_mismatch")
        raw = envelope.model_dump_json()
        if len(raw.encode("utf-8")) > 65536:
            raise HTTPException(422, "assistant_request_too_large")
        now = utcnow()
        if session.title in DEFAULT_SESSION_TITLES:
            first_input = local.execute(
                select(AssistantRun.submission_envelope_json)
                .where(AssistantRun.session_id == sid)
                .order_by(AssistantRun.created_at, AssistantRun.id)
                .limit(1)
            ).scalar_one_or_none()
            session.title = (
                title_from_envelope(first_input)
                if first_input else title_from_input(envelope.input)
            )
        session.updated_at = now
        row = AssistantRun(
            id=uuid_text(envelope.idempotency_key),
            user_id=user_id,
            session_id=sid,
            client_request_id=request_id,
            input_hash=input_hash,
            submission_envelope_json=raw,
            api_key_generation=envelope.api_key_generation,
            created_at=now,
            updated_at=now,
            deadline_at=now + timedelta(seconds=180),
            status="submitting",
        )
        local.add(row)
        local.flush()
        return row


def stop_run_row(local, row):
    from .models import AssistantProposal

    now = utcnow()
    if row.stop_requested_at is None:
        row.stop_requested_at = now
    if row.executor_exited_at is None:
        row.status = "stopping"
    row.updated_at = now
    local.query(AssistantProposal).filter(
        AssistantProposal.run_id == row.id, AssistantProposal.state == "pending"
    ).update({"state": "rejected", "consumed_at": now}, synchronize_session=False)
    return row


def mark_run_stopping(db, user_id, run_id):
    with write_transaction(db) as local:
        return stop_run_row(local, require_owned_run(local, user_id, run_id))


def mark_session_deleting(db, user_id, session_id):
    from .models import AssistantProposal

    with write_transaction(db) as local:
        session = require_owned_session(local, user_id, session_id)
        now = utcnow()
        session.state = "deleting"
        session.updated_at = now
        for row in local.query(AssistantRun).filter(
            AssistantRun.session_id == session.id
        ):
            if row.stop_requested_at is None:
                row.stop_requested_at = now
            if row.executor_exited_at is None:
                row.status = "stopping"
            row.updated_at = now
        local.query(AssistantProposal).filter(
            AssistantProposal.session_id == session.id,
            AssistantProposal.state == "pending",
        ).update({"state": "rejected", "consumed_at": now}, synchronize_session=False)
        return session
