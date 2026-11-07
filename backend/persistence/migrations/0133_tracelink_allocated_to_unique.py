"""P2: enforce N:1 allocation (one Requirement -> at most one element).

A duplicate ``allocated-to`` edge per source artifact is a data-integrity
violation that the pre-P2 generic TraceLink path could create (only
``TraceLinkService.allocate`` enforced the cardinality). The migration aborts
loudly and names the offending requirements instead of silently deleting one
of the competing edges — a silent choice would decide an SE question for the
user.
"""
from __future__ import annotations

from django.db import migrations, models
from django.db.models import Count, Q


def _assert_no_duplicate_allocations(apps, schema_editor):
    TraceLink = apps.get_model("persistence", "TraceLink")
    Requirement = apps.get_model("persistence", "Requirement")
    alias = schema_editor.connection.alias

    duplicates = list(
        TraceLink.objects.using(alias)
        .filter(link_type="allocated-to")
        .values("source_id")
        .annotate(edge_count=Count("id"))
        .filter(edge_count__gt=1)
        .values_list("source_id", "edge_count")
    )
    if not duplicates:
        return

    artifact_ids = [source_id for source_id, _ in duplicates]
    requirement_ids = list(
        Requirement.objects.using(alias)
        .filter(artifact_id__in=artifact_ids)
        .values_list("id", flat=True)
    )
    rendered = ", ".join(
        f"{requirement_id} (artifact {artifact_id})"
        for requirement_id, (artifact_id, _) in zip(requirement_ids, duplicates)
    )
    raise RuntimeError(
        "Cannot enforce N:1 allocation: the following requirements have more "
        "than one 'allocated-to' link — resolve them first: "
        f"{rendered or artifact_ids}"
    )


class Migration(migrations.Migration):
    dependencies = [
        ("persistence", "0132_artifact_sort_key"),
    ]

    operations = [
        migrations.RunPython(
            _assert_no_duplicate_allocations, migrations.RunPython.noop
        ),
        migrations.AddConstraint(
            model_name="tracelink",
            constraint=models.UniqueConstraint(
                condition=Q(link_type="allocated-to"),
                fields=("source",),
                name="uniq_tracelink_allocated_to_source",
            ),
        ),
    ]
