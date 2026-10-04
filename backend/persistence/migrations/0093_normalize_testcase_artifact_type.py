"""Normalise TestCase artifacts onto the plain ``"TestCase"`` type (#816).

Background
----------
``TestCase.test_type`` (first-class column, migration 0041) is the single
source of truth for a test case's type. Two write paths *also* tagged the
backing Artifact with a redundant ``"TestCase:<Type>"`` sub-type prefix
(``TestService.create_test_case`` and the CSV importer), which forced every
reader — link-type catalog, artifact diff, MCP neighbour projection and the
frontend traceability coverage badge — to strip the suffix again. Migration
0041 already backfilled the column from that prefix; this migration removes
the redundant representation itself.

Forward
-------
Delegates to :func:`persistence.testcase_type_normalization.normalize_testcase_artifact_types`:
``test_type`` is backfilled from the suffix for rows where the column is still
NULL (defensive, idempotent), then every ``"TestCase:<anything>"``
``artifact_type`` backed by a ``TestCase`` row is rewritten to the plain
``"TestCase"``. The rewrite is *guarded* (DATA-08): a tagged artifact with no
backing TestCase row is left untouched and logged rather than silently
relabelled.

Reverse
-------
Re-derives ``"TestCase:<Title>"`` from ``TestCase.test_type`` (the forward
mapping inverted). Rows whose column is NULL stay untagged, which is a faithful
inverse of the forward data migration; the column itself is never modified by
the reverse. No information is lost either way.
"""

from django.db import migrations

from persistence.testcase_type_normalization import (
    normalize_testcase_artifact_types,
    restore_testcase_artifact_type_tags,
    suspend_row_level_security,
)


def normalize_artifact_types(apps, schema_editor):
    """Backfill test_type from the suffix, then drop the redundant tag."""
    # schema_editor is None only when the test invokes the function directly.
    if schema_editor is not None:
        suspend_row_level_security()
    Artifact = apps.get_model("persistence", "Artifact")
    TestCase = apps.get_model("persistence", "TestCase")
    normalize_testcase_artifact_types(Artifact, TestCase)


def restore_artifact_type_tag(apps, schema_editor):
    """Reverse: re-derive the legacy sub-type tag from the canonical column."""
    if schema_editor is not None:
        suspend_row_level_security()
    Artifact = apps.get_model("persistence", "Artifact")
    TestCase = apps.get_model("persistence", "TestCase")
    restore_testcase_artifact_type_tags(Artifact, TestCase)


class Migration(migrations.Migration):

    dependencies = [
        ("persistence", "0092_rename_risk_owner_to_owner_name"),
    ]

    operations = [
        migrations.RunPython(normalize_artifact_types, restore_artifact_type_tag),
    ]
