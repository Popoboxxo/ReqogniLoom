"""No create path accepts or writes an initial status.

Datenmodell-Konsolidierung Phase 1. The workflow definition's initial_state is
the only source of a new item's state (ADR-status-single-source).
"""
import inspect
import uuid

import pytest

from application.adr_service import AdrService
from application.issue_service import IssueService
from application.risk_service import RiskService

CREATE_METHODS = [
    (AdrService, "create_adr"),
    (RiskService, "create_risk"),
    (IssueService, "create_issue"),
]


@pytest.mark.parametrize(
    "service,method", CREATE_METHODS, ids=lambda v: getattr(v, "__name__", str(v))
)
def test_create_has_no_status_parameter(service, method):
    signature = inspect.signature(getattr(service, method))
    assert "status" not in signature.parameters


def test_adr_validator_has_no_status_check():
    source = inspect.getsource(AdrService)
    assert "VALID_STATUSES" not in source


@pytest.fixture
def api_client_env(db):
    """An authenticated APIClient (real Bearer JWT) + a workspace id.

    DRF's ``force_authenticate`` never populates ``request.auth_context``
    under this codebase's ``AuthTenancyAuthentication`` (see
    rest_api/tests/conftest.py::authed_client and
    rest_api/tests/test_interview_provenance.py's module docstring) — a
    real login is required, or the create call 401s before ever reaching
    ``IssueService.create_issue``.
    """
    from rest_framework.test import APIClient

    from auth_tenancy.models import ROLE_ADMIN, UserRole
    from persistence.middleware import clear_request_tenant, set_request_tenant
    from persistence.models import Tenant, User, Workspace

    tenant = Tenant.objects.create(
        name="t-no-init-status",
        slug=f"no-init-status-{uuid.uuid4().hex[:8]}",
        is_active=True,
    )
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="ws-no-init-status", preset={"name": "extended"}
        )
    finally:
        clear_request_tenant()

    username = f"u{uuid.uuid4().hex[:8]}"
    user = User.objects.create(
        username=username,
        email=f"{username}@example.com",
        tenant=tenant,
    )
    user.set_password("hunter2pass")
    user.save(update_fields=["password"])

    set_request_tenant(tenant.id)
    try:
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=workspace, role=ROLE_ADMIN
        )
    finally:
        clear_request_tenant()

    login_client = APIClient()
    login = login_client.post(
        "/api/v1/auth/login/",
        {"username": username, "password": "hunter2pass"},
        format="json",
    )
    assert login.status_code == 200, login.content
    token = login.json()["token"]
    authed = APIClient()
    authed.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return authed, workspace.id


@pytest.mark.django_db
def test_issue_create_ignores_a_client_supplied_status(api_client_env):
    client, workspace_id = api_client_env

    response = client.post(
        "/api/v1/issues/",
        {
            "workspace_id": str(workspace_id),
            "title": "I1",
            "description": "d",
            "status": "closed",
        },
        format="json",
    )

    assert response.status_code == 201, response.content
    assert response.data["status"] != "closed"
