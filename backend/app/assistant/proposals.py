"""Immutable, target-specific change previews. Creation never changes media."""

import json
from datetime import timedelta
from uuid import uuid4
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from .. import models
from . import schemas
from .identity import require_tool_context
from .models import AssistantProposal
from .readonly import visible
from .store import (
    canonical_json,
    input_hash,
    require_admin,
    utcnow,
    uuid_text,
    write_transaction,
)


class UpdateRequest(schemas.DTO):
    media_id: schemas.PositiveID
    patch: schemas.MediaPatch


class ScanRequest(schemas.DTO):
    folder_id: schemas.PositiveID


PROPOSAL_TOOLS = {"propose_media_update": "media_update", "propose_scan": "scan", "propose_media_batch_update":"media_batch_update", "propose_tag_rename":"tag_rename", "propose_tag_merge":"tag_merge", "propose_maintenance":"maintenance", "propose_file_move":"file_move"}


def normalize(kind, payload):
    try:
        request = (
            UpdateRequest if kind == "media_update" else ScanRequest
        ).model_validate(payload)
    except ValidationError:
        raise HTTPException(422, "assistant_invalid_proposal") from None
    if kind == "scan":
        return request.folder_id, {"folder_id": request.folder_id}
    patch = request.patch.model_dump(exclude_unset=True)
    if "add_tags" in patch:
        patch["add_tags"] = [
            {"name": name, "namespace": namespace}
            for name, namespace in sorted(
                {
                    (t["name"], t["namespace"])
                    for t in request.patch.model_dump()["add_tags"]
                }
            )
        ]
    if "remove_tag_ids" in patch:
        patch["remove_tag_ids"] = sorted(set(patch["remove_tag_ids"]))
    patch = {
        k: v for k, v in patch.items() if k not in ("add_tags", "remove_tag_ids") or v
    }
    if not patch:
        raise HTTPException(422, "assistant_empty_change")
    return request.media_id, {"media_id": request.media_id, "patch": patch}


def full_tags(media):
    return [
        {"id": t.id, "name": t.name or "", "namespace": t.namespace or "general"}
        for t in sorted(media.tags, key=lambda x: x.id)
    ]


def media_snapshot(media, patch):
    # Compare exact values, including the complete tag relationship. Only hashes
    # of credential-bearing values are saved outside the existing media record.
    value = {
        k: getattr(media, k) for k in patch if k in ("rating", "favorite", "source_url")
    }
    value["tags"] = full_tags(media)
    return value


def safe_url(value):
    if value is None:
        return None
    try:
        schemas.MediaPatch(source_url=value)
    except ValidationError:
        return "[已隐藏含凭据或无效的旧来源地址]"
    return value


def public_snapshot(snapshot):
    result = dict(snapshot)
    if "source_url" in result:
        result["source_url"] = safe_url(result["source_url"])
    # Tags have a 50-item display bound; the exact relationship is fingerprinted.
    tags = result.get("tags", [])
    result["tags"] = [
        {"id": t.get("id"), "name": t["name"][:80], "namespace": t["namespace"][:40]}
        for t in tags[:50]
    ]
    if len(tags) > 50:
        result["tags_truncated"] = True
    return result


def folder_snapshot(row):
    return {
        k: getattr(row, k)
        for k in ("id", "path", "scan_mode", "thumbnail_enabled", "thumbnail_interval")
    }


def folder_label(row):
    value = (row.path or "").replace("\\", "/").rstrip("/").split("/")[-1]
    return (value if value and not value.endswith(":") else "目录 " + str(row.id))[:500]


def ack(row):
    return schemas.ProposalAckDTO.model_validate(row)


def proposal_dto(row):
    return schemas.ProposalDTO(
        **ack(row).model_dump(),
        session_id=row.session_id,
        targets=json.loads(row.targets_json or "[]"),
        before=json.loads(row.before_json),
        after=json.loads(row.after_json),
        payload_hash=row.normalized_payload_hash,
        result=(
            schemas.ActionResultDTO.model_validate_json(row.result_json)
            if row.result_json
            else None
        ),
    )


def owned(db, user_id, proposal_id):
    require_admin(db, user_id)
    row = db.execute(
        select(AssistantProposal)
        .where(
            AssistantProposal.id == uuid_text(proposal_id),
            AssistantProposal.user_id == user_id,
        )
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "assistant_not_found")
    return row


def get_owned_proposal(db, user_id, proposal_id):
    return proposal_dto(owned(db, user_id, proposal_id))


def create_proposal(db, principal, context, kind, payload):
    if kind not in ("media_update", "scan"):
        from .operation_registry import create_operation_proposal
        return create_operation_proposal(db,principal,context,kind,payload)
    target_id, normalized = normalize(kind, payload)
    digest = input_hash(
        {
            "version": 1,
            "user_id": principal.user_id,
            "session_id": str(context.session_id),
            "run_id": str(context.run_id),
            "kind": kind,
            "target_id": target_id,
            "payload": normalized,
        }
    )
    with write_transaction(db) as local:
        require_tool_context(local, principal, context)
        existing = local.execute(
            select(AssistantProposal).where(
                AssistantProposal.run_id == str(context.run_id),
                AssistantProposal.kind == kind,
                AssistantProposal.normalized_payload_hash == digest,
            )
        ).scalar_one_or_none()
        if existing:
            if existing.state == "pending" and existing.expires_at <= utcnow():
                existing.state = "expired"
                existing.consumed_at = utcnow()
            return ack(existing)
        if kind == "media_update":
            row = (
                visible(local)
                .options(selectinload(models.Media.tags))
                .filter(models.Media.id == target_id)
                .first()
            )
            if row is None:
                raise HTTPException(404, "assistant_media_not_found")
            patch = normalized["patch"]
            before = media_snapshot(row, patch)
            after = {**before, "tags": [dict(t) for t in before["tags"]]}
            remove = set(patch.get("remove_tag_ids", []))
            added = {(t["name"], t["namespace"]) for t in patch.get("add_tags", [])}
            if not remove.issubset({t["id"] for t in before["tags"]}) or any(
                (t["name"], t["namespace"]) in added and t["id"] in remove
                for t in before["tags"]
            ):
                raise HTTPException(422, "assistant_conflicting_tags")
            for key in ("rating", "favorite", "source_url", "title", "artist", "view_status"):
                if key in patch:
                    after[key] = patch[key]
            after["tags"] = [t for t in after["tags"] if t["id"] not in remove]
            old = {(t["name"], t["namespace"]) for t in after["tags"]}
            after["tags"].extend(
                {"id": None, "name": name, "namespace": namespace}
                for name, namespace in sorted(added - old)
            )
            if before == after:
                raise HTTPException(422, "assistant_empty_change")
            fingerprint = input_hash(before)
            display_before = public_snapshot(before)
            display_after = public_snapshot(after)
            # The relationship preview is capped at 50. Explicit bounded changes
            # remain fully reviewable even when an edited tag falls beyond it.
            initial_tags = {(t["name"], t["namespace"]) for t in before["tags"]}
            display_after["add_tags"] = [
                t
                for t in patch.get("add_tags", [])
                if (t["name"], t["namespace"]) not in initial_tags
            ]
            display_after["remove_tags"] = [
                {
                    "id": t["id"],
                    "name": t["name"][:80],
                    "namespace": t["namespace"][:40],
                }
                for t in before["tags"]
                if t["id"] in remove
            ]
            label = (row.title or "")[:500]
        else:
            row = local.get(models.Folder, target_id)
            if row is None:
                raise HTTPException(404, "assistant_folder_not_found")
            fingerprint = input_hash(folder_snapshot(row))
            label = folder_label(row)
            display_before = {
                "folder_id": row.id,
                "display_name": label,
                "scan_mode": row.scan_mode or "auto",
            }
            display_after = {
                **display_before,
                "action": "scan",
                "notice": "扫描可能逐项更新媒体记录，失败时可能已有部分结果，不自动重放。",
            }
        now = utcnow()
        proposal = AssistantProposal(
            id=str(uuid4()),
            user_id=principal.user_id,
            session_id=str(context.session_id),
            run_id=str(context.run_id),
            kind=kind,
            target_id=target_id,
            target_label=label,
            normalized_payload_hash=digest,
            payload_json=canonical_json(normalized),
            before_json=canonical_json(display_before),
            after_json=canonical_json(display_after),
            target_fingerprint=fingerprint,
            state="pending",
            created_at=now,
            expires_at=now + timedelta(seconds=300),
        )
        local.add(proposal)
        local.flush()
        return ack(proposal)


def reject_proposal(db, user_id, proposal_id):
    with write_transaction(db) as local:
        row = owned(local, user_id, proposal_id)
        if row.state == "pending":
            row.state = "expired" if row.expires_at <= utcnow() else "rejected"
            row.consumed_at = utcnow()
        elif row.state not in ("rejected", "expired"):
            raise HTTPException(409, "assistant_proposal_consumed")
        return proposal_dto(row)
