"""Plan P0.6 — an incomplete interview proposal reports its missing fields.

Acceptance cases (docs/plans/2026-11-26-interview-und-listen-modus.md, §5 A2
and P0.7):

  a. A Risk proposal without ``probability`` → ``propose`` names it in
     ``missing_fields`` and raises nothing (it is incomplete, not malformed).
  b. The same proposal through ``formalize`` → ``MISSING_REQUIRED_FIELD`` and
     no artifact is created.
  c. A complete Risk proposal → ``formalize`` creates the artifact.
  d. An unknown field → ``UNKNOWN_FIELD`` (a typo is a shape error, never
     reported as "missing required").
  e. A multi chat turn with an incomplete proposal names the missing field in
     ``reply``/``missing_fields``; a second, complete turn adds no follow-up
     sentence.

The missing-field rule is the ONE derivation in
``attribute_contract_service.artifact_field_contract``; these tests pin the
readout/write/chat surfaces to it without re-deriving it here.
"""
from __future__ import annotations

import contextlib
import json
from collections.abc import Iterator

import pytest

from application.interview_proposal_errors import ProposalValidationError
from application.interview_service import InterviewService
from auth_tenancy.context import AuthContext, AuthMethod
from mcp_server.tools.interview import InterviewToolGroup
from persistence.models import (
    InterviewSession,
    Risk,
    Tenant,
    User,
    Workspace,
)
from persistence.tenancy import TenantContext
from persistence.tests.factories import make_workspace

pytestmark = pytest.mark.django_db

VALID_API_KEY = "reqlo_placeholder_testkey1234"

#: Risk without its two mandatory fields — the exact case the live plugin test
#: hit ("invalid fields for 'Risk' … 'probability'").
_INCOMPLETE_RISK_PROPOSAL = [
    {"type": "Risk", "fields": {"title": "Display overpressure"}, "links": []}
]

_COMPLETE_RISK_PROPOSAL = [
    {
        "type": "Risk",
        "fields": {
            "title": "Display overpressure",
            "probability": "high",
            "impact": "high",
        },
        "links": [],
    }
]


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
    return Tenant.objects.create(name="IV-Missing-Fields Tenant", slug="iv-missing-fields")


@pytest.fixture
def workspace(tenant: Tenant) -> Workspace:
    with _active(tenant):
        return make_workspace(tenant, name="IV-Missing-Fields WS")


@pytest.fixture
def german_workspace(tenant: Tenant) -> Workspace:
    """Workspace with an explicit German AI language (follow-up must follow it)."""
    with _active(tenant):
        return make_workspace(
            tenant, name="IV-Missing-Fields DE WS", ai_language="de"
        )


@pytest.fixture
def editor_user(tenant: Tenant) -> User:
    return User.objects.create(
        username="iv-missing-fields-editor",
        email="missing-fields@example.test",
        tenant=tenant,
    )


@pytest.fixture
def editor_ctx(editor_user: User) -> AuthContext:
    return AuthContext(
        user_id=editor_user.id,
        tenant_id=editor_user.tenant.id,
        active_roles=("editor",),
        auth_method=AuthMethod.API_KEY,
    )


def _multi_session(
    tenant: Tenant, ws: Workspace, proposal: list[dict] | None = None
) -> InterviewSession:
    with _active(tenant):
        snapshot = {"pending_proposal": proposal} if proposal is not None else {}
        return InterviewSession.objects.create(
            tenant=tenant,
            workspace=ws,
            artifact_type=None,
            session_kind=InterviewSession.SESSION_KIND_MULTI,
            grounding_snapshot=snapshot,
        )


class _FakeProvider:
    """Provider double whose ``complete()`` returns a fixed multi-protocol reply."""

    def __init__(self, reply: str):
        self._reply = reply
        self.last_prompt = None

    def complete(self, prompt, *, purpose="", context=None, timeout=None):
        self.last_prompt = prompt
        return self._reply


def _fenced(items: list[dict]) -> str:
    return f"Here is the proposal:\n```json\n{json.dumps(items)}\n```"


class TestProposeReportsMissingFields:
    def test_incomplete_risk_proposal_names_probability_without_raising(
        self, tenant, workspace, editor_ctx
    ):
        """Case (a): readout, not an error."""
        session = _multi_session(tenant, workspace, _INCOMPLETE_RISK_PROPOSAL)

        with _active(tenant):
            result = InterviewService().propose(editor_ctx, session.id)

        assert result["proposal"] is not None
        assert result["proposal"][0]["type"] == "Risk"
        assert result["missing_fields"] == [
            {
                "item_index": 0,
                "artifact_type": "Risk",
                "fields": ["probability", "impact"],
            }
        ]

    def test_complete_risk_proposal_reports_no_missing_fields(
        self, tenant, workspace, editor_ctx
    ):
        session = _multi_session(tenant, workspace, _COMPLETE_RISK_PROPOSAL)

        with _active(tenant):
            result = InterviewService().propose(editor_ctx, session.id)

        assert result["missing_fields"] == []
        assert result["proposal"] == _COMPLETE_RISK_PROPOSAL

    def test_propose_proposal_round_trips_into_formalize_unchanged(
        self, tenant, workspace, editor_ctx
    ):
        """m6 / plan P0 gate: the readout IS writable, byte for byte.

        ``propose()`` validates and normalises the stored proposal, so feeding
        ``result["proposal"]`` straight into ``formalize()`` must create the
        artifact without a single caller-side edit. This is the claim the whole
        readout contract rests on; the other tests assert the halves separately.
        """
        session = _multi_session(tenant, workspace, _COMPLETE_RISK_PROPOSAL)

        with _active(tenant):
            readout = InterviewService().propose(editor_ctx, session.id)
            assert readout["missing_fields"] == []
            assert readout["proposal"] is not None

            result = InterviewService().formalize(
                editor_ctx,
                session.id,
                confirmed_proposal=readout["proposal"],
            )

        assert result["status"] == "completed"
        assert len(result["created"]) == 1
        with _active(tenant):
            created = Risk.objects.get(title="Display overpressure")
            assert created.probability == "high"
            assert created.impact == "high"

    def test_mcp_propose_exposes_missing_fields_next_to_the_proposal(
        self, tenant, workspace, editor_ctx
    ):
        """Both transports expose the same readout shape (P0.6)."""
        session = _multi_session(tenant, workspace, _INCOMPLETE_RISK_PROPOSAL)

        with _active(tenant):
            result = InterviewToolGroup().execute_tool(
                tool_name="interview.propose",
                params={"session_id": str(session.id)},
                auth_context=editor_ctx,
                api_key=VALID_API_KEY,
            )

        assert result.success is True
        assert result.data["proposal"][0]["type"] == "Risk"
        assert result.data["missing_fields"] == [
            {
                "item_index": 0,
                "artifact_type": "Risk",
                "fields": ["probability", "impact"],
            }
        ]


class TestFormalizeGate:
    def test_incomplete_proposal_is_rejected_and_creates_nothing(
        self, tenant, workspace, editor_ctx
    ):
        """Case (b): same code, field names, zero artifacts."""
        session = _multi_session(tenant, workspace)

        with _active(tenant):
            risks_before = Risk.objects.filter(workspace_id=workspace.id).count()

        with pytest.raises(ProposalValidationError) as excinfo:
            with _active(tenant):
                InterviewService().formalize(
                    editor_ctx,
                    session.id,
                    confirmed_proposal=_INCOMPLETE_RISK_PROPOSAL,
                )

        error = excinfo.value
        assert error.code == "MISSING_REQUIRED_FIELD"
        assert error.details["artifact_type"] == "Risk"
        assert error.details["fields"] == ["probability", "impact"]
        assert error.field == "probability"

        with _active(tenant):
            assert Risk.objects.filter(workspace_id=workspace.id).count() == risks_before
            assert Risk.objects.filter(title="Display overpressure").count() == 0
            from persistence.models import InterviewSessionArtifact

            assert (
                InterviewSessionArtifact.objects.filter(session=session).count() == 0
            )

    def test_complete_proposal_creates_the_artifact(
        self, tenant, workspace, editor_ctx
    ):
        """Case (c): the readout contract is actually writable."""
        session = _multi_session(tenant, workspace)

        with _active(tenant):
            result = InterviewService().formalize(
                editor_ctx, session.id, confirmed_proposal=_COMPLETE_RISK_PROPOSAL
            )

        assert result["status"] == "completed"
        assert len(result["created"]) == 1
        with _active(tenant):
            created = Risk.objects.get(title="Display overpressure")
            assert created.probability == "high"
            assert created.impact == "high"

    def test_unknown_field_is_a_shape_error_not_a_missing_field(
        self, tenant, workspace, editor_ctx
    ):
        """Case (d): a typo must never be reported as 'missing required'."""
        proposal = [
            {"type": "Risk", "fields": {"titel": "R", "probability": "high", "impact": "low"}}
        ]
        session = _multi_session(tenant, workspace, proposal)

        with _active(tenant):
            with pytest.raises(ProposalValidationError) as excinfo:
                InterviewService().propose(editor_ctx, session.id)
        assert excinfo.value.code == "UNKNOWN_FIELD"
        assert excinfo.value.field == "titel"

        with pytest.raises(ProposalValidationError) as excinfo:
            with _active(tenant):
                InterviewService().formalize(
                    editor_ctx, session.id, confirmed_proposal=proposal
                )
        assert excinfo.value.code == "UNKNOWN_FIELD"


class TestChatTurnAsksForMissingFields:
    def test_incomplete_proposal_turn_asks_for_probability(
        self, tenant, workspace, editor_ctx, monkeypatch
    ):
        """Case (e), first half: reply and payload name the missing field."""
        session = _multi_session(tenant, workspace)
        provider = _FakeProvider(_fenced(_INCOMPLETE_RISK_PROPOSAL))
        monkeypatch.setattr(
            InterviewService, "_resolve_provider", lambda self: (provider, "mock", None)
        )

        with _active(tenant):
            result = InterviewService().generate_chat_turn(
                editor_ctx, session.id, "The display must alarm above 8 bar."
            )

        assert result["missing_fields"] == [
            {
                "item_index": 0,
                "artifact_type": "Risk",
                "fields": ["probability", "impact"],
            }
        ]
        # Same value inside state, so a client reading only state sees it.
        assert result["state"]["missing_fields"] == result["missing_fields"]
        # Deterministic server-side follow-up question names the gap.
        assert "Before I can file this Risk" in result["reply"]
        assert "probability" in result["reply"]
        assert "impact" in result["reply"]

    def test_german_workspace_gets_the_german_follow_up_sentence(
        self, tenant, german_workspace, editor_ctx, monkeypatch
    ):
        """The deterministic follow-up follows ``Workspace.ai_language``.

        ``ai_language = "de"`` must render the German template, not the English
        one -- the sentence is appended server-side next to an LLM reply whose
        language the same setting governs.
        """
        session = _multi_session(tenant, german_workspace)
        provider = _FakeProvider(_fenced(_INCOMPLETE_RISK_PROPOSAL))
        monkeypatch.setattr(
            InterviewService, "_resolve_provider", lambda self: (provider, "mock", None)
        )

        with _active(tenant):
            result = InterviewService().generate_chat_turn(
                editor_ctx, session.id, "Das Display muss über 8 bar alarmieren."
            )

        assert result["missing_fields"][0]["fields"] == ["probability", "impact"]
        # Distinctive German fragment of _MISSING_FIELDS_FOLLOWUP_TEXT["de"].
        assert "Bevor ich diesen Risk anlegen kann, fehlen mir noch:" in result["reply"]
        assert "Before I can file this Risk" not in result["reply"]

    def test_auto_workspace_keeps_the_english_follow_up_sentence(
        self, tenant, workspace, editor_ctx, monkeypatch
    ):
        """``auto`` without a German content language keeps the English text."""
        assert workspace.ai_language == "auto"
        session = _multi_session(tenant, workspace)
        provider = _FakeProvider(_fenced(_INCOMPLETE_RISK_PROPOSAL))
        monkeypatch.setattr(
            InterviewService, "_resolve_provider", lambda self: (provider, "mock", None)
        )

        with _active(tenant):
            result = InterviewService().generate_chat_turn(
                editor_ctx, session.id, "The display must alarm above 8 bar."
            )

        assert "Before I can file this Risk" in result["reply"]
        assert "Bevor ich diesen Risk anlegen kann" not in result["reply"]

    def test_complete_second_turn_adds_no_follow_up_sentence(
        self, tenant, workspace, editor_ctx, monkeypatch
    ):
        """Case (e), second half: a complete proposal needs no follow-up."""
        session = _multi_session(tenant, workspace)
        provider = _FakeProvider(_fenced(_COMPLETE_RISK_PROPOSAL))
        monkeypatch.setattr(
            InterviewService, "_resolve_provider", lambda self: (provider, "mock", None)
        )

        with _active(tenant):
            result = InterviewService().generate_chat_turn(
                editor_ctx,
                session.id,
                "Probability is high and impact is high.",
            )

        assert result["missing_fields"] == []
        assert "Before I can file" not in result["reply"]

    def test_follow_up_sentence_is_not_duplicated_when_reply_names_the_fields(
        self, tenant, workspace, editor_ctx, monkeypatch
    ):
        """Idempotent: a model reply that already asks is left untouched."""
        session = _multi_session(tenant, workspace)
        reply = (
            "Sure. Before I can file the risk, what are its probability and impact?"
            "\n```json\n" + json.dumps(_INCOMPLETE_RISK_PROPOSAL) + "\n```"
        )
        provider = _FakeProvider(reply)
        monkeypatch.setattr(
            InterviewService, "_resolve_provider", lambda self: (provider, "mock", None)
        )

        with _active(tenant):
            result = InterviewService().generate_chat_turn(
                editor_ctx, session.id, "Here is a risk."
            )

        # Missing fields are still reported, but the sentence is not doubled.
        assert result["missing_fields"][0]["fields"] == ["probability", "impact"]
        assert result["reply"].count("Before I can file") == 1
        assert result["reply"] == reply

    def test_a_follow_up_turn_reports_the_same_proposal_it_reports_missing_fields_for(
        self, tenant, workspace, editor_ctx, monkeypatch
    ):
        """m1: ``proposal`` and ``missing_fields`` describe the SAME proposal.

        A turn that emits no new fenced proposal still has the stored,
        incomplete pending proposal -- the one ``missing_fields`` belongs to.
        Before m1 the payload answered ``proposal: null`` next to a non-empty
        ``missing_fields``, which no client can act on. ``has_proposal`` in the
        emitted event is derived from the same value.
        """
        from application.models import DomainEventOutbox

        session = _multi_session(tenant, workspace)
        first_provider = _FakeProvider(_fenced(_INCOMPLETE_RISK_PROPOSAL))
        monkeypatch.setattr(
            InterviewService,
            "_resolve_provider",
            lambda self: (first_provider, "mock", None),
        )
        with _active(tenant):
            first = InterviewService().generate_chat_turn(
                editor_ctx, session.id, "The display must alarm above 8 bar."
            )

        # Second turn: a plain reply with no fenced proposal.
        monkeypatch.setattr(
            InterviewService,
            "_resolve_provider",
            lambda self: (_FakeProvider("Thanks, noted."), "mock", None),
        )
        with _active(tenant):
            second = InterviewService().generate_chat_turn(
                editor_ctx, session.id, "It is risky."
            )
            event = (
                DomainEventOutbox.objects.filter(
                    entity_id=session.id,
                    event_type=DomainEventOutbox.EventType.INTERVIEW_CHAT_TURN,
                )
                .order_by("-created_at")
                .first()
            )

        assert second["proposal"] == first["proposal"]
        assert second["proposal"][0]["type"] == "Risk"
        assert second["missing_fields"] == first["missing_fields"]
        assert second["missing_fields"] != []
        assert second["state"]["missing_fields"] == second["missing_fields"]
        assert event is not None
        assert event.payload["has_proposal"] is True
        assert event.payload["missing_fields"] == second["missing_fields"]
