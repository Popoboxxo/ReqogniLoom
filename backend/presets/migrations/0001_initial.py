"""
ARCH-L1-008 PresetConfigEngine — initial migration.

Creates: pc_workspace_preset_config

Requirements:
- REQ-L2-PC-001 (preset tier per workspace)
- REQ-L2-PC-009 / REQ-L3-PC002-003 (terminology profile persistence)
- REQ-L3-PC003-003 (downgrade_policy persistence)

Depends on persistence.0001_initial (Workspace + Tenant must exist first).

leaf_id: ARCH-L1-008
req_id : REQ-L2-PC-001, REQ-L2-PC-009, REQ-L2-PC-011
"""
from __future__ import annotations

import django.db.models.deletion
from django.db import migrations, models
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("persistence", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="WorkspacePresetConfig",
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
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("modified_at", models.DateTimeField(auto_now=True)),
                ("version", models.IntegerField(default=1)),
                (
                    "active_tier",
                    models.CharField(
                        choices=[
                            ("minimal", "Minimal"),
                            ("standard", "Standard"),
                            ("extended", "Extended"),
                        ],
                        default="minimal",
                        max_length=32,
                    ),
                ),
                (
                    "terminology_profile",
                    models.CharField(
                        choices=[
                            ("dev_mode", "Dev Mode"),
                            ("se_mode", "SE Mode"),
                        ],
                        default="dev_mode",
                        max_length=32,
                    ),
                ),
                (
                    "downgrade_policy",
                    models.CharField(
                        choices=[
                            ("block", "Block"),
                            ("warn", "Warn"),
                            ("allow", "Allow"),
                        ],
                        default="block",
                        max_length=16,
                    ),
                ),
                # Audit FK fields from AuditableModel
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="persistence.user",
                    ),
                ),
                (
                    "modified_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="persistence.user",
                    ),
                ),
                # Tenant FK from TenantScopedModel
                (
                    "tenant",
                    models.ForeignKey(
                        db_index=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="workspacepresetconfig_set",
                        to="persistence.tenant",
                    ),
                ),
                # OneToOne to Workspace
                (
                    "workspace",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="preset_config",
                        to="persistence.workspace",
                    ),
                ),
            ],
            options={
                "db_table": "pc_workspace_preset_config",
                "base_manager_name": "unscoped",
            },
        ),
    ]
