# Plan F F2-T1 (#1374, ADR-026): the document artifact.
#
# `Document` owns one backing `pl_artifact` row (like Requirement), carries a
# per-workspace partial uid uniqueness (`uq_document_workspace_uid`, G1.3/#1402)
# and a DB mirror of its kind choices (`ck_document_kind`). There is deliberately
# no lifecycle/status column: the workflow state lives in `we_item_state` and
# soft-delete lives on `pl_artifact.lifecycle_status` (Plan G G1.5 V1).
#
# The tenant RLS policy ships in the very next migration
# (`0124_document_rls_policy`) in the same release (KA-F-13).
import django.db.models.deletion
import django.db.models.manager
import persistence.models
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('persistence', '0122_quality_assessment_rls_policy'),
    ]

    operations = [
        migrations.CreateModel(
            name='Document',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('modified_at', models.DateTimeField(auto_now=True)),
                ('version', models.IntegerField(default=1)),
                ('uid', models.CharField(blank=True, help_text="Local readable identifier, auto-generated per (workspace, item_type) as 'DOC-NNN' (issue #932 / Plan G G1.1). The concept's source identity ('doc:<repo>:<path>') belongs to the F5 SourceBinding, not here.", max_length=64, null=True)),
                ('title', models.CharField(max_length=255)),
                ('kind', models.CharField(choices=[('Spec', 'Spec'), ('Plan', 'Plan'), ('AuditReport', 'Audit Report'), ('Review', 'Review'), ('Conclusion', 'Conclusion'), ('Concept', 'Concept'), ('Guide', 'Guide')], max_length=32)),
                ('description', models.TextField(blank=True, default='', help_text='Purpose/summary; not the document content.')),
                ('body', models.TextField(blank=True, default='', help_text='Markdown content of the document.')),
                ('doc_date', models.DateField(blank=True, help_text='Document date (e.g. derived from a source file name).', null=True)),
                ('frozen_at', models.DateTimeField(blank=True, help_text="Set when the document enters 'Freigegeben' (freeze F-1).", null=True)),
                ('frozen_fields', models.JSONField(blank=True, default=list, help_text='Names of the fields frozen by the approval (freeze F-2).')),
                ('artifact', models.OneToOneField(help_text='Backing Artifact for TraceLinks, baselines and history.', on_delete=django.db.models.deletion.CASCADE, related_name='document', to='persistence.artifact')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('modified_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='%(class)s_set', to='persistence.tenant')),
                ('workspace', models.ForeignKey(help_text='Owning workspace; mirrored from artifact.workspace_id on save.', on_delete=django.db.models.deletion.CASCADE, related_name='documents', to='persistence.workspace')),
            ],
            options={
                'db_table': 'pl_document',
                'indexes': [models.Index(fields=['tenant', 'workspace', '-modified_at'], name='idx_doc_workspace_modified')],
                'constraints': [models.UniqueConstraint(condition=models.Q(models.Q(('uid', None), _negated=True), models.Q(('uid', ''), _negated=True)), fields=('workspace', 'uid'), name='uq_document_workspace_uid'), models.CheckConstraint(condition=models.Q(('kind__in', ['Spec', 'Plan', 'AuditReport', 'Review', 'Conclusion', 'Concept', 'Guide'])), name='ck_document_kind')],
            },
            bases=(persistence.models.ArtifactWorkspaceMirrorMixin, models.Model),
            managers=[
                ('objects', django.db.models.manager.Manager()),
                ('unscoped', django.db.models.manager.Manager()),
            ],
        ),
    ]
