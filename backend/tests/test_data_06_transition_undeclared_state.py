"""DATA-06 follow-up (findings 171/180/186/227): a state transition into a
state that the owning workflow definition does not declare must surface as a
clean 4xx, never as an HTTP 500.

The migration ``workflow/0021_we_item_state_integrity`` installs a
``BEFORE INSERT OR UPDATE`` trigger (``trg_we_state_current_state_in_definition``)
that rejects any ``current_state`` outside the definition's own
``workflow_json->'states'``. That trigger is the last line of defence: the
application normally validates an edge first, but a definition whose
``states``/``transitions`` are inconsistent (legacy/migrated data, a direct
definition edit) makes the write reach the database, where PostgreSQL raises a
``check_violation``. Django surfaces that as a ``DatabaseError`` /
``IntegrityError``.

Untranslated, that database error escapes ``WorkflowFacade`` and
``rest_api.views._service_error_response`` has no entry for it, so the client
gets ``500 {"code": "INTERNAL_SERVER_ERROR"}`` — a server-fault shape for what
is a rejected request. This module pins the contract that the facade translates
the DB guard into a ``ValidationError`` (HTTP 400, ``VALIDATION_ERROR``) with a
message that names the offending state.
"""
from __future__ import annotations

import uuid

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_ADMIN, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace
from workflow.models import WorkflowEngineDefinition
from workflow.services import create_default_workflow

# Fixture-only signing key; ``placeholder`` is the W1 secret scanner's
# documented allowlist token, exactly as in the neighbouring REST tests.
_SECRET = "test-secret-placeholder-not-a-real-key"

_JWT_OVERRIDES = dict(
    AUTH_JWT_SECRET=_SECRET,
    AUTH_JWT_ISSUER="reqflow",
    AUTH_JWT_AUDIENCE="reqflow-api",
    AUTH_JWT_TTL_SECONDS=3600,
)


@pytest.fixture
def undeclared_env(db):
    """Tenant + admin + a workspace with a provisioned Requirement workflow."""
    tenant = Tenant.objects.create(
        name="D06 T", slug=f"d06-t-{uuid.uuid4().hex[:8]}", is_active=True
    )
    admin = User.objects.create(
        username=f"d06admin-{uuid.uuid4().hex[:8]}",
        email="d06admin@t.test",
        tenant=tenant,
    )
    admin.set_password("d06pass123")
    admin.save(update_fields=["password"])
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="D06 WS", preset={"name": "standard"}
        )
        UserRole.objects.create(
            tenant=tenant, user=admin, workspace=workspace, role=ROLE_ADMIN
        )
        create_default_workflow(
            workspace_id=workspace.id,
            preset="standard",
            item_type="Requirement",
            tenant_id=tenant.id,
        )
        yield {"tenant": tenant, "admin": admin, "workspace": workspace}
    finally:
        clear_request_tenant()


def _client(env: dict) -> APIClient:
    client = APIClient()
    resp = client.post(
        "/api/v1/auth/login/",
        {"username": env["admin"].username, "password": "d06pass123"},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    token = resp.json()["token"]
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


def _create_requirement(client: APIClient, env: dict) -> str:
    created = client.post(
        "/api/v1/requirements/",
        {
            "workspace_id": str(env["workspace"].id),
            "title": "DATA-06 undeclared state",
            "description": "Exercises the state-membership DB guard.",
            "acceptance_criteria": "A rejected state answers 4xx, not 500.",
        },
        format="json",
    )
    assert created.status_code == 201, created.content
    return created.json()["id"]


def _drop_state_from_definition(env: dict, state: str) -> None:
    """Remove *state* from the definition's ``states`` but keep its transitions.

    That is the inconsistent shape the DB trigger exists to catch: the
    ``draft -> approved`` edge is still declared, so the application validator
    accepts the request, while the target is no longer a declared state.
    """
    set_request_tenant(env["tenant"].id)
    try:
        definition = WorkflowEngineDefinition.objects.get(
            workspace_id=env["workspace"].id, item_type="Requirement"
        )
        workflow_json = dict(definition.workflow_json)
        workflow_json["states"] = [
            s for s in workflow_json.get("states", []) if s != state
        ]
        definition.workflow_json = workflow_json
        definition.save(update_fields=["workflow_json"])
    finally:
        clear_request_tenant()


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_transition_into_undeclared_state_is_400_not_500(undeclared_env):
    client = _client(undeclared_env)
    item_id = _create_requirement(client, undeclared_env)
    _drop_state_from_definition(undeclared_env, "approved")

    response = client.post(
        f"/api/v1/requirements/{item_id}/transitions/",
        {"target_state": "approved", "change_reason": "target dropped"},
        format="json",
    )

    assert response.status_code == 400, (
        "a transition into a state the definition does not declare must be a "
        f"client error, got {response.status_code}: {response.content!r}"
    )
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR", body
    assert "approved" in body["error"]["message"], body
