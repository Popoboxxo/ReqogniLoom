"""
AiReviewService (SysEng 2.0 N8, ``audit.ai_review``) — referential-integrity tests.

UMSETZUNGSPLAN_SYSENG_2.0.md §3.2 + §4, Phase 4b. Acceptance criterion (verbatim):
"N8: Refactoring-Pakete referenzieren reale, existierende Findings-IDs aus
Phase-3-Dashboard." This module tests that criterion literally:

* every ``finding_refs`` entry in every returned package must match an actual
  finding from an independent :meth:`AuditService.run_audit` call on the same
  workspace/tier (same index, rule_id, artifact_ids);
* an empty audit report yields zero packages without contacting the LLM;
* a provider that proposes out-of-range / duplicate / non-integer indices has
  every one of them silently dropped rather than surfacing a fake reference
  (defense-in-depth: the guarantee holds even against a misbehaving provider,
  not just the cooperative mock).
"""
from __future__ import annotations

import contextlib
import json
from typing import Iterator

import pytest

from application.ai_review_service import AiReviewService
from application.audit_service import AuditFindingView, AuditReport, AuditService
from auth_tenancy.context import AuthContext
from persistence.models import Artifact, Requirement, Tenant, User, Workspace
from persistence.tenancy import TenantContext
from traceability.audit import Finding, RemediationProposal, Severity

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Fixtures + helpers (mirrors application/tests/test_audit_service.py)
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
    return Tenant.objects.create(name="AiReview Tenant", slug="ai-review-tenant")


@pytest.fixture
def user(tenant: Tenant) -> User:
    return User.objects.create(
        username="ai-review-user", email="ai-review@example.com", tenant=tenant
    )


@pytest.fixture
def workspace(tenant: Tenant) -> Workspace:
    with _active(tenant):
        return Workspace.objects.create(tenant=tenant, name="AiReview-WS")


@pytest.fixture
def ctx(user: User) -> AuthContext:
    return AuthContext(
        user_id=user.id,
        tenant_id=user.tenant.id,
        active_roles=("editor",),
        auth_method="test",
        api_key_id=None,
        tenant_name="AiReview Tenant",
    )


def _artifact(tenant: Tenant, workspace: Workspace, artifact_type: str) -> Artifact:
    return Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type=artifact_type
    )


def _requirement(tenant: Tenant, workspace: Workspace, title: str = "Req") -> Requirement:
    art = _artifact(tenant, workspace, "requirement")
    return Requirement.objects.create(tenant=tenant, artifact=art, title=title)


def _all_refs(result) -> list[dict]:
    """Flatten every finding_ref across every package of an AiReviewResult."""
    refs = []
    for pkg in result.packages:
        refs.extend(pkg.finding_refs)
    return refs


# ---------------------------------------------------------------------------
# Referential integrity — the literal acceptance criterion
# ---------------------------------------------------------------------------


class TestReviewReferentialIntegrity:
    def test_packages_reference_only_real_findings(self, tenant, workspace, ctx):
        with _active(tenant):
            _requirement(tenant, workspace, "Root")
            # Ground truth: an independent run_audit() call over the same data.
            ground_truth = AuditService().run_audit(workspace.id, ctx, tier="extended")

        assert ground_truth.findings, "fixture must yield at least one finding"
        truth_by_index = {fv.index: fv for fv in ground_truth.findings}

        with _active(tenant):
            result = AiReviewService().review(workspace.id, ctx, tier="extended")

        assert result.total_findings == len(ground_truth.findings)
        refs = _all_refs(result)
        assert refs, "mock provider is expected to group at least one package"

        for ref in refs:
            idx = ref["index"]
            assert idx in truth_by_index, (
                f"package references finding index {idx}, which does not exist "
                "in the independently-fetched audit report"
            )
            real = truth_by_index[idx]
            assert ref["rule_id"] == real.finding.rule_id
            assert ref["artifact_ids"] == list(real.finding.artifact_ids)
            assert ref["scope_artifact_id"] == real.finding.scope_artifact_id

    def test_over_daily_token_limit_raises_and_never_calls_provider(
        self, tenant, workspace, ctx, monkeypatch, settings
    ):
        """Code review regression: audit.ai_review (N8) bypassed REQ-106
        entirely -- no is_over_daily_limit() check existed at all before
        this fix, unlike every other free-form LLM flow."""
        from unittest.mock import MagicMock

        from application.ai_derivation_service import LlmResponseError
        from persistence.models import TokenUsageRecord

        settings.TENANT_TOKEN_LIMIT_PER_DAY = 100
        with _active(tenant):
            TokenUsageRecord.objects.create(
                provider="mock", capability="audit_ai_review",
                input_tokens=150, output_tokens=0,
            )
            _requirement(tenant, workspace, "Root")

        stub_provider = MagicMock()
        stub_provider.complete.return_value = "[]"
        monkeypatch.setattr(
            "llm_adapter.providers.get_provider", lambda *a, **k: stub_provider
        )

        with _active(tenant):
            with pytest.raises(LlmResponseError):
                AiReviewService().review(workspace.id, ctx, tier="extended")
        # Load-bearing: the budget check runs BEFORE the provider is ever
        # called, not just that some exception was eventually raised.
        stub_provider.complete.assert_not_called()

    def test_no_findings_yields_no_packages_without_llm_call(
        self, tenant, workspace, ctx, monkeypatch
    ):
        def _boom():
            raise AssertionError("LLM provider must not be contacted when there are no findings")

        monkeypatch.setattr("llm_adapter.providers.get_provider", _boom)

        with _active(tenant):
            _requirement(tenant, workspace, "Root")
            result = AiReviewService().review(workspace.id, ctx, tier="minimal")

        assert result.packages == []
        assert result.total_findings == 0


# ---------------------------------------------------------------------------
# BUG-15 code review M2 — the truncation signal from AuditService.run_audit()
# must survive this layer, not be silently dropped.
# ---------------------------------------------------------------------------


class _StubAuditServiceForReport:
    """Duck-typed AuditService stand-in that returns a pre-built report.

    AiReviewService only ever calls ``run_audit()`` on its injected
    ``audit_service`` — a plain stub avoids needing a real >500-finding
    workspace just to prove the ``truncated`` flag propagates.
    """

    def __init__(self, report: AuditReport) -> None:
        self._report = report

    def run_audit(self, *args, **kwargs) -> AuditReport:
        return self._report


class TestReviewPropagatesTruncation:
    def test_truncated_report_flag_survives_into_ai_review_result(
        self, tenant, workspace, ctx
    ):
        finding = Finding(
            rule_id="TRACE-P4",
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
                        rule_id="TRACE-P4", automatic=False, reason="manual"
                    ),
                )
            ],
            truncated=True,
            total_findings_available=4440,
        )

        with _active(tenant):
            result = AiReviewService(
                audit_service=_StubAuditServiceForReport(capped_report)
            ).review(workspace.id, ctx, tier="extended")

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
            result = AiReviewService(
                audit_service=_StubAuditServiceForReport(empty_report)
            ).review(workspace.id, ctx, tier="extended")

        assert result.truncated is False
        assert result.total_findings_available == 0


# ---------------------------------------------------------------------------
# Defense-in-depth — a misbehaving provider must not leak fake references
# ---------------------------------------------------------------------------


class TestReviewDropsHallucinatedIndices:
    def test_out_of_range_duplicate_and_non_int_indices_are_dropped(
        self, tenant, workspace, ctx, monkeypatch
    ):
        with _active(tenant):
            _requirement(tenant, workspace, "Root")
            ground_truth = AuditService().run_audit(workspace.id, ctx, tier="extended")

        assert ground_truth.findings
        valid_index = ground_truth.findings[0].index
        real = ground_truth.findings[0]

        class _StubProvider:
            def complete(self, prompt, *, purpose="", context=None, timeout=None):
                return json.dumps(
                    [
                        {
                            "title": "Suspicious package",
                            "rationale": "provider hallucinates extra indices",
                            "finding_indices": [
                                valid_index,
                                valid_index,  # duplicate -> collapsed
                                999999,  # out of range -> dropped
                                "not-an-int",  # wrong type -> dropped
                                True,  # bool -> rejected explicitly
                            ],
                        }
                    ]
                )

        monkeypatch.setattr(
            "llm_adapter.providers.get_provider", lambda: _StubProvider()
        )

        with _active(tenant):
            result = AiReviewService().review(workspace.id, ctx, tier="extended")

        assert len(result.packages) == 1
        refs = result.packages[0].finding_refs
        assert len(refs) == 1
        assert refs[0]["index"] == valid_index
        assert refs[0]["rule_id"] == real.finding.rule_id
        assert refs[0]["artifact_ids"] == list(real.finding.artifact_ids)

    def test_package_with_only_hallucinated_indices_is_dropped_entirely(
        self, tenant, workspace, ctx, monkeypatch
    ):
        with _active(tenant):
            _requirement(tenant, workspace, "Root")

        class _StubProvider:
            def complete(self, prompt, *, purpose="", context=None, timeout=None):
                return json.dumps(
                    [
                        {
                            "title": "Entirely fake package",
                            "rationale": "no valid indices at all",
                            "finding_indices": [123456, "nope"],
                        }
                    ]
                )

        monkeypatch.setattr(
            "llm_adapter.providers.get_provider", lambda: _StubProvider()
        )

        with _active(tenant):
            result = AiReviewService().review(workspace.id, ctx, tier="extended")

        assert result.packages == []
