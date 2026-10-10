"""Exactly-once business changes under a fresh BEGIN IMMEDIATE transaction."""

import json
from fastapi import HTTPException
from sqlalchemy.orm import selectinload
from .. import models, tagging
from . import config, schemas
from .models import AssistantAudit
from .proposals import owned, media_snapshot, folder_snapshot
from .readonly import visible
from .store import (
    input_hash,
    require_owned_session,
    require_owned_run,
    utcnow,
    write_transaction,
)


def confirm_proposal(db, user_id, proposal_id, payload_hash, *, enqueue=None):
    config.require_enabled()
    initial = owned(db, user_id, proposal_id)
    if initial.normalized_payload_hash != payload_hash:
        raise HTTPException(409, "assistant_proposal_hash_mismatch")
    if (
        initial.kind == "scan"
        and initial.state == "pending"
        and initial.expires_at > utcnow()
    ):
        from . import scan_jobs

        scan_jobs.preflight_scan(db, initial)
    reservation = None
    error = None
    result = None
    queued = False
    try:
        with write_transaction(db) as local:
            proposal = owned(local, user_id, proposal_id)
            if proposal.normalized_payload_hash != payload_hash:
                raise HTTPException(409, "assistant_proposal_hash_mismatch")
            if proposal.state in ("applied", "queued"):
                return schemas.ActionResultDTO.model_validate_json(proposal.result_json)
            if proposal.state != "pending":
                raise HTTPException(409, "assistant_proposal_consumed")
            session = require_owned_session(local, user_id, proposal.session_id)
            run = require_owned_run(local, user_id, proposal.run_id)
            if (
                session.state != "active"
                or run.stop_requested_at is not None
                or run.status not in ("submitting", "running", "completed")
            ):
                raise HTTPException(409, "assistant_proposal_unavailable")
            if proposal.expires_at <= utcnow():
                proposal.state = "expired"
                proposal.consumed_at = utcnow()
                error = "assistant_proposal_expired"
            else:
                payload = json.loads(proposal.payload_json)
                if proposal.kind == "media_update":
                    media = (
                        visible(local)
                        .options(selectinload(models.Media.tags))
                        .filter(models.Media.id == proposal.target_id)
                        .first()
                    )
                    fingerprint = (
                        input_hash(media_snapshot(media, payload["patch"]))
                        if media
                        else None
                    )
                else:
                    folder = local.get(models.Folder, proposal.target_id)
                    fingerprint = (
                        input_hash(folder_snapshot(folder)) if folder else None
                    )
                if fingerprint != proposal.target_fingerprint:
                    proposal.state = "stale"
                    proposal.consumed_at = utcnow()
                    error = "assistant_proposal_stale"
                else:
                    if proposal.kind == "media_update":
                        patch = payload["patch"]
                        for name in ("rating", "favorite", "source_url"):
                            if name in patch:
                                setattr(media, name, patch[name])
                        remove = set(patch.get("remove_tag_ids", []))
                        media.tags = [t for t in media.tags if t.id not in remove]
                        for tag in patch.get("add_tags", []):
                            tagging.attach_tag(
                                local, media, tag["name"], tag["namespace"]
                            )
                        result = schemas.ActionResultDTO(
                            proposal_id=proposal.id, state="applied", media_id=media.id
                        )
                        proposal.state = "applied"
                    else:
                        from . import scan_jobs

                        reservation = scan_jobs.reserve_scan(local, proposal.target_id)
                        result = scan_jobs.insert_job(local, proposal)
                        proposal.state = "queued"
                        queued = True
                    proposal.consumed_at = utcnow()
                    proposal.result_json = result.model_dump_json()
                    local.add(
                        AssistantAudit(
                            proposal_id=proposal.id,
                            user_id=user_id,
                            kind=proposal.kind,
                            changes_json=json.dumps(
                                {
                                    "target_id": proposal.target_id,
                                    "before": json.loads(proposal.before_json),
                                    "after": json.loads(proposal.after_json),
                                },
                                ensure_ascii=False,
                            ),
                            result_json=proposal.result_json,
                        )
                    )
    except BaseException:
        if reservation is not None:
            from . import scan_jobs

            scan_jobs.scanner.release_folder_scan(initial.target_id, reservation)
        raise
    if error:
        raise HTTPException(409, error)
    if queued:
        try:
            (enqueue or scan_jobs.enqueue_scan_job)(
                result.job_id, initial.target_id, reservation
            )
        except Exception:
            scan_jobs.scanner.release_folder_scan(initial.target_id, reservation)
            result = scan_jobs.save_scan_status(
                result.job_id, "failed", "扫描排队失败，未自动重放；请检查后重新发起。"
            )
    return result
