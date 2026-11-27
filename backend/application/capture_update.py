"""Update-proposal support for ``suggestion.capture`` (ADR-032, plan P3).

"Anpassen, erweitern, korrigieren" must not become a second write path. This
module is the thin bridge between a capture suggestion and the **existing**
shared update seam
:func:`application.artifact_fields_update.update_artifact_fields` — the same
function the bulk-edit and inline-edit surfaces use. Everything that makes an
update correct therefore comes for free and cannot drift:

* the type's explicit content allowlist (``UpdateAdapter.writable_fields``, never
  signature introspection),
* the gateway fields (``owner``/``reporter``/``priority``/carrier fields and
  ``custom_fields``) written through :class:`ArtifactAttributeGateway`,
* the workflow/structural guard (``NEVER_BULK_WRITABLE``, ``WORKFLOW_OWNED_FALLBACK``),
  the ``freeze_on_enter`` gate and the item-level write right,
* the optimistic lock via ``expected_version``,
* the audit entry and the version bump.

The only thing added here is the capture vocabulary: a suggestion stores the
**entity** id (what ``*.get`` returns), while the seam addresses the backing
``Artifact``; and a stale ``base_version`` is surfaced as
:class:`CaptureConflictError` (409 ``CONFLICT``) so the inbox can say "re-read
and retry" instead of leaking the seam's internal error type.

Goal is deliberately absent: the shared seam has no Goal adapter because Goals
are immutable rows per version (an "update" appends a version), and inventing a
parallel path here would bypass exactly the guards this module exists to reuse.
Goal update proposals are therefore not offered in v1 (see ADR-032).
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from application.artifact_update_adapters import (
    ARTIFACT_UPDATE_ADAPTERS,
    GATEWAY_FIELDS,
)
from application.base import NotFoundError, OptimisticLockError, ValidationError

__all__ = [
    "CaptureConflictError",
    "apply_update",
    "supports_update",
    "update_allowlist",
]


class CaptureConflictError(ValidationError):
    """An update suggestion no longer applies to the current artifact state.

    Raised when the proposal's ``base_version`` is stale (**409 CONFLICT**) or
    the target vanished. The inbox keeps the suggestion ``open`` — the human can
    inspect the current artifact and re-capture or reject — and nothing is
    overwritten (plan P3 gate: "überschreibt keinen fremden Stand").

    A ``ValidationError`` subclass so every ``except ValidationError`` caller
    keeps working; REST/MCP map this exact type to ``CONFLICT``/409 because the
    shared maps look exceptions up by type.
    """

    error_code = "CONFLICT"
    http_status = 409

    def __init__(
        self,
        message: str,
        *,
        expected_version: int | None = None,
        current_version: int | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details = {
            "base_version": expected_version,
            "current_version": current_version,
        }


def supports_update(item_type: str) -> bool:
    """Return whether the shared update seam can write *item_type*."""
    return item_type in ARTIFACT_UPDATE_ADAPTERS


def update_allowlist(item_type: str) -> frozenset[str]:
    """Return the names an update proposal may carry for *item_type*.

    The union of the type's content allowlist and the gateway fields, i.e. the
    same set :func:`artifact_fields_update.update_artifact_fields` divides into
    "typed service" and "gateway" writes. An unknown type has no allowlist.
    """
    adapter = ARTIFACT_UPDATE_ADAPTERS.get(item_type)
    if adapter is None:
        return frozenset()
    return frozenset(adapter.writable_fields) | GATEWAY_FIELDS


def apply_update(
    ctx: Any,
    *,
    item_type: str,
    entity_id: UUID,
    fields: dict[str, Any],
    base_version: int | None,
    change_reason: str | None = None,
):
    """Apply an accepted update proposal through the shared seam.

    Args:
        ctx: The deciding human's context.
        item_type: Artifact type the proposal targeted.
        entity_id: The **entity** id stored on the suggestion (what
            ``requirement.get``/``adr.read`` return).
        fields: Validated proposal fields (content + gateway names).
        base_version: The version the proposal was derived from; the seam's
            ``expected_version``, so a stale value is refused, not applied.
        change_reason: Forwarded to the typed service where it accepts one.

    Returns:
        The seam's ``FieldUpdateResult`` (``artifact_id``, ``entity_id``,
        ``version``).

    Raises:
        CaptureConflictError: *base_version* is stale, or the target vanished.
        ValidationError: a field the seam refuses (structural, workflow-owned,
            not in the allowlist), a frozen artifact, or no adapter.
    """
    from application.artifact_fields_update import update_artifact_fields
    from persistence.artifact_backing import model_for

    if not supports_update(item_type):
        raise ValidationError(
            f"Artifact type {item_type!r} cannot be updated through a capture "
            "proposal."
        )

    model = model_for(item_type)
    artifact_id = (
        model.objects.filter(id=entity_id)
        .values_list("artifact_id", flat=True)
        .first()
    )
    if artifact_id is None:
        raise CaptureConflictError(
            "The artifact this suggestion targets no longer exists; nothing was "
            "written.",
            expected_version=base_version,
            current_version=None,
        )

    try:
        return update_artifact_fields(
            ctx,
            item_type,
            artifact_id,
            fields,
            expected_version=base_version,
            change_reason=change_reason,
        )
    except OptimisticLockError as exc:
        raise CaptureConflictError(
            "This update suggestion is based on an older version of the "
            "artifact; nothing was overwritten.",
            expected_version=base_version,
            current_version=None,
        ) from exc
    except NotFoundError as exc:
        raise CaptureConflictError(
            "The artifact this suggestion targets is no longer available; "
            "nothing was written.",
            expected_version=base_version,
            current_version=None,
        ) from exc
