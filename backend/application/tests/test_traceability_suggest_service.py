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

import pytest

from application.audit_service import AuditService
from application.traceability_suggest_service import TraceabilitySuggestService
from auth_tenancy.context import AuthContext
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
        return Workspace.objects.create(tenant=tenant, name="SuggestLinks-WS")


@pytest.fixture
def ctx(user: User) -> AuthContext:
    return AuthContext(
        user_id=user.id,
        tenant_id=user.tenant.id,
        active_roles=("editor",),
        auth_method="test",
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
