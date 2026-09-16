"""#816: migration 0093 strips the redundant TestCase artifact_type sub-type tag.

``TestCase.test_type`` (first-class column) was introduced in 0041 as the
single source of truth for a test case's type, but two write paths kept tagging
the backing Artifact with a ``"TestCase:<Type>"`` prefix as well. 0093 removes
that second representation.

The migration's ``RunPython`` functions are exercised directly against the
*historical* model registry they really run under (same pattern as
``test_artifact_backfill``), not the live one: the historical models carry
plain, unscoped managers while the live ``.objects`` is a ``TenantManager``
that demands an ambient ``TenantContext`` and would silently tenant-filter a
cross-tenant rewrite.
"""
import uuid
from importlib import import_module

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

BASE_TYPE = "TestCase"


def _historical_apps():
    """The model registry 0093's RunPython functions really receive."""
    return MigrationExecutor(connection).loader.project_state().apps


def _migration_module():
    """Import 0093 by string — its module name starts with a digit."""
    return import_module(
        "persistence.migrations.0093_normalize_testcase_artifact_type"
    )


@pytest.fixture
def legacy_test_cases(db):
    """Three rows: two pre-0093 tagged ones and one already-plain one."""
    from persistence.models import Artifact, Tenant, TestCase, Workspace
    from persistence.tenancy import TenantContext

    tenant = Tenant.objects.create(
        name="t-tc-type", slug=f"t-tc-type-{uuid.uuid4().hex[:8]}"
    )
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(tenant=tenant, name="tc-type-ws")

        def _case(title, artifact_type, test_type=None):
            artifact = Artifact.objects.create(
                tenant=tenant, workspace=workspace, artifact_type=artifact_type
            )
            return TestCase.objects.create(
                tenant=tenant,
                artifact=artifact,
                title=title,
                test_type=test_type,
            )

        yield {
            # Pre-0093 shape, column still empty: the suffix is the only source.
            "unit": _case("legacy-unit", "TestCase:Unit"),
            # Pre-0093 shape, column already backfilled by 0041.
            "system": _case("legacy-system", "TestCase:System", "system"),
            # Written by the #816 code path: no tag at all.
            "plain": _case("plain-integration", BASE_TYPE, "integration"),
        }
    finally:
        TenantContext.clear_tenant()


def _stored(tenant_id, test_case):
    """Re-read (title, test_type, artifact_type) through the live models."""
    from persistence.models import TestCase
    from persistence.tenancy import TenantContext

    TenantContext.set_tenant(tenant_id)
    try:
        row = (
            TestCase.objects.filter(id=test_case.id)
            .select_related("artifact")
            .first()
        )
        return row.title, row.test_type, row.artifact.artifact_type
    finally:
        TenantContext.clear_tenant()


def test_normalize_strips_the_tag_and_backfills_a_missing_column(legacy_test_cases):
    """The suffix is folded into the column, then removed from artifact_type."""
    migration = _migration_module()
    cases = legacy_test_cases
    tenant_id = cases["unit"].tenant_id

    migration.normalize_artifact_types(_historical_apps(), None)

    assert _stored(tenant_id, cases["unit"]) == ("legacy-unit", "unit", BASE_TYPE)
    assert _stored(tenant_id, cases["system"]) == (
        "legacy-system",
        "system",
        BASE_TYPE,
    )
    # Already-plain rows (and their column value) are untouched.
    assert _stored(tenant_id, cases["plain"]) == (
        "plain-integration",
        "integration",
        BASE_TYPE,
    )


def test_normalize_never_overwrites_an_existing_column_value(legacy_test_cases):
    """A row whose column disagrees with the legacy tag keeps the column."""
    migration = _migration_module()
    cases = legacy_test_cases
    tenant_id = cases["system"].tenant_id

    migration.normalize_artifact_types(_historical_apps(), None)

    _, test_type, artifact_type = _stored(tenant_id, cases["system"])
    assert test_type == "system", (
        "the backfill must only fill NULL columns, never overwrite 0041's value"
    )
    assert artifact_type == BASE_TYPE


def test_normalize_is_idempotent(legacy_test_cases):
    """Re-running the migration is a no-op (no rows keep a legacy tag)."""
    migration = _migration_module()
    cases = legacy_test_cases
    tenant_id = cases["unit"].tenant_id

    migration.normalize_artifact_types(_historical_apps(), None)
    before = _stored(tenant_id, cases["unit"])
    migration.normalize_artifact_types(_historical_apps(), None)

    assert _stored(tenant_id, cases["unit"]) == before


def test_reverse_re_derives_the_legacy_tag(legacy_test_cases):
    """The reverse restores the pre-0093 representation from the column."""
    migration = _migration_module()
    cases = legacy_test_cases
    tenant_id = cases["unit"].tenant_id

    migration.normalize_artifact_types(_historical_apps(), None)
    migration.restore_artifact_type_tag(_historical_apps(), None)

    assert _stored(tenant_id, cases["unit"]) == ("legacy-unit", "unit", "TestCase:Unit")
    assert _stored(tenant_id, cases["system"]) == (
        "legacy-system",
        "system",
        "TestCase:System",
    )
