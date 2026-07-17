"""Add the V-model hierarchy ``level`` field to Requirement (K3).

Promotes the L0-L4 requirement hierarchy from a naming convention to an
explicit, queryable column. Additive and backward-compatible: the column is
nullable with no default, so every existing row keeps ``level = NULL``. No
backfill — the level must be assigned deliberately going forward (a naming
convention cannot be mapped to a level reliably without human intent).

Reversible: reverse drops the column (RemoveField), restoring the prior schema
exactly. No data loss on reverse because the column carried no pre-existing data.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('persistence', '0039_migrate_artifact_parent_deprecation'),
    ]

    operations = [
        migrations.AddField(
            model_name='requirement',
            name='level',
            field=models.PositiveSmallIntegerField(
                blank=True,
                null=True,
                choices=[
                    (0, 'L0 System'),
                    (1, 'L1 Subsystem'),
                    (2, 'L2 Component'),
                    (3, 'L3 Part'),
                    (4, 'L4 Material'),
                ],
                help_text=(
                    'K3: V-model hierarchy level (0=System, 1=Subsystem, '
                    '2=Component, 3=Part, 4=Material). NULL until assigned '
                    'explicitly.'
                ),
            ),
        ),
    ]
