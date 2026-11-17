"""AI-005 — ``interview.formalize`` validates proposal fields for MCP callers too.

An AUTHOR-scoped API key is a first-class content-writing caller of the MCP
surface. Before the service-layer gate, a proposal supplied directly to
``interview.formalize`` flowed unchecked into ``create_X(**fields)``, so an
AUTHOR key could smuggle server-owned fields (``status``/``owner``) or
oversized strings past the LLM-parse path. These tests pin that the MCP tool
cannot bypass the SAME service-layer validation REST/UI pass through.
"""
from __future__ import annotations

import contextlib
from collections.abc import Iterator

import pytest

from auth_tenancy.context import AuthContext, AuthMethod
from mcp_server.tools.interview import InterviewToolGroup
from persistence.models import InterviewSessionArtifact, Tenant, User, Workspace
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db

# Fixture-only key: no real credential, just a shape the auth stub accepts. The
# ``placeholder`` marker is the W1 secret scanner's documented allowlist token.
VALID_API_KEY = "reqlo_placeholder_testkey1234"


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
    return Tenant.objects.create(name="AI005 Tenant", slug="ai005-tenant")


@pytest.fixture
def workspace(tenant: Tenant) -> Workspace:
    with _active(tenant):
        return Workspace.objects.create(tenant=tenant, name="AI005 WS")


@pytest.fixture
def user(tenant: Tenant) -> User:
    with _active(tenant):
        return User.objects.create(
            username="ai005-author",
            email="author@example.test",
            tenant=tenant,
            is_active=True,
        )


@pytest.fixture
def author_ctx(tenant: Tenant, user: User) -> AuthContext:
    # `scope="author"` is the AUTHOR-tier API-key capability (content writes
    # allowed, governance denied). WRITE requires exactly that tier, so this
    # caller passes the write permission check and reaches the field gate.
    return AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=("editor",),
        auth_method=AuthMethod.API_KEY,
        scope="author",
    )


def _start_multi(group: InterviewToolGroup, ctx: AuthContext, workspace: Workspace) -> str:
    started = group.execute_tool(
        tool_name="interview.start",
        params={"workspace_id": str(workspace.id), "session_kind": "multi"},
        auth_context=ctx,
        api_key=VALID_API_KEY,
    )
    assert started.success is True, started.message
    return started.data["id"]


def _formalize(group: InterviewToolGroup, ctx: AuthContext, session_id: str, proposal: list):
    return group.execute_tool(
        tool_name="interview.formalize",
        params={"session_id": session_id, "confirmed_proposal": proposal},
        auth_context=ctx,
        api_key=VALID_API_KEY,
    )


class TestAuthorCannotBypassFieldValidation:
    def test_author_cannot_smuggle_reserved_field(self, tenant, workspace, author_ctx):
        group = InterviewToolGroup()
        session_id = _start_multi(group, author_ctx, workspace)
        proposal = [
            {"type": "Requirement", "fields": {"title": "R", "status": "approved"}, "links": []}
        ]

        result = _formalize(group, author_ctx, session_id, proposal)

        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR", result
        assert "status" in (result.message or ""), result.message
        with _active(tenant):
            assert InterviewSessionArtifact.objects.filter(session_id=session_id).count() == 0

    def test_author_cannot_smuggle_oversized_title(self, tenant, workspace, author_ctx):
        group = InterviewToolGroup()
        session_id = _start_multi(group, author_ctx, workspace)
        proposal = [
            {"type": "Requirement", "fields": {"title": "x" * 10_000}, "links": []}
        ]

        result = _formalize(group, author_ctx, session_id, proposal)

        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR", result
        assert "limit" in (result.message or ""), result.message
        with _active(tenant):
            assert InterviewSessionArtifact.objects.filter(session_id=session_id).count() == 0

    def test_author_legitimate_proposal_still_succeeds(self, tenant, workspace, author_ctx):
        # Control: the gate must not turn every AUTHOR write into a rejection.
        group = InterviewToolGroup()
        session_id = _start_multi(group, author_ctx, workspace)
        proposal = [{"type": "Requirement", "fields": {"title": "Fine"}, "links": []}]

        result = _formalize(group, author_ctx, session_id, proposal)

        assert result.success is True, result.message
        assert result.data["status"] == "completed"
        assert len(result.data["created"]) == 1
