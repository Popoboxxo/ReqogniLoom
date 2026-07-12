"""
Migration 0006: Additive Artifact backing for ADR (REQ-L2-TE-020).

Adds a nullable OneToOne ``artifact`` FK from ``as_adr`` to ``pl_artifact`` and
backfills one Artifact row per existing ADR so that ADRs can participate in the
Artifact-to-Artifact TraceLink graph (ADR <-> ArchitectureElement links).

Strategy (backward-compatible, no destructive changes):
  1. AddField ``artifact`` (nullable) — pure schema addition, existing rows keep
     NULL until backfilled.
  2. RunPython ``backfill_artifacts`` — for every ADR without a backing Artifact
     create one (artifact_type="Adr", same tenant/workspace) and assign it.
     Best-effort per row: an ADR whose workspace no longer exists is skipped and
     left with a NULL artifact instead of failing the whole migration.

The column stays nullable on purpose — see application/models.py::Adr.artifact.

COMP-AS-013 AdrService, COMP-AS-005 TraceLinkService.
leaf_id : COMP-AS-013
req_id  : REQ-L2-TE-020
"""
import uuid

from django.db import migrations, models
import django.db.models.deletion


def backfill_artifacts(apps, schema_editor):
    """Create one backing Artifact per existing ADR (idempotent)."""
    Adr = apps.get_model("application", "Adr")
    Artifact = apps.get_model("persistence", "Artifact")
    Workspace = apps.get_model("persistence", "Workspace")

    for adr in Adr.objects.filter(artifact__isnull=True).iterator():
        # Guard: the backing Artifact requires a valid workspace FK. If the
        # referenced workspace was removed, skip this ADR (leaves artifact NULL).
        if not Workspace.objects.filter(id=adr.workspace_id).exists():
            continue
        artifact = Artifact.objects.create(
            id=uuid.uuid4(),
            tenant_id=adr.tenant_id,
            workspace_id=adr.workspace_id,
            artifact_type="Adr",
            custom_fields={},
        )
        adr.artifact_id = artifact.id
        adr.save(update_fields=["artifact"])


def remove_artifacts(apps, schema_editor):
    """Reverse: delete backing Artifacts of type 'Adr' referenced by ADRs."""
    Adr = apps.get_model("application", "Adr")
    Artifact = apps.get_model("persistence", "Artifact")

    artifact_ids = list(
        Adr.objects.filter(artifact__isnull=False).values_list(
            "artifact_id", flat=True
        )
    )
    # Detach first to avoid the CASCADE deleting the ADR rows themselves.
    Adr.objects.filter(artifact__isnull=False).update(artifact=None)
    Artifact.objects.filter(id__in=artifact_ids, artifact_type="Adr").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("application", "0005_add_uid_to_adr_risk_issue"),
        ("persistence", "0027_add_prompt_template"),
    ]

    operations = [
        migrations.AddField(
            model_name="adr",
            name="artifact",
            field=models.OneToOneField(
                to="persistence.artifact",
                on_delete=django.db.models.deletion.CASCADE,
                related_name="adr",
                null=True,
                blank=True,
                help_text="REQ-L2-TE-020: backing Artifact for TraceLink support.",
            ),
        ),
        migrations.RunPython(backfill_artifacts, remove_artifacts),
    ]
