"""S1 (REQ-217) — AI-derived drafts carry structured AC + verification method.

Covers the normalization helpers, the preview draft shape, the tolerant
"never drop a draft" behaviour, the accept-path normalizer and the
create-and-persist round-trip through ``persist_derived_requirements``.
"""
from __future__ import annotations

import json

import pytest

from application.ai_derivation_service import (
    AC_MAX_CHARS,
    AC_MAX_ITEMS,
    AC_MIN_CHARS,
    VERIFICATION_METHODS,
    AiDerivationService,
)
from application.requirement_service import RequirementService
from auth_tenancy.context import AuthContext
from persistence.models import (
    DEFAULT_NEED_TO_SYSREQ,
    Artifact,
    Requirement,
    StakeholderNeed,
    Tenant,
    User,
)
from persistence.tenancy import TenantContext
from persistence.tests.factories import make_workspace

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tenant():
    return Tenant.objects.create(name="ac-tenant", slug="ac-tenant")


@pytest.fixture
def user(tenant):
    return User.objects.create(username="acuser", email="ac@example.com", tenant=tenant)


@pytest.fixture
def auth_context(user):
    return AuthContext(
        user_id=user.id,
        tenant_id=user.tenant.id,
        active_roles=("editor",),
        auth_method="test",
        api_key_id=None,
        tenant_name="ac-tenant",
    )


@pytest.fixture
def workspace(tenant):
    TenantContext.set_tenant(tenant.id)
    try:
        return make_workspace(tenant, name="ac-ws")
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def need(auth_context, workspace):
    TenantContext.set_tenant(auth_context.tenant_id)
    try:
        artifact = Artifact.objects.create(
            workspace=workspace,
            artifact_type="StakeholderNeed",
            tenant_id=auth_context.tenant_id,
        )
        return StakeholderNeed.objects.create(
            artifact=artifact,
            tenant_id=auth_context.tenant_id,
            title="Users need a search",
            description="Search must feel instant.",
        )
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def workflow_need(auth_context, workspace):
    """A need in a workspace whose requirement graph has a ``proposed`` state."""
    from workflow.services import create_default_workflow

    TenantContext.set_tenant(auth_context.tenant_id)
    try:
        create_default_workflow(
            workspace_id=workspace.id,
            preset="extended",
            item_type="Requirement",
            tenant_id=auth_context.tenant_id,
        )
        artifact = Artifact.objects.create(
            workspace=workspace,
            artifact_type="StakeholderNeed",
            tenant_id=auth_context.tenant_id,
        )
        return StakeholderNeed.objects.create(
            artifact=artifact,
            tenant_id=auth_context.tenant_id,
            title="Users need workflow-aware derivation",
            description="The derivation must persist reviewable proposals.",
        )
    finally:
        TenantContext.clear_tenant()


class _PayloadProvider:
    """Provider double returning one fixed JSON array."""

    def __init__(self, payload) -> None:
        self._payload = payload

    def complete(self, prompt, *, purpose="", context=None, timeout=None):
        return json.dumps(self._payload)


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------


def test_prompt_defaults_request_structured_criteria_and_method():
    text = DEFAULT_NEED_TO_SYSREQ
    assert "acceptance_criteria" in text
    assert "verification_method" in text
    assert "STRICT JSON" in text
    # The existing render contract must survive the extension.
    assert "{max_requirements_per_need}" in text
    assert "{need_title}" in text
    assert "{need_description}" in text
    assert "{memory_context}" in text


def test_criteria_are_normalized_to_the_criteria_list_shape():
    criteria, incomplete = AiDerivationService._normalize_draft_acceptance_criteria(
        [{"text": "The system shall respond within 200 ms."}]
    )
    assert incomplete == []
    assert criteria == [
        {
            "text": "The system shall respond within 200 ms.",
            "fulfilled": False,
            "evidence_ref": None,
        }
    ]


def test_bare_strings_are_tolerated_as_criterion_text():
    criteria, incomplete = AiDerivationService._normalize_draft_acceptance_criteria(
        ["The system shall respond within 200 ms."]
    )
    assert incomplete == []
    assert criteria[0]["text"] == "The system shall respond within 200 ms."


def test_duplicate_criteria_are_removed_keeping_first_seen_order():
    criteria, incomplete = AiDerivationService._normalize_draft_acceptance_criteria(
        [
            {"text": "The system shall respond within 200 ms."},
            {"text": "  the   SYSTEM shall respond within 200 ms.  "},
            {"text": "The system shall log every request."},
        ]
    )
    assert incomplete == []
    assert [c["text"] for c in criteria] == [
        "The system shall respond within 200 ms.",
        "The system shall log every request.",
    ]


def test_more_than_the_cap_is_truncated_without_marking_incomplete():
    raw = [
        {"text": f"Criterion number {index} is measurable."}
        for index in range(AC_MAX_ITEMS + 1)
    ]
    criteria, incomplete = AiDerivationService._normalize_draft_acceptance_criteria(raw)
    assert len(criteria) == AC_MAX_ITEMS
    assert incomplete == []


def test_short_criterion_is_dropped_and_marks_incomplete():
    criteria, incomplete = AiDerivationService._normalize_draft_acceptance_criteria(
        [{"text": "a" * (AC_MIN_CHARS - 1)}, {"text": "The system shall be fast."}]
    )
    assert [c["text"] for c in criteria] == ["The system shall be fast."]
    assert incomplete == ["acceptance_criteria"]


def test_long_criterion_is_dropped_and_marks_incomplete():
    criteria, incomplete = AiDerivationService._normalize_draft_acceptance_criteria(
        [{"text": "a" * (AC_MAX_CHARS + 1)}, {"text": "The system shall be fast."}]
    )
    assert [c["text"] for c in criteria] == ["The system shall be fast."]
    assert incomplete == ["acceptance_criteria"]


def test_missing_or_non_list_criteria_report_incomplete():
    for raw in (None, "not a list", [], 42):
        assert AiDerivationService._normalize_draft_acceptance_criteria(raw) == (
            [],
            ["acceptance_criteria"],
        )


def test_all_criteria_dropped_leaves_an_empty_list_and_incomplete():
    criteria, incomplete = AiDerivationService._normalize_draft_acceptance_criteria([{"text": "tiny"}])
    assert criteria == []
    assert incomplete == ["acceptance_criteria"]


# ---------------------------------------------------------------------------
# Verification method
# ---------------------------------------------------------------------------


def test_verification_method_is_case_insensitively_canonicalized():
    for method in VERIFICATION_METHODS:
        assert AiDerivationService._normalize_verification_method(method.lower()) == (method, [])


def test_missing_or_unknown_verification_method_reports_incomplete():
    for raw in (None, "", "Vibes", 3):
        assert AiDerivationService._normalize_verification_method(raw) == (
            None,
            ["verification_method"],
        )


# ---------------------------------------------------------------------------
# Preview draft shape
# ---------------------------------------------------------------------------


def test_mock_drafts_carry_structured_criteria_and_method(auth_context, need):
    result = AiDerivationService().derive_requirements_from_need(
        auth_context, need.id, n=2
    )

    assert len(result["drafts"]) == 2
    for draft in result["drafts"]:
        assert 1 <= len(draft["acceptance_criteria"]) <= AC_MAX_ITEMS
        for criterion in draft["acceptance_criteria"]:
            assert set(criterion) == {"text", "fulfilled", "evidence_ref"}
            assert criterion["fulfilled"] is False
            assert criterion["evidence_ref"] is None
            assert AC_MIN_CHARS <= len(criterion["text"]) <= AC_MAX_CHARS
        assert draft["verification_method"] == "Test"
        assert draft["incomplete_fields"] == []


def test_a_draft_with_bad_criteria_is_still_returned(auth_context, need, monkeypatch):
    provider = _PayloadProvider(
        [
            {
                "title": "Search latency",
                "description": "The system shall answer search queries quickly.",
                "rationale": "Needed for the stated need.",
                "acceptance_criteria": "not a list",
                "verification_method": "Magic",
            }
        ]
    )
    monkeypatch.setattr(
        "llm_adapter.providers.get_provider", lambda *a, **k: provider
    )

    result = AiDerivationService().derive_requirements_from_need(
        auth_context, need.id, n=1
    )

    # Never dropped — the draft is returned, marked incomplete.
    assert len(result["drafts"]) == 1
    draft = result["drafts"][0]
    assert draft["title"] == "Search latency"
    assert draft["acceptance_criteria"] == []
    assert draft["verification_method"] is None
    assert draft["incomplete_fields"] == [
        "acceptance_criteria",
        "verification_method",
    ]


def test_decompose_drafts_carry_structured_criteria_and_method(
    auth_context, workspace
):
    from application.architecture_service import ArchitectureService
    from application.trace_link_service import TraceLinkService

    req = RequirementService().create_requirement(
        workspace_id=workspace.id, title="Parent req", ctx=auth_context
    )
    arch = ArchitectureService().create_architecture_element(
        workspace_id=workspace.id, title="Component C", ctx=auth_context
    )
    TraceLinkService().allocate(
        requirement_id=req.id, architecture_element_id=arch.id, ctx=auth_context
    )

    result = AiDerivationService().decompose_requirement_next_level(
        auth_context, req.id
    )

    assert result["drafts"]
    for draft in result["drafts"]:
        assert draft["acceptance_criteria"]
        assert draft["verification_method"] == "Test"
        assert draft["incomplete_fields"] == []


# ---------------------------------------------------------------------------
# Accept-path normalizer
# ---------------------------------------------------------------------------


def test_validate_accepted_drafts_carries_the_new_keys():
    accepted = AiDerivationService._validate_accepted_drafts(
        [
            {
                "title": "Child",
                "description": "d",
                "rationale": "r",
                "acceptance_criteria": [{"text": "The child shall be verifiable."}],
                "verification_method": "review",
            }
        ]
    )
    assert len(accepted) == 1
    assert accepted[0]["verification_method"] == "Review"
    assert accepted[0]["acceptance_criteria"][0]["fulfilled"] is False
    assert accepted[0]["acceptance_criteria"][0]["evidence_ref"] is None


def test_validate_accepted_drafts_defaults_missing_fields():
    accepted = AiDerivationService._validate_accepted_drafts([{"title": "Child"}])
    assert accepted[0]["acceptance_criteria"] == []
    assert accepted[0]["verification_method"] is None


# ---------------------------------------------------------------------------
# Persist round-trip
# ---------------------------------------------------------------------------


def test_persist_derived_requirements_writes_criteria_and_method(
    auth_context, workflow_need
):
    result = AiDerivationService().persist_derived_requirements(
        auth_context,
        need_id=workflow_need.id,
        drafts=[
            {
                "title": "Persisted child",
                "description": "Persisted description.",
                "rationale": "Persisted rationale.",
                "acceptance_criteria": [
                    {"text": "The child shall be verifiable end to end."}
                ],
                "verification_method": "Test",
            }
        ],
    )

    assert result["count"] == 1
    requirement = Requirement.objects.get(id=result["created"][0]["id"])
    assert requirement.verification_method == "Test"
    assert len(requirement.acceptance_criteria_items) == 1
    criterion = requirement.acceptance_criteria_items[0]
    assert criterion["text"] == "The child shall be verifiable end to end."
    assert criterion["fulfilled"] is False
    assert criterion["evidence_ref"] is None
