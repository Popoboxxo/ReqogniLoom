# Generated for issue #126: enforce uniqueness on TraceLink (source, target,
# link_type) at the DB level. Deduplication runs first so the constraint can
# be added safely even if legacy duplicate edges exist.

from django.db import migrations, models


def dedupe_tracelinks(apps, schema_editor):
    """Keep the oldest row per (source, target, link_type); delete the rest.

    Safe to run repeatedly (idempotent): once no duplicates remain this is a
    no-op. Verified against the current dev/demo database: 0 duplicate edges
    found prior to this migration.
    """
    TraceLink = apps.get_model("persistence", "TraceLink")
    duplicates = (
        TraceLink.objects.values("source_id", "target_id", "link_type")
        .order_by("source_id", "target_id", "link_type")
        .annotate(cnt=models.Count("id"))
        .filter(cnt__gt=1)
    )
    for dup in duplicates:
        ids = list(
            TraceLink.objects.filter(
                source_id=dup["source_id"],
                target_id=dup["target_id"],
                link_type=dup["link_type"],
            )
            .order_by("created_at", "id")
            .values_list("id", flat=True)
        )
        # Keep the first (oldest), delete the rest.
        TraceLink.objects.filter(id__in=ids[1:]).delete()


def noop_reverse(apps, schema_editor):
    """Deduplication is not reversible (duplicate rows are gone for good).

    This is intentional: the deleted rows were true duplicates carrying no
    unique information, so re-creating them on reverse would recreate the
    exact defect this migration fixes.
    """


class Migration(migrations.Migration):

    dependencies = [
        ("persistence", "0048_app_role"),
    ]

    operations = [
        migrations.RunPython(dedupe_tracelinks, noop_reverse),
        migrations.AddConstraint(
            model_name="tracelink",
            constraint=models.UniqueConstraint(
                fields=["source", "target", "link_type"],
                name="uq_tracelink_edge",
            ),
        ),
    ]
