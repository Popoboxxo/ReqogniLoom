"""Dependency-inversion seam for Layer-0 -> Layer-1 soft-delete lookups.

SA-21 (SYSTEMAUDIT_2026-08-27 §4.1 #5): ``persistence/models.py`` (Layer 0)
used to ``import workflow.services`` (Layer 1) directly from
``ArchitectureElement.annotate_roles``/``get_role`` — the wrong direction in
the layering (persistence/auth_tenancy/presets/audit sit *below*
llm_adapter/traceability/workflow/baseline, per CLAUDE.md's Architektur
section). ``ArchitectureElement`` has no denormalized status mirror column
(see ``workflow.lifecycle_manager``), so its soft-delete state lives only in
``WorkflowItemState`` — the children-visibility check genuinely needs an
answer from the WorkflowEngine.

Rather than have Layer 0 import Layer 1, Layer 0 defines this narrow
provider seam; ``WorkflowConfig.ready()`` (Layer 1, ``workflow/apps.py``)
registers the real implementation at Django startup — the same
register-on-``ready()`` pattern ``audit.apps.AuditConfig`` already uses for
``AuditLogWriter``/``DomainEventBus``. ``persistence`` never imports
``workflow`` at module load time; it only calls whatever was registered.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Optional
from uuid import UUID

if TYPE_CHECKING:
    from django.db.models import QuerySet

#: Signature matches ``workflow.services.outdated_item_ids`` exactly —
#: ``item_type`` positional, ``tenant_id`` keyword-only, returning a lazy
#: QuerySet of item ids so callers can embed it as an ``id__in=`` subquery
#: without materialising it (see that function's docstring).
OutdatedItemIdsProvider = Callable[..., "QuerySet[UUID]"]

_provider: Optional[OutdatedItemIdsProvider] = None


def register_outdated_item_ids_provider(provider: OutdatedItemIdsProvider) -> None:
    """Register the Layer-1 implementation. Called once from
    ``WorkflowConfig.ready()`` at Django startup."""
    global _provider
    _provider = provider


def outdated_item_ids(
    item_type: str, *, tenant_id: UUID | str | None = None
) -> "QuerySet[UUID]":
    """Return the outdated-item-id queryset for *item_type* (Layer-0 facade).

    Delegates to whatever ``workflow.services.outdated_item_ids`` registered
    via :func:`register_outdated_item_ids_provider`. Fails fast with a clear
    message if called before Django app startup completed (``workflow`` is a
    core, always-installed app — this should be unreachable in practice,
    mirroring how ``TenantContextNotSetError`` fails fast on a missing
    thread-local rather than silently degrading).

    Raises:
        RuntimeError: If no provider has been registered yet.
    """
    if _provider is None:
        raise RuntimeError(
            "No outdated-item-ids provider registered — WorkflowConfig.ready() "
            "must run before any Layer-0 soft-delete-aware query. Is 'workflow' "
            "in INSTALLED_APPS?"
        )
    return _provider(item_type, tenant_id=tenant_id)


__all__ = [
    "OutdatedItemIdsProvider",
    "register_outdated_item_ids_provider",
    "outdated_item_ids",
]
