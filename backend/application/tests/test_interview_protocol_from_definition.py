"""Interview protocol derived from ai_elicit attributes (spec section 7)."""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest

from application.interview_protocol import (
    ProtocolValidationError,
    get_protocol,
    protocol_from_definition,
)
from persistence.middleware import clear_request_tenant, set_request_tenant


def _attr(name, **over):
    base = {
        "name": name, "kind": "core", "type": "text", "section": "general",
        "order": 0, "ai_elicit": True, "visible": True, "options": [],
        "label": {"de": name, "en": name}, "widget_key": None, "fields": [],
    }
    base.update(over)
    return base


def test_only_ai_elicit_attributes_become_required_fields() -> None:
    protocol = protocol_from_definition(
        [_attr("title"), _attr("quiet", ai_elicit=False)], "Risk"
    )
    names = [f.name for phase in protocol.phases for f in phase.required_fields]
    assert names == ["title"]


def test_section_order_becomes_phase_order() -> None:
    protocol = protocol_from_definition(
        [
            _attr("severity", section="classification", order=0),
            _attr("title", section="general", order=0),
        ],
        "Risk",
    )
    assert [p.name for p in protocol.phases[:2]] == ["classification", "general"]


def test_approval_and_formalization_phases_are_always_appended() -> None:
    protocol = protocol_from_definition([_attr("title")], "Risk")
    assert [p.name for p in protocol.phases[-2:]] == ["approval", "formalization"]
    assert protocol.phases[-1].required_fields == []


def test_enum_attributes_carry_their_choices() -> None:
    protocol = protocol_from_definition(
        [_attr("category", type="enum",
               options=[{"value": "a", "label_de": "A", "label_en": "A"}])],
        "Risk",
    )
    field = protocol.phases[0].required_fields[0]
    assert field.type == "enum"
    assert field.choices == ["a"]


def test_multi_enum_is_narrowed_to_enum_and_other_types_to_text() -> None:
    protocol = protocol_from_definition(
        [
            _attr("tags", type="multi-enum",
                  options=[{"value": "x", "label_de": "X", "label_en": "X"}]),
            _attr("due", type="date"),
            _attr("owner", type="user"),
        ],
        "Issue",
    )
    by_name = {f.name: f for p in protocol.phases for f in p.required_fields}
    assert by_name["tags"].type == "enum"
    assert by_name["due"].type == "text"
    assert by_name["owner"].type == "text"


def test_widget_attributes_are_skipped() -> None:
    protocol = protocol_from_definition(
        [_attr("risk_matrix", type="widget", widget_key="risk_matrix_rpz",
               fields=["probability"]),
         _attr("probability", type="enum",
               options=[{"value": "low", "label_de": "N", "label_en": "L"}])],
        "Risk",
    )
    names = [f.name for p in protocol.phases for f in p.required_fields]
    assert names == ["probability"]


def test_a_definition_with_no_ai_elicit_attribute_raises() -> None:
    """A protocol with zero elicitable fields is not a usable interview."""
    with pytest.raises(ProtocolValidationError):
        protocol_from_definition([_attr("quiet", ai_elicit=False)], "Risk")


@pytest.fixture
def protocol_from_definition_ctx(db):
    """Tenant + workspace + AuthContext, same shape as test_interview_protocol.py.

    A real tenant/workspace is required (not MagicMock()/uuid.uuid4()):
    get_protocol's tier-1 check now queries PromptTemplate directly (see the
    deviation note in interview_protocol.py's get_protocol docstring), which
    goes through the tenant-scoped ORM manager and raises
    TenantContextNotSetError without an active TenantContext.
    """
    from auth_tenancy.context import AuthContext, AuthMethod
    from persistence.models import Tenant, User, Workspace

    tenant = Tenant.objects.create(name="Protocol From Definition Test", is_active=True)
    set_request_tenant(tenant.id)
    workspace = Workspace.objects.create(tenant=tenant, name="Test Workspace")
    user = User.objects.create(
        username="protocolfromdefuser", email="protocolfromdef@t.test", tenant=tenant
    )
    ctx = AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=("editor",),
        auth_method=AuthMethod.API_KEY,
        api_key_id=None,
    )
    try:
        yield ctx, workspace
    finally:
        clear_request_tenant()


def test_get_protocol_prefers_an_explicit_template_over_the_definition(
    protocol_from_definition_ctx,
) -> None:
    """Tier 1 (an explicit PromptTemplate row) wins over tier 2 (the definition).

    Deviation from the plan's literal test (which patched
    ``application.prompt_resolver.try_resolve_template_content``): that
    function is no longer on get_protocol's call path (see the docstring
    deviation note) — a real PromptTemplate row exercises the actual tier-1
    query instead of a resolver seam get_protocol no longer uses.
    """
    from persistence.models import PromptTemplate

    ctx, workspace = protocol_from_definition_ctx
    PromptTemplate.objects.create(
        tenant_id=ctx.tenant_id,
        name="interview.protocol.Risk",
        content=(
            "phases:\n  - name: custom\n    required_fields:\n"
            "      - name: handcrafted\n        type: text\n"
        ),
        version=1,
        is_active=True,
        workspace_id=workspace.id,
    )

    protocol = get_protocol(ctx, "Risk", workspace.id)
    assert protocol.phases[0].name == "custom"


def test_get_protocol_falls_back_to_the_definition(protocol_from_definition_ctx) -> None:
    ctx, workspace = protocol_from_definition_ctx
    with patch(
        "application.interview_protocol.AttributeDefinitionService"
    ) as service:
        service.return_value.elicit_attributes.return_value = [_attr("title")]
        protocol = get_protocol(ctx, "Risk", workspace.id)
    assert [f.name for p in protocol.phases for f in p.required_fields] == ["title"]


def test_get_protocol_falls_back_to_the_factory_default_without_a_definition(
    protocol_from_definition_ctx,
) -> None:
    from application.attribute_definition_service import AttributeDefinitionNotFound

    ctx, workspace = protocol_from_definition_ctx
    with patch(
        "application.interview_protocol.AttributeDefinitionService"
    ) as service:
        service.return_value.elicit_attributes.side_effect = AttributeDefinitionNotFound("x")
        protocol = get_protocol(ctx, "Risk", workspace.id)
    names = [f.name for p in protocol.phases for f in p.required_fields]
    assert names == ["title", "rationale"]


@pytest.mark.django_db
def test_full_interview_cycle_against_a_bootstrapped_definition_preserves_description() -> None:
    """C-1 / I-4 regression, non-mocked on purpose.

    Every test above patches ``AttributeDefinitionService`` outright, so none
    of them can observe the real shape of a definition-derived protocol --
    exactly how C-1 slipped through review: ``bootstrap_attribute_definitions``
    marks ``title``/``description`` ``ai_elicit`` (see
    ``introspect_core_attributes``), never the old hardcoded ``rationale``,
    but ``interview_service._formalize_single`` kept reading
    ``collected_fields["rationale"]`` -- silently formalizing every
    definition-derived interview with an empty description.

    This drives a real bootstrap -> start -> answer -> formalize cycle and
    asserts the user's typed description survives into the created
    Requirement.
    """
    from django.core.management import call_command

    from application.interview_service import InterviewService
    from application.requirement_service import RequirementService
    from auth_tenancy.context import AuthContext, AuthMethod
    from persistence.middleware import clear_request_tenant, set_request_tenant
    from persistence.models import Tenant, User, Workspace

    tenant = Tenant.objects.create(name="Full Interview Cycle Test", is_active=True)
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="ws", preset={"name": "standard"}
        )
        user = User.objects.create(
            username="fullcycleuser", email="fullcycle@t.test", tenant=tenant
        )
    finally:
        clear_request_tenant()

    # bootstrap_attribute_definitions.Command.handle() arms and clears its
    # own tenant context per tenant internally -- running it while the block
    # above's context is still active would just get silently cleared by the
    # command's own `finally`, so it runs fully outside that block.
    call_command("bootstrap_attribute_definitions", tenant=str(tenant.id))

    # Re-armed for the rest of the test: get_protocol() is called directly
    # below (not through a ServiceBase subclass, which arms its own tenant
    # context), and it queries a tenant-scoped PromptTemplate manager --
    # same idiom as protocol_from_definition_ctx above.
    set_request_tenant(tenant.id)
    try:
        ctx = AuthContext(
            user_id=user.id,
            tenant_id=tenant.id,
            active_roles=("editor",),
            auth_method=AuthMethod.API_KEY,
            api_key_id=None,
        )

        # Sanity check: prove this test actually exercises tier 2 (the
        # definition-derived protocol), not the hardcoded factory default --
        # otherwise this would be exactly as blind as the mocked tests above.
        protocol = get_protocol(ctx, "Requirement", workspace.id)
        elicited = {f.name for phase in protocol.phases for f in phase.required_fields}
        assert elicited == {"title", "description"}

        session = InterviewService().start(ctx, "Requirement", workspace.id)
        InterviewService().answer(ctx, session.id, "title", "SSO login support")
        InterviewService().answer(
            ctx, session.id, "description", "Reduce password fatigue for support staff"
        )

        result = InterviewService().formalize(ctx, session.id)

        requirement = RequirementService().get_requirement(
            uuid.UUID(result["resulting_artifact_ids"][0]), ctx
        )
        assert requirement.title == "SSO login support"
        assert requirement.description == "Reduce password fatigue for support staff"
    finally:
        clear_request_tenant()
