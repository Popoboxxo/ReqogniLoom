"""
REST tests for Task 8 — workspace member assign/suspend/reactivate.

Covers:
- POST /api/v1/workspaces/<workspace_id>/members/            (assign role)
- POST /api/v1/workspaces/<workspace_id>/members/<uid>/suspend/
- POST /api/v1/workspaces/<workspace_id>/members/<uid>/reactivate/
- Cross-tenant IDOR regression: a caller from tenant A must not be able to
  assign a role into a workspace owned by tenant B, even when they hold
  admin/tenant-admin standing in their own tenant A (mirrors the exact class
  of cross-tenant IDOR fixed in Task 7's review for the analogous endpoints).
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_ADMIN, TenantRole, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace


@pytest.fixture
def tenant(db) -> Tenant:
    return Tenant.objects.create(name="WSM-T", slug="wsm-t", is_active=True)


@pytest.fixture
def workspace(tenant: Tenant) -> Workspace:
    set_request_tenant(tenant.id)
    try:
        return Workspace.objects.create(tenant=tenant, name="WSM-WS", preset={"name": "extended"})
    finally:
        clear_request_tenant()


@pytest.fixture
def admin_client(tenant: Tenant, workspace: Workspace) -> APIClient:
    set_request_tenant(tenant.id)
    try:
        user = User.objects.create(username="wsm-admin", email="wsm-admin@t.test", tenant=tenant)
        user.set_password("hunter2pass")
        user.save(update_fields=["password"])
        UserRole.objects.create(tenant=tenant, user=user, workspace=workspace, role=ROLE_ADMIN)
    finally:
        clear_request_tenant()
    client = APIClient()
    login = client.post("/api/v1/auth/login/", {"username": "wsm-admin", "password": "hunter2pass"}, format="json")
    assert login.status_code == 200, login.content
    authed = APIClient()
    authed.credentials(HTTP_AUTHORIZATION=f"Bearer {login.json()['token']}")
    return authed


@pytest.mark.django_db
def test_assign_role_via_rest(admin_client, tenant, workspace):
    set_request_tenant(tenant.id)
    try:
        target = User.objects.create(username="wsm-target", email="wsm-target@t.test", tenant=tenant)
    finally:
        clear_request_tenant()

    resp = admin_client.post(
        f"/api/v1/workspaces/{workspace.id}/members/",
        {"user_id": str(target.id), "role": "editor", "preset": "extended"},
        format="json",
    )
    assert resp.status_code == 201, resp.content

    set_request_tenant(tenant.id)
    try:
        assert UserRole.objects.filter(user=target, workspace=workspace, role="editor").exists()
    finally:
        clear_request_tenant()


@pytest.mark.django_db
def test_suspend_and_reactivate_role_via_rest(admin_client, tenant, workspace):
    set_request_tenant(tenant.id)
    try:
        target = User.objects.create(username="wsm-target2", email="wsm-target2@t.test", tenant=tenant)
        UserRole.objects.create(tenant=tenant, user=target, workspace=workspace, role="editor")
    finally:
        clear_request_tenant()

    suspend = admin_client.post(f"/api/v1/workspaces/{workspace.id}/members/{target.id}/suspend/", {"role": "editor"}, format="json")
    assert suspend.status_code == 200, suspend.content
    set_request_tenant(tenant.id)
    try:
        role = UserRole.objects.get(user=target, workspace=workspace, role="editor")
        assert role.suspended_at is not None
    finally:
        clear_request_tenant()

    reactivate = admin_client.post(f"/api/v1/workspaces/{workspace.id}/members/{target.id}/reactivate/", {"role": "editor"}, format="json")
    assert reactivate.status_code == 200, reactivate.content
    set_request_tenant(tenant.id)
    try:
        role = UserRole.objects.get(user=target, workspace=workspace, role="editor")
        assert role.suspended_at is None
    finally:
        clear_request_tenant()


@pytest.mark.django_db
def test_suspend_blocks_last_workspace_admin(admin_client, tenant, workspace):
    set_request_tenant(tenant.id)
    try:
        admin_user = User.objects.get(username="wsm-admin")
    finally:
        clear_request_tenant()

    resp = admin_client.post(
        f"/api/v1/workspaces/{workspace.id}/members/{admin_user.id}/suspend/", {"role": "admin"}, format="json"
    )
    assert resp.status_code == 409, resp.content
    assert resp.json()["error"] == "LAST_ADMIN"


@pytest.mark.django_db
def test_assign_role_rejects_cross_tenant_workspace(admin_client, tenant, workspace):
    """A tenant-A admin/workspace-admin must not be able to assign a role
    into a workspace that belongs to tenant B (cross-tenant IDOR regression,
    mirrors the class of bug fixed in Task 7's review for analogous
    endpoints). ``AuthorizationService.assign_role`` self-enforces that
    ``workspace_id`` belongs to the caller's own ``tenant_id`` and raises
    ``NotFoundError`` otherwise, which the view maps to 404.
    """
    tenant_b = Tenant.objects.create(name="WSM-T-B", slug="wsm-t-b", is_active=True)
    set_request_tenant(tenant_b.id)
    try:
        workspace_b = Workspace.objects.create(tenant=tenant_b, name="WSM-WS-B", preset={"name": "extended"})
        target_b = User.objects.create(username="wsm-target-b", email="wsm-target-b@t.test", tenant=tenant_b)
    finally:
        clear_request_tenant()

    resp = admin_client.post(
        f"/api/v1/workspaces/{workspace_b.id}/members/",
        {"user_id": str(target_b.id), "role": "editor", "preset": "extended"},
        format="json",
    )
    # NotFoundError from AuthorizationService.assign_role maps to 404; a 403
    # would also be an acceptable deny, but the real, demonstrated behaviour
    # of this exact code path is 404 (workspace not found under the caller's
    # tenant) — assert that explicitly rather than accepting either.
    assert resp.status_code == 404, resp.content

    # Fix round 1 (I-2): query the UNSCOPED manager, not the tenant-scoped
    # `UserRole.objects` under tenant B's context. A corrupted row written
    # with the WRONG tenant_id (tenant_id=A, workspace_id=<tenant B's
    # workspace>) would be invisible to the tenant-scoped manager under
    # either tenant's context, so that assertion would pass even if the
    # vulnerability were still present. `unscoped` sees everything
    # regardless of tenant_id, so it actually guards what this test claims.
    assert not UserRole.unscoped.filter(workspace_id=workspace_b.id, user_id=target_b.id).exists()


@pytest.mark.django_db
def test_assign_role_rejects_spoofed_preset_for_approver(admin_client, tenant, workspace):
    """C-2 regression: a workspace-admin cannot bypass the Approver
    preset gate by lying about ``preset`` in the request body.

    ``workspace`` (see fixture) is created with a REAL preset of
    ``"extended"`` — Approver assignment is allowed there. To exercise the
    spoofing path in the other direction (claim a MORE permissive preset
    than reality to unlock a role reality forbids), this test creates a
    dedicated Standard-tier workspace (``Workspace.preset={"name": "standard"}``
    — the same field ``presets.services.get_preset``'s lazy
    ``WorkspacePresetConfig`` bootstrap reads for the initial tier, per
    ``presets/gate.py``'s ``_get_or_create_preset_config``), then sends
    `"preset": "extended"` in the body while assigning `role="approver"`.
    Approver must be rejected (400) even though the spoofed body value would
    have allowed it — proving the server ignores the client-supplied value
    and resolves the real tier itself.
    """
    set_request_tenant(tenant.id)
    try:
        standard_ws = Workspace.objects.create(
            tenant=tenant, name="WSM-WS-STD", preset={"name": "standard"}
        )
        target = User.objects.create(username="wsm-target-std", email="wsm-target-std@t.test", tenant=tenant)
        # Make the admin caller an admin of this second workspace too, so the
        # RBAC gate passes and the request reaches the preset check.
        admin_user = User.objects.get(username="wsm-admin")
        UserRole.objects.create(tenant=tenant, user=admin_user, workspace=standard_ws, role=ROLE_ADMIN)
    finally:
        clear_request_tenant()

    resp = admin_client.post(
        f"/api/v1/workspaces/{standard_ws.id}/members/",
        {"user_id": str(target.id), "role": "approver", "preset": "extended"},
        format="json",
    )
    assert resp.status_code == 400, resp.content

    set_request_tenant(tenant.id)
    try:
        assert not UserRole.objects.filter(user=target, workspace=standard_ws, role="approver").exists()
    finally:
        clear_request_tenant()


@pytest.mark.django_db
def test_assign_role_denies_non_admin_caller(tenant, workspace):
    """I-3(a): a non-admin (editor) caller gets 403 on assign."""
    set_request_tenant(tenant.id)
    try:
        editor = User.objects.create(username="wsm-editor", email="wsm-editor@t.test", tenant=tenant)
        editor.set_password("hunter2pass")
        editor.save(update_fields=["password"])
        UserRole.objects.create(tenant=tenant, user=editor, workspace=workspace, role="editor")
        target = User.objects.create(username="wsm-target3", email="wsm-target3@t.test", tenant=tenant)
    finally:
        clear_request_tenant()

    client = APIClient()
    login = client.post("/api/v1/auth/login/", {"username": "wsm-editor", "password": "hunter2pass"}, format="json")
    assert login.status_code == 200, login.content
    authed = APIClient()
    authed.credentials(HTTP_AUTHORIZATION=f"Bearer {login.json()['token']}")

    resp = authed.post(
        f"/api/v1/workspaces/{workspace.id}/members/",
        {"user_id": str(target.id), "role": "editor", "preset": "extended"},
        format="json",
    )
    assert resp.status_code == 403, resp.content


@pytest.mark.django_db
def test_suspend_denies_non_admin_caller(tenant, workspace):
    """I-3(a): a non-admin (editor) caller gets 403 on suspend."""
    set_request_tenant(tenant.id)
    try:
        editor = User.objects.create(username="wsm-editor2", email="wsm-editor2@t.test", tenant=tenant)
        editor.set_password("hunter2pass")
        editor.save(update_fields=["password"])
        UserRole.objects.create(tenant=tenant, user=editor, workspace=workspace, role="editor")
        target = User.objects.create(username="wsm-target4", email="wsm-target4@t.test", tenant=tenant)
        UserRole.objects.create(tenant=tenant, user=target, workspace=workspace, role="editor")
    finally:
        clear_request_tenant()

    client = APIClient()
    login = client.post("/api/v1/auth/login/", {"username": "wsm-editor2", "password": "hunter2pass"}, format="json")
    assert login.status_code == 200, login.content
    authed = APIClient()
    authed.credentials(HTTP_AUTHORIZATION=f"Bearer {login.json()['token']}")

    resp = authed.post(
        f"/api/v1/workspaces/{workspace.id}/members/{target.id}/suspend/", {"role": "editor"}, format="json"
    )
    assert resp.status_code == 403, resp.content


@pytest.mark.django_db
def test_suspend_rejects_cross_tenant_workspace(admin_client, tenant, workspace):
    """I-3(b): a tenant-A caller cannot suspend a role in a tenant-B workspace."""
    tenant_b = Tenant.objects.create(name="WSM-T-B-S", slug="wsm-t-b-s", is_active=True)
    set_request_tenant(tenant_b.id)
    try:
        workspace_b = Workspace.objects.create(tenant=tenant_b, name="WSM-WS-B-S", preset={"name": "extended"})
        target_b = User.objects.create(username="wsm-target-b-s", email="wsm-target-b-s@t.test", tenant=tenant_b)
        UserRole.objects.create(tenant=tenant_b, user=target_b, workspace=workspace_b, role="editor")
    finally:
        clear_request_tenant()

    resp = admin_client.post(
        f"/api/v1/workspaces/{workspace_b.id}/members/{target_b.id}/suspend/", {"role": "editor"}, format="json"
    )
    assert resp.status_code == 404, resp.content

    role = UserRole.unscoped.get(user_id=target_b.id, workspace_id=workspace_b.id, role="editor")
    assert role.suspended_at is None


@pytest.mark.django_db
def test_reactivate_rejects_cross_tenant_workspace(admin_client, tenant, workspace):
    """I-3(b): a tenant-A caller cannot reactivate a role in a tenant-B workspace."""
    tenant_b = Tenant.objects.create(name="WSM-T-B-R", slug="wsm-t-b-r", is_active=True)
    set_request_tenant(tenant_b.id)
    try:
        workspace_b = Workspace.objects.create(tenant=tenant_b, name="WSM-WS-B-R", preset={"name": "extended"})
        target_b = User.objects.create(username="wsm-target-b-r", email="wsm-target-b-r@t.test", tenant=tenant_b)
        UserRole.objects.create(
            tenant=tenant_b,
            user=target_b,
            workspace=workspace_b,
            role="editor",
            suspended_at=datetime.now(timezone.utc),
        )
    finally:
        clear_request_tenant()

    resp = admin_client.post(
        f"/api/v1/workspaces/{workspace_b.id}/members/{target_b.id}/reactivate/", {"role": "editor"}, format="json"
    )
    assert resp.status_code == 404, resp.content

    role = UserRole.unscoped.get(user_id=target_b.id, workspace_id=workspace_b.id, role="editor")
    assert role.suspended_at is not None


@pytest.mark.django_db
def test_suspend_already_suspended_role_is_noop_200(admin_client, tenant, workspace):
    """I-3(c): suspending an already-suspended role returns 200 (no-op)."""
    set_request_tenant(tenant.id)
    try:
        target = User.objects.create(username="wsm-target5", email="wsm-target5@t.test", tenant=tenant)
        UserRole.objects.create(
            tenant=tenant,
            user=target,
            workspace=workspace,
            role="editor",
            suspended_at=datetime.now(timezone.utc),
        )
    finally:
        clear_request_tenant()

    resp = admin_client.post(
        f"/api/v1/workspaces/{workspace.id}/members/{target.id}/suspend/", {"role": "editor"}, format="json"
    )
    assert resp.status_code == 200, resp.content


@pytest.mark.django_db
def test_reactivate_already_active_role_is_noop_200(admin_client, tenant, workspace):
    """I-3(c): reactivating an already-active role returns 200 (no-op)."""
    set_request_tenant(tenant.id)
    try:
        target = User.objects.create(username="wsm-target6", email="wsm-target6@t.test", tenant=tenant)
        UserRole.objects.create(tenant=tenant, user=target, workspace=workspace, role="editor")
    finally:
        clear_request_tenant()

    resp = admin_client.post(
        f"/api/v1/workspaces/{workspace.id}/members/{target.id}/reactivate/", {"role": "editor"}, format="json"
    )
    assert resp.status_code == 200, resp.content


@pytest.mark.django_db
def test_suspend_nonexistent_role_assignment_returns_404(admin_client, tenant, workspace):
    """I-3(d): suspending a role assignment that genuinely doesn't exist -> 404."""
    set_request_tenant(tenant.id)
    try:
        target = User.objects.create(username="wsm-target7", email="wsm-target7@t.test", tenant=tenant)
    finally:
        clear_request_tenant()

    resp = admin_client.post(
        f"/api/v1/workspaces/{workspace.id}/members/{target.id}/suspend/", {"role": "editor"}, format="json"
    )
    assert resp.status_code == 404, resp.content


@pytest.mark.django_db
def test_reactivate_nonexistent_role_assignment_returns_404(admin_client, tenant, workspace):
    """I-3(d): reactivating a role assignment that genuinely doesn't exist -> 404."""
    set_request_tenant(tenant.id)
    try:
        target = User.objects.create(username="wsm-target8", email="wsm-target8@t.test", tenant=tenant)
    finally:
        clear_request_tenant()

    resp = admin_client.post(
        f"/api/v1/workspaces/{workspace.id}/members/{target.id}/reactivate/", {"role": "editor"}, format="json"
    )
    assert resp.status_code == 404, resp.content


# ---------------------------------------------------------------------------
# Fix Round 2 — Task A: SEC-05 first-admin-bootstrap scope pinning
#
# The re-review confirmed (and the controller ruled acceptable/intentional)
# that a role-less-in-that-workspace but authenticated-in-the-tenant caller
# can self-assign admin in a workspace with zero active admins, via REST,
# for the first time. This is NOT a bug to fix — these tests only pin the
# CORRECT, NARROW scope of that behaviour so it can't silently widen later.
# ---------------------------------------------------------------------------


@pytest.fixture
def admin_less_workspace(tenant: Tenant) -> Workspace:
    """A workspace in ``tenant`` with ZERO active admin ``UserRole`` rows."""
    set_request_tenant(tenant.id)
    try:
        return Workspace.objects.create(
            tenant=tenant, name="WSM-WS-NOADMIN", preset={"name": "extended"}
        )
    finally:
        clear_request_tenant()


@pytest.fixture
def roleless_client(tenant: Tenant):
    """An authenticated caller with NO ``UserRole`` and NO ``TenantRole``
    anywhere. Returns ``(authenticated APIClient, User)``.
    """
    set_request_tenant(tenant.id)
    try:
        user = User.objects.create(
            username="wsm-roleless", email="wsm-roleless@t.test", tenant=tenant
        )
        user.set_password("hunter2pass")
        user.save(update_fields=["password"])
    finally:
        clear_request_tenant()
    client = APIClient()
    login = client.post(
        "/api/v1/auth/login/", {"username": "wsm-roleless", "password": "hunter2pass"}, format="json"
    )
    assert login.status_code == 200, login.content
    authed = APIClient()
    authed.credentials(HTTP_AUTHORIZATION=f"Bearer {login.json()['token']}")
    return authed, user


@pytest.mark.django_db
def test_sec05_bootstrap_allows_self_assign_admin_in_own_tenant_admin_less_workspace(
    roleless_client, tenant, admin_less_workspace
):
    """SEC-05 pinning: the intended, accepted case. A role-less-everywhere
    caller CAN self-assign ``admin`` in a workspace of THEIR OWN tenant that
    has zero active admins. Fix round 2 leaves this branch untouched — this
    test only pins its scope.
    """
    authed, user = roleless_client
    resp = authed.post(
        f"/api/v1/workspaces/{admin_less_workspace.id}/members/",
        {"user_id": str(user.id), "role": "admin"},
        format="json",
    )
    assert resp.status_code == 201, resp.content
    set_request_tenant(tenant.id)
    try:
        assert UserRole.objects.filter(
            user=user, workspace=admin_less_workspace, role="admin", suspended_at__isnull=True
        ).exists()
    finally:
        clear_request_tenant()


@pytest.mark.django_db
def test_sec05_bootstrap_rejects_different_tenant_workspace(roleless_client, tenant):
    """SEC-05 pinning: the SAME caller CANNOT bootstrap-self-assign admin in
    a workspace of a DIFFERENT tenant (even one with zero admins there too).
    """
    authed, user = roleless_client
    tenant_b = Tenant.objects.create(name="WSM-SEC05-B", slug="wsm-sec05-b", is_active=True)
    set_request_tenant(tenant_b.id)
    try:
        workspace_b = Workspace.objects.create(
            tenant=tenant_b, name="WSM-SEC05-WS-B", preset={"name": "extended"}
        )
    finally:
        clear_request_tenant()

    resp = authed.post(
        f"/api/v1/workspaces/{workspace_b.id}/members/",
        {"user_id": str(user.id), "role": "admin"},
        format="json",
    )
    # Matches this file's existing cross-tenant precedent
    # (test_assign_role_rejects_cross_tenant_workspace): the tenant-scoped
    # bootstrap existence check technically passes (workspace_b's rows are
    # invisible under the caller's own tenant scope), but assign_role's own
    # workspace-belongs-to-tenant check catches it and raises
    # NotFoundError -> 404.
    assert resp.status_code == 404, resp.content
    assert not UserRole.unscoped.filter(workspace_id=workspace_b.id, user_id=user.id).exists()


@pytest.mark.django_db
def test_sec05_bootstrap_rejects_when_workspace_already_has_admin(roleless_client, tenant, workspace):
    """SEC-05 pinning: the SAME caller CANNOT bootstrap-self-assign admin in
    a workspace of their own tenant that already HAS an active admin —
    exercises ``is_first_admin_bootstrap``'s
    ``not UserRole.objects.filter(...).exists()`` condition.

    Creates its own active admin directly (does NOT rely on the
    ``admin_client`` fixture's side effect — that fixture is not requested
    here, so its ``UserRole(admin)`` creation would never run).
    """
    authed, user = roleless_client
    set_request_tenant(tenant.id)
    try:
        existing_admin = User.objects.create(
            username="wsm-existing-admin", email="wsm-existing-admin@t.test", tenant=tenant
        )
        UserRole.objects.create(tenant=tenant, user=existing_admin, workspace=workspace, role=ROLE_ADMIN)
    finally:
        clear_request_tenant()

    resp = authed.post(
        f"/api/v1/workspaces/{workspace.id}/members/",
        {"user_id": str(user.id), "role": "admin"},
        format="json",
    )
    assert resp.status_code == 403, resp.content
    set_request_tenant(tenant.id)
    try:
        assert not UserRole.objects.filter(user=user, workspace=workspace, role="admin").exists()
    finally:
        clear_request_tenant()


@pytest.mark.django_db
def test_sec05_bootstrap_rejects_non_admin_role(roleless_client, tenant, admin_less_workspace):
    """SEC-05 pinning: the SAME caller CANNOT self-assign a role OTHER than
    ``admin`` (e.g. ``editor``) via this bootstrap path in an admin-less
    workspace — bootstrap only ever applies to ``role="admin"``.
    """
    authed, user = roleless_client
    resp = authed.post(
        f"/api/v1/workspaces/{admin_less_workspace.id}/members/",
        {"user_id": str(user.id), "role": "editor"},
        format="json",
    )
    assert resp.status_code == 403, resp.content
    set_request_tenant(tenant.id)
    try:
        assert not UserRole.objects.filter(
            user=user, workspace=admin_less_workspace, role="editor"
        ).exists()
    finally:
        clear_request_tenant()


@pytest.mark.django_db
def test_sec05_bootstrap_rejects_assigning_admin_to_a_different_user(
    roleless_client, tenant, admin_less_workspace
):
    """SEC-05 pinning: the SAME caller CANNOT assign ``admin`` to a
    DIFFERENT user via this bootstrap path — bootstrap requires
    ``target_user_id == assigned_by_user_id`` (self-assignment only).
    """
    authed, user = roleless_client
    set_request_tenant(tenant.id)
    try:
        other = User.objects.create(
            username="wsm-other-target", email="wsm-other-target@t.test", tenant=tenant
        )
    finally:
        clear_request_tenant()

    resp = authed.post(
        f"/api/v1/workspaces/{admin_less_workspace.id}/members/",
        {"user_id": str(other.id), "role": "admin"},
        format="json",
    )
    assert resp.status_code == 403, resp.content
    set_request_tenant(tenant.id)
    try:
        assert not UserRole.objects.filter(
            user=other, workspace=admin_less_workspace, role="admin"
        ).exists()
    finally:
        clear_request_tenant()


# ---------------------------------------------------------------------------
# Fix Round 2 — Task D: remaining small test-coverage gaps
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_reactivate_denies_non_admin_caller(tenant, workspace):
    """Task D(1): ``reactivate`` had no non-admin-403 test yet (``assign``
    and ``suspend`` already did) — matches the existing pattern.
    """
    set_request_tenant(tenant.id)
    try:
        editor = User.objects.create(username="wsm-editor3", email="wsm-editor3@t.test", tenant=tenant)
        editor.set_password("hunter2pass")
        editor.save(update_fields=["password"])
        UserRole.objects.create(tenant=tenant, user=editor, workspace=workspace, role="editor")
        target = User.objects.create(username="wsm-target9", email="wsm-target9@t.test", tenant=tenant)
        UserRole.objects.create(
            tenant=tenant,
            user=target,
            workspace=workspace,
            role="editor",
            suspended_at=datetime.now(timezone.utc),
        )
    finally:
        clear_request_tenant()

    client = APIClient()
    login = client.post("/api/v1/auth/login/", {"username": "wsm-editor3", "password": "hunter2pass"}, format="json")
    assert login.status_code == 200, login.content
    authed = APIClient()
    authed.credentials(HTTP_AUTHORIZATION=f"Bearer {login.json()['token']}")

    resp = authed.post(
        f"/api/v1/workspaces/{workspace.id}/members/{target.id}/reactivate/", {"role": "editor"}, format="json"
    )
    assert resp.status_code == 403, resp.content
    set_request_tenant(tenant.id)
    try:
        role = UserRole.objects.get(user=target, workspace=workspace, role="editor")
        assert role.suspended_at is not None  # untouched by the denied request
    finally:
        clear_request_tenant()


@pytest.mark.django_db
def test_suspend_nonexistent_admin_role_assignment_returns_404(tenant, admin_less_workspace):
    """Task D(2): I-1's existing 404 regression test only ever exercised
    ``role="editor"``, which never reaches
    ``_assert_not_last_workspace_admin`` at all (only ``role="admin"``
    does) — so it never actually exercised the reordering I-1 fixed.

    Uses a workspace with ZERO active admin ``UserRole`` rows (so, without
    I-1's fix, ``_assert_not_last_workspace_admin`` would see zero locked
    admin rows and misfire ``LastAdminError`` / 409) and a tenant-admin
    caller (so the request passes the admin gate without the workspace
    itself needing a ``UserRole(admin)`` row). Suspending ``role="admin"``
    for a target who was never assigned it must return 404, not 409.
    """
    set_request_tenant(tenant.id)
    try:
        tenant_admin_user = User.objects.create(
            username="wsm-tadmin", email="wsm-tadmin@t.test", tenant=tenant
        )
        tenant_admin_user.set_password("hunter2pass")
        tenant_admin_user.save(update_fields=["password"])
        TenantRole.objects.create(
            tenant=tenant, user=tenant_admin_user, role=TenantRole.ROLE_ADMIN
        )
        target = User.objects.create(
            username="wsm-target-noadmin", email="wsm-target-noadmin@t.test", tenant=tenant
        )
    finally:
        clear_request_tenant()

    client = APIClient()
    login = client.post("/api/v1/auth/login/", {"username": "wsm-tadmin", "password": "hunter2pass"}, format="json")
    assert login.status_code == 200, login.content
    authed = APIClient()
    authed.credentials(HTTP_AUTHORIZATION=f"Bearer {login.json()['token']}")

    resp = authed.post(
        f"/api/v1/workspaces/{admin_less_workspace.id}/members/{target.id}/suspend/",
        {"role": "admin"},
        format="json",
    )
    assert resp.status_code == 404, resp.content
    assert resp.json()["error"] == "NOT_FOUND"
