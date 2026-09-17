"""
Migration 0064: Additive Artifact backing for InterviewSession (Issue: UI
Interview-Feedback follow-up, 2026-08-20).

Adds a nullable OneToOne ``artifact`` FK from ``pl_interview_session`` to
``pl_artifact`` and backfills one Artifact row per existing InterviewSession,
mirroring the Risk/Issue backing added in
``application/migrations/0008_risk_issue_artifact_backing.py``. Unlike Risk/
Issue this is NOT primarily for TraceLink participation — the driving need is
enabling InterviewSession to register with the workflow engine
(``workflow.services.initialize_workflow_states``/``transition``), which does
not itself require an Artifact FK (``WorkflowItemState.item_id`` is a bare
UUID field), but is added anyway for architectural consistency with every
other workflow-tracked entity and to allow interview sessions to eventually
participate in the TraceLink graph (e.g. linking a session to the artifact it
grounded against, not just via ``target_artifact``).

Strategy (backward-compatible, no destructive changes):
  1. AddField ``artifact`` (nullable) to InterviewSession — pure schema
     addition, existing rows keep NULL until backfilled.
  2. RunPython ``backfill_artifacts`` — for every InterviewSession without a
     backing Artifact, create one (artifact_type="Interview", same tenant/
     workspace) and assign it. Best-effort per row: a session whose
     workspace no longer exists is skipped and left with a NULL artifact
     instead of failing the migration.

     Unlike the Risk/Issue backfill, there is no legacy "same id as the
     entity" seed hack to preserve here (InterviewSession is new enough that
     no such hack ever existed) — the backing Artifact gets its own fresh id.
"""
import uuid

from django.db import migrations, models
import django.db.models.deletion


def backfill_artifacts(apps, schema_editor):
    InterviewSession = apps.get_model("persistence", "InterviewSession")
    Artifact = apps.get_model("persistence", "Artifact")
    Workspace = apps.get_model("persistence", "Workspace")

    for session in InterviewSession.objects.filter(artifact__isnull=True).iterator():
        if not Workspace.objects.filter(id=session.workspace_id).exists():
            continue
        artifact = Artifact.objects.create(
            id=uuid.uuid4(),
            tenant_id=session.tenant_id,
            workspace_id=session.workspace_id,
            artifact_type="Interview",
            custom_fields={},
        )
        session.artifact_id = artifact.id
        session.save(update_fields=["artifact"])


def remove_artifacts(apps, schema_editor):
    InterviewSession = apps.get_model("persistence", "InterviewSession")
    Artifact = apps.get_model("persistence", "Artifact")

    artifact_ids = list(
        InterviewSession.objects.filter(artifact__isnull=False).values_list(
            "artifact_id", flat=True
        )
    )
    InterviewSession.objects.filter(artifact__isnull=False).update(artifact=None)
    Artifact.objects.filter(id__in=artifact_ids, artifact_type="Interview").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("persistence", "0063_migrate_need_to_sysreq_n_placeholder"),
    ]

    operations = [
        migrations.AddField(
            model_name="interviewsession",
            name="artifact",
            field=models.OneToOneField(
                to="persistence.artifact",
                on_delete=django.db.models.deletion.CASCADE,
                related_name="interview_session",
                null=True,
                blank=True,
                help_text="Backing Artifact — enables workflow-engine tracking and future TraceLink participation.",
            ),
        ),
        migrations.RunPython(backfill_artifacts, remove_artifacts),
    ]
