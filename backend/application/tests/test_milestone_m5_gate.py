"""Milestone M5 gate — one versioning mechanism, one diff dispatch.

Datenmodell-Konsolidierung Phase 5, spec section 6.4 ("ArtifactDiff bedient
danach nur noch eine Welt statt zwei parallele Formate").

Task 29 unified ``list_versions``/``diff`` onto ``persistence.ArtifactVersion``
for every artifact type, including ICD — whose REST ``versions``/``diff``
actions used to hand-roll their own dispatch against
:func:`icd.services.get_icd_history` rather than going through
``ArtifactDiffService``. The ICD-specific tests below prove that type is
genuinely part of "one world" too: listable and diffable through the exact
same two generic methods as Requirement, with real recorded structured
parameter content surviving the round trip.
"""
from __future__ import annotations

import inspect
import uuid
from unittest.mock import patch

import pytest

from application.artifact_diff_service import ArtifactDiffService

REMOVED_METHODS = [
    "list_versions_for_diagram",
    "diff_for_diagram",
    "list_versions_for_glossary_term",
    "diff_for_glossary_term",
    "_resolve_diagram_snapshot",
]

KEPT_LINEAGE_METHODS = ["list_versions_for_goal", "list_versions_for_main_goal"]


@pytest.mark.parametrize("name", REMOVED_METHODS)
def test_per_type_variant_is_gone(name):
    assert not hasattr(ArtifactDiffService, name)


@pytest.mark.parametrize("name", KEPT_LINEAGE_METHODS)
def test_lineage_variant_is_kept(name):
    assert hasattr(ArtifactDiffService, name)


def test_no_legacy_version_table_is_referenced():
    source = inspect.getsource(ArtifactDiffService)
    for token in ("DiagramVersion", "GlossaryTermVersion", "IcdVersion"):
        assert token not in source


@pytest.mark.django_db
def test_every_listed_version_has_content(diffable_requirement):
    ctx, artifact_id = diffable_requirement

    entries = ArtifactDiffService().list_versions(artifact_id, ctx)

    # Creation baseline (v0, no content) + revision 1 (create) + revision 2
    # (update) — every content write records a revision (Task 27).
    assert len(entries) == 3
    assert entries[0]["content_available"] is False
    assert all(entry["content_available"] for entry in entries[1:])


@pytest.mark.django_db
def test_diff_between_two_stored_revisions(diffable_requirement):
    ctx, artifact_id = diffable_requirement

    result = ArtifactDiffService().diff(artifact_id, 1, 2, ctx)

    changed = {field["name"] for field in result["fields"] if field["status"] == "modified"}
    assert "title" in changed


@pytest.fixture
def diffable_requirement(db):
    from auth_tenancy.context import AuthContext, AuthMethod
    from persistence.models import Tenant, Workspace
    from persistence.tenancy import TenantContext

    from application.requirement_service import RequirementService

    tenant = Tenant.objects.create(name="t-m5", slug=f"t-m5-{uuid.uuid4().hex[:8]}")
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(tenant=tenant, name="ws-m5")
        ctx = AuthContext(
            user_id=uuid.uuid4(),
            tenant_id=tenant.id,
            active_roles=("admin",),
            auth_method=AuthMethod.BEARER_TOKEN,
            workspace_id=workspace.id,
        )
        service = RequirementService()
        req = service.create_requirement(
            workspace_id=workspace.id, title="R1", description="d", ctx=ctx
        )
        service.update_requirement(req.id, ctx, title="R2")
        return ctx, req.artifact_id
    finally:
        TenantContext.clear_tenant()


# ---------------------------------------------------------------------------
# ICD — the type Task 28c-2 deliberately left on its own REST code path,
# unified onto the generic list_versions/diff here (Task 29's own judgment
# call, since the brief did not cover ICD at all).
# ---------------------------------------------------------------------------


@pytest.fixture
def _mock_arch_artifact_resolution():
    """ICD's create/update path resolves source/target element ids against
    real ArchitectureElement artifacts; mocked out here exactly like
    icd/tests/test_icd_version_retired.py does, since this fixture only cares
    about the ICD's own content history, not architecture linking.
    """
    with patch(
        "icd.icd_manager.IcdManager._resolve_arch_artifact_id",
        side_effect=lambda x: x,
    ):
        with patch(
            "icd.traceability_connector.TraceabilityConnector.link_to_architecture"
        ):
            yield


@pytest.fixture
def diffable_icd(db, _mock_arch_artifact_resolution):
    from auth_tenancy.context import AuthContext, AuthMethod
    from persistence.models import Tenant, Workspace
    from persistence.tenancy import TenantContext

    from icd.services import (
        IcdCreateDTO,
        IcdParameterCreateDTO,
        IcdUpdateDTO,
        create_icd,
        create_icd_parameter,
        update_icd,
    )

    tenant = Tenant.objects.create(name="t-m5-icd", slug=f"t-m5-icd-{uuid.uuid4().hex[:8]}")
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(tenant=tenant, name="ws-m5-icd")
        ctx = AuthContext(
            user_id=uuid.uuid4(),
            tenant_id=tenant.id,
            active_roles=("admin",),
            auth_method=AuthMethod.BEARER_TOKEN,
            workspace_id=workspace.id,
        )

        result = create_icd(
            IcdCreateDTO(
                tenant_id=tenant.id,
                workspace_id=workspace.id,
                name="M5 Gate ICD",
                source_element_id=uuid.uuid4(),
                target_element_id=uuid.uuid4(),
                interface_type="provides",
                semantic_description="v1",
            )
        )
        create_icd_parameter(
            IcdParameterCreateDTO(
                icd_id=result.icd.id, name="voltage", unit="V", min_value=1, max_value=5
            ),
            tenant_id=tenant.id,
        )
        update_icd(
            icd_id=result.icd.id,
            payload=IcdUpdateDTO(semantic_description="v2"),
            tenant_id=tenant.id,
        )
        result.icd.refresh_from_db()
        return ctx, result.icd
    finally:
        TenantContext.clear_tenant()


@pytest.mark.django_db
class TestIcdIsPartOfTheOneDiffWorld:
    """M5's own stated goal, proven for the one type most likely to be missed."""

    def test_icd_versions_are_listable_through_the_generic_entry_point(self, diffable_icd):
        ctx, icd = diffable_icd

        entries = ArtifactDiffService().list_versions(icd.artifact_id, ctx)

        # Creation baseline (v0) + revision 1 (create) + revision 2 (update).
        assert [e["version"] for e in entries] == [0, 1, 2]
        assert entries[1]["content_available"] is True
        assert entries[2]["content_available"] is True

    def test_icd_diff_is_computable_through_the_generic_entry_point(self, diffable_icd):
        ctx, icd = diffable_icd

        result = ArtifactDiffService().diff(icd.artifact_id, 1, 2, ctx)

        assert result["entity_type"] == "Icd"
        field_statuses = {f["name"]: f["status"] for f in result["fields"]}
        assert field_statuses["semantic_description"] == "modified"

    def test_icd_diff_carries_real_recorded_parameter_content(self, diffable_icd):
        """The field the hand-rolled REST diff action never compared (#767
        gap closed by Task 29): recorded parameters are visible in a diff
        between the revision before and after they existed.

        Revision 1 is recorded at create() time, before the parameter is
        added; revision 2 is recorded at the subsequent update() and captures
        the parameter by value.
        """
        ctx, icd = diffable_icd

        result = ArtifactDiffService().diff(icd.artifact_id, 1, 2, ctx)

        params_field = next(
            f for f in result["fields"] if f["name"] == "parameters_snapshot"
        )
        assert params_field["status"] == "modified"
        assert params_field["from"] == []
        assert params_field["to"][0]["name"] == "voltage"
        assert params_field["to"][0]["unit"] == "V"

    def test_icd_diff_also_covers_the_name_field(self, diffable_icd):
        """The other field the hand-rolled REST diff action never compared."""
        ctx, icd = diffable_icd

        result = ArtifactDiffService().diff(icd.artifact_id, 0, 1, ctx)

        name_field = next(f for f in result["fields"] if f["name"] == "name")
        assert name_field["status"] == "added"
        assert name_field["to"] == "M5 Gate ICD"
