"""Add semantic uid field + BTree index to Adr, Risk and Issue.

REQ-L2-RF-025 AC3: uid enables stable, prominent identification of artifacts.
Mirrors the existing uid rollout on Requirement / ArchitectureElement /
StakeholderNeed. No backfill: existing rows keep uid=NULL (same as the
established pattern); uid is read-only / auto-generated for new rows.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('application', '0004_alter_domaineventoutbox_event_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='adr',
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
            model_name='risk',
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
            model_name='issue',
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
            model_name='adr',
            index=models.Index(fields=['uid'], name='idx_adr_uid_btree'),
        ),
        migrations.AddIndex(
            model_name='risk',
            index=models.Index(fields=['uid'], name='idx_risk_uid_btree'),
        ),
        migrations.AddIndex(
            model_name='issue',
            index=models.Index(fields=['uid'], name='idx_issue_uid_btree'),
        ),
    ]
