"""
Initial migration for ARCH-L1-004 ApplicationService.

Creates Transactional Outbox and Dead-Letter Queue tables for
COMP-AS-016 DomainEventBus (REQ-L2-AS-029).
"""
import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="DomainEventOutbox",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "event_id",
                    models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
                ),
                ("event_type", models.CharField(max_length=64)),
                ("workspace_id", models.UUIDField(db_index=True)),
                ("entity_id", models.UUIDField()),
                ("payload", models.JSONField(default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("published_at", models.DateTimeField(blank=True, null=True)),
                ("published", models.BooleanField(default=False)),
                ("retry_count", models.IntegerField(default=0)),
            ],
            options={
                "db_table": "as_domain_event_outbox",
                "ordering": ["created_at"],
            },
        ),
        migrations.CreateModel(
            name="DomainEventDLQ",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("event_id", models.UUIDField(unique=True)),
                ("event_type", models.CharField(max_length=64)),
                ("workspace_id", models.UUIDField()),
                ("entity_id", models.UUIDField()),
                ("payload", models.JSONField(default=dict)),
                ("error_message", models.TextField(blank=True)),
                ("retry_count", models.IntegerField(default=0)),
                ("moved_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "db_table": "as_domain_event_dlq",
            },
        ),
        migrations.AddIndex(
            model_name="domaineventoutbox",
            index=models.Index(
                fields=["published", "created_at"],
                name="idx_outbox_unpublished",
            ),
        ),
        migrations.AddIndex(
            model_name="domaineventoutbox",
            index=models.Index(
                fields=["workspace_id", "created_at"],
                name="idx_outbox_ws",
            ),
        ),
    ]
