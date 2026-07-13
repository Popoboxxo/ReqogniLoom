"""Add interface type choices to IcdVersion.interface_type.

REQ-006: Add structured interface type enumeration to support ICDS architecture.
Interface types classify the communication pattern: provides, requires, event-in,
event-out, data, control. Replaces free-text field with constrained choices.
"""
from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('icd', '0003_icdversion_embedding'),
    ]

    operations = [
        migrations.AlterField(
            model_name='icdversion',
            name='interface_type',
            field=models.CharField(
                max_length=32,
                blank=True,
                default='',
                choices=[
                    ('provides', 'Provides'),
                    ('requires', 'Requires'),
                    ('event-in', 'Event In'),
                    ('event-out', 'Event Out'),
                    ('data', 'Data'),
                    ('control', 'Control'),
                ],
                help_text='Interface type classification: provides, requires, event-in, event-out, data, control.',
            ),
        ),
    ]
