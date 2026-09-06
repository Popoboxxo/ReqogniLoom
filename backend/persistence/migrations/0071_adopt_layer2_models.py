"""Adopt the seven Layer-2 domain models into persistence — **state only**.

Datenmodell-Konsolidierung Phase 2 / Milestone M2 (spec section 3). Paired with
``application/0024_release_layer2_models``, which drops the same seven models
from the ``application`` app's migration state.

**No SQL runs.** The seven tables — ``as_adr``, ``as_risk``, ``as_goal``,
``as_main_goal``, ``as_issue``, ``as_change_request`` and
``as_change_request_affected_item`` — were created by ``application/0006``..
``application/0023`` and are left exactly where they are, together with their
indexes, constraints and row-level-security policies (which are written against
the *table*, so an app-label change cannot disturb them). What changes is only
Django's model registry: the seven models are now owned by Layer 0.

The ``CreateModel`` bodies below are ``makemigrations`` output, wrapped verbatim
in ``SeparateDatabaseAndState`` with an empty ``database_operations``. Verify
with ``manage.py sqlmigrate persistence 0071_adopt_layer2_models``: any
``CREATE TABLE`` in that output means the wrapper is broken.

.. note:: ``ChangeRequest.baseline`` points at ``baseline.BaselineSnapshot``,
   so this Layer-0 migration depends on a Layer-1 one. That is a lazy string
   reference, not a Python import — ``persistence/models.py`` imports nothing
   from ``baseline``. It does mean no future ``baseline`` migration may depend
   on ``persistence/0071`` or later, or the graph acquires a cycle.
"""
import django.core.validators
import django.db.models.deletion
import django.db.models.manager
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        # Supplies BaselineSnapshot, the target of ChangeRequest.baseline.
        ("baseline", "0006_baseline_snapshot_rls"),
        ("persistence", "0070_drop_status_mirror_columns"),
        # The seven models must have reached their final field shape in the
        # `application` app before Layer 0 adopts that shape verbatim.
        ("application", "0023_crai_tenant_scoped"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            # Intentionally empty: the tables already exist.
            database_operations=[],
            state_operations=[
                migrations.CreateModel(
                    name='ChangeRequest',
                    fields=[
                        ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                        ('created_at', models.DateTimeField(auto_now_add=True)),
                        ('modified_at', models.DateTimeField(auto_now=True)),
                        ('version', models.IntegerField(default=1)),
                        ('workspace_id', models.UUIDField(db_index=True)),
                        ('title', models.CharField(max_length=255)),
                        ('description', models.TextField(blank=True)),
                        ('impact_assessment', models.TextField(blank=True, help_text='Assessment of the impact this change will have on the system.')),
                        ('change_reason', models.TextField(blank=True, help_text='Reason for the change request (required for submit and reject transitions).')),
                        ('requestor_id', models.UUIDField(blank=True, help_text='UUID of the user who created this change request.', null=True)),
                        ('assigned_reviewer_id', models.UUIDField(blank=True, help_text='UUID of the user assigned as CCB reviewer.', null=True)),
                        ('created_by_name', models.CharField(blank=True, db_column='created_by', max_length=255)),
                        ('updated_at', models.DateTimeField(auto_now=True)),
                        ('baseline', models.ForeignKey(blank=True, help_text='Configuration baseline this change request is evaluated / implemented against. Linked on approval when the workspace preset enables baselines.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='change_requests', to='baseline.baselinesnapshot')),
                        ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                        ('modified_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                        ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='%(class)s_set', to='persistence.tenant')),
                    ],
                    options={
                        'db_table': 'as_change_request',
                    },
                    managers=[
                        ('objects', django.db.models.manager.Manager()),
                        ('unscoped', django.db.models.manager.Manager()),
                    ],
                ),
                migrations.CreateModel(
                    name='ChangeRequestAffectedItem',
                    fields=[
                        ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                        ('created_at', models.DateTimeField(auto_now_add=True)),
                        ('modified_at', models.DateTimeField(auto_now=True)),
                        ('version', models.IntegerField(default=1)),
                        ('item_id', models.CharField(db_index=True, max_length=64)),
                        ('entity_type', models.CharField(default='item', max_length=32)),
                        ('version_before', models.IntegerField(blank=True, help_text='Artifact version when the item was attached to the CR.', null=True)),
                        ('version_after', models.IntegerField(blank=True, help_text='Artifact version when the CR was approved / implemented.', null=True)),
                        ('state_before', models.JSONField(default=None, help_text='Full curated entity state when attached (see state_capture).', null=True)),
                        ('state_after', models.JSONField(default=None, help_text='Full curated entity state at approval / implementation time.', null=True)),
                        ('updated_at', models.DateTimeField(auto_now=True)),
                        ('change_request', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='affected_items', to='persistence.changerequest')),
                        ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                        ('modified_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                        ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='%(class)s_set', to='persistence.tenant')),
                    ],
                    options={
                        'db_table': 'as_change_request_affected_item',
                    },
                    managers=[
                        ('objects', django.db.models.manager.Manager()),
                        ('unscoped', django.db.models.manager.Manager()),
                    ],
                ),
                migrations.CreateModel(
                    name='Goal',
                    fields=[
                        ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                        ('created_at', models.DateTimeField(auto_now_add=True)),
                        ('modified_at', models.DateTimeField(auto_now=True)),
                        ('version', models.IntegerField(default=1)),
                        ('workspace_id', models.UUIDField(db_index=True)),
                        ('lineage_id', models.UUIDField(db_index=True)),
                        ('sequence_number', models.PositiveIntegerField()),
                        ('title', models.CharField(max_length=255)),
                        ('description', models.TextField(blank=True, default='')),
                        ('created_by_name', models.CharField(blank=True, db_column='created_by', max_length=255)),
                        ('updated_at', models.DateTimeField(auto_now=True)),
                        ('artifact', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='goal', to='persistence.artifact')),
                        ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                        ('modified_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                        ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='%(class)s_set', to='persistence.tenant')),
                    ],
                    options={
                        'db_table': 'as_goal',
                        'ordering': ['lineage_id', 'sequence_number'],
                    },
                    managers=[
                        ('objects', django.db.models.manager.Manager()),
                        ('unscoped', django.db.models.manager.Manager()),
                    ],
                ),
                migrations.CreateModel(
                    name='Issue',
                    fields=[
                        ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                        ('created_at', models.DateTimeField(auto_now_add=True)),
                        ('modified_at', models.DateTimeField(auto_now=True)),
                        ('version', models.IntegerField(default=1)),
                        ('workspace_id', models.UUIDField(db_index=True)),
                        ('title', models.CharField(max_length=255)),
                        ('description', models.TextField(blank=True)),
                        ('severity', models.CharField(choices=[('critical', 'Critical'), ('high', 'High'), ('medium', 'Medium'), ('low', 'Low')], default='medium', max_length=16)),
                        ('category', models.CharField(choices=[('defect', 'Defect'), ('improvement', 'Improvement'), ('documentation', 'Documentation'), ('question', 'Question')], default='defect', max_length=32)),
                        ('assignee_id', models.UUIDField(blank=True, null=True)),
                        ('assignee_changed_date', models.DateTimeField(blank=True, null=True)),
                        ('due_date', models.DateTimeField(blank=True, null=True)),
                        ('tags', models.JSONField(default=list)),
                        ('uid', models.CharField(blank=True, help_text='Unique identifier (read-only, auto-generated)', max_length=64, null=True)),
                        ('created_by_name', models.CharField(blank=True, db_column='created_by', max_length=255)),
                        ('updated_at', models.DateTimeField(auto_now=True)),
                        ('artifact', models.OneToOneField(blank=True, help_text='REQ-L2-TE-020: backing Artifact for TraceLink support.', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='issue', to='persistence.artifact')),
                        ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                        ('modified_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                        ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='%(class)s_set', to='persistence.tenant')),
                    ],
                    options={
                        'db_table': 'as_issue',
                    },
                    managers=[
                        ('objects', django.db.models.manager.Manager()),
                        ('unscoped', django.db.models.manager.Manager()),
                    ],
                ),
                migrations.CreateModel(
                    name='MainGoal',
                    fields=[
                        ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                        ('created_at', models.DateTimeField(auto_now_add=True)),
                        ('modified_at', models.DateTimeField(auto_now=True)),
                        ('version', models.IntegerField(default=1)),
                        ('workspace_id', models.UUIDField(db_index=True)),
                        ('sequence_number', models.PositiveIntegerField()),
                        ('content', models.TextField()),
                        ('source', models.CharField(choices=[('ai', 'AI'), ('manual', 'Manual')], max_length=20)),
                        ('generated_from_goal_ids', models.JSONField(blank=True, default=list)),
                        ('created_by_name', models.CharField(blank=True, db_column='created_by', max_length=255)),
                        ('updated_at', models.DateTimeField(auto_now=True)),
                        ('artifact', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='main_goal', to='persistence.artifact')),
                        ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                        ('modified_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                        ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='%(class)s_set', to='persistence.tenant')),
                    ],
                    options={
                        'db_table': 'as_main_goal',
                        'ordering': ['sequence_number'],
                    },
                    managers=[
                        ('objects', django.db.models.manager.Manager()),
                        ('unscoped', django.db.models.manager.Manager()),
                    ],
                ),
                migrations.CreateModel(
                    name='Risk',
                    fields=[
                        ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                        ('created_at', models.DateTimeField(auto_now_add=True)),
                        ('modified_at', models.DateTimeField(auto_now=True)),
                        ('version', models.IntegerField(default=1)),
                        ('workspace_id', models.UUIDField(db_index=True)),
                        ('title', models.CharField(max_length=255)),
                        ('description', models.TextField(blank=True)),
                        ('category', models.CharField(choices=[('technical', 'Technical'), ('operational', 'Operational'), ('organizational', 'Organizational'), ('business', 'Business')], default='technical', max_length=32)),
                        ('probability', models.CharField(choices=[('low', 'Low (1)'), ('medium', 'Medium (2)'), ('high', 'High (3)')], default='low', max_length=16)),
                        ('impact', models.CharField(choices=[('low', 'Low (1)'), ('medium', 'Medium (2)'), ('high', 'High (3)')], default='low', max_length=16)),
                        ('risk_score', models.IntegerField(default=1)),
                        ('severity', models.CharField(choices=[('low', 'Low'), ('medium', 'Medium'), ('high', 'High')], default='low', max_length=16)),
                        ('owner', models.CharField(blank=True, max_length=255)),
                        ('detection', models.PositiveSmallIntegerField(default=5, help_text='REQ-L1-029: FMEA detection score (1=easy .. 10=impossible).', validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(10)])),
                        ('mitigation_strategy', models.TextField(blank=True)),
                        ('uid', models.CharField(blank=True, help_text='Unique identifier (read-only, auto-generated)', max_length=64, null=True)),
                        ('created_by_name', models.CharField(blank=True, db_column='created_by', max_length=255)),
                        ('updated_at', models.DateTimeField(auto_now=True)),
                        ('artifact', models.OneToOneField(blank=True, help_text='REQ-L2-TE-020: backing Artifact for TraceLink support.', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='risk', to='persistence.artifact')),
                        ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                        ('modified_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                        ('owner_user', models.ForeignKey(blank=True, help_text='REQ-L1-029: assigned risk owner (User FK).', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='owned_risks', to=settings.AUTH_USER_MODEL)),
                        ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='%(class)s_set', to='persistence.tenant')),
                    ],
                    options={
                        'db_table': 'as_risk',
                    },
                    managers=[
                        ('objects', django.db.models.manager.Manager()),
                        ('unscoped', django.db.models.manager.Manager()),
                    ],
                ),
                migrations.CreateModel(
                    name='Adr',
                    fields=[
                        ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                        ('created_at', models.DateTimeField(auto_now_add=True)),
                        ('modified_at', models.DateTimeField(auto_now=True)),
                        ('version', models.IntegerField(default=1)),
                        ('workspace_id', models.UUIDField(db_index=True)),
                        ('title', models.CharField(max_length=200)),
                        ('description', models.TextField(max_length=10000)),
                        ('context', models.TextField(blank=True, max_length=5000)),
                        ('decision', models.TextField(blank=True, max_length=5000)),
                        ('consequences', models.TextField(blank=True, max_length=5000)),
                        ('uid', models.CharField(blank=True, help_text='Unique identifier (read-only, auto-generated)', max_length=64, null=True)),
                        ('created_by_name', models.CharField(blank=True, db_column='created_by', max_length=255)),
                        ('updated_at', models.DateTimeField(auto_now=True)),
                        ('artifact', models.OneToOneField(blank=True, help_text='REQ-L2-TE-020: backing Artifact for TraceLink support.', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='adr', to='persistence.artifact')),
                        ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                        ('modified_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                        ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='%(class)s_set', to='persistence.tenant')),
                    ],
                    options={
                        'db_table': 'as_adr',
                        'indexes': [models.Index(fields=['tenant', 'workspace_id'], name='idx_adr_tenant_ws'), models.Index(fields=['uid'], name='idx_adr_uid_btree')],
                    },
                    managers=[
                        ('objects', django.db.models.manager.Manager()),
                        ('unscoped', django.db.models.manager.Manager()),
                    ],
                ),
                migrations.AddIndex(
                    model_name='changerequest',
                    index=models.Index(fields=['tenant', 'workspace_id'], name='idx_cr_tenant_ws'),
                ),
                migrations.AddIndex(
                    model_name='changerequest',
                    index=models.Index(fields=['workspace_id', 'requestor_id'], name='idx_cr_ws_requestor'),
                ),
                migrations.AddIndex(
                    model_name='changerequestaffecteditem',
                    index=models.Index(fields=['change_request', 'item_id'], name='idx_cr_affected_cr_item'),
                ),
                migrations.AddIndex(
                    model_name='changerequestaffecteditem',
                    index=models.Index(fields=['tenant'], name='idx_cr_affected_tenant'),
                ),
                migrations.AddConstraint(
                    model_name='changerequestaffecteditem',
                    constraint=models.UniqueConstraint(fields=('change_request', 'item_id'), name='uq_cr_affected_item'),
                ),
                migrations.AddIndex(
                    model_name='goal',
                    index=models.Index(fields=['workspace_id', 'lineage_id'], name='as_goal_workspa_9319d2_idx'),
                ),
                migrations.AddIndex(
                    model_name='issue',
                    index=models.Index(fields=['workspace_id', 'severity'], name='idx_issue_ws_severity'),
                ),
                migrations.AddIndex(
                    model_name='issue',
                    index=models.Index(fields=['tenant', 'workspace_id'], name='idx_issue_tenant_ws'),
                ),
                migrations.AddIndex(
                    model_name='issue',
                    index=models.Index(fields=['workspace_id', 'assignee_id'], name='idx_issue_ws_assignee'),
                ),
                migrations.AddIndex(
                    model_name='issue',
                    index=models.Index(fields=['uid'], name='idx_issue_uid_btree'),
                ),
                migrations.AddIndex(
                    model_name='maingoal',
                    index=models.Index(fields=['workspace_id', 'sequence_number'], name='as_main_goa_workspa_548196_idx'),
                ),
                migrations.AddConstraint(
                    model_name='maingoal',
                    constraint=models.UniqueConstraint(fields=('workspace_id', 'sequence_number'), name='uq_main_goal_workspace_sequence'),
                ),
                migrations.AddIndex(
                    model_name='risk',
                    index=models.Index(fields=['tenant', 'workspace_id'], name='idx_risk_tenant_ws'),
                ),
                migrations.AddIndex(
                    model_name='risk',
                    index=models.Index(fields=['workspace_id', 'severity'], name='idx_risk_ws_severity'),
                ),
                migrations.AddIndex(
                    model_name='risk',
                    index=models.Index(fields=['workspace_id', 'risk_score'], name='idx_risk_ws_score'),
                ),
                migrations.AddIndex(
                    model_name='risk',
                    index=models.Index(fields=['uid'], name='idx_risk_uid_btree'),
                ),
    
            ],
        ),
    ]
