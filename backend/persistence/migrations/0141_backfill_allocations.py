"""Backfill ``Allocation`` rows from existing ``allocated-to`` trace links.

Every existing edge becomes one active allocation. Deliberately **draft**, not
``released``: the historical edges never carried a release decision, and a
retroactive release would freeze artefacts nobody released. The release path
(``POST /elements/{id}/release/``) sets ``released`` explicitly from now on.

Idempotent by construction: the partial unique constraint on
``(requirement_artifact, element_artifact)`` for active rows plus
``ON CONFLICT DO NOTHING`` means a second run inserts nothing.
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

_DELETE_SQL = "DELETE FROM pl_allocation;"


class Migration(migrations.Migration):
    dependencies = [
        ("persistence", "0140_allocation_rls_policy"),
    ]

    operations = [
        migrations.RunSQL(sql=_BACKFILL_SQL, reverse_sql=_DELETE_SQL),
    ]
