"""CR-09b at the HTTP edge: a blocked global state delete answers 409, not 400.

DoD gap: ``rest_api/global_default_views.py::_map_workflow_error`` gained an
explicit ``isinstance(exc, (OrphanedStateError, StateReferencedError))`` branch
that answers 409. That branch had no test, and it is the kind of line that looks
covered by the branch below it: ``OrphanedStateError`` is a SUBCLASS of
``WorkflowDefinitionError``, so without the explicit branch the code still runs,
still returns a well-formed error envelope, and still has a 4xx status — it just
returns **400**. A test that only asserted "4xx" or "an error envelope" would
pass on the broken version.

So these tests assert the status code exactly, and they also assert the
distinction that gives the branch its purpose: 409 CONFLICT means "move the
items first, then retry", 400 VALIDATION_ERROR means "your request is
malformed". A client cannot recover from one and can from the other.
"""
from __future__ import annotations

import uuid

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from application.workspace_service import WorkspaceService
from auth_tenancy.context import AuthContext, AuthMethod
from persistence.models import Tenant, User
from persistence.tenancy import TenantContext
from workflow.models import GlobalWorkflowDefinition, WorkflowEngineDefinition, WorkflowItemState

pytestmark = pytest.mark.django_db

# Fixture-only signing key; ``placeholder`` is the W1 secret scanner's
# documented allowlist token (``_SAFE_PATTERNS``), cf.
# test_readonly_and_unknown_field_rejection_915_916.py.
_JWT = dict(
    AUTH_JWT_SECRET="test-secret-placeholder-not-a-real-key",
    AUTH_JWT_ISSUER="reqflow",
    AUTH_JWT_AUDIENCE="reqflow-api",
    AUTH_JWT_TTL_SECONDS=3600,
)

_ITEM_TYPE = "Adr"
_PRESET = "adr_default"
_DOOMED_STATE = "Superseded"


@pytest.fixture
def admin_client(db):
    tenant = Tenant.objects.create(name="CR09bTenant")
    TenantContext.set_tenant(tenant.id)
    try:
        user = User.objects.create(
            tenant=tenant, username="cr09badmin", email="a@x.io", is_active=True
        )
        user.set_password("cr09bpass123")
        user.save()
        ctx = AuthContext(
            user_id=user.id,
            tenant_id=tenant.id,
            active_roles=("admin",),
            auth_method=AuthMethod.BEARER_TOKEN,
        )
        ws = WorkspaceService().create_workspace(ctx, name="WS", preset="extended")
    finally:
        TenantContext.clear_tenant()

    client = APIClient()
    with override_settings(**_JWT):
        resp = client.post(
            "/api/v1/auth/login/",
            {"username": "cr09badmin", "password": "cr09bpass123"},
            format="json",
        )
        assert resp.status_code == 200, resp.content
        token = resp.json()["token"]
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client, tenant, ws


def _url(action: str = "") -> str:
    return f"/api/v1/workflow-defaults/{_ITEM_TYPE}/{_PRESET}/states/{_DOOMED_STATE}/{action}"


def _seed_blocking_setup(tenant, workspace) -> GlobalWorkflowDefinition:
    """A tenant global + a non-customized derived row + a live item in the state.

    The derived row is what makes this a *global* edit: the global row itself
    owns no ``WorkflowItemState``, so without a workspace inheriting from it the
    orphan gate has nothing to find and the delete would simply succeed.

    The global and the derived row are both REUSED, not created:
    ``WorkspaceService.create_workspace`` already seeded both, and
    ``uq_we_global_def_tenant_type_preset`` / ``uq_wedef_tenant_ws_type`` make a
    second row impossible. They are rewritten in place to a graph the gate
    cannot be short-circuited on.
    """
    global_def = GlobalWorkflowDefinition.unscoped.get(
        tenant_id=tenant.id, item_type=_ITEM_TYPE, preset=_PRESET
    )
    graph = {
        "states": ["Draft", "In Review", "Approved", _DOOMED_STATE],
        # No transition references the doomed state, so the STRUCTURAL gate
        # passes and the LIVE-ITEM gate is the only thing that can block. If the
        # two were conflated the test would pass for the wrong reason.
        "transitions": [
            {
                "from_state": "Draft",
                "to_state": "In Review",
                "allowed_roles": ["admin"],
                "requires_change_reason": False,
                "signature_gate": False,
            }
        ],
    }
    global_def.workflow_json = graph
    global_def.save(update_fields=["workflow_json"])
    TenantContext.set_tenant(tenant.id)
    try:
        derived = WorkflowEngineDefinition.objects.get(
            tenant=tenant, workspace_id=str(workspace.id), item_type=_ITEM_TYPE
        )
        derived.workflow_json = graph
        derived.source_global = global_def
        derived.is_customized = False
        derived.save(
            update_fields=["workflow_json", "source_global", "is_customized"]
        )
        WorkflowItemState.objects.create(
            tenant=tenant,
            item_id=uuid.uuid4(),
            item_type=_ITEM_TYPE,
            workspace_id=str(workspace.id),
            definition=derived,
            current_state=_DOOMED_STATE,
        )
    finally:
        TenantContext.clear_tenant()
    return global_def


@override_settings(**_JWT)
def test_orphaned_state_error_answers_409_conflict(admin_client):
    client, tenant, ws = admin_client
    _seed_blocking_setup(tenant, ws)

    resp = client.delete(_url())

    assert resp.status_code == 409, (
        f"a blocked delete must be a retryable CONFLICT, got "
        f"{resp.status_code}: {resp.content!r}"
    )
    assert resp.json()["error"]["code"] == "CONFLICT", resp.content


@override_settings(**_JWT)
def test_structural_state_referenced_error_also_answers_409(admin_client):
    """The same branch covers ``StateReferencedError`` — asserted separately.

    Both are mapped by one ``isinstance`` tuple; if someone later splits the
    branch and only keeps the orphan half, this test is what notices.
    """
    client, tenant, ws = admin_client
    _seed_blocking_setup(tenant, ws)
    # Make the doomed state transition-referenced so the STRUCTURAL gate fires
    # first, with NO live item anywhere (delete the item, keep the edge).
    global_def = GlobalWorkflowDefinition.unscoped.get(
        tenant_id=tenant.id, item_type=_ITEM_TYPE, preset=_PRESET
    )
    global_def.workflow_json = {
        "states": ["Draft", "In Review", "Approved", _DOOMED_STATE],
        "transitions": [
            {
                "from_state": "Approved",
                "to_state": _DOOMED_STATE,
                "allowed_roles": ["admin"],
                "requires_change_reason": False,
                "signature_gate": False,
            }
        ],
    }
    global_def.save(update_fields=["workflow_json"])
    WorkflowItemState.unscoped.filter(item_type=_ITEM_TYPE).delete()

    resp = client.delete(_url())

    assert resp.status_code == 409, resp.content
    assert resp.json()["error"]["code"] == "CONFLICT", resp.content


@override_settings(**_JWT)
def test_a_genuinely_malformed_request_still_answers_400(admin_client):
    """Counter-case pinning the DISTINCTION the branch exists to preserve.

    Without the explicit ``isinstance`` branch, ``OrphanedStateError`` degrades
    to exactly this 400 body. So this test is the control that shows the 409
    above is a real behavioural difference and not just "the endpoint returns
    an error either way".
    """
    client, _tenant, _ws = admin_client

    resp = client.delete(
        f"/api/v1/workflow-defaults/{_ITEM_TYPE}/{_PRESET}/states/NoSuchState/"
    )

    assert resp.status_code == 400, resp.content
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR", resp.content
