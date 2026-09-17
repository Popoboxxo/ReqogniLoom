"""REST regression tests for issue #796.

``requirement.check_consistency`` dispatches an async Celery task and
returns only a ``task_id`` -- before this fix there was no REST endpoint to
ever retrieve the result (orphan task; ``GET
/api/v1/consistency-status/<id>/`` 404'd). ``ConsistencyStatusView`` wires
the previously-unused generic ``llm_adapter.services.get_task_status`` to
this capability, tenant-scoped the same way as
``BundleCompressionStatusView`` (ADR-03).
"""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace


@pytest.fixture
def other_tenant_authed_client() -> APIClient:
    """A second, unrelated tenant's authenticated APIClient (mirrors
    test_requirement_bundle_export.py's fixture of the same purpose): used
    to prove a task_id dispatched by one tenant cannot be polled by
    another via GET /api/v1/consistency-status/{task_id}/."""
    from auth_tenancy.models import ROLE_ADMIN, UserRole

    other_tenant = Tenant.objects.create(
        name="Other Consistency Tenant",
        slug=f"other-consistency-tenant-{uuid.uuid4().hex[:8]}",
        is_active=True,
    )
    set_request_tenant(other_tenant.id)
    try:
        other_workspace = Workspace.objects.create(
            tenant=other_tenant, name="Other Consistency WS", preset={"name": "extended"}
        )
        user = User.objects.create(
            username="otherconsistencyadmin",
            email="otherconsistencyadmin@t.test",
            tenant=other_tenant,
        )
        user.set_password("hunter2pass")
        user.save(update_fields=["password"])
        UserRole.objects.create(
            tenant=other_tenant, user=user, workspace=other_workspace, role=ROLE_ADMIN
        )
    finally:
        clear_request_tenant()

    client = APIClient()
    login = client.post(
        "/api/v1/auth/login/",
        {"username": "otherconsistencyadmin", "password": "hunter2pass"},
        format="json",
    )
    assert login.status_code == 200, login.content
    token = login.json()["token"]
    authed = APIClient()
    authed.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return authed


def _dispatch_task_id(tenant: Tenant, workspace: Workspace) -> str:
    """Dispatch a check_consistency task for *tenant*/*workspace* and return
    its task_id, bypassing the LLM/Celery broker via a mock."""
    from application.requirement_service import RequirementService
    from auth_tenancy.context import AuthContext, AuthMethod

    ctx = AuthContext(
        tenant_id=tenant.id,
        user_id=uuid.uuid4(),
        active_roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN,
    )
    with patch(
        "llm_adapter.services.check_consistency",
        return_value={"task_id": f"gh796-{uuid.uuid4().hex[:12]}"},
    ):
        result = RequirementService().check_consistency(workspace.id, ctx)
    return result["task_id"]


@pytest.mark.django_db
class TestConsistencyStatusView:
    def test_unknown_task_id_returns_not_found_not_404(self, authed_client):
        """A task_id that was never dispatched must report status=not_found
        with HTTP 200, matching BundleCompressionStatusView's contract --
        not a raw HTTP 404 (the pre-fix symptom from the QA report)."""
        resp = authed_client.get("/api/v1/consistency-status/never-dispatched/")

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "not_found"
        assert body["task_id"] == "never-dispatched"

    def test_same_tenant_poll_reaches_the_real_status(
        self, authed_client, tenant, workspace,
    ):
        task_id = _dispatch_task_id(tenant, workspace)

        from llm_adapter.dispatcher import AsyncTaskDispatcher, TaskStatusResult

        with patch.object(
            AsyncTaskDispatcher, "get_task_status",
            return_value=TaskStatusResult(task_id=task_id, status="pending"),
        ):
            resp = authed_client.get(f"/api/v1/consistency-status/{task_id}/")

        assert resp.status_code == 200
        assert resp.json()["status"] == "pending"
        assert resp.json()["task_id"] == task_id

    def test_cross_tenant_poll_returns_not_found(
        self, authed_client, other_tenant_authed_client, tenant, workspace,
    ):
        task_id = _dispatch_task_id(tenant, workspace)

        from llm_adapter.dispatcher import AsyncTaskDispatcher

        with patch.object(AsyncTaskDispatcher, "get_task_status") as mock_get_status:
            resp = other_tenant_authed_client.get(
                f"/api/v1/consistency-status/{task_id}/"
            )

        assert resp.status_code == 200
        body = resp.json()
        # Load-bearing: identical to a genuinely-unknown task_id's response
        # -- a cross-tenant probe must not be able to distinguish "exists,
        # not yours" from "doesn't exist".
        assert body["status"] == "not_found"
        assert body["task_id"] == task_id
        mock_get_status.assert_not_called()
