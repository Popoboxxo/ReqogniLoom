"""
Migration 0010: Additive FMEA fields for Risk (REQ-L1-029).

Extends the Risk entity toward a complete FMEA model. The existing 3x3 matrix
(probability x impact) is FMEA-adjacent; this migration adds the third FMEA
axis (detection) so the Risk Priority Number (RPN = probability x impact x
detection) can be derived, plus a proper User FK for risk ownership.

Strategy (backward-compatible, no destructive changes):
  1. AddField ``detection`` (PositiveSmallInteger, default=5) — existing rows
     receive a neutral mid-scale value; no backfill required.
  2. AddField ``owner_user`` (nullable FK to AUTH_USER_MODEL, on_delete
     SET_NULL) — added ALONGSIDE the legacy ``owner`` CharField, which is
     intentionally kept (expand phase of expand/contract). Existing rows keep a
     NULL owner_user; the free-text ``owner`` continues to work unchanged.

The RPN itself is a computed @property on the model (Risk.rpn) — no column,
no migration.

Reverse: both fields are plain AddField operations, so Django's automatic
reversal (RemoveField) restores the prior schema exactly. No data loss on
down: the retained ``owner`` CharField still holds ownership information.

COMP-AS-014 RiskService.
leaf_id : COMP-AS-014
req_id  : REQ-L1-029
"""
import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("application", "0009_risk_issue_rls_policies"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="risk",
            name="detection",
            field=models.PositiveSmallIntegerField(
                default=5,
                validators=[
                    django.core.validators.MinValueValidator(1),
                    django.core.validators.MaxValueValidator(10),
                ],
                help_text=(
                    "REQ-L1-029: FMEA detection score "
                    "(1=easy .. 10=impossible)."
                ),
            ),
        ),
        migrations.AddField(
            model_name="risk",
            name="owner_user",
            field=models.ForeignKey(
                to=settings.AUTH_USER_MODEL,
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="owned_risks",
                help_text="REQ-L1-029: assigned risk owner (User FK).",
            ),
        ),
    ]
