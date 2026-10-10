"""Disposable HE tool identity and SQLite; launched only by integration tests."""

import unittest
from app.assistant import internal_app, proposals
from tests.assistant_fixtures import assistant_fixture, business_snapshot
from fastapi import HTTPException
from fastapi.responses import JSONResponse

owner = unittest.TestCase()
fixture = assistant_fixture(owner)
original = business_snapshot(fixture.engine)


def get_db():
    with fixture.factory() as db:
        yield db


internal_app.app.dependency_overrides[internal_app.get_db] = get_db
app = internal_app.app


@app.get("/fixture/context")
def context():
    return {
        "token": fixture.token,
        "context": fixture.context.model_dump(mode="json"),
        "profile": "he-user-1",
    }


@app.post("/fixture/reject/{proposal_id}")
def reject(proposal_id: str):
    with fixture.factory() as db:
        return proposals.reject_proposal(db, 1, proposal_id)


@app.get("/fixture/unchanged")
def unchanged():
    from app.assistant.models import AssistantProposal, AssistantAudit

    with fixture.factory() as db:
        return {
            "unchanged": business_snapshot(fixture.engine) == original,
            "proposals": db.query(AssistantProposal).count(),
            "audits": db.query(AssistantAudit).count(),
        }
