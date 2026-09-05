"""
DB-backed tests for the SE-conformance transition gates.

leaf_id : COMP-WE-002 (extension)

Lever 1 — mandatory-field completeness
    ``presets.registry.mandatory_fields`` is declared per rigor tier and is now
    enforced on approval transitions by
    ``workflow.precondition_rules.check_mandatory_fields``.

Lever 3 — verification evidence
    ``docs/se/V_AND_V_STRATEGY.md`` §3 "Passed" is derived from the trace graph
    plus the latest test-run results by
    ``workflow.precondition_rules.check_verification_evidence``.

Rule 7 — TestCase verifies-link coverage (GitHub #584)
    An Extended-tier TestCase may not be approved without a ``verifies`` link
    to a live Requirement or ArchitectureElement, enforced by
    ``workflow.precondition_rules.check_verifies_link``.

All gates are exercised through the real :class:`TransitionValidator` against
real workflow definitions and real preset configs — no mocks, because the whole
point of these levers is that a *declared* policy is actually consumed.
"""
from __future__ import annotations

import uuid

import pytest

from persistence.models import (
    Artifact,
    Requirement,
    Tenant,
    TestCase,
    TestRun,
    TestRunResult,
    TraceLink,
    Workspace,
)
from persistence.tenancy import TenantContext
from workflow.definition_store import PRESET_SCHEMAS
from workflow.precondition_rules import (
    EC_MANDATORY_FIELDS_MISSING,
    EC_VERIFICATION_EVIDENCE_MISSING,
    EC_VERIFIES_LINK_MISSING,
)
from workflow.services import create_default_workflow, outdate
from workflow.transition_validator import (
    TransitionValidator,
    ValidationRequest,
    _definition_cache,
)

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


class _SystemCtx:
    """Minimal AuthContext stand-in -- outdate() only reads ``user_id``."""

    user_id = "system:test-se-conformance-gates"


@pytest.fixture(autouse=True)
def _clean_caches():
    """Drop the process-level caches that survive the DB rollback."""
    TenantContext.clear_tenant()
    _definition_cache.clear()
    yield
    TenantContext.clear_tenant()
    _definition_cache.clear()
    from presets import gate

    with gate._cache_lock:
        gate._tier_cache.clear()


@pytest.fixture
def tenant() -> Tenant:
    return Tenant.objects.create(name="se-gate-tenant", slug="se-gate-tenant")


def _workspace(tenant: Tenant, tier: str) -> Workspace:
    """Create a workspace pinned to *tier* via ``Workspace.preset["name"]``."""
    TenantContext.set_tenant(tenant.id)
    try:
        return Workspace.objects.create(
            tenant=tenant, name=f"ws-{tier}-{uuid.uuid4().hex[:6]}",
            preset={"name": tier},
        )
    finally:
        TenantContext.clear_tenant()


def _make_workflow(tenant: Tenant, ws: Workspace, preset: str, item_type: str) -> None:
    """Create the workspace's workflow definition inside a tenant context."""
    TenantContext.set_tenant(tenant.id)
    try:
        create_default_workflow(
            workspace_id=ws.id,
            preset=preset,
            item_type=item_type,
            tenant_id=tenant.id,
        )
    finally:
        TenantContext.clear_tenant()


def _requirement(tenant: Tenant, workspace: Workspace, **fields) -> Requirement:
    TenantContext.set_tenant(tenant.id)
    try:
        artifact = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="requirement"
        )
        return Requirement.objects.create(
            tenant=tenant, artifact=artifact, **fields
        )
    finally:
        TenantContext.clear_tenant()


def _validate(
    *,
    tenant: Tenant,
    workspace: Workspace,
    item_id: uuid.UUID,
    item_type: str,
    current_state: str,
    target_state: str,
    roles: tuple[str, ...] = ("admin",),
    change_reason: str = "because",
):
    TenantContext.set_tenant(tenant.id)
    try:
        return TransitionValidator().validate(
            ValidationRequest(
                item_id=item_id,
                workspace_id=workspace.id,
                item_type=item_type,
                current_state=current_state,
                target_state=target_state,
                user_id=uuid.uuid4(),
                user_roles=roles,
                tenant_id=tenant.id,
                change_reason=change_reason,
            )
        )
    finally:
        TenantContext.clear_tenant()


# ---------------------------------------------------------------------------
# Lever 1 — mandatory-field completeness
# ---------------------------------------------------------------------------


class TestTierPolicyIsRead:
    """The tier policy is read from the registry, never re-derived."""

    def test_registry_tier_lists_are_what_the_gate_assumes(self):
        from presets.registry import (
            TIER_EXTENDED,
            TIER_MINIMAL,
            TIER_STANDARD,
            get_registry,
        )

        registry = get_registry()
        assert registry.get_preset_config(TIER_MINIMAL).mandatory_fields == (
            "title",
        )
        assert registry.get_preset_config(TIER_STANDARD).mandatory_fields == (
            "title",
            "description",
            "acceptance_criteria",
            "priority",
        )
        assert set(
            registry.get_preset_config(TIER_EXTENDED).mandatory_fields
        ) >= {"classification", "traceability_target", "change_reason"}

    def test_minimal_workflow_has_no_approval_state(self):
        """Minimal is a structural no-op: its schema is draft -> done."""
        assert "approved" not in PRESET_SCHEMAS["minimal"]["states"]
        assert "verified" not in PRESET_SCHEMAS["minimal"]["states"]
        assert "verified" not in PRESET_SCHEMAS["standard"]["states"]


class TestMandatoryFieldGate:
    """Approval transitions are gated on the tier's mandatory_fields."""

    def test_extended_blocks_requirement_missing_fields(self, tenant):
        ws = _workspace(tenant, "extended")
        _make_workflow(tenant, ws, "extended", "Requirement")
        req = _requirement(tenant, ws, title="R1", description="", acceptance_criteria="")

        result = _validate(
            tenant=tenant,
            workspace=ws,
            item_id=req.id,
            item_type="Requirement",
            current_state="in_review",
            target_state="approved",
        )

        assert result.valid is False
        assert result.error_code == EC_MANDATORY_FIELDS_MISSING
        assert "description" in result.error_message
        assert "acceptance_criteria" in result.error_message
        # traceability_target is the SE-Auditor's mandate, not a scalar field.
        assert "traceability_target" not in result.error_message

    def test_extended_allows_complete_requirement(self, tenant):
        ws = _workspace(tenant, "extended")
        _make_workflow(tenant, ws, "extended", "Requirement")
        req = _requirement(
            tenant,
            ws,
            title="R1",
            description="A description",
            acceptance_criteria="Given/When/Then",
        )

        result = _validate(
            tenant=tenant,
            workspace=ws,
            item_id=req.id,
            item_type="Requirement",
            current_state="in_review",
            target_state="approved",
        )

        assert result.valid is True, result.error_message

    def test_extended_blocks_when_change_reason_is_blank(self, tenant):
        """``change_reason`` is a request-level mandatory field on Extended.

        Rule 3 already rejects it for this transition, so assert the earlier
        rule wins and the message stays specific rather than being swallowed.
        """
        ws = _workspace(tenant, "extended")
        _make_workflow(tenant, ws, "extended", "Requirement")
        req = _requirement(
            tenant, ws, title="R1", description="d", acceptance_criteria="ac"
        )

        result = _validate(
            tenant=tenant,
            workspace=ws,
            item_id=req.id,
            item_type="Requirement",
            current_state="in_review",
            target_state="approved",
            change_reason="",
        )

        assert result.valid is False
        assert result.error_code == "CHANGE_REASON_REQUIRED"

    def test_standard_blocks_and_skips_inapplicable_fields(self, tenant):
        """Standard gates draft -> approved; 'priority' is not a Requirement field."""
        ws = _workspace(tenant, "standard")
        _make_workflow(tenant, ws, "standard", "Requirement")
        req = _requirement(
            tenant, ws, title="R1", description="", acceptance_criteria="ac"
        )

        result = _validate(
            tenant=tenant,
            workspace=ws,
            item_id=req.id,
            item_type="Requirement",
            current_state="draft",
            target_state="approved",
        )

        assert result.valid is False
        assert result.error_code == EC_MANDATORY_FIELDS_MISSING
        assert "description" in result.error_message
        # Requirement has no `priority`/`moscow_priority` column, so the policy
        # field is not applicable and must not appear.
        assert "priority" not in result.error_message
        assert "'standard' preset" in result.error_message

    def test_minimal_is_a_no_op(self, tenant):
        """Minimal has only ``title`` mandatory and no approval state at all."""
        ws = _workspace(tenant, "minimal")
        _make_workflow(tenant, ws, "minimal", "Requirement")
        req = _requirement(
            tenant, ws, title="R1", description="", acceptance_criteria=""
        )

        result = _validate(
            tenant=tenant,
            workspace=ws,
            item_id=req.id,
            item_type="Requirement",
            current_state="draft",
            target_state="done",
        )

        assert result.valid is True, result.error_message

    def test_non_approval_transition_is_untouched(self, tenant):
        """A draft-internal transition never triggers field completeness."""
        ws = _workspace(tenant, "extended")
        _make_workflow(tenant, ws, "extended", "Requirement")
        req = _requirement(
            tenant, ws, title="R1", description="", acceptance_criteria=""
        )

        result = _validate(
            tenant=tenant,
            workspace=ws,
            item_id=req.id,
            item_type="Requirement",
            current_state="draft",
            target_state="in_review",
        )

        assert result.valid is True, result.error_message


class TestSharedValidatorStaysGenericAcrossArtifactTypes:
    """Requirement-shaped policy fields must not leak onto other types."""

    def _adr(self, tenant: Tenant, ws: Workspace, **fields):
        from application.models import Adr

        TenantContext.set_tenant(tenant.id)
        try:
            artifact = Artifact.objects.create(
                tenant=tenant, workspace=ws, artifact_type="adr"
            )
            return Adr.objects.create(
                artifact=artifact,
                tenant_id=tenant.id,
                workspace_id=ws.id,
                **fields,
            )
        finally:
            TenantContext.clear_tenant()

    def test_adr_approval_is_not_blocked_by_requirement_fields(self, tenant):
        ws = _workspace(tenant, "extended")
        _make_workflow(tenant, ws, "adr_default", "Adr")
        adr = self._adr(tenant, ws, title="ADR-1", description="a decision")

        result = _validate(
            tenant=tenant,
            workspace=ws,
            item_id=adr.id,
            item_type="Adr",
            current_state="In Review",
            target_state="Approved",
        )

        assert result.valid is True, result.error_message

    def test_change_request_ccb_decision_is_exempt(self, tenant):
        """``ccb_approval``'s "approved" is a decision, not artefact readiness."""
        from application.models import ChangeRequest

        ws = _workspace(tenant, "standard")
        _make_workflow(tenant, ws, "ccb_approval", "ChangeRequest")
        TenantContext.set_tenant(tenant.id)
        try:
            cr = ChangeRequest.objects.create(
                tenant_id=tenant.id,
                workspace_id=ws.id,
                title="CR-1",
                description="",
            )
        finally:
            TenantContext.clear_tenant()

        result = _validate(
            tenant=tenant,
            workspace=ws,
            item_id=cr.id,
            item_type="ChangeRequest",
            current_state="under_review",
            target_state="approved",
        )

        assert result.valid is True, result.error_message


# ---------------------------------------------------------------------------
# Lever 3 — verification evidence (V&V strategy §3 "Passed")
# ---------------------------------------------------------------------------


def _testcase(tenant: Tenant, ws: Workspace, title: str) -> tuple[Artifact, TestCase]:
    TenantContext.set_tenant(tenant.id)
    try:
        artifact = Artifact.objects.create(
            tenant=tenant, workspace=ws, artifact_type="testcase"
        )
        tc = TestCase.objects.create(tenant=tenant, artifact=artifact, title=title)
        return artifact, tc
    finally:
        TenantContext.clear_tenant()


def _verifies(tenant: Tenant, tc_artifact: Artifact, req_artifact: Artifact) -> None:
    """Create the link in the SE direction: TestCase -> Requirement."""
    TenantContext.set_tenant(tenant.id)
    try:
        TraceLink.objects.create(
            tenant=tenant,
            source=tc_artifact,
            target=req_artifact,
            link_type="verifies",
        )
    finally:
        TenantContext.clear_tenant()


def _run(tenant: Tenant, ws: Workspace, tc: TestCase, status: str) -> None:
    TenantContext.set_tenant(tenant.id)
    try:
        run = TestRun.objects.create(
            tenant=tenant, workspace=ws, name=f"run-{uuid.uuid4().hex[:6]}"
        )
        TestRunResult.objects.create(
            tenant=tenant,
            test_run=run,
            test_case=tc,
            test_case_title=tc.title,
            status=status,
        )
    finally:
        TenantContext.clear_tenant()


class TestVerificationEvidenceGate:
    """``implemented -> verified`` is derived, not claimed."""

    @pytest.fixture
    def extended_ws(self, tenant):
        ws = _workspace(tenant, "extended")
        _make_workflow(tenant, ws, "extended", "Requirement")
        return ws

    def _complete_req(self, tenant, ws) -> Requirement:
        return _requirement(
            tenant, ws, title="R1", description="d", acceptance_criteria="ac"
        )

    def test_rejected_without_any_verifying_testcase(self, tenant, extended_ws):
        req = self._complete_req(tenant, extended_ws)

        result = _validate(
            tenant=tenant,
            workspace=extended_ws,
            item_id=req.id,
            item_type="Requirement",
            current_state="implemented",
            target_state="verified",
        )

        assert result.valid is False
        assert result.error_code == EC_VERIFICATION_EVIDENCE_MISSING
        assert "no active TestCase" in result.error_message

    def test_rejected_when_testcase_never_ran(self, tenant, extended_ws):
        req = self._complete_req(tenant, extended_ws)
        tc_art, _tc = _testcase(tenant, extended_ws, "TC-1")
        _verifies(tenant, tc_art, req.artifact)

        result = _validate(
            tenant=tenant,
            workspace=extended_ws,
            item_id=req.id,
            item_type="Requirement",
            current_state="implemented",
            target_state="verified",
        )

        assert result.valid is False
        assert result.error_code == EC_VERIFICATION_EVIDENCE_MISSING
        assert "Not Run" in result.error_message
        assert str(tc_art.id) in result.error_message

    def test_rejected_when_latest_run_failed(self, tenant, extended_ws):
        req = self._complete_req(tenant, extended_ws)
        tc_art, tc = _testcase(tenant, extended_ws, "TC-1")
        _verifies(tenant, tc_art, req.artifact)
        _run(tenant, extended_ws, tc, "failed")

        result = _validate(
            tenant=tenant,
            workspace=extended_ws,
            item_id=req.id,
            item_type="Requirement",
            current_state="implemented",
            target_state="verified",
        )

        assert result.valid is False
        assert result.error_code == EC_VERIFICATION_EVIDENCE_MISSING
        assert str(tc_art.id) in result.error_message

    def test_accepted_when_every_verifying_testcase_passed(
        self, tenant, extended_ws
    ):
        req = self._complete_req(tenant, extended_ws)
        tc1_art, tc1 = _testcase(tenant, extended_ws, "TC-1")
        tc2_art, tc2 = _testcase(tenant, extended_ws, "TC-2")
        _verifies(tenant, tc1_art, req.artifact)
        _verifies(tenant, tc2_art, req.artifact)
        _run(tenant, extended_ws, tc1, "passed")
        _run(tenant, extended_ws, tc2, "passed")

        result = _validate(
            tenant=tenant,
            workspace=extended_ws,
            item_id=req.id,
            item_type="Requirement",
            current_state="implemented",
            target_state="verified",
        )

        assert result.valid is True, result.error_message

    def test_rejected_when_one_of_several_testcases_failed(
        self, tenant, extended_ws
    ):
        req = self._complete_req(tenant, extended_ws)
        tc1_art, tc1 = _testcase(tenant, extended_ws, "TC-1")
        tc2_art, tc2 = _testcase(tenant, extended_ws, "TC-2")
        _verifies(tenant, tc1_art, req.artifact)
        _verifies(tenant, tc2_art, req.artifact)
        _run(tenant, extended_ws, tc1, "passed")
        _run(tenant, extended_ws, tc2, "blocked")

        result = _validate(
            tenant=tenant,
            workspace=extended_ws,
            item_id=req.id,
            item_type="Requirement",
            current_state="implemented",
            target_state="verified",
        )

        assert result.valid is False
        assert str(tc2_art.id) in result.error_message
        assert str(tc1_art.id) not in result.error_message

    def test_link_direction_matters(self, tenant, extended_ws):
        """A backwards link (Requirement -> TestCase) is not evidence."""
        req = self._complete_req(tenant, extended_ws)
        tc_art, tc = _testcase(tenant, extended_ws, "TC-1")
        _verifies(tenant, req.artifact, tc_art)  # deliberately reversed
        _run(tenant, extended_ws, tc, "passed")

        result = _validate(
            tenant=tenant,
            workspace=extended_ws,
            item_id=req.id,
            item_type="Requirement",
            current_state="implemented",
            target_state="verified",
        )

        assert result.valid is False
        assert result.error_code == EC_VERIFICATION_EVIDENCE_MISSING


# ---------------------------------------------------------------------------
# Rule 7 — a TestCase must verify something before it can be approved (#584)
# ---------------------------------------------------------------------------


def _approvable_testcase(
    tenant: Tenant, ws: Workspace, title: str
) -> tuple[Artifact, TestCase]:
    """A TestCase that already satisfies rule 5 on every tier.

    ``description`` is a ``mandatory_fields`` entry from Standard upwards, so a
    bare ``_testcase()`` is rejected by rule 5 before rule 7 is ever reached.
    Filling it in keeps these tests about the verifies link only.
    """
    TenantContext.set_tenant(tenant.id)
    try:
        artifact = Artifact.objects.create(
            tenant=tenant, workspace=ws, artifact_type="testcase"
        )
        tc = TestCase.objects.create(
            tenant=tenant,
            artifact=artifact,
            title=title,
            description="Steps are documented elsewhere.",
        )
        return artifact, tc
    finally:
        TenantContext.clear_tenant()


def _architecture_element(tenant: Tenant, ws: Workspace, title: str):
    from persistence.models import ArchitectureElement

    TenantContext.set_tenant(tenant.id)
    try:
        artifact = Artifact.objects.create(
            tenant=tenant, workspace=ws, artifact_type="architectureelement"
        )
        element = ArchitectureElement.objects.create(
            tenant=tenant, artifact=artifact, title=title, element_type="component"
        )
        return artifact, element
    finally:
        TenantContext.clear_tenant()


class TestVerifiesLinkGate:
    """GH-584(a): ``ready -> approved`` on a TestCase needs a verifies link.

    The V&V chain Requirement -> TestCase -> TestRun was structurally present
    but functionally broken at the first hop (0 of 30 TestCases carried a
    ``verifies`` link). The gate lives at the approval transition — the same
    place rule 5 consumes ``mandatory_fields`` — rather than at create time,
    because both the REST and the MCP create paths build the entity first and
    the link afterwards.
    """

    @pytest.fixture
    def extended_ws(self, tenant):
        ws = _workspace(tenant, "extended")
        _make_workflow(tenant, ws, "testcase_default", "TestCase")
        return ws

    def _approve(self, tenant, ws, tc):
        return _validate(
            tenant=tenant,
            workspace=ws,
            item_id=tc.id,
            item_type="TestCase",
            current_state="ready",
            target_state="approved",
        )

    def test_extended_blocks_testcase_without_verifies_link(self, tenant, extended_ws):
        _tc_art, tc = _approvable_testcase(tenant, extended_ws, "Orphan TC")

        result = self._approve(tenant, extended_ws, tc)

        assert result.valid is False
        assert result.error_code == EC_VERIFIES_LINK_MISSING
        assert "verifies" in result.error_message

    def test_extended_allows_testcase_verifying_a_requirement(
        self, tenant, extended_ws
    ):
        req = _requirement(
            tenant, extended_ws, title="R1", description="d", acceptance_criteria="ac"
        )
        tc_art, tc = _approvable_testcase(tenant, extended_ws, "Linked TC")
        _verifies(tenant, tc_art, req.artifact)

        result = self._approve(tenant, extended_ws, tc)

        assert result.valid is True, result.error_message

    def test_extended_allows_testcase_verifying_an_architecture_element(
        self, tenant, extended_ws
    ):
        """SE_LINK_SEMANTICS allows TestCase -> ArchitectureElement too."""
        arch_art, _arch = _architecture_element(tenant, extended_ws, "Component A")
        tc_art, tc = _approvable_testcase(tenant, extended_ws, "Linked TC")
        _verifies(tenant, tc_art, arch_art)

        result = self._approve(tenant, extended_ws, tc)

        assert result.valid is True, result.error_message

    def test_link_direction_matters(self, tenant, extended_ws):
        """A reversed link (Requirement -> TestCase) is not coverage."""
        req = _requirement(
            tenant, extended_ws, title="R1", description="d", acceptance_criteria="ac"
        )
        tc_art, tc = _approvable_testcase(tenant, extended_ws, "Backwards TC")
        _verifies(tenant, req.artifact, tc_art)  # deliberately reversed

        result = self._approve(tenant, extended_ws, tc)

        assert result.valid is False
        assert result.error_code == EC_VERIFIES_LINK_MISSING

    def test_link_to_a_soft_deleted_requirement_is_not_coverage(
        self, tenant, extended_ws
    ):
        """Same target pool as TRACE-P6: an outdated target does not count."""
        req = _requirement(
            tenant, extended_ws, title="R1", description="d", acceptance_criteria="ac"
        )
        tc_art, tc = _approvable_testcase(tenant, extended_ws, "TC of a deleted Req")
        _verifies(tenant, tc_art, req.artifact)
        # Task 12: the `status` column is dropped -- outdating a Requirement
        # is now only representable through the engine (workflow.services
        # .outdate), the same real path RequirementService.delete_requirement
        # uses in production. This class's `extended_ws` fixture only
        # provisions a TestCase workflow definition, so a Requirement one is
        # provisioned here too (outdate()'s lazy-init needs a definition to
        # create the WorkflowItemState row against).
        _make_workflow(tenant, extended_ws, "standard", "Requirement")
        TenantContext.set_tenant(tenant.id)
        try:
            outdate(
                item_id=req.id,
                item_type="Requirement",
                workspace_id=extended_ws.id,
                ctx=_SystemCtx(),
                reason="test: simulate soft-deleted Requirement",
            )
        finally:
            TenantContext.clear_tenant()

        result = self._approve(tenant, extended_ws, tc)

        assert result.valid is False
        assert result.error_code == EC_VERIFIES_LINK_MISSING

    def test_a_second_live_target_still_satisfies_the_gate(
        self, tenant, extended_ws
    ):
        """Multiple 'verifies' targets: any single live one satisfies the gate."""
        old_req = _requirement(
            tenant, extended_ws, title="Old R", description="d", acceptance_criteria="ac"
        )
        live_req = _requirement(
            tenant, extended_ws, title="Live R", description="d", acceptance_criteria="ac"
        )
        tc_art, tc = _approvable_testcase(tenant, extended_ws, "TC with two subjects")
        _verifies(tenant, tc_art, old_req.artifact)
        _verifies(tenant, tc_art, live_req.artifact)

        result = self._approve(tenant, extended_ws, tc)

        assert result.valid is True, result.error_message

    def test_standard_tier_does_not_gate_the_testcase(self, tenant):
        """Tier lever: only Extended declares ``traceability_target``."""
        ws = _workspace(tenant, "standard")
        _make_workflow(tenant, ws, "testcase_default", "TestCase")
        _tc_art, tc = _approvable_testcase(tenant, ws, "Orphan TC")

        result = self._approve(tenant, ws, tc)

        assert result.valid is True, result.error_message

    def test_minimal_tier_does_not_gate_the_testcase(self, tenant):
        ws = _workspace(tenant, "minimal")
        _make_workflow(tenant, ws, "testcase_default", "TestCase")
        _tc_art, tc = _approvable_testcase(tenant, ws, "Orphan TC")

        result = self._approve(tenant, ws, tc)

        assert result.valid is True, result.error_message

    def test_non_approval_transition_is_untouched(self, tenant, extended_ws):
        """draft -> ready must keep working for an unlinked TestCase."""
        _tc_art, tc = _approvable_testcase(tenant, extended_ws, "Orphan TC")

        result = _validate(
            tenant=tenant,
            workspace=extended_ws,
            item_id=tc.id,
            item_type="TestCase",
            current_state="draft",
            target_state="ready",
            roles=("editor",),
        )

        assert result.valid is True, result.error_message

    def test_requirement_approval_is_untouched_by_rule_7(self, tenant):
        """Control: rule 7 is TestCase-only; Requirements keep rule 5's verdict."""
        ws = _workspace(tenant, "extended")
        _make_workflow(tenant, ws, "extended", "Requirement")
        req = _requirement(
            tenant, ws, title="R1", description="d", acceptance_criteria="ac"
        )

        result = _validate(
            tenant=tenant,
            workspace=ws,
            item_id=req.id,
            item_type="Requirement",
            current_state="in_review",
            target_state="approved",
        )

        assert result.valid is True, result.error_message
