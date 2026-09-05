"""
Round-trip fidelity tests for COMP-AS-008 ExportService and COMP-AS-009
ImportService.

leaf_id : COMP-AS-008, COMP-AS-009
req_id  : REQ-L1-019, REQ-L1-021, REQ-L3-EXP-002, REQ-L3-IMP-001..004

These are real-DB tests (not mocked): an entity is created, exported to CSV,
the original (and its backing Artifact) is deleted, then the CSV is re-imported.
The re-imported row must reproduce the original exactly — including ``id``,
``version`` and the audit timestamps (``created_at`` and the model's modified
timestamp) — for every supported entity type:

    StakeholderNeed, Requirement, ArchitectureElement, TestCase  (persistence)
    Adr, Risk, Issue                                             (application)

This is the safety net for the ReqFlow self-migration: the docs/se register is
only safe to import if ``export -> import`` is lossless.

Datenmodell-Konsolidierung Task 12: the ``status`` column is dropped from
every status-bearing type above (all but ArchitectureElement). Status now
round-trips exclusively through ``WorkflowItemState`` — real production
workspaces always have one (``workspace_provisioning.WORKFLOW_ENTITY_TYPES``
provisions every type's definition at workspace creation), so the tests below
create one explicitly to exercise the realistic, lossless path; a
definition-less workspace is a documented, reviewed data-loss edge case (see
the Task 12 report Finding 2), not the common case this safety net protects.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from application.export_service import ExportService
from application.import_service import ImportService
from application.models import Adr, Issue, Risk
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import (
    ArchitectureElement,
    Artifact,
    Requirement,
    StakeholderNeed,
    TestCase,
    Tenant,
    Workspace,
)
from workflow import state_reader
from workflow.models import WorkflowEngineDefinition

pytestmark = pytest.mark.django_db


# A deliberately non-"now" timestamp so preservation is observable: a fresh
# create would stamp the current time, which would not equal this value.
_FIXED_TS = datetime(2020, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
_FIXED_VERSION = 7


# ---------- Helpers ----------


def _make_ctx(tenant_id):
    ctx = MagicMock()
    ctx.tenant_id = tenant_id
    ctx.user_id = uuid.uuid4()
    ctx.active_roles = ("editor",)
    ctx.has_role = lambda role: role in ctx.active_roles
    return ctx


@pytest.fixture(autouse=True)
def _clear_ctx():
    clear_request_tenant()
    yield
    clear_request_tenant()


@pytest.fixture
def ws():
    tenant = Tenant.objects.create(name="RT-T", slug="rt-roundtrip", is_active=True)
    set_request_tenant(tenant.id)
    workspace = Workspace.objects.create(tenant=tenant, name="RT WS")
    yield {"tenant": tenant, "workspace": workspace, "ctx": _make_ctx(tenant.id)}
    clear_request_tenant()


def _stamp_persistence(model, pk):
    """Force id-independent audit fields to fixed, non-'now' values."""
    model.objects.filter(pk=pk).update(
        version=_FIXED_VERSION, created_at=_FIXED_TS, modified_at=_FIXED_TS
    )


def _stamp_app(model, pk):
    model.objects.filter(pk=pk).update(
        version=_FIXED_VERSION, created_at=_FIXED_TS, updated_at=_FIXED_TS
    )


def _make_definition(ws, item_type, states):
    """Provision a WorkflowEngineDefinition so status round-trips via
    WorkflowItemState (Task 12) instead of the dropped `status` column."""
    return WorkflowEngineDefinition.objects.create(
        tenant=ws["tenant"],
        workspace_id=ws["workspace"].id,
        item_type=item_type,
        preset=WorkflowEngineDefinition.PRESET_STANDARD,
        workflow_json={"states": states, "transitions": []},
    )


def _export_csv(entity_type, workspace_id, ctx):
    with patch(
        "application.export_service.ExportService._get_terminology_profile",
        return_value="standard",
    ):
        return ExportService().export_csv(entity_type, workspace_id, ctx)


def _roundtrip(entity_type, model, original, ws):
    """Export -> delete original+artifact -> import. Return the re-imported obj."""
    ctx = ws["ctx"]
    artifact_id = original.artifact_id
    export = _export_csv(entity_type, ws["workspace"].id, ctx)
    assert export.record_count == 1

    # Drop the original so the preserved primary key is free to be re-inserted
    # (models restore into a clean target — the migration scenario).
    Artifact.objects.filter(id=artifact_id).delete()  # cascades to the entity
    assert not model.objects.filter(pk=original.id).exists()

    result = ImportService().import_csv(
        csv_text=export.content,
        entity_type=entity_type,
        workspace_id=ws["workspace"].id,
        ctx=ctx,
    )
    assert result.success, result.errors
    assert result.imported_count == 1

    return model.objects.get(pk=original.id)


def _assert_identity(reimported, *, artifact_id, modified_attr="modified_at"):
    assert reimported.id is not None
    assert reimported.version == _FIXED_VERSION
    assert reimported.created_at == _FIXED_TS
    assert getattr(reimported, modified_attr) == _FIXED_TS
    # Backing Artifact reference is preserved verbatim.
    assert reimported.artifact_id == artifact_id


# ---------- Persistence-app entities ----------


class TestPersistenceRoundTrip:
    def test_requirement_roundtrip(self, ws):
        """Task 12: the `status` column is dropped. A definition-provisioned
        workspace (the realistic case -- see module docstring) round-trips
        status through WorkflowItemState: the original has no engine state
        (created directly, bypassing RequirementService), so it exports at
        its "draft" preset initial state, and import re-seeds exactly that
        value via the same definition."""
        t, w = ws["tenant"], ws["workspace"]
        _make_definition(ws, "Requirement", ["draft", "in_review", "approved", "deprecated"])
        art = Artifact.objects.create(tenant=t, workspace=w, artifact_type="Requirement")
        req = Requirement.objects.create(
            tenant=t,
            artifact=art,
            title="Req Alpha",
            description="Alpha description",
            category="functional",
            type="SyReq",
            level=1,
            uid="REQ-RT-001",
        )
        _stamp_persistence(Requirement, req.id)

        out = _roundtrip("Requirement", Requirement, req, ws)

        _assert_identity(out, artifact_id=art.id)
        assert out.title == "Req Alpha"
        assert out.description == "Alpha description"
        assert out.category == "functional"
        assert state_reader.current_state("Requirement", out.id) == "draft"
        assert out.type == "SyReq"
        assert out.level == 1
        assert out.uid == "REQ-RT-001"

    def test_stakeholder_need_roundtrip(self, ws):
        t, w = ws["tenant"], ws["workspace"]
        art = Artifact.objects.create(
            tenant=t, workspace=w, artifact_type="StakeholderNeed"
        )
        need = StakeholderNeed.objects.create(
            tenant=t,
            artifact=art,
            title="Need Alpha",
            description="Need description",
            category="functional",
            moscow_priority="Must",
            uid="NEED-RT-001",
        )
        _stamp_persistence(StakeholderNeed, need.id)

        out = _roundtrip("StakeholderNeed", StakeholderNeed, need, ws)

        _assert_identity(out, artifact_id=art.id)
        assert out.title == "Need Alpha"
        assert out.moscow_priority == "Must"
        assert out.uid == "NEED-RT-001"

    def test_architecture_element_roundtrip(self, ws):
        t, w = ws["tenant"], ws["workspace"]
        art = Artifact.objects.create(
            tenant=t, workspace=w, artifact_type="ArchitectureElement"
        )
        elem = ArchitectureElement.objects.create(
            tenant=t,
            artifact=art,
            title="Elem Alpha",
            description="Elem description",
            element_type="component",
            asil_level="B",
            uid="AE-RT-001",
        )
        _stamp_persistence(ArchitectureElement, elem.id)

        out = _roundtrip("ArchitectureElement", ArchitectureElement, elem, ws)

        _assert_identity(out, artifact_id=art.id)
        assert out.element_type == "component"
        assert out.asil_level == "B"
        assert out.uid == "AE-RT-001"

    def test_testcase_roundtrip_preserves_json_steps(self, ws):
        t, w = ws["tenant"], ws["workspace"]
        steps = [
            {"action": "click login", "expected": "form shown"},
            {"action": "submit", "expected": "200 OK"},
        ]
        art = Artifact.objects.create(tenant=t, workspace=w, artifact_type="TestCase")
        tc = TestCase.objects.create(
            tenant=t,
            artifact=art,
            title="TC Alpha",
            description="TC description",
            steps=steps,
            uid="TC-RT-001",
        )
        _stamp_persistence(TestCase, tc.id)

        out = _roundtrip("TestCase", TestCase, tc, ws)

        _assert_identity(out, artifact_id=art.id)
        assert out.steps == steps  # JSON list survived the CSV round-trip
        assert out.uid == "TC-RT-001"


# ---------- Application-app entities (Adr / Risk / Issue) ----------


class TestAppModelRoundTrip:
    def test_adr_roundtrip(self, ws):
        """Task 12: closes a pre-existing gap -- CSV import never seeded
        WorkflowItemState for Adr/Risk/Issue before this task (it bypasses
        AdrService.create_adr's own initialize_workflow_states call), so
        status round-tripped only through the (now-dropped) column. It now
        round-trips through the engine like every other type, given a
        provisioned definition (the realistic case -- see module docstring)."""
        t, w = ws["tenant"], ws["workspace"]
        _make_definition(
            ws, "Adr", ["Draft", "In Review", "Approved", "Rejected", "Superseded"]
        )
        art = Artifact.objects.create(tenant=t, workspace=w, artifact_type="Adr")
        adr = Adr.objects.create(
            artifact=art,
            workspace_id=w.id,
            tenant_id=t.id,
            title="Use REST over SOAP",
            description="REST is simpler",
            context="API design",
            consequences="Simpler clients",
            uid="ADR-RT-001",
            created_by="author-1",
        )
        _stamp_app(Adr, adr.id)

        out = _roundtrip("Adr", Adr, adr, ws)

        _assert_identity(out, artifact_id=art.id, modified_attr="updated_at")
        assert out.title == "Use REST over SOAP"
        assert out.context == "API design"
        assert out.consequences == "Simpler clients"
        # The original has no engine state (created directly, bypassing
        # AdrService) -- exports/re-imports at the adr_default initial state.
        assert state_reader.current_state("Adr", out.id) == "Draft"
        assert out.uid == "ADR-RT-001"
        assert out.created_by == "author-1"
        assert out.workspace_id == w.id
        assert out.tenant_id == t.id

    def test_risk_roundtrip_preserves_score_and_severity(self, ws):
        t, w = ws["tenant"], ws["workspace"]
        _make_definition(
            ws, "Risk", ["Identified", "Monitored", "Mitigated", "Accepted", "Closed"]
        )
        art = Artifact.objects.create(tenant=t, workspace=w, artifact_type="Risk")
        risk = Risk.objects.create(
            artifact=art,
            workspace_id=w.id,
            tenant_id=t.id,
            title="Data loss risk",
            description="Backups may fail",
            category="technical",
            probability="high",
            impact="high",
            risk_score=9,
            severity="high",
            owner="ops-team",
            mitigation_strategy="Add redundancy",
            detection=8,
            uid="RISK-RT-001",
            created_by="author-2",
        )
        _stamp_app(Risk, risk.id)

        out = _roundtrip("Risk", Risk, risk, ws)

        _assert_identity(out, artifact_id=art.id, modified_attr="updated_at")
        assert out.probability == "high"
        assert out.impact == "high"
        assert out.risk_score == 9
        assert out.severity == "high"
        assert out.detection == 8
        assert out.owner == "ops-team"
        assert state_reader.current_state("Risk", out.id) == "Identified"
        assert out.uid == "RISK-RT-001"

    def test_issue_roundtrip_preserves_tags(self, ws):
        t, w = ws["tenant"], ws["workspace"]
        _make_definition(
            ws, "Issue", ["Open", "In Progress", "Resolved", "Closed", "Wontfix"]
        )
        assignee = uuid.uuid4()
        art = Artifact.objects.create(tenant=t, workspace=w, artifact_type="Issue")
        issue = Issue.objects.create(
            artifact=art,
            workspace_id=w.id,
            tenant_id=t.id,
            title="Login fails on Safari",
            description="500 on submit",
            severity="high",
            category="defect",
            assignee_id=assignee,
            tags=["frontend", "auth"],
            uid="ISSUE-RT-001",
            created_by="author-3",
        )
        _stamp_app(Issue, issue.id)

        out = _roundtrip("Issue", Issue, issue, ws)

        _assert_identity(out, artifact_id=art.id, modified_attr="updated_at")
        assert out.severity == "high"
        assert out.category == "defect"
        assert state_reader.current_state("Issue", out.id) == "Open"
        assert out.assignee_id == assignee
        assert out.tags == ["frontend", "auth"]
        assert out.uid == "ISSUE-RT-001"


# ---------- Backward compatibility: hand-authored CSV without identity columns ----------


class TestMinimalCsvBackwardCompat:
    def test_minimal_requirement_csv_generates_fresh_identity(self, ws):
        """A CSV with only content columns still imports (no id/version/ts).

        Fresh UUIDs, version 1 and model defaults must apply — the pre-existing
        importer behaviour must not regress.
        """
        csv_text = "title,description\nHand Written,Typed by a user\n"

        result = ImportService().import_csv(
            csv_text=csv_text,
            entity_type="Requirement",
            workspace_id=ws["workspace"].id,
            ctx=ws["ctx"],
        )
        assert result.success, result.errors
        assert result.imported_count == 1

        req = Requirement.objects.get(title="Hand Written")
        assert req.description == "Typed by a user"
        assert req.version == 1  # default, not preserved
        # Task 12: the `status` column (and its "draft" default) is gone, and
        # this workspace has no WorkflowEngineDefinition -- no engine state
        # is created either (documented, reviewed data-loss tradeoff, see the
        # Task 12 report Finding 2). state_reader falls back to the "draft"
        # preset initial state for any caller reading it through the seam.
        assert state_reader.current_state("Requirement", req.id) is None
        assert state_reader.initial_state("Requirement") == "draft"
