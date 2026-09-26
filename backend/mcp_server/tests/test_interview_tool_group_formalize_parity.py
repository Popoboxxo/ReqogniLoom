"""CR-05 — REST/MCP parity for ``interview.formalize``.

Audit finding CR-05 (W2 slice): ``POST /api/v1/interviews/{id}/formalize/``
forwarded a caller-supplied ``confirmed_proposal`` to
``InterviewService.formalize`` (``rest_api/interview_views.py``), but the MCP
tool's ``inputSchema`` had no such property and ``_handle_formalize`` called
``formalize(auth_context, session_id)`` with no third argument. Since
``_formalize_multi`` raises ``ValidationError("confirmed_proposal is
required for a multi-mode interview")`` on an empty proposal, **every**
multi-mode formalize over MCP was permanently blocked — the tool description
advertised a capability that no caller could ever reach.

This module pins the resulting parity contract, using the same real-service
(never mocked) style as ``test_interview_formalize_issue736.py``:

* multi + proposal succeeds and returns the same ``created[]`` + ``status``
  contract REST returns (``test_interview_views_multi.py``);
* multi without a proposal still fails, with the *same* VALIDATION_ERROR
  channel and message as REST — the error seam was never the defect and is
  deliberately not changed;
* single-kind formalize still works with ``session_id`` alone. This is the
  regression guard that matters most: ``confirmed_proposal`` is an OPTIONAL
  schema property precisely because making it required would break every
  existing single-mode MCP client.
"""
from __future__ import annotations

import pytest

from auth_tenancy.context import AuthContext, AuthMethod
from mcp_server.tools.interview import InterviewToolGroup
from persistence.models import Tenant, User, Workspace
from persistence.tenancy import TenantContext
from workflow.services import create_default_workflow

pytestmark = pytest.mark.django_db

# Fixture-only key: no real credential, just a shape the auth stub accepts. The
# ``placeholder`` marker is the W1 secret scanner's documented allowlist token
# (``_SAFE_PATTERNS``) — the scanner pattern still matches, the allowlist is
# what clears it, exactly as in
# rest_api/tests/test_readonly_and_unknown_field_rejection_915_916.py.
VALID_API_KEY = "reqlo_placeholder_testkey1234"


@pytest.fixture
def tenant(db: None) -> Tenant:
    return Tenant.objects.create(name="CR05 Tenant", slug="cr05-tenant")


@pytest.fixture
def workspace(tenant: Tenant) -> Workspace:
    """A workspace with a provisioned ``Interview`` workflow definition.

    Mirrors the real stack, where workspace creation provisions definitions.
    Without one the engine transition is swallowed by the legacy fallback and
    the session's state never leaves ``in_progress``.
    """
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(tenant=tenant, name="WS")
        create_default_workflow(
            workspace_id=workspace.id,
            preset="interview_default",
            item_type="Interview",
            tenant_id=tenant.id,
        )
        return workspace
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def user(tenant: Tenant) -> User:
    """A real User row: the multi adapter's ``Artifact.created_by`` is a real FK."""
    return User.objects.create(
        username="cr05-user",
        email="cr05-user@example.test",
        tenant=tenant,
        is_active=True,
    )


@pytest.fixture
def ctx(tenant: Tenant, user: User) -> AuthContext:
    return AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=("editor",),
        auth_method=AuthMethod.API_KEY,
    )


def _start(group: InterviewToolGroup, ctx: AuthContext, workspace, **extra):
    started = group.execute_tool(
        tool_name="interview.start",
        params={"workspace_id": str(workspace.id), **extra},
        auth_context=ctx,
        api_key=VALID_API_KEY,
    )
    assert started.success is True, started.message
    return started.data["id"]


def _formalize(group: InterviewToolGroup, ctx: AuthContext, params: dict):
    return group.execute_tool(
        tool_name="interview.formalize",
        params=params,
        auth_context=ctx,
        api_key=VALID_API_KEY,
    )


class TestFormalizeParity:
    def test_multi_formalize_with_proposal_succeeds(self, ctx, workspace):
        """The capability the tool description already advertised (CR-05)."""
        group = InterviewToolGroup()
        session_id = _start(group, ctx, workspace, session_kind="multi")
        proposal = [{"type": "StakeholderNeed", "fields": {"title": "Need A"}, "links": []}]

        result = _formalize(
            group, ctx, {"session_id": session_id, "confirmed_proposal": proposal}
        )

        assert result.success is True, result.message
        # Identical fachlicher Vertrag to the REST test
        # (rest_api/tests/test_interview_views_multi.py::test_formalize_multi_
        # accepts_confirmed_proposal): a `created` list plus a `status`.
        assert len(result.data["created"]) == 1, result.data
        assert result.data["status"] == "completed", result.data
        assert result.data["created"][0]["artifact_type"] == "StakeholderNeed"

    def test_multi_formalize_without_proposal_is_a_validation_error(self, ctx, workspace):
        """The error channel is unchanged — it was never the defect."""
        group = InterviewToolGroup()
        session_id = _start(group, ctx, workspace, session_kind="multi")

        result = _formalize(group, ctx, {"session_id": session_id})

        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR", result
        assert "confirmed_proposal" in (result.message or ""), result.message

    def test_single_formalize_still_works_without_a_proposal(self, ctx, workspace):
        """Regression guard: `confirmed_proposal` must stay OPTIONAL.

        Making it `required` in the inputSchema (or indexing `params[...]`
        instead of `params.get(...)`) would break every existing single-mode
        MCP client, which passes `session_id` alone.
        """
        group = InterviewToolGroup()
        session_id = _start(group, ctx, workspace, artifact_type="Requirement")
        for field, value in (
            ("title", "Parity probe"),
            ("rationale", "single-mode path must be unaffected"),
        ):
            answered = group.execute_tool(
                tool_name="interview.answer",
                params={"session_id": session_id, "field": field, "value": value},
                auth_context=ctx,
                api_key=VALID_API_KEY,
            )
            assert answered.success is True, answered.message

        result = _formalize(group, ctx, {"session_id": session_id})

        assert result.success is True, result.message
        assert result.data["status"] == "completed", result.data
        assert len(result.data["resulting_artifact_ids"]) == 1, result.data

    def test_confirmed_proposal_is_an_optional_schema_property(self):
        """Schema-level parity assertion, independent of any DB state.

        Optional, not required: a single-mode client must remain valid.
        """
        schemas = {
            s["name"]: s["inputSchema"]
            for s in InterviewToolGroup()._TOOL_SCHEMAS
            if s["name"] == "interview.formalize"
        }
        formalize_schema = schemas["interview.formalize"]
        assert "confirmed_proposal" in formalize_schema["properties"], formalize_schema
        assert "confirmed_proposal" not in formalize_schema["required"], formalize_schema
        assert formalize_schema["required"] == ["session_id"], formalize_schema
        assert formalize_schema["properties"]["confirmed_proposal"]["type"] == "array"
