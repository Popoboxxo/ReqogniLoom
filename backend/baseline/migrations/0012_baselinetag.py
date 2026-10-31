"""F4.2 — ``bl_baseline_tag`` model (CreateModel; reverse = DeleteModel).

Plan F (2026-10-21), F4.2. Tags are metadata and get their own table because
the immutable snapshot cannot be UPDATEd (``bl_raise_immutable``); see
``BaselineTag`` in ``baseline/models.py`` and R-F4-3.

Generated with ``makemigrations``; the ``persistence`` dependency is the
cross-app requirement of the ``TenantScopedModel`` base (tenant/user FKs).
"""
import uuid

import django.db.models.deletion
import django.db.models.functions.text
import django.db.models.manager
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("baseline", "0011_baseline_admin_delete_trigger"),
        ("persistence", "0122_quality_assessment_rls_policy"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="BaselineTag",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("modified_at", models.DateTimeField(auto_now=True)),
                ("version", models.IntegerField(default=1)),
                ("workspace_id", models.UUIDField(db_index=True)),
                ("label", models.CharField(max_length=64)),
                ("baseline", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="tags", to="baseline.baselinesnapshot")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("modified_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="%(class)s_set", to="persistence.tenant")),
            ],
            options={
                "db_table": "bl_baseline_tag",
                "indexes": [models.Index(fields=["workspace_id", "label"], name="idx_bl_tag_ws_label")],
                "constraints": [models.UniqueConstraint(django.db.models.functions.text.Lower("label"), models.F("baseline"), name="uq_bl_tag_baseline_label_ci")],
            },
            managers=[
                ("objects", django.db.models.manager.Manager()),
                ("unscoped", django.db.models.manager.Manager()),
            ],
        ),
    ]
