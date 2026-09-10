"""Seeding logic shared by the backfill migration and its tests.

Lives outside the numbered migration module (the ``_`` prefix keeps Django's
migration loader from picking it up as a migration) so the behaviour is
testable without replaying migration state. ``0003_seed_builtin_link_types``
is a thin wrapper around :func:`seed_tenant`.

The workspace half deliberately delegates to
``link_types.workspace_store.provision_workspace_link_types`` instead of
re-implementing it: that function is already the idempotent seed used by
``application.workspace_provisioning`` for newly created workspaces, so a
backfilled workspace and a freshly provisioned one are guaranteed to end up
with byte-identical rows.
"""
from __future__ import annotations

from typing import Iterable, List, Tuple
from uuid import UUID


def seed_tenant(
    tenant_id: UUID | str, workspace_ids: Iterable[UUID | str]
) -> Tuple[int, int]:
    """Create the missing global and workspace rows for one tenant.

    Both writes are ``get_or_create``: an existing row — customized or not —
    is never overwritten, which is what makes the migration safe to re-run
    and safe to apply to a database where Task 7's provisioning has already
    seeded some workspaces.

    The caller is responsible for arming ``app.current_tenant`` for
    *tenant_id* before calling: both ``lt_*`` tables carry FORCE ROW LEVEL
    SECURITY, so an unarmed non-``BYPASSRLS`` connection would silently write
    and read nothing.

    Args:
        tenant_id: Tenant to seed.
        workspace_ids: Every workspace of that tenant.

    Returns:
        ``(globals_created, workspace_rows_created)``. Both are 0 on a repeat
        run.
    """
    from link_types.builtin import BUILTIN_LINK_TYPES, builtin_definition
    from link_types.models import GlobalLinkTypeDefinition
    from link_types.workspace_store import provision_workspace_link_types

    globals_created = 0
    for key in sorted(BUILTIN_LINK_TYPES):
        _row, created = GlobalLinkTypeDefinition.unscoped.get_or_create(
            tenant_id=tenant_id,
            key=key,
            defaults={"definition_json": builtin_definition(key), "version": 1},
        )
        globals_created += int(created)

    ids: List[UUID | str] = list(workspace_ids)
    rows_created = sum(
        provision_workspace_link_types(workspace_id=workspace_id, tenant_id=tenant_id)
        for workspace_id in ids
    )
    return globals_created, rows_created


__all__ = ["seed_tenant"]
