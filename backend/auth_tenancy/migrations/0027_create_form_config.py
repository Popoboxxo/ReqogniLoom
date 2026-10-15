"""auth_tenancy — create-dialog form definition (Issue #1263).

Adds the two storage slots of the configurable "new artifact" dialog, reusing
the tables the #1257 tree-display configuration already established:

* ``at_user_display_preference.create_form_fields`` — the personal level
  (self-service, ``ctx.user_id`` is the boundary), a JSON map
  ``{item_type: [{"field_key", "visible", "required", "order", "default"}, …]}``;
* ``at_tree_display_config.create_form_json`` — the workspace and global levels,
  the same JSON map shape.

``NULL`` (personal) / a missing entry (administrative) means "inherit": the
resolution walks ``user > workspace > global > definition-derived default`` and
the default is exactly the pre-#1263 rendering, so an unconfigured tenant is
byte-for-byte unchanged.

No new table and no RLS change: both columns live on already tenant-scoped
tables and are covered by their existing RLS policies
(``0020_user_display_preference_rls`` / ``0026_treedisplayconfig_rls``,
REQ-L2-PL-010).

Authored manually for human review (mirrors ``0024_…tree_display_fields``); no
``makemigrations``/``migrate`` run.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("auth_tenancy", "0026_treedisplayconfig_rls"),
    ]

    operations = [
        migrations.AddField(
            model_name="userdisplaypreference",
            name="create_form_fields",
            field=models.JSONField(blank=True, default=None, null=True),
        ),
        migrations.AddField(
            model_name="treedisplayconfig",
            name="create_form_json",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
