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
* ``test_type`` is backfilled from the suffix for rows where the column is
  still NULL (defensive, idempotent — 0041 already did this for the then-known
  suffixes).
* Every ``"TestCase:<anything>"`` ``artifact_type`` is rewritten to the plain
  ``"TestCase"``.

Reverse
-------
Re-derives ``"TestCase:<Title>"`` from ``TestCase.test_type`` (the forward
mapping inverted). Rows whose column is NULL stay untagged, which is a faithful
inverse of the forward data migration; the column itself is never modified by
the reverse. No information is lost either way, and no read path depends on
the tag any more.
"""

from django.db import migrations

# Legacy lowercase artifact_type suffix -> canonical test_type value.
_SUFFIX_TO_TEST_TYPE = {
    "system": "system",
    "integration": "integration",
    "unit": "unit",
    "inspection": "inspection",
    "analysis": "analysis",
    "demonstration": "demonstration",
}

# Canonical test_type value -> legacy Title-case suffix (reverse mapping).
_TEST_TYPE_TO_SUFFIX = {
    "system": "System",
    "integration": "Integration",
    "unit": "Unit",
    "inspection": "Inspection",
    "analysis": "Analysis",
    "demonstration": "Demonstration",
}

_PREFIX = "TestCase:"
_BASE_TYPE = "TestCase"


def normalize_artifact_types(apps, schema_editor):
    """Backfill test_type from the suffix, then drop the redundant tag."""
    Artifact = apps.get_model("persistence", "Artifact")
    TestCase = apps.get_model("persistence", "TestCase")

    # The legacy suffixes were written Title-case ("TestCase:Unit"); matching
    # case-insensitively keeps this idempotent for any hand-written variant.
    for suffix, test_type in _SUFFIX_TO_TEST_TYPE.items():
        artifact_ids = list(
            Artifact.objects.filter(
                artifact_type__iexact=f"{_PREFIX}{suffix}"
            ).values_list("id", flat=True)
        )
        if not artifact_ids:
            continue
        TestCase.objects.filter(
            artifact_id__in=artifact_ids, test_type__isnull=True
        ).update(test_type=test_type)

    Artifact.objects.filter(artifact_type__istartswith=_PREFIX).update(
        artifact_type=_BASE_TYPE
    )


def restore_artifact_type_tag(apps, schema_editor):
    """Reverse: re-derive the legacy sub-type tag from the canonical column."""
    Artifact = apps.get_model("persistence", "Artifact")
    TestCase = apps.get_model("persistence", "TestCase")

    for test_type, suffix in _TEST_TYPE_TO_SUFFIX.items():
        artifact_ids = TestCase.objects.filter(test_type=test_type).values_list(
            "artifact_id", flat=True
        )
        Artifact.objects.filter(id__in=list(artifact_ids)).update(
            artifact_type=f"{_PREFIX}{suffix}"
        )


class Migration(migrations.Migration):

    dependencies = [
        ("persistence", "0092_rename_risk_owner_to_owner_name"),
    ]

    operations = [
        migrations.RunPython(normalize_artifact_types, restore_artifact_type_tag),
    ]
