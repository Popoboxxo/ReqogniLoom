"""#272 / Plan B B1-T1 — a Requirement interview elicits AC, method and rationale.

Tier 2 is asserted on the resolved protocol (not only on the round trip), so a
regression that drops one of the three fails with a readable diff. The
end-to-end half proves the answers reach ``RequirementService.create_requirement``
through ``build_adapter_fields`` — i.e. the alias fix R-B1-1 as well, since the
definition elicits ``description`` and ``rationale`` in the same phase.
"""
from __future__ import annotations

import uuid

import pytest
from django.core.management import call_command

from application.interview_protocol import get_protocol
from application.interview_service import InterviewService
from application.requirement_service import RequirementService
from auth_tenancy.context import AuthContext, AuthMethod
from persistence.models import Tenant, User, Workspace
from persistence.tenancy import TenantContext

_VERIFICATION_METHODS = {"Test", "Review", "Analysis", "Inspection", "Demonstration"}
_ANSWERS = {
    "acceptance_criteria": "Gegeben ein geladener Akku, wenn gestartet, dann 5000 RPM.",
    "verification_method": "Analysis",
    "rationale": "Der Motor muss die Nennleistung im Dauerlauf halten.",
}


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="Req Interview 272", slug="req-interview-272")


@pytest.fixture
def workspace(tenant):
    # `extended` on purpose: the three SE attributes are visible (and therefore
    # elicited) from the standard stage on -- see the 0011 migration's scope.
    TenantContext.set_tenant(tenant.id)
    try:
        return Workspace.objects.create(
            tenant=tenant, name="WS-272", preset={"name": "extended"}
        )
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def bootstrapped_workspace(tenant, workspace):
    """self_init runs this for every tenant, so tier 2 is the real-deployment
    tier -- see test_interview_formalize_all_types.py."""
    call_command("bootstrap_attribute_definitions", tenant=str(tenant.id))
    return workspace


@pytest.fixture
def ctx(tenant):
    TenantContext.set_tenant(tenant.id)
    try:
        user = User.objects.create(
            username="req-272-user", email="req272@t.test", tenant=tenant
        )
    finally:
        TenantContext.clear_tenant()
    return AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=("editor",),
        auth_method=AuthMethod.API_KEY,
    )


def _fields_by_name(protocol) -> dict:
    return {
        field.name: field
        for phase in protocol.phases
        for field in phase.required_fields
    }


def test_tier2_protocol_elicits_acceptance_criteria_method_and_rationale(
    ctx, bootstrapped_workspace
) -> None:
    TenantContext.set_tenant(ctx.tenant_id)
    try:
        protocol = get_protocol(ctx, "Requirement", bootstrapped_workspace.id)
    finally:
        TenantContext.clear_tenant()

    fields = _fields_by_name(protocol)
    assert {"acceptance_criteria", "verification_method", "rationale"} <= set(fields)
    assert fields["acceptance_criteria"].type == "textarea"
    assert fields["verification_method"].type == "enum"
    # Choices come from the definition, not a second hardcoded list.
    assert set(fields["verification_method"].choices) == _VERIFICATION_METHODS
    assert fields["rationale"].type == "textarea"


def test_formalized_requirement_carries_the_three_answers(
    ctx, bootstrapped_workspace
) -> None:
    svc = InterviewService()
    session = svc.start(ctx, "Requirement", bootstrapped_workspace.id)

    # Answer every elicited field; the SE ones get their documented value, the
    # remaining ones (title/description) a readable one. Loops because tier 2
    # reports the missing fields of the FIRST incomplete phase only.
    for _ in range(20):
        missing = svc.get_state(ctx, session.id)["missing_fields"]
        if not missing:
            break
        for field in missing:
            if field["name"] in _ANSWERS:
                value = _ANSWERS[field["name"]]
            elif field["type"] == "enum":
                value = field["choices"][0]
            else:
                value = f"Answer for {field['name']}"
            svc.answer(ctx, session.id, field["name"], value)
    else:  # pragma: no cover - a non-draining protocol is a bug, not a timeout
        raise AssertionError("protocol still reports missing fields")

    result = svc.formalize(ctx, session.id)

    requirement = RequirementService().get_requirement(
        uuid.UUID(result["resulting_artifact_ids"][0]), ctx
    )
    assert requirement.acceptance_criteria == _ANSWERS["acceptance_criteria"]
    assert requirement.verification_method == "Analysis"
    assert requirement.rationale == _ANSWERS["rationale"]
    # R-B1-1: `description` is elicited in the same phase; the rationale must
    # not have been consumed by the rationale->description alias.
    assert requirement.description
