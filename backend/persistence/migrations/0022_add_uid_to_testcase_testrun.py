"""Add semantic uid field + BTree index to TestCase and TestRun.

REQ-L2-RF-025 AC3: uid enables stable, prominent identification of artifacts.
Mirrors the existing uid rollout on Requirement / ArchitectureElement /
StakeholderNeed. No backfill: existing rows keep uid=NULL (same as the
established pattern); uid is read-only / auto-generated for new rows.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('persistence', '0021_workspace_ai_prompts'),
    ]

    operations = [
        migrations.AddField(
            model_name='testcase',
            name='uid',
            field=models.CharField(
                max_length=64,
                null=True,
                blank=True,
                unique=False,
                help_text='Unique identifier (read-only, auto-generated)',
            ),
        ),
        migrations.AddField(
            model_name='testrun',
            name='uid',
            field=models.CharField(
                max_length=64,
                null=True,
                blank=True,
                unique=False,
                help_text='Unique identifier (read-only, auto-generated)',
            ),
        ),
        migrations.AddIndex(
            model_name='testcase',
            index=models.Index(fields=['uid'], name='idx_testcase_uid_btree'),
        ),
        migrations.AddIndex(
            model_name='testrun',
            index=models.Index(fields=['uid'], name='idx_test_run_uid_btree'),
        ),
    ]
