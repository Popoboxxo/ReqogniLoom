"""Add ``at_api_key.tool_groups`` for MCP manifest curation (Plan Phase D).

MCP-Modernisierung spec section 6.2: a non-empty ``tool_groups`` list narrows
the tool prefixes ``tools/list`` advertises to a key. It is pure catalogue
curation and deliberately NOT a security boundary — ``scope`` remains the
enforcement field.

Purely additive: ``JSONField(default=list, blank=True)`` is backed by a
non-null column with a Python-side default, so no existing row is rewritten and
no ``RunPython`` backfill is needed. ``at_api_key`` is RLS-enabled, but the
policy is row-level, so a new column needs no policy change.

Migration number: Plan Phase D reserved "0153", but that ordinal belongs to the
``persistence`` chain; ``ApiKey`` lives in ``auth_tenancy``, whose chain ends at
``0034`` — this is max+1 there.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("auth_tenancy", "0034_revoke_refresh_families_for_user"),
    ]

    operations = [
        migrations.AddField(
            model_name="apikey",
            name="tool_groups",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
