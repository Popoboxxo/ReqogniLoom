"""RLS-in-Celery-worker regression test (issue #444).

Root cause: ``run_capability`` (llm_adapter/tasks.py) restored the tenant
context for the worker via ``TenantContext.set_tenant(tenant_id)`` alone —
the Python-side thread-local the app-layer ``TenantManager`` (COMP-PL-002)
reads. It never issued ``SET app.current_tenant`` on the worker's own DB
connection, the session variable RLS policies (COMP-PL-006) key off. In
production the Celery worker's Django DB user is the least-privilege,
non-superuser ``reqogniloom_app`` role (RLS is FORCEd for it, see
persistence/migrations/0003_rls_policies.py and persistence/db_roles.py), so
every ``TokenUsageRecord`` INSERT issued at the end of ``run_capability``
violated the table's ``WITH CHECK`` policy: "new row violates row-level
security policy for table pl_token_usage_record". The ``LlmSettings`` lookup
earlier in the same call failed more quietly — RLS's ``USING`` clause simply
hid the row, so the worker fell back to env config without an error.

Same class of bug as #405 (se_metrics/tests/test_rls_worker_threads_405.py),
same fix technique: ``set_request_tenant``/``clear_request_tenant``
(persistence/middleware.py) instead of the bare ``TenantContext`` methods.

The default *test* DB connection authenticates as a Postgres superuser,
which bypasses RLS unconditionally (even with FORCE ROW LEVEL SECURITY) —
this is why the existing tenant-settings-propagation tests never caught
this. To reproduce the real production condition, ``SET ROLE`` to the
least-privilege application role on the test's own connection before
calling ``run_capability.run(...)`` synchronously (Celery's local ``.run()``
executes in-process, on this same thread/connection — no separate worker
thread needed to exercise the bug, unlike #405's ThreadPoolExecutor case).
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from django.db import connection, transaction

from llm_adapter import tasks
from llm_adapter.interface import LlmResult
from llm_adapter.providers import resolve_provider_config
from llm_adapter.token_tracking import record_token_usage
from persistence.db_roles import APP_DB_ROLE
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import LlmSettings, Tenant, TokenUsageRecord
from persistence.tenancy import TenantContext, TenantContextNotSetError

pytestmark = pytest.mark.django_db(transaction=True)

_IS_POSTGRES = connection.vendor == "postgresql"
_pg_only = pytest.mark.skipif(not _IS_POSTGRES, reason="PostgreSQL-only assertion")


def _mock_provider() -> MagicMock:
    provider = MagicMock()
    provider.PROVIDER_NAME = "mock"
    provider.validate_artifact.return_value = LlmResult(
        score=0.9, suggestions=[], provider="mock", model="m", token_usage=42
    )
    return provider


@pytest.fixture
def tenant(db):
    # Created as the superuser test role, which bypasses RLS — setup data,
    # not the thing under test.
    return Tenant.objects.create(
        name="RLS-444 Tenant", slug=f"rls-444-{uuid.uuid4().hex[:8]}", is_active=True
    )


@_pg_only
class TestRunCapabilityRecordsTokenUsageUnderRls:
    def test_token_usage_record_created_under_least_privilege_role(self, tenant):
        """The fix (set_request_tenant inside run_capability) must let the
        TokenUsageRecord INSERT pass RLS's WITH CHECK even under the
        RLS-enforced application role — reproducing #444's "new row violates
        row-level security policy for table pl_token_usage_record"."""
        with connection.cursor() as cursor:
            cursor.execute(f'SET ROLE "{APP_DB_ROLE}"')
        try:
            with patch(
                "llm_adapter.providers.get_provider", return_value=_mock_provider()
            ):
                tasks.run_capability.run(
                    "validate_artifact", {"artifact_id": "a1"}, str(tenant.id)
                )
        finally:
            with connection.cursor() as cursor:
                cursor.execute("RESET ROLE")

        record = TokenUsageRecord.unscoped.filter(tenant_id=tenant.id).first()
        assert record is not None, (
            "TokenUsageRecord was not persisted — run_capability's RLS session "
            "variable was not set for this connection/role"
        )
        assert record.provider == "mock"
        assert record.capability == "validate_artifact"
        assert record.input_tokens == 42

    def test_tenant_context_cleared_after_task_under_least_privilege_role(self, tenant):
        """clear_request_tenant must reset both the Python-side context and
        the RLS session variable — a lingering app.current_tenant would leak
        into whatever runs on this connection next."""
        with connection.cursor() as cursor:
            cursor.execute(f'SET ROLE "{APP_DB_ROLE}"')
        try:
            with patch(
                "llm_adapter.providers.get_provider", return_value=_mock_provider()
            ):
                tasks.run_capability.run(
                    "validate_artifact", {"artifact_id": "a1"}, str(tenant.id)
                )

            with pytest.raises(TenantContextNotSetError):
                TenantContext.get_tenant()

            with connection.cursor() as cursor:
                # `current_setting(..., missing_ok=true)` — not SHOW/plain
                # current_setting — is the only form that does not itself
                # raise "unrecognized configuration parameter" for a custom
                # placeholder GUC that has never been SET in this session.
                cursor.execute("SELECT current_setting('app.current_tenant', true)")
                current = cursor.fetchone()[0]
            assert current in (None, ""), (
                f"app.current_tenant was not reset after the task, still: {current!r}"
            )
        finally:
            with connection.cursor() as cursor:
                cursor.execute("RESET app.current_tenant")
                cursor.execute("RESET ROLE")


@_pg_only
class TestResolveProviderConfigUnderRls:
    """The quieter half of #444: the LlmSettings SELECT, not the INSERT.

    RLS's ``USING`` clause does not raise when ``app.current_tenant`` is unset —
    it returns zero rows. ``_apply_db_settings`` reads that as "this tenant has
    no settings" and silently hands back the environment config, so the worker
    ran on the wrong provider/model with nothing in the logs. The INSERT tests
    above cannot catch a regression of this half, because they mock
    ``get_provider`` and never look at the resolved config.
    """

    @staticmethod
    def _seed_settings(tenant: Tenant) -> None:
        # Written as the superuser test role (bypasses RLS) — setup data.
        TenantContext.set_tenant(tenant.id)
        try:
            LlmSettings.objects.create(
                provider="ollama",
                base_url="http://tenant-444.invalid:11434",
                model_name="tenant-model-444",
            )
        finally:
            TenantContext.clear_tenant()

    def test_settings_hidden_without_rls_session_variable(self, tenant):
        """Pre-fix condition: TenantContext alone leaves RLS unarmed, so the
        tenant's LlmSettings row is invisible and the env fallback wins."""
        self._seed_settings(tenant)
        env_config = resolve_provider_config()  # no tenant at all — pure env

        with connection.cursor() as cursor:
            cursor.execute(f'SET ROLE "{APP_DB_ROLE}"')
        TenantContext.set_tenant(tenant.id)
        try:
            config = resolve_provider_config()
        finally:
            TenantContext.clear_tenant()
            with connection.cursor() as cursor:
                cursor.execute("RESET ROLE")

        assert config.model_name == env_config.model_name
        assert config.model_name != "tenant-model-444", (
            "LlmSettings row was visible without app.current_tenant — RLS is "
            "not enforced for this role, so this test proves nothing"
        )

    def test_settings_resolved_with_rls_session_variable(self, tenant):
        """The fix: set_request_tenant arms RLS, so the persisted per-tenant
        settings win over the environment config again."""
        self._seed_settings(tenant)

        with connection.cursor() as cursor:
            cursor.execute(f'SET ROLE "{APP_DB_ROLE}"')
        try:
            set_request_tenant(tenant.id)
            config = resolve_provider_config()
        finally:
            clear_request_tenant()
            with connection.cursor() as cursor:
                cursor.execute("RESET ROLE")

        assert config.provider_name == "ollama"
        assert config.model_name == "tenant-model-444"
        assert config.api_base_url == "http://tenant-444.invalid:11434"


@_pg_only
class TestRecordTokenUsageDoesNotPoisonCallerTransaction:
    """#444 follow-up (#522 suggestion 1): the ``transaction.atomic()`` savepoint.

    ``record_token_usage`` swallows its own failures by contract, but before the
    savepoint was added the *caller's* ambient transaction stayed in Postgres's
    "aborted" state afterwards — every later query on that connection raised
    ``TransactionManagementError``, including ``clear_request_tenant``'s own
    ``RESET``. Swallowing the exception while wrecking the caller's transaction
    is not "best-effort", it is the same outage with a quieter traceback.

    The failure is produced the way production produced it — an RLS ``WITH
    CHECK`` violation under the least-privilege role with ``app.current_tenant``
    unset — rather than by patching ``objects.create`` to raise: a mock raises
    before touching the database, so no transaction is ever aborted and the
    test would pass with or without the savepoint.
    """

    def test_failed_insert_leaves_callers_transaction_usable(self, tenant):
        TenantContext.set_tenant(tenant.id)
        try:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(f'SET ROLE "{APP_DB_ROLE}"')

                # app.current_tenant deliberately unset -> WITH CHECK rejects.
                record_token_usage(
                    provider="mock", capability="validate_artifact", input_tokens=7
                )

                # The caller's transaction must still accept queries. Without
                # the savepoint this raises TransactionManagementError.
                assert TokenUsageRecord.objects.count() == 0
        finally:
            with connection.cursor() as cursor:
                cursor.execute("RESET ROLE")
            TenantContext.clear_tenant()

        assert not TokenUsageRecord.unscoped.filter(tenant_id=tenant.id).exists()
