"""
Tests for COMP-AS-008b ReqifImportService (REQ-147).

leaf_id : COMP-AS-008b
req_id  : REQ-147

Round-trips real ORM data through ReqifExportService -> ReqIF 1.2 XML ->
ReqifImportService into a *second* workspace, asserting object/relation
counts, hierarchy, and idempotency on re-import. Also covers dry-run,
per-object/per-relation soft-error handling, and the REQ-143 status-mirror
coupling (mapping onto a WorkflowEngineDefinition's states, or normalising
to "draft" when no definition exists).

DB-marker convention mirrors test_reqif_export_service.py: module-level
``pytestmark = pytest.mark.django_db``, tenant context activated via
persistence.middleware.set_request_tenant/clear_request_tenant.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest

from application.base import ValidationError
from application.reqif_export_service import ReqifExportService
from application.reqif_import_service import ReqifImportService
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import (
    Artifact,
    Requirement,
    StakeholderNeed,
    Tenant,
    TraceLink,
    Workspace,
)
from workflow.models import WorkflowEngineDefinition, WorkflowItemState

pytestmark = pytest.mark.django_db


# ---------- Helpers ----------


def _make_ctx(tenant_id):
    ctx = MagicMock()
    ctx.tenant_id = tenant_id
    ctx.user_id = uuid.uuid4()
    ctx.active_roles = ("editor",)
    return ctx


def _export(workspace_id, tenant_id) -> str:
    svc = ReqifExportService()
    return svc.export_reqif(workspace_id=workspace_id, ctx=_make_ctx(tenant_id)).content


def _import(reqif_text, workspace_id, tenant_id, dry_run=False):
    svc = ReqifImportService()
    return svc.import_reqif(
        reqif_text=reqif_text,
        workspace_id=workspace_id,
        ctx=_make_ctx(tenant_id),
        dry_run=dry_run,
    )


# ---------- Fixture: source workspace with hierarchy + tracelinks ----------


@pytest.fixture
def source_workspace():
    """Same shape as test_reqif_export_service.reqif_workspace.

    Tree:  need1 -> req1 -> req2   (3 levels deep)
           need2                    (top-level)
           req3                     (top-level)
    TraceLinks: req1 --satisfies--> need1, req2 --verifies--> req1
    """
    tenant = Tenant.objects.create(
        name="Reqif-Import-Src-T", slug="reqif-import-src-t", is_active=True
    )
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="Reqif Import Src WS", preset={"name": "standard"}
        )

        need1_art = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="StakeholderNeed"
        )
        need1 = StakeholderNeed.objects.create(
            tenant=tenant,
            artifact=need1_art,
            title="Need One",
            description="First need",
            category="functional",
            moscow_priority="Must",
            uid="NEED-001",
        )
        need2_art = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="StakeholderNeed"
        )
        need2 = StakeholderNeed.objects.create(
            tenant=tenant,
            artifact=need2_art,
            title="Need Two",
            description="Second need",
            category="functional",
            uid="NEED-002",
        )

        req1_art = Artifact.objects.create(
            tenant=tenant,
            workspace=workspace,
            artifact_type="Requirement",
            parent=need1_art,
        )
        req1 = Requirement.objects.create(
            tenant=tenant,
            artifact=req1_art,
            title="Req One",
            description="Req one description",
            category="functional",
            verification_method="Test",
            uid="REQ-001",
        )
        req2_art = Artifact.objects.create(
            tenant=tenant,
            workspace=workspace,
            artifact_type="Requirement",
            parent=req1_art,
        )
        req2 = Requirement.objects.create(
            tenant=tenant,
            artifact=req2_art,
            title="Req Two",
            description="Req two description",
            category="functional",
            verification_method="Review",
            uid="REQ-002",
        )
        req3_art = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="Requirement"
        )
        req3 = Requirement.objects.create(
            tenant=tenant,
            artifact=req3_art,
            title="Req Three",
            description="Req three description",
            category="non-functional",
            uid="REQ-003",
        )

        satisfies_link = TraceLink.objects.create(
            tenant=tenant, source=req1_art, target=need1_art, link_type="satisfies"
        )
        verifies_link = TraceLink.objects.create(
            tenant=tenant, source=req2_art, target=req1_art, link_type="verifies"
        )

        yield {
            "tenant": tenant,
            "workspace": workspace,
            "need1": need1,
            "need2": need2,
            "req1": req1,
            "req2": req2,
            "req3": req3,
            "satisfies_link": satisfies_link,
            "verifies_link": verifies_link,
        }
    finally:
        clear_request_tenant()


@pytest.fixture
def target_workspace(source_workspace):
    """A second, empty workspace in the SAME tenant as source_workspace."""
    tenant = source_workspace["tenant"]
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="Reqif Import Target WS", preset={"name": "standard"}
        )
        yield workspace
    finally:
        clear_request_tenant()


# ---------- Round-trip: export -> import into a second workspace ----------


class TestReqifImportRoundTrip:
    def test_import_creates_all_entities_in_target_workspace(
        self, source_workspace, target_workspace
    ):
        tenant = source_workspace["tenant"]
        reqif_text = _export(source_workspace["workspace"].id, tenant.id)

        result = _import(reqif_text, target_workspace.id, tenant.id)

        assert result.success is True
        assert result.dry_run is False
        assert result.needs.created == 2
        assert result.needs.updated == 0
        assert result.needs.skipped == 0
        assert result.requirements.created == 3
        assert result.requirements.updated == 0
        assert result.requirements.skipped == 0
        assert result.relations.created == 2
        assert result.relations.skipped == 0

        assert (
            StakeholderNeed.objects.filter(artifact__workspace=target_workspace).count()
            == 2
        )
        assert (
            Requirement.objects.filter(artifact__workspace=target_workspace).count() == 3
        )
        assert TraceLink.objects.filter(source__workspace=target_workspace).count() == 2

    def test_import_preserves_attribute_values(self, source_workspace, target_workspace):
        tenant = source_workspace["tenant"]
        reqif_text = _export(source_workspace["workspace"].id, tenant.id)

        _import(reqif_text, target_workspace.id, tenant.id)

        req1_copy = Requirement.objects.get(
            artifact__workspace=target_workspace, uid="REQ-001"
        )
        assert req1_copy.title == "Req One"
        assert req1_copy.description == "Req one description"
        assert req1_copy.category == "functional"
        assert req1_copy.verification_method == "Test"

        need1_copy = StakeholderNeed.objects.get(
            artifact__workspace=target_workspace, uid="NEED-001"
        )
        assert need1_copy.title == "Need One"
        assert need1_copy.moscow_priority == "Must"

    def test_import_reproduces_hierarchy(self, source_workspace, target_workspace):
        tenant = source_workspace["tenant"]
        reqif_text = _export(source_workspace["workspace"].id, tenant.id)

        _import(reqif_text, target_workspace.id, tenant.id)

        need1_copy = StakeholderNeed.objects.get(
            artifact__workspace=target_workspace, uid="NEED-001"
        )
        req1_copy = Requirement.objects.get(
            artifact__workspace=target_workspace, uid="REQ-001"
        )
        req2_copy = Requirement.objects.get(
            artifact__workspace=target_workspace, uid="REQ-002"
        )
        req3_copy = Requirement.objects.get(
            artifact__workspace=target_workspace, uid="REQ-003"
        )

        assert req1_copy.artifact.parent_id == need1_copy.artifact_id
        assert req2_copy.artifact.parent_id == req1_copy.artifact_id
        assert req3_copy.artifact.parent_id is None

    def test_import_reproduces_tracelinks(self, source_workspace, target_workspace):
        tenant = source_workspace["tenant"]
        reqif_text = _export(source_workspace["workspace"].id, tenant.id)

        _import(reqif_text, target_workspace.id, tenant.id)

        need1_copy = StakeholderNeed.objects.get(
            artifact__workspace=target_workspace, uid="NEED-001"
        )
        req1_copy = Requirement.objects.get(
            artifact__workspace=target_workspace, uid="REQ-001"
        )
        req2_copy = Requirement.objects.get(
            artifact__workspace=target_workspace, uid="REQ-002"
        )

        assert TraceLink.objects.filter(
            source=req1_copy.artifact, target=need1_copy.artifact, link_type="satisfies"
        ).exists()
        assert TraceLink.objects.filter(
            source=req2_copy.artifact, target=req1_copy.artifact, link_type="verifies"
        ).exists()

    def test_reimport_same_document_is_idempotent(self, source_workspace, target_workspace):
        """REQ-147: re-importing the same ReqIF file updates in place, no duplicates."""
        tenant = source_workspace["tenant"]
        reqif_text = _export(source_workspace["workspace"].id, tenant.id)

        _import(reqif_text, target_workspace.id, tenant.id)
        result2 = _import(reqif_text, target_workspace.id, tenant.id)

        assert result2.needs.created == 0
        assert result2.needs.updated == 2
        assert result2.requirements.created == 0
        assert result2.requirements.updated == 3
        # Relations upsert via get_or_create — re-import must not duplicate.
        assert result2.relations.created == 0
        assert result2.relations.updated == 2

        assert (
            StakeholderNeed.objects.filter(artifact__workspace=target_workspace).count()
            == 2
        )
        assert (
            Requirement.objects.filter(artifact__workspace=target_workspace).count() == 3
        )
        assert TraceLink.objects.filter(source__workspace=target_workspace).count() == 2

    def test_reimport_into_same_workspace_updates_not_duplicates(self, source_workspace):
        """Re-exporting + re-importing into the ORIGINAL workspace must update,
        not create duplicates (identifiers match existing Artifacts)."""
        tenant = source_workspace["tenant"]
        workspace = source_workspace["workspace"]
        reqif_text = _export(workspace.id, tenant.id)

        result = _import(reqif_text, workspace.id, tenant.id)

        assert result.needs.created == 0
        assert result.needs.updated == 2
        assert result.requirements.created == 0
        assert result.requirements.updated == 3
        assert (
            StakeholderNeed.objects.filter(artifact__workspace=workspace).count() == 2
        )
        assert Requirement.objects.filter(artifact__workspace=workspace).count() == 3


# ---------- Dry-run ----------


class TestReqifImportDryRun:
    def test_dry_run_report_matches_real_run_but_db_unchanged(
        self, source_workspace, target_workspace
    ):
        tenant = source_workspace["tenant"]
        reqif_text = _export(source_workspace["workspace"].id, tenant.id)

        dry_result = _import(reqif_text, target_workspace.id, tenant.id, dry_run=True)

        assert dry_result.dry_run is True
        assert dry_result.needs.created == 2
        assert dry_result.requirements.created == 3
        assert dry_result.relations.created == 2

        assert (
            StakeholderNeed.objects.filter(artifact__workspace=target_workspace).count()
            == 0
        )
        assert (
            Requirement.objects.filter(artifact__workspace=target_workspace).count() == 0
        )
        assert TraceLink.objects.filter(source__workspace=target_workspace).count() == 0

        # A real run afterwards produces the identical report.
        real_result = _import(reqif_text, target_workspace.id, tenant.id, dry_run=False)
        assert real_result.needs.created == dry_result.needs.created
        assert real_result.requirements.created == dry_result.requirements.created
        assert real_result.relations.created == dry_result.relations.created


# ---------- Error / edge cases ----------


class TestReqifImportErrorCases:
    def test_broken_xml_raises_validation_error(self, target_workspace, source_workspace):
        tenant = source_workspace["tenant"]

        with pytest.raises(ValidationError):
            _import("<not-valid-reqif>><<<", target_workspace.id, tenant.id)

        assert (
            StakeholderNeed.objects.filter(artifact__workspace=target_workspace).count()
            == 0
        )

    def test_empty_document_raises_validation_error(self, target_workspace, source_workspace):
        tenant = source_workspace["tenant"]
        with pytest.raises(ValidationError):
            _import("   ", target_workspace.id, tenant.id)

    def test_unknown_spec_object_type_is_skipped_and_reported(
        self, source_workspace, target_workspace
    ):
        tenant = source_workspace["tenant"]
        reqif_text = _export(source_workspace["workspace"].id, tenant.id)
        # Corrupt one SPEC-OBJECT-TYPE reference to something out of REQ-147 scope.
        mutated = reqif_text.replace(
            'SPEC-OBJECT-TYPE-REF>ST-StakeholderNeed<', 'SPEC-OBJECT-TYPE-REF>ST-Unknown<', 1
        )
        assert mutated != reqif_text  # sanity: replacement actually happened

        result = _import(mutated, target_workspace.id, tenant.id)

        # One need's SPEC-OBJECT-TYPE-REF now points at an undeclared type;
        # it must be skipped, reported as a warning, not create a row.
        assert any("unknown" in w.lower() for w in result.warnings)
        assert (
            StakeholderNeed.objects.filter(artifact__workspace=target_workspace).count()
            == 1
        )

    def test_relation_with_missing_endpoint_is_skipped_and_reported(
        self, source_workspace, target_workspace
    ):
        tenant = source_workspace["tenant"]
        reqif_text = _export(source_workspace["workspace"].id, tenant.id)
        # Remove need1's SPEC-OBJECT entirely so the "satisfies" relation that
        # targets it becomes unresolvable.
        import re

        need1_so_id = f"_{source_workspace['need1'].artifact_id}"

        mutated = re.sub(
            rf'<SPEC-OBJECT IDENTIFIER="{re.escape(need1_so_id)}".*?</SPEC-OBJECT>',
            "",
            reqif_text,
            flags=re.DOTALL,
        )
        assert mutated != reqif_text

        result = _import(mutated, target_workspace.id, tenant.id)

        assert result.relations.skipped >= 1
        assert any(
            "not resolvable" in e["message"] or "endpoint" in e["message"]
            for e in result.relations.errors
        )
        # The other relation (verifies, between req1/req2) still imports fine.
        assert result.relations.created == 1


# ---------- Status mapping (REQ-143) ----------


class TestReqifImportStatusMapping:
    def test_status_mapped_onto_workflow_state_when_definition_exists(
        self, source_workspace, target_workspace
    ):
        tenant = source_workspace["tenant"]
        set_request_tenant(tenant.id)
        try:
            WorkflowEngineDefinition.objects.create(
                tenant=tenant,
                workspace_id=target_workspace.id,
                item_type="Requirement",
                preset=WorkflowEngineDefinition.PRESET_STANDARD,
                workflow_json={
                    "states": ["draft", "in_review", "approved", "deprecated"],
                    "transitions": [],
                },
            )
            # Task 12: the `status` column is dropped, so req2's "in_review"
            # source status (this test's whole premise -- the export must
            # carry a non-default value for the mapping to be meaningful)
            # can only be represented by a real WorkflowItemState now.
            source_definition = WorkflowEngineDefinition.objects.create(
                tenant=tenant,
                workspace_id=source_workspace["workspace"].id,
                item_type="Requirement",
                preset=WorkflowEngineDefinition.PRESET_STANDARD,
                workflow_json={
                    "states": ["draft", "in_review", "approved", "deprecated"],
                    "transitions": [],
                },
            )
            WorkflowItemState.objects.create(
                tenant=tenant,
                item_id=source_workspace["req2"].id,
                item_type="Requirement",
                workspace_id=source_workspace["workspace"].id,
                definition=source_definition,
                current_state="in_review",
            )
        finally:
            clear_request_tenant()

        reqif_text = _export(source_workspace["workspace"].id, tenant.id)
        _import(reqif_text, target_workspace.id, tenant.id)

        req2_copy = Requirement.objects.get(
            artifact__workspace=target_workspace, uid="REQ-002"
        )
        # req2 was exported with status "in_review", a known state of the
        # target definition -> kept as-is, and a WorkflowItemState mirrors it.
        # Task 12: the `status` column is dropped, so WorkflowItemState is
        # the only place left to check.
        state = WorkflowItemState.objects.get(
            item_id=req2_copy.id, item_type="Requirement"
        )
        assert state.current_state == "in_review"
        assert state.workspace_id == target_workspace.id

    def test_unknown_status_normalises_to_draft_without_definition(
        self, source_workspace, target_workspace
    ):
        """No WorkflowEngineDefinition for StakeholderNeed in target_workspace ->
        no WorkflowItemState row is created (the FK to a definition is
        PROTECT). Task 12: the `status` column that used to at least keep
        the normalised ("unknown" -> "draft") value is dropped, so this case
        now has no record of the imported status anywhere at all --
        documented, reviewed data-loss tradeoff, see the Task 12 report
        Finding 2.

        Mutates need1's ATTR-STATUS value to an unrecognised free-text status
        before importing, exercising the "unknown -> draft" branch of
        _map_status (which still runs -- it just has nowhere left to persist
        its result when there is no definition).
        """
        import re

        tenant = source_workspace["tenant"]
        reqif_text = _export(source_workspace["workspace"].id, tenant.id)

        need1_so_id = f"_{source_workspace['need1'].artifact_id}"
        match = re.search(
            rf'<SPEC-OBJECT IDENTIFIER="{re.escape(need1_so_id)}".*?</SPEC-OBJECT>',
            reqif_text,
            flags=re.DOTALL,
        )
        assert match is not None
        block = match.group(0)
        mutated_block = block.replace(
            'THE-VALUE="draft"', 'THE-VALUE="frobnicated-status"', 1
        )
        assert mutated_block != block  # sanity: mutation actually applied
        mutated = reqif_text.replace(block, mutated_block, 1)

        _import(mutated, target_workspace.id, tenant.id)

        need1_copy = StakeholderNeed.objects.get(
            artifact__workspace=target_workspace, uid="NEED-001"
        )
        assert not WorkflowItemState.objects.filter(
            item_id=need1_copy.id, item_type="StakeholderNeed"
        ).exists()

    def test_status_outside_definition_states_falls_back_to_first_state(
        self, source_workspace, target_workspace
    ):
        tenant = source_workspace["tenant"]
        # req2 is exported with status "in_review"; give the target a
        # definition whose states do NOT include "in_review" at all.
        set_request_tenant(tenant.id)
        try:
            WorkflowEngineDefinition.objects.create(
                tenant=tenant,
                workspace_id=target_workspace.id,
                item_type="Requirement",
                preset=WorkflowEngineDefinition.PRESET_STANDARD,
                workflow_json={
                    "states": ["backlog", "active", "done"],
                    "transitions": [],
                },
            )
        finally:
            clear_request_tenant()

        reqif_text = _export(source_workspace["workspace"].id, tenant.id)
        _import(reqif_text, target_workspace.id, tenant.id)

        req2_copy = Requirement.objects.get(
            artifact__workspace=target_workspace, uid="REQ-002"
        )
        state = WorkflowItemState.objects.get(
            item_id=req2_copy.id, item_type="Requirement"
        )
        assert state.current_state == "backlog"


# ---------- Upsert identifier-collision handling ----------


class TestReqifImportUpsertCollisions:
    def test_identifier_matching_other_workspace_creates_new_with_fresh_id(
        self, source_workspace, target_workspace
    ):
        """A SPEC-OBJECT identifier that matches an Artifact in a DIFFERENT
        workspace must never be touched; import creates a new artifact with a
        fresh id instead, and reports the collision as a warning."""
        tenant = source_workspace["tenant"]
        req1 = source_workspace["req1"]
        original_parent_id = req1.artifact.parent_id

        # Hand-craft a minimal ReqIF doc whose SPEC-OBJECT identifier is
        # exactly req1's artifact id (which lives in source_workspace), but
        # import it into target_workspace.
        reqif_text = _export(source_workspace["workspace"].id, tenant.id)

        result = _import(reqif_text, target_workspace.id, tenant.id)

        assert any("outside this workspace" in w for w in result.warnings)
        # req1's own row in source_workspace is untouched.
        req1.refresh_from_db()
        assert req1.artifact.parent_id == original_parent_id
        assert (
            Requirement.objects.filter(artifact__workspace=source_workspace["workspace"]).count()
            == 3
        )
        # A new copy was created in target_workspace with a different id.
        req1_copy = Requirement.objects.get(
            artifact__workspace=target_workspace, uid="REQ-001"
        )
        assert req1_copy.artifact_id != req1.artifact_id


# ---------- Untrusted custom_fields in an imported file (#269 follow-up) ----


class TestReqifImportCustomFieldsGuard:
    """A ReqIF file is untrusted input; its custom fields go through the same
    guard as a request body.

    This import assigns ``artifact.custom_fields`` directly and calls
    ``save(update_fields=...)``, which never runs the model validators — so
    without the explicit ``validate_custom_fields`` call, an attacker-authored
    file could seed markup / ``javascript:`` payloads straight into the map,
    the exact surface that #290 made live for REST.
    """

    def test_spec_object_with_markup_in_custom_fields_is_skipped(
        self, source_workspace, target_workspace
    ):
        tenant = source_workspace["tenant"]
        # Written straight onto the model: validators do not run on ``save``,
        # which is precisely how a hostile file's payload would arrive.
        artifact = source_workspace["req1"].artifact
        artifact.custom_fields = {"owner": "<img src=x onerror=alert(1)>"}
        artifact.save(update_fields=["custom_fields"])

        reqif_text = _export(source_workspace["workspace"].id, tenant.id)
        result = _import(reqif_text, target_workspace.id, tenant.id)

        assert result.requirements.skipped == 1
        assert any(
            "custom_fields" in e["message"] for e in result.requirements.errors
        ), result.requirements.errors
        # The rest of the file still imports — a soft error, not a hard abort.
        assert result.needs.created == 2
        assert Requirement.objects.filter(
            artifact__workspace=target_workspace, uid="REQ-001"
        ).count() == 0

    def test_ordinary_custom_fields_still_import(
        self, source_workspace, target_workspace
    ):
        tenant = source_workspace["tenant"]
        artifact = source_workspace["req1"].artifact
        artifact.custom_fields = {"owner": "alice", "sprint": 7}
        artifact.save(update_fields=["custom_fields"])

        reqif_text = _export(source_workspace["workspace"].id, tenant.id)
        result = _import(reqif_text, target_workspace.id, tenant.id)

        assert result.requirements.skipped == 0
        imported = Requirement.objects.get(
            artifact__workspace=target_workspace, uid="REQ-001"
        )
        assert imported.artifact.custom_fields == {"owner": "alice", "sprint": 7}
