"""Issue #342 — the three workspace-wide LLM flows and their timeout contract.

``ai_derivation.derive_glossary_from_workspace``, ``traceability.suggest_links``
and ``audit.ai_review`` prompt over the whole workspace. They used to run under
the tight per-artifact cap (``LLM_SYNC_TIMEOUT_SECONDS``, 25s) or the provider's
30s config default, always exceeded it and surfaced as an uncaught transport
error / HTTP 500.

This module pins both halves of the fix at service level:

1. each of the three flows hands the provider the **long-running** timeout
   (``LLM_LONG_RUNNING_TIMEOUT_SECONDS``), while a single-artifact flow on the
   very same code path keeps the short one;
2. a provider call that still fails (timeout / open circuit breaker) is mapped
   onto the flow's own catchable error type, which the MCP and REST boundaries
   already translate into a structured error response — instead of escaping as
   an unhandled ``LlmTransportError``.

Unit-level coverage of the resolution seam itself lives in
``llm_adapter/tests/test_long_running_timeout.py``.
"""
from __future__ import annotations

import contextlib
import json
from typing import Any, Dict, Iterator, List, Optional

import pytest

from application.ai_derivation_service import AiDerivationService, LlmResponseError
from application.ai_review_service import AiReviewResponseError, AiReviewService
from application.traceability_suggest_service import (
    SuggestLinksResponseError,
    TraceabilitySuggestService,
)
from auth_tenancy.context import AuthContext
from llm_adapter.resilient_transport import LlmTransportError
from persistence.models import (
    Artifact,
    Requirement,
    StakeholderNeed,
    Tenant,
    User,
    Workspace,
)
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db

SHORT_TIMEOUT = 25
LONG_TIMEOUT = 180


# ---------------------------------------------------------------------------
# Fixtures + helpers (mirrors application/tests/test_ai_review_service.py)
# ---------------------------------------------------------------------------


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


@pytest.fixture(autouse=True)
def _pinned_timeouts(settings) -> None:
    """Pin both caps so the assertions do not depend on deployment config."""
    settings.LLM_SYNC_TIMEOUT_SECONDS = SHORT_TIMEOUT
    settings.LLM_LONG_RUNNING_TIMEOUT_SECONDS = LONG_TIMEOUT


@pytest.fixture
def tenant() -> Tenant:
    return Tenant.objects.create(name="Timeout Tenant", slug="timeout-tenant")


@pytest.fixture
def user(tenant: Tenant) -> User:
    return User.objects.create(
        username="timeout-user", email="timeout@example.com", tenant=tenant
    )


@pytest.fixture
def workspace(tenant: Tenant) -> Workspace:
    with _active(tenant):
        return Workspace.objects.create(tenant=tenant, name="Timeout-WS")


@pytest.fixture
def ctx(user: User) -> AuthContext:
    return AuthContext(
        user_id=user.id,
        tenant_id=user.tenant.id,
        active_roles=("editor",),
        auth_method="test",
        api_key_id=None,
        tenant_name="Timeout Tenant",
    )


def _artifact(tenant: Tenant, workspace: Workspace, artifact_type: str) -> Artifact:
    return Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type=artifact_type
    )


def _requirement(
    tenant: Tenant, workspace: Workspace, title: str = "Req", description: str = ""
) -> Requirement:
    art = _artifact(tenant, workspace, "requirement")
    return Requirement.objects.create(
        tenant=tenant, artifact=art, title=title, description=description
    )


def _need(
    tenant: Tenant, workspace: Workspace, title: str = "Need", description: str = ""
) -> StakeholderNeed:
    art = _artifact(tenant, workspace, "stakeholder_need")
    return StakeholderNeed.objects.create(
        tenant=tenant, artifact=art, title=title, description=description
    )


class _TimeoutCapturingProvider:
    """Provider double recording the per-call timeout it was handed."""

    PROVIDER_NAME = "capture"

    def __init__(self, response: str = "[]") -> None:
        self.response = response
        self.calls: List[Dict[str, Any]] = []

    def complete(
        self,
        prompt: str,
        *,
        purpose: str = "",
        context: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> str:
        self.calls.append({"purpose": purpose, "timeout": timeout})
        return self.response


class _TimingOutProvider:
    """Provider double failing the way a real timeout does (issue #342)."""

    PROVIDER_NAME = "capture"

    def __init__(self, timeout_seconds: float = LONG_TIMEOUT) -> None:
        self._timeout_seconds = timeout_seconds

    def complete(self, *_args: Any, **_kwargs: Any) -> str:
        raise LlmTransportError(
            f"LLM provider 'capture' call failed (timeout): TimeoutError: "
            f"operation on 'llm:capture' exceeded {self._timeout_seconds}s timeout"
        )


def _patch_provider(monkeypatch, provider) -> None:
    monkeypatch.setattr(
        "llm_adapter.providers.get_provider", lambda *a, **k: provider
    )


def _seed_findings(tenant: Tenant, workspace: Workspace) -> None:
    """Create content that yields at least one missing-link audit finding."""
    _need(tenant, workspace, "Login authentication need", "Users must authenticate.")
    _requirement(
        tenant,
        workspace,
        "Login authentication requirement",
        "The system shall authenticate users securely.",
    )


# ---------------------------------------------------------------------------
# 1. The three workspace-wide flows use the long timeout
# ---------------------------------------------------------------------------


class TestWorkspaceWideFlowsUseLongTimeout:
    def test_derive_glossary_from_workspace(self, tenant, workspace, ctx, monkeypatch):
        provider = _TimeoutCapturingProvider(json.dumps([]))
        _patch_provider(monkeypatch, provider)

        with _active(tenant):
            _requirement(tenant, workspace, "Some requirement")
            AiDerivationService().derive_glossary_from_workspace(ctx, workspace.id)

        assert provider.calls, "the flow must have called the provider"
        assert provider.calls[0]["purpose"] == "derive_glossary_from_workspace"
        assert provider.calls[0]["timeout"] == float(LONG_TIMEOUT)

    def test_traceability_suggest_links(self, tenant, workspace, ctx, monkeypatch):
        provider = _TimeoutCapturingProvider(json.dumps([]))
        _patch_provider(monkeypatch, provider)

        with _active(tenant):
            _seed_findings(tenant, workspace)
            TraceabilitySuggestService().suggest_links(
                workspace.id, ctx, tier="standard"
            )

        assert provider.calls, "the flow must have called the provider"
        assert provider.calls[0]["purpose"] == "traceability_suggest_links"
        assert provider.calls[0]["timeout"] == float(LONG_TIMEOUT)

    def test_audit_ai_review(self, tenant, workspace, ctx, monkeypatch):
        provider = _TimeoutCapturingProvider(json.dumps([]))
        _patch_provider(monkeypatch, provider)

        with _active(tenant):
            _seed_findings(tenant, workspace)
            AiReviewService().review(workspace.id, ctx, tier="extended")

        assert provider.calls, "the flow must have called the provider"
        assert provider.calls[0]["purpose"] == "audit_ai_review"
        assert provider.calls[0]["timeout"] == float(LONG_TIMEOUT)


class TestSingleArtifactFlowKeepsShortTimeout:
    """Regression guard: the fix must not raise the cap for everything."""

    def test_derive_testcase_from_requirement(
        self, tenant, workspace, ctx, monkeypatch
    ):
        provider = _TimeoutCapturingProvider(json.dumps({"title": "T", "steps": []}))
        _patch_provider(monkeypatch, provider)

        with _active(tenant):
            req = _requirement(tenant, workspace, "Single artifact requirement")
            with contextlib.suppress(LlmResponseError):
                AiDerivationService().derive_testcase_from_requirement(ctx, req.id)

        assert provider.calls, "the flow must have called the provider"
        assert provider.calls[0]["timeout"] == float(SHORT_TIMEOUT)


# ---------------------------------------------------------------------------
# 2. A timeout that still happens becomes a clean, catchable error
# ---------------------------------------------------------------------------


class TestTimeoutProducesCleanError:
    """The MCP/REST boundaries catch these types — no unhandled 500 path."""

    def test_derive_glossary_maps_transport_error(
        self, tenant, workspace, ctx, monkeypatch
    ):
        _patch_provider(monkeypatch, _TimingOutProvider())

        with _active(tenant):
            _requirement(tenant, workspace, "Some requirement")
            with pytest.raises(LlmResponseError) as exc_info:
                AiDerivationService().derive_glossary_from_workspace(ctx, workspace.id)

        assert "timeout" in str(exc_info.value).lower()

    def test_suggest_links_maps_transport_error(
        self, tenant, workspace, ctx, monkeypatch
    ):
        _patch_provider(monkeypatch, _TimingOutProvider())

        with _active(tenant):
            _seed_findings(tenant, workspace)
            with pytest.raises(SuggestLinksResponseError) as exc_info:
                TraceabilitySuggestService().suggest_links(
                    workspace.id, ctx, tier="standard"
                )

        message = str(exc_info.value)
        assert str(LONG_TIMEOUT) in message
        assert "LLM_LONG_RUNNING_TIMEOUT" in message

    def test_ai_review_maps_transport_error(self, tenant, workspace, ctx, monkeypatch):
        _patch_provider(monkeypatch, _TimingOutProvider())

        with _active(tenant):
            _seed_findings(tenant, workspace)
            with pytest.raises(AiReviewResponseError) as exc_info:
                AiReviewService().review(workspace.id, ctx, tier="extended")

        message = str(exc_info.value)
        assert str(LONG_TIMEOUT) in message
        assert "LLM_LONG_RUNNING_TIMEOUT" in message
