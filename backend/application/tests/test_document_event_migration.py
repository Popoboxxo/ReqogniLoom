"""Plan F F2-T7 — the outbox ``EventType`` choices migration is reversible.

The five ``Document*`` members are an expand-only enum extension
(``application/0037``, depends on ``0036``): the forward operation is a choices
change only, so it emits no destructive SQL, and its reverse restores exactly
the pre-Document choice list. The test drives the real ``MigrationExecutor``
rather than only inspecting the migration file, so a broken dependency or an
un-reversible operation fails here.
"""
from __future__ import annotations

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from application.models import DomainEventOutbox

PRE_TARGET = ("application", "0036_alter_domaineventoutbox_event_type")
TARGET = ("application", "0037_alter_domaineventoutbox_event_type_documents")

DOCUMENT_EVENT_VALUES = {
    "DocumentCreated",
    "DocumentUpdated",
    "DocumentDeleted",
    "DocumentStateChanged",
    "DocumentPublished",
}


def _projected_choices(target) -> set[str]:
    executor = MigrationExecutor(connection)
    state = executor.loader.project_state([target]).apps
    field = state.get_model("application", "DomainEventOutbox")._meta.get_field(
        "event_type"
    )
    return {value for value, _label in field.choices}


def test_model_declares_the_document_events():
    assert DOCUMENT_EVENT_VALUES <= set(DomainEventOutbox.EventType.values)


@pytest.mark.django_db(transaction=True)
def test_choices_migration_round_trip():
    executor = MigrationExecutor(connection)
    latest_target = executor.loader.graph.leaf_nodes()
    try:
        executor.migrate([PRE_TARGET])
        executor.loader.build_graph()
        assert not (DOCUMENT_EVENT_VALUES & _projected_choices(PRE_TARGET))

        executor.migrate([TARGET])
        executor.loader.build_graph()
        assert DOCUMENT_EVENT_VALUES <= _projected_choices(TARGET)

        # Reverse: the operation must roll back to the pre-Document choices.
        executor.migrate([PRE_TARGET])
        executor.loader.build_graph()
        assert not (DOCUMENT_EVENT_VALUES & _projected_choices(PRE_TARGET))
    finally:
        MigrationExecutor(connection).migrate(latest_target)
