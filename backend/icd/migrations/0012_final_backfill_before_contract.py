"""Re-run the 28c-1 backfill immediately before ``IcdVersion`` is dropped.

Datenmodell-Konsolidierung Task 28c-2 (Migrate half of the Expand/Migrate/
Contract that retires ``IcdVersion``).

Why this exists at all — the single most important carry-over from Task 28c-1:
migration ``0011`` filled the header's contract columns from
``Icd.current_version`` back when ``IcdManager`` still wrote *only* the version
row. Every ICD created or updated between then and this deploy therefore has a
**stale or empty** header contract, a ``current_revision`` of 0, and (for
parameters created in that window) a NULL ``icd_id``. Making those columns
authoritative without re-running the copy would silently revert live content to
whatever it looked like at 28c-1.

So the ordering is load-bearing and is the reason this is its own migration:

    writers cut over (code)  ->  THIS backfill  ->  0013 drops the old columns

Same source rows and same guards as ``0011``, so it is idempotent by
construction: it copies from ``current_version``/``icd_version.icd_id``, both of
which still exist at this point in the graph.

Depends on ``persistence.0078_migrate_legacy_versions`` — the same discipline
``persistence/0079`` (Task 28b) used — so no path through the migration graph
can drop ``icd_version`` before its history has been copied into
``ArtifactVersion``.
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
      AND (i.direction IS DISTINCT FROM v.direction
           OR i.interface_type IS DISTINCT FROM v.interface_type
           OR i.semantic_description IS DISTINCT FROM v.semantic_description
           OR i.preconditions IS DISTINCT FROM v.preconditions
           OR i.postconditions IS DISTINCT FROM v.postconditions
           OR i.invariants IS DISTINCT FROM v.invariants
           OR i.embedding IS DISTINCT FROM v.embedding
           OR i.current_revision IS DISTINCT FROM v.version_number)
"""

_BACKFILL_PARAMETER_SQL = """
    UPDATE icd_parameter AS p
    SET icd_id = v.icd_id
    FROM icd_version AS v
    WHERE p.icd_version_id = v.id
      AND p.icd_id IS DISTINCT FROM v.icd_id
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

#: ``icd_version_id`` is NOT NULL, so the join above covers every row and this
#: must be 0 — but ``0013`` is about to make ``icd_id`` NOT NULL, and a
#: constraint violation there would abort the deploy with a bare Postgres
#: error instead of a message naming the cause. Checked explicitly.
_VERIFY_PARAMETER_OWNED_SQL = """
    SELECT count(*) FROM icd_parameter WHERE icd_id IS NULL
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
        cursor.execute(_VERIFY_PARAMETER_OWNED_SQL)
        parameter_unowned = cursor.fetchone()[0]

    if icd_mismatched:
        raise RuntimeError(
            f"Icd contract backfill incomplete: {icd_mismatched} row(s) still "
            "differ from the IcdVersion they point at. Dropping icd_version "
            "now would lose that content."
        )
    if parameter_mismatched:
        raise RuntimeError(
            f"IcdParameter owner backfill incomplete: {parameter_mismatched} "
            "row(s) still have no or a wrong icd_id."
        )
    if parameter_unowned:
        raise RuntimeError(
            f"{parameter_unowned} icd_parameter row(s) have a NULL icd_id; "
            "making the column NOT NULL in 0013 would fail."
        )


class Migration(migrations.Migration):
    # Atomic (the default) is load-bearing twice over: ``SET LOCAL`` is scoped
    # to this migration's transaction, and a RuntimeError from ``verify``
    # rolls the backfill back rather than leaving it half-applied.
    atomic = True

    dependencies = [
        ("icd", "0011_backfill_current_content"),
        # Task 28a's history copy. Without this edge, a fresh database could
        # order 0013's DeleteModel before the copy and lose every historical
        # contract revision.
        ("persistence", "0078_migrate_legacy_versions"),
    ]

    operations = [
        # Irreversible on purpose: a reverse would have to blank the columns,
        # which destroys the live contract now that they are the source of
        # record. Unapplying is a no-op; re-applying is safe.
        migrations.RunPython(backfill, migrations.RunPython.noop),
        migrations.RunPython(verify, migrations.RunPython.noop),
    ]
