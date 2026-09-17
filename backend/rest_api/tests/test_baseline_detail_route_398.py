"""Issue #398 — ``GET /api/v1/baselines/<id>/`` must return the captured items.

The audit observed a hard 404 on the detail route (UI: "Captured items —
Laden…" hangs forever) even though the create response had listed entries and
``bl_delta_index_entry`` held rows for that baseline.

Cause: ``BaselineViewSet.retrieve`` ran the preset gate *before* loading the
baseline. The detail route carries no ``workspace_id`` in its URL or query
string, so ``PresetGateMixin._guard_preset`` fell through to its last-resort
fallback and substituted the caller's **tenant** id for the workspace id.
``presets.gate._get_or_create_preset_config`` then looked that id up in
``pl_workspace``, raised ``Workspace.DoesNotExist``, and the gate mapped the
resulting ``PresetError`` to a bare ``Http404`` — for every caller, in every
preset. ``/baselines/diff/`` sat on the same landmine.

Fix: resolve the baseline first (the service is tenant-scoped and raises
NotFoundError for foreign baselines) and gate on the baseline's *own*
workspace.
"""
from __future__ import annotations

import uuid

import pytest
from rest_framework.test import APIRequestFactory

from rest_api.views import BaselineViewSet


def _auth_context(user_id: uuid.UUID, tenant_id: uuid.UUID):
    from auth_tenancy.context import AuthContext, AuthMethod

    return AuthContext(
        user_id=user_id,
        tenant_id=tenant_id,
        active_roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN,
    )


def _build_baseline(workspace_id, tenant_id, name: str):
    """Create a project baseline through ``baseline.services``.

    Deliberately not through ``BaselineFacade``: its SE-Auditor gate rejects a
    workspace whose lone Requirement has no upstream 'derives-from' link, which
    is orthogonal to the REST routing behaviour under test here.
    """
    from baseline.services import build as baseline_build

    return baseline_build(
        scope="project",
        workspace_id=workspace_id,
        name=name,
        tenant_id=tenant_id,
        created_by="issue398-rest-test",
    )


@pytest.fixture()
def baseline_fixture(db):
    """A tenant/workspace with one requirement and one project baseline."""
    from persistence.models import Artifact, Requirement, Tenant, User, Workspace
    from persistence.tenancy import TenantContext

    tenant = Tenant.objects.create(
        id=uuid.uuid4(),
        name="issue398-rest-tenant",
        slug=f"issue398-rest-{uuid.uuid4().hex[:8]}",
    )
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            id=uuid.uuid4(),
            tenant=tenant,
            name=f"issue398-rest-ws-{uuid.uuid4().hex[:6]}",
            preset={"name": "standard"},
        )
        user = User.objects.create(
            id=uuid.uuid4(),
            tenant=tenant,
            username=f"issue398-{uuid.uuid4().hex[:8]}",
            email="issue398@example.com",
        )
        artifact = Artifact.objects.create(
            id=uuid.uuid4(),
            tenant=tenant,
            workspace=workspace,
            artifact_type="Requirement",
        )
        Requirement.objects.create(
            id=uuid.uuid4(),
            tenant=tenant,
            artifact=artifact,
            workspace=workspace,
            uid="REQ-398-REST-001",
            title="Detail route must load",
        )

        ctx = _auth_context(user.id, tenant.id)
        baseline_id = _build_baseline(
            workspace.id, tenant.id, f"issue398-rest-{uuid.uuid4().hex[:6]}"
        )
        yield {
            "tenant": tenant,
            "workspace": workspace,
            "ctx": ctx,
            "baseline_id": baseline_id,
            "artifact_id": str(artifact.id),
        }
    finally:
        TenantContext.clear_tenant()


def _call(view_actions, path, ctx, tenant_id, **kwargs):
    """Invoke a viewset action directly, with the thread-local tenant set.

    A direct ``view()`` call bypasses ``persistence.middleware``, which is what
    normally installs the TenantContext for the request — mirrors the existing
    pattern in ``test_baseline_workspace_routing.py``.
    """
    from persistence.tenancy import TenantContext

    factory = APIRequestFactory()
    req = factory.get(path)
    req.auth_context = ctx
    view = BaselineViewSet.as_view(view_actions)
    TenantContext.set_tenant(tenant_id)
    try:
        return view(req, **kwargs)
    finally:
        TenantContext.clear_tenant()


@pytest.mark.django_db
class TestBaselineDetailRoute:
    def test_detail_route_returns_200_with_entries(self, baseline_fixture):
        fx = baseline_fixture
        response = _call(
            {"get": "retrieve"},
            f"/api/v1/baselines/{fx['baseline_id']}/",
            fx["ctx"],
            fx["tenant"].id,
            pk=str(fx["baseline_id"]),
        )

        assert response.status_code == 200, response.data
        assert response.data["id"] == str(fx["baseline_id"])
        entries = response.data["entries"]
        assert entries, "detail route must serve the captured delta entries"
        assert fx["artifact_id"] in {e["item_id"] for e in entries}
        # REQ-L2-BL-012: each entry carries its full-state snapshot.
        captured = next(e for e in entries if e["item_id"] == fx["artifact_id"])
        assert captured["state"]["title"] == "Detail route must load"

    def test_diff_route_returns_200_without_a_workspace_id_param(
        self, baseline_fixture
    ):
        """The diff endpoint sat on the same preset-gate landmine."""
        fx = baseline_fixture
        second_id = _build_baseline(
            fx["workspace"].id,
            fx["tenant"].id,
            f"issue398-rest-b-{uuid.uuid4().hex[:6]}",
        )

        response = _call(
            {"get": "diff"},
            f"/api/v1/baselines/diff/?baseline_a={fx['baseline_id']}"
            f"&baseline_b={second_id}",
            fx["ctx"],
            fx["tenant"].id,
        )

        assert response.status_code == 200, response.data
        assert response.data["summary"]["changed"] == 0

    def test_diff_reports_a_post_baseline_requirement_edit(self, baseline_fixture):
        """End-to-end #398: edit a requirement, re-baseline, diff sees it."""
        from persistence.models import Requirement

        fx = baseline_fixture
        Requirement.unscoped.filter(artifact_id=fx["artifact_id"]).update(
            title="[POST-BASELINE-EDIT] Detail route must load"
        )
        second_id = _build_baseline(
            fx["workspace"].id,
            fx["tenant"].id,
            f"issue398-rest-c-{uuid.uuid4().hex[:6]}",
        )

        response = _call(
            {"get": "diff"},
            f"/api/v1/baselines/diff/?baseline_a={fx['baseline_id']}"
            f"&baseline_b={second_id}",
            fx["ctx"],
            fx["tenant"].id,
        )

        assert response.status_code == 200, response.data
        assert response.data["summary"]["changed"] == 1
        item = next(i for i in response.data["items"] if i["status"] == "changed")
        assert item["item_id"] == fx["artifact_id"]
        titles = [
            fc for fc in item["field_changes"] if fc["field_name"] == "title"
        ]
        assert titles[0]["new_value"] == "[POST-BASELINE-EDIT] Detail route must load"
