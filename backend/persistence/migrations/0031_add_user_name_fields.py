# Migration 0031: Add first_name and last_name fields to User.
#
# REQ-006: Editable user profile — adds human-readable name fields to the
# application User model so the profile page can display and update them.
#
# Columns are added with a safe empty-string default; no data is modified and
# existing users remain valid. Reversible: RemoveField restores original schema.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("persistence", "0030_add_closed_status_testrun"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="first_name",
            field=models.CharField(blank=True, default="", max_length=150),
        ),
        migrations.AddField(
            model_name="user",
            name="last_name",
            field=models.CharField(blank=True, default="", max_length=150),
        ),
    ]
