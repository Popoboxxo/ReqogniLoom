"""
ARCH-L1-015 SeMetrics — RLS-in-worker-thread regression tests (issue #405).

Root cause: ``MetricsAggregator.compute()`` runs its four source queries
(``_fetch_audit_entries``, ``_fetch_coverage``, ``_fetch_incomplete_states``,
``_fetch_risks``) via a ``ThreadPoolExecutor``. Each worker thread gets its
own DB connection (Django connections are thread-local). Before the fix,
each worker only called ``TenantContext.set_tenant(tenant_id)`` — the
Python-side thread-local used by the app-layer ``TenantManager``
(COMP-PL-002) — but never set the PostgreSQL session variable
``app.current_tenant`` that the RLS policies (COMP-PL-006) key off on that
worker's own connection. In production, the Django DB user is the
least-privilege, non-superuser ``reqogniloom_app`` role (RLS is FORCEd for
it, see persistence/migrations/0003_rls_policies.py and
persistence/db_roles.py), so every tenant-scoped query issued by a worker
thread silently matched zero rows — coverage always computed 0/0 and
rendered as 0%, regardless of real data.

The default *test* DB connection authenticates as a Postgres superuser,
which bypasses RLS unconditionally (even with FORCE ROW LEVEL SECURITY) —
this is why the aggregator's existing unit tests (which mock out all four
``_fetch_*`` functions) never caught this. To reproduce the real production
condition, these tests explicitly ``SET ROLE`` to the least-privilege
application role inside the worker thread's own connection before invoking
the fetch function — the same technique already established by
``application/tests/test_rls_policies.py::test_rls_blocks_raw_query_without_tenant_setting``.

All assertions are PostgreSQL-specific (RLS is a PostgreSQL feature) and are
skipped on other backends, matching the project convention.
"""
from __future__ import annotations

import threading
import uuid

import pytest
from django.db import connection

from persistence.db_roles import APP_DB_ROLE
from persistence.tenancy import TenantContext
from se_metrics.aggregator import _fetch_coverage

pytestmark = pytest.mark.django_db(transaction=True)

_IS_POSTGRES = connection.vendor == "postgresql"
_pg_only = pytest.mark.skipif(not _IS_POSTGRES, reason="PostgreSQL-only assertion")


def _make_workspace_with_requirement(tenant, title="Login must support 2FA"):
    """Create tenant-scoped Workspace + Artifact + Requirement.

    Uses the superuser test connection (bypasses RLS), which is fine — this
    is setup data, not the thing under test.
    """
    from persistence.models import Artifact, Requirement, Workspace

    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(tenant=tenant, name="RLS-405-WS")
        artifact = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="requirement"
        )
        req = Requirement.objects.create(tenant=tenant, artifact=artifact, title=title)
        return workspace, artifact, req
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def tenant(db):
    from persistence.models import Tenant

    return Tenant.objects.create(
        name="RLS-405 Tenant", slug=f"rls-405-{uuid.uuid4().hex[:8]}", is_active=True
    )


@_pg_only
class TestFetchCoverageRlsInWorkerThread:
    """Issue #405: _fetch_coverage must see rows in its own worker thread."""

    def test_fetch_coverage_sees_data_under_least_privilege_role(self, tenant):
        """The fix (set_request_tenant inside the worker) must make the
        Requirement visible even under the RLS-enforced application role,
        from a thread that owns its own, fresh DB connection."""
        workspace, _artifact, _req = _make_workspace_with_requirement(tenant)

        result_holder: dict = {}

        def _worker():
            with connection.cursor() as cursor:
                cursor.execute(f'SET ROLE "{APP_DB_ROLE}"')
            try:
                result_holder["coverage"] = _fetch_coverage(
                    workspace_id=str(workspace.id), tenant_id=tenant.id
                )
            finally:
                with connection.cursor() as cursor:
                    cursor.execute("RESET ROLE")
                connection.close()

        t = threading.Thread(target=_worker)
        t.start()
        t.join(timeout=10)

        coverage = result_holder.get("coverage")
        assert coverage is not None, (
            "_fetch_coverage returned None (source failure) — RLS likely "
            "blocked the query in the worker thread's own connection"
        )
        assert coverage.total == 1, (
            f"Expected 1 requirement visible under RLS, got {coverage.total} "
            "— worker thread's connection is missing the app.current_tenant "
            "session variable (issue #405)"
        )

    def test_worker_thread_without_rls_session_var_sees_no_rows(self, tenant):
        """Control test proving the RLS mechanism itself: a worker thread
        that only sets the Python-side TenantContext (the pre-fix behaviour)
        — without the Postgres session variable — sees zero rows under the
        least-privilege role, even though the Requirement exists and belongs
        to the correct tenant. This is the exact bug #405 reproduced without
        the fix, isolating that ``set_request_tenant`` (not just
        ``TenantContext.set_tenant``) is the necessary ingredient."""
        from persistence.models import Requirement

        workspace, _artifact, _req = _make_workspace_with_requirement(tenant)

        result_holder: dict = {}

        def _worker():
            with connection.cursor() as cursor:
                cursor.execute(f'SET ROLE "{APP_DB_ROLE}"')
            try:
                # Pre-fix behaviour: only the Python-side thread-local is
                # set, app.current_tenant is never SET on this connection.
                TenantContext.set_tenant(tenant.id)
                result_holder["count"] = Requirement.objects.filter(
                    artifact__workspace_id=workspace.id
                ).count()
            finally:
                TenantContext.clear_tenant()
                with connection.cursor() as cursor:
                    cursor.execute("RESET ROLE")
                connection.close()

        t = threading.Thread(target=_worker)
        t.start()
        t.join(timeout=10)

        assert result_holder.get("count") == 0, (
            "Expected RLS to block the row without app.current_tenant set "
            "on this connection — if this fails, the RLS policy itself (or "
            "the test role) is not enforcing isolation as assumed"
        )
