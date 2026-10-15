"""auth_tenancy — personal tree-display configuration (Issue #1257).

Adds ``at_user_display_preference.tree_display_fields``: a nullable JSON map
``{item_type: [{"key": …, "width": …}, …]}`` holding the caller's own selection
of the fields the navigation tree renders. ``NULL`` means "no personal
selection" — resolution falls through to the workspace level, then the global
level (``at_tree_display_config``), then the built-in default.

No new table and no RLS change: the column lives on the already tenant-scoped
``at_user_display_preference`` table and is covered by the RLS policy created in
``0020_user_display_preference_rls`` (REQ-L2-PL-010).
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("auth_tenancy", "0023_userdisplaypreference_visible_metrics"),
    ]

    operations = [
        migrations.AddField(
            model_name="userdisplaypreference",
            name="tree_display_fields",
            field=models.JSONField(blank=True, default=None, null=True),
        ),
    ]
