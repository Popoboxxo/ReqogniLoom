"""REST-level regression coverage for workspace deletion (GitHub #265).

Two defects are covered here:

* **A** — ``POST /api/v1/workspaces/{id}/delete/`` with the *correct*
  confirmation string returned ``500`` and left the workspace in place, even
  though the confirmation check itself worked (a wrong string cleanly 409s).
* **B** — the generic DRF ``DELETE /api/v1/workspaces/{id}/`` verb answered
  ``204 No Content`` without deleting anything, faking success to clients.

leaf_id : COMP-RA-WS (WorkspaceViewSet)
req_id  : REQ-L1-042 / GitHub #265
"""
from __future__ import annotations

import uuid

import pytest
from rest_framework.test import APIClient

from audit.models import AuditEntry
from auth_tenancy.models import ROLE_ADMIN, UserRole
from auth_tenancy.rest import ACCESS_COOKIE_NAME
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Artifact, Tenant, User, Workspace

pytestmark = pytest.mark.django_db

_PASSWORD = "hunter2pass"


def _tenant_user_workspace(name: str) -> tuple[Tenant, User, Workspace]:
    slug = f"wsdel-{uuid.uuid4().hex[:8]}"
    tenant = Tenant.objects.create(name=f"T-{slug}", slug=slug, is_active=True)
    user = User.objects.create(
        username=f"user-{slug}", email=f"{slug}@t.test", tenant=tenant
    )
    user.set_password(_PASSWORD)
    user.save(update_fields=["password"])

    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name=name, preset={"name": "extended"}
        )
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=workspace, role=ROLE_ADMIN
        )
    finally:
        clear_request_tenant()
    return tenant, user, workspace


def _client(user: User) -> APIClient:
    client = APIClient()
    resp = client.post(
        "/api/v1/auth/login/",
        {"username": user.username, "password": _PASSWORD},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    assert ACCESS_COOKIE_NAME in client.cookies
    return client


def _exists(workspace: Workspace) -> bool:
    return Workspace.unscoped.filter(pk=workspace.pk).exists()


# ---------------------------------------------------------------------------
# Befund A — POST /delete/ with a correct confirmation
# ---------------------------------------------------------------------------


def test_post_delete_with_correct_confirmation_deletes_workspace() -> None:
    """#265 A: correct confirmation must actually delete and never 500."""
    _, user, workspace = _tenant_user_workspace("Delete Me A")
    client = _client(user)

    resp = client.post(
        f"/api/v1/workspaces/{workspace.id}/delete/",
        {"confirmation": "Delete Me A"},
        format="json",
    )

    assert resp.status_code in (200, 204), (
        f"expected 200/204 but got {resp.status_code}: {resp.content!r}"
    )
    assert not _exists(workspace), "workspace still present after a successful delete"
    # The 500 originated in the audit write, so assert the entry really landed.
    assert AuditEntry.unscoped.filter(
        op="workspace.delete", entity_id=workspace.id
    ).exists(), "no audit entry written for the deletion"


def test_post_delete_with_content_deletes_workspace_and_artifacts() -> None:
    """#265 A: a non-empty workspace must cascade, not blow up."""
    tenant, user, workspace = _tenant_user_workspace("Delete Me Full")
    set_request_tenant(tenant.id)
    try:
        artifact = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="generic"
        )
    finally:
        clear_request_tenant()
    client = _client(user)

    resp = client.post(
        f"/api/v1/workspaces/{workspace.id}/delete/",
        {"confirmation": "Delete Me Full"},
        format="json",
    )

    assert resp.status_code in (200, 204), (
        f"expected 200/204 but got {resp.status_code}: {resp.content!r}"
    )
    assert not _exists(workspace)
    assert not Artifact.unscoped.filter(pk=artifact.pk).exists()


def test_post_delete_of_a_realistic_workspace_succeeds() -> None:
    """#265 A: a workspace with the rows a real one accumulates must delete.

    The original 500 was masked in the service tests because they all patch
    ``ServiceBase._audit`` and delete near-empty workspaces. This one goes
    through REST with needs/requirements/roles/permissions attached, which is
    what the reporter actually had.
    """
    tenant, user, workspace = _tenant_user_workspace("Realistic WS")
    client = _client(user)

    need = client.post(
        f"/api/v1/workspaces/{workspace.id}/needs/",
        {"title": "a stakeholder need"},
        format="json",
    )
    assert need.status_code == 201, need.content
    req = client.post(
        "/api/v1/requirements/",
        {"workspace_id": str(workspace.id), "title": "a requirement"},
        format="json",
    )
    assert req.status_code == 201, req.content

    resp = client.post(
        f"/api/v1/workspaces/{workspace.id}/delete/",
        {"confirmation": "Realistic WS"},
        format="json",
    )

    assert resp.status_code in (200, 204), (
        f"expected 200/204 but got {resp.status_code}: {resp.content!r}"
    )
    assert not _exists(workspace)
    assert not UserRole.unscoped.filter(workspace_id=workspace.id).exists()


def test_post_delete_with_wrong_confirmation_returns_409() -> None:
    """Regression guard: the working half of the endpoint must stay working."""
    _, user, workspace = _tenant_user_workspace("Keep Me")
    client = _client(user)

    resp = client.post(
        f"/api/v1/workspaces/{workspace.id}/delete/",
        {"confirmation": "wrong"},
        format="json",
    )

    assert resp.status_code == 409, resp.content
    assert _exists(workspace)


def test_post_delete_without_confirmation_returns_400() -> None:
    """Regression guard: a missing confirmation is a 400, workspace untouched."""
    _, user, workspace = _tenant_user_workspace("Keep Me 400")
    client = _client(user)

    resp = client.post(
        f"/api/v1/workspaces/{workspace.id}/delete/", {}, format="json"
    )

    assert resp.status_code == 400, resp.content
    assert _exists(workspace)


# ---------------------------------------------------------------------------
# Befund B — the generic DELETE verb
# ---------------------------------------------------------------------------


def test_delete_verb_without_confirmation_is_never_a_silent_success() -> None:
    """#265 B: DELETE without confirmation must not answer 204 as a no-op."""
    _, user, workspace = _tenant_user_workspace("Silent No-Op")
    client = _client(user)

    resp = client.delete(f"/api/v1/workspaces/{workspace.id}/")

    assert resp.status_code == 400, (
        f"DELETE without confirmation must be rejected, got {resp.status_code}: "
        f"{resp.content!r}"
    )
    assert _exists(workspace), "workspace vanished without a confirmation"

    # ... and it must still be a fully usable workspace, not half-mutated.
    get_resp = client.get(f"/api/v1/workspaces/{workspace.id}/")
    assert get_resp.status_code == 200, get_resp.content
    assert get_resp.data["is_active"] is True


def test_delete_verb_with_wrong_confirmation_returns_409() -> None:
    """#265 B: DELETE shares the captcha semantics of POST /delete/."""
    _, user, workspace = _tenant_user_workspace("Keep Me B")
    client = _client(user)

    resp = client.delete(
        f"/api/v1/workspaces/{workspace.id}/",
        {"confirmation": "wrong"},
        format="json",
    )

    assert resp.status_code == 409, resp.content
    assert _exists(workspace)


def test_delete_verb_with_correct_confirmation_matches_post_delete() -> None:
    """#265 B: if DELETE carries the confirmation it behaves like POST /delete/."""
    _, user, workspace = _tenant_user_workspace("Delete Me B")
    client = _client(user)

    resp = client.delete(
        f"/api/v1/workspaces/{workspace.id}/",
        {"confirmation": "Delete Me B"},
        format="json",
    )

    assert resp.status_code == 204, resp.content
    assert not _exists(workspace)


def test_soft_close_remains_available_via_post_close() -> None:
    """#265 B: the reversible operation DELETE used to perform still exists."""
    _, user, workspace = _tenant_user_workspace("Close Me")
    client = _client(user)

    resp = client.post(f"/api/v1/workspaces/{workspace.id}/close/", {}, format="json")

    assert resp.status_code == 200, resp.content
    assert resp.data["is_active"] is False
    assert _exists(workspace)
