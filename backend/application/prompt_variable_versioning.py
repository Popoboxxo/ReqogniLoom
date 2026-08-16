"""Shared PromptVariable version-bump helpers (spec §3.1).

Structural twin of ``application/prompt_template_versioning.py``: the REST
views, the MCP tool group and the resolver all need the same "deactivate
whatever row is active for a (tenant, workspace_id, name) scope, then create
the next version and mark it active" operation, so it lives in exactly one
place.

``PromptVariable.save()`` already enforces "at most one active row per scope"
via its own Tenant-row mutex — these helpers only sequence the deactivate +
create pair inside one transaction so a crash between the two steps can never
leave the scope with zero active rows.
"""
from __future__ import annotations

from uuid import UUID

from persistence.models import PromptVariable
from persistence.transactions import atomic_transaction


def get_active_variable(
    *, tenant_id: UUID, name: str, workspace_id: UUID | None = None
) -> PromptVariable | None:
    """Return the active row for one exact scope, or ``None``.

    ``workspace_id=None`` selects the *tenant-wide* scope (``None`` is the
    real column value there); it does not mean "any workspace" — use
    :func:`list_active_variables` for an unfiltered listing.
    """
    return PromptVariable.objects.filter(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        name=name,
        is_active=True,
    ).first()


def list_active_variables(
    *, tenant_id: UUID, workspace_id: UUID | None = None
) -> list[PromptVariable]:
    """Return the tenant's active variable rows, ordered by name.

    Unlike :func:`get_active_variable`, ``workspace_id=None`` here means *no
    workspace filter at all*: the result then contains both tenant-wide rows
    and every workspace-scoped row.
    """
    qs = PromptVariable.objects.filter(tenant_id=tenant_id, is_active=True)
    if workspace_id is not None:
        qs = qs.filter(workspace_id=workspace_id)
    return list(qs.order_by("name"))


@atomic_transaction
def deactivate_variable_scope(
    *, tenant_id: UUID, name: str, workspace_id: UUID | None = None
) -> bool:
    """Deactivate the active row for one exact scope, if there is one.

    Rows are never deleted; the scope is simply left with zero active rows so
    the resolution chain (workspace -> tenant -> factory) falls through.

    Returns:
        ``True`` if a row was deactivated, ``False`` if the scope had none.
    """
    prior = get_active_variable(
        tenant_id=tenant_id, name=name, workspace_id=workspace_id
    )
    if prior is None:
        return False
    prior.is_active = False
    prior.save(update_fields=["is_active"])
    return True


@atomic_transaction
def publish_new_variable_version(
    *,
    tenant_id: UUID,
    name: str,
    kind: str,
    var_type: str,
    description: str,
    default_value: str,
    workspace_id: UUID | None = None,
) -> PromptVariable:
    """Deactivate the current active row for the scope (if any); create N+1."""
    prior = get_active_variable(
        tenant_id=tenant_id, name=name, workspace_id=workspace_id
    )

    next_version = (prior.version + 1) if prior is not None else 1
    if prior is not None:
        prior.is_active = False
        prior.save(update_fields=["is_active"])

    new_row = PromptVariable(
        tenant_id=tenant_id,
        name=name,
        kind=kind,
        var_type=var_type,
        description=description,
        default_value=default_value,
        version=next_version,
        is_active=True,
        workspace_id=workspace_id,
    )
    new_row.save()
    return new_row


__all__ = [
    "deactivate_variable_scope",
    "get_active_variable",
    "list_active_variables",
    "publish_new_variable_version",
]
