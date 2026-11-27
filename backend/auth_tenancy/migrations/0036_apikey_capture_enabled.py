"""Add the ``capture`` right to API keys (ADR-032, decision D2).

``suggestion.capture`` needs a credential that may produce proposals from free
text without gaining the right to decide one. Rather than widening ``scope``
(which would also widen every other MCP tool) or reusing the agent-only producer
context (which would force every relay to hold two keys), the right is a single
orthogonal boolean: exactly one call consults it.

Default ``False``: no existing key changes behaviour, and a key must be
deliberately granted capture. ``at_api_key`` is RLS-enabled; the policy is
row-level, so a new column needs no policy change.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("auth_tenancy", "0035_apikey_tool_groups"),
    ]

    operations = [
        migrations.AddField(
            model_name="apikey",
            name="capture_enabled",
            field=models.BooleanField(default=False),
        ),
    ]
