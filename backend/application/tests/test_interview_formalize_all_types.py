"""L2.1 regression: formalize() works for every in-scope artifact type.

One parametrized round trip per type -- start, answer the protocol's required
fields, formalize, then assert the artifact exists with the right
``artifact_type`` and an initialized workflow state. Requirement is included
(not only the 7 new types) so the parametrization is the single place the
per-type contract is stated.

Run TWICE, against both protocol tiers ``get_protocol()`` can resolve:

* ``TestFormalizeFactoryDefaultProtocol`` -- a workspace with no attribute
  definition, so tier 3 (``INTERVIEW_PROTOCOL_DEFAULTS``) answers.
* ``TestFormalizeBootstrappedProtocol`` -- the same round trip after
  ``bootstrap_attribute_definitions`` ran, so tier 2
  (``protocol_from_definition``, the definition's ``ai_elicit`` attributes)
  answers. ``application.self_init`` runs that bootstrap for every new tenant,
  which makes tier 2 the tier every real deployment actually uses -- a
  tier-3-only suite once "proved" all 8 types work while Risk was broken in
  production for exactly that reason (``probability``/``impact`` were not
  marked ``ai_elicit``).
"""
from __future__ import annotations

import uuid

import pytest
from django.core.management import call_command

from application.interview_protocol import IN_SCOPE_ARTIFACT_TYPES
from application.interview_service import InterviewService
from auth_tenancy.context import AuthContext, AuthMethod
from persistence.models import Artifact, Tenant, User, Workspace
from persistence.tenancy import TenantContext
from workflow.services import create_default_workflow


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="IFA Tenant", slug="ifa-tenant")


@pytest.fixture
def workspace(tenant):
    TenantContext.set_tenant(tenant.id)
    try:
        ws = Workspace.objects.create(tenant=tenant, name="WS", goals_enabled=True)
        # A real WorkflowItemState only materializes if a workflow definition
        # exists for (workspace, item_type) -- initialize_workflow_states()
        # no-ops silently otherwise (graceful degradation for an
        # unconfigured type, not a bug). Provision the standard preset for
        # every in-scope type so the workflow-state assertion below is a
        # real integration check, not a false negative on a bare fixture.
        for artifact_type in IN_SCOPE_ARTIFACT_TYPES:
            create_default_workflow(
                workspace_id=ws.id,
                preset="standard",
                item_type=artifact_type,
                tenant_id=tenant.id,
            )
        return ws
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def bootstrapped_workspace(tenant, workspace):
    """The same workspace, after the per-tenant attribute-definition bootstrap.

    ``application.self_init`` runs this exact command for every new tenant, so
    this is the state of every real deployment: ``get_protocol()`` resolves
    tier 2 (the definition's ``ai_elicit`` attributes) instead of the
    hardcoded factory default.
    """
    call_command("bootstrap_attribute_definitions", tenant=str(tenant.id))
    return workspace


@pytest.fixture
def ctx(tenant):
    # A real User row: StakeholderNeedService.create() (unlike several of the
    # sibling create_X() methods) sets created_by=ctx.user_id with a real FK
    # to pl_user -- a bare uuid4() 404s on the constraint, not on business logic.
    TenantContext.set_tenant(tenant.id)
    try:
        user = User.objects.create(
            username="ifa-user", email="ifa@t.test", tenant=tenant
        )
    finally:
        TenantContext.clear_tenant()
    return AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=("editor",),
        auth_method=AuthMethod.API_KEY,
    )


#: Values to answer per protocol field type. The factory-default protocol asks
#: title+rationale for every type; Risk additionally asks probability+impact
#: (enum low/medium/high, see interview_protocol._EXTRA_REQUIRED_FIELDS).
_ENUM_ANSWER = "high"


def _answer_all_required_fields(svc: InterviewService, ctx, session_id) -> None:
    """Answer whatever the resolved protocol declares as still missing.

    Loops: ``get_state`` reports the missing fields of the FIRST incomplete
    phase only, and a definition-derived protocol (tier 2) has one elicitation
    phase per definition section -- Risk's ``probability``/``impact`` live in
    ``classification``, not in the same phase as ``title``.
    """
    for _ in range(_MAX_PHASES):
        missing = svc.get_state(ctx, session_id)["missing_fields"]
        if not missing:
            return
        for field in missing:
            if field["type"] == "enum":
                value = (field.get("choices") or [_ENUM_ANSWER])[0]
            elif field["type"] == "number":
                value = 1
            else:
                value = f"Interview answer for {field['name']}"
            svc.answer(ctx, session_id, field["name"], value)
    raise AssertionError(
        f"protocol still reports missing fields after {_MAX_PHASES} phases"
    )


#: Safety bound for the answer loop above -- a protocol whose phases never
#: drain is a bug, not something to spin on.
_MAX_PHASES = 20


def _assert_artifact_and_workflow_state(ctx, workspace, artifact_type, result) -> None:
    """One artifact of *artifact_type*, with the workflow state create_X() inits."""
    from workflow.models import WorkflowItemState

    entity_id = result["resulting_artifact_ids"][0]
    TenantContext.set_tenant(ctx.tenant_id)
    try:
        # TestCase is the one type whose Artifact.artifact_type is stored as
        # a compound "TestCase:<test_type>" value (TestService.create_test_case,
        # REQ-L2-AS-005 -- deliberate, tags the test type for differentiation);
        # the interview never sets test_type, so the service default "Unit"
        # applies. Every other in-scope type stores the bare name. An explicit
        # two-value `__in` rather than `__startswith`, which would also match
        # an unrelated longer type name.
        artifacts = list(
            Artifact.objects.filter(
                workspace_id=workspace.id,
                artifact_type__in=(artifact_type, f"{artifact_type}:Unit"),
            )
        )
        assert len(artifacts) == 1, (
            f"expected exactly one {artifact_type} Artifact row, got {len(artifacts)}"
        )
        # Scoped to the row this interview created (item_id is the subtype id,
        # which is what resulting_artifact_ids carries -- issue #736) and to
        # this workspace: an unscoped .exists() would pass on any leftover
        # state row of the same type.
        assert WorkflowItemState.objects.filter(
            item_type=artifact_type,
            item_id=entity_id,
            workspace_id=workspace.id,
        ).exists(), f"no WorkflowItemState initialized for {artifact_type} {entity_id}"
    finally:
        TenantContext.clear_tenant()


class TestFormalizeFactoryDefaultProtocol:
    """Tier 3: no attribute definition exists, so the factory default answers."""

    @pytest.mark.parametrize("artifact_type", IN_SCOPE_ARTIFACT_TYPES)
    def test_formalize_creates_the_artifact_for_every_in_scope_type(
        self, ctx, workspace, artifact_type
    ):
        svc = InterviewService()
        session = svc.start(ctx, artifact_type, workspace.id)
        _answer_all_required_fields(svc, ctx, session.id)

        result = svc.formalize(ctx, session.id)

        assert result["status"] == "completed"
        assert len(result["resulting_artifact_ids"]) == 1

    @pytest.mark.parametrize("artifact_type", IN_SCOPE_ARTIFACT_TYPES)
    def test_formalized_artifact_has_the_right_type_and_a_workflow_state(
        self, ctx, workspace, artifact_type
    ):
        """The adapters call the production create_X(), which initializes the
        workflow state -- that is the whole reason the registry exists (see
        interview_artifact_adapters module docstring)."""
        svc = InterviewService()
        session = svc.start(ctx, artifact_type, workspace.id)
        _answer_all_required_fields(svc, ctx, session.id)
        result = svc.formalize(ctx, session.id)

        _assert_artifact_and_workflow_state(ctx, workspace, artifact_type, result)


class TestFormalizeBootstrappedProtocol:
    """Tier 2: the tier a real, self_init-bootstrapped tenant resolves.

    ``get_protocol()`` prefers the attribute-definition-derived protocol over
    the factory default whenever a definition exists, and every tenant gets
    one at creation (``application.self_init`` -> ``bootstrap_attribute_
    definitions``). A regression that only fixes the factory default is
    therefore invisible to the tier-3 suite above and still broken in
    production -- which is exactly what happened to Risk.
    """

    @pytest.mark.parametrize("artifact_type", IN_SCOPE_ARTIFACT_TYPES)
    def test_formalize_round_trip_on_a_bootstrapped_tenant(
        self, ctx, bootstrapped_workspace, artifact_type
    ):
        svc = InterviewService()
        session = svc.start(ctx, artifact_type, bootstrapped_workspace.id)
        _answer_all_required_fields(svc, ctx, session.id)

        result = svc.formalize(ctx, session.id)

        assert result["status"] == "completed"
        assert len(result["resulting_artifact_ids"]) == 1
        _assert_artifact_and_workflow_state(
            ctx, bootstrapped_workspace, artifact_type, result
        )

    def test_bootstrapped_risk_protocol_elicits_probability_and_impact(
        self, ctx, bootstrapped_workspace
    ):
        """The specific regression: RiskService.create_risk has no default for
        either field, so a protocol that does not ask for them yields a
        session formalize() can only reject. Asserted on the resolved
        protocol, not just on the round trip, so a future change that drops
        one of the two fails here with a readable diff."""
        from application.interview_protocol import get_protocol

        # get_protocol() queries tenant-scoped tables directly; the service
        # methods above arm the context themselves, a bare call does not.
        TenantContext.set_tenant(ctx.tenant_id)
        try:
            protocol = get_protocol(ctx, "Risk", bootstrapped_workspace.id)
        finally:
            TenantContext.clear_tenant()
        elicited = {
            f.name for phase in protocol.phases for f in phase.required_fields
        }
        assert {"title", "probability", "impact"} <= elicited

    def test_bootstrapped_risk_carries_the_answered_probability_and_impact(
        self, ctx, bootstrapped_workspace
    ):
        """Elicited is not enough -- the answers must reach create_risk()."""
        from application.risk_service import RiskService

        svc = InterviewService()
        session = svc.start(ctx, "Risk", bootstrapped_workspace.id)
        _answer_all_required_fields(svc, ctx, session.id)
        result = svc.formalize(ctx, session.id)

        risk = RiskService().get_risk(
            uuid.UUID(result["resulting_artifact_ids"][0]), ctx
        )
        assert risk.probability in ("low", "medium", "high")
        assert risk.impact in ("low", "medium", "high")
