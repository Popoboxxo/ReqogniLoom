"""RFC #1002 PR C: ``memory_context`` is auto-injected into non-interview AI paths.

Only the interview chat path used to fill ``{memory_context}``. The central
render path (``application.prompt_resolver.resolve_and_render``) now computes
it automatically for every slot that declares it, so the other AI slots
receive retrieved memory without each call site wiring it up.

Pick one concrete non-interview slot (``testcase_derive``, one of the
``ai_derivation`` flows) and prove:

* the rendered prompt contains the memory block, and
* the injection is fail-open -- a disabled or unreachable memory backend
  leaves the render intact instead of breaking the AI call.

Note on scope: the task named ``requirement.validate`` and ``audit.ai_review``
as examples. ``requirement.validate`` is an MCP tool name for the provider-layer
``validate_artifact`` capability, which builds its prompt inside
``llm_adapter.providers`` and has neither a prompt slot nor an ``AuthContext``
to resolve memory with -- it is deliberately deferred (see the PR report).
``audit.ai_review`` is a module-constant template, not a catalog slot, and is
wired directly in ``AiReviewService.review`` instead.
"""
from __future__ import annotations

import pytest

from application.ai_derivation_service import AiDerivationService
from application.prompt_resolver import resolve_and_render
from auth_tenancy.context import AuthContext
from memory.backends import get_memory_backend
from persistence.tests.factories import active_tenant, make_user, make_workspace

pytestmark = pytest.mark.django_db


@pytest.fixture
def ctx_workspace():
    with active_tenant() as tenant:
        workspace = make_workspace(tenant)
        user = make_user(tenant)
        ctx = AuthContext(
            user_id=user.id,
            tenant_id=tenant.id,
            active_roles=("admin",),
            auth_method="test",
        )
        yield ctx, workspace


def test_ai_derivation_slot_receives_memory_context(ctx_workspace, monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
    ctx, workspace = ctx_workspace
    get_memory_backend().write(
        ctx.tenant_id, "workspace", workspace.id, "Project uses hexagonal architecture."
    )

    rendered = AiDerivationService._resolve_and_render(
        ctx,
        "testcase_derive",
        workspace.id,
        req_title="Login",
        req_description="Users log in.",
    )

    assert "hexagonal architecture" in rendered
    assert "{memory_context}" not in rendered


def test_injection_is_silent_when_workspace_memory_is_disabled(
    ctx_workspace, monkeypatch
):
    from memory.models import WorkspaceMemorySettings

    monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
    ctx, workspace = ctx_workspace
    get_memory_backend().write(
        ctx.tenant_id, "workspace", workspace.id, "Project uses hexagonal architecture."
    )
    WorkspaceMemorySettings.objects.create(
        tenant_id=ctx.tenant_id, workspace=workspace, enabled=False
    )

    rendered = resolve_and_render(
        "testcase_derive", ctx, workspace.id, req_title="Login", req_description="D"
    )

    assert "hexagonal architecture" not in rendered
    assert "Login" in rendered


def test_injection_is_fail_open_when_memory_backend_raises(ctx_workspace, monkeypatch):
    """Memory being down must never break an AI call (fail-open contract)."""
    ctx, workspace = ctx_workspace

    def _boom(*args, **kwargs):
        raise RuntimeError("memory backend unreachable")

    monkeypatch.setattr("memory.context_builder.build_memory_context", _boom)

    rendered = resolve_and_render(
        "testcase_derive", ctx, workspace.id, req_title="Login", req_description="D"
    )

    assert "Login" in rendered
    assert "{memory_context}" not in rendered


def test_a_slot_without_the_declared_variable_is_untouched(ctx_workspace, monkeypatch):
    """``interview.transcript_summary`` deliberately stays memory-free."""
    ctx, workspace = ctx_workspace
    render = resolve_and_render(
        "interview.transcript_summary",
        ctx,
        workspace.id,
        previous_summary="",
        overflow_json="[]",
    )

    assert "{memory_context}" not in render
