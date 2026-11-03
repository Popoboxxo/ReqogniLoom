# Plan B B6-T1 (#879): planned review milestones ("Technical Planning").
#
# `Milestone` is a plain tenant-scoped entity — deliberately not backed by an
# Artifact (ENT-B2 = a: only Milestone, no Measure). It records a planned
# formal review (SRR/PDR/CDR/TRR/ORR/OTHER), its target date, the baseline it
# refers to and, once `record_audit` has run, a frozen copy of the SE-Auditor
# counts. `baseline` is PROTECTed so a bound baseline cannot be hard-deleted.
#
# `version` is the plan-specified PositiveIntegerField form of the inherited
# optimistic-concurrency counter; `updated_at` sits next to `modified_at` as in
# Adr/Risk (published REST/MCP contract).
#
# The tenant RLS policy ships in the very next migration
# (`0130_milestone_rls_policy`) in the same release (D-RLS, KA-B-11).
import django.db.models.deletion
import django.db.models.manager
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("baseline", "0013_baseline_tag_rls_policy"),
        ("persistence", "0128_inline_anchor_rls_policy"),
    ]

    operations = [
        migrations.CreateModel(
            name="Milestone",
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
                (
                    "name",
                    models.CharField(
                        help_text="Human-readable milestone name, e.g. 'PDR Fahrwerk'.",
                        max_length=200,
                    ),
                ),
                (
                    "review_type",
                    models.CharField(
                        choices=[
                            ("SRR", "System Requirements Review"),
                            ("PDR", "Preliminary Design Review"),
                            ("CDR", "Critical Design Review"),
                            ("TRR", "Test Readiness Review"),
                            ("ORR", "Operational Readiness Review"),
                            ("OTHER", "Other"),
                        ],
                        help_text="Formal review this milestone plans.",
                        max_length=16,
                    ),
                ),
                (
                    "target_date",
                    models.DateField(
                        help_text=(
                            "Planned review date; the primary sort key of every "
                            "list."
                        )
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("planned", "Planned"),
                            ("in_review", "In review"),
                            ("passed", "Passed"),
                            ("failed", "Failed"),
                            ("cancelled", "Cancelled"),
                        ],
                        default="planned",
                        help_text="Planning/execution state (default 'planned').",
                        max_length=16,
                    ),
                ),
                (
                    "audit_snapshot",
                    models.JSONField(
                        blank=True,
                        help_text=(
                            "Frozen copy of one SE-Auditor run ({tier, counts: "
                            "{total, blockers, warnings}, run_at}); a record, "
                            "never a gate."
                        ),
                        null=True,
                    ),
                ),
                ("version", models.PositiveIntegerField(default=1)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "baseline",
                    models.ForeignKey(
                        blank=True,
                        help_text=(
                            "Baseline the milestone refers to. PROTECT keeps a "
                            "bound baseline from being hard-deleted; the normal "
                            "path is immutable anyway."
                        ),
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="milestones",
                        to="baseline.baselinesnapshot",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "modified_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="%(class)s_set",
                        to="persistence.tenant",
                    ),
                ),
                (
                    "workspace",
                    models.ForeignKey(
                        help_text="Owning workspace.",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="milestones",
                        to="persistence.workspace",
                    ),
                ),
            ],
            options={
                "db_table": "pl_milestone",
                "ordering": ["target_date", "id"],
                "indexes": [
                    models.Index(
                        fields=["tenant", "workspace", "target_date"],
                        name="idx_milestone_ws_target",
                    )
                ],
            },
            managers=[
                ("objects", django.db.models.manager.Manager()),
                ("unscoped", django.db.models.manager.Manager()),
            ],
        ),
    ]
