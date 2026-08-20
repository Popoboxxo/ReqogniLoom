# State-only migration: help_text update on InterviewSession.status,
# documenting it as a denormalized workflow-engine mirror (2026-08-20 UI-
# visibility fix). No DB-level change (help_text is not a column property).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('persistence', '0064_interview_session_artifact_backing'),
    ]

    operations = [
        migrations.AlterField(
            model_name='interviewsession',
            name='status',
            field=models.CharField(
                choices=[('in_progress', 'In Progress'), ('completed', 'Completed'), ('abandoned', 'Abandoned')],
                default='in_progress',
                help_text='Denormalized mirror of the workflow engine\'s current_state (see workflow.lifecycle_manager._STATUS_MIRROR_MODELS) — read-only projection, written only inside a workflow transition.',
                max_length=16,
            ),
        ),
    ]
