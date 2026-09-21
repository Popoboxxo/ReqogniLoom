# AI Long-Term Memory — admin-configurable write ratelimit for ``memory.write``
# (RFC #1002, PR B).
#
# Plain ``AddField``: ``SystemMemorySettings`` is deliberately NOT a
# ``TenantScopedModel`` (see its model docstring), so no RLS policy applies to
# the table and none has to be extended here. NULL means "no override, env
# default wins"; the effective value is resolved in
# ``memory.ratelimit.resolve_write_rate_limit``.
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("memory", "0006_drop_legacy_memory_tables"),
    ]

    operations = [
        migrations.AddField(
            model_name="systemmemorysettings",
            name="memory_write_rate_limit_per_hour",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
    ]
