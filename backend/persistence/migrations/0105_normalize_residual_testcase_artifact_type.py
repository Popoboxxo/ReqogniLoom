# DATA-08 (audit-review 2026-09, findings 181/189) — residual TestCase tag
# correction.
#
# 0093 removed the deprecated ``"TestCase:<Type>"`` artifact_type tag, but it
# had already been applied when this unit ran, and live rows created/restored
# afterwards still carried it:
#
#   SELECT artifact_type, count(*) FROM pl_artifact
#   WHERE artifact_type LIKE 'TestCase:%' GROUP BY artifact_type;
#     TestCase:Unit   -> 69
#     TestCase:System -> 30
#
# All 99 were backed by a TestCase row and all 99 had ``test_type IS NULL``
# (30 of them were the source/target of a live TraceLink). This migration
# re-runs the same normalisation in a guarded, idempotent, reversible way:
#
#   * it backfills ``TestCase.test_type`` from the suffix only where the column
#     is NULL — never overwriting the canonical column;
#   * it rewrites only artifacts backed by a TestCase row, so an unrelated
#     artifact that merely starts with "TestCase:" is not relabelled; such
#     unbacked rows are logged as a documented residual instead;
#   * re-running is a no-op (both steps filter on the current state);
#   * ``SET LOCAL row_security = off`` makes a migration run under an
#     RLS-blinded role (the least-privilege app user) fail loudly instead of
#     silently normalising zero rows.
#
# Reverse mirrors 0093: re-derive the Title-case tag from the canonical column.
# It transfers the same information in both directions and never deletes data;
# like 0093 it re-tags every TestCase whose column carries a known value rather
# than only the residual rows (the two populations are not distinguishable
# after the forward pass).
#
# The implementation lives in ``persistence.testcase_type_normalization`` so
# 0093, 0105 and the tests share one code path (no drift).

from django.db import migrations

from persistence.testcase_type_normalization import (
    normalize_testcase_artifact_types,
    restore_testcase_artifact_type_tags,
    suspend_row_level_security,
)


def normalize_residual(apps, schema_editor):
    # Fail loudly if the migration runs under a role RLS would blind (see
    # suspend_row_level_security) instead of silently normalising zero rows.
    # schema_editor is None only when a test invokes the function directly.
    if schema_editor is not None:
        suspend_row_level_security()
    Artifact = apps.get_model("persistence", "Artifact")
    TestCase = apps.get_model("persistence", "TestCase")
    normalize_testcase_artifact_types(Artifact, TestCase)


def restore_residual(apps, schema_editor):
    if schema_editor is not None:
        suspend_row_level_security()
    Artifact = apps.get_model("persistence", "Artifact")
    TestCase = apps.get_model("persistence", "TestCase")
    restore_testcase_artifact_type_tags(Artifact, TestCase)


class Migration(migrations.Migration):

    dependencies = [
        ("persistence", "0104_tracelink_no_self_link"),
    ]

    operations = [
        migrations.RunPython(normalize_residual, restore_residual),
    ]
