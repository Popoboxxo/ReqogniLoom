"""Issue #1990 — ``interview.propose`` output round-trips into ``formalize``.

The LLM-authored proposal used to carry three shape defects that only failed
at write time: a top-level ``title`` (instead of ``fields['title']``), a
server-owned field, and a trace-link type whose endpoint pair the workspace
catalog does not allow. At readout, ``propose`` now normalises the first and
explicitly rejects the other two with machine-readable reason codes.
"""
from __future__ import annotations

import contextlib
import json
from collections.abc import Iterator

import pytest

from application.interview_proposal_errors import ProposalValidationError
from application.interview_service import InterviewService
from application.interview_multi_protocol import (
    normalize_proposal_items,
    parse_multi_proposal,
    validate_proposal_link_pairs,
)
from auth_tenancy.context import AuthContext, AuthMethod
from link_types.builtin import BUILTIN_LINK_TYPES
from link_types.catalog import invalidate_workspace
from link_types.models import WorkspaceLinkTypeDefinition
from mcp_server.tools.interview import InterviewToolGroup
from persistence.models import InterviewSession, Tenant, User, Workspace
from persistence.tenancy import TenantContext
from persistence.tests.factories import make_workspace

pytestmark = pytest.mark.django_db

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
    return Tenant.objects.create(name="Proposal Validation Tenant", slug="proposal-validation")


@pytest.fixture
def workspace(tenant: Tenant) -> Workspace:
    with _active(tenant):
        return make_workspace(tenant, name="Proposal Validation WS")


@pytest.fixture
def editor_ctx(tenant: Tenant) -> AuthContext:
    with _active(tenant):
        user = User.objects.create(
            username="proposal-editor", email="proposal-editor@example.test", tenant=tenant
        )
    return AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=("editor",),
        auth_method=AuthMethod.API_KEY,
        scope="author",
    )


def _multi_session(tenant: Tenant, ws: Workspace, proposal: list[dict] | None = None) -> InterviewSession:
    with _active(tenant):
        snapshot = {"pending_proposal": proposal} if proposal is not None else {}
        return InterviewSession.objects.create(
            tenant=tenant,
            workspace=ws,
            artifact_type=None,
            session_kind=InterviewSession.SESSION_KIND_MULTI,
            grounding_snapshot=snapshot,
        )


def _seed_realizes(tenant: Tenant, ws: Workspace) -> None:
    """Materialise the builtin ``realizes`` type (Requirement -> Goal only)."""
    with _active(tenant):
        WorkspaceLinkTypeDefinition.unscoped.get_or_create(
            workspace_id=ws.id,
            key="realizes",
            defaults=dict(BUILTIN_LINK_TYPES["realizes"]),
        )
    invalidate_workspace(ws.id)


class TestProposalNormalisation:
    def test_top_level_title_is_folded_into_fields(self):
        raw = json.dumps([
            {"type": "Requirement", "title": "Need A", "fields": {}, "links": []}
        ])
        parsed = parse_multi_proposal(f"```json\n{raw}\n```")
        assert parsed is not None
        assert parsed[0]["fields"]["title"] == "Need A"

    def test_explicit_fields_title_wins_and_input_is_not_mutated(self):
        item = {"type": "Requirement", "title": "legacy", "fields": {"title": "explicit"}}
        result = normalize_proposal_items([item])
        assert result[0]["fields"]["title"] == "explicit"
        assert item["fields"] == {"title": "explicit"}

    def test_reserved_top_level_field_is_rejected_with_a_reason_code(self):
        item = {"type": "Requirement", "priority": "high", "fields": {"title": "R"}}
        with pytest.raises(ProposalValidationError) as excinfo:
            normalize_proposal_items([item])
        assert excinfo.value.code == "RESERVED_FIELD"
        assert excinfo.value.field == "priority"

    def test_unknown_top_level_field_is_rejected_with_a_reason_code(self):
        item = {"type": "Requirement", "typo": "x", "fields": {"title": "R"}}
        with pytest.raises(ProposalValidationError) as excinfo:
            normalize_proposal_items([item])
        assert excinfo.value.code == "UNEXPECTED_ITEM_FIELD"


class TestProposalReadoutValidation:
    def test_propose_returns_normalised_proposal(self, tenant, workspace, editor_ctx):
        proposal = [
            {"type": "Requirement", "title": "Need A", "fields": {}, "links": []}
        ]
        session = _multi_session(tenant, workspace, proposal)
        with _active(tenant):
            result = InterviewService().propose(editor_ctx, session.id)
        assert result["missing_fields"] == []
        assert result["proposal"] is not None
        assert result["proposal"][0]["fields"]["title"] == "Need A"

    def test_propose_rejects_invalid_item_shape_with_a_reason_code(
        self, tenant, workspace, editor_ctx
    ):
        """M2: a structural defect is an INVALID_PROPOSAL_SHAPE readout.

        It used to be a bare ``ValidationError`` with only a message, so the
        reason token the readout's other rejections carry was missing here.
        """
        proposal = [{"type": 1, "fields": {"title": "R"}, "links": []}]
        session = _multi_session(tenant, workspace, proposal)
        with _active(tenant):
            with pytest.raises(ProposalValidationError) as excinfo:
                InterviewService().propose(editor_ctx, session.id)
        assert excinfo.value.code == "INVALID_PROPOSAL_SHAPE"
        assert excinfo.value.item_index == 0
        assert "proposal item #0" in str(excinfo.value)

    def test_propose_rejects_reserved_field_with_machine_readable_reason(
        self, tenant, workspace, editor_ctx
    ):
        proposal = [
            {
                "type": "Requirement",
                "fields": {"title": "R", "status": "approved"},
                "links": [],
            }
        ]
        session = _multi_session(tenant, workspace, proposal)
        with _active(tenant):
            with pytest.raises(ProposalValidationError) as excinfo:
                InterviewService().propose(editor_ctx, session.id)
        assert excinfo.value.code == "RESERVED_FIELD"
        assert excinfo.value.field == "status"

    def test_propose_rejects_invalid_link_pair_before_the_write(
        self, tenant, workspace, editor_ctx
    ):
        _seed_realizes(tenant, workspace)
        proposal = [
            {"type": "ArchitectureElement", "fields": {"title": "A"}, "links": []},
            {
                "type": "Requirement",
                "fields": {"title": "R"},
                "links": [{"from": 0, "to": 1, "type": "realizes"}],
            },
        ]
        session = _multi_session(tenant, workspace, proposal)
        with _active(tenant):
            with pytest.raises(ProposalValidationError) as excinfo:
                InterviewService().propose(editor_ctx, session.id)
        assert excinfo.value.code == "INVALID_LINK_PAIR"
        assert excinfo.value.details["source_type"] == "ArchitectureElement"
        assert excinfo.value.details["target_type"] == "Requirement"

    def test_valid_link_pair_is_accepted(self, tenant, workspace, editor_ctx):
        _seed_realizes(tenant, workspace)
        proposal = [
            {"type": "Requirement", "fields": {"title": "R"}, "links": []},
            {
                "type": "Goal",
                "fields": {"title": "G"},
                "links": [{"from": 0, "to": 1, "type": "realizes"}],
            },
        ]
        session = _multi_session(tenant, workspace, proposal)
        with _active(tenant):
            assert InterviewService().propose(editor_ctx, session.id) == {
                "proposal": proposal,
                "missing_fields": [],
            }

    def test_normalised_proposal_can_be_formalized_unchanged(
        self, tenant, workspace, editor_ctx
    ):
        proposal = [
            {
                "type": "StakeholderNeed",
                "title": "Need A",
                "fields": {},
                "links": [],
            }
        ]
        session = _multi_session(tenant, workspace)
        with _active(tenant):
            readout = InterviewService().propose(editor_ctx, session.id)
            assert readout == {"proposal": None, "missing_fields": []}
            # Simulate the chat-turn parse path: the stored proposal is the
            # parse output, which is already normalised.
            stored = parse_multi_proposal(
                f"```json\n{json.dumps(proposal)}\n```"
            )
            assert stored is not None
            result = InterviewService().formalize(
                editor_ctx, session.id, confirmed_proposal=stored
            )
        assert result["status"] == "completed"
        assert len(result["created"]) == 1

    def test_link_pair_validation_is_safe_standalone(self, workspace):
        # Out-of-range endpoints are a shape error, never an IndexError.
        proposal = [
            {
                "type": "Requirement",
                "fields": {"title": "R"},
                "links": [{"from": 9, "to": 0, "type": "realizes"}],
            }
        ]
        with pytest.raises(ProposalValidationError) as excinfo:
            validate_proposal_link_pairs(proposal, workspace.id)
        assert excinfo.value.code == "INVALID_LINK_PAIR"


class TestMcpProposeReason:
    def test_mcp_propose_returns_machine_readable_reason(self, tenant, workspace, editor_ctx):
        proposal = [
            {
                "type": "Requirement",
                "fields": {"title": "R", "status": "approved"},
                "links": [],
            }
        ]
        session = _multi_session(tenant, workspace, proposal)
        group = InterviewToolGroup()
        with _active(tenant):
            result = group.execute_tool(
                tool_name="interview.propose",
                params={"session_id": str(session.id)},
                auth_context=editor_ctx,
                api_key=VALID_API_KEY,
            )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"
        assert result.details["reason"] == "RESERVED_FIELD"

    def test_mcp_formalize_returns_reason_and_details_like_propose(
        self, tenant, workspace, editor_ctx
    ):
        """M1: formalize must not drop the machine-readable refusal.

        Before the shared helper, ``_handle_formalize`` answered the bare
        message, so ``code``/``details`` existed over REST but not over MCP for
        the same rejection.
        """
        session = _multi_session(tenant, workspace)
        group = InterviewToolGroup()
        proposal = [{"type": "Risk", "fields": {"title": "R"}, "links": []}]
        with _active(tenant):
            result = group.execute_tool(
                tool_name="interview.formalize",
                params={
                    "session_id": str(session.id),
                    "confirmed_proposal": proposal,
                },
                auth_context=editor_ctx,
                api_key=VALID_API_KEY,
            )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"
        assert result.details["reason"] == "MISSING_REQUIRED_FIELD"
        assert result.details["item_index"] == 0
        assert result.details["field"] == "probability"
        assert result.details["fields"] == ["probability", "impact"]
