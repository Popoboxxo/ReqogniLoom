# Generated for issue #125.
#
# user.create (mcp_server/tools/users.py) pre-checks uniqueness with
# `username__iexact`, but the DB constraint on `username` was case-sensitive
# (`unique=True`), so two users differing only by case could be created
# concurrently (TOCTOU race between the `.exists()` check and `.create()`).
# This adds a case-insensitive functional unique index so the DB enforces
# the same semantics the application already assumes.
#
# Verified against the current database (2026-07-29): 0 case-insensitive
# username collisions exist, so this constraint can be added directly
# without a prior deduplication step.

from django.db import migrations, models
from django.db.models.functions import Lower


class Migration(migrations.Migration):

    dependencies = [
        ("persistence", "0050_requirement_type_check_constraint"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="user",
            constraint=models.UniqueConstraint(
                Lower("username"),
                name="uq_user_username_ci",
            ),
        ),
    ]
