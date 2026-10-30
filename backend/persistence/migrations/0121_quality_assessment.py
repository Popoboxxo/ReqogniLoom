# WP B5-T1 (#378): the append-only quality-assessment table.
#
# One row per assessment run for any artifact type; index names are explicit
# (``idx_qa_*``) and follow the access patterns of the read paths:
# latest verdict per entity, the workspace history feed, and the
# content-hash reuse lookup. Reverse is ``DeleteModel`` (implicit), which is
# safe because nothing else references this table yet.
#
# The tenant RLS policy ships in the very next migration
# (``0122_quality_assessment_rls_policy``) in the same release (D-RLS).
import django.core.validators
import django.db.models.deletion
import django.db.models.manager
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('persistence', '0120_requirement_list_index'),
    ]

    operations = [
        migrations.CreateModel(
            name='QualityAssessment',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('modified_at', models.DateTimeField(auto_now=True)),
                ('version', models.IntegerField(default=1)),
                ('entity_type', models.CharField(help_text="Artifact type of the assessed entity, e.g. 'Requirement'.", max_length=64)),
                ('entity_id', models.UUIDField(help_text='Id of the assessed entity (not its backing artifact id).')),
                ('score', models.FloatField(help_text='Overall quality score on the 0.0-1.0 scale (UI shows percent).', validators=[django.core.validators.MinValueValidator(0.0), django.core.validators.MaxValueValidator(1.0)])),
                ('reasoning', models.TextField(blank=True, default='', help_text='LLM rationale for the score; empty for a failed run.')),
                ('suggestions', models.JSONField(blank=True, default=list, help_text='Free-text improvement hints produced by the run.')),
                ('criteria', models.JSONField(blank=True, default=dict, help_text='Per-criterion sub-scores (name -> 0.0-1.0).')),
                ('content_hash', models.CharField(db_index=True, help_text='Hash of the assessed content, pinning what the verdict refers to.', max_length=64)),
                ('entity_version', models.IntegerField(blank=True, help_text='Optimistic-lock version of the entity at assessment time.', null=True)),
                ('prompt_slot', models.CharField(help_text="Prompt template slot used for the run (e.g. 'quality_requirement').", max_length=100)),
                ('prompt_scope', models.CharField(choices=[('workspace', 'Workspace'), ('global', 'Global'), ('factory', 'Factory')], max_length=16)),
                ('prompt_version', models.IntegerField(blank=True, help_text='Version of the resolved prompt template; NULL when unknown.', null=True)),
                ('provider', models.CharField(help_text='LLM provider key.', max_length=64)),
                ('model', models.CharField(help_text='Provider model identifier.', max_length=128)),
                ('token_usage', models.IntegerField(blank=True, help_text='Reported token count; NULL when the provider does not report it.', null=True)),
                ('trigger', models.CharField(choices=[('manual', 'Manual'), ('mcp', 'MCP')], max_length=16)),
                ('triggered_by', models.CharField(help_text='Principal that started the run (user id or API-key label).', max_length=255)),
                ('status', models.CharField(choices=[('ok', 'OK'), ('failed', 'Failed')], max_length=16)),
                ('error_code', models.CharField(blank=True, default='', help_text='Provider error class for a failed run; empty on success.', max_length=64)),
                ('artifact', models.ForeignKey(blank=True, help_text='Backing artifact when one exists; SET_NULL keeps the history.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='quality_assessments', to='persistence.artifact')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('modified_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='%(class)s_set', to='persistence.tenant')),
                ('workspace', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='quality_assessments', to='persistence.workspace')),
            ],
            options={
                'db_table': 'pl_quality_assessment',
                # DB-level mirrors of the TextChoices and score validator;
                # ``entity_type`` stays unconstrained on purpose (loose column).
                'constraints': [
                    models.CheckConstraint(condition=models.Q(('score__gte', 0.0), ('score__lte', 1.0)), name='ck_quality_assessment_score_range'),
                    models.CheckConstraint(condition=models.Q(('prompt_scope__in', ['workspace', 'global', 'factory'])), name='ck_quality_assessment_prompt_scope'),
                    models.CheckConstraint(condition=models.Q(('trigger__in', ['manual', 'mcp'])), name='ck_quality_assessment_trigger'),
                    models.CheckConstraint(condition=models.Q(('status__in', ['ok', 'failed'])), name='ck_quality_assessment_status'),
                ],
                'indexes': [models.Index(fields=['tenant', 'entity_type', 'entity_id', '-created_at'], name='idx_qa_entity_created'), models.Index(fields=['tenant', 'workspace', '-created_at'], name='idx_qa_workspace_created'), models.Index(fields=['tenant', 'content_hash'], name='idx_qa_tenant_hash')],
            },
            managers=[
                ('objects', django.db.models.manager.Manager()),
                ('unscoped', django.db.models.manager.Manager()),
            ],
        ),
    ]
