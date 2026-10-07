"""Issue #1197 — async dispatch + tenant-scoped poll for ``suggest-links``.

The synchronous ``TraceabilitySuggestService.suggest_links`` measured ~94.5 s
on a large workspace and blocked the request thread. These tests cover the new
``suggest_links_async`` / ``get_suggest_links_status`` pair and the Celery task
that runs the same computation off-thread:

* the async trigger returns a ``task_id`` (never blocks) and records the
  dispatching tenant for ADR-03 ownership enforcement;
* a poll of another tenant's / an unknown ``task_id`` is indistinguishable and
  never reaches the tenant-blind Celery result backend;
* the worker task re-arms the tenant context and executes the real
  ``suggest_links`` (RBAC is enforced at dispatch; the worker run is tenant
  scoped and read-only).
"""
from __future__ import annotations

import contextlib
import uuid
from typing import Iterator
from unittest.mock import MagicMock, patch

import pytest
from django.core.cache import cache

from application.traceability_suggest_service import (
    _TASK_TENANT_CACHE_PREFIX,
    TraceabilitySuggestService,
)
from auth_tenancy.context import AuthContext
from persistence.models import Tenant, User, Workspace
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db


@contextlib.contextmanager
def _active(tenant: Tenant) -> Iterator[None]:
    TenantContext.set_tenant(tenant.id)
    try:
        yield
    finally:
        TenantContext.clear_tenant()


@pytest.fixture(autouse=True)
def _clear_tenant() -> Iterator[None]:
    TenantContext.clear_tenant()
    yield
    TenantContext.clear_tenant()


@pytest.fixture
def tenant() -> Tenant:
    return Tenant.objects.create(
        name="SuggestLinks Async Tenant", slug="suggest-links-async-tenant"
    )


@pytest.fixture
def user(tenant: Tenant) -> User:
    return User.objects.create(
        username="suggest-links-async-user",
        email="suggest-links-async@example.com",
        tenant=tenant,
    )


@pytest.fixture
def workspace(tenant: Tenant) -> Workspace:
    with _active(tenant):
        return Workspace.objects.create(tenant=tenant, name="SuggestLinks-Async-WS")


@pytest.fixture
def ctx(user: User) -> AuthContext:
    return AuthContext(
        user_id=user.id,
        tenant_id=user.tenant.id,
        active_roles=("editor",),
        auth_method="test",
    )


class TestSuggestLinksAsyncTrigger:
    def test_returns_task_id_and_records_tenant_ownership(
        self,
        tenant: Tenant,
        workspace: Workspace,
        ctx: AuthContext,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Env pin: AsyncTaskDispatcher._broker_configured() reads the OS env var
        # CELERY_BROKER_URL (not settings), so CI job set-1-core — which never
        # exports it — would otherwise short-circuit dispatch before the patched
        # apply_async is reached. Mirrors the canonical pattern in
        # test_bundle_compression_service.py's TestCompressAsync.
        monkeypatch.setenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
        fake_async = MagicMock()
        fake_async.id = "task-1197"

        with patch(
            "application.tasks.run_traceability_suggest_links.apply_async",
            return_value=fake_async,
        ) as apply_async:
            result = TraceabilitySuggestService().suggest_links_async(
                workspace.id, ctx
            )

        assert result == "task-1197"
        apply_async.assert_called_once()
        # ADR-03 ownership record: the tenant-blind Celery result backend is
        # only reachable through this mapping.
        assert (
            cache.get(f"{_TASK_TENANT_CACHE_PREFIX}:task-1197") == str(tenant.id)
        )

    def test_graceful_stub_when_broker_not_configured(
        self, workspace: Workspace, ctx: AuthContext
    ) -> None:
        with patch(
            "llm_adapter.dispatcher._broker_configured", return_value=False
        ):
            result = TraceabilitySuggestService().suggest_links_async(
                workspace.id, ctx
            )

        assert isinstance(result, dict)
        assert result["error"]["code"] == "BROKER_NOT_CONFIGURED"


class TestSuggestLinksStatusTenantFence:
    def test_unknown_task_id_is_not_found(self, ctx: AuthContext) -> None:
        from llm_adapter.dispatcher import AsyncTaskDispatcher

        with patch.object(AsyncTaskDispatcher, "get_task_status") as get_status:
            result = TraceabilitySuggestService().get_suggest_links_status(
                "never-dispatched", ctx
            )

        assert result == {
            "task_id": "never-dispatched",
            "status": "not_found",
            "result": None,
            "error": None,
        }
        get_status.assert_not_called()

    def test_foreign_tenant_task_id_is_not_found(
        self, tenant: Tenant, ctx: AuthContext
    ) -> None:
        from llm_adapter.dispatcher import AsyncTaskDispatcher

        cache.set(f"{_TASK_TENANT_CACHE_PREFIX}:foreign-task", str(uuid.uuid4()))

        with patch.object(AsyncTaskDispatcher, "get_task_status") as get_status:
            result = TraceabilitySuggestService().get_suggest_links_status(
                "foreign-task", ctx
            )

        assert result["status"] == "not_found"
        # Load-bearing: never touches the tenant-blind result backend.
        get_status.assert_not_called()

    def test_same_tenant_poll_reaches_the_real_status(
        self, tenant: Tenant, ctx: AuthContext
    ) -> None:
        from llm_adapter.dispatcher import AsyncTaskDispatcher, TaskStatusResult

        cache.set(f"{_TASK_TENANT_CACHE_PREFIX}:own-task", str(tenant.id))
        payload = {"tier": "standard", "suggestions": []}

        with patch.object(
            AsyncTaskDispatcher,
            "get_task_status",
            return_value=TaskStatusResult(
                task_id="own-task", status="done", result=payload
            ),
        ):
            result = TraceabilitySuggestService().get_suggest_links_status(
                "own-task", ctx
            )

        assert result == {
            "task_id": "own-task",
            "status": "done",
            "result": payload,
            "error": None,
        }


class TestSuggestLinksWorkerTask:
    def test_task_runs_the_real_service_with_a_tenant_scoped_ctx(
        self, tenant: Tenant, workspace: Workspace
    ) -> None:
        from application import tasks as application_tasks

        fake_result = MagicMock()
        fake_result.to_dict.return_value = {"tier": "standard", "suggestions": []}

        with patch.object(
            TraceabilitySuggestService, "suggest_links", return_value=fake_result
        ) as suggest:
            out = application_tasks.run_traceability_suggest_links(
                workspace_id=str(workspace.id),
                tenant_id=str(tenant.id),
            )

        assert out == {"tier": "standard", "suggestions": []}
        passed_ctx = suggest.call_args.args[1]
        assert passed_ctx.tenant_id == tenant.id
        # Tenant context is armed inside the worker, then torn down.
        assert not TenantContext.is_set()

    def test_task_rebuilds_audit_scopes_from_plain_dicts(
        self, tenant: Tenant, workspace: Workspace
    ) -> None:
        from application import tasks as application_tasks
        from traceability.audit import AuditScope

        fake_result = MagicMock()
        fake_result.to_dict.return_value = {}
        artifact_id = str(uuid.uuid4())

        with patch.object(
            TraceabilitySuggestService, "suggest_links", return_value=fake_result
        ) as suggest:
            application_tasks.run_traceability_suggest_links(
                workspace_id=str(workspace.id),
                tenant_id=str(tenant.id),
                scopes=[{"scope": "document", "artifact_id": artifact_id}],
                tier="extended",
            )

        assert suggest.call_args.kwargs["scopes"] == [
            AuditScope(scope="document", artifact_id=artifact_id)
        ]
        assert suggest.call_args.kwargs["tier"] == "extended"
