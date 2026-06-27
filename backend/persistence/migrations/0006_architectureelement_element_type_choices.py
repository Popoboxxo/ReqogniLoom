# Generated manually for element_type TextChoices enum

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('persistence', '0005_user_password'),
    ]

    operations = [
        migrations.AlterField(
            model_name='architectureelement',
            name='element_type',
            field=models.CharField(
                blank=True,
                choices=[
                    ('component', 'Component'),
                    ('interface', 'Interface'),
                    ('subsystem', 'Subsystem'),
                    ('layer', 'Layer'),
                    ('module', 'Module'),
                ],
                default='component',
                max_length=64,
            ),
        ),
    ]
