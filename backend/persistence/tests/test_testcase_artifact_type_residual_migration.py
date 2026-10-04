"""DATA-08: residual ``"TestCase:<Type>"`` tags normalise guarded + idempotent.

Migration 0093 was already applied when the residual rows appeared, so the
follow-up correction migration 0105 (and the shared helper it delegates to) is
exercised directly against the historical model registry — same pattern as
``test_testcase_artifact_type_migration.py``, because the live ``.objects`` is a
``TenantManager`` that demands an ambient ``TenantContext`` and would silently
tenant-filter a cross-tenant rewrite.
"""
import uuid
from importlib import import_module

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

BASE_TYPE = "TestCase"


def _historical_apps():
    """The model registry 0105's RunPython functions really receive."""
    return MigrationExecutor(connection).loader.project_state().apps


def _migration_module():
    """Import 0105 by string — its module name starts with a digit."""
    return import_module(
        "persistence.migrations.0105_normalize_residual_testcase_artifact_type"
    )


@pytest.fixture
def residual_rows(db):
    """Two residual tagged TestCases, one plain, one unbacked tagged artifact."""
    from persistence.models import Artifact, Tenant, TestCase, Workspace
    from persistence.tenancy import TenantContext

    tenant = Tenant.objects.create(
        name="t-data08", slug=f"t-data08-{uuid.uuid4().hex[:8]}"
    )
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(tenant=tenant, name="data08-ws")

        def _artifact(artifact_type):
            return Artifact.objects.create(
                tenant=tenant, workspace=workspace, artifact_type=artifact_type
            )

        def _case(title, artifact_type, test_type=None):
            artifact = _artifact(artifact_type)
            return TestCase.objects.create(
                tenant=tenant, artifact=artifact, title=title, test_type=test_type
            )

        unit = _case("residual-unit", "TestCase:Unit")
        system = _case("residual-system", "TestCase:System", "system")
        plain = _case("plain", BASE_TYPE, "integration")
        # Tagged but NOT backed by a TestCase row: the guard must leave it alone.
        orphan = _artifact("TestCase:Unit")
        yield {
            "unit": unit,
            "system": system,
            "plain": plain,
            "orphan": orphan,
            "tenant_id": tenant.id,
        }
    finally:
        TenantContext.clear_tenant()


def _stored_artifact(tenant_id, artifact):
    from persistence.models import Artifact
    from persistence.tenancy import TenantContext

    TenantContext.set_tenant(tenant_id)
    try:
        return Artifact.objects.get(id=artifact.id).artifact_type
    finally:
        TenantContext.clear_tenant()


def _stored_case(tenant_id, test_case):
    from persistence.models import TestCase
    from persistence.tenancy import TenantContext

    TenantContext.set_tenant(tenant_id)
    try:
        row = (
            TestCase.objects.filter(id=test_case.id).select_related("artifact").first()
        )
        return row.test_type, row.artifact.artifact_type
    finally:
        TenantContext.clear_tenant()


def test_normalizes_residual_tags_and_backfills_null_column(residual_rows):
    """Both the tag and the still-NULL canonical column are corrected."""
    migration = _migration_module()
    rows = residual_rows

    migration.normalize_residual(_historical_apps(), None)

    assert _stored_case(rows["tenant_id"], rows["unit"]) == ("unit", BASE_TYPE)
    # Column already set by 0041 is preserved, tag still stripped.
    assert _stored_case(rows["tenant_id"], rows["system"]) == ("system", BASE_TYPE)
    # Already-plain rows are untouched.
    assert _stored_case(rows["tenant_id"], rows["plain"]) == ("integration", BASE_TYPE)


def test_guard_leaves_unbacked_tagged_artifact_untouched(residual_rows):
    """A tagged artifact with no TestCase row is not silently relabelled."""
    migration = _migration_module()
    rows = residual_rows

    migration.normalize_residual(_historical_apps(), None)

    assert _stored_artifact(rows["tenant_id"], rows["orphan"]) == "TestCase:Unit"


def test_guard_reports_counts(residual_rows):
    """The helper surfaces tagged/rewritten/unbacked counts for the migration log."""
    from persistence.testcase_type_normalization import (
        normalize_testcase_artifact_types,
    )

    apps = _historical_apps()
    counts = normalize_testcase_artifact_types(
        apps.get_model("persistence", "Artifact"),
        apps.get_model("persistence", "TestCase"),
    )

    assert counts["tagged"] == 3  # residual unit + residual system + orphan
    assert counts["rewritten"] == 2
    assert counts["unbacked"] == 1
    assert counts["column_backfilled"] == 1  # only the unit row was NULL


def test_normalization_is_idempotent(residual_rows):
    """Re-running the correction migration is a no-op."""
    migration = _migration_module()
    rows = residual_rows
    tenant_id = rows["tenant_id"]

    migration.normalize_residual(_historical_apps(), None)
    before = (
        _stored_case(tenant_id, rows["unit"]),
        _stored_case(tenant_id, rows["system"]),
        _stored_artifact(tenant_id, rows["orphan"]),
    )

    migration.normalize_residual(_historical_apps(), None)

    after = (
        _stored_case(tenant_id, rows["unit"]),
        _stored_case(tenant_id, rows["system"]),
        _stored_artifact(tenant_id, rows["orphan"]),
    )
    assert after == before


def test_reverse_re_derives_the_legacy_tag(residual_rows):
    """The reverse restores the Title-case tag from the canonical column."""
    migration = _migration_module()
    rows = residual_rows
    tenant_id = rows["tenant_id"]

    migration.normalize_residual(_historical_apps(), None)
    migration.restore_residual(_historical_apps(), None)

    assert _stored_case(tenant_id, rows["unit"]) == ("unit", "TestCase:Unit")
    assert _stored_case(tenant_id, rows["system"]) == ("system", "TestCase:System")
