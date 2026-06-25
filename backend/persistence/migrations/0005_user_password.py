"""
COMP-PL-004 SchemaMigrationEngine — add ``User.password`` (REQ-L1-010).

Password-login extension (ARCH-L1-011 AuthAndTenancy): adds a salted password
hash column to ``pl_user``. Stores only the Django-hasher-formatted hash, never
plaintext (see ``persistence.models.User.set_password``).

Hand-authored to match ``persistence/models.py``; ``makemigrations --check`` must
report no changes against this migration.
"""
from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("persistence", "0004_alter_architectureelement_options_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="password",
            field=models.CharField(blank=True, default="", max_length=128),
        ),
    ]
