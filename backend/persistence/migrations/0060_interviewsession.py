# Generated migration for InterviewSession model
# Interview-Management-Engine spec §3.2

import uuid
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('persistence', '0059_testcase_status_lowercase'),
    ]

    operations = [
        migrations.CreateModel(
            name='InterviewSession',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('modified_at', models.DateTimeField(auto_now=True)),
                ('version', models.IntegerField(default=1)),
                ('artifact_type', models.CharField(help_text='Which interview protocol applies (PascalCase, matches Artifact.artifact_type).', max_length=64)),
                ('status', models.CharField(choices=[('in_progress', 'In Progress'), ('completed', 'Completed'), ('abandoned', 'Abandoned')], default='in_progress', max_length=16)),
                ('collected_fields', models.JSONField(blank=True, default=dict)),
                ('grounding_snapshot', models.JSONField(blank=True, default=dict)),
                ('resulting_artifact_ids', models.JSONField(blank=True, default=list)),
                ('transcript', models.JSONField(blank=True, default=list, help_text='List of {role, text, timestamp}. Only chat-driving clients (Spec 3) write to this; form clients (Spec 2) leave it empty.')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='persistence.user')),
                ('modified_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='persistence.user')),
                ('target_artifact', models.ForeignKey(blank=True, help_text='Set once grounding identifies an existing artifact to adjust instead of creating a new one.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='interview_sessions', to='persistence.artifact')),
                ('tenant', models.ForeignKey(db_index=True, on_delete=django.db.models.deletion.PROTECT, related_name='%(class)s_set', to='persistence.tenant')),
                ('workspace', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='interview_sessions', to='persistence.workspace')),
            ],
            options={
                'db_table': 'pl_interview_session',
                'abstract': False,
            },
        ),
        migrations.AddIndex(
            model_name='interviewsession',
            index=models.Index(fields=['workspace', 'status'], name='pl_interview_session_workspace_id_status_idx'),
        ),
    ]
