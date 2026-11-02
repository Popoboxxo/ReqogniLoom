# Plan F F3-T1 (#1374): the state-bearing work node inside a document.
#
# `WorkItem` owns one backing `pl_artifact` row (like Requirement/Document),
# carries a per-workspace partial uid uniqueness (`uq_work_item_workspace_uid`,
# G1.3/#1402), DB mirrors of its kind choices (`ck_work_item_kind`) and of the
# 0-100 progress contract (`ck_work_item_progress_range`). `document` is
# mandatory and PROTECTed (concept E11/O7). There is deliberately no
# state/status column: the workflow state lives in `we_item_state` and
# soft-delete lives on `pl_artifact.lifecycle_status` (Plan G G1.5 V1).
#
# The tenant RLS policy ships in the very next migration
# (`0126_work_item_rls_policy`) in the same release (KA-F-13).
import django.db.models.deletion
import django.db.models.manager
import persistence.models
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('persistence', '0124_document_rls_policy'),
    ]

    operations = [
        migrations.CreateModel(
            name='WorkItem',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('modified_at', models.DateTimeField(auto_now=True)),
                ('version', models.IntegerField(default=1)),
                ('uid', models.CharField(blank=True, help_text="Local readable identifier, auto-generated per (workspace, item_type) as 'WI-NNN' (issue #932 / Plan G G1.1). The concept's source identity ('item:<document-uid>:<selector>') belongs to the F5 SourceBinding, not here.", max_length=64, null=True)),
                ('kind', models.CharField(choices=[('Phase', 'Phase'), ('Step', 'Step'), ('Milestone', 'Milestone'), ('OpenPoint', 'Open Point'), ('Checkpoint', 'Checkpoint')], max_length=32)),
                ('ordinal', models.IntegerField(default=0, help_text="Position inside the document. Replaces the rejected 'precedes' link type; resume sorts by (ordinal, id).")),
                ('title', models.CharField(max_length=255)),
                ('body', models.TextField(blank=True, default='', help_text='Markdown of the section (used by Step/Checkpoint).')),
                ('progress', models.PositiveSmallIntegerField(blank=True, help_text='0-100, for Phase/Milestone. DB-checked by ck_work_item_progress_range.', null=True)),
                ('blocked_reason', models.TextField(blank=True, default='', help_text="Why the item is blocked (mandatory while the workflow state is 'blocked', enforced by the service) or why it was dropped.")),
                ('next_action', models.CharField(blank=True, default='', help_text="Resume hint for agents ('where to continue').", max_length=255)),
                ('last_activity_at', models.DateTimeField(blank=True, help_text='Heartbeat (A-3); DOC-P5 reports stale in_progress items.', null=True)),
                ('last_actor', models.CharField(blank=True, default='', help_text='Agent/human identifier of the last action (A-1).', max_length=128)),
                ('evidence_ref', models.CharField(blank=True, default='', help_text='Evidence (commit, test run, artifact id).', max_length=512)),
                ('approved_by', models.CharField(blank=True, default='', help_text='Human approval identity; only the extended preset sets this.', max_length=128)),
                ('approved_at', models.DateTimeField(blank=True, help_text='Human approval timestamp; only the extended preset sets this.', null=True)),
                ('due_date', models.DateTimeField(blank=True, null=True)),
                ('exit_criteria', models.TextField(blank=True, default='', help_text='Definition of done for this item (gates, concept §5.4).')),
                ('artifact', models.OneToOneField(help_text='Backing Artifact for TraceLinks, baselines and history.', on_delete=django.db.models.deletion.CASCADE, related_name='work_item', to='persistence.artifact')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('document', models.ForeignKey(help_text='Owning document (mandatory, concept E11/O7). PROTECT only bites on a hard delete; the regular path is the Artifact soft delete.', on_delete=django.db.models.deletion.PROTECT, related_name='work_items', to='persistence.document')),
                ('modified_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='%(class)s_set', to='persistence.tenant')),
                ('workspace', models.ForeignKey(help_text='Owning workspace; mirrored from artifact.workspace_id on save.', on_delete=django.db.models.deletion.CASCADE, related_name='workspace_work_items', to='persistence.workspace')),
            ],
            options={
                'db_table': 'pl_work_item',
                'indexes': [models.Index(fields=['tenant', 'document', 'ordinal'], name='idx_workitem_document_ordinal')],
                'constraints': [models.UniqueConstraint(condition=models.Q(models.Q(('uid', None), _negated=True), models.Q(('uid', ''), _negated=True)), fields=('workspace', 'uid'), name='uq_work_item_workspace_uid'), models.CheckConstraint(condition=models.Q(('kind__in', ['Phase', 'Step', 'Milestone', 'OpenPoint', 'Checkpoint'])), name='ck_work_item_kind'), models.CheckConstraint(condition=models.Q(('progress__isnull', True), models.Q(('progress__gte', 0), ('progress__lte', 100)), _connector='OR'), name='ck_work_item_progress_range')],
            },
            bases=(persistence.models.ArtifactWorkspaceMirrorMixin, models.Model),
            managers=[
                ('objects', django.db.models.manager.Manager()),
                ('unscoped', django.db.models.manager.Manager()),
            ],
        ),
    ]
