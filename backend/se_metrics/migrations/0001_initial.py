"""
ARCH-L1-015 SeMetrics — Initial migration.

leaf_id: COMP-SM-008
req_id: REQ-L2-SM-007, REQ-L2-SM-009

Creates:
  sm_metric_cache         (MetricCache model)
  sm_threshold_config     (WorkspaceThresholdConfig model)
"""
from __future__ import annotations

import uuid

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    """Initial migration for SeMetrics models."""

    initial = True

    dependencies: list = []

    operations = [
        migrations.CreateModel(
            name="MetricCache",
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
                ("tenant_id", models.UUIDField(db_index=True)),
                ("timeframe_key", models.CharField(max_length=32)),
                ("result_json", models.JSONField(default=dict)),
                ("computed_at", models.DateTimeField()),
                ("cache_ttl_seconds", models.IntegerField(default=300)),
            ],
            options={
                "db_table": "sm_metric_cache",
            },
        ),
        migrations.CreateModel(
            name="WorkspaceThresholdConfig",
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
                ("workspace_id", models.UUIDField(db_index=True, unique=True)),
                ("tenant_id", models.UUIDField(db_index=True)),
                (
                    "traceability_coverage_min",
                    models.FloatField(blank=True, null=True),
                ),
                ("volatility_max_avg", models.FloatField(blank=True, null=True)),
                ("workflow_gaps_max", models.IntegerField(blank=True, null=True)),
                (
                    "open_risks_max_critical",
                    models.IntegerField(blank=True, null=True),
                ),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "sm_threshold_config",
            },
        ),
        migrations.AddConstraint(
            model_name="metriccache",
            constraint=models.UniqueConstraint(
                fields=["workspace_id", "tenant_id", "timeframe_key"],
                name="uq_sm_cache_workspace_timeframe",
            ),
        ),
        migrations.AddIndex(
            model_name="metriccache",
            index=models.Index(
                fields=["workspace_id", "timeframe_key"],
                name="idx_sm_cache_ws_timeframe",
            ),
        ),
        migrations.AddIndex(
            model_name="metriccache",
            index=models.Index(
                fields=["tenant_id", "workspace_id"],
                name="idx_sm_cache_tenant_ws",
            ),
        ),
        migrations.AddIndex(
            model_name="workspacethresholdconfig",
            index=models.Index(
                fields=["tenant_id", "workspace_id"],
                name="idx_sm_threshold_tenant_ws",
            ),
        ),
    ]
