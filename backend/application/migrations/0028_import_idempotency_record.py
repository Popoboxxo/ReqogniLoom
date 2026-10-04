# ADR-014 §3 (INT-01 import contract v2): replay store for the optional
# ``Idempotency-Key`` header. Scope (tenant, user, endpoint, key); TTL 24 h;
# only terminal successes are cached.
import django.utils.timezone
import uuid

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("application", "0027_alter_domaineventoutbox_event_type"),
    ]

    operations = [
        migrations.CreateModel(
            name="ImportIdempotencyRecord",
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
                ("tenant_id", models.UUIDField(db_index=True)),
                ("user_id", models.UUIDField(db_index=True)),
                ("endpoint", models.CharField(max_length=64)),
                ("key", models.CharField(max_length=255)),
                ("request_fingerprint", models.CharField(max_length=64)),
                (
                    "state",
                    models.CharField(
                        choices=[
                            ("in_flight", "In flight"),
                            ("succeeded", "Succeeded"),
                        ],
                        default="in_flight",
                        max_length=16,
                    ),
                ),
                ("status_code", models.IntegerField(blank=True, null=True)),
                ("response_body", models.JSONField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "claimed_at",
                    models.DateTimeField(default=django.utils.timezone.now),
                ),
                ("expires_at", models.DateTimeField(db_index=True)),
            ],
            options={
                "db_table": "as_import_idempotency",
                "indexes": [
                    models.Index(
                        fields=["expires_at"], name="idx_import_idem_expires"
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=["tenant_id", "user_id", "endpoint", "key"],
                        name="uniq_import_idem_scope_key",
                    ),
                ],
            },
        ),
    ]
