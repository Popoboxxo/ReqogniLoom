"""Idempotency test for the Phase 4 PromptTemplate data migration
(0044_prompt_template_versioning_data.py, ``_split_singleton_rows``).

The brief (task-1-brief.md Step 4) requires the data migration to be
"idempotent: safe to re-run." The migration file has a guard for this
(existence check + ``.exclude(pk=old_row.pk)``, plus restricting the outer
loop to ``name__isnull=True`` old-shape rows so an already-split row is never
picked up and deleted again), but nothing in the original diff exercised the
function twice to prove the guard actually works.

This uses Django's ``MigrationExecutor`` to put the ``persistence`` app's
schema back into the exact state ``_split_singleton_rows`` runs against in
production (right after 0043: new nullable columns present, old 3-slot
columns still present, old tenant-only uniqueness constraint already
dropped), seeds one old-shape singleton row via the historical model, then
calls the real ``_split_singleton_rows`` function (imported directly from the
migration file — its module name starts with a digit, so it is loaded via
``importlib`` rather than a dotted import) twice, asserting the row count
stays at 3 (one row per old slot name) after the second call rather than
growing to 6 or collapsing to 0.

Uses ``transaction=True`` (``TransactionTestCase`` semantics) because
``MigrationExecutor.migrate()`` runs real, separately-committed schema
migrations that must actually apply against the database — they cannot run
inside the outer rolled-back transaction pytest-django normally wraps tests
in. The ``finally`` block unconditionally migrates the ``persistence`` app
forward again to its latest migration so the schema is back to normal for
every other test in the suite, regardless of whether the assertions above it
passed or failed.
"""
from __future__ import annotations

import importlib.util
import pathlib

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

_APP_LABEL = "persistence"
_SCHEMA_MIGRATION = "0043_prompt_template_versioning_schema"
_DATA_MIGRATION = "0044_prompt_template_versioning_data"

_MIGRATION_PATH = (
    pathlib.Path(__file__).resolve().parents[1]
    / "migrations"
    / f"{_DATA_MIGRATION}.py"
)


def _load_split_singleton_rows():
    """Import ``_split_singleton_rows`` directly from the migration file.

    The migration module's filename starts with a digit
    (``0044_prompt_template_versioning_data.py``), which is not a valid
    Python identifier, so it can't be reached via a normal dotted import
    (``from persistence.migrations.0044_... import ...`` is a syntax error).
    """
    spec = importlib.util.spec_from_file_location(
        "_prompt_template_versioning_data_under_test", _MIGRATION_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module._split_singleton_rows


@pytest.mark.django_db(transaction=True)
def test_split_singleton_rows_is_idempotent() -> None:
    _split_singleton_rows = _load_split_singleton_rows()

    executor = MigrationExecutor(connection)
    # Leaf nodes across ALL apps, not just `persistence` (issue found
    # auditing the #568 theming branch): rolling `persistence` back to 0043
    # below forces Django to unapply every migration in the dependency
    # graph that transitively depends on it first — including apps outside
    # `persistence`. `context_graph.0001_initial` declares a dependency on
    # `persistence.0063_migrate_need_to_sysreq_n_placeholder`, so the
    # rollback silently drops `cg_workspace_context_settings`/
    # `cg_context_edge` too. Restoring only `persistence`'s own leaf in the
    # `finally` block below left those collaterally-unapplied tables gone
    # for the rest of the pytest session whenever this test ran before
    # rest_api's context-graph-settings tests — reproducing only in
    # full-suite runs, never in isolation.
    latest_target = executor.loader.graph.leaf_nodes()

    try:
        # Roll the `persistence` app's schema back to right after 0043: the
        # new nullable columns exist, the old 3-slot columns still exist,
        # the old tenant-only uniqueness constraint is already dropped — the
        # exact pre-state _split_singleton_rows runs against in production.
        executor.migrate([(_APP_LABEL, _SCHEMA_MIGRATION)])
        executor.loader.build_graph()

        state = executor.loader.project_state((_APP_LABEL, _SCHEMA_MIGRATION))
        historical_apps = state.apps
        OldPromptTemplate = historical_apps.get_model(_APP_LABEL, "PromptTemplate")
        Tenant = historical_apps.get_model(_APP_LABEL, "Tenant")

        tenant = Tenant.objects.create(
            name="Migration Idempotency Test Tenant", slug="mig-idempotency-test"
        )

        # Seed exactly one old-shape singleton row (name=None, the 3 old
        # slot fields populated) — mirrors real pre-Phase-4 data.
        old_row = OldPromptTemplate.objects.create(
            tenant_id=tenant.id,
            need_to_sysreq="Derive system requirement from {need_title}",
            sysreq_to_arch_assign="Assign {sysreq_id} to architecture element",
            sysreq_decompose_next_level="Decompose {sysreq_id} to next V-model level",
        )
        assert OldPromptTemplate.objects.filter(tenant_id=tenant.id).count() == 1

        # First run: the real migration behavior — splits the singleton
        # into 3 named v1 rows and deletes the old row.
        _split_singleton_rows(historical_apps, None)
        rows_after_first = OldPromptTemplate.objects.filter(tenant_id=tenant.id)
        assert rows_after_first.count() == 3
        assert not rows_after_first.filter(pk=old_row.pk).exists()
        snapshot_after_first = {
            row.name: (row.pk, row.content)
            for row in rows_after_first
        }
        assert set(snapshot_after_first) == {
            "need_to_sysreq",
            "sysreq_to_arch_assign",
            "sysreq_decompose_next_level",
        }

        # Second run against the now-split data: must be a true no-op —
        # same row count, same primary keys, same content. A plain
        # ``objects.all()`` without the ``name__isnull=True`` guard does NOT
        # simply wipe the table to 0 on a re-run (the row count alone stays
        # misleadingly at 3): because the historical model's old slot fields
        # (``need_to_sysreq`` etc.) carry non-None Python-level defaults,
        # ``getattr(split_row, slot_name)`` on an already-split row returns
        # that default (truthy) rather than None, so the inner loop's
        # ``already_exists`` check (which excludes the row's own pk) finds
        # "no conflict" for the row's own slot name and creates a *duplicate*
        # replacement row with default content, then deletes the original —
        # silently discarding the tenant's actual customized content and
        # replacing it with placeholder defaults, while keeping the total
        # row count at 3 by coincidence. Asserting pks and content are
        # unchanged (not just the count) is what catches this.
        _split_singleton_rows(historical_apps, None)
        rows_after_second = OldPromptTemplate.objects.filter(tenant_id=tenant.id)
        assert rows_after_second.count() == 3
        snapshot_after_second = {
            row.name: (row.pk, row.content)
            for row in rows_after_second
        }
        assert snapshot_after_second == snapshot_after_first
    finally:
        # Always restore the schema to its latest state so every other test
        # in the suite sees the normal, current PromptTemplate shape.
        executor = MigrationExecutor(connection)
        executor.migrate(latest_target)
