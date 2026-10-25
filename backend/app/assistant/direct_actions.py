"""Chat-authorized routine actions using the existing immutable audit pipeline."""
from . import actions, proposals, schemas
from .identity import require_tool_context


def manage_library(db, principal, context, args):
    require_tool_context(db, principal, context)
    operation = schemas.ManageLibraryArgs.model_validate(args).operation
    payload = operation.model_dump(mode="json", exclude_unset=True)
    kind = payload.pop("kind")
    # The discriminated schema deliberately excludes deletion, merge and moves.
    proposal = proposals.create_proposal(db, principal, context, kind, payload)
    snapshot = proposals.get_owned_proposal(db, principal.user_id, proposal.id)
    require_tool_context(db, principal, context)
    return actions.confirm_proposal(db, principal.user_id, proposal.id, snapshot.payload_hash)
