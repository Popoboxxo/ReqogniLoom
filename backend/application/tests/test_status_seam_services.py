"""ADR/Risk/Issue list paths filter through the workflow engine, not a column.

Datenmodell-Konsolidierung Phase 1.
"""
import inspect
import uuid

import pytest

from application import adr_service, issue_service, risk_service

MODULES = [adr_service, risk_service, issue_service]


def _seed_item(model_cls, item_type, states=("Draft", "outdated")):
    """Create *model_cls* rows (one per state in *states*) with matching
    WorkflowItemState rows, mirroring the adr_fixture shape for Risk/Issue."""
    from persistence.models import Artifact, Tenant, Workspace
    from persistence.tenancy import TenantContext
    from workflow.models import WorkflowEngineDefinition, WorkflowItemState

    tenant = Tenant.objects.create(name=f"t-status-seam-{item_type}")
    # Workspace/Artifact/model rows below are tenant-scoped managers — the
    # context must be active before they are created, not just before the
    # AuthContext is built (the brief's own fixture sets it in this order).
    TenantContext.set_tenant(tenant.id)
    workspace = Workspace.objects.create(tenant=tenant, name=f"ws-status-seam-{item_type}")
    definition = WorkflowEngineDefinition.objects.create(
        tenant=tenant,
        workspace_id=workspace.id,
        item_type=item_type,
        preset=WorkflowEngineDefinition.PRESET_MINIMAL,
        workflow_json={"states": list(states), "transitions": []},
    )
    created = []
    for state in states:
        artifact = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type=item_type
        )
        kwargs = {
            "artifact": artifact,
            "workspace_id": workspace.id,
            "tenant_id": tenant.id,
            "title": f"{item_type} {state}",
            "description": "d",
        }
        if item_type == "Risk":
            kwargs.update(probability="low", impact="low", category="technical")
        if item_type == "Issue":
            kwargs.update(severity="medium", category="defect")
        item = model_cls.objects.create(**kwargs)
        WorkflowItemState.objects.create(
            tenant=tenant,
            item_id=item.id,
            item_type=item_type,
            workspace_id=workspace.id,
            definition=definition,
            current_state=state,
        )
        created.append(item.id)
    return tenant, workspace, created


def _make_ctx(tenant, workspace):
    """Build a real AuthContext (not the brief's sketch — ``AuthContext`` has
    no ``roles=`` kwarg, it's ``active_roles``; there's no free
    ``persistence.tenancy.set_tenant`` function, only the
    ``TenantContext.set_tenant`` classmethod)."""
    from auth_tenancy.context import AuthContext, AuthMethod
    from persistence.tenancy import TenantContext

    TenantContext.set_tenant(tenant.id)
    return AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=tenant.id,
        active_roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN,
        workspace_id=workspace.id,
    )


@pytest.fixture
def adr_fixture(db):
    from application.models import Adr

    tenant, workspace, (live_id, outdated_id) = _seed_item(Adr, "Adr")
    ctx = _make_ctx(tenant, workspace)
    return ctx, workspace.id, live_id, outdated_id


@pytest.fixture
def risk_fixture(db):
    from application.models import Risk

    tenant, workspace, (live_id, outdated_id) = _seed_item(Risk, "Risk")
    ctx = _make_ctx(tenant, workspace)
    return ctx, workspace.id, live_id, outdated_id


@pytest.fixture
def issue_fixture(db):
    from application.models import Issue

    tenant, workspace, (live_id, outdated_id) = _seed_item(Issue, "Issue")
    ctx = _make_ctx(tenant, workspace)
    return ctx, workspace.id, live_id, outdated_id


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.__name__)
def test_no_status_column_filter_remains(module):
    source = inspect.getsource(module)
    assert 'exclude(status="outdated")' not in source
    assert "status=status," not in source


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.__name__)
def test_module_imports_the_seam(module):
    assert "from workflow import state_reader" in inspect.getsource(module)


@pytest.mark.django_db
class TestAdrListing:
    def test_outdated_adr_is_excluded_by_default(self, adr_fixture):
        from application.adr_service import AdrService

        ctx, workspace_id, live_id, outdated_id = adr_fixture
        ids = {a.id for a in AdrService().list_adrs(workspace_id, ctx)}

        assert live_id in ids
        assert outdated_id not in ids

    def test_include_deleted_returns_both(self, adr_fixture):
        from application.adr_service import AdrService

        ctx, workspace_id, live_id, outdated_id = adr_fixture
        ids = {
            a.id
            for a in AdrService().list_adrs(workspace_id, ctx, include_deleted=True)
        }

        assert {live_id, outdated_id} <= ids

    def test_list_by_status_matches_engine_state(self, adr_fixture):
        from application.adr_service import AdrService

        ctx, workspace_id, live_id, outdated_id = adr_fixture
        result = AdrService().list_adrs_by_status(workspace_id, "outdated", ctx)

        assert [a.id for a in result] == [outdated_id]


@pytest.mark.django_db
class TestRiskListing:
    def test_outdated_risk_is_excluded_by_default(self, risk_fixture):
        from application.risk_service import RiskService

        ctx, workspace_id, live_id, outdated_id = risk_fixture
        ids = {r.id for r in RiskService().list_risks(workspace_id, ctx)}

        assert live_id in ids
        assert outdated_id not in ids

    def test_include_deleted_returns_both(self, risk_fixture):
        from application.risk_service import RiskService

        ctx, workspace_id, live_id, outdated_id = risk_fixture
        ids = {
            r.id
            for r in RiskService().list_risks(workspace_id, ctx, include_deleted=True)
        }

        assert {live_id, outdated_id} <= ids

    def test_list_by_status_matches_engine_state(self, risk_fixture):
        from application.risk_service import RiskService

        ctx, workspace_id, live_id, outdated_id = risk_fixture
        result = RiskService().list_risks_by_status(workspace_id, "outdated", ctx)

        assert [r.id for r in result] == [outdated_id]


@pytest.mark.django_db
class TestIssueListing:
    def test_outdated_issue_is_excluded_by_default(self, issue_fixture):
        from application.issue_service import IssueService

        ctx, workspace_id, live_id, outdated_id = issue_fixture
        ids = {i.id for i in IssueService().list_issues(workspace_id, ctx)}

        assert live_id in ids
        assert outdated_id not in ids

    def test_include_deleted_returns_both(self, issue_fixture):
        from application.issue_service import IssueService

        ctx, workspace_id, live_id, outdated_id = issue_fixture
        ids = {
            i.id
            for i in IssueService().list_issues(workspace_id, ctx, include_deleted=True)
        }

        assert {live_id, outdated_id} <= ids

    def test_list_by_status_matches_engine_state(self, issue_fixture):
        from application.issue_service import IssueService

        ctx, workspace_id, live_id, outdated_id = issue_fixture
        result = IssueService().list_issues_by_status(workspace_id, "outdated", ctx)

        assert [i.id for i in result] == [outdated_id]
