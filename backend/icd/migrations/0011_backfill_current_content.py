"""Backfill ``Icd``'s contract columns and ``IcdParameter.icd``.

Datenmodell-Konsolidierung Task 28c-1 (Expand half of the Expand/Migrate/
Contract that retires ``IcdVersion``). Migration 0010 added the
Design-by-Contract columns, ``embedding`` and ``current_revision`` to
``icd_icd`` plus the nullable ``icd`` FK on ``icd_parameter``; this migration
fills them for every pre-existing row.

Two backfills, both from the row the header already points at or the row the
child already hangs off:

1. ``Icd`` <- ``Icd.current_version`` (contract fields, embedding, revision).
   An ICD with ``current_version IS NULL`` has nothing to copy and keeps the
   field defaults.
2. ``IcdParameter.icd`` <- ``IcdParameter.icd_version.icd_id``, for **every**
   parameter row, not just those on the current version. Rationale: parameters
   are already mutable in place (``IcdParameterService.update_parameter``
   saves the row; only ``IcdVersion`` is under the immutability trigger) and
   ``IcdManager.update_icd`` does not copy them onto the new version, so
   "the parameter set of revision N" is not a semantics the system actually
   maintains. Backfilling only the current version's parameters would strip
   every ICD that has ever been updated of its live, user-visible parameter
   list. See the Task 28c-1 report for the full argument.

Purely additive in effect: nothing reads the new columns yet (Task 28c-2
repoints the readers and the writers), and ``current_version`` /
``icd_parameter.icd_version`` / the ``icd_version`` table are left untouched.

Idempotent: re-running copies the same values from the same source rows.
"""
from django.db import migrations

#: Straight column copy off the current version. ``embedding`` is a pgvector
#: column on both sides, so the assignment is a plain vector-to-vector copy.
_BACKFILL_ICD_SQL = """
    UPDATE icd_icd AS i
    SET direction = v.direction,
        interface_type = v.interface_type,
        semantic_description = v.semantic_description,
        preconditions = v.preconditions,
        postconditions = v.postconditions,
        invariants = v.invariants,
        embedding = v.embedding,
        current_revision = v.version_number
    FROM icd_version AS v
    WHERE i.current_version_id = v.id
"""

_BACKFILL_PARAMETER_SQL = """
    UPDATE icd_parameter AS p
    SET icd_id = v.icd_id
    FROM icd_version AS v
    WHERE p.icd_version_id = v.id
"""

#: Null-safe (``IS DISTINCT FROM``) mismatch counts. A non-zero result means a
#: row that should have been copied was not — which under RLS is the classic
#: silent failure mode this migration's guard exists to make loud.
_VERIFY_ICD_SQL = """
    SELECT count(*)
    FROM icd_icd AS i
    JOIN icd_version AS v ON i.current_version_id = v.id
    WHERE i.direction IS DISTINCT FROM v.direction
       OR i.interface_type IS DISTINCT FROM v.interface_type
       OR i.semantic_description IS DISTINCT FROM v.semantic_description
       OR i.preconditions IS DISTINCT FROM v.preconditions
       OR i.postconditions IS DISTINCT FROM v.postconditions
       OR i.invariants IS DISTINCT FROM v.invariants
       OR i.embedding IS DISTINCT FROM v.embedding
       OR i.current_revision IS DISTINCT FROM v.version_number
"""

_VERIFY_PARAMETER_SQL = """
    SELECT count(*)
    FROM icd_parameter AS p
    JOIN icd_version AS v ON p.icd_version_id = v.id
    WHERE p.icd_id IS DISTINCT FROM v.icd_id
"""


def _require_full_row_visibility(schema_editor):
    """Fail loudly instead of silently backfilling nothing under RLS.

    ``icd_icd``, ``icd_version`` and ``icd_parameter`` all carry
    ``FORCE ROW LEVEL SECURITY`` with a policy keyed on the
    ``app.current_tenant`` session GUC, which no migration sets
    (``icd/0007_icd_rls_policies``). FORCE means even the table *owner* is
    subject to the policy, so an unguarded run updates zero rows and reports
    ``OK``.

    ``row_security = off`` inverts that: Postgres raises "query would be
    affected by row-level security policy" rather than quietly filtering the
    rows away. For a superuser / ``BYPASSRLS`` connection no policy is ever
    applied, so the setting is a no-op and the backfill sees every tenant's
    rows. Same guard as ``persistence/0073_backfill_artifact_backing``.
    """
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("SET LOCAL row_security = off")


def backfill(apps_registry, schema_editor):
    """Copy the current contract onto the header and re-own every parameter."""
    _require_full_row_visibility(schema_editor)
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(_BACKFILL_ICD_SQL)
        cursor.execute(_BACKFILL_PARAMETER_SQL)


def verify(apps_registry, schema_editor):
    """Fail the migration if any backed Icd or parameter was left behind."""
    _require_full_row_visibility(schema_editor)
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(_VERIFY_ICD_SQL)
        icd_mismatched = cursor.fetchone()[0]
        cursor.execute(_VERIFY_PARAMETER_SQL)
        parameter_mismatched = cursor.fetchone()[0]

    if icd_mismatched:
        raise RuntimeError(
            f"Icd contract backfill incomplete: {icd_mismatched} row(s) still "
            "differ from the IcdVersion they point at."
        )
    if parameter_mismatched:
        raise RuntimeError(
            f"IcdParameter owner backfill incomplete: {parameter_mismatched} "
            "row(s) still have no or a wrong icd_id."
        )


class Migration(migrations.Migration):
    # Atomic (the default) is load-bearing twice over: ``SET LOCAL`` is scoped
    # to this migration's transaction, and a RuntimeError from ``verify``
    # rolls the backfill back rather than leaving it half-applied.
    atomic = True

    dependencies = [
        ("icd", "0010_expand_current_content"),
    ]

    operations = [
        # Irreversible on purpose: a reverse would have to blank the columns,
        # which destroys live content once Task 28c-2 makes them the source of
        # record. Unapplying is a no-op; re-applying is safe.
        migrations.RunPython(backfill, migrations.RunPython.noop),
        migrations.RunPython(verify, migrations.RunPython.noop),
    ]
