"""
Migration 0002: WebhookSubscription and WebhookDeliveryLog tables.

COMP-AS-011 WebhookDispatcher (REQ-L1-024, REQ-L3-WHOOK-002/008/009).
"""
import uuid

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("application", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="WebhookSubscription",
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
                ("workspace_id", models.UUIDField(db_index=True)),
                ("event_types", models.CharField(default="", max_length=512)),
                ("url", models.URLField(max_length=2048)),
                ("secret", models.CharField(blank=True, max_length=255)),
                ("enabled", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "db_table": "as_webhook_subscription",
            },
        ),
        migrations.CreateModel(
            name="WebhookDeliveryLog",
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
                    "subscription",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="delivery_logs",
                        to="application.webhooksubscription",
                    ),
                ),
                ("event_id", models.UUIDField(db_index=True)),
                ("event_type", models.CharField(max_length=64)),
                ("attempt", models.IntegerField(default=1)),
                ("status_code", models.IntegerField(blank=True, null=True)),
                ("success", models.BooleanField(default=False)),
                ("error_message", models.TextField(blank=True)),
                ("dispatched_at", models.DateTimeField(auto_now_add=True)),
                ("is_dead_letter", models.BooleanField(default=False)),
            ],
            options={
                "db_table": "as_webhook_delivery_log",
            },
        ),
        migrations.AddIndex(
            model_name="webhooksubscription",
            index=models.Index(
                fields=["workspace_id", "enabled"],
                name="idx_webhook_ws_enabled",
            ),
        ),
        migrations.AddIndex(
            model_name="webhookdeliverylog",
            index=models.Index(
                fields=["subscription", "event_id"],
                name="idx_webhook_log_sub_event",
            ),
        ),
    ]
