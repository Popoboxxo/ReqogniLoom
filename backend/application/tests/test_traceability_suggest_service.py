"""
TraceabilitySuggestService (SysEng 2.0 N3, ``traceability.suggest_links``,
first stage) — referential-integrity + no-pgvector tests.

UMSETZUNGSPLAN_SYSENG_2.0.md §3.2 + §4, Phase 4b. Acceptance criterion
(verbatim): "N3 (Erststufe): Ranking-Ausgabe referenziert existierende
Findings, keine pgvector-Abhängigkeit im Code." This module tests that
criterion literally:

* every suggestion's ``finding_index`` matches an actual finding from an
  independent :meth:`AuditService.run_audit` call on the same workspace/
  tier (same index, rule_id, artifact_ids);
* every ``ranked_candidates`` entry is a real, existing artifact from the
  workspace (a StakeholderNeed or Requirement, depending on the rule) — not
  an id invented by the LLM;
* a provider that proposes out-of-range / duplicate / non-integer indices
  has every one of them silently dropped rather than surfacing a fake
  reference (defense-in-depth, mirrors the N8 precedent in
  ``test_ai_review_service.py``);
* no ``pgvector`` / embedding / vector-search code path is involved
  anywhere in the module or the mock provider branch it calls.
"""
from __future__ import annotations

import contextlib
import inspect
import json
import re
from typing import Iterator
from uuid import UUID

import pytest

from application.audit_service import AuditFindingView, AuditReport, AuditService
from application.base import ProducerContextRequiredError
from application.traceability_suggest_service import TraceabilitySuggestService
from auth_tenancy.context import AuthContext, AuthMethod
from auth_tenancy.models import ApiKey
from link_types.workspace_store import provision_workspace_link_types
from persistence.models import (
    Artifact,
    Requirement,
    StakeholderNeed,
    Suggestion,
    Tenant,
    TraceLink,
    User,
    Workspace,
)
from persistence.tenancy import TenantContext
from traceability.audit import Finding, RemediationProposal, Severity

pytestmark = pytest.mark.django_db


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


@pytest.fixture
def tenant() -> Tenant:
    return Tenant.objects.create(name="SuggestLinks Tenant", slug="suggest-links-tenant")


@pytest.fixture
def user(tenant: Tenant) -> User:
    return User.objects.create(
        username="suggest-links-user", email="suggest-links@example.com", tenant=tenant
    )


@pytest.fixture
def workspace(tenant: Tenant) -> Workspace:
    with _active(tenant):
        workspace = Workspace.objects.create(tenant=tenant, name="SuggestLinks-WS")
        # ADR-019 WP5: suggest_links now persists a trace_link suggestion per
        # finding, which needs the workspace's built-in link-type catalog.
        provision_workspace_link_types(
            workspace_id=workspace.id, tenant_id=tenant.id
        )
        return workspace


@pytest.fixture
def api_key(user: User) -> ApiKey:
    """An active agent API key — the only principal that may produce (Zusage 7(f))."""
    # Arm the tenant context first: ApiKey is tenant-scoped and its manager
    # raises TenantContextNotSetError without an active tenant.
    with _active(user.tenant):
        return ApiKey.objects.create(
            tenant=user.tenant,
            user=user,
            name="suggest-links-agent",
            key_hash="sha256p1:suggest-links-agent",
            principal_type="agent",
            agent_label="SuggestLinks Agent",
        )


@pytest.fixture
def ctx(user: User, api_key: ApiKey) -> AuthContext:
    """Agent/API-key context: suggest_links is a production since ADR-019 WP5."""
    return AuthContext(
        user_id=user.id,
        tenant_id=user.tenant.id,
        active_roles=("editor",),
        auth_method=AuthMethod.API_KEY,
        api_key_id=api_key.id,
        actor_type="agent",
        agent_label="SuggestLinks Agent",
        tenant_name="SuggestLinks Tenant",
    )


@pytest.fixture
def human_ctx(user: User) -> AuthContext:
    """A human bearer context — must be refused fail-closed by the producer."""
    return AuthContext(
        user_id=user.id,
        tenant_id=user.tenant.id,
        active_roles=("editor",),
        auth_method=AuthMethod.BEARER_TOKEN,
        api_key_id=None,
        tenant_name="SuggestLinks Tenant",
    )


def _artifact(tenant: Tenant, workspace: Workspace, artifact_type: str) -> Artifact:
    return Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type=artifact_type
    )


def _requirement(
    tenant: Tenant, workspace: Workspace, title: str = "Req", description: str = ""
) -> Requirement:
    # Canonical catalog artifact_type: link-type validation matches it exactly,
    # and the audit resolves StakeholderNeeds/Requirements via the model join
    # (not this string), so the canonical casing is required for WP5's
    # persisted proposal links to be accepted.
    art = _artifact(tenant, workspace, "Requirement")
    return Requirement.objects.create(
        tenant=tenant, artifact=art, title=title, description=description
    )


def _need(
    tenant: Tenant, workspace: Workspace, title: str = "Need", description: str = ""
) -> StakeholderNeed:
    # Canonical catalog artifact_type (see _requirement).
    art = _artifact(tenant, workspace, "StakeholderNeed")
    return StakeholderNeed.objects.create(
        tenant=tenant, artifact=art, title=title, description=description
    )


def _all_candidate_ids(result) -> list[str]:
    """Flatten every ranked candidate's artifact_id across all suggestions."""
    ids: list[str] = []
    for s in result.suggestions:
        ids.extend(c.artifact_id for c in s.ranked_candidates)
    return ids


# ---------------------------------------------------------------------------
# Referential integrity — the literal acceptance criterion
# ---------------------------------------------------------------------------


class TestSuggestLinksReferentialIntegrity:
    def test_suggestions_reference_only_real_findings_and_real_candidates(
        self, tenant, workspace, ctx
    ):
        with _active(tenant):
            need_a = _need(
                tenant, workspace, "Login authentication need", "Users must authenticate securely."
            )
            need_b = _need(
                tenant, workspace, "Reporting dashboard need", "Users must see usage reports."
            )
            _requirement(
                tenant,
                workspace,
                "Login authentication requirement",
                "The system shall authenticate users securely.",
            )
            # Ground truth: an independent run_audit() call over the same data.
            ground_truth = AuditService().run_audit(workspace.id, ctx, tier="standard")

        assert ground_truth.findings, "fixture must yield at least one TRACE-P1 finding"
        truth_by_index = {fv.index: fv for fv in ground_truth.findings}
        real_need_ids = {str(need_a.artifact_id), str(need_b.artifact_id)}

        with _active(tenant):
            result = TraceabilitySuggestService().suggest_links(
                workspace.id, ctx, tier="standard"
            )

        assert result.total_findings == len(ground_truth.findings)
        assert result.suggestions, "mock provider is expected to rank at least one finding"

        for suggestion in result.suggestions:
            assert suggestion.finding_index in truth_by_index, (
                f"suggestion references finding index {suggestion.finding_index}, which "
                "does not exist in the independently-fetched audit report"
            )
            real = truth_by_index[suggestion.finding_index]
            assert suggestion.rule_id == real.finding.rule_id
            assert suggestion.source_artifact_id == real.finding.artifact_ids[0]
            assert suggestion.ranked_candidates, "suggestion must rank at least one candidate"
            for candidate in suggestion.ranked_candidates:
                assert candidate.artifact_id in real_need_ids, (
                    f"candidate {candidate.artifact_id} is not a real StakeholderNeed "
                    "that exists in this workspace"
                )

        # The keyword-overlap heuristic should rank the lexically-closer need
        # first (deterministic mock preserves the service's given order).
        top_candidate_ids = [
            s.ranked_candidates[0].artifact_id for s in result.suggestions
        ]
        assert str(need_a.artifact_id) in top_candidate_ids

    def test_over_daily_token_limit_raises_and_never_calls_provider(
        self, tenant, workspace, ctx, monkeypatch, settings
    ):
        """Code review regression: traceability.suggest_links (N3) bypassed
        REQ-106 entirely -- no is_over_daily_limit() check existed at all
        before this fix, unlike every other free-form LLM flow."""
        from unittest.mock import MagicMock

        from application.ai_derivation_service import LlmResponseError
        from persistence.models import TokenUsageRecord

        settings.TENANT_TOKEN_LIMIT_PER_DAY = 100
        with _active(tenant):
            TokenUsageRecord.objects.create(
                provider="mock", capability="traceability_suggest_links",
                input_tokens=150, output_tokens=0,
            )
            _need(
                tenant, workspace, "Login authentication need",
                "Users must authenticate securely.",
            )
            _requirement(
                tenant, workspace, "Login authentication requirement",
                "The system shall authenticate users securely.",
            )

        stub_provider = MagicMock()
        stub_provider.complete.return_value = "[]"
        monkeypatch.setattr(
            "llm_adapter.providers.get_provider", lambda *a, **k: stub_provider
        )

        with _active(tenant):
            with pytest.raises(LlmResponseError):
                TraceabilitySuggestService().suggest_links(
                    workspace.id, ctx, tier="standard"
                )
        # Load-bearing: the budget check runs BEFORE the provider is ever
        # called, not just that some exception was eventually raised.
        stub_provider.complete.assert_not_called()

    def test_records_estimated_token_counts_not_zero(
        self, tenant, workspace, ctx, monkeypatch
    ):
        """SA-26: traceability.suggest_links (N3) used to hardcode
        input_tokens=0 on record_token_usage(), leaving the daily budget
        (REQ-106) blind to this flow's real spend. Both sides must now be
        estimated from the actual prompt/completion via
        approximate_token_count()."""
        from unittest.mock import MagicMock

        from llm_adapter.token_tracking import approximate_token_count

        with _active(tenant):
            _need(
                tenant, workspace, "Login authentication need",
                "Users must authenticate securely.",
            )
            _requirement(
                tenant, workspace, "Login authentication requirement",
                "The system shall authenticate users securely.",
            )

        stub_provider = MagicMock()
        stub_provider.complete.return_value = "[]"
        monkeypatch.setattr(
            "llm_adapter.providers.get_provider", lambda *a, **k: stub_provider
        )
        record_mock = MagicMock()
        monkeypatch.setattr(
            "llm_adapter.token_tracking.record_token_usage", record_mock
        )

        with _active(tenant):
            TraceabilitySuggestService().suggest_links(
                workspace.id, ctx, tier="standard"
            )

        record_mock.assert_called_once()
        _, kwargs = record_mock.call_args
        sent_prompt = stub_provider.complete.call_args[0][0]
        assert kwargs["input_tokens"] == approximate_token_count(sent_prompt)
        assert kwargs["output_tokens"] == approximate_token_count("[]")
        assert kwargs["input_tokens"] > 0
        assert kwargs["output_tokens"] > 0

    def test_no_missing_link_findings_yields_no_suggestions_without_llm_call(
        self, tenant, workspace, ctx, monkeypatch
    ):
        def _boom():
            raise AssertionError("LLM provider must not be contacted when there are no eligible findings")

        monkeypatch.setattr("llm_adapter.providers.get_provider", _boom)

        with _active(tenant):
            # Minimal tier => RuleEngine returns zero findings (§2.2: "Minimal
            # = no SE-Auditor mandate"), so no missing-link finding exists.
            _requirement(tenant, workspace, "Root")
            result = TraceabilitySuggestService().suggest_links(
                workspace.id, ctx, tier="minimal"
            )

        assert result.suggestions == []
        assert result.total_findings == 0
        assert result.eligible_findings == 0

    def test_finding_with_empty_candidate_pool_yields_no_suggestion(
        self, tenant, workspace, ctx, monkeypatch
    ):
        """A TRACE-P1 finding with zero StakeholderNeeds in the workspace has
        nothing to rank — the LLM must not be contacted for it either."""

        def _boom():
            raise AssertionError("LLM provider must not be contacted when the candidate pool is empty")

        monkeypatch.setattr("llm_adapter.providers.get_provider", _boom)

        with _active(tenant):
            _requirement(tenant, workspace, "Orphan root requirement")
            ground_truth = AuditService().run_audit(workspace.id, ctx, tier="standard")

        assert ground_truth.findings, "fixture must yield a TRACE-P1/-P1b finding"

        with _active(tenant):
            result = TraceabilitySuggestService().suggest_links(
                workspace.id, ctx, tier="standard"
            )

        assert result.suggestions == []
        assert result.eligible_findings == 0


# ---------------------------------------------------------------------------
# R5/R7 (systemaudit 2026-09-02) — non-retryable provider errors fail fast
# ---------------------------------------------------------------------------


class TestSuggestLinksFailsFastOnNonRetryableProviderError:
    def test_suggest_links_fails_fast_on_non_retryable_provider_error(
        self, tenant, workspace, ctx, monkeypatch
    ):
        """R5/R7 (systemaudit 2026-09-02): a 401 from the real provider SDK
        must not make suggest_links wait out the full 180s
        LLM_LONG_RUNNING_TIMEOUT (``llm_adapter/timeouts.py``) -- it must
        abort within the resilience policy's own (short) budget instead.

        Reproduces the actual call chain traced for this task: suggest_links
        -> _complete() -> provider.complete() -> AnthropicProvider._chat()
        -> _resilient() -> resilient_call() ->
        PolicyEngine.execute_with_policy(), with the Anthropic SDK client
        itself raising a 401 immediately (no network delay) -- exactly the
        audit's reported failure mode.
        """
        import time

        import anthropic

        from application.traceability_suggest_service import SuggestLinksResponseError
        from llm_adapter.providers import AnthropicProvider, ProviderConfig

        class _Fake401(Exception):
            status_code = 401

        class _FakeMessages:
            def create(self, **kwargs):
                raise _Fake401("unauthorized")

        class _FakeAnthropicClient:
            def __init__(self, **kwargs):
                self.messages = _FakeMessages()

        monkeypatch.setattr(anthropic, "Anthropic", _FakeAnthropicClient)

        provider = AnthropicProvider(
            ProviderConfig(provider_name="anthropic", api_key="fake-key", timeout=30)
        )
        monkeypatch.setattr(
            "llm_adapter.providers.get_provider", lambda *a, **k: provider
        )

        with _active(tenant):
            _need(
                tenant, workspace, "Login authentication need",
                "Users must authenticate securely.",
            )
            _requirement(
                tenant, workspace, "Login authentication requirement",
                "The system shall authenticate users securely.",
            )

        started = time.monotonic()
        with _active(tenant):
            with pytest.raises(SuggestLinksResponseError):
                TraceabilitySuggestService().suggest_links(
                    workspace.id, ctx, tier="standard"
                )
        elapsed = time.monotonic() - started
        assert elapsed < 10.0, (
            f"took {elapsed:.1f}s — non-retryable error was retried/awaited"
        )


# ---------------------------------------------------------------------------
# Defense-in-depth — a misbehaving provider must not leak fake references
# ---------------------------------------------------------------------------


class TestSuggestLinksDropsHallucinatedIndices:
    def test_out_of_range_duplicate_and_non_int_indices_are_dropped(
        self, tenant, workspace, ctx, monkeypatch
    ):
        with _active(tenant):
            need_a = _need(tenant, workspace, "Only need")
            _requirement(tenant, workspace, "Root")
            ground_truth = AuditService().run_audit(workspace.id, ctx, tier="standard")

        assert ground_truth.findings
        valid_finding_index = ground_truth.findings[0].index
        real = ground_truth.findings[0]

        class _StubProvider:
            def complete(self, prompt, *, purpose="", context=None, timeout=None):
                return json.dumps(
                    [
                        {
                            "finding_index": valid_finding_index,
                            "rationale": "provider hallucinates extra candidate indices",
                            "ranked_candidate_indices": [
                                0,
                                0,  # duplicate -> collapsed
                                999999,  # out of range -> dropped
                                "not-an-int",  # wrong type -> dropped
                                True,  # bool -> rejected explicitly
                            ],
                        },
                        {
                            # Hallucinated finding_index entirely -> whole
                            # suggestion dropped.
                            "finding_index": 987654,
                            "rationale": "fake finding",
                            "ranked_candidate_indices": [0],
                        },
                    ]
                )

        monkeypatch.setattr(
            "llm_adapter.providers.get_provider", lambda: _StubProvider()
        )

        with _active(tenant):
            result = TraceabilitySuggestService().suggest_links(
                workspace.id, ctx, tier="standard"
            )

        assert len(result.suggestions) == 1
        suggestion = result.suggestions[0]
        assert suggestion.finding_index == valid_finding_index
        assert suggestion.rule_id == real.finding.rule_id
        assert len(suggestion.ranked_candidates) == 1
        assert suggestion.ranked_candidates[0].artifact_id == str(need_a.artifact_id)

    def test_suggestion_with_only_hallucinated_indices_is_dropped_entirely(
        self, tenant, workspace, ctx, monkeypatch
    ):
        with _active(tenant):
            _need(tenant, workspace, "Only need")
            _requirement(tenant, workspace, "Root")
            ground_truth = AuditService().run_audit(workspace.id, ctx, tier="standard")

        assert ground_truth.findings
        valid_finding_index = ground_truth.findings[0].index

        class _StubProvider:
            def complete(self, prompt, *, purpose="", context=None, timeout=None):
                return json.dumps(
                    [
                        {
                            "finding_index": valid_finding_index,
                            "rationale": "no valid candidate indices at all",
                            "ranked_candidate_indices": [123456, "nope"],
                        }
                    ]
                )

        monkeypatch.setattr(
            "llm_adapter.providers.get_provider", lambda: _StubProvider()
        )

        with _active(tenant):
            result = TraceabilitySuggestService().suggest_links(
                workspace.id, ctx, tier="standard"
            )

        assert result.suggestions == []


# ---------------------------------------------------------------------------
# Explicit "no pgvector" acceptance check (§3.2 / §4 Phase 4b criterion)
# ---------------------------------------------------------------------------


_TRIPLE_QUOTED_RE = re.compile(r'("""|\'\'\')(?:.|\n)*?\1')
_SINGLE_QUOTED_RE = re.compile(r'(\"(?:[^\"\\]|\\.)*\"|\'(?:[^\'\\]|\\.)*\')')
_COMMENT_RE = re.compile(r"#.*")


def _code_only(source: str) -> str:
    """Strip comments, docstrings and string literals from *source*.

    Reduces *source* to just its executable tokens. This module's own
    docstrings and comments intentionally *discuss* pgvector in prose
    (explaining that it is deliberately NOT used — see the module
    docstring), which would otherwise trip a naive substring search.
    Stripping strings/comments first makes the check exact: it can only
    fire on an actual import, call or identifier, mirroring how a real
    dependency (e.g. ``from pgvector.django import CosineDistance`` in
    ``application/requirement_service.py``) would appear in code.

    Regex-based rather than ``tokenize``-based on purpose: the caller may
    hand in a dedented *fragment* of a method body (not a standalone,
    correctly-indented module), which the C tokenizer rejects with an
    ``IndentationError`` even though it is perfectly fine for a textual
    "does this contain identifier X" check.
    """
    text = _TRIPLE_QUOTED_RE.sub(" ", source)
    text = _SINGLE_QUOTED_RE.sub(" ", text)
    text = _COMMENT_RE.sub(" ", text)
    return text


class TestNoPgvectorDependency:
    def test_service_module_has_no_vector_search_code_path(self):
        import application.traceability_suggest_service as module

        code = _code_only(inspect.getsource(module)).lower()
        for forbidden in ("pgvector", "vectorfield", "cosinedistance", "generate_embedding", "embedding"):
            assert forbidden not in code, (
                f"traceability_suggest_service.py must not contain a "
                f"'{forbidden}' code path (first-stage N3 is deterministic "
                "findings-ranking only, no vector search — §3.2)."
            )

    def test_mock_provider_suggest_links_branch_has_no_vector_search_code_path(self):
        # NOTE: the codebase legitimately uses pgvector elsewhere (Requirement/
        # TraceLink/ICDVersion embedding columns, see persistence/migrations/
        # 0024_requirement_embedding.py, 0025_tracelink_embedding.py) — those
        # are pre-existing, unrelated features. This check is scoped to just
        # the N3 mock branch's own code tokens (comments/docstrings/string
        # literals stripped via ``_code_only``, since this branch's own
        # comments legitimately explain in prose that it is NOT a vector
        # search) — the correct, literal acceptance check for "N3 first
        # stage has no vector-search code path" (§3.2).
        import llm_adapter.providers as providers_module

        full_source = inspect.getsource(providers_module.MockLlmProvider.complete)
        marker = 'if purpose == "traceability_suggest_links":'
        assert marker in full_source, "expected branch not found in MockLlmProvider.complete"
        start = full_source.index(marker)
        # Isolate this purpose's branch up to the next top-level `if purpose ==`.
        rest = full_source[start + len(marker) :]
        next_branch = rest.find('\n        if purpose == "')
        branch_source = rest if next_branch == -1 else rest[:next_branch]
        code = _code_only(branch_source).lower()
        for forbidden in ("pgvector", "vectorfield", "cosinedistance", "generate_embedding", "embedding"):
            assert forbidden not in code, (
                f"MockLlmProvider.complete()'s traceability_suggest_links branch "
                f"must not contain a '{forbidden}' code path."
            )


# ---------------------------------------------------------------------------
# BUG-15 code review M2 — the truncation signal from AuditService.run_audit()
# must survive this layer, not be silently dropped.
# ---------------------------------------------------------------------------


class _StubAuditServiceForReport:
    """Duck-typed AuditService stand-in that returns a pre-built report.

    TraceabilitySuggestService only ever calls ``run_audit()`` on its
    injected ``audit_service`` — a plain stub avoids needing a real
    >500-finding workspace just to prove the ``truncated`` flag propagates.
    """

    def __init__(self, report: AuditReport) -> None:
        self._report = report

    def run_audit(self, *args, **kwargs) -> AuditReport:
        return self._report


class TestSuggestLinksPropagatesTruncation:
    def test_truncated_report_flag_survives_into_suggest_links_result(
        self, tenant, workspace, ctx
    ):
        # An ineligible rule_id (not in _SUPPORTED_RULE_IDS) is enough to hit
        # the "no eligible findings" early return — the simplest of
        # suggest_links()'s three SuggestLinksResult construction sites, and
        # sufficient to prove the flag isn't dropped at this layer.
        finding = Finding(
            rule_id="TRACE-P7",
            severity=Severity.BLOCKER,
            message="padding",
            artifact_ids=(),
        )
        capped_report = AuditReport(
            tier="extended",
            scope=None,
            scope_artifact_id=None,
            findings=[
                AuditFindingView(
                    index=0,
                    finding=finding,
                    remediation=RemediationProposal(
                        rule_id="TRACE-P7", automatic=False, reason="manual"
                    ),
                )
            ],
            truncated=True,
            total_findings_available=4440,
        )

        with _active(tenant):
            result = TraceabilitySuggestService(
                audit_service=_StubAuditServiceForReport(capped_report)
            ).suggest_links(workspace.id, ctx, tier="extended")

        assert result.eligible_findings == 0
        assert result.truncated is True
        assert result.total_findings_available == 4440
        # to_dict() must expose it too — the actual REST/MCP wire shape.
        assert result.to_dict()["truncated"] is True
        assert result.to_dict()["total_findings_available"] == 4440

    def test_non_truncated_report_flag_is_false(self, tenant, workspace, ctx):
        empty_report = AuditReport(
            tier="extended",
            scope=None,
            scope_artifact_id=None,
            findings=[],
            truncated=False,
            total_findings_available=0,
        )

        with _active(tenant):
            result = TraceabilitySuggestService(
                audit_service=_StubAuditServiceForReport(empty_report)
            ).suggest_links(workspace.id, ctx, tier="extended")

        assert result.truncated is False
        assert result.total_findings_available == 0


# ---------------------------------------------------------------------------
# Regression (Phase 0 final review, Fund 1 #3): _candidate_pool() must exclude
# Requirements/ArchitectureElements soft-deleted via workflow.services.outdate().
# ---------------------------------------------------------------------------


class TestCandidatePoolExcludesOutdatedArtifacts:
    def test_outdated_requirement_excluded_from_trace_p1b_pool(self, tenant, workspace, ctx):
        from traceability.audit.registry import TRACE_P1B
        from workflow.services import create_default_workflow, outdate

        with _active(tenant):
            create_default_workflow(
                workspace_id=workspace.id,
                preset="standard",
                item_type="Requirement",
                tenant_id=tenant.id,
            )
            source = _requirement(tenant, workspace, "Source Requirement")
            kept = _requirement(tenant, workspace, "Kept Requirement")
            deleted = _requirement(tenant, workspace, "Deleted Requirement")

            outdate(
                item_id=deleted.id,
                item_type="Requirement",
                workspace_id=workspace.id,
                ctx=ctx,
                reason="test soft-delete",
            )

            pool = TraceabilitySuggestService._candidate_pool(
                TRACE_P1B, str(source.artifact_id), str(tenant.id), str(workspace.id)
            )

        assert str(kept.artifact_id) in pool
        assert str(deleted.artifact_id) not in pool

    def test_outdated_architecture_element_excluded_from_trace_p2_pool(
        self, tenant, workspace, ctx
    ):
        from persistence.models import ArchitectureElement
        from traceability.audit.registry import TRACE_P2
        from workflow.services import create_default_workflow, outdate

        with _active(tenant):
            create_default_workflow(
                workspace_id=workspace.id,
                preset="architecture_default",
                item_type="ArchitectureElement",
                tenant_id=tenant.id,
            )
            source = _requirement(tenant, workspace, "Source Requirement")

            kept_art = _artifact(tenant, workspace, "ArchitectureElement")
            kept = ArchitectureElement.objects.create(
                tenant=tenant, artifact=kept_art, title="Kept AE"
            )
            deleted_art = _artifact(tenant, workspace, "ArchitectureElement")
            deleted = ArchitectureElement.objects.create(
                tenant=tenant, artifact=deleted_art, title="Deleted AE"
            )

            outdate(
                item_id=deleted.id,
                item_type="ArchitectureElement",
                workspace_id=workspace.id,
                ctx=ctx,
                reason="test soft-delete",
            )

            pool = TraceabilitySuggestService._candidate_pool(
                TRACE_P2, str(source.artifact_id), str(tenant.id), str(workspace.id)
            )

        assert str(kept.artifact_id) in pool
        assert str(deleted.artifact_id) not in pool


# ---------------------------------------------------------------------------
# ADR-019 WP5 — the producer persists one suggestion per eligible finding
# ---------------------------------------------------------------------------


class TestSuggestLinksPersistsSuggestions:
    def test_agent_run_persists_one_open_suggestion_per_distinct_edge(
        self, tenant, workspace, ctx
    ):
        with _active(tenant):
            _need(
                tenant,
                workspace,
                "Login authentication need",
                "Users must authenticate securely.",
            )
            _requirement(
                tenant,
                workspace,
                "Login authentication requirement",
                "The system shall authenticate users securely.",
            )
            result = TraceabilitySuggestService().suggest_links(
                workspace.id, ctx, tier="standard"
            )
            persisted = list(Suggestion.objects.filter(workspace_id=workspace.id))

            # Assertions stay inside the armed tenant context: Suggestion and
            # TraceLink are tenant-scoped managers, so the per-row link lookup
            # below needs an active TenantContext.
            assert result.suggestions, "mock provider must rank at least one finding"
            # ADR-019 WP5 / B-02: one persisted open receipt per *distinct edge*
            # (same source/target collapses), not per finding — a second finding
            # proposing the same edge must not add a duplicate, un-rejectable row.
            expected_edges = {
                (
                    str(suggestion.source_artifact_id),
                    str(suggestion.ranked_candidates[0].artifact_id),
                )
                for suggestion in result.suggestions
            }
            assert len(persisted) == len(expected_edges)
            # No two receipts point at the same M2 proposal link.
            assert len(persisted) == len({row.target_item_id for row in persisted})
            for row in persisted:
                assert row.status == Suggestion.Status.OPEN
                assert row.kind == "trace_link"
                assert row.producer == "SuggestLinks Agent"
                # Server-set provenance from the API key, never from a payload.
                assert row.proposed_by_id == ctx.api_key_id
                assert row.proposed_at is not None
                assert row.decided_by_id is None
                # target_item_id is the real, still-unconfirmed M2 proposal link.
                link = TraceLink.objects.get(id=row.target_item_id)
                assert link.is_proposal is True
                assert link.proposed_by_id == ctx.api_key_id
                assert link.source_id == UUID(row.payload["source_artifact_id"])
                assert link.target_id == UUID(
                    row.payload["ranked_candidates"][0]["artifact_id"]
                )

    def test_repeated_run_dedupes_on_the_edge(self, tenant, workspace, ctx):
        with _active(tenant):
            _need(tenant, workspace, "Login authentication need", "auth login")
            _requirement(
                tenant, workspace, "Login authentication requirement", "auth login"
            )
            first = TraceabilitySuggestService().suggest_links(
                workspace.id, ctx, tier="standard"
            )
            receipts_after_first = Suggestion.objects.filter(
                workspace_id=workspace.id
            ).count()
            open_after_first = Suggestion.objects.filter(
                workspace_id=workspace.id, status=Suggestion.Status.OPEN
            ).count()

            second = TraceabilitySuggestService().suggest_links(
                workspace.id, ctx, tier="standard"
            )
            edges = list(TraceLink.objects.filter(link_type="derives-from"))
            receipts = Suggestion.objects.filter(workspace_id=workspace.id)
            open_receipts = receipts.filter(status=Suggestion.Status.OPEN)

            # Assertions stay inside the armed tenant context: ``receipts`` is
            # a lazy tenant-scoped queryset, so ``.count()`` here needs an
            # active TenantContext.
            assert first.suggestions and second.suggestions
            # B-02/O7: the repeated run neither adds a receipt nor a second
            # ``open`` row — it reuses the receipt of the edge.
            assert receipts.count() == receipts_after_first
            assert open_receipts.count() == open_after_first
            edge_keys = {
                (str(link.source_id), str(link.target_id), link.link_type)
                for link in edges
            }
            assert len(edge_keys) == len(edges), "duplicate trace-link edges were created"

    def test_human_bearer_context_is_refused_fail_closed(
        self, tenant, workspace, human_ctx
    ):
        with _active(tenant):
            _need(tenant, workspace, "Login authentication need", "auth login")
            _requirement(
                tenant, workspace, "Login authentication requirement", "auth login"
            )
            with pytest.raises(ProducerContextRequiredError):
                TraceabilitySuggestService().suggest_links(
                    workspace.id, human_ctx, tier="standard"
                )
            # Fail-closed wrote nothing: no receipt, no unstamped link.
            assert not Suggestion.objects.filter(workspace_id=workspace.id).exists()
            assert not TraceLink.objects.exists()


class TestSuggestLinksAuditsConfirmedTraceState:
    def test_suggest_links_forwards_include_proposal_links_false(
        self, tenant, ctx
    ):
        """B-05: the producer audits only the *confirmed* trace state.

        Its own persisted proposal must not satisfy the completeness rule on a
        repeated run; the seam runs ``AuditService.run_audit`` ->
        ``RuleEngine.run(include_proposal_links=False)``.
        """

        class _StubAudit:
            def __init__(self) -> None:
                self.kwargs: dict = {}

            def run_audit(self, *args, **kwargs) -> AuditReport:
                self.kwargs = kwargs
                return AuditReport(
                    tier="standard",
                    scope=None,
                    scope_artifact_id=None,
                    findings=[],
                    truncated=False,
                    total_findings_available=0,
                )

        stub = _StubAudit()
        with _active(tenant):
            TraceabilitySuggestService(audit_service=stub).suggest_links(
                "00000000-0000-0000-0000-000000000000", ctx, tier="standard"
            )

        assert stub.kwargs["include_proposal_links"] is False
