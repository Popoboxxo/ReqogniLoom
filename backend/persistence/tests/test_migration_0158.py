"""Forward/reverse test for migration 0158 (change-impact data model).

Covers spec 2026-11-28 §4.2.3–§4.2.5 / REQ-216:

* the three new tables are created and dropped cleanly,
* the additive ``ChangeRequest`` / ``ChangeRequestAffectedItem`` columns
  arrive with defaults that keep existing rows valid,
* the RLS policies ship in the same migration,
* ``makemigrations --check`` reports no drift.

The reverse test rolls the ``persistence`` app back to ``0157``. Only this
migration depends on ``0157`` (verified: no other app's migration names it),
so the rollback does not collaterally unapply other apps' tables — the trap
that ``test_prompt_template_migration.py`` documents.
"""
from __future__ import annotations

import pytest
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

_APP = "persistence"
_PREV = "0157_suggestion_capture_fields"
_CURRENT = "0158_change_impact_analysis"

_TABLES = (
    "as_change_impact_run",
    "as_change_impact_finding",
    "as_change_impact_chain",
)

_RUN_COLUMNS = {
    "workspace_id",
    "baseline_id",
    "status",
    "trigger",
    "algorithm_version",
    "root_item_ids",
    "roots_source",
    "gate_eligible",
    "graph_fingerprint",
    "gate_fingerprint",
    "affected_items_hash",
    "catalog_hash",
    "policy_hash",
    "visited_node_ids",
    "node_count",
    "edge_count",
    "path_count",
    "truncated",
    "truncated_reason",
    "include_semantic",
    "forced",
    "pinned",
    "llm_used",
    "llm_provider",
    "llm_model",
    "prompt_version",
    "heartbeat_at",
    "error",
    "started_at",
    "finished_at",
}

_CR_COLUMNS = {
    "impact_summary",
    "summary_run_id",
    "impact_source",
    "impact_generated_at",
    "impact_override_reason",
    "impact_truncation_waiver_reason",
    "truncation_waiver_run_id",
    "truncation_waiver_by_id",
    "truncation_waiver_expires_at",
}

_AFFECTED_ITEM_COLUMNS = {
    "change_action",
    "rationale",
    "origin",
    "removed_reason",
}


def _table_exists(table: str) -> bool:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = %s",
            [table],
        )
        return cursor.fetchone() is not None


def _columns(table: str) -> set[str]:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = %s",
            [table],
        )
        return {row[0] for row in cursor.fetchall()}


@pytest.mark.django_db(transaction=True)
def test_forward_then_reverse_then_forward_is_deterministic() -> None:
    executor = MigrationExecutor(connection)
    leaf_targets = executor.loader.graph.leaf_nodes()
    try:
        # --- reverse to 0157 ---------------------------------------------
        executor = MigrationExecutor(connection)
        executor.migrate([(_APP, _PREV)])

        for table in _TABLES:
            assert not _table_exists(table), f"{table} survived the reverse"
        assert not (_CR_COLUMNS & _columns("as_change_request"))
        assert not (_AFFECTED_ITEM_COLUMNS & _columns("as_change_request_affected_item"))

        # --- forward again ------------------------------------------------
        executor = MigrationExecutor(connection)
        executor.migrate([(_APP, _CURRENT)])

        for table in _TABLES:
            assert _table_exists(table), f"{table} missing after forward"
        assert _RUN_COLUMNS <= _columns("as_change_impact_run")
        assert _CR_COLUMNS <= _columns("as_change_request")
        assert _AFFECTED_ITEM_COLUMNS <= _columns("as_change_request_affected_item")

        # RLS shipped with the tables.
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT relname, relrowsecurity, relforcerowsecurity "
                "FROM pg_class WHERE relname = ANY(%s)",
                [list(_TABLES)],
            )
            state = {row[0]: (row[1], row[2]) for row in cursor.fetchall()}
        for table in _TABLES:
            enabled, forced = state[table]
            assert enabled, f"RLS not enabled on {table}"
            assert forced, f"RLS not forced on {table}"

        # --- reverse again: deterministic up/down/up ----------------------
        executor = MigrationExecutor(connection)
        executor.migrate([(_APP, _PREV)])
        for table in _TABLES:
            assert not _table_exists(table)
    finally:
        # Restore the schema for every other test in the session.
        executor = MigrationExecutor(connection)
        executor.migrate(leaf_targets)


@pytest.mark.django_db(transaction=True)
def test_existing_rows_get_safe_defaults() -> None:
    executor = MigrationExecutor(connection)
    leaf_targets = executor.loader.graph.leaf_nodes()
    try:
        executor = MigrationExecutor(connection)
        executor.migrate([(_APP, _PREV)])

        # Historical model state at 0157: no impact columns yet.
        old_apps = executor.loader.project_state([(_APP, _PREV)]).apps
        OldTenant = old_apps.get_model("persistence", "Tenant")
        OldCR = old_apps.get_model("persistence", "ChangeRequest")
        OldItem = old_apps.get_model("persistence", "ChangeRequestAffectedItem")

        tenant = OldTenant.objects.create(name="mig-0158", slug="mig-0158")
        cr = OldCR.objects.create(
            tenant_id=tenant.id, workspace_id="00000000-0000-0000-0000-000000000001",
            title="existing CR",
        )
        OldItem.objects.create(
            tenant_id=tenant.id, change_request_id=cr.id, item_id="a" * 64
        )

        # Apply 0158 over the existing rows.
        executor = MigrationExecutor(connection)
        executor.migrate([(_APP, _CURRENT)])

        # The rows are still readable and carry the documented defaults.
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT impact_source, impact_summary, impact_override_reason "
                "FROM as_change_request WHERE id = %s",
                [cr.id],
            )
            impact_source, summary, override = cursor.fetchone()
            assert impact_source == "none"
            assert summary == ""
            assert override == ""

            cursor.execute(
                "SELECT change_action, origin, rationale, removed_reason "
                "FROM as_change_request_affected_item WHERE change_request_id = %s",
                [cr.id],
            )
            change_action, origin, rationale, removed_reason = cursor.fetchone()
            assert change_action == "modify"
            assert origin == "manual"
            assert rationale == ""
            assert removed_reason == ""
    finally:
        executor = MigrationExecutor(connection)
        executor.migrate(leaf_targets)


@pytest.mark.django_db
def test_makemigrations_check_is_clean() -> None:
    """The committed model state must match migration 0158 (no drift)."""
    call_command(
        "makemigrations",
        "--check",
        "--dry-run",
        verbosity=0,
    )
