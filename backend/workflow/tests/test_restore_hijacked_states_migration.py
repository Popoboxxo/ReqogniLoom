"""``workflow/0018`` gives back the states the old ``outdate()`` overwrote.

Datenmodell-Konsolidierung Phase 4, Decision D-3.

Exercised against the *historical* model registry the RunPython functions really
receive (built via ``MigrationExecutor``), not the live one — same reasoning as
``persistence/tests/test_artifact_backfill.py``: the historical registry hands
out plain, unscoped managers, while the live ``.objects`` is a ``TenantManager``
that would demand an ambient ``TenantContext`` and silently tenant-filter the
migration.
"""
from importlib import import_module

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from persistence.tenancy import TenantContext

MIGRATION = ("workflow", "0018_restore_states_hijacked_by_outdate")


def _historical_apps():
    """The model registry ``0018``'s RunPython functions really receive."""
    return MigrationExecutor(connection).loader.project_state(MIGRATION).apps


def _module():
    """Import 0018 by string — its module name starts with a digit."""
    return import_module("workflow.migrations.0018_restore_states_hijacked_by_outdate")


@pytest.fixture
def legacy_outdated(db):
    """A WorkflowItemState stranded on "outdated", with its pre-outdate history.

    Written directly rather than through ``outdate()``: Phase 4's ``outdate()``
    no longer produces this shape at all, so going through it would seed an
    input that cannot occur and make the test vacuous.
    """
    import uuid

    from django.utils import timezone

    from persistence.models import Tenant
    from workflow.models import (
        WorkflowEngineDefinition,
        WorkflowHistoryEntry,
        WorkflowItemState,
    )

    tenant = Tenant.objects.create(name="t-0018", slug="t-0018")
    TenantContext.set_tenant(tenant.id)
    try:
        definition = WorkflowEngineDefinition.objects.create(
            tenant=tenant,
            workspace_id=tenant.id,
            item_type="Requirement",
            preset=WorkflowEngineDefinition.PRESET_MINIMAL,
            workflow_json={"states": ["draft", "approved"], "transitions": []},
        )

        def _stranded(history_from):
            state = WorkflowItemState.objects.create(
                tenant=tenant,
                item_id=uuid.uuid4(),
                item_type="Requirement",
                workspace_id=tenant.id,
                definition=definition,
                current_state="outdated",
            )
            if history_from is not None:
                WorkflowHistoryEntry.objects.create(
                    tenant=tenant,
                    item_state=state,
                    from_state=history_from,
                    to_state="outdated",
                    transitioned_by="tester",
                    transitioned_at=timezone.now(),
                    workspace_id=tenant.id,
                )
            return state

        with_history = _stranded("approved")
        without_history = _stranded(None)
        yield tenant, definition, with_history, without_history
    finally:
        TenantContext.clear_tenant()


@pytest.mark.django_db(transaction=True)
def test_restores_the_pre_outdate_state_from_history(legacy_outdated):
    _tenant, _definition, with_history, _without = legacy_outdated
    from workflow.models import WorkflowItemState

    _module().restore_hijacked_states(_historical_apps(), connection.schema_editor())

    assert (
        WorkflowItemState.objects.get(pk=with_history.pk).current_state == "approved"
    )


@pytest.mark.django_db(transaction=True)
def test_falls_back_to_the_initial_state_without_history(legacy_outdated):
    """The documented fallback: ``workflow_json["states"][0]``.

    Leaving ``"outdated"`` would strand the row on a state no preset declares,
    so nothing could ever transition it out again.
    """
    _tenant, _definition, _with, without_history = legacy_outdated
    from workflow.models import WorkflowItemState

    _module().restore_hijacked_states(_historical_apps(), connection.schema_editor())

    assert (
        WorkflowItemState.objects.get(pk=without_history.pk).current_state == "draft"
    )


@pytest.mark.django_db(transaction=True)
def test_verify_passes_once_nothing_is_left_outdated(legacy_outdated):
    module = _module()

    module.restore_hijacked_states(_historical_apps(), connection.schema_editor())
    module.verify_no_state_left_outdated(
        _historical_apps(), connection.schema_editor()
    )  # must not raise


@pytest.mark.django_db(transaction=True)
def test_verify_fails_loudly_when_a_row_could_not_be_restored(legacy_outdated):
    """A partial run must not report success — it has no second chance."""
    module = _module()

    with pytest.raises(RuntimeError, match="still have"):
        module.verify_no_state_left_outdated(
            _historical_apps(), connection.schema_editor()
        )


@pytest.mark.django_db(transaction=True)
def test_is_idempotent(legacy_outdated):
    """A second run finds nothing stranded and must not re-write anything."""
    _tenant, _definition, with_history, _without = legacy_outdated
    from workflow.models import WorkflowItemState

    module = _module()
    module.restore_hijacked_states(_historical_apps(), connection.schema_editor())
    module.restore_hijacked_states(_historical_apps(), connection.schema_editor())

    assert (
        WorkflowItemState.objects.get(pk=with_history.pk).current_state == "approved"
    )
