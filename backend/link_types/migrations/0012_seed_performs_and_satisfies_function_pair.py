"""Seed ``performs`` and merge the function pair into ``satisfies`` (#877).

``BUILTIN_LINK_TYPES`` is only read when a tenant or workspace is *provisioned*,
so a catalog edit leaves every pre-existing tenant without the change. This
migration does both halves: it materialises ``performs`` (global template +
workspace copy, customized rows untouched — the shape of ``0008``/``0011``) and
appends ``Requirement -> ArchitectureElement:function`` to the ``satisfies``
rows, additively and duplicate-free (the merge helper of ``0009:57-77``) and
only where ``is_customized=False``.

Both definitions are **pinned** instead of imported from ``link_types.builtin``:
the migration must also run on a database whose code predates the entry, where
reading the live dict would make it a silent no-op (the lesson in ``0009``).

Same RLS handling as ``0003``/``0008``/``0011`` — both ``lt_*`` tables carry
FORCE ROW LEVEL SECURITY, so ``app.current_tenant`` is armed per tenant.

Reverse: ``performs`` behaves like the ``validates`` reverse in ``0011`` — it
deletes only the rows this migration created and refuses to run while a
``TraceLink`` still references the key, because dropping the type would leave
those links on a key no workspace catalog can resolve. The ``satisfies`` pair
merge is an explicit **noop** (``0009:26-30``): removing a pair on reverse could
delete a tenant customization and would orphan links on a now-disallowed pair.
"""
from __future__ import annotations

import copy
import logging
from typing import Any

from django.db import migrations

logger = logging.getLogger(__name__)

#: The only key this migration creates.
KEY = "performs"

#: The key whose ``allowed_pairs`` list this migration extends.
SATISFIES_KEY = "satisfies"

#: Verbatim copy of the ``performs`` entry in ``link_types/builtin.py`` — see
#: the module docstring for why it is pinned rather than imported.
DEFINITION: dict[str, Any] = {
    "label": {
        "de": {
            "downstream": "führt aus",
            "upstream": "wird ausgeführt von",
            "neutral": "Funktionszuordnung",
        },
        "en": {
            "downstream": "performs",
            "upstream": "is performed by",
            "neutral": "Function allocation",
        },
    },
    "allowed_pairs": [
        {"source_type": "ArchitectureElement", "target_type": "ArchitectureElement:function"}
    ],
    "coverage_relevant": False,
    "suspect_rule": "target_change_flags_source",
    "impact_weight": 0.8,
    "manual_creatable": True,
    "system_owned": False,
    "active": True,
    "built_in": True,
}

#: The one edge this migration adds to ``satisfies``, in the ``allowed_pairs``
#: shape stored in ``definition_json`` (``Typ:Subtag`` notation, B3-T2).
SATISFIES_WANTED_PAIRS = [
    {"source_type": "Requirement", "target_type": "ArchitectureElement:function"}
]


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
    is missing, so the caller can skip the write. Duplicated from ``0009`` on
    purpose — a later migration must not depend on an earlier one being
    unsquashed.
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


def seed_performs(apps, schema_editor):
    """Materialise the ``performs`` definition for every tenant and workspace."""
    Tenant = apps.get_model("persistence", "Tenant")
    Workspace = apps.get_model("persistence", "Workspace")
    GlobalLinkTypeDefinition = apps.get_model("link_types", "GlobalLinkTypeDefinition")
    WorkspaceLinkTypeDefinition = apps.get_model(
        "link_types", "WorkspaceLinkTypeDefinition"
    )

    total_globals = 0
    total_rows = 0
    try:
        for tenant_id in list(Tenant.objects.values_list("id", flat=True)):
            _arm(schema_editor, tenant_id)
            global_row, created = GlobalLinkTypeDefinition.unscoped.get_or_create(
                tenant_id=tenant_id,
                key=KEY,
                defaults={
                    "definition_json": copy.deepcopy(DEFINITION),
                    "version": 1,
                },
            )
            total_globals += int(created)

            workspace_ids = list(
                Workspace.objects.filter(tenant_id=tenant_id).values_list(
                    "id", flat=True
                )
            )
            for workspace_id in workspace_ids:
                _row, row_created = WorkspaceLinkTypeDefinition.unscoped.get_or_create(
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    key=KEY,
                    defaults={
                        "definition_json": copy.deepcopy(global_row.definition_json),
                        "source_global": global_row,
                        "is_customized": False,
                        "version": 1,
                    },
                )
                total_rows += int(row_created)
    finally:
        _disarm(schema_editor)

    logger.info(
        "LinkTypeCatalog '%s' seed: %d global templates, %d workspace rows created.",
        KEY,
        total_globals,
        total_rows,
    )


def merge_satisfies_pair(apps, schema_editor):
    """Append the function pair to global + non-customized ``satisfies`` rows."""
    Tenant = apps.get_model("persistence", "Tenant")
    GlobalLinkTypeDefinition = apps.get_model("link_types", "GlobalLinkTypeDefinition")
    WorkspaceLinkTypeDefinition = apps.get_model(
        "link_types", "WorkspaceLinkTypeDefinition"
    )

    updated = 0
    try:
        for tenant_id in list(Tenant.objects.values_list("id", flat=True)):
            _arm(schema_editor, tenant_id)
            rows = list(
                GlobalLinkTypeDefinition.unscoped.filter(
                    tenant_id=tenant_id, key=SATISFIES_KEY
                )
            ) + list(
                WorkspaceLinkTypeDefinition.unscoped.filter(
                    tenant_id=tenant_id,
                    key=SATISFIES_KEY,
                    is_customized=False,
                )
            )
            for row in rows:
                current = row.definition_json or {}
                merged = _merge_missing_pairs(current, SATISFIES_WANTED_PAIRS)
                if merged is current:
                    continue
                row.definition_json = merged
                row.save(update_fields=["definition_json"])
                updated += 1
    finally:
        _disarm(schema_editor)

    logger.info(
        "LinkTypeCatalog: '%s' Requirement->ArchitectureElement:function pair "
        "backfilled into %d rows.",
        SATISFIES_KEY,
        updated,
    )


def unseed(apps, schema_editor):
    """Reverse: drop the rows this migration created, unless links still use them."""
    Tenant = apps.get_model("persistence", "Tenant")
    TraceLink = apps.get_model("persistence", "TraceLink")
    GlobalLinkTypeDefinition = apps.get_model("link_types", "GlobalLinkTypeDefinition")
    WorkspaceLinkTypeDefinition = apps.get_model(
        "link_types", "WorkspaceLinkTypeDefinition"
    )

    try:
        for tenant_id in list(Tenant.objects.values_list("id", flat=True)):
            _arm(schema_editor, tenant_id)
            linked = TraceLink.objects.filter(
                tenant_id=tenant_id, link_type=KEY
            ).count()
            if linked:
                raise RuntimeError(
                    f"Cannot reverse 0012_seed_performs_and_satisfies_function_pair: "
                    f"{linked} TraceLink row(s) still reference the '{KEY}' link "
                    "type. Delete or re-type those links before rolling back."
                )
            WorkspaceLinkTypeDefinition.unscoped.filter(
                tenant_id=tenant_id, key=KEY, is_customized=False
            ).delete()
            GlobalLinkTypeDefinition.unscoped.filter(
                tenant_id=tenant_id, key=KEY
            ).delete()
    finally:
        _disarm(schema_editor)


class Migration(migrations.Migration):

    dependencies = [
        ("link_types", "0011_seed_validates_link_type"),
    ]

    operations = [
        migrations.RunPython(seed_performs, unseed),
        # The ``satisfies`` pair merge is deliberately irreversible
        # (``RunPython.noop``): removing a pair on reverse could delete a
        # deliberately added tenant customization and would leave existing
        # ``Requirement -> ArchitectureElement:function`` links on a
        # no-longer-allowed pair — the justification recorded in ``0009:26-30``.
        migrations.RunPython(merge_satisfies_pair, migrations.RunPython.noop),
    ]
