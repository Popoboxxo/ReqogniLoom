"""
D14d: ReqIF 1.2 export/import of TestCase and Icd as standard SPEC-OBJECTs.

The two additional types are mapped with plain ``ATTRIBUTE-DEFINITION-STRING``
declarations (no THE-OTHER-CONTENT / TOOL-EXTENSIONS). This module pins both
halves of that contract: the generated document validates against the ReqIF
1.2 XSD shipped with the ``reqif`` package, and a real export -> import
round-trip recreates TestCase/Icd fields plus a ``verifies`` TraceLink.

DB-marker convention mirrors the sibling ReqIF tests: module-level
``pytestmark = pytest.mark.django_db`` and tenant context via
``persistence.middleware.set_request_tenant``.
"""
from __future__ import annotations

import os
import uuid
from unittest.mock import MagicMock

import pytest
from reqif.parser import ReqIFParser

from application.reqif_export_service import ReqifExportService
from application.reqif_import_service import ReqifImportService
from icd.models import Icd
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import (
    Artifact,
    Requirement,
    Tenant,
    TestCase,
    TraceLink,
    Workspace,
)

pytestmark = pytest.mark.django_db


def _make_ctx(tenant_id):
    ctx = MagicMock()
    ctx.tenant_id = tenant_id
    ctx.user_id = uuid.uuid4()
    ctx.active_roles = ("editor",)
    return ctx


@pytest.fixture
def tc_icd_workspace():
    """One tenant, two workspaces; source has a Requirement, TestCase and Icd.

    The TestCase verifies the Requirement (a TraceLink between two now
    exported artifact types, which must survive the ReqIF round-trip).
    """
    tenant = Tenant.objects.create(
        name="ReqIF-TC-ICD-T", slug="reqif-tc-icd-t", is_active=True
    )
    set_request_tenant(tenant.id)
    try:
        source = Workspace.objects.create(
            tenant=tenant, name="ReqIF TC/ICD Source", preset={"name": "standard"}
        )
        target = Workspace.objects.create(
            tenant=tenant, name="ReqIF TC/ICD Target", preset={"name": "standard"}
        )

        req_art = Artifact.objects.create(
            tenant=tenant, workspace=source, artifact_type="Requirement"
        )
        req = Requirement.objects.create(
            tenant=tenant,
            artifact=req_art,
            workspace=source,
            title="Authentication requirement",
            description="The system shall authenticate users.",
            category="functional",
            verification_method="Test",
            uid="REQ-AUTH-001",
        )

        tc_art = Artifact.objects.create(
            tenant=tenant, workspace=source, artifact_type="TestCase"
        )
        tc = TestCase.objects.create(
            tenant=tenant,
            artifact=tc_art,
            workspace=source,
            title="TC login nominal",
            description="A user logs in with valid credentials.",
            test_type="system",
            scenario_kind="nominal",
            steps=[
                {"step_type": "given", "text": "a registered user"},
                {"step_type": "when", "text": "the user logs in"},
                {"step_type": "then", "text": "access is granted"},
            ],
            origin="manual",
            reviewed=True,
            suspect=False,
            uid="TC-AUTH-001",
        )

        icd_art = Artifact.objects.create(
            tenant=tenant, workspace=source, artifact_type="Icd"
        )
        icd = Icd.objects.create(
            tenant=tenant,
            workspace=source,
            artifact=icd_art,
            name="Auth gateway interface",
            source_element_id=uuid.uuid4(),
            target_element_id=uuid.uuid4(),
            direction="unidirectional",
            interface_type="provides",
            semantic_description="Exposes token validation to consumers.",
            preconditions=["token issued"],
            postconditions=["claims returned"],
            invariants=["signature valid"],
            current_revision=3,
        )

        TraceLink.objects.create(
            tenant=tenant,
            source=tc_art,
            target=req_art,
            link_type="verifies",
        )
        yield {
            "tenant": tenant,
            "source": source,
            "target": target,
            "requirement": req,
            "test_case": tc,
            "icd": icd,
        }
    finally:
        clear_request_tenant()


def _export(workspace, tenant_id) -> str:
    return ReqifExportService().export_reqif(
        workspace_id=workspace.id, ctx=_make_ctx(tenant_id)
    ).content


def _import(xml, workspace, tenant_id, dry_run=False):
    return ReqifImportService().import_reqif(
        reqif_text=xml,
        workspace_id=workspace.id,
        ctx=_make_ctx(tenant_id),
        dry_run=dry_run,
    )


def _spec_objects(xml):
    bundle = ReqIFParser.parse_from_string(xml)
    return bundle, {so.identifier: so for so in bundle.core_content.req_if_content.spec_objects}


def test_export_contains_standard_tc_and_icd_spec_objects(tc_icd_workspace):
    tenant, source = tc_icd_workspace["tenant"], tc_icd_workspace["source"]
    tc, icd = tc_icd_workspace["test_case"], tc_icd_workspace["icd"]

    xml = _export(source, tenant.id)
    bundle, objects = _spec_objects(xml)
    types = {
        t.identifier for t in bundle.core_content.req_if_content.spec_types
    }
    assert "ST-TestCase" in types
    assert "ST-Icd" in types

    tc_obj = objects[f"_{tc.artifact_id}"]
    assert tc_obj.spec_object_type == "ST-TestCase"
    tc_attrs = {
        a.definition_ref: a.value for a in tc_obj.attributes
    }
    assert tc_attrs["ATTR-TEST-TYPE"] == "system"
    assert tc_attrs["ATTR-SCENARIO-KIND"] == "nominal"
    assert "logs in" in tc_attrs["ATTR-STEPS-JSON"]
    assert tc_attrs["ATTR-REVIEWED"] == "true"

    icd_obj = objects[f"_icd-{icd.id}"]
    assert icd_obj.spec_object_type == "ST-Icd"
    icd_attrs = {
        a.definition_ref: a.value for a in icd_obj.attributes
    }
    assert icd_attrs["ATTR-ICD-NAME"] == "Auth gateway interface"
    assert icd_attrs["ATTR-ICD-INTERFACE-TYPE"] == "provides"
    assert icd_attrs["ATTR-ICD-CURRENT-REVISION"] == "3"
    assert "token issued" in icd_attrs["ATTR-ICD-PRECONDITIONS"]

    # The verifies link (TestCase -> Requirement) is now in scope.
    relations = bundle.core_content.req_if_content.spec_relations
    assert any(r.source == f"_{tc.artifact_id}" for r in relations)


def test_export_with_tc_and_icd_is_xsd_valid(tc_icd_workspace):
    """D14d: no non-standard constructs — the document validates against XSD."""
    xmlschema = pytest.importorskip("xmlschema")
    import reqif

    tenant, source = tc_icd_workspace["tenant"], tc_icd_workspace["source"]
    xml = _export(source, tenant.id)

    xsd_path = os.path.join(
        os.path.dirname(reqif.__file__), "reqif_schema", "reqif.xsd"
    )
    errors = list(xmlschema.XMLSchema(xsd_path).iter_errors(xml))
    assert errors == [], (
        f"{len(errors)} XSD violation(s): "
        + "; ".join(f"{e.reason} @ {e.path}" for e in errors[:5])
    )


def test_roundtrip_recreates_tc_icd_and_verifies_link(tc_icd_workspace):
    tenant = tc_icd_workspace["tenant"]
    source, target = tc_icd_workspace["source"], tc_icd_workspace["target"]

    xml = _export(source, tenant.id)
    result = _import(xml, target, tenant.id)

    assert result.success, result.to_dict()
    assert result.test_cases.created == 1, result.test_cases.to_dict()
    assert result.icds.created == 1, result.icds.to_dict()
    assert result.relations.created >= 1, result.relations.to_dict()

    imported_tc = TestCase.objects.get(artifact__workspace=target)
    assert imported_tc.title == "TC login nominal"
    assert imported_tc.test_type == "system"
    assert imported_tc.scenario_kind == "nominal"
    assert imported_tc.reviewed is True
    assert len(imported_tc.steps) == 3

    imported_icd = Icd.objects.get(workspace=target)
    assert imported_icd.name == "Auth gateway interface"
    assert imported_icd.interface_type == "provides"
    assert imported_icd.current_revision == 3
    assert imported_icd.preconditions == ["token issued"]

    imported_link = TraceLink.objects.get(
        source__workspace=target, target__workspace=target, link_type="verifies"
    )
    assert imported_link.source.artifact_type == "TestCase"
    assert imported_link.target.artifact_type == "Requirement"


def test_second_import_is_idempotent(tc_icd_workspace):
    tenant = tc_icd_workspace["tenant"]
    target = tc_icd_workspace["target"]
    xml = _export(tc_icd_workspace["source"], tenant.id)

    _import(xml, target, tenant.id)
    second = _import(xml, target, tenant.id)

    assert second.test_cases.skipped == 1, second.test_cases.to_dict()
    assert second.icds.skipped == 1, second.icds.to_dict()
    assert TestCase.objects.filter(artifact__workspace=target).count() == 1
    assert Icd.objects.filter(workspace=target).count() == 1


def test_dry_run_leaves_no_rows(tc_icd_workspace):
    tenant = tc_icd_workspace["tenant"]
    target = tc_icd_workspace["target"]
    xml = _export(tc_icd_workspace["source"], tenant.id)

    result = _import(xml, target, tenant.id, dry_run=True)

    assert result.dry_run is True
    assert result.test_cases.created == 1
    assert result.icds.created == 1
    assert TestCase.objects.filter(artifact__workspace=target).count() == 0
    assert Icd.objects.filter(workspace=target).count() == 0
