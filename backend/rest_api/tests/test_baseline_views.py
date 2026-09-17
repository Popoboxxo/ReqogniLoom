"""REST regression test for issue #724 — malformed document_id returns 400, not 500.

When ``scope=document`` is requested with a non-UUID ``document_id``, the
BaselineFacade must raise a ``ValidationError`` (mapped to HTTP 400) instead
of leaking an unhandled ``ValueError`` through the generic exception handler
(HTTP 500).
"""
from __future__ import annotations

import uuid

import pytest
from rest_framework.test import APIClient

from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace
from persistence.tenancy import TenantContext


def _make_tenant_and_workspace():
    tenant = Tenant.objects.create(
        id=uuid.uuid4(),
        name="gh724-tenant",
        slug=f"gh724-{uuid.uuid4().hex[:8]}",
    )
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            id=uuid.uuid4(),
            tenant=tenant,
            name="gh724-workspace",
            preset={"name": "standard"},
        )
        user = User.objects.create(
            id=uuid.uuid4(),
            tenant=tenant,
            username=f"gh724-{uuid.uuid4().hex[:8]}",
            email="gh724@example.com",
        )
    finally:
        TenantContext.clear_tenant()
    return tenant, workspace, user


def _get_token(client: APIClient, username: str, password: str = "gh724-pass-secure!") -> str:
    login = client.post(
        "/api/v1/auth/login/",
        {"username": username, "password": password},
        format="json",
    )
    assert login.status_code == 200, login.content
    return login.json()["token"]


@pytest.mark.django_db
class TestMalformedDocumentIdRest:
    def test_malformed_document_id_returns_400_not_500(self):
        """POST /api/v1/baselines/ with scope=document and a non-UUID
        document_id must return HTTP 400, not 500.

        Regression test for issue #724.
        """
        tenant, workspace, user = _make_tenant_and_workspace()
        user.set_password("gh724-pass-secure!")
        user.save(update_fields=["password"])

        from auth_tenancy.models import ROLE_EDITOR, UserRole

        set_request_tenant(tenant.id)
        try:
            UserRole.objects.create(
                tenant=tenant, user=user, workspace=workspace, role=ROLE_EDITOR
            )
        finally:
            clear_request_tenant()

        client = APIClient()
        token = _get_token(client, user.username)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        # Bypass the serializer-level artifact_id UUIDField by sending
        # document_id directly in the body (as MCP callers do).
        # The serializer ignores unknown fields, so the facade receives
        # "not-a-uuid" and must convert it to a ValidationError (400),
        # not leak a ValueError (500).
        set_request_tenant(tenant.id)
        try:
            response = client.post(
                "/api/v1/baselines/",
                {
                    "workspace_id": str(workspace.id),
                    "scope": "document",
                    "document_id": "not-a-uuid",
                },
                format="json",
            )
        finally:
            clear_request_tenant()

        # Must be 400 (validation error), never 500 (unhandled exception).
        assert response.status_code == 400, (
            f"Expected 400 for malformed document_id, got {response.status_code}: "
            f"{response.data}"
        )

    def test_malformed_artifact_id_returns_400_not_500(self):
        """POST /api/v1/baselines/ with scope=document and a non-UUID
        artifact_id must return HTTP 400 from serializer validation.

        This is the normal REST path (artifact_id is a UUIDField on the
        BaselineSerializer); the facade-level fix (#724) protects callers
        that bypass the serializer (MCP tools, direct service calls).
        """
        tenant, workspace, user = _make_tenant_and_workspace()
        user.set_password("gh724-pass-secure!")
        user.save(update_fields=["password"])

        from auth_tenancy.models import ROLE_EDITOR, UserRole

        set_request_tenant(tenant.id)
        try:
            UserRole.objects.create(
                tenant=tenant, user=user, workspace=workspace, role=ROLE_EDITOR
            )
        finally:
            clear_request_tenant()

        client = APIClient()
        token = _get_token(client, user.username)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        set_request_tenant(tenant.id)
        try:
            response = client.post(
                "/api/v1/baselines/",
                {
                    "workspace_id": str(workspace.id),
                    "scope": "document",
                    "artifact_id": "not-a-uuid",
                },
                format="json",
            )
        finally:
            clear_request_tenant()

        assert response.status_code == 400, (
            f"Expected 400 for malformed artifact_id, got {response.status_code}: "
            f"{response.data}"
        )
