"""auth_tenancy — per-user SE-statistics widget selection (Issue #1265).

Adds ``at_user_display_preference.visible_metrics``: a nullable JSON list of
metric keys (see ``se_metrics.registry``) holding the caller's own statistics
widget selection and order. ``NULL`` means "no explicit selection"; the client
then renders the registry's ``default_visible`` set, so an existing row (or a
missing one) keeps the historical dashboard unchanged.

No new table and no RLS change: the column lives on the already tenant-scoped
``at_user_display_preference`` table and is covered by the RLS policy created
in ``0020_user_display_preference_rls`` (REQ-L2-PL-010).
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("auth_tenancy", "0022_rls_hard_enforcement_policy"),
    ]

    operations = [
        migrations.AddField(
            model_name="userdisplaypreference",
            name="visible_metrics",
            field=models.JSONField(blank=True, default=None, null=True),
        ),
    ]
