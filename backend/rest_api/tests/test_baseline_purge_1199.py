"""GH-1199 — REST contract: baseline immutability vs. administrative purge.

Pins the two halves of the contradiction this issue is about:

* ``DELETE /api/v1/baselines/{id}/`` is a *domain* prohibition. It answers 403
  with the dedicated code ``BASELINE_IMMUTABLE`` — never the generic
  ``PERMISSION_DENIED``, which used to make "nobody may delete this" look like
  "you personally lack the role". The message names the one real removal path
  and must not tell the caller to "remove them first" (that was impossible:
  no route could remove a baseline).
* ``DELETE /api/v1/baselines/{id}/purge/`` is that path: admin-only, audited
  (``operation="baseline.purge"``), and it actually removes the row via the
  transaction-local GUC from migration ``0011`` (never ``DISABLE TRIGGER``).

This is the REST-level counterpart of the Layer-1 coverage in
``baseline/tests/test_admin_purge_1199.py``.
"""
from __future__ import annotations

import uuid

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from audit.models import AuditEntry
from auth_tenancy.models import ROLE_ADMIN, ROLE_EDITOR, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Artifact, Tenant, User, Workspace

pytestmark = pytest.mark.django_db

_PASSWORD = "purge1199pass"

_JWT_OVERRIDES = dict(
    AUTH_JWT_SECRET="test-secret-not-a-real-key",
    AUTH_JWT_ISSUER="reqflow",
    AUTH_JWT_AUDIENCE="reqflow-api",
    AUTH_JWT_TTL_SECONDS=3600,
)


def _env(role: str = ROLE_ADMIN) -> tuple[Tenant, User, Workspace]:
    """Create tenant + user(role) + extended-preset workspace."""
    slug = f"purge1199-{uuid.uuid4().hex[:8]}"
    tenant = Tenant.objects.create(name=f"T-{slug}", slug=slug, is_active=True)
    user = User.objects.create(
        username=f"user-{slug}", email=f"{slug}@t.test", tenant=tenant
    )
    user.set_password(_PASSWORD)
    user.save(update_fields=["password"])
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name=f"WS-{slug}", preset={"name": "extended"}
        )
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=workspace, role=role
        )
    finally:
        clear_request_tenant()
    return tenant, user, workspace


def _client(user: User) -> APIClient:
    client = APIClient()
    with override_settings(**_JWT_OVERRIDES):
        login = client.post(
            "/api/v1/auth/login/",
            {"username": user.username, "password": _PASSWORD},
            format="json",
        )
    assert login.status_code == 200, login.content
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.json()['token']}")
    return client


def _two_workspace_env(
    admin_workspace: str = "A",
) -> tuple[Tenant, User, Workspace, Workspace]:
    """Tenant + user with ``admin`` in exactly one of two workspaces.

    ``admin_workspace`` selects which of the two workspaces the role is attached
    to (``"A"`` or ``"B"``); the other workspace holds no role for the user.
    Used by the cross-workspace purge regression (review B1).
    """
    slug = f"purge1199x-{uuid.uuid4().hex[:8]}"
    tenant = Tenant.objects.create(name=f"T-{slug}", slug=slug, is_active=True)
    user = User.objects.create(
        username=f"user-{slug}", email=f"{slug}@t.test", tenant=tenant
    )
    user.set_password(_PASSWORD)
    user.save(update_fields=["password"])
    set_request_tenant(tenant.id)
    try:
        ws_a = Workspace.objects.create(
            tenant=tenant, name=f"WS-A-{slug}", preset={"name": "extended"}
        )
        ws_b = Workspace.objects.create(
            tenant=tenant, name=f"WS-B-{slug}", preset={"name": "extended"}
        )
        admin_ws = ws_a if admin_workspace == "A" else ws_b
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=admin_ws, role=ROLE_ADMIN
        )
    finally:
        clear_request_tenant()
    return tenant, user, ws_a, ws_b


def _baseline(tenant: Tenant, workspace: Workspace) -> str:
    """Insert one baseline straight through the unscoped manager (INSERT is
    unaffected by the DELETE/UPDATE immutability trigger) and return its id."""
    from baseline.models import BaselineSnapshot

    set_request_tenant(tenant.id)
    try:
        artifact = Artifact.unscoped.create(
            workspace=workspace, artifact_type="generic", tenant=tenant
        )
        snapshot = BaselineSnapshot.unscoped.create(
            workspace_id=workspace.id,
            name=f"bl-{uuid.uuid4().hex[:8]}",
            scope="document",
            artifact=artifact,
            tenant=tenant,
        )
        return str(snapshot.id)
    finally:
        clear_request_tenant()


# ---------------------------------------------------------------------------
# Generic DELETE — domain prohibition, dedicated code, real path
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
def test_plain_delete_is_refused_with_the_dedicated_code() -> None:
    tenant, user, workspace = _env()
    baseline_id = _baseline(tenant, workspace)
    client = _client(user)

    response = client.delete(f"/api/v1/baselines/{baseline_id}/")

    assert response.status_code == 403, response.content
    body = response.json()
    assert body["error"]["code"] == "BASELINE_IMMUTABLE", body


@override_settings(**_JWT_OVERRIDES)
def test_plain_delete_message_has_no_dead_end_and_names_the_admin_route() -> None:
    """#1199 requirement 1: the old "remove them first" was a dead end."""
    tenant, user, workspace = _env()
    baseline_id = _baseline(tenant, workspace)
    client = _client(user)

    response = client.delete(f"/api/v1/baselines/{baseline_id}/")

    assert response.status_code == 403, response.content
    message = response.json()["error"]["message"].lower()
    assert "remove them first" not in message, message
    assert "purge" in message, message


# ---------------------------------------------------------------------------
# Administrative purge — the one sanctioned removal path
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
def test_admin_purge_removes_the_baseline_and_writes_an_audit_entry() -> None:
    from baseline.models import BaselineSnapshot

    tenant, user, workspace = _env(ROLE_ADMIN)
    baseline_id = _baseline(tenant, workspace)
    client = _client(user)

    response = client.delete(f"/api/v1/baselines/{baseline_id}/purge/")

    assert response.status_code == 204, response.content
    assert not BaselineSnapshot.unscoped.filter(pk=baseline_id).exists()
    assert AuditEntry.unscoped.filter(
        op="baseline.purge", entity_id=baseline_id
    ).exists(), "purge must leave an audit trail"


@override_settings(**_JWT_OVERRIDES)
def test_purge_by_non_admin_is_403_and_keeps_the_baseline() -> None:
    """An editor reaches the route through the RBAC WRITE mapping but the
    facade's admin assertion must still deny — and change nothing."""
    from baseline.models import BaselineSnapshot

    tenant, user, workspace = _env(ROLE_EDITOR)
    baseline_id = _baseline(tenant, workspace)
    client = _client(user)

    response = client.delete(f"/api/v1/baselines/{baseline_id}/purge/")

    assert response.status_code == 403, response.content
    assert BaselineSnapshot.unscoped.filter(pk=baseline_id).exists()


@override_settings(**_JWT_OVERRIDES)
def test_purge_of_an_unknown_baseline_is_404() -> None:
    _, user, _workspace = _env(ROLE_ADMIN)
    client = _client(user)

    response = client.delete(f"/api/v1/baselines/{uuid.uuid4()}/purge/")

    assert response.status_code == 404, response.content


# ---------------------------------------------------------------------------
# Review B1 — the purge gate must be scoped to the baseline's own workspace.
#
# The purge route carries no ``workspace_id`` in its URL, so a naive gate on
# ``ctx.active_roles`` sees the tenant-wide role union: an ``admin`` in any one
# workspace could then purge a baseline of a *different* workspace in the same
# tenant. The facade must assert admin against the baseline's workspace.
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
def test_admin_of_workspace_a_cannot_purge_workspace_b_baseline() -> None:
    from baseline.models import BaselineSnapshot

    tenant, user, _ws_a, ws_b = _two_workspace_env(admin_workspace="A")
    baseline_b = _baseline(tenant, ws_b)
    client = _client(user)

    response = client.delete(f"/api/v1/baselines/{baseline_b}/purge/")

    assert response.status_code == 403, response.content
    assert BaselineSnapshot.unscoped.filter(pk=baseline_b).exists(), (
        "a workspace-A admin must not remove a workspace-B baseline"
    )


@override_settings(**_JWT_OVERRIDES)
def test_admin_of_the_baselines_own_workspace_still_succeeds() -> None:
    """The scoped gate must not lock out the legitimate same-workspace admin."""
    from baseline.models import BaselineSnapshot

    tenant, user, _ws_a, ws_b = _two_workspace_env(admin_workspace="B")
    baseline_b = _baseline(tenant, ws_b)
    client = _client(user)

    response = client.delete(f"/api/v1/baselines/{baseline_b}/purge/")

    assert response.status_code == 204, response.content
    assert not BaselineSnapshot.unscoped.filter(pk=baseline_b).exists()
