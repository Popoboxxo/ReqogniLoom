"""Performance-budget tests for the MCP server.

These tests are marked ``@pytest.mark.slow`` and exercise the end-to-end
HTTP path with a realistic load. Use ``pytest -m "not slow"`` to skip
them in fast CI runs.

The budgets are intentionally generous (seconds, not milliseconds)
because the test runs against a synchronous Django test client that
boots a fresh DB transaction per test. They are meant to catch severe
regressions (e.g. accidental N+1 queries that turn a 50-row response
into 500-row response), not to enforce absolute production SLAs.
"""
from __future__ import annotations

import time
from uuid import uuid4

import pytest

from application.services import RequirementService
from audit.models import AuditEntry
from auth_tenancy.context import AuthContext, AuthMethod
from auth_tenancy.models import (
    ITEM_PERMISSION_READ,
    ROLE_ADMIN,
    ItemPermission,
)
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User

# Fixtures below are auto-loaded from conftest.py; re-imported here
# so type checkers and IDEs see them as fixture references.
from mcp_server.tests.conftest import (  # noqa: F401
    admin_client,
    e2e_api_key_admin,
    e2e_preset,
    e2e_tenant,
    e2e_user_admin,
    e2e_user_member,
    e2e_userrole_admin,
    e2e_workspace,
)
from mcp_server.tests.helpers import extract_result, post_mcp

# SYSTEMAUDIT SA-62: classification marker for the `test_e2e_*.py` family —
# see the `e2e` marker docstring in pyproject.toml. Composes with the
# per-test `@pytest.mark.slow` below (module-level pytestmark + function
# decorators both apply).
pytestmark = pytest.mark.e2e


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _admin_auth_context(workspace, user_id) -> AuthContext:
    """Build an admin AuthContext suitable for seeding via service APIs.

    The ``tenant_id`` is taken from the workspace (same as the e2e tenant).
    The ``active_roles`` tuple is exactly ``("admin",)`` because
    ``ServiceBase._assert_write_permission`` only blocks the
    single-role viewer case, but the ItemPermission service additionally
    requires the explicit ``admin`` role.
    """
    return AuthContext(
        user_id=user_id,
        tenant_id=workspace.tenant_id,
        active_roles=(ROLE_ADMIN,),
        auth_method=AuthMethod.API_KEY,
    )


def _seed_audit_entry_bulk(workspace, user, count: int) -> None:
    """Insert ``count`` AuditEntry rows directly via the unscoped model.

    Bypasses the ``log_write`` path (which would do a Tenant.objects.get
    per call) because the seed step is not what we are measuring. The
    resulting rows are indistinguishable from real ones for the
    ``audit.query`` read path: same columns, same tenant scope, same
    index layout.
    """
    set_request_tenant(workspace.tenant_id)
    try:
        tenant = Tenant.objects.get(pk=workspace.tenant_id)
        for _ in range(count):
            entry = AuditEntry(
                tenant=tenant,
                actor=str(user.id),
                actor_type=AuditEntry.ACTOR_TYPE_USER,
                op=AuditEntry.OP_CREATE,
                entity_type="Requirement",
                entity_id=uuid4(),
                source=AuditEntry.SOURCE_REST,
            )
            # Bypass the AppendOnlyManager save guard (pk is None).
            AuditEntry.unscoped.model.save(entry)
    finally:
        clear_request_tenant()


# ---------------------------------------------------------------------------
# requirement.query — 100 requirements
# ---------------------------------------------------------------------------


@pytest.mark.slow
@pytest.mark.django_db(transaction=True)
def test_requirement_query_with_100_requirements_under_2s(
    admin_client,
    e2e_workspace,
    e2e_user_admin,
    e2e_userrole_admin,
):
    """100 Requirements: query must complete in < 2s.

    ``e2e_userrole_admin`` is required, not incidental: since Systemaudit
    2026-08-29 §6.5 a workspace-scoped read needs an active ``UserRole`` in
    that workspace. ``admin_client`` alone only carries the tenant-wide
    ``TenantRole(admin)``, which — exactly as on the REST path — does not by
    itself grant access to a workspace's contents. The three sibling
    perf tests already requested this fixture; this one did not.
    """
    svc = RequirementService()
    ctx = _admin_auth_context(e2e_workspace, e2e_user_admin.id)

    set_request_tenant(e2e_workspace.tenant_id)
    try:
        for i in range(100):
            svc.create_requirement(
                workspace_id=e2e_workspace.id,
                title=f"Perf Req {i}",
                ctx=ctx,
                description=f"Perf description {i}",
            )
    finally:
        clear_request_tenant()

    start = time.perf_counter()
    response = post_mcp(
        admin_client,
        "requirement.query",
        {"workspace_id": str(e2e_workspace.id)},
    )
    elapsed = time.perf_counter() - start

    assert response.status_code == 200, response.content
    result = extract_result(response)
    assert result["count"] == 100, (
        f"expected 100 requirements, got {result['count']}"
    )
    assert elapsed < 2.0, (
        f"requirement.query with 100 requirements took {elapsed:.2f}s "
        f"(budget: 2.0s)"
    )


# ---------------------------------------------------------------------------
# permissions.list — 50 item permissions
# ---------------------------------------------------------------------------


@pytest.mark.slow
@pytest.mark.django_db(transaction=True)
def test_permissions_list_with_50_rules_under_1_5s(
    admin_client,
    e2e_workspace,
    e2e_user_admin,
    e2e_user_member,
    e2e_userrole_admin,
):
    """50 ItemPermissions: list must complete in < 1.5s.

    Each rule has a distinct ``artifact_id`` because the (user, workspace,
    artifact) triple is the natural key — granting 50 identical triples
    would just upsert one row. Varying artifact_id yields 50 distinct
    rows that ``permissions.list`` returns as a single page.
    """
    from persistence.models import Artifact
    set_request_tenant(e2e_workspace.tenant_id)
    try:
        for _ in range(50):
            art = Artifact.objects.create(
                tenant_id=e2e_workspace.tenant_id,
                workspace_id=e2e_workspace.id,
            )
            ItemPermission.unscoped.create(
                tenant_id=e2e_workspace.tenant_id,
                user_id=e2e_user_member.id,
                workspace_id=e2e_workspace.id,
                artifact_id=art.id,
                permission_level=ITEM_PERMISSION_READ,
                granted_by_id=e2e_user_admin.id,
            )
    finally:
        clear_request_tenant()

    start = time.perf_counter()
    response = post_mcp(
        admin_client,
        "permissions.list",
        {
            "workspace_id": str(e2e_workspace.id),
            "user_id": str(e2e_user_member.id),
        },
    )
    elapsed = time.perf_counter() - start

    assert response.status_code == 200, response.content
    result = extract_result(response)
    assert len(result["permissions"]) == 50, (
        f"expected 50 permissions, got {len(result['permissions'])}"
    )
    assert elapsed < 1.5, (
        f"permissions.list with 50 rules took {elapsed:.2f}s "
        f"(budget: 1.5s)"
    )


# ---------------------------------------------------------------------------
# audit.query — 50 audit entries
# ---------------------------------------------------------------------------


@pytest.mark.slow
@pytest.mark.django_db(transaction=True)
def test_audit_query_with_50_entries_under_1_5s(
    admin_client,
    e2e_workspace,
    e2e_user_admin,
    e2e_userrole_admin,
):
    """50 AuditEntries: query must complete in < 1.5s."""
    _seed_audit_entry_bulk(e2e_workspace, e2e_user_admin, count=50)

    start = time.perf_counter()
    response = post_mcp(
        admin_client,
        "audit.query",
        {"workspace_id": str(e2e_workspace.id), "limit": 200},
    )
    elapsed = time.perf_counter() - start

    assert response.status_code == 200, response.content
    result = extract_result(response)
    assert result["total"] >= 50, (
        f"expected at least 50 audit entries, got total={result['total']}"
    )
    assert elapsed < 1.5, (
        f"audit.query with 50 entries took {elapsed:.2f}s "
        f"(budget: 1.5s)"
    )


# ---------------------------------------------------------------------------
# user.list — 50 users
# ---------------------------------------------------------------------------


@pytest.mark.slow
@pytest.mark.django_db(transaction=True)
def test_user_list_with_50_users_under_1s(
    admin_client,
    e2e_tenant,
    e2e_workspace,
    e2e_userrole_admin,
):
    """50 Users: list must complete in < 1s.

    Users are created via the default ``User.objects`` manager (Django
    auth manager, not tenant-scoped) so no tenant context is required
    for the seed.
    """
    for i in range(50):
        User.objects.create(
            username=f"perf_user_{i}_{uuid4().hex[:6]}",
            email=f"perf_{i}_{uuid4().hex[:6]}@e2e.test",
            tenant=e2e_tenant,
            is_active=True,
        )

    start = time.perf_counter()
    response = post_mcp(
        admin_client,
        "user.list",
        {"workspace_id": str(e2e_workspace.id)},
    )
    elapsed = time.perf_counter() - start

    assert response.status_code == 200, response.content
    result = extract_result(response)
    assert result["count"] >= 50, (
        f"expected at least 50 users, got count={result['count']}"
    )
    assert elapsed < 1.0, (
        f"user.list with 50 users took {elapsed:.2f}s "
        f"(budget: 1.0s)"
    )
