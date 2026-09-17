"""Tenant-context teardown regressions found reviewing #444 (issue #522).

Three defects, all introduced or made load-bearing when ``run_capability``
switched from the pure-Python ``TenantContext.set_tenant``/``clear_tenant``
to ``set_request_tenant``/``clear_request_tenant``, which also talk to the DB:

F1  The ``finally`` can now raise. A raise from a ``finally`` *replaces* the
    exception in flight, so a broken connection during
    ``RESET app.current_tenant`` made Celery store the teardown error as the
    task result while the real failure survived only in a log line.

F3  Under ``CELERY_TASK_ALWAYS_EAGER`` the task body runs inline on the
    caller's thread and connection, and ``AsyncTaskDispatcher``
    ``._resolve_tenant_id`` reads ``tenant_id`` off that same caller's
    thread-local — so ``tenant_id`` is non-None precisely when the caller
    already owns a context. Clearing unconditionally disarmed the caller's
    isolation at both layers for the rest of its request.

F4  ``record_token_usage`` got a ``transaction.atomic()`` savepoint in #444,
    but the read paths did not. On Postgres a failing SELECT aborts the
    caller's ambient transaction exactly as a failing INSERT does, so the
    module's documented "never affects the caller" contract held on one of
    four paths only — and the uncovered one, ``get_daily_usage`` via
    ``is_over_daily_limit``, runs before every single LLM request.

The role-switching pattern (``SET ROLE`` to the least-privilege application
role, because the test connection is a Postgres superuser and bypasses RLS)
follows ``test_rls_token_usage_444.py``.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from django.db import OperationalError, connection, transaction

from llm_adapter import tasks
from llm_adapter.interface import LlmResult
from llm_adapter.token_tracking import aggregate_usage, get_daily_usage
from persistence.db_roles import APP_DB_ROLE
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, TokenUsageRecord
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db(transaction=True)

_IS_POSTGRES = connection.vendor == "postgresql"
_pg_only = pytest.mark.skipif(not _IS_POSTGRES, reason="PostgreSQL-only assertion")


def _mock_provider() -> MagicMock:
    provider = MagicMock()
    provider.PROVIDER_NAME = "mock"
    provider.validate_artifact.return_value = LlmResult(
        score=0.9, suggestions=[], provider="mock", model="m", token_usage=13
    )
    return provider


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(
        name="Teardown-522 Tenant",
        slug=f"teardown-522-{uuid.uuid4().hex[:8]}",
        is_active=True,
    )


@pytest.fixture(autouse=True)
def _reset_context():
    """Leave no context behind even when a test patches the teardown away."""
    yield
    TenantContext.clear_tenant()
    if _IS_POSTGRES:
        with connection.cursor() as cursor:
            cursor.execute("RESET ROLE")
            cursor.execute("RESET app.current_tenant")


class TestCallerOwnedContextSurvives:
    """F3 — the eager-Celery case: the task must not clear what it did not set."""

    def test_python_context_still_active_after_the_task(self, tenant):
        set_request_tenant(tenant.id)
        try:
            with patch(
                "llm_adapter.providers.get_provider", return_value=_mock_provider()
            ):
                tasks.run_capability.run(
                    "validate_artifact", {"artifact_id": "a1"}, str(tenant.id)
                )
            assert TenantContext.is_set(), (
                "run_capability tore down a tenant context it did not activate — "
                "under CELERY_TASK_ALWAYS_EAGER that is the caller's own context"
            )
            assert TenantContext.get_tenant() == tenant.id
        finally:
            clear_request_tenant()

    @_pg_only
    def test_rls_session_variable_still_armed_after_the_task(self, tenant):
        set_request_tenant(tenant.id)
        try:
            with patch(
                "llm_adapter.providers.get_provider", return_value=_mock_provider()
            ):
                tasks.run_capability.run(
                    "validate_artifact", {"artifact_id": "a1"}, str(tenant.id)
                )
            with connection.cursor() as cursor:
                cursor.execute("SELECT current_setting('app.current_tenant', true)")
                current = cursor.fetchone()[0]
            assert current == str(tenant.id), (
                "app.current_tenant was reset on the caller's connection; any "
                f"unscoped/raw query the caller runs next loses RLS (got {current!r})"
            )
        finally:
            clear_request_tenant()

    def test_worker_owned_context_is_still_cleared(self, tenant):
        """The guard must not disable teardown in the real worker case, where
        nothing was active before the task."""
        assert not TenantContext.is_set()
        with patch(
            "llm_adapter.providers.get_provider", return_value=_mock_provider()
        ):
            tasks.run_capability.run(
                "validate_artifact", {"artifact_id": "a1"}, str(tenant.id)
            )
        assert not TenantContext.is_set()


class TestTeardownFailureDoesNotMaskTheCause:
    """F1 — a failing RESET must not replace the exception being raised."""

    def test_original_exception_reaches_celery(self, tenant):
        provider = MagicMock()
        provider.PROVIDER_NAME = "mock"
        provider.validate_artifact.side_effect = RuntimeError("provider exploded")

        with patch(
            "llm_adapter.providers.get_provider", return_value=provider
        ), patch(
            "persistence.middleware.clear_request_tenant",
            side_effect=OperationalError("connection already gone"),
        ):
            with pytest.raises(RuntimeError, match="provider exploded"):
                tasks.run_capability.run(
                    "validate_artifact", {"artifact_id": "a1"}, str(tenant.id)
                )

    def test_teardown_failure_alone_does_not_fail_a_successful_task(self, tenant):
        with patch(
            "llm_adapter.providers.get_provider", return_value=_mock_provider()
        ), patch(
            "persistence.middleware.clear_request_tenant",
            side_effect=OperationalError("connection already gone"),
        ):
            result = tasks.run_capability.run(
                "validate_artifact", {"artifact_id": "a1"}, str(tenant.id)
            )
        assert result["score"] == 0.9


@_pg_only
class TestReadPathsDoNotPoisonCallerTransaction:
    """F4 — the savepoint must cover the SELECTs, not just the INSERT.

    The failure is produced the way a real one would be — the application role
    losing SELECT on the table — rather than by patching the queryset to raise:
    a mock raises before touching the database, so no transaction is ever
    aborted and the test would pass with or without the savepoint.
    """

    def test_failed_reads_leave_the_callers_transaction_usable(self, tenant):
        TenantContext.set_tenant(tenant.id)
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    f'REVOKE SELECT ON pl_token_usage_record FROM "{APP_DB_ROLE}"'
                )
                cursor.execute(f'SET ROLE "{APP_DB_ROLE}"')

            try:
                # Both swallow their own failure by contract ...
                assert get_daily_usage(days=1) == 0
                assert aggregate_usage(days=30)["total_tokens"] == 0
            finally:
                # RESET ROLE unconditionally. SET ROLE is session-level and
                # is NOT undone by the transaction ROLLBACK below, so an
                # AssertionError from either assert above would otherwise
                # leave this shared connection permanently downgraded to
                # the low-privilege app role for every test that runs
                # after this one in the same pytest session — the exact
                # test-order-dependent failure this class exists to guard
                # against (discovered auditing the #568 theming branch).
                with connection.cursor() as cursor:
                    cursor.execute("RESET ROLE")

            try:
                # ... and must leave the caller able to keep querying. Without the
                # savepoints this raises TransactionManagementError.
                assert TokenUsageRecord.unscoped.filter(tenant_id=tenant.id).count() == 0
            finally:
                # Undo the REVOKE unconditionally too, for the same reason:
                # with django_db(transaction=True) this atomic block is the
                # outermost one and would otherwise COMMIT the privilege
                # change into the shared test database on any failure here.
                transaction.set_rollback(True)
