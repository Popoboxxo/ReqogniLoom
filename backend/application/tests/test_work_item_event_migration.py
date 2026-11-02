"""Plan F F3-T8 — the outbox ``EventType`` choices migration is reversible.

The two ``Item*`` members are an expand-only enum extension
(``application/0038``, depends on ``0037``): the forward operation is a choices
change only, so it emits no destructive SQL, and its reverse restores exactly
the pre-WorkItem choice list. The test drives the real ``MigrationExecutor``
rather than only inspecting the migration file, so a broken dependency or an
un-reversible operation fails here.

Run with ``--create-db`` when touching the migration: the executor rewinds the
schema, which a reused test database may not tolerate.
"""
from __future__ import annotations

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from application.models import DomainEventOutbox

PRE_TARGET = ("application", "0037_alter_domaineventoutbox_event_type_documents")
TARGET = ("application", "0038_alter_domaineventoutbox_event_type_work_items")

WORK_ITEM_EVENT_VALUES = {
    "ItemStateChanged",
    "ItemBlocked",
}


def _projected_choices(target) -> set[str]:
    executor = MigrationExecutor(connection)
    state = executor.loader.project_state([target]).apps
    field = state.get_model("application", "DomainEventOutbox")._meta.get_field(
        "event_type"
    )
    return {value for value, _label in field.choices}


def test_model_declares_the_work_item_events():
    assert WORK_ITEM_EVENT_VALUES <= set(DomainEventOutbox.EventType.values)


@pytest.mark.django_db(transaction=True)
def test_choices_migration_round_trip():
    executor = MigrationExecutor(connection)
    latest_target = executor.loader.graph.leaf_nodes()
    try:
        executor.migrate([PRE_TARGET])
        executor.loader.build_graph()
        assert not (WORK_ITEM_EVENT_VALUES & _projected_choices(PRE_TARGET))

        executor.migrate([TARGET])
        executor.loader.build_graph()
        assert WORK_ITEM_EVENT_VALUES <= _projected_choices(TARGET)

        # Reverse: the operation must roll back to the pre-WorkItem choices.
        executor.migrate([PRE_TARGET])
        executor.loader.build_graph()
        assert not (WORK_ITEM_EVENT_VALUES & _projected_choices(PRE_TARGET))
    finally:
        MigrationExecutor(connection).migrate(latest_target)
