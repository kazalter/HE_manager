"""Administrator-only HE confirmation and durable job views."""

from fastapi import APIRouter, Depends
from pydantic import Field
from .. import auth
from ..database import get_db
from ..assistant import actions, proposals, scan_jobs, schemas

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
    return scan_jobs.get_owned_scan_job(db, user.id, job_id)
