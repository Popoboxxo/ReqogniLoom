"""Plan B / B5-T3 (#378) — QualityService.

Pins the three contracts that make the assessment usable and safe:

* a run writes exactly one ``QualityAssessment`` row (``cached=False``),
* an unchanged artifact is served from the content hash — ``cached=True`` and
  the provider is not called a second time,
* an unusable answer leaves a ``status="failed"`` row behind and still raises
  ``LlmResponseError`` (so the transport answers 502, not 500).
"""
from __future__ import annotations

import json
import uuid

import pytest

from application.ai_derivation_service import LlmResponseError
from application.base import NotFoundError, ValidationError
from application.quality_service import (
    ASSESSABLE_TYPES,
    QualityService,
    assessment_payload,
)
from application.requirement_service import RequirementService
from auth_tenancy.context import AuthContext
from persistence.models import QualityAssessment, Tenant, User
from persistence.tenancy import TenantContext
from persistence.tests.factories import make_workspace

pytestmark = pytest.mark.django_db

_VERDICT = {
    "score": 0.75,
    "reasoning": "Clear, but the acceptance criteria are vague.",
    "suggestions": ["Name a measurable acceptance criterion."],
    "criteria": {"atomic": 0.9, "verifiable": 0.6},
}


class _CountingProvider:
    """Fake provider: counts calls and replays a fixed payload."""

    PROVIDER_NAME = "counting"
    MODEL_NAME = "counting-v1"

    def __init__(self, response: str) -> None:
        self.response = response
        self.calls: list[str] = []

    def complete(self, prompt, *, purpose="", context=None, timeout=None):
        self.calls.append(prompt)
        return self.response


@pytest.fixture
def tenant() -> Tenant:
    return Tenant.objects.create(name="quality-tenant", slug="quality-tenant")


@pytest.fixture
def user(tenant: Tenant) -> User:
    return User.objects.create(
        username="quality-user", email="quality@example.com", tenant=tenant
    )


@pytest.fixture
def ctx(user: User) -> AuthContext:
    return AuthContext(
        user_id=user.id,
        tenant_id=user.tenant.id,
        active_roles=("editor",),
        auth_method="test",
        api_key_id=None,
        tenant_name="quality-tenant",
    )


@pytest.fixture
def workspace(tenant: Tenant):
    TenantContext.set_tenant(tenant.id)
    try:
        return make_workspace(tenant, name="quality-ws")
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def other_workspace(tenant: Tenant):
    TenantContext.set_tenant(tenant.id)
    try:
        return make_workspace(tenant, name="quality-ws-b")
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def requirement(ctx: AuthContext, workspace):
    return RequirementService().create_requirement(
        workspace_id=workspace.id, title="The system shall respond", ctx=ctx
    )


@pytest.fixture
def provider(monkeypatch: pytest.MonkeyPatch) -> _CountingProvider:
    fake = _CountingProvider(json.dumps(_VERDICT))
    monkeypatch.setattr("llm_adapter.providers.get_provider", lambda *a, **k: fake)
    return fake


def _rows(workspace) -> list[QualityAssessment]:
    TenantContext.set_tenant(workspace.tenant_id)
    try:
        return list(
            QualityAssessment.objects.filter(workspace_id=workspace.id).order_by(
                "created_at"
            )
        )
    finally:
        TenantContext.clear_tenant()


def test_assessable_types_map_onto_the_quality_slots():
    assert set(ASSESSABLE_TYPES) == {"Requirement", "Adr", "TestCase", "Risk"}
    assert all(slot.startswith("quality_") for slot in ASSESSABLE_TYPES.values())


def test_assess_writes_one_row_and_returns_cached_false(
    ctx: AuthContext, workspace, requirement, provider: _CountingProvider
):
    assessment, cached = QualityService().assess(
        ctx, workspace.id, "Requirement", requirement.id
    )

    assert cached is False
    assert assessment.status == QualityAssessment.Status.OK
    assert assessment.score == pytest.approx(0.75)
    assert assessment.reasoning == _VERDICT["reasoning"]
    assert set(assessment.suggestions) == set(_VERDICT["suggestions"])
    assert set(assessment.criteria) == set(_VERDICT["criteria"])
    assert assessment.prompt_slot == "quality_requirement"
    assert assessment.entity_type == "Requirement"
    assert assessment.entity_id == requirement.id
    assert assessment.content_hash
    assert len(provider.calls) == 1
    assert len(_rows(workspace)) == 1


def test_second_call_with_unchanged_content_is_cached_and_calls_no_provider(
    ctx: AuthContext, workspace, requirement, provider: _CountingProvider
):
    service = QualityService()
    first, first_cached = service.assess(
        ctx, workspace.id, "Requirement", requirement.id
    )
    calls_after_first = len(provider.calls)

    second, second_cached = service.assess(
        ctx, workspace.id, "Requirement", requirement.id
    )

    assert (first_cached, second_cached) == (False, True)
    assert second.id == first.id
    assert len(provider.calls) == calls_after_first, (
        "the cache hit must not reach the provider"
    )
    assert len(_rows(workspace)) == 1


def test_title_change_produces_a_new_row(
    ctx: AuthContext, workspace, requirement, provider: _CountingProvider
):
    service = QualityService()
    service.assess(ctx, workspace.id, "Requirement", requirement.id)
    RequirementService().update_requirement(
        requirement.id,
        ctx,
        title="The system shall respond within 200 ms",
    )

    assessment, cached = service.assess(
        ctx, workspace.id, "Requirement", requirement.id
    )

    assert cached is False
    assert len(provider.calls) == 2
    rows = _rows(workspace)
    assert len(rows) == 2
    assert rows[0].content_hash != rows[1].content_hash
    assert assessment.id == rows[-1].id


def test_template_bump_invalidates_the_cached_verdict(
    ctx: AuthContext, workspace, requirement, provider: _CountingProvider
):
    """A rubric change must not replay the old verdict as ``cached``.

    The artifact is untouched, so hashing its content alone would return the
    stale row (same content hash) while carrying the *old* prompt provenance.
    """
    from application.prompt_template_versioning import publish_new_version

    service = QualityService()
    first, first_cached = service.assess(
        ctx, workspace.id, "Requirement", requirement.id
    )
    calls_after_first = len(provider.calls)
    assert first_cached is False

    unchanged, unchanged_cached = service.assess(
        ctx, workspace.id, "Requirement", requirement.id
    )
    assert unchanged_cached is True
    assert unchanged.id == first.id
    assert len(provider.calls) == calls_after_first
    assert unchanged.prompt_scope == QualityAssessment.PromptScope.FACTORY

    publish_new_version(
        tenant_id=ctx.tenant_id,
        name="quality_requirement",
        content="Assess this requirement against the revised rubric.",
        workspace_id=workspace.id,
    )

    after_bump, cached_after_bump = service.assess(
        ctx, workspace.id, "Requirement", requirement.id
    )

    assert cached_after_bump is False, "a rubric change must invalidate the cache"
    assert after_bump.id != first.id
    assert after_bump.content_hash != first.content_hash
    assert len(provider.calls) == calls_after_first + 1
    assert after_bump.prompt_scope == QualityAssessment.PromptScope.WORKSPACE
    assert after_bump.prompt_version == 1
    rows = _rows(workspace)
    assert len(rows) == 2
    assert rows[-1].id == after_bump.id
    assert rows[-1].prompt_scope == QualityAssessment.PromptScope.WORKSPACE
    assert rows[-1].prompt_version == 1

    still_cached, still_cached_flag = service.assess(
        ctx, workspace.id, "Requirement", requirement.id
    )
    assert still_cached_flag is True
    assert still_cached.id == after_bump.id
    assert len(provider.calls) == calls_after_first + 1


def test_force_re_runs_even_when_content_is_unchanged(
    ctx: AuthContext, workspace, requirement, provider: _CountingProvider
):
    service = QualityService()
    first, _ = service.assess(ctx, workspace.id, "Requirement", requirement.id)
    second, cached = service.assess(
        ctx, workspace.id, "Requirement", requirement.id, force=True
    )

    # ``force`` bypasses the content-hash cache and records a second, distinct
    # row. The provider may still answer from AiDerivationService's own
    # prompt cache (REQ-105) — that is an LLM-level deduplication, not the
    # verdict cache this service owns.
    assert cached is False
    assert second.id != first.id
    assert len(_rows(workspace)) == 2


def test_invalid_llm_json_raises_and_keeps_a_failed_row(
    ctx: AuthContext, workspace, requirement, monkeypatch: pytest.MonkeyPatch
):
    fake = _CountingProvider("this is not json at all")
    monkeypatch.setattr("llm_adapter.providers.get_provider", lambda *a, **k: fake)

    with pytest.raises(LlmResponseError):
        QualityService().assess(ctx, workspace.id, "Requirement", requirement.id)

    rows = _rows(workspace)
    assert len(fake.calls) >= 1
    assert len(rows) == 1
    assert rows[0].status == QualityAssessment.Status.FAILED
    assert rows[0].error_code
    assert rows[0].reasoning == ""


def test_score_outside_zero_to_one_is_an_invalid_output(
    ctx: AuthContext, workspace, requirement, monkeypatch: pytest.MonkeyPatch
):
    fake = _CountingProvider(json.dumps({**_VERDICT, "score": 1.5}))
    monkeypatch.setattr("llm_adapter.providers.get_provider", lambda *a, **k: fake)

    with pytest.raises(LlmResponseError):
        QualityService().assess(ctx, workspace.id, "Requirement", requirement.id)

    rows = _rows(workspace)
    assert len(rows) == 1
    assert rows[0].status == QualityAssessment.Status.FAILED


def test_unassessable_type_is_a_validation_error(ctx: AuthContext, workspace):
    with pytest.raises(ValidationError):
        QualityService().assess(
            ctx, workspace.id, "ArchitectureElement", uuid.uuid4()
        )


def test_entity_of_another_workspace_is_not_found_and_never_assesed(
    ctx: AuthContext,
    workspace,
    other_workspace,
    requirement,
    provider: _CountingProvider,
):
    """The entity lives in the *other* workspace of the same tenant."""
    assert requirement.workspace_id == workspace.id
    with pytest.raises(NotFoundError):
        QualityService().assess(
            ctx, other_workspace.id, "Requirement", requirement.id
        )
    assert provider.calls == []
    assert _rows(workspace) == []
    assert _rows(other_workspace) == []


def test_history_is_newest_first_and_workspace_bound(
    ctx: AuthContext, workspace, other_workspace, requirement, provider
):
    service = QualityService()
    service.assess(ctx, workspace.id, "Requirement", requirement.id)
    service.assess(ctx, workspace.id, "Requirement", requirement.id, force=True)

    rows = service.history(ctx, workspace.id, "Requirement", requirement.id)
    assert len(rows) == 2
    assert rows[0].created_at >= rows[1].created_at

    with pytest.raises(NotFoundError):
        service.history(ctx, other_workspace.id, "Requirement", requirement.id)


def test_history_limit_is_validated(ctx: AuthContext, workspace, requirement):
    with pytest.raises(ValidationError):
        QualityService().history(
            ctx, workspace.id, "Requirement", requirement.id, limit=0
        )


def test_latest_for_returns_one_row_per_entity(
    ctx: AuthContext, workspace, requirement, provider
):
    service = QualityService()
    service.assess(ctx, workspace.id, "Requirement", requirement.id)
    second, _ = service.assess(
        ctx, workspace.id, "Requirement", requirement.id, force=True
    )

    latest = service.latest_for(
        ctx, workspace.id, "Requirement", [requirement.id, uuid.uuid4()]
    )
    assert set(latest) == {requirement.id}
    assert latest[requirement.id].id == second.id
    assert service.latest_for(ctx, workspace.id, "Requirement", []) == {}


def test_assessment_payload_carries_the_documented_keys(
    ctx: AuthContext, workspace, requirement, provider
):
    assessment, _ = QualityService().assess(
        ctx, workspace.id, "Requirement", requirement.id
    )
    payload = assessment_payload(assessment, cached=True)

    assert set(payload) == {
        "assessment_id",
        "entity_type",
        "entity_id",
        "score",
        "reasoning",
        "suggestions",
        "criteria",
        "prompt_slot",
        "prompt_scope",
        "provider",
        "model",
        "trigger",
        "status",
        "cached",
        "assessed_at",
    }
    assert payload["cached"] is True
    assert payload["prompt_scope"] in {"factory", "global", "workspace"}
    assert payload["trigger"] == "manual"
