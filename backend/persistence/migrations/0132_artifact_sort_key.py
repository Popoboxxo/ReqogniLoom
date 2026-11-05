"""P1 "Ordnung und Allokation": persistent sibling order on ``Artifact``.

Adds the collation-``C`` fractional key column plus its sort index, then
backfills only the two ordered tree types (Requirements and Architecture
Elements). Every other artifact type keeps ``sort_key = NULL`` and continues to
sort by ``created_at, id``.

The backfill is idempotent: a sibling block that is already fully keyed is left
untouched, so running the migration a second time writes nothing. Existing keys
keep their value on a re-run because a block with no NULL key is skipped.
"""
from __future__ import annotations

from django.db import migrations, models

from persistence.sort_keys import rebalance_keys

_ORDERED_TYPES = ("Requirement", "ArchitectureElement")


def _backfill_sort_keys(apps, schema_editor):
    Artifact = apps.get_model("persistence", "Artifact")
    alias = schema_editor.connection.alias

    rows = list(
        Artifact.objects.using(alias)
        .filter(artifact_type__in=_ORDERED_TYPES)
        .values_list("id", "workspace_id", "parent_id", "artifact_type", "sort_key")
        .order_by("created_at", "id")
    )

    groups: dict[tuple, list[tuple]] = {}
    for artifact_id, workspace_id, parent_id, artifact_type, sort_key in rows:
        key = (
            ("child", workspace_id, parent_id)
            if parent_id is not None
            else ("root", workspace_id, artifact_type)
        )
        groups.setdefault(key, []).append((artifact_id, sort_key))

    for members in groups.values():
        if all(sort_key is not None for _, sort_key in members):
            continue
        keys = rebalance_keys(len(members))
        objs = [
            Artifact(id=artifact_id, sort_key=new_key)
            for (artifact_id, _), new_key in zip(members, keys, strict=True)
        ]
        for start in range(0, len(objs), 500):
            Artifact.objects.using(alias).bulk_update(
                objs[start : start + 500], ["sort_key"]
            )


def _clear_sort_keys(apps, schema_editor):
    Artifact = apps.get_model("persistence", "Artifact")
    Artifact.objects.using(schema_editor.connection.alias).filter(
        artifact_type__in=_ORDERED_TYPES
    ).update(sort_key=None)


class Migration(migrations.Migration):
    dependencies = [
        ("persistence", "0131_interview_session_orphan_cleanup"),
    ]

    operations = [
        migrations.AddField(
            model_name="artifact",
            name="sort_key",
            field=models.CharField(
                blank=True,
                db_collation="C",
                help_text=(
                    "Fractional sort key for persistent sibling order. Scoped by "
                    "``parent``; roots are ordered per ``(workspace, artifact_type)``. "
                    "NULL for artifact types that do not participate in ordered trees."
                ),
                max_length=64,
                null=True,
            ),
        ),
        migrations.AddIndex(
            model_name="artifact",
            index=models.Index(
                fields=["parent", "sort_key", "id"],
                name="idx_artifact_parent_sort",
            ),
        ),
        migrations.RunPython(_backfill_sort_keys, _clear_sort_keys),
    ]
