"""Tests for the workflow state read seam (Datenmodell-Konsolidierung Phase 0)."""
import uuid

import pytest

from persistence.tenancy import TenantContext
from workflow import state_reader


@pytest.fixture
def seeded_states(db):
    """Two Requirement item states: ids[0] -> draft, ids[1] -> approved."""
    from persistence.models import Tenant, Workspace
    from workflow.models import WorkflowEngineDefinition, WorkflowItemState

    tenant = Tenant.objects.create(name="t-state-reader", slug="t-state-reader")
    TenantContext.set_tenant(tenant.id)
    workspace = Workspace.objects.create(tenant=tenant, name="ws-state-reader")
    definition = WorkflowEngineDefinition.objects.create(
        tenant=tenant,
        workspace_id=workspace.id,
        item_type="Requirement",
        preset="standard",
        workflow_json={"states": ["draft", "approved"], "transitions": []},
    )
    ids = [uuid.uuid4(), uuid.uuid4()]
    for item_id, state in zip(ids, ["draft", "approved"]):
        WorkflowItemState.objects.create(
            tenant=tenant,
            item_id=item_id,
            item_type="Requirement",
            workspace_id=workspace.id,
            definition=definition,
            current_state=state,
        )
    return tenant, workspace, ids


@pytest.mark.django_db
class TestCurrentStates:
    def test_returns_state_keyed_by_string_id(self, seeded_states):
        tenant, workspace, ids = seeded_states
        TenantContext.set_tenant(tenant.id)

        result = state_reader.current_states("Requirement", ids)

        assert result == {str(ids[0]): "draft", str(ids[1]): "approved"}

    def test_unknown_id_is_absent_not_none(self, seeded_states):
        tenant, workspace, ids = seeded_states
        TenantContext.set_tenant(tenant.id)
        missing = uuid.uuid4()

        result = state_reader.current_states("Requirement", [missing])

        assert result == {}

    def test_empty_input_does_not_hit_the_db(self, django_assert_num_queries):
        with django_assert_num_queries(0):
            assert state_reader.current_states("Requirement", []) == {}

    def test_one_query_for_many_ids(self, seeded_states, django_assert_num_queries):
        tenant, workspace, ids = seeded_states
        TenantContext.set_tenant(tenant.id)

        with django_assert_num_queries(1):
            state_reader.current_states("Requirement", ids)

    def test_item_type_scopes_the_lookup(self, seeded_states):
        tenant, workspace, ids = seeded_states
        TenantContext.set_tenant(tenant.id)

        assert state_reader.current_states("Adr", ids) == {}

    def test_explicit_tenant_id_reads_a_different_tenant_than_active_context(
        self, seeded_states
    ):
        """``tenant_id`` must switch tenants, not just re-affirm the active
        one (N1: mirrors item_ids_in_state's identical contract)."""
        from persistence.models import Tenant, Workspace
        from workflow.models import WorkflowEngineDefinition, WorkflowItemState

        tenant, workspace, ids = seeded_states
        other_tenant = Tenant.objects.create(
            name="t-state-reader-other2", slug="t-state-reader-other2"
        )
        TenantContext.set_tenant(other_tenant.id)
        other_workspace = Workspace.objects.create(tenant=other_tenant, name="ws-other2")
        other_definition = WorkflowEngineDefinition.objects.create(
            tenant=other_tenant,
            workspace_id=other_workspace.id,
            item_type="Requirement",
            preset="standard",
            workflow_json={"states": ["draft", "approved"], "transitions": []},
        )
        other_id = uuid.uuid4()
        WorkflowItemState.objects.create(
            tenant=other_tenant,
            item_id=other_id,
            item_type="Requirement",
            workspace_id=other_workspace.id,
            definition=other_definition,
            current_state="draft",
        )

        # Active context is `other_tenant`, but tenant_id= explicitly asks for
        # `tenant`'s data — the result must come from `tenant`, not the active one.
        result = state_reader.current_states("Requirement", ids, tenant_id=tenant.id)

        assert result == {str(ids[0]): "draft", str(ids[1]): "approved"}

    def test_works_without_an_active_tenant_context(self, seeded_states):
        """The documented use case: no request-scoped ``TenantContext`` at all."""
        tenant, workspace, ids = seeded_states
        TenantContext.clear_tenant()

        result = state_reader.current_states("Requirement", ids, tenant_id=tenant.id)

        assert result == {str(ids[0]): "draft", str(ids[1]): "approved"}


@pytest.mark.django_db
class TestCurrentState:
    def test_single_lookup(self, seeded_states):
        tenant, workspace, ids = seeded_states
        TenantContext.set_tenant(tenant.id)

        assert state_reader.current_state("Requirement", ids[1]) == "approved"

    def test_missing_returns_none(self, seeded_states):
        tenant, workspace, ids = seeded_states
        TenantContext.set_tenant(tenant.id)

        assert state_reader.current_state("Requirement", uuid.uuid4()) is None


@pytest.mark.django_db
class TestItemIdsInState:
    def test_filters_by_state(self, seeded_states):
        tenant, workspace, ids = seeded_states
        TenantContext.set_tenant(tenant.id)

        assert list(state_reader.item_ids_in_state("Requirement", "approved")) == [ids[1]]

    def test_explicit_tenant_id_reads_a_different_tenant_than_active_context(
        self, seeded_states
    ):
        """``tenant_id`` must switch tenants, not just re-affirm the active one."""
        from persistence.models import Tenant, Workspace
        from workflow.models import WorkflowEngineDefinition, WorkflowItemState

        tenant, workspace, ids = seeded_states
        other_tenant = Tenant.objects.create(
            name="t-state-reader-other", slug="t-state-reader-other"
        )
        TenantContext.set_tenant(other_tenant.id)
        other_workspace = Workspace.objects.create(tenant=other_tenant, name="ws-other")
        other_definition = WorkflowEngineDefinition.objects.create(
            tenant=other_tenant,
            workspace_id=other_workspace.id,
            item_type="Requirement",
            preset="standard",
            workflow_json={"states": ["draft", "approved"], "transitions": []},
        )
        WorkflowItemState.objects.create(
            tenant=other_tenant,
            item_id=uuid.uuid4(),
            item_type="Requirement",
            workspace_id=other_workspace.id,
            definition=other_definition,
            current_state="draft",
        )

        # Active context is `other_tenant`, but tenant_id= explicitly asks for
        # `tenant`'s data — the result must come from `tenant`, not the active one.
        result = list(
            state_reader.item_ids_in_state("Requirement", "draft", tenant_id=tenant.id)
        )

        assert result == [ids[0]]

    def test_works_without_an_active_tenant_context(self, seeded_states):
        """The documented use case: no request-scoped ``TenantContext`` at all."""
        tenant, workspace, ids = seeded_states
        TenantContext.clear_tenant()

        result = list(
            state_reader.item_ids_in_state("Requirement", "draft", tenant_id=tenant.id)
        )

        assert result == [ids[0]]
