"""The artifact update seam ``update_artifact_fields`` (Tabellenansicht S1, Task 1.2).

*A single write path for "change these fields of this artifact".* It composes
exactly what a type's single ``PATCH`` assembles in Layer 3 — workflow/structural
guard, attribute-definition validation, the item-level write right, the
optimistic lock, the gateway write — so the next caller (bulk edit, inline cell
edit, the Dokumentensicht save) does not re-assemble it and cannot drift from the
single PATCH.

Why a seam and not another endpoint
-----------------------------------
The plan (spec §2) forbids bulk- and inline-write paths from writing
workflow-owned or structural fields, and pins the per-artifact item right on
*write* (the single PATCH deliberately has no such check yet, plan O10). Both
rules are one function, called once per artifact, so a second transport cannot
forget them.

Contract
--------
``update_artifact_fields(ctx, item_type, artifact_id, fields, expected_version,
change_reason=...) -> FieldUpdateResult``

Order of work (all inside one transaction):

1. tenant context, RBAC write check,
2. the tenant-scoped ``Artifact`` (missing/foreign → ``NotFoundError``; soft
   deleted → ``ValidationError`` "outdated", never resurrected),
3. the item-level write right (:meth:`ServiceBase._assert_item_write_permission`:
   an explicit ``read`` rule → 403, ``none`` → 404 with the missing-id wording),
4. the resolved attribute definition (absent → the guard falls back to
   :data:`application.artifact_update_adapters.WORKFLOW_OWNED_FALLBACK`),
5. the workflow/structural guard over **every** name in the payload,
6. the freeze gate (``artifact_freeze.is_frozen`` — content fields included,
   plan O5),
7. the gateway validation (definition + actor resolution),
8. the typed ``update_X`` (always called, also with no entity fields, so a
   gateway-only write still bumps the version — plan O11),
9. the gateway write for ``owner``/``reporter``/``priority``/carrier fields and
   ``custom_fields``.

Failure modes keep the transport vocabulary: ``ValidationError`` → 400,
``PermissionDeniedError`` → 403, ``NotFoundError`` → 404,
``WorkflowFrozenError`` → 409 ``WORKFLOW_FROZEN`` (its ``details.state`` names
the state), ``OptimisticLockError`` → 409.
"""
from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from django.db import transaction
from django.db.models import F

from application.artifact_attribute_gateway import (
    ArtifactAttributeGateway,
    AttributeValues,
)
from application.artifact_update_adapters import (
    adapter_for,
    assert_no_forbidden_fields,
    classify_fields,
)
from application.base import (
    NotFoundError,
    ServiceBase,
    ValidationError,
    WorkflowFrozenError,
)
from auth_tenancy.context import AuthContext
from persistence.artifact_backing import model_for
from persistence.models import Artifact, LifecycleStatus

logger = logging.getLogger(__name__)

__all__ = ["ArtifactFrozenError", "FieldUpdateResult", "update_artifact_fields"]

#: Public alias of the artifact freeze error. ``WorkflowFrozenError`` is the
#: type the transports already map to **409 WORKFLOW_FROZEN** (registered in
#: ``rest_api.views._EXC_TO_HTTP``/``_ERROR_CODES``), and it carries the state
#: name in ``details["state"]``. The plan calls the type ``ArtifactFrozenError``;
#: aliasing it keeps one class instead of two 409 types with identical meaning.
ArtifactFrozenError = WorkflowFrozenError


@dataclass(frozen=True)
class FieldUpdateResult:
    """Outcome of one seam write."""

    artifact_id: UUID
    entity_id: UUID
    item_type: str
    version: int


def _resolved_attributes(
    ctx: AuthContext, item_type: str, workspace_id: UUID
) -> list[dict[str, Any]]:
    """Return the definition's attributes, or ``[]`` when none exists.

    An empty list is not "nothing may be written": :func:`assert_no_forbidden_fields`
    still rejects the structural and workflow-owned names, which is exactly what
    plan O11's defense-in-depth asks for.
    """
    from application.attribute_definition_service import AttributeDefinitionService
    from attribute_definitions.global_definition_store import AttributeDefinitionNotFound
    from attribute_definitions.schema import AttributeSchemaError

    try:
        definition = AttributeDefinitionService().resolve(ctx, item_type, workspace_id)
    except (AttributeDefinitionNotFound, AttributeSchemaError):
        return []
    return list(definition.get("attributes") or [])


def _assert_not_frozen(artifact: Artifact) -> None:
    """Raise ``WorkflowFrozenError`` when a freeze state holds *artifact*."""
    from application.artifact_freeze import is_frozen

    info = is_frozen(artifact)
    if info is None:
        return
    raise WorkflowFrozenError(
        f"Artifact is frozen in state '{info.state_name}' and cannot be "
        "changed",
        state_name=info.state_name,
    )


def _assert_gateway_validation(
    ctx: AuthContext,
    item_type: str,
    workspace_id: UUID,
    payload: Mapping[str, Any],
) -> None:
    """Run the gateway's definition and actor validation before any write."""
    gateway = ArtifactAttributeGateway()
    from attribute_definitions.field_validation import FieldValidationError
    from attribute_definitions.global_definition_store import AttributeDefinitionNotFound

    try:
        gateway.validate(
            ctx, item_type, workspace_id, dict(payload), {"__exists__": True}
        )
        gateway.validate_actor_system_fields(ctx, item_type, workspace_id, dict(payload))
    except AttributeDefinitionNotFound:
        # The bootstrap has not run for this workspace's preset. Same graceful
        # degradation as the single PATCH's ``_validate_attribute_definition``:
        # an unconfigured deployment stays writable.
        logger.info(
            "No attribute definition for %s in workspace %s; skipping the "
            "gateway validation",
            item_type,
            workspace_id,
        )
        return
    except FieldValidationError as exc:
        # Same message shape the PATCH validator produces, so a client sees one
        # vocabulary regardless of which transport rejected the payload.
        details = getattr(exc, "errors", None) or getattr(exc, "details", None)
        if isinstance(details, dict):
            message = "; ".join(
                f"{field}: {messages}" for field, messages in details.items()
            )
            raise ValidationError(message) from exc
        raise ValidationError(str(exc)) from exc


def update_artifact_fields(
    ctx: AuthContext,
    item_type: str,
    artifact_id: UUID,
    fields: Mapping[str, Any],
    expected_version: int | None = None,
    *,
    change_reason: str | None = None,
) -> FieldUpdateResult:
    """Write *fields* on one artifact through the shared update path.

    Args:
        ctx: Authenticated caller (roles plus the item-level rule decide).
        item_type: Must equal the artifact's ``artifact_type``.
        artifact_id: Backing ``pl_artifact`` id (what a table row returns).
        fields: Content, gateway and ``custom_fields`` names only.
        expected_version: Last-seen entity ``version`` (``None`` skips the lock).
        change_reason: Forwarded to the typed service where it accepts one.

    Returns:
        The written artifact/entity ids and the new entity ``version``.

    Raises:
        ValidationError: unknown/forbidden field, definition violation,
            ``item_type`` mismatch, soft-deleted artifact.
        NotFoundError: no such artifact under the caller's tenant, no typed row,
            or an explicit item-level ``none`` rule.
        PermissionDeniedError: no write role, or an item-level ``read`` rule.
        WorkflowFrozenError: a freeze state holds the artifact.
        OptimisticLockError: ``expected_version`` is stale.
    """
    ServiceBase._set_tenant_context(ctx)
    ServiceBase._assert_write_permission(ctx)

    artifact = Artifact.objects.select_related(None).filter(id=artifact_id).first()
    if artifact is None:
        raise NotFoundError(f"Artifact {artifact_id} not found")
    if artifact.artifact_type != item_type:
        raise ValidationError(
            f"Artifact {artifact_id} is a {artifact.artifact_type}, not a "
            f"{item_type}"
        )
    if artifact.lifecycle_status == LifecycleStatus.OUTDATED:
        raise ValidationError(
            f"Artifact {artifact_id} is outdated and cannot be changed"
        )

    workspace_id = artifact.workspace_id
    ServiceBase._assert_item_write_permission(
        ctx, artifact.id, workspace_id=workspace_id
    )

    attributes = _resolved_attributes(ctx, item_type, workspace_id)
    assert_no_forbidden_fields(attributes, fields)
    entity_fields, gateway_fields = classify_fields(item_type, fields)

    adapter = adapter_for(artifact)
    entity = getattr(artifact, adapter.accessor, None)
    if entity is None:
        raise NotFoundError(f"Artifact {artifact_id} has no {item_type} row")
    entity_id = entity.id
    before_version = entity.version

    _assert_not_frozen(artifact)
    _assert_gateway_validation(
        ctx, item_type, workspace_id, {**entity_fields, **gateway_fields}
    )

    with transaction.atomic():
        # Always call the typed service, also for a gateway-only change: that is
        # what makes a successful write bump the entity version (plan O11), and
        # what makes a replayed ``expected_version`` conflict.
        _, version = adapter.update(
            ctx, entity_id, entity_fields, expected_version, change_reason
        )
        if gateway_fields:
            extended = gateway_fields.get("custom_fields") or {}
            core = {
                name: value
                for name, value in gateway_fields.items()
                if name != "custom_fields"
            }
            if not isinstance(extended, Mapping):
                raise ValidationError("'custom_fields' must be an object")
            from attribute_definitions.global_definition_store import (
                AttributeDefinitionNotFound,
            )

            try:
                ArtifactAttributeGateway().write(
                    ctx,
                    item_type,
                    entity,
                    AttributeValues(core=dict(core), extended=dict(extended)),
                )
            except AttributeDefinitionNotFound:
                # Nothing to validate/write against: the system fields are not
                # visible without a definition (same no-op as the PATCH).
                logger.info(
                    "No attribute definition for %s in workspace %s; skipping "
                    "the gateway write",
                    item_type,
                    workspace_id,
                )
            if version == before_version:
                # The type's service gated the bump on a content change; a
                # gateway-only write is a write too, so bump it here.
                model_for(item_type).objects.filter(pk=entity_id).update(
                    version=F("version") + 1
                )
                version = before_version + 1

    return FieldUpdateResult(
        artifact_id=artifact.id,
        entity_id=entity_id,
        item_type=item_type,
        version=version,
    )

