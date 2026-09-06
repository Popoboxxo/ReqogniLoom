"""Backfill integrity: one Artifact per legacy row, no orphans, no duplicates.

Datenmodell-Konsolidierung Phase 3, spec section 4.2.

The migration's ``backfill``/``verify`` functions are exercised directly against
the *historical* model registry they actually run under (built via
``MigrationExecutor``), not the live one. That distinction is the whole point of
the migration: the historical registry hands out plain, unscoped managers, while
the live ``.objects`` is a ``TenantManager`` that would demand an ambient
``TenantContext`` and silently tenant-filter the backfill.
"""
import io
from importlib import import_module

import pytest
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

def _historical_apps():
    """The model registry ``0073``'s RunPython functions really receive.

    Datenmodell-Konsolidierung Task 24: pinning this to the ``0073`` node
    itself (as before) freezes a ``GlossaryTerm`` model that still declares
    ``lifecycle_status`` -- a field ``0075_drop_entity_lifecycle_status``
    later removes from the *physical* table. ``0073``'s own logic never
    touches that field (only ``artifact``/``workspace_id``/``tenant_id``), so
    resolving to the graph's current head instead keeps the registry in
    lockstep with whatever schema the shared test DB actually has, with no
    migration reference to bump the next time a later migration drops a
    column an earlier RunPython's model happens to also declare.
    """
    return MigrationExecutor(connection).loader.project_state().apps


def _migration_module():
    """Import 0073 by string — its module name starts with a digit."""
    return import_module("persistence.migrations.0073_backfill_artifact_backing")


@pytest.fixture
def legacy_rows(db):
    """Rows that predate their type's artifact FK, plus one workspace-less row."""
    from diagram.models import Diagram
    from icd.models import Icd
    from persistence.models import ChangeRequest, GlossaryTerm, Tenant
    from persistence.tenancy import TenantContext
    from persistence.tests.factories import make_workspace

    tenant = Tenant.objects.create(name="t-backfill", slug="t-backfill")
    TenantContext.set_tenant(tenant.id)
    workspace = make_workspace(tenant)

    # Created through the plain managers, NOT the services Task 19 wired up, so
    # these rows land with artifact IS NULL exactly like pre-Task-19 rows.
    diagram = Diagram.objects.create(
        tenant=tenant, name="D", diagram_type="block", workspace_id=workspace.id
    )
    orphan_diagram = Diagram.objects.create(
        tenant=tenant, name="D-no-ws", diagram_type="block", workspace_id=None
    )
    icd = Icd.objects.create(
        tenant=tenant,
        workspace_id=workspace.id,
        name="ICD",
        source_element_id=workspace.id,
        target_element_id=workspace.id,
    )
    term = GlossaryTerm.objects.create(
        tenant=tenant, workspace=workspace, term="T", definition="d"
    )
    orphan_term = GlossaryTerm.objects.create(
        tenant=tenant, workspace=None, term="T-no-ws", definition="d"
    )
    change_request = ChangeRequest.objects.create(
        tenant=tenant, workspace_id=workspace.id, title="CR"
    )

    for row in (diagram, orphan_diagram, icd, term, orphan_term, change_request):
        assert row.artifact_id is None, f"{type(row).__name__} was not created unbacked"

    return {
        "tenant": tenant,
        "workspace": workspace,
        "backable": [diagram, icd, term, change_request],
        "orphans": [orphan_diagram, orphan_term],
    }


@pytest.mark.django_db
def test_backfill_backs_every_legacy_row(legacy_rows):
    """The core promise of Milestone M3, per type."""
    _migration_module().backfill(_historical_apps(), connection.schema_editor())

    for row in legacy_rows["backable"]:
        row.refresh_from_db()
        assert row.artifact_id is not None, f"{type(row).__name__} left unbacked"
        assert row.artifact.artifact_type == type(row).__name__
        assert row.artifact.tenant_id == row.tenant_id
        assert row.artifact.workspace_id == legacy_rows["workspace"].id


@pytest.mark.django_db
def test_backfill_is_idempotent(legacy_rows):
    """A re-run after an interrupted deploy must not duplicate anything."""
    from persistence.models import Artifact

    module = _migration_module()
    module.backfill(_historical_apps(), connection.schema_editor())
    after_first = Artifact.unscoped.count()
    ids = {type(r).__name__: r.__class__.objects.get(pk=r.pk).artifact_id
           for r in legacy_rows["backable"]}

    module.backfill(_historical_apps(), connection.schema_editor())

    assert Artifact.unscoped.count() == after_first
    for row in legacy_rows["backable"]:
        row.refresh_from_db()
        assert row.artifact_id == ids[type(row).__name__]


@pytest.mark.django_db
def test_workspace_less_rows_are_skipped_not_guessed(legacy_rows):
    """Artifact.workspace is non-nullable; guessing a workspace would be worse."""
    module = _migration_module()
    module.backfill(_historical_apps(), connection.schema_editor())

    for row in legacy_rows["orphans"]:
        row.refresh_from_db()
        assert row.artifact_id is None

    # verify() must treat them as skipped, not as a failed backfill.
    module.verify(_historical_apps(), connection.schema_editor())


@pytest.mark.django_db
def test_verify_rejects_a_row_the_backfill_missed(legacy_rows):
    """verify() is the migration's own safety net — prove it actually fires."""
    module = _migration_module()
    module.backfill(_historical_apps(), connection.schema_editor())

    from diagram.models import Diagram

    missed = legacy_rows["backable"][0]
    Diagram.unscoped.filter(pk=missed.pk).update(artifact=None)

    with pytest.raises(RuntimeError, match="still unbacked"):
        module.verify(_historical_apps(), connection.schema_editor())


@pytest.mark.django_db
def test_check_command_reports_unbacked_rows(legacy_rows):
    out = io.StringIO()

    with pytest.raises(SystemExit) as excinfo:
        call_command("check_artifact_backing", stdout=out)

    assert excinfo.value.code != 0
    report = out.getvalue()
    assert "FAIL Diagram" in report
    assert "FAIL Icd" in report
    assert "FAIL GlossaryTerm" in report
    assert "FAIL ChangeRequest" in report


@pytest.mark.django_db
def test_check_command_passes_after_the_backfill(legacy_rows):
    """Green path, including the workspace-less rows being reported as skipped."""
    _migration_module().backfill(_historical_apps(), connection.schema_editor())

    out = io.StringIO()
    call_command("check_artifact_backing", stdout=out)

    report = out.getvalue()
    assert "All artifact types are consistently backed." in report
    assert "FAIL" not in report
    # One Diagram and one GlossaryTerm intentionally have no workspace.
    assert "OK   Diagram: 2 rows, 1 skipped (no workspace)" in report
    assert "OK   GlossaryTerm: 2 rows, 1 skipped (no workspace)" in report


@pytest.mark.django_db
def test_check_command_covers_every_workspace_less_type_without_erroring():
    """Regression guard: three BACKED_TYPES have no workspace field at all.

    Filtering them on ``workspace_id`` raises FieldError, which would take the
    whole integrity report down.
    """
    from django.apps import apps

    from persistence.management.commands.check_artifact_backing import BACKED_TYPES

    for app_label, model_name, workspace_attr in BACKED_TYPES:
        model = apps.get_model(app_label, model_name)
        assert hasattr(model, "unscoped"), model_name
        if workspace_attr is not None:
            model.unscoped.filter(**{f"{workspace_attr}__isnull": True}).count()
