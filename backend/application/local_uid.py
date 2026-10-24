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
from typing import Any
from uuid import UUID

from django.db import IntegrityError, models, transaction

logger = logging.getLogger(__name__)

#: item_type -> local uid prefix. Mirrors the artifact vocabulary the models and
#: seeds already use.
UID_PREFIXES: dict[str, str] = {
    "StakeholderNeed": "NEED",
    "Requirement": "REQ",
    "ArchitectureElement": "ARCH",
    "TestCase": "TC",
    "TestRun": "RUN",
    "Adr": "ADR",
    "Risk": "RISK",
    "Issue": "ISSUE",
}

#: Model labels that carry a local readable ``uid`` (issue #932, G1.1).
#:
#: This tuple and :data:`UID_PREFIXES` are the *only* two registration points for
#: a new uid-carrying model (Plan G G1.1 extension contract). Adding a model here
#: without a prefix, or a prefix without a model, is caught by
#: ``application/tests/test_local_uid_all_paths.py::test_uid_models_and_prefixes_in_sync``.
UID_MODELS: tuple[str, ...] = (
    "persistence.Requirement",
    "persistence.StakeholderNeed",
    "persistence.ArchitectureElement",
    "persistence.TestCase",
    "persistence.TestRun",
    "persistence.Adr",
    "persistence.Risk",
    "persistence.Issue",
)


def uid_prefix(item_type: str) -> str:
    """Return the local-uid prefix for *item_type* (fallback: upper-cased)."""
    return UID_PREFIXES.get(item_type) or item_type[:6].upper() or "ITEM"


def generate_local_uid(item_type: str, workspace_id: UUID | str) -> str | None:
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


def _has_field(model: type[models.Model], name: str) -> bool:
    """True when *model* declares a concrete field called *name*."""
    return any(field.name == name for field in model._meta.get_fields())


def _artifact_workspace_id(artifact_id: Any) -> UUID | None:
    """Resolve the workspace of a backing Artifact without a tenant context.

    ``Artifact.unscoped`` is deliberate: the receiver also runs on paths that
    have no request-scoped :class:`~persistence.tenancy.TenantContext` (seeds,
    management commands, data migrations). The lookup is keyed on the primary
    key, so it cannot cross a tenant boundary.
    """
    from persistence.models import Artifact

    return (
        Artifact.unscoped.filter(id=artifact_id)
        .values_list("workspace_id", flat=True)
        .first()
    )


def _resolve_workspace_id(instance: models.Model) -> UUID | None:
    """Return the workspace a uid-carrying *instance* belongs to, if any.

    Two carriers exist in the current model set: the denormalized ``workspace``
    FK (Requirement, TestRun, and — since G1.3 — TestCase/ArchitectureElement/
    StakeholderNeed) and a plain ``workspace_id`` UUID column (Adr/Risk/Issue).
    Everything else derives it from the backing Artifact.
    """
    model = type(instance)
    if _has_field(model, "workspace") or _has_field(model, "workspace_id"):
        workspace_id = getattr(instance, "workspace_id", None)
        if workspace_id:
            return workspace_id

    artifact_id = getattr(instance, "artifact_id", None)
    if artifact_id:
        return _artifact_workspace_id(artifact_id)
    return None


def assign_local_uid(
    sender: type[models.Model],
    instance: models.Model,
    raw: bool = False,
    **kwargs: Any,
) -> None:
    """``pre_save`` receiver: allocate ``uid`` and the denormalized workspace FK.

    Root-cause complement to the eight services that call
    :func:`generate_local_uid` explicitly (issue #932, Plan G G1.1): every path
    that writes a model directly — the ReqIF importer, ``seed_toothbrush`` and
    any future writer — now gets a local identifier too. An explicit ``uid``
    set by the caller always wins; allocation only happens on INSERT
    (``_state.adding``) and never for fixture loading (``raw=True``).

    The denormalized workspace FK is filled from ``artifact.workspace_id`` when
    the model carries it and it is still empty. That is what lets the
    per-workspace uid constraints from G1.3 hold on every create path, not just
    the service paths.
    """
    if raw:
        return

    model = type(instance)
    if _has_field(model, "workspace") or _has_field(model, "workspace_id"):
        if getattr(instance, "workspace_id", None) is None:
            workspace_id = _resolve_workspace_id(instance)
            if workspace_id is not None:
                instance.workspace_id = workspace_id

    if not instance._state.adding:
        return
    if getattr(instance, "uid", None):
        return

    workspace_id = _resolve_workspace_id(instance)
    if workspace_id is None:
        # A mocked-ORM unit test or an artifact-less draft row. Leaving the uid
        # unset mirrors generate_local_uid's own tolerant contract.
        return

    # UidSequence is tenant-scoped, so allocation needs an active tenant. A
    # context-free maintenance path (``Model.unscoped.create`` outside a
    # request) keeps its pre-G1.1 behaviour instead of raising here.
    from persistence.tenancy import TenantContext

    if not TenantContext.is_set():
        return

    instance.uid = generate_local_uid(model.__name__, workspace_id)


def register_uid_signals() -> None:
    """Connect :func:`assign_local_uid` to every model in :data:`UID_MODELS`.

    Called from ``ApplicationConfig.ready()``. ``dispatch_uid`` makes repeated
    calls (Django re-runs ``ready()`` in some test setups) idempotent;
    ``weak=False`` keeps the module-level receiver alive for the process.
    """
    from django.apps import apps as django_apps
    from django.db.models.signals import pre_save

    for label in UID_MODELS:
        model = django_apps.get_model(label)
        pre_save.connect(
            assign_local_uid,
            sender=model,
            dispatch_uid=f"local_uid:{label}",
            weak=False,
        )


__all__ = [
    "UID_MODELS",
    "UID_PREFIXES",
    "assign_local_uid",
    "generate_local_uid",
    "register_uid_signals",
    "uid_prefix",
]
