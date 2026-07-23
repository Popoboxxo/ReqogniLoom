"""SEC-02 / REQ-186/187 — Flip permission enforcement to ``authoritative``.

The REQ-186 end-state is the permission_json matrix as the SOLE authoritative
access-control mechanism. The rollout parked at ``shadow`` (legacy decides, new
model only observed) even though:

* the backfilled matrix (``0006_backfill_permission_defaults``) is a frozen 1:1
  lift of the coded legacy ``_RBAC_MATRIX``, and
* the live deployment's shadow-verify log showed no unreviewed mismatches
  ("safe to flip" per the REQ-187 advisory).

This migration performs the cutover for EXISTING tenants under the same
evidence gate the REST flip endpoint enforces (``flip_enforcement`` in
``auth_tenancy.services.permission_definition``): a tenant is flipped only when
it has ZERO pending ``PermissionDecisionMismatch`` rows in the trailing 30-day
window. Tenants with untriaged mismatches stay on ``shadow`` and are logged —
they must be triaged and flipped via the guarded endpoint instead.

The ``AlterField`` aligns the model default so NEW tenants start authoritative
immediately; their freshly seeded matrix mirrors legacy 1:1, so day-1
authoritative verdicts are decision-for-decision identical to the legacy check.

Reverse: restores the ``shadow`` default but does NOT flip tenants back — an
access-control hardening step must never be silently rolled back by a migration
reversal. Use the guarded flip endpoint (``authoritative -> shadow`` needs no
confirmation) for a deliberate rollback.
"""
from __future__ import annotations

import logging
from datetime import timedelta

from django.db import migrations, models
from django.utils import timezone

logger = logging.getLogger(__name__)

# Trailing window (days) for the pending-mismatch gate — mirrors
# DEFAULT_MISMATCH_WINDOW_DAYS in auth_tenancy.services.permission_definition.
MISMATCH_WINDOW_DAYS = 30


def flip_clean_tenants_to_authoritative(apps, schema_editor):
    GlobalPermissionDefinition = apps.get_model(
        "auth_tenancy", "GlobalPermissionDefinition"
    )
    PermissionDecisionMismatch = apps.get_model(
        "auth_tenancy", "PermissionDecisionMismatch"
    )

    since = timezone.now() - timedelta(days=MISMATCH_WINDOW_DAYS)
    flipped = 0
    skipped = 0
    for row in GlobalPermissionDefinition.objects.filter(
        enforcement_mode="shadow"
    ):
        pending = PermissionDecisionMismatch.objects.filter(
            tenant_id=row.tenant_id, created_at__gte=since
        ).count()
        if pending == 0:
            row.enforcement_mode = "authoritative"
            row.save(update_fields=["enforcement_mode"])
            flipped += 1
        else:
            skipped += 1
            logger.warning(
                "SEC-02 migration: tenant %s keeps enforcement_mode='shadow' — "
                "%d untriaged permission mismatches in the trailing %d days. "
                "Triage them, then flip via POST "
                "/api/v1/permission-defaults/enforcement/flip/.",
                row.tenant_id,
                pending,
                MISMATCH_WINDOW_DAYS,
            )
    logger.info(
        "SEC-02 migration: flipped %d tenant(s) to authoritative, %d skipped.",
        flipped,
        skipped,
    )


def noop_reverse(apps, schema_editor):
    """No automatic rollback of an access-control hardening step."""


class Migration(migrations.Migration):

    dependencies = [
        ("auth_tenancy", "0006_backfill_permission_defaults"),
    ]

    operations = [
        migrations.AlterField(
            model_name="globalpermissiondefinition",
            name="enforcement_mode",
            field=models.CharField(
                choices=[
                    ("shadow", "Shadow (legacy decides, new observed)"),
                    ("authoritative", "Authoritative (new decides)"),
                ],
                default="authoritative",
                max_length=16,
            ),
        ),
        migrations.RunPython(
            flip_clean_tenants_to_authoritative, noop_reverse
        ),
    ]
