"""
Tests for COMP-AS-008 ReqifExportService (REQ-146).

leaf_id : COMP-AS-008
req_id  : REQ-146

Builds a real workspace with StakeholderNeeds, Requirements (parent
hierarchy), and TraceLinks via direct ORM creation, exports ReqIF 1.2, and
round-trips the output through the `reqif` library's OWN parser to assert
structural correctness (object counts, relation-per-tracelink, attribute
values, hierarchy nesting, identifier stability) — not just "produces some
XML".

DB-marker convention: module-level ``pytestmark = pytest.mark.django_db``
(mirrors application/tests/test_export_service.py, test_service_boundaries_
req066.py). Tenant context is activated via persistence.middleware.
set_request_tenant/clear_request_tenant (both the app-layer thread-local AND
the Postgres RLS session variable), matching test_service_boundaries_req066.
py's TestCustomFieldService._env() pattern.
"""
from __future__ import annotations

import re
import uuid
from unittest.mock import MagicMock

import pytest
from reqif.parser import ReqIFParser

from application.base import NotFoundError
from application.reqif_export_service import ReqifExportService
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import (
    Artifact,
    Requirement,
    StakeholderNeed,
    Tenant,
    TraceLink,
    Workspace,
)

pytestmark = pytest.mark.django_db


# ---------- Helpers ----------


def _make_ctx(tenant_id):
    ctx = MagicMock()
    ctx.tenant_id = tenant_id
    ctx.user_id = uuid.uuid4()
    ctx.active_roles = ("editor",)
    return ctx


def _export(workspace_id, tenant_id):
    svc = ReqifExportService()
    return svc.export_reqif(workspace_id=workspace_id, ctx=_make_ctx(tenant_id))


def _so_id(artifact_id) -> str:
    return f"_{artifact_id}"


# ---------- Fixture: 2 needs, 3 requirements (parent hierarchy), 2 tracelinks ----------


@pytest.fixture
def reqif_workspace():
    """Workspace with a 2-level hierarchy and a satisfies + a verifies TraceLink.

    Tree:  need1 -> req1 -> req2   (3 levels deep)
           need2                    (top-level)
           req3                     (top-level)

    TraceLinks (both endpoints exported, both must round-trip as SPEC-RELATIONs):
           req1 --satisfies--> need1
           req2 --verifies-->  req1
    """
    tenant = Tenant.objects.create(
        name="Reqif-Test-T", slug="reqif-test-t", is_active=True
    )
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="Reqif WS", preset={"name": "standard"}
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
            status="draft",
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
            status="draft",
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
            status="draft",
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
            status="in-review",
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
            status="draft",
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


# ---------- Tests ----------


class TestReqifExportMapping:
    def test_media_type_and_filename(self, reqif_workspace):
        result = _export(reqif_workspace["workspace"].id, reqif_workspace["tenant"].id)

        assert result.media_type == "application/xml"
        assert result.filename.endswith(".reqif")

    def test_spec_object_counts(self, reqif_workspace):
        result = _export(reqif_workspace["workspace"].id, reqif_workspace["tenant"].id)

        bundle = ReqIFParser.parse_from_string(result.content)
        content = bundle.core_content.req_if_content

        assert len(content.spec_objects) == 5  # 2 needs + 3 requirements
        assert result.record_count == 5

    def test_one_relation_per_tracelink(self, reqif_workspace):
        result = _export(reqif_workspace["workspace"].id, reqif_workspace["tenant"].id)

        bundle = ReqIFParser.parse_from_string(result.content)
        content = bundle.core_content.req_if_content

        assert len(content.spec_relations) == 2
        relation_type_refs = {r.relation_type_ref for r in content.spec_relations}
        assert relation_type_refs == {"SRT-satisfies", "SRT-verifies"}

        req1 = reqif_workspace["req1"]
        need1 = reqif_workspace["need1"]
        req2 = reqif_workspace["req2"]
        by_type = {r.relation_type_ref: r for r in content.spec_relations}
        assert by_type["SRT-satisfies"].source == _so_id(req1.artifact_id)
        assert by_type["SRT-satisfies"].target == _so_id(need1.artifact_id)
        assert by_type["SRT-verifies"].source == _so_id(req2.artifact_id)
        assert by_type["SRT-verifies"].target == _so_id(req1.artifact_id)

    def test_attribute_values(self, reqif_workspace):
        result = _export(reqif_workspace["workspace"].id, reqif_workspace["tenant"].id)

        bundle = ReqIFParser.parse_from_string(result.content)
        content = bundle.core_content.req_if_content
        spec_objects_by_id = {so.identifier: so for so in content.spec_objects}

        req1 = reqif_workspace["req1"]
        so = spec_objects_by_id[_so_id(req1.artifact_id)]
        assert so.attribute_map["ATTR-TITLE"].value == "Req One"
        assert so.attribute_map["ATTR-DESCRIPTION"].value == "Req one description"
        assert so.attribute_map["ATTR-STATUS"].value == "draft"
        assert so.attribute_map["ATTR-UID"].value == "REQ-001"
        assert so.attribute_map["ATTR-VERIFICATION-METHOD"].value == "Test"
        assert "ATTR-MOSCOW-PRIORITY" not in so.attribute_map

        need1 = reqif_workspace["need1"]
        need_so = spec_objects_by_id[_so_id(need1.artifact_id)]
        assert need_so.attribute_map["ATTR-TITLE"].value == "Need One"
        assert need_so.attribute_map["ATTR-MOSCOW-PRIORITY"].value == "Must"
        assert "ATTR-VERIFICATION-METHOD" not in need_so.attribute_map

    def test_spec_object_types_are_distinct_per_artifact_type(self, reqif_workspace):
        result = _export(reqif_workspace["workspace"].id, reqif_workspace["tenant"].id)

        bundle = ReqIFParser.parse_from_string(result.content)
        content = bundle.core_content.req_if_content
        spec_objects_by_id = {so.identifier: so for so in content.spec_objects}

        need1 = reqif_workspace["need1"]
        req1 = reqif_workspace["req1"]
        assert (
            spec_objects_by_id[_so_id(need1.artifact_id)].spec_object_type
            == "ST-StakeholderNeed"
        )
        assert (
            spec_objects_by_id[_so_id(req1.artifact_id)].spec_object_type
            == "ST-Requirement"
        )

    def test_hierarchy_nesting(self, reqif_workspace):
        result = _export(reqif_workspace["workspace"].id, reqif_workspace["tenant"].id)

        bundle = ReqIFParser.parse_from_string(result.content)
        specification = bundle.core_content.req_if_content.specifications[0]
        levels = {
            h.spec_object: h.level
            for h in bundle.iterate_specification_hierarchy(specification)
        }

        need1 = reqif_workspace["need1"]
        need2 = reqif_workspace["need2"]
        req1 = reqif_workspace["req1"]
        req2 = reqif_workspace["req2"]
        req3 = reqif_workspace["req3"]

        assert levels[_so_id(need1.artifact_id)] == 1
        assert levels[_so_id(req1.artifact_id)] == 2  # child of need1
        assert levels[_so_id(req2.artifact_id)] == 3  # grandchild of need1
        assert levels[_so_id(need2.artifact_id)] == 1  # top-level
        assert levels[_so_id(req3.artifact_id)] == 1  # top-level

    def test_identifier_stability_across_exports(self, reqif_workspace):
        """REQ-146: a re-export MUST produce identical identifiers."""
        result1 = _export(reqif_workspace["workspace"].id, reqif_workspace["tenant"].id)
        result2 = _export(reqif_workspace["workspace"].id, reqif_workspace["tenant"].id)

        ids1 = sorted(re.findall(r'IDENTIFIER="([^"]+)"', result1.content))
        ids2 = sorted(re.findall(r'IDENTIFIER="([^"]+)"', result2.content))

        assert ids1 == ids2
        assert len(ids1) > 0

        # Every SPEC-OBJECT identifier is exactly "_<Artifact.id>".
        for artifact in (
            reqif_workspace["need1"],
            reqif_workspace["need2"],
            reqif_workspace["req1"],
            reqif_workspace["req2"],
            reqif_workspace["req3"],
        ):
            assert _so_id(artifact.artifact_id) in ids1

    def test_tracelink_touching_non_exported_type_is_skipped(self, reqif_workspace):
        """A TraceLink to a non-Need/Requirement artifact is out of REQ-146 scope."""
        from persistence.models import ArchitectureElement

        tenant = reqif_workspace["tenant"]
        workspace = reqif_workspace["workspace"]
        req3 = reqif_workspace["req3"]

        ae_art = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="ArchitectureElement"
        )
        ArchitectureElement.objects.create(
            tenant=tenant, artifact=ae_art, title="Some Component"
        )
        TraceLink.objects.create(
            tenant=tenant,
            source=req3.artifact,
            target=ae_art,
            link_type="allocated-to",
        )

        result = _export(workspace.id, tenant.id)
        bundle = ReqIFParser.parse_from_string(result.content)
        content = bundle.core_content.req_if_content

        # Still only the original 2 relations — the AE-touching link is skipped.
        assert len(content.spec_relations) == 2
        assert len(content.spec_objects) == 5


class TestReqifExportEdgeCases:
    def test_empty_workspace_exports_valid_document(self):
        tenant = Tenant.objects.create(
            name="Reqif-Empty-T", slug="reqif-empty-t", is_active=True
        )
        set_request_tenant(tenant.id)
        try:
            workspace = Workspace.objects.create(
                tenant=tenant, name="Empty WS", preset={"name": "standard"}
            )

            result = _export(workspace.id, tenant.id)

            bundle = ReqIFParser.parse_from_string(result.content)
            content = bundle.core_content.req_if_content
            assert content.spec_objects == []
            assert content.spec_relations == []
            assert len(content.specifications) == 1
            assert result.record_count == 0
        finally:
            clear_request_tenant()

    def test_unknown_workspace_raises_not_found(self):
        tenant = Tenant.objects.create(
            name="Reqif-NF-T", slug="reqif-nf-t", is_active=True
        )
        set_request_tenant(tenant.id)
        try:
            with pytest.raises(NotFoundError):
                _export(uuid.uuid4(), tenant.id)
        finally:
            clear_request_tenant()

    def test_custom_fields_exported_as_json_attribute(self, reqif_workspace):
        req1_art = reqif_workspace["req1"].artifact
        req1_art.custom_fields = {"risk_level": "high", "owner": "team-alpha"}
        req1_art.save(update_fields=["custom_fields"])

        result = _export(reqif_workspace["workspace"].id, reqif_workspace["tenant"].id)
        bundle = ReqIFParser.parse_from_string(result.content)
        content = bundle.core_content.req_if_content
        so = next(
            so
            for so in content.spec_objects
            if so.identifier == _so_id(reqif_workspace["req1"].artifact_id)
        )

        import json

        assert json.loads(so.attribute_map["ATTR-CUSTOM-FIELDS"].value) == {
            "risk_level": "high",
            "owner": "team-alpha",
        }
