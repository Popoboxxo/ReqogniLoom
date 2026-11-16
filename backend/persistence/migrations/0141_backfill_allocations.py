"""Backfill ``Allocation`` rows from existing ``allocated-to`` trace links.

Every existing edge becomes one active allocation. Deliberately **draft**, not
``released``: the historical edges never carried a release decision, and a
retroactive release would freeze artefacts nobody released. The release path
(``POST /elements/{id}/release/``) sets ``released`` explicitly from now on.

Idempotent by construction: the partial unique constraint on
``(requirement_artifact, element_artifact)`` for active rows plus
``ON CONFLICT DO NOTHING`` means a second run inserts nothing.

DELIBERATE ONE-WAY DOOR (S0.3-A / L0-002)
-----------------------------------------
This migration has **no reverse**. Reversing it used to issue an unqualified
bulk ``DELETE`` against ``pl_allocation``, which would wipe *every* allocation
— including the ones subsequently created through the API and released by users. The
backfilled draft rows carry no provenance marker that distinguishes them from
API-created rows ("drafts are indistinguishable from real allocations"), so a
targeted rollback is impossible. A broad delete is worse than an irreversible
forward step: it destroys live data on a routine ``migrate <app> 0140``. The
reverse is therefore ``RunSQL.noop`` on purpose — operators must use an
explicit, audited data-repair path instead of rolling this migration back.
Guarded by ``persistence/tests/test_backfill_allocations_reverse_guard.py``.
"""
from __future__ import annotations

from django.db import migrations

_BACKFILL_SQL = """
INSERT INTO pl_allocation (
    id, tenant_id, workspace_id,
    requirement_artifact_id, element_artifact_id,
    status, is_primary, version, revocation_reason,
    created_at, modified_at
)
SELECT
    gen_random_uuid(), tl.tenant_id, req_artifact.workspace_id,
    tl.source_id, tl.target_id,
    'draft', true, 1, '',
    now(), now()
FROM pl_tracelink tl
JOIN pl_artifact req_artifact ON req_artifact.id = tl.source_id
WHERE tl.link_type = 'allocated-to'
ON CONFLICT DO NOTHING;
"""


class Migration(migrations.Migration):
    """One-way backfill; see the module docstring for the one-way-door rationale."""

    dependencies = [
        ("persistence", "0140_allocation_rls_policy"),
    ]

    operations = [
        migrations.RunSQL(sql=_BACKFILL_SQL, reverse_sql=migrations.RunSQL.noop),
    ]
