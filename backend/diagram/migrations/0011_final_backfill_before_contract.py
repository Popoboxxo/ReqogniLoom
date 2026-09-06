"""Re-run the 28c-1 backfill immediately before ``DiagramVersion`` is dropped.

Datenmodell-Konsolidierung Task 28c-2 (Migrate half of the Expand/Migrate/
Contract that retires ``DiagramVersion``).

Why this exists at all — the single most important carry-over from Task 28c-1:
migration ``0010`` filled the Diagram's content columns from
``Diagram.current_version`` back when ``DiagramManager`` still wrote *only* the
version row. Every diagram created or updated between then and this deploy
therefore has a **stale or empty** payload on the row itself and a
``current_revision`` of 0. Making those columns authoritative without re-running
the copy would silently revert live content to whatever it looked like at 28c-1.

So the ordering is load-bearing and is the reason this is its own migration:

    writers cut over (code)  ->  THIS backfill  ->  0012 drops the old columns

Same source rows and same guards as ``0010``, so it is idempotent by
construction: it copies from ``current_version``, which still exists at this
point in the graph.

Depends on ``persistence.0078_migrate_legacy_versions`` — the same discipline
``persistence/0079`` (Task 28b) used — so no path through the migration graph
can drop ``diagram_diagramversion`` before its history has been copied into
``ArtifactVersion``.
"""
from django.db import migrations

_BACKFILL_SQL = """
    UPDATE diagram_diagram AS d
    SET payload_format = v.payload_format,
        payload = v.payload,
        canvas_json = v.canvas_json,
        current_revision = v.version_number
    FROM diagram_diagramversion AS v
    WHERE d.current_version_id = v.id
      AND (d.payload_format IS DISTINCT FROM v.payload_format
           OR d.payload IS DISTINCT FROM v.payload
           OR d.canvas_json IS DISTINCT FROM v.canvas_json
           OR d.current_revision IS DISTINCT FROM v.version_number)
"""

#: Null-safe (``IS DISTINCT FROM``) mismatch count. A non-zero result means a
#: row that should have been copied was not — which under RLS is the classic
#: silent failure mode this migration's guard exists to make loud.
_VERIFY_SQL = """
    SELECT count(*)
    FROM diagram_diagram AS d
    JOIN diagram_diagramversion AS v ON d.current_version_id = v.id
    WHERE d.payload_format IS DISTINCT FROM v.payload_format
       OR d.payload IS DISTINCT FROM v.payload
       OR d.canvas_json IS DISTINCT FROM v.canvas_json
       OR d.current_revision IS DISTINCT FROM v.version_number
"""


def _require_full_row_visibility(schema_editor):
    """Fail loudly instead of silently backfilling nothing under RLS.

    ``diagram_diagram`` and ``diagram_diagramversion`` both carry
    ``FORCE ROW LEVEL SECURITY`` with a policy keyed on the
    ``app.current_tenant`` session GUC, which no migration sets
    (``diagram/0008_diagram_rls_policies``). FORCE means even the table
    *owner* is subject to the policy, so an unguarded run updates zero rows
    and reports ``OK``.

    ``row_security = off`` inverts that: Postgres raises "query would be
    affected by row-level security policy" rather than quietly filtering the
    rows away. For a superuser / ``BYPASSRLS`` connection no policy is ever
    applied, so the setting is a no-op and the backfill sees every tenant's
    rows. Same guard as ``persistence/0073_backfill_artifact_backing``.
    """
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("SET LOCAL row_security = off")


def backfill(apps_registry, schema_editor):
    """Copy the current version's payload onto every Diagram row."""
    _require_full_row_visibility(schema_editor)
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(_BACKFILL_SQL)


def verify(apps_registry, schema_editor):
    """Fail the migration if any backed Diagram was left behind."""
    _require_full_row_visibility(schema_editor)
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(_VERIFY_SQL)
        mismatched = cursor.fetchone()[0]

    if mismatched:
        raise RuntimeError(
            f"Diagram content backfill incomplete: {mismatched} row(s) still "
            "differ from the DiagramVersion they point at. Dropping "
            "diagram_diagramversion now would lose that content."
        )


class Migration(migrations.Migration):
    # Atomic (the default) is load-bearing twice over: ``SET LOCAL`` is scoped
    # to this migration's transaction, and a RuntimeError from ``verify``
    # rolls the backfill back rather than leaving it half-applied.
    atomic = True

    dependencies = [
        ("diagram", "0010_backfill_current_content"),
        # Task 28a's history copy. Without this edge, a fresh database could
        # order 0012's DeleteModel before the copy and lose every historical
        # diagram payload.
        ("persistence", "0078_migrate_legacy_versions"),
    ]

    operations = [
        # Irreversible on purpose: a reverse would have to blank the columns,
        # which destroys the live payload now that they are the source of
        # record. Unapplying is a no-op; re-applying is safe.
        migrations.RunPython(backfill, migrations.RunPython.noop),
        migrations.RunPython(verify, migrations.RunPython.noop),
    ]
