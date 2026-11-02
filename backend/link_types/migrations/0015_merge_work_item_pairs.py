"""Merge the WorkItem pairs into ``decomposes`` and ``references``.

Plan F, F3-T3 (``docs/plans/2026-10-21-plan-f-dokumente-baselines.md``, spec
``2026-11-02-f3-workitem-design.md`` §5): a ``WorkItem`` is a first-class,
decomposable artifact. Two already-shipped link types gain a pair — no new key
is introduced:

* ``decomposes`` — ``Document -> WorkItem`` (a document is broken into items)
  and ``WorkItem -> WorkItem`` (a phase into steps);
* ``references`` — ``WorkItem -> *`` (replaces the concept's ``implements`` /
  ``traces``; both stay aliases of ``references``).

``depends-on`` already ships ``WorkItem -> WorkItem`` since F2 (``0014``), so
this migration deliberately does not touch it: no second pair, no duplicate
entry.

``BUILTIN_LINK_TYPES`` is only read when a tenant or workspace is
*provisioned*, so extending the dict in ``link_types/builtin.py`` leaves every
pre-existing tenant and workspace on the old pair list. This migration
materialises the merge for every tenant (global template) and every
non-customized workspace copy, leaving a customized row untouched — the shape
of ``0014_seed_document_link_types``.

The merge is additive and duplicate-free: an existing pair is never dropped or
reordered, and re-running the migration is a no-op.

Reverse removes exactly the pairs this migration added, from the same rows
(global templates and non-customized workspace copies). It refuses to run at
all while a ``TraceLink`` still relies on one of them: dropping the pair would
leave that link on a pair no workspace catalog allows, which is silent data
loss — the reverse policy of ``0014``. The check is deliberately conservative:
for ``references`` it keys on the source type ``WorkItem`` as a whole (the side
this migration extends), not on a specific target.

Same RLS handling as ``0003``/``0008``/``0011``/``0012``/``0013``/``0014``:
both ``lt_*`` tables carry FORCE ROW LEVEL SECURITY, which binds the table
owner too, so the migration iterates tenants and arms ``app.current_tenant``
per tenant before touching either table.
"""
from __future__ import annotations

import logging

from django.db import migrations
from django.db.models import Q

logger = logging.getLogger(__name__)

#: The pairs this migration appends, keyed by link type and in the
#: ``allowed_pairs`` shape stored in ``definition_json``.
MERGED_PAIRS: dict[str, list[dict[str, str]]] = {
    "decomposes": [
        {"source_type": "Document", "target_type": "WorkItem"},
        {"source_type": "WorkItem", "target_type": "WorkItem"},
    ],
    "references": [
        {"source_type": "WorkItem", "target_type": "*"},
    ],
}


def _arm(schema_editor, tenant_id) -> None:
    """Point the RLS policies at *tenant_id* for the rest of this transaction."""
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("SET app.current_tenant = %s", [str(tenant_id)])


def _disarm(schema_editor) -> None:
    """Clear the tenant GUC again so no later statement inherits it."""
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("RESET app.current_tenant")


def _merge_missing_pairs(definition, wanted):
    """Return *definition* with every pair of *wanted* it does not have yet.

    Additive and duplicate-free, exactly like
    ``grandfathered.apply_grandfathered_pairs``: an existing pair is never
    dropped or reordered. Returns the input unchanged (same object) when nothing
    is missing, so the caller can skip the write. Duplicated from ``0012`` and
    ``0014`` on purpose — a later migration must not depend on an earlier one
    being unsquashed.
    """
    pairs = list(definition.get("allowed_pairs") or [])
    seen = {(p.get("source_type"), p.get("target_type")) for p in pairs}
    missing = [
        dict(pair)
        for pair in wanted
        if (pair["source_type"], pair["target_type"]) not in seen
    ]
    if not missing:
        return definition
    merged = dict(definition)
    merged["allowed_pairs"] = pairs + missing
    return merged


def _without_pairs(definition, unwanted):
    """Return *definition* with every pair of *unwanted* removed, order intact.

    Returns the input unchanged (same object) when nothing is present, so the
    caller can skip the write.
    """
    pairs = list(definition.get("allowed_pairs") or [])
    doomed = {(p["source_type"], p["target_type"]) for p in unwanted}
    kept = [
        pair
        for pair in pairs
        if (pair.get("source_type"), pair.get("target_type")) not in doomed
    ]
    if len(kept) == len(pairs):
        return definition
    stripped = dict(definition)
    stripped["allowed_pairs"] = kept
    return stripped


def _rows_to_touch(apps, tenant_id):
    """Yield the global and non-customized workspace rows this migration owns.

    A customized workspace row is a tenant decision and is never rewritten.
    """
    GlobalLinkTypeDefinition = apps.get_model("link_types", "GlobalLinkTypeDefinition")
    WorkspaceLinkTypeDefinition = apps.get_model(
        "link_types", "WorkspaceLinkTypeDefinition"
    )

    yield from GlobalLinkTypeDefinition.unscoped.filter(
        tenant_id=tenant_id, key__in=MERGED_PAIRS
    )
    yield from WorkspaceLinkTypeDefinition.unscoped.filter(
        tenant_id=tenant_id, key__in=MERGED_PAIRS, is_customized=False
    )


def merge_work_item_pairs(apps, schema_editor):
    """Append the WorkItem pairs to every global template and workspace copy."""
    Tenant = apps.get_model("persistence", "Tenant")

    updated = 0
    try:
        for tenant_id in list(Tenant.objects.values_list("id", flat=True)):
            _arm(schema_editor, tenant_id)
            for row in _rows_to_touch(apps, tenant_id):
                current = row.definition_json or {}
                merged = _merge_missing_pairs(current, MERGED_PAIRS[row.key])
                if merged is current:
                    continue
                row.definition_json = merged
                row.save(update_fields=["definition_json"])
                updated += 1
    finally:
        _disarm(schema_editor)

    logger.info(
        "LinkTypeCatalog: WorkItem pairs merged into %d %s row(s).",
        updated,
        "/".join(sorted(MERGED_PAIRS)),
    )


def _links_relying_on_pairs(apps, tenant_id) -> dict[str, int]:
    """Count TraceLinks that would be left on a disallowed pair by the reverse.

    ``decomposes`` is filtered to the two new endpoint combinations — the type
    itself is far older and heavily used. ``references`` is filtered to a
    ``WorkItem`` source, which is the side this migration extends.
    """
    TraceLink = apps.get_model("persistence", "TraceLink")
    Artifact = apps.get_model("persistence", "Artifact")

    # ``unscoped`` on purpose: a data migration runs without a TenantContext,
    # and the explicit ``tenant_id`` filter is the isolation here (RLS is armed
    # by the caller).
    document_ids = Artifact.unscoped.filter(
        tenant_id=tenant_id, artifact_type="Document"
    ).values("id")
    work_item_ids = Artifact.unscoped.filter(
        tenant_id=tenant_id, artifact_type="WorkItem"
    ).values("id")

    decomposes = TraceLink.unscoped.filter(
        tenant_id=tenant_id, link_type="decomposes"
    ).filter(
        Q(source_id__in=document_ids, target_id__in=work_item_ids)
        | Q(source_id__in=work_item_ids, target_id__in=work_item_ids)
    )
    references = TraceLink.unscoped.filter(
        tenant_id=tenant_id,
        link_type="references",
        source_id__in=work_item_ids,
    )

    counts = {"decomposes": decomposes.count(), "references": references.count()}
    return {key: count for key, count in counts.items() if count}


def unmerge_work_item_pairs(apps, schema_editor):
    """Reverse: drop the added pairs unless a link still relies on one."""
    Tenant = apps.get_model("persistence", "Tenant")

    updated = 0
    try:
        for tenant_id in list(Tenant.objects.values_list("id", flat=True)):
            _arm(schema_editor, tenant_id)
            relying = _links_relying_on_pairs(apps, tenant_id)
            if relying:
                total = sum(relying.values())
                detail = ", ".join(
                    f"'{key}' ({count})" for key, count in sorted(relying.items())
                )
                raise RuntimeError(
                    f"Cannot reverse 0015_merge_work_item_pairs: {total} "
                    f"TraceLink row(s) rely on the WorkItem pairs in {detail}. "
                    "Delete or re-type those links before rolling back."
                )
            for row in _rows_to_touch(apps, tenant_id):
                current = row.definition_json or {}
                stripped = _without_pairs(current, MERGED_PAIRS[row.key])
                if stripped is current:
                    continue
                row.definition_json = stripped
                row.save(update_fields=["definition_json"])
                updated += 1
    finally:
        _disarm(schema_editor)

    logger.info(
        "LinkTypeCatalog: WorkItem pairs removed from %d %s row(s).",
        updated,
        "/".join(sorted(MERGED_PAIRS)),
    )


class Migration(migrations.Migration):

    dependencies = [
        ("link_types", "0014_seed_document_link_types"),
    ]

    operations = [
        # The merge is reversible: the reverse removes exactly the pairs added
        # here, but only after proving no TraceLink depends on them.
        migrations.RunPython(merge_work_item_pairs, unmerge_work_item_pairs),
    ]
