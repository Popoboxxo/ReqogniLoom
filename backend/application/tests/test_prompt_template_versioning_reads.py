"""Read seams on ``application.prompt_template_versioning`` (ADR-01, #124).

``mcp_server/tools/prompt_template.py`` used to run its ``PromptTemplate``
queries inline. They moved into ``get_active_template`` / ``list_active_templates``.

The two functions deliberately give ``workspace_id=None`` *different* meanings,
which is the single most likely thing to get wrong later, so it is pinned here:

* ``get_active_template(workspace_id=None)`` selects the tenant-wide scope —
  ``None`` is the real column value for a tenant-wide row.
* ``list_active_templates(workspace_id=None)`` applies **no** workspace filter
  and therefore also returns workspace-scoped rows.
"""
from __future__ import annotations

import pytest

from application.prompt_template_versioning import (
    get_active_template,
    list_active_templates,
    publish_new_version,
)
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db


@pytest.fixture
def tenant_workspace():
    from persistence.models import Tenant, Workspace

    tenant = Tenant.objects.create(name="PT Tenant", slug="pt-tenant")
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(tenant=tenant, name="PT WS")
        yield tenant, workspace
    finally:
        TenantContext.clear_tenant()


class TestGetActiveTemplate:
    def test_returns_none_when_nothing_published(self, tenant_workspace):
        tenant, _workspace = tenant_workspace

        assert get_active_template(tenant_id=tenant.id, name="slot_a") is None

    def test_returns_the_published_tenant_wide_row(self, tenant_workspace):
        tenant, _workspace = tenant_workspace
        publish_new_version(tenant_id=tenant.id, name="slot_a", content="global v1")

        row = get_active_template(tenant_id=tenant.id, name="slot_a")

        assert row is not None
        assert row.content == "global v1"
        assert row.workspace_id is None

    def test_workspace_none_does_not_match_a_workspace_scoped_row(
        self, tenant_workspace
    ):
        """``None`` means "tenant-wide", not "any workspace"."""
        tenant, workspace = tenant_workspace
        publish_new_version(
            tenant_id=tenant.id,
            name="slot_a",
            content="ws only",
            workspace_id=workspace.id,
        )

        assert get_active_template(tenant_id=tenant.id, name="slot_a") is None
        scoped = get_active_template(
            tenant_id=tenant.id, name="slot_a", workspace_id=workspace.id
        )
        assert scoped is not None
        assert scoped.content == "ws only"

    def test_returns_only_the_latest_version(self, tenant_workspace):
        tenant, _workspace = tenant_workspace
        publish_new_version(tenant_id=tenant.id, name="slot_a", content="v1")
        publish_new_version(tenant_id=tenant.id, name="slot_a", content="v2")

        row = get_active_template(tenant_id=tenant.id, name="slot_a")

        assert row.content == "v2"
        assert row.version == 2


class TestListActiveTemplates:
    def test_empty_by_default(self, tenant_workspace):
        tenant, _workspace = tenant_workspace

        assert list_active_templates(tenant_id=tenant.id) == []

    def test_no_workspace_filter_returns_global_and_scoped_rows(
        self, tenant_workspace
    ):
        tenant, workspace = tenant_workspace
        publish_new_version(tenant_id=tenant.id, name="slot_a", content="global")
        publish_new_version(
            tenant_id=tenant.id,
            name="slot_b",
            content="scoped",
            workspace_id=workspace.id,
        )

        rows = list_active_templates(tenant_id=tenant.id)

        assert {r.name for r in rows} == {"slot_a", "slot_b"}

    def test_workspace_filter_narrows_to_that_workspace(self, tenant_workspace):
        tenant, workspace = tenant_workspace
        publish_new_version(tenant_id=tenant.id, name="slot_a", content="global")
        publish_new_version(
            tenant_id=tenant.id,
            name="slot_b",
            content="scoped",
            workspace_id=workspace.id,
        )

        rows = list_active_templates(tenant_id=tenant.id, workspace_id=workspace.id)

        assert {r.name for r in rows} == {"slot_b"}

    def test_ordered_by_name(self, tenant_workspace):
        tenant, _workspace = tenant_workspace
        for name in ("zulu", "alpha", "mike"):
            publish_new_version(tenant_id=tenant.id, name=name, content="x")

        rows = list_active_templates(tenant_id=tenant.id)

        assert [r.name for r in rows] == ["alpha", "mike", "zulu"]

    def test_superseded_versions_are_excluded(self, tenant_workspace):
        tenant, _workspace = tenant_workspace
        publish_new_version(tenant_id=tenant.id, name="slot_a", content="v1")
        publish_new_version(tenant_id=tenant.id, name="slot_a", content="v2")

        rows = list_active_templates(tenant_id=tenant.id)

        assert len(rows) == 1
        assert rows[0].content == "v2"
