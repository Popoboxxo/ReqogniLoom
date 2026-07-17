"""
Migration 0008: Additive Artifact backing for Risk and Issue (REQ-L2-TE-020).

Adds a nullable OneToOne ``artifact`` FK from ``as_risk`` and ``as_issue`` to
``pl_artifact`` and backfills one Artifact row per existing Risk/Issue so that
Risks and Issues can participate in the Artifact-to-Artifact TraceLink graph.

This mirrors the ADR backing added in migration 0006 and replaces the former
UUID-identity hack in the seed script (``Artifact.objects.create(id=risk.id)``),
which created an Artifact sharing the entity's primary key with no referential
integrity and no CASCADE guarantee.

Strategy (backward-compatible, no destructive changes):
  1. AddField ``artifact`` (nullable) to Risk and Issue — pure schema addition,
     existing rows keep NULL until backfilled.
  2. RunPython ``backfill_artifacts`` — for every Risk/Issue without a backing
     Artifact create one (correct artifact_type, same tenant/workspace) and
     assign it. Best-effort per row: an entity whose workspace no longer exists
     is skipped and left with a NULL artifact instead of failing the migration.

     Backfill re-uses the entity's own id as the Artifact id where that id is not
     already taken. This keeps existing TraceLinks — which were created against
     ``Artifact.id == entity.id`` by the old seed hack — valid after migration.
     If an Artifact with that id already exists (the seed hack ran), it is simply
     linked instead of duplicated.

The column stays nullable on purpose — see application/models.py::Risk.artifact
and Issue.artifact.

COMP-AS-014 RiskService, COMP-AS-015 IssueService, COMP-AS-005 TraceLinkService.
leaf_id : COMP-AS-014, COMP-AS-015
req_id  : REQ-L2-TE-020
"""
import uuid

from django.db import migrations, models
import django.db.models.deletion


def _backfill(apps, entity_label, artifact_type):
    """Create/link one backing Artifact per existing entity (idempotent)."""
    Entity = apps.get_model("application", entity_label)
    Artifact = apps.get_model("persistence", "Artifact")
    Workspace = apps.get_model("persistence", "Workspace")

    for entity in Entity.objects.filter(artifact__isnull=True).iterator():
        # Guard: the backing Artifact requires a valid workspace FK. If the
        # referenced workspace was removed, skip (leaves artifact NULL).
        if not Workspace.objects.filter(id=entity.workspace_id).exists():
            continue

        # Reuse the entity id as the Artifact id when free. This preserves any
        # TraceLinks the old seed hack created against Artifact.id == entity.id.
        existing = Artifact.objects.filter(id=entity.id).first()
        if existing is not None:
            artifact = existing
        else:
            artifact = Artifact.objects.create(
                id=entity.id,
                tenant_id=entity.tenant_id,
                workspace_id=entity.workspace_id,
                artifact_type=artifact_type,
                custom_fields={},
            )
        entity.artifact_id = artifact.id
        entity.save(update_fields=["artifact"])


def backfill_artifacts(apps, schema_editor):
    _backfill(apps, "Risk", "Risk")
    _backfill(apps, "Issue", "Issue")


def _remove(apps, entity_label, artifact_type):
    """Reverse: detach and delete backing Artifacts of the given type."""
    Entity = apps.get_model("application", entity_label)
    Artifact = apps.get_model("persistence", "Artifact")

    artifact_ids = list(
        Entity.objects.filter(artifact__isnull=False).values_list(
            "artifact_id", flat=True
        )
    )
    # Detach first to avoid the CASCADE deleting the entity rows themselves.
    Entity.objects.filter(artifact__isnull=False).update(artifact=None)
    Artifact.objects.filter(
        id__in=artifact_ids, artifact_type=artifact_type
    ).delete()


def remove_artifacts(apps, schema_editor):
    _remove(apps, "Risk", "Risk")
    _remove(apps, "Issue", "Issue")
    # The OneToOne FK is DEFERRABLE INITIALLY DEFERRED, so the DELETE/UPDATE
    # rows above leave pending deferred-constraint trigger events. The reverse
    # migration runs the RemoveField DDL next in the same transaction, and
    # PostgreSQL refuses ``ALTER TABLE ... because it has pending trigger
    # events``. Force the deferred constraints to be checked now so the DDL can
    # proceed.
    schema_editor.execute("SET CONSTRAINTS ALL IMMEDIATE")


class Migration(migrations.Migration):

    dependencies = [
        ("application", "0007_adr_status_deleted"),
        ("persistence", "0038_workspace_default_link_type"),
    ]

    operations = [
        migrations.AddField(
            model_name="risk",
            name="artifact",
            field=models.OneToOneField(
                to="persistence.artifact",
                on_delete=django.db.models.deletion.CASCADE,
                related_name="risk",
                null=True,
                blank=True,
                help_text="REQ-L2-TE-020: backing Artifact for TraceLink support.",
            ),
        ),
        migrations.AddField(
            model_name="issue",
            name="artifact",
            field=models.OneToOneField(
                to="persistence.artifact",
                on_delete=django.db.models.deletion.CASCADE,
                related_name="issue",
                null=True,
                blank=True,
                help_text="REQ-L2-TE-020: backing Artifact for TraceLink support.",
            ),
        ),
        migrations.RunPython(backfill_artifacts, remove_artifacts),
    ]
