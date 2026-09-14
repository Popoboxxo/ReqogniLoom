"""Risk PATCH: free-text ``owner_name`` vs Actor ``owner`` (WS6/WS7 #939/#940).

Regression for the review Blocker 1: ``RiskViewSet.partial_update`` forwarded
``data.get("owner")`` — the Actor wire value declared by
``ArtifactSystemFieldsSerializerMixin`` — to ``RiskService.update_risk(owner=…)``,
which writes it into the free-text ``Risk.owner_name`` CharField (``str(dict)``)
and dropped the client's real ``owner_name``.

The two carriers are independent and both must survive a PATCH:

* ``owner_name`` → the legacy ``Risk`` CharField (free text);
* ``owner``      → the Artifact-level ``Actor`` FK via the system-field gateway.
"""
from __future__ import annotations

import uuid

import pytest
from django.core.management import call_command
from rest_framework.test import APIClient

from application.risk_service import RiskService
from auth_tenancy.context import AuthContext, AuthMethod
from auth_tenancy.models import ROLE_ADMIN, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Actor, Artifact, Risk, Tenant, User, Workspace

pytestmark = pytest.mark.django_db

PASSWORD = "hunter2pass"


@pytest.fixture
def risk_env(db):
    """A bootstrapped standard-Risk tenant/workspace plus a logged-in admin."""
    suffix = uuid.uuid4().hex[:8]
    tenant = Tenant.objects.create(
        name=f"rn-{suffix}", slug=f"rn-{suffix}", is_active=True
    )
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="ws", preset={"name": "standard"}
        )
        user = User.objects.create(
            username=f"rn-admin-{suffix}",
            email=f"rn-{suffix}@t.test",
            tenant=tenant,
            first_name="Ada",
            last_name="Lovelace",
        )
        user.set_password(PASSWORD)
        user.save(update_fields=["password"])
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=workspace, role=ROLE_ADMIN
        )
    finally:
        clear_request_tenant()

    call_command("bootstrap_attribute_definitions", tenant=str(tenant.id))

    client = APIClient()
    login = client.post(
        "/api/v1/auth/login/",
        {"username": user.username, "password": PASSWORD},
        format="json",
    )
    assert login.status_code == 200, login.content
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.json()['token']}")
    return tenant, workspace, user, client


def _create_risk(tenant, workspace, user, owner_name: str = "Original Text") -> Risk:
    ctx = AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        workspace_id=workspace.id,
        active_roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN,
    )
    return RiskService().create_risk(
        workspace_id=workspace.id,
        title="Regression Risk",
        probability="medium",
        impact="medium",
        ctx=ctx,
        owner=owner_name,
    )


def test_create_persists_owner_name_free_text(risk_env) -> None:
    """The create path already routed ``owner_name`` correctly — pin it."""
    tenant, workspace, user, client = risk_env
    response = client.post(
        "/api/v1/risks/",
        {
            "workspace_id": str(workspace.id),
            "title": "Created Risk",
            "owner_name": "Alan Turing",
        },
        format="json",
    )
    assert response.status_code == 201, response.content
    risk = Risk.unscoped.get(id=response.json()["id"])
    assert risk.owner_name == "Alan Turing"


def test_patch_owner_name_persists_free_text_and_never_str_dict(risk_env) -> None:
    """Blocker 1: a free-text ``owner_name`` PATCH must reach the column."""
    tenant, workspace, user, client = risk_env
    risk = _create_risk(tenant, workspace, user)

    response = client.patch(
        f"/api/v1/risks/{risk.id}/", {"owner_name": "Grace Hopper"}, format="json"
    )

    assert response.status_code == 200, response.content
    risk.refresh_from_db()
    assert risk.owner_name == "Grace Hopper"
    assert "{" not in risk.owner_name, "an Actor dict must never be str()-ed into owner_name"


def test_patch_actor_owner_sets_actor_and_leaves_owner_name(risk_env) -> None:
    """Blocker 1: an Actor ``owner`` PATCH must not touch ``owner_name``."""
    tenant, workspace, user, client = risk_env
    risk = _create_risk(tenant, workspace, user)
    actor = {"kind": "user", "id": str(user.id)}

    response = client.patch(
        f"/api/v1/risks/{risk.id}/", {"owner": actor}, format="json"
    )

    assert response.status_code == 200, response.content
    risk.refresh_from_db()
    assert risk.owner_name == "Original Text", "owner_name must be untouched"
    assert "{" not in risk.owner_name

    artifact = Artifact.unscoped.get(id=risk.artifact_id)
    assert artifact.owner_id is not None
    assert Actor.unscoped.get(id=artifact.owner_id).user_id == user.id


def test_patch_owner_name_and_actor_owner_together(risk_env) -> None:
    """The primary RiskArtifactForm sends both carriers in one PATCH."""
    tenant, workspace, user, client = risk_env
    risk = _create_risk(tenant, workspace, user)

    response = client.patch(
        f"/api/v1/risks/{risk.id}/",
        {"owner_name": "Grace Hopper", "owner": {"kind": "user", "id": str(user.id)}},
        format="json",
    )

    assert response.status_code == 200, response.content
    risk.refresh_from_db()
    assert risk.owner_name == "Grace Hopper"
    assert "{" not in risk.owner_name
    artifact = Artifact.unscoped.get(id=risk.artifact_id)
    assert artifact.owner_id is not None
