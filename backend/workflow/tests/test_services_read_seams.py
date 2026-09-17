"""Read seams exposed for the ``review.*`` MCP tools (ADR-01, issue #124).

``mcp_server/tools/review.py`` used to query ``WorkflowEngineDefinition`` and
``WorkflowItemState`` directly, which broke ADR-01's Single-Entry-Point rule.
The queries moved behind ``workflow.services.get_workflow_json`` and
``workflow.services.list_item_states``; these tests pin the two contracts that
the tool relies on and that a naive re-implementation would get wrong:

* ``get_workflow_json`` must return the *raw* document (``WorkflowDefinitionDTO``
  drops the per-state metadata block that ``get_state_meta`` reads) and must
  return ``{}`` instead of raising when nothing is configured.
* ``list_item_states`` must filter by tenant *and* workspace, and treat a falsy
  ``item_type`` as "no filter".
"""
from __future__ import annotations

import uuid

import pytest

from persistence.models import Tenant, Workspace
from persistence.tenancy import TenantContext
from workflow.definition_store import get_state_meta
from workflow.services import (
    create_default_workflow,
    get_workflow_json,
    list_item_states,
)

pytestmark = pytest.mark.django_db


class TestGetWorkflowJson:
    def test_returns_raw_document_with_states(self, tenant, workspace):
        TenantContext.set_tenant(tenant.id)
        try:
            create_default_workflow(
                workspace_id=workspace.id,
                preset="standard",
                item_type="Requirement",
                tenant_id=tenant.id,
            )

            workflow_json = get_workflow_json(workspace.id, "Requirement")
        finally:
            TenantContext.clear_tenant()

        assert isinstance(workflow_json, dict)
        assert workflow_json.get("states"), "raw document must carry the state list"
        assert workflow_json.get("transitions")

    def test_result_is_consumable_by_get_state_meta(self, tenant, workspace):
        """The whole point of this seam: DTO-dropped metadata stays reachable."""
        TenantContext.set_tenant(tenant.id)
        try:
            create_default_workflow(
                workspace_id=workspace.id,
                preset="standard",
                item_type="Requirement",
                tenant_id=tenant.id,
            )
            workflow_json = get_workflow_json(workspace.id, "Requirement")
        finally:
            TenantContext.clear_tenant()

        for state in workflow_json["states"]:
            assert isinstance(get_state_meta(workflow_json, state), dict)

    def test_unconfigured_workspace_returns_empty_dict_not_raises(
        self, tenant, workspace
    ):
        TenantContext.set_tenant(tenant.id)
        try:
            assert get_workflow_json(workspace.id, "Requirement") == {}
            # Also for a workspace that does not exist at all.
            assert get_workflow_json(uuid.uuid4(), "Requirement") == {}
        finally:
            TenantContext.clear_tenant()

    def test_unknown_item_type_returns_empty_dict(self, tenant, workspace):
        TenantContext.set_tenant(tenant.id)
        try:
            create_default_workflow(
                workspace_id=workspace.id,
                preset="standard",
                item_type="Requirement",
                tenant_id=tenant.id,
            )

            assert get_workflow_json(workspace.id, "NoSuchType") == {}
        finally:
            TenantContext.clear_tenant()


class TestListItemStates:
    def test_returns_the_workspace_item_states(self, requirement_with_workflow, tenant, workspace):
        TenantContext.set_tenant(tenant.id)
        try:
            rows = list(
                list_item_states(workspace.id, tenant_id=tenant.id)
            )
        finally:
            TenantContext.clear_tenant()

        assert rows, "the fixture initialises a WorkflowItemState"
        assert {r.item_type for r in rows} == {"Requirement"}

    def test_item_type_filter_narrows_the_result(
        self, requirement_with_workflow, tenant, workspace
    ):
        TenantContext.set_tenant(tenant.id)
        try:
            matching = list(
                list_item_states(
                    workspace.id, tenant_id=tenant.id, item_type="Requirement"
                )
            )
            other = list(
                list_item_states(
                    workspace.id, tenant_id=tenant.id, item_type="TestCase"
                )
            )
        finally:
            TenantContext.clear_tenant()

        assert matching
        assert other == []

    def test_falsy_item_type_means_no_filter(
        self, requirement_with_workflow, tenant, workspace
    ):
        """``review.list_pending`` passes ``params.get("item_type")`` straight
        through, so ``None``/``""`` must not degenerate into an impossible
        ``item_type=""`` filter."""
        TenantContext.set_tenant(tenant.id)
        try:
            unfiltered = list(list_item_states(workspace.id, tenant_id=tenant.id))
            empty_string = list(
                list_item_states(workspace.id, tenant_id=tenant.id, item_type="")
            )
        finally:
            TenantContext.clear_tenant()

        assert unfiltered
        assert len(empty_string) == len(unfiltered)

    def test_other_workspace_is_not_returned(
        self, requirement_with_workflow, tenant, workspace
    ):
        TenantContext.set_tenant(tenant.id)
        try:
            other_ws = Workspace.objects.create(tenant=tenant, name="Other WS")
            rows = list(list_item_states(other_ws.id, tenant_id=tenant.id))
        finally:
            TenantContext.clear_tenant()

        assert rows == []

    def test_other_tenant_is_not_returned(
        self, requirement_with_workflow, tenant, workspace
    ):
        other_tenant = Tenant.objects.create(name="Other Tenant", slug="other-tenant")

        TenantContext.set_tenant(other_tenant.id)
        try:
            rows = list(list_item_states(workspace.id, tenant_id=other_tenant.id))
        finally:
            TenantContext.clear_tenant()

        assert rows == []
