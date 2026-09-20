"""Local readable ``uid`` allocation (issue #932).

Eight artifact models carry a local, human-readable identifier (``REQ-001``,
``NEED-014``, …). Before this module nothing generated it: the field was
documented as auto-generated on some models and as the external ReqIF key on
others, and it was read-only — so 0 % of artifacts had one and the UI fell back
to the UUID short hash. ReqIF's own identity now lives on the Artifact's
``reqif_*`` fields (#1003); this module owns the *local* identifier only.

Allocation is atomic and non-recycling: a :class:`persistence.models.UidSequence`
row per ``(workspace, item_type)`` is locked with ``SELECT … FOR UPDATE``, then
incremented and formatted as ``{PREFIX}-{NNN}``. A counter (not ``MAX(uid)+1``)
is what guarantees a deleted artifact's number is never handed out again.
"""
from __future__ import annotations

import logging
from typing import Dict, Optional
from uuid import UUID

from django.db import IntegrityError, transaction

logger = logging.getLogger(__name__)

#: item_type -> local uid prefix. Mirrors the artifact vocabulary the models and
#: seeds already use.
UID_PREFIXES: Dict[str, str] = {
    "StakeholderNeed": "NEED",
    "Requirement": "REQ",
    "ArchitectureElement": "ARCH",
    "TestCase": "TC",
    "TestRun": "RUN",
    "Adr": "ADR",
    "Risk": "RISK",
    "Issue": "ISSUE",
}


def uid_prefix(item_type: str) -> str:
    """Return the local-uid prefix for *item_type* (fallback: upper-cased)."""
    return UID_PREFIXES.get(item_type) or item_type[:6].upper() or "ITEM"


def generate_local_uid(item_type: str, workspace_id: UUID | str) -> Optional[str]:
    """Allocate the next local ``uid`` for *(workspace, item_type)*.

    Opens its own ``transaction.atomic()`` so the locked read/increment cannot
    be left half-applied even when the caller has no transaction of its own.
    On the first allocation for a workspace/item type two concurrent callers
    may race to create the sequence row; the loser retries once against the
    winner's row (the unique constraint is the arbiter), so the call itself
    never surfaces an ``IntegrityError``.

    Returns:
        ``{PREFIX}-{NNN}`` — e.g. ``REQ-001``, ``NEED-014`` — or ``None`` when
        the workspace row cannot be read (only reachable from a mocked-ORM unit
        test; every real create path has already validated the workspace, so the
        caller's ``uid or generate_local_uid(...)`` then keeps ``uid`` NULL
        exactly as before this feature).
    """
    from persistence.models import UidSequence, Workspace

    # The sequence row is tenant-scoped. Take the tenant from the *workspace*
    # row (authoritative) rather than the ambient TenantContext, which a test or
    # a cross-tenant maintenance path may leave pointed elsewhere.
    tenant_id = (
        Workspace.unscoped.filter(id=workspace_id)
        .values_list("tenant_id", flat=True)
        .first()
    )
    if tenant_id is None:
        logger.warning(
            "generate_local_uid: workspace %s not found — leaving uid unset.",
            workspace_id,
        )
        return None

    prefix = uid_prefix(item_type)
    last_attempt = 1
    for attempt in range(last_attempt + 1):
        try:
            with transaction.atomic():
                sequence, _created = UidSequence.objects.select_for_update().get_or_create(
                    workspace_id=workspace_id,
                    item_type=item_type,
                    defaults={"tenant_id": tenant_id},
                )
                sequence.last_value += 1
                sequence.save(update_fields=["last_value"])
                return f"{prefix}-{sequence.last_value:03d}"
        except IntegrityError:
            # Only reachable when two callers create the row at once; the
            # second pass finds the winner's row and allocates normally.
            if attempt >= last_attempt:
                raise
            logger.debug(
                "generate_local_uid: sequence row race for ws=%s/%s — retrying",
                workspace_id,
                item_type,
            )
    raise AssertionError("unreachable")  # pragma: no cover


__all__ = ["UID_PREFIXES", "generate_local_uid", "uid_prefix"]
