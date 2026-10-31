"""#378 / WP B5-T4 — the advisory ``QUAL-P1``/``QUAL-P2``/``QUAL-P3`` rules.

Pins the four contracts that make the quality layer safe to ship:

* every finding is a WARNING — a quality hint must never block a baseline build
  (the #581 calibration lesson: an unassessable gate is worse than no gate);
* the rules read the ``QualityAssessment`` table only — an audit run never calls
  an LLM, so a workspace is not billed for opening the auditor;
* registration and tier placement are asserted by *membership*, never by a
  total count (KA-B-03: a count test breaks on every unrelated new rule);
* the three data gates: ``QUAL-P1`` stays silent until the workspace has used
  the feature, ``QUAL-P2`` ignores ``status="failed"`` sentinel rows, and
  ``QUAL-P3`` fires only once the content moved past the assessed revision.
"""
from __future__ import annotations

import json
import uuid
from collections.abc import Iterator

import pytest

from application.prompt_variable_versioning import publish_new_variable_version
from application.prompt_variables import PROMPT_VARIABLE_DEFAULTS
from application.quality_service import ASSESSABLE_TYPES, QualityService
from auth_tenancy.context import AuthContext
from persistence.models import QualityAssessment, Requirement, Tenant, User, Workspace
from persistence.tests.factories import make_workspace
from traceability.audit import RuleEngine
from traceability.audit.registry import (
    QUAL_P1,
    QUAL_P2,
    QUAL_P3,
    active_rule_ids_for_tier,
    get_registered_rules,
    get_rule_catalogue,
)
from traceability.audit.rules import quality_score
from traceability.audit.rules.quality_score import DEFAULT_MIN_SCORE, MIN_SCORE_VARIABLE
from traceability.audit.types import AuditContext, Severity
from traceability.tests.conftest import active_tenant

pytestmark = pytest.mark.django_db

QUAL_IDS = frozenset({QUAL_P1, QUAL_P2, QUAL_P3})

#: A usable verdict for the counting provider (shape only, see _validate_verdict).
_VERDICT = {
    "score": 0.75,
    "reasoning": "Clear, but the acceptance criteria are vague.",
    "suggestions": ["Name a measurable acceptance criterion."],
    "criteria": {"atomic": 0.9, "verifiable": 0.6},
}


class _CountingProvider:
    """Fake LLM provider that counts both lookups and completions."""

    PROVIDER_NAME = "counting"
    MODEL_NAME = "counting-v1"

    def __init__(self, response: str, counter: dict[str, int]) -> None:
        self.response = response
        self.counter = counter

    def complete(self, prompt, *, purpose="", context=None, timeout=None):
        self.counter["complete"] += 1
        return self.response


@pytest.fixture(autouse=True)
def _clear_preset_cache() -> Iterator[None]:
    yield
    from presets import gate

    with gate._cache_lock:
        gate._tier_cache.clear()


@pytest.fixture
def tenant() -> Tenant:
    return Tenant.objects.create(name="qual-tenant", slug="qual-tenant")


@pytest.fixture
def user(tenant: Tenant) -> User:
    return User.objects.create(
        username="qual-user", email="qual@example.com", tenant=tenant
    )


@pytest.fixture
def ctx(user: User) -> AuthContext:
    return AuthContext(
        user_id=user.id,
        tenant_id=user.tenant.id,
        active_roles=("editor",),
        auth_method="test",
        api_key_id=None,
        tenant_name="qual-tenant",
    )


@pytest.fixture
def workspace(tenant: Tenant) -> Workspace:
    """An Extended workspace — the only tier the QUAL rules run in."""
    with active_tenant(tenant):
        return make_workspace(tenant, name="qual-ws", preset={"name": "extended"})


@pytest.fixture
def qual_only(settings) -> None:
    """Restrict the Extended tier to the QUAL rules for this test.

    Keeps the severity / baseline-gate assertions independent of the other
    Extended rules: only a QUAL finding may appear, so "no blocker" cannot be
    satisfied accidentally by an unrelated rule being silent.
    """
    settings.SE_AUDITOR_RULE_PRESETS = {"extended": QUAL_IDS}


@pytest.fixture
def counter(monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    """Count every provider lookup/completion; assert nothing is billed."""
    counts = {"get_provider": 0, "complete": 0}
    fake = _CountingProvider(json.dumps(_VERDICT), counts)

    def _get_provider(*args, **kwargs):
        counts["get_provider"] += 1
        return fake

    monkeypatch.setattr("llm_adapter.providers.get_provider", _get_provider)
    return counts


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _requirement(tenant: Tenant, workspace: Workspace, title: str = "Req"):
    """Create an Artifact + Requirement pair in the active tenant."""
    from persistence.models import Artifact

    with active_tenant(tenant):
        artifact = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="Requirement"
        )
        requirement = Requirement.objects.create(
            tenant=tenant, artifact=artifact, title=title
        )
    return artifact, requirement


def _assessment_row(
    tenant: Tenant,
    workspace: Workspace,
    requirement: Requirement,
    *,
    score: float = 0.75,
    status: str = QualityAssessment.Status.OK,
    content_hash: str = "0" * 64,
) -> QualityAssessment:
    """Write an assessment row directly (bypasses the LLM entirely)."""
    with active_tenant(tenant):
        return QualityAssessment.objects.create(
            tenant=tenant,
            workspace=workspace,
            entity_type="Requirement",
            entity_id=requirement.id,
            artifact_id=requirement.artifact_id,
            score=score,
            reasoning="",
            suggestions=[],
            criteria={},
            content_hash=content_hash,
            entity_version=requirement.version,
            prompt_slot=ASSESSABLE_TYPES["Requirement"],
            prompt_scope=QualityAssessment.PromptScope.FACTORY,
            prompt_version=None,
            provider="mock",
            model="mock",
            trigger=QualityAssessment.Trigger.MANUAL,
            triggered_by="test",
            status=status,
        )


def _publish_threshold(
    tenant: Tenant, raw_json: str, *, workspace: Workspace | None = None
) -> None:
    """Publish an active ``quality_min_score`` row for the scope."""
    with active_tenant(tenant):
        publish_new_variable_version(
            tenant_id=tenant.id,
            name=MIN_SCORE_VARIABLE,
            kind="config",
            var_type="json",
            description="test threshold",
            default_value=raw_json,
            workspace_id=workspace.id if workspace is not None else None,
        )


def _run(tenant: Tenant, workspace: Workspace, tier: str = "extended"):
    with active_tenant(tenant):
        return RuleEngine().run(
            tier=tier,
            workspace_id=str(workspace.id),
            tenant_id=str(tenant.id),
        )


def _by_rule(result, rule_id: str) -> list:
    return [finding for finding in result.findings if finding.rule_id == rule_id]


def _artifact_id_of(finding) -> set[str]:
    return set(finding.artifact_ids)


def _audit_context(tenant: Tenant, workspace: Workspace) -> AuditContext:
    return AuditContext(
        tier="extended",
        workspace_id=str(workspace.id),
        tenant_id=str(tenant.id),
    )


# ---------------------------------------------------------------------------
# Registration + tier placement (membership, never a total count)
# ---------------------------------------------------------------------------


class TestRegistration:
    def test_the_three_ids_are_registered(self):
        registered = {rule.rule_id for rule in get_registered_rules()}
        assert QUAL_IDS <= registered

    def test_the_three_ids_are_in_the_rule_catalogue(self):
        catalogue = {entry["rule_id"] for entry in get_rule_catalogue()}
        assert QUAL_IDS <= catalogue

    def test_catalogue_entries_are_advisory_and_extended_only(self):
        catalogue = {entry["rule_id"]: entry for entry in get_rule_catalogue()}
        for rule_id in sorted(QUAL_IDS):
            entry = catalogue[rule_id]
            assert entry["severity"] == Severity.WARNING.value
            assert "extended" in entry["active_tiers"]
            assert "standard" not in entry["active_tiers"]
            assert "minimal" not in entry["active_tiers"]
            assert entry["deferred"] is False

    def test_extended_active_minimal_and_standard_inactive(self):
        assert QUAL_IDS <= active_rule_ids_for_tier("extended")
        assert not (QUAL_IDS & active_rule_ids_for_tier("standard"))
        assert not (QUAL_IDS & active_rule_ids_for_tier("minimal"))


# ---------------------------------------------------------------------------
# Severity: advisory only
# ---------------------------------------------------------------------------


class TestSeverityIsAlwaysWarning:
    def test_every_finding_is_a_warning(
        self, tenant: Tenant, workspace: Workspace, qual_only
    ):
        _, assessed = _requirement(tenant, workspace, "Assessed")
        _requirement(tenant, workspace, "Unassessed")
        _assessment_row(tenant, workspace, assessed, score=0.1)

        result = _run(tenant, workspace)

        qual = [f for f in result.findings if f.rule_id in QUAL_IDS]
        assert qual, "expected QUAL findings on this fixture"
        assert {finding.severity for finding in qual} == {Severity.WARNING}

    def test_no_qual_finding_ever_reaches_the_baseline_gate(
        self, tenant: Tenant, workspace: Workspace, qual_only
    ):
        from application.audit_service import AuditService
        from traceability.audit import AuditScope

        _, assessed = _requirement(tenant, workspace, "Assessed")
        _requirement(tenant, workspace, "Unassessed")
        _assessment_row(tenant, workspace, assessed, score=0.1)

        with active_tenant(tenant):
            result = RuleEngine().run(
                tier="extended",
                workspace_id=str(workspace.id),
                tenant_id=str(tenant.id),
            )
            blockers = AuditService().blocking_findings(
                workspace.id, _ctx_for(tenant), scopes=[AuditScope("project")]
            )

        assert [f for f in result.findings if f.rule_id in QUAL_IDS]
        assert not [f for f in blockers if f.rule_id in QUAL_IDS]
        assert all(f.severity is Severity.BLOCKER for f in blockers)


def _ctx_for(tenant: Tenant) -> AuthContext:
    return AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=tenant.id,
        active_roles=("admin",),
        auth_method="test",
    )


# ---------------------------------------------------------------------------
# Baseline creation is not blocked by QUAL findings (BaselineFacade through)
# ---------------------------------------------------------------------------


class TestBaselineGateUnaffected:
    def test_warnings_present_but_baseline_is_created(
        self, tenant: Tenant, workspace: Workspace, qual_only
    ):
        """The gate sees QUAL findings and still lets the baseline through."""
        from application.baseline_facade import BaselineFacade

        _, assessed = _requirement(tenant, workspace, "Assessed")
        _requirement(tenant, workspace, "Unassessed")
        _assessment_row(tenant, workspace, assessed, score=0.1)

        with active_tenant(tenant):
            result = RuleEngine().run(
                tier="extended",
                workspace_id=str(workspace.id),
                tenant_id=str(tenant.id),
            )
            assert [f for f in result.findings if f.rule_id in QUAL_IDS]

            baseline_id = BaselineFacade().create_baseline(
                scope="project",
                workspace_id=workspace.id,
                name="qual-warnings-baseline",
                ctx=_ctx_for(tenant),
            )

        assert baseline_id is not None


# ---------------------------------------------------------------------------
# No provider call
# ---------------------------------------------------------------------------


class TestNoLlm:
    def test_check_makes_no_provider_call(
        self,
        tenant: Tenant,
        workspace: Workspace,
        ctx: AuthContext,
        counter: dict[str, int],
    ):
        """An audit run inspects verdicts, it never requests one."""
        _, requirement = _requirement(tenant, workspace, "Assess me")
        # A second, never-assessed artifact so the run really produces a QUAL
        # finding (that the counter stays at zero must not be vacuous).
        _requirement(tenant, workspace, "Never assessed")
        # One genuine assessment through the service — this is the only call
        # that is allowed to reach the provider, and it happens *before* the
        # measurement starts.
        QualityService().assess(ctx, workspace.id, "Requirement", requirement.id)
        counter["get_provider"] = 0
        counter["complete"] = 0

        result = _run(tenant, workspace)

        assert [f for f in result.findings if f.rule_id in QUAL_IDS]
        assert counter["get_provider"] == 0
        assert counter["complete"] == 0


# ---------------------------------------------------------------------------
# QUAL-P1 — coverage, gated on "the feature is in use"
# ---------------------------------------------------------------------------


class TestQualP1:
    def test_silent_when_the_workspace_has_no_assessment(
        self, tenant: Tenant, workspace: Workspace
    ):
        """Legacy data: nothing was ever assessed, so nothing is "missing"."""
        _requirement(tenant, workspace, "Legacy one")
        _requirement(tenant, workspace, "Legacy two")

        result = _run(tenant, workspace)

        assert _by_rule(result, QUAL_P1) == []
        assert [f for f in result.findings if f.rule_id in QUAL_IDS] == []

    def test_fires_for_the_unassessed_artifact_once_the_feature_is_used(
        self, tenant: Tenant, workspace: Workspace
    ):
        assessed_artifact, assessed = _requirement(tenant, workspace, "Assessed")
        missing_artifact, _ = _requirement(tenant, workspace, "Missing")
        _assessment_row(tenant, workspace, assessed)

        result = _run(tenant, workspace)

        flagged = set()
        for finding in _by_rule(result, QUAL_P1):
            flagged |= _artifact_id_of(finding)
        assert str(missing_artifact.id) in flagged
        assert str(assessed_artifact.id) not in flagged


# ---------------------------------------------------------------------------
# QUAL-P2 — score floor
# ---------------------------------------------------------------------------


class TestQualP2:
    def test_a_failed_row_is_ignored(self, tenant: Tenant, workspace: Workspace):
        """score=0.0 on a failed row is a sentinel, not a real zero."""
        _, requirement = _requirement(tenant, workspace, "Failed run")
        _assessment_row(
            tenant,
            workspace,
            requirement,
            score=0.0,
            status=QualityAssessment.Status.FAILED,
        )

        result = _run(tenant, workspace)

        assert _by_rule(result, QUAL_P2) == []

    def test_a_low_successful_score_is_reported(
        self, tenant: Tenant, workspace: Workspace
    ):
        artifact, requirement = _requirement(tenant, workspace, "Weak")
        _assessment_row(tenant, workspace, requirement, score=0.2)

        result = _run(tenant, workspace)

        flagged = set()
        for finding in _by_rule(result, QUAL_P2):
            flagged |= _artifact_id_of(finding)
        assert str(artifact.id) in flagged

    def test_a_score_at_or_above_the_default_floor_is_silent(
        self, tenant: Tenant, workspace: Workspace
    ):
        _, requirement = _requirement(tenant, workspace, "Solid")
        _assessment_row(
            tenant, workspace, requirement, score=DEFAULT_MIN_SCORE
        )

        result = _run(tenant, workspace)

        assert _by_rule(result, QUAL_P2) == []

    def test_a_workspace_override_raises_the_floor(
        self, tenant: Tenant, workspace: Workspace
    ):
        _, requirement = _requirement(tenant, workspace, "Above default")
        _assessment_row(
            tenant, workspace, requirement, score=DEFAULT_MIN_SCORE + 0.05
        )
        assert _by_rule(_run(tenant, workspace), QUAL_P2) == []

        _publish_threshold(tenant, "0.95", workspace=workspace)
        result = _run(tenant, workspace)

        flagged = set()
        for finding in _by_rule(result, QUAL_P2):
            flagged |= _artifact_id_of(finding)
        assert str(requirement.artifact_id) in flagged


class TestThresholdResolution:
    def test_the_factory_default_matches_the_rule_constant(self):
        """One number, two places — pinned so they cannot drift apart."""
        spec = PROMPT_VARIABLE_DEFAULTS[MIN_SCORE_VARIABLE]
        assert spec.kind == "config"
        assert spec.var_type == "json"
        assert spec.default_value == DEFAULT_MIN_SCORE

    def test_defaults_are_used_without_any_stored_row(
        self, tenant: Tenant, workspace: Workspace
    ):
        with active_tenant(tenant):
            assert (
                quality_score._resolve_threshold(_audit_context(tenant, workspace))
                == DEFAULT_MIN_SCORE
            )

    def test_a_numeric_override_is_used(self, tenant: Tenant, workspace: Workspace):
        _publish_threshold(tenant, "0.8", workspace=workspace)

        with active_tenant(tenant):
            assert quality_score._resolve_threshold(
                _audit_context(tenant, workspace)
            ) == pytest.approx(0.8)

    def test_a_non_numeric_value_falls_back_to_the_default(
        self, tenant: Tenant, workspace: Workspace
    ):
        _publish_threshold(tenant, json.dumps("high"), workspace=workspace)

        with active_tenant(tenant):
            assert (
                quality_score._resolve_threshold(_audit_context(tenant, workspace))
                == DEFAULT_MIN_SCORE
            )

    def test_an_out_of_range_value_falls_back_to_the_default(
        self, tenant: Tenant, workspace: Workspace
    ):
        _publish_threshold(tenant, "2.0", workspace=workspace)

        with active_tenant(tenant):
            assert (
                quality_score._resolve_threshold(_audit_context(tenant, workspace))
                == DEFAULT_MIN_SCORE
            )

    def test_a_boolean_value_is_rejected(self, tenant: Tenant, workspace: Workspace):
        """``float(True) == 1.0`` would silently flood QUAL-P2 instead."""
        _publish_threshold(tenant, "true", workspace=workspace)

        with active_tenant(tenant):
            assert (
                quality_score._resolve_threshold(_audit_context(tenant, workspace))
                == DEFAULT_MIN_SCORE
            )


# ---------------------------------------------------------------------------
# QUAL-P3 — staleness
# ---------------------------------------------------------------------------


class TestQualP3:
    def test_not_stale_immediately_after_a_real_assessment(
        self, tenant: Tenant, workspace: Workspace, ctx: AuthContext, counter
    ):
        """The stored hash covers the prompt provenance as well as the content.

        Comparing it with a content-only hash would flag every row in the
        table; this is the test that keeps the rule honest.
        """
        _, requirement = _requirement(tenant, workspace, "Fresh")
        QualityService().assess(ctx, workspace.id, "Requirement", requirement.id)
        completions_after_assess = counter["complete"]

        result = _run(tenant, workspace)

        assert _by_rule(result, QUAL_P3) == []
        assert counter["complete"] == completions_after_assess

    def test_fires_when_the_content_changed_after_the_assessment(
        self, tenant: Tenant, workspace: Workspace, ctx: AuthContext, counter
    ):
        artifact, requirement = _requirement(tenant, workspace, "Before")
        QualityService().assess(ctx, workspace.id, "Requirement", requirement.id)
        completions_after_assess = counter["complete"]
        assert _by_rule(_run(tenant, workspace), QUAL_P3) == []

        with active_tenant(tenant):
            Requirement.objects.filter(id=requirement.id).update(
                title="After the assessment"
            )

        result = _run(tenant, workspace)

        flagged = set()
        for finding in _by_rule(result, QUAL_P3):
            flagged |= _artifact_id_of(finding)
        assert flagged == {str(artifact.id)}
        # The staleness check is a read: the provider was not called again.
        assert counter["complete"] == completions_after_assess
