"""Backfill ``Diagram``'s new content columns from ``current_version``.

Datenmodell-Konsolidierung Task 28c-1 (Expand half of the Expand/Migrate/
Contract that retires ``DiagramVersion``). Migration 0009 added
``payload_format`` / ``payload`` / ``canvas_json`` / ``current_revision`` to
``diagram_diagram``; this migration fills them for every pre-existing row from
the ``DiagramVersion`` the header already points at.

Purely additive in effect: nothing reads the new columns yet (Task 28c-2
repoints the readers and the writers), and ``current_version`` and the whole
``diagram_diagramversion`` table are left untouched. A Diagram with
``current_version IS NULL`` has no content to copy and keeps the field
defaults (``""`` / ``""`` / ``NULL`` / ``0``).

Idempotent: re-running copies the same values from the same source row.
"""
from django.db import migrations

#: Straight column copy. Raw SQL rather than an ORM loop because this is a
#: single self-join UPDATE — the ORM shape would be one query per row for no
#: added safety, and the verify step below is the actual guard.
_BACKFILL_SQL = """
    UPDATE diagram_diagram AS d
    SET payload_format = v.payload_format,
        payload = v.payload,
        canvas_json = v.canvas_json,
        current_revision = v.version_number
    FROM diagram_diagramversion AS v
    WHERE d.current_version_id = v.id
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
    """Copy the current version's payload onto every Diagram header row."""
    _require_full_row_visibility(schema_editor)
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(_BACKFILL_SQL)


def verify(apps_registry, schema_editor):
    """Fail the migration if any backed Diagram did not receive its content."""
    _require_full_row_visibility(schema_editor)
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(_VERIFY_SQL)
        mismatched = cursor.fetchone()[0]
    if mismatched:
        raise RuntimeError(
            f"Diagram content backfill incomplete: {mismatched} row(s) still "
            "differ from the DiagramVersion they point at."
        )


class Migration(migrations.Migration):
    # Atomic (the default) is load-bearing twice over: ``SET LOCAL`` is scoped
    # to this migration's transaction, and a RuntimeError from ``verify``
    # rolls the backfill back rather than leaving it half-applied.
    atomic = True

    dependencies = [
        ("diagram", "0009_expand_current_content"),
    ]

    operations = [
        # Irreversible on purpose: a reverse would have to blank the columns,
        # which destroys live content once Task 28c-2 makes them the source of
        # record. Unapplying is a no-op; re-applying is safe.
        migrations.RunPython(backfill, migrations.RunPython.noop),
        migrations.RunPython(verify, migrations.RunPython.noop),
    ]
