"""#1987 follow-up — the Celery worker applies the same producer gate as dispatch.

Before this fix ``_resolve_agent_context`` filtered ``principal_type="agent"``,
so an async ``traceability.suggest_links`` call with a user-principal
``author``-scoped plugin key passed the dispatcher gate and then failed inside
the worker. The worker now rebuilds the context from any active API key and
runs it through the shared ``require_producer_context`` gate: a human bearer
(no key id), a read-only key and an unknown scope stay refused fail-closed.
"""
from __future__ import annotations

import contextlib
from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import pytest

from application.base import ProducerContextRequiredError
from application.tasks import _resolve_agent_context, run_traceability_suggest_links
from application.traceability_suggest_service import TraceabilitySuggestService
from auth_tenancy.models import (
    API_KEY_SCOPE_AUTHOR,
    API_KEY_SCOPE_READ,
    PRINCIPAL_TYPE_AGENT,
    PRINCIPAL_TYPE_USER,
    ApiKey,
)
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
        name="Async Producer Gate Tenant", slug="async-producer-gate-tenant"
    )


@pytest.fixture
def user(tenant: Tenant) -> User:
    return User.objects.create(
        username="async-producer-user",
        email="async-producer@example.com",
        tenant=tenant,
    )


@pytest.fixture
def workspace(tenant: Tenant) -> Workspace:
    with _active(tenant):
        return Workspace.objects.create(tenant=tenant, name="Async-Producer-WS")


def _key(
    tenant: Tenant,
    user: User,
    *,
    principal_type: str,
    scope: str,
    agent_label: str = "",
    revoked: bool = False,
) -> ApiKey:
    from django.utils import timezone

    with _active(tenant):
        return ApiKey.objects.create(
            tenant=tenant,
            user=user,
            name=f"async-{principal_type}-{scope}",
            key_hash=f"sha256p1:async-{principal_type}-{scope}-{tenant.id}",
            principal_type=principal_type,
            scope=scope,
            agent_label=agent_label,
            revoked_at=timezone.now() if revoked else None,
        )


def _run(tenant: Tenant, workspace: Workspace, key: ApiKey):
    fake_result = MagicMock()
    fake_result.to_dict.return_value = {"tier": "standard", "suggestions": []}
    with patch.object(
        TraceabilitySuggestService, "suggest_links", return_value=fake_result
    ) as suggest:
        out = run_traceability_suggest_links(
            workspace_id=str(workspace.id),
            tenant_id=str(tenant.id),
            api_key_id=str(key.id),
        )
    return out, suggest


class TestWorkerProducerGate:
    def test_user_principal_author_key_runs_and_keeps_agent_stamp(
        self, tenant: Tenant, user: User, workspace: Workspace
    ) -> None:
        key = _key(
            tenant,
            user,
            principal_type=PRINCIPAL_TYPE_USER,
            scope=API_KEY_SCOPE_AUTHOR,
            agent_label="Claude Code Plugin",
        )

        out, suggest = _run(tenant, workspace, key)

        assert out == {"tier": "standard", "suggestions": []}
        ctx = suggest.call_args.args[1]
        assert ctx.api_key_id == key.id
        assert ctx.scope == API_KEY_SCOPE_AUTHOR
        # Stamping / self-confirm block depend on this flag downstream.
        assert ctx.actor_type == PRINCIPAL_TYPE_AGENT
        assert ctx.agent_label == "Claude Code Plugin"

    def test_agent_principal_key_keeps_working(
        self, tenant: Tenant, user: User, workspace: Workspace
    ) -> None:
        key = _key(
            tenant, user, principal_type=PRINCIPAL_TYPE_AGENT, scope="write"
        )

        _out, suggest = _run(tenant, workspace, key)

        assert suggest.call_args.args[1].actor_type == PRINCIPAL_TYPE_AGENT

    @pytest.mark.parametrize("principal_type", [PRINCIPAL_TYPE_USER, PRINCIPAL_TYPE_AGENT])
    def test_read_only_key_is_refused_fail_closed(
        self, tenant: Tenant, user: User, workspace: Workspace, principal_type: str
    ) -> None:
        key = _key(
            tenant, user, principal_type=principal_type, scope=API_KEY_SCOPE_READ
        )

        with (
            patch.object(TraceabilitySuggestService, "suggest_links") as suggest,
            pytest.raises(ProducerContextRequiredError),
        ):
            _run(tenant, workspace, key)

        suggest.assert_not_called()

    def test_user_principal_legacy_write_scope_stays_refused_in_worker(
        self, tenant: Tenant, user: User, workspace: Workspace
    ) -> None:
        """The worker gate is widened only by #1987, not for owner keys.

        A user-principal ``write`` key keeps ``actor_type="user"``, so the M2
        proposal stamp would silently skip it. Refuse instead of persisting an
        unstamped proposal (the old worker filtered ``principal_type="agent"``).
        """
        key = _key(tenant, user, principal_type=PRINCIPAL_TYPE_USER, scope="write")

        with (
            patch.object(TraceabilitySuggestService, "suggest_links") as suggest,
            pytest.raises(ProducerContextRequiredError),
        ):
            _run(tenant, workspace, key)

        suggest.assert_not_called()

    def test_unknown_scope_is_refused_fail_closed(
        self, tenant: Tenant, user: User, workspace: Workspace
    ) -> None:
        key = _key(
            tenant, user, principal_type=PRINCIPAL_TYPE_USER, scope="not-a-scope"
        )

        with (
            patch.object(TraceabilitySuggestService, "suggest_links") as suggest,
            pytest.raises(ProducerContextRequiredError),
        ):
            _run(tenant, workspace, key)

        suggest.assert_not_called()

    def test_revoked_author_key_is_still_refused(
        self, tenant: Tenant, user: User, workspace: Workspace
    ) -> None:
        key = _key(
            tenant,
            user,
            principal_type=PRINCIPAL_TYPE_USER,
            scope=API_KEY_SCOPE_AUTHOR,
            revoked=True,
        )

        with pytest.raises(ProducerContextRequiredError):
            _run(tenant, workspace, key)

    def test_missing_key_id_is_still_refused(
        self, tenant: Tenant, workspace: Workspace
    ) -> None:
        with pytest.raises(ProducerContextRequiredError):
            run_traceability_suggest_links(
                workspace_id=str(workspace.id), tenant_id=str(tenant.id)
            )


class TestResolveAgentContextDirect:
    def test_user_principal_author_key_resolves_to_agent_context(
        self, tenant: Tenant, user: User
    ) -> None:
        key = _key(
            tenant, user, principal_type=PRINCIPAL_TYPE_USER, scope=API_KEY_SCOPE_AUTHOR
        )

        with _active(tenant):
            ctx = _resolve_agent_context(str(tenant.id), str(key.id))

        assert ctx.actor_type == PRINCIPAL_TYPE_AGENT
        assert ctx.api_key_id == key.id

    def test_read_only_key_is_refused_by_the_shared_gate(
        self, tenant: Tenant, user: User
    ) -> None:
        key = _key(
            tenant, user, principal_type=PRINCIPAL_TYPE_USER, scope=API_KEY_SCOPE_READ
        )

        with _active(tenant), pytest.raises(ProducerContextRequiredError):
            _resolve_agent_context(str(tenant.id), str(key.id))
