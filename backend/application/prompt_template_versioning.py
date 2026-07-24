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


@atomic_transaction
def publish_new_version(
    *, tenant_id: UUID, name: str, content: str, workspace_id: UUID | None = None
) -> PromptTemplate:
    """Deactivate the current active row for the scope (if any); create version N+1."""
    prior = PromptTemplate.objects.filter(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        name=name,
        is_active=True,
    ).first()

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


__all__ = ["publish_new_version"]
