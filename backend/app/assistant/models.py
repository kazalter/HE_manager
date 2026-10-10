"""Assistant state is persistent; business writes belong to explicit confirmation."""

from datetime import datetime
from uuid import uuid4
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from ..database import Base


def new_id():
    return str(uuid4())


class AssistantToolIdentity(Base):
    __tablename__ = "assistant_tool_identities"
    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    profile_name = Column(String(100), unique=True, nullable=False)
    tool_token_hash = Column(String(64), unique=True, nullable=False, index=True)
    credential_generation = Column(Integer, nullable=False, default=1)
    enabled = Column(Boolean, nullable=False, default=False)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class AssistantSession(Base):
    __tablename__ = "assistant_sessions"
    id = Column(String(36), primary_key=True, default=new_id)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    upstream_session_id = Column(String(100), unique=True, nullable=False)
    title = Column(String(100), nullable=False, default="新对话")
    state = Column(String(20), nullable=False, default="creating")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    error_code = Column(String(100), nullable=True)


class AssistantRun(Base):
    __tablename__ = "assistant_runs"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "client_request_id", name="uq_assistant_run_request"
        ),
    )
    id = Column(String(36), primary_key=True, default=new_id)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    session_id = Column(
        String(36), ForeignKey("assistant_sessions.id"), nullable=False, index=True
    )
    client_request_id = Column(String(36), nullable=False)
    input_hash = Column(String(64), nullable=False)
    upstream_run_id = Column(String(100), nullable=True, index=True)
    status = Column(String(30), nullable=False, default="submitting")
    submission_envelope_json = Column(Text, nullable=True)
    api_key_generation = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    deadline_at = Column(DateTime, nullable=True)
    stop_requested_at = Column(DateTime, nullable=True)
    executor_exited_at = Column(DateTime, nullable=True)
    final_message_id = Column(String(36), nullable=False, default=new_id)
    output = Column(Text, nullable=False, default="")
    usage_json = Column(Text, nullable=True)
    error_code = Column(String(100), nullable=True)
    tool_results_json = Column(Text, nullable=False, default="[]")
    tool_results_truncated = Column(Boolean, nullable=False, default=False)


class AssistantProposal(Base):
    __tablename__ = "assistant_proposals"
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "kind",
            "normalized_payload_hash",
            name="uq_assistant_proposal_payload",
        ),
    )
    id = Column(String(36), primary_key=True, default=new_id)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    session_id = Column(
        String(36), ForeignKey("assistant_sessions.id"), nullable=False, index=True
    )
    run_id = Column(
        String(36), ForeignKey("assistant_runs.id"), nullable=False, index=True
    )
    kind = Column(String(30), nullable=False)
    target_id = Column(Integer, nullable=False)
    target_label = Column(String(500), nullable=False)
    normalized_payload_hash = Column(String(64), nullable=False)
    payload_json = Column(Text, nullable=False)
    before_json = Column(Text, nullable=False)
    after_json = Column(Text, nullable=False)
    target_fingerprint = Column(String(64), nullable=False)
    state = Column(String(20), nullable=False, default="pending")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    result_json = Column(Text, nullable=True)
    consumed_at = Column(DateTime, nullable=True)


class AssistantAudit(Base):
    __tablename__ = "assistant_audits"
    id = Column(String(36), primary_key=True, default=new_id)
    proposal_id = Column(
        String(36), ForeignKey("assistant_proposals.id"), unique=True, nullable=False
    )
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    kind = Column(String(30), nullable=False)
    changes_json = Column(Text, nullable=False)
    result_json = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class AssistantToolEvent(Base):
    __tablename__ = "assistant_tool_events"
    id = Column(String(36), primary_key=True, default=new_id)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    run_id = Column(String(36), ForeignKey("assistant_runs.id"), nullable=False)
    tool_name = Column(String(80), nullable=False)
    error_code = Column(String(100), nullable=False)
    request_id = Column(String(36), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
