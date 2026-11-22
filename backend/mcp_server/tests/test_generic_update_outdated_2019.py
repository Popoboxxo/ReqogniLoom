"""#2019 — the generic MCP ``*.update`` path must refuse outdated artifacts.

Before this fix ``GenericCrudToolGroup._handle_update`` called the typed service
directly, so an ADR soft-deleted through ``*.outdate`` could still be updated —
and ``AdrService.update_adr`` happily bumped its version. The outdated guard
lived only in the REST/bulk seam ``update_artifact_fields``. The fix shares one
guard between both seams; these tests pin the MCP side (and that reactivation
restores updatability) against a real ADR row.
"""
from __future__ import annotations

import pytest

from application.adr_service import AdrService
from mcp_server.tools.generic import GenericCrudToolGroup
from persistence.models import Artifact, LifecycleStatus
from persistence.tests.factories import active_tenant, editor_ctx, make_workspace
from persistence.tenancy import TenantContext
from workflow.services import reactivate

ORIGINAL_TITLE = "ADR under test"


def _create_adr(tenant, workspace, ctx):
    """Create a real ADR and return (adr, initial_version)."""
    TenantContext.set_tenant(tenant.id)
    try:
        adr = AdrService().create_adr(
            workspace_id=workspace.id,
            title=ORIGINAL_TITLE,
            description="description",
            ctx=ctx,
            context="context",
            consequences="consequences",
        )
        return adr, adr.version
    finally:
        TenantContext.clear_tenant()


def _mark_outdated(tenant, artifact_id) -> None:
    """Mirror ``workflow.services._set_lifecycle_status``'s soft-delete flag."""
    TenantContext.set_tenant(tenant.id)
    try:
        Artifact.objects.filter(id=artifact_id).update(
            lifecycle_status=LifecycleStatus.OUTDATED
        )
    finally:
        TenantContext.clear_tenant()


@pytest.mark.django_db
def test_outdated_adr_rejected_via_mcp_and_version_unchanged():
    with active_tenant() as tenant:
        workspace = make_workspace(tenant)
        ctx = editor_ctx(tenant, workspace)
        adr, initial_version = _create_adr(tenant, workspace, ctx)
        _mark_outdated(tenant, adr.artifact_id)

        group = GenericCrudToolGroup("adr", AdrService)
        result = group.execute_tool(
            "adr.update",
            {"id": str(adr.id), "title": "SHOULD NOT STICK"},
            ctx,
            "reqlo_test",
        )

        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"
        assert "outdated" in result.message.lower()

        TenantContext.set_tenant(tenant.id)
        try:
            adr.refresh_from_db()
            assert adr.title == ORIGINAL_TITLE
            assert adr.version == initial_version
        finally:
            TenantContext.clear_tenant()


@pytest.mark.django_db
def test_reactivated_adr_is_updatable_via_mcp():
    """Reactivating clears the soft-delete flag; the artifact is writable again."""
    with active_tenant() as tenant:
        workspace = make_workspace(tenant)
        ctx = editor_ctx(tenant, workspace)
        adr, initial_version = _create_adr(tenant, workspace, ctx)
        _mark_outdated(tenant, adr.artifact_id)

        TenantContext.set_tenant(tenant.id)
        try:
            reactivate(
                item_id=adr.id,
                item_type="Adr",
                workspace_id=workspace.id,
                ctx=ctx,
            )
        finally:
            TenantContext.clear_tenant()

        group = GenericCrudToolGroup("adr", AdrService)
        result = group.execute_tool(
            "adr.update",
            {"id": str(adr.id), "title": "Now it sticks"},
            ctx,
            "reqlo_test",
        )

        assert result.success is True, result.message

        TenantContext.set_tenant(tenant.id)
        try:
            adr.refresh_from_db()
            assert adr.title == "Now it sticks"
            assert adr.version == initial_version + 1
        finally:
            TenantContext.clear_tenant()
