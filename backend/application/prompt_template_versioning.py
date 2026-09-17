"""Shared PromptTemplate version-bump helper (REQ-L2-PT-001).

Both the MCP ``prompt_template`` tool group (``mcp_server/tools/
prompt_template.py``, Task 3) and the REST ``SettingsService`` (Task 4) need
to perform the exact same operation: "deactivate whatever row is currently
active for a (tenant, workspace_id, name) scope, then create the next
version and mark it active." Extracting it here means that transaction
logic exists in exactly one place instead of being copied a second (or
third) time.

``PromptTemplate.save()`` already enforces "at most one active row per
scope" via its own Tenant-row mutex (see that method's docstring) — this
helper does not duplicate that locking, it only sequences the deactivate +
create pair inside one transaction so a crash between the two steps can
never leave the scope with zero active rows.
"""
from __future__ import annotations

from uuid import UUID

from persistence.models import PromptTemplate
from persistence.transactions import atomic_transaction


def get_active_template(
    *, tenant_id: UUID, name: str, workspace_id: UUID | None = None
) -> PromptTemplate | None:
    """Return the active row for one exact scope, or ``None``.

    Note the scope semantics: ``workspace_id=None`` selects the *tenant-wide*
    scope, because ``None`` is the real column value for tenant-wide rows. It
    does **not** mean "any workspace" — use :func:`list_active_templates` for
    an unfiltered listing.

    Args:
        tenant_id:    Owning tenant.
        name:         Template name (the "slot").
        workspace_id: Workspace scope, or ``None`` for the tenant-wide row.

    Returns:
        The active ``PromptTemplate`` for that scope, or ``None`` if there is
        none. At most one row per scope can be active (enforced by
        ``PromptTemplate.save()``).
    """
    return PromptTemplate.objects.filter(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        name=name,
        is_active=True,
    ).first()


def list_active_templates(
    *, tenant_id: UUID, workspace_id: UUID | None = None
) -> list[PromptTemplate]:
    """Return the tenant's active templates, ordered by name.

    Unlike :func:`get_active_template`, ``workspace_id=None`` here means *no
    workspace filter at all*: the result then contains both the tenant-wide
    rows and every workspace-scoped row. This mirrors the pre-existing
    ``prompt_template.list`` behaviour exactly.

    Args:
        tenant_id:    Owning tenant.
        workspace_id: Restrict to one workspace, or ``None`` for no filter.

    Returns:
        Active ``PromptTemplate`` rows sorted by ``name``.
    """
    qs = PromptTemplate.objects.filter(tenant_id=tenant_id, is_active=True)
    if workspace_id is not None:
        qs = qs.filter(workspace_id=workspace_id)
    return list(qs.order_by("name"))


@atomic_transaction
def deactivate_scope(
    *, tenant_id: UUID, name: str, workspace_id: UUID | None = None
) -> bool:
    """Deactivate the active row for one exact scope, if there is one.

    This is how an *override* is removed: rows are never deleted (the version
    history is audit material, see :class:`~persistence.models.PromptTemplate`),
    the scope is simply left with zero active rows so the resolution chain
    (workspace -> tenant-global -> factory default) falls through to the next
    level. A scope with no active row is a normal, pre-existing state — it is
    what every scope looks like before anyone customises it.

    Args:
        tenant_id:    Owning tenant.
        name:         Template name (the "slot").
        workspace_id: Workspace scope, or ``None`` for the tenant-wide row.

    Returns:
        ``True`` if an active row was deactivated, ``False`` if the scope had
        none (already at its inherited value — a no-op, not an error).
    """
    prior = get_active_template(
        tenant_id=tenant_id, name=name, workspace_id=workspace_id
    )
    if prior is None:
        return False
    prior.is_active = False
    prior.save(update_fields=["is_active"])
    return True


@atomic_transaction
def publish_new_version(
    *, tenant_id: UUID, name: str, content: str, workspace_id: UUID | None = None
) -> PromptTemplate:
    """Deactivate the current active row for the scope (if any); create version N+1."""
    prior = get_active_template(
        tenant_id=tenant_id, name=name, workspace_id=workspace_id
    )

    next_version = (prior.version + 1) if prior is not None else 1
    if prior is not None:
        prior.is_active = False
        prior.save(update_fields=["is_active"])

    new_row = PromptTemplate(
        tenant_id=tenant_id,
        name=name,
        content=content,
        version=next_version,
        is_active=True,
        workspace_id=workspace_id,
    )
    new_row.save()
    return new_row


__all__ = [
    "deactivate_scope",
    "get_active_template",
    "list_active_templates",
    "publish_new_version",
]
