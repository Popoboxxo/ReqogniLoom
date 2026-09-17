"""Add DomainEventOutbox.claimed_at (SA-04).

The outbox poller used to hold a ``SELECT FOR UPDATE`` row lock across the whole
subscriber dispatch, which — now that WebhookDispatcher is actually registered
(commit ad1179f2) — means holding a row lock and an open transaction across an
outbound HTTP call that can block for ~65s per subscription.

``claimed_at`` replaces the row lock as the "this row is being worked on" marker
so the lock can be released before dispatch. Nullable with no default: existing
rows are unclaimed, which is exactly the correct initial state.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("application", "0017_alter_domaineventoutbox_event_type"),
    ]

    operations = [
        migrations.AddField(
            model_name="domaineventoutbox",
            name="claimed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
