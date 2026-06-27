# Generated manually for REQ-L1-042 (Workspace Lifecycle Management).

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('persistence', '0008_add_staff_flags_to_user'),
    ]

    operations = [
        migrations.AddField(
            model_name='workspace',
            name='is_active',
            field=models.BooleanField(
                default=True,
                help_text='Soft-delete flag. False = workspace is closed (REQ-L1-042).',
            ),
        ),
        migrations.AddField(
            model_name='workspace',
            name='closed_at',
            field=models.DateTimeField(
                blank=True,
                help_text='Timestamp when the workspace was closed.',
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='workspace',
            name='closed_by',
            field=models.ForeignKey(
                blank=True,
                help_text='User who closed this workspace.',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='+',
                to='persistence.user',
            ),
        ),
    ]
