"""Seed the document built-ins ``documented-in`` / ``evidences`` / ``depends-on``.

Plan F, F2-T3 (``docs/plans/2026-10-21-plan-f-dokumente-baselines.md``, spec
``2026-11-02-f2-document-design.md`` §5, ADR-026): three new link types for the
``Document`` artifact, plus an additive extension of ``references`` with
``Document`` as source and target.

``BUILTIN_LINK_TYPES`` is only read when a tenant or workspace is *provisioned*,
so extending the dict leaves every pre-existing tenant and workspace without the
rows. This migration materialises the three definitions for every tenant
(global template) and every workspace of that tenant, leaving any customized row
untouched — the shape of ``0012_seed_performs_and_satisfies_function_pair`` and
``0013_seed_issue_risk_link_types``.

The three definitions are **pinned** here instead of being imported from
``link_types.builtin``: a data migration must reproduce the state of the commit
that introduced it, so reading the live dict would make the row content drift
with later catalog edits (and turn the seed into a silent no-op on a database
whose code predates the entries — the lesson in ``0009``).

The kind restriction of ``evidences`` (``Conclusion``/``Review``/``AuditReport``)
is carried by the ``Document:<kind>`` pairs, i.e. by the generic sub-type
register (``link_types.catalog.SUBTYPE_FIELDS``, Plan B B3-T2) — this migration
only stores the pinned pair list.

Same RLS handling as ``0003``/``0008``/``0011``/``0012``/``0013``: both ``lt_*``
tables carry FORCE ROW LEVEL SECURITY, which binds the table owner too, so the
migration iterates tenants and arms ``app.current_tenant`` per tenant before
touching either table.

Reverse deletes only the rows this migration created — the three keys' global
templates plus their non-customized workspace copies. It refuses to run at all
while a ``TraceLink`` still references any of the three keys: dropping the type
would leave those links on a key no workspace catalog can resolve, which is
silent data loss. The ``references`` pair merge is an explicit **noop** on
reverse (``0009:26-30``, ``0012``): removing a pair could delete a tenant
customization and would orphan links on a now-disallowed pair.
"""
from __future__ import annotations

import copy
import logging
from typing import Any

from django.db import migrations

logger = logging.getLogger(__name__)

#: The keys this migration creates, in the order they are seeded.
NEW_KEYS: tuple[str, ...] = ("documented-in", "evidences", "depends-on")

#: The key whose ``allowed_pairs`` list this migration extends.
REFERENCES_KEY = "references"

#: Verbatim copies of the ``documented-in``/``evidences``/``depends-on`` entries
#: in ``link_types/builtin.py`` — see the module docstring for why they are
#: pinned rather than imported.
DEFINITIONS: dict[str, dict[str, Any]] = {
    "documented-in": {
        "label": {
            "de": {
                "downstream": "dokumentiert in",
                "upstream": "dokumentiert",
                "neutral": "Dokumentation",
            },
            "en": {
                "downstream": "documented in",
                "upstream": "documents",
                "neutral": "Documentation",
            },
        },
        "allowed_pairs": [
            {"source_type": "Requirement", "target_type": "Document"},
            {"source_type": "StakeholderNeed", "target_type": "Document"},
            {"source_type": "ArchitectureElement", "target_type": "Document"},
            {"source_type": "Adr", "target_type": "Document"},
            {"source_type": "Risk", "target_type": "Document"},
            {"source_type": "Issue", "target_type": "Document"},
            {"source_type": "Goal", "target_type": "Document"},
        ],
        "coverage_relevant": False,
        "suspect_rule": "target_change_flags_source",
        "impact_weight": 0.3,
        "manual_creatable": True,
        "system_owned": False,
        "active": True,
        "built_in": True,
    },
    "evidences": {
        "label": {
            "de": {
                "downstream": "belegt",
                "upstream": "wird belegt durch",
                "neutral": "Beleg",
            },
            "en": {
                "downstream": "evidences",
                "upstream": "is evidenced by",
                "neutral": "Evidence",
            },
        },
        "allowed_pairs": [
            {"source_type": "Document:conclusion", "target_type": "Requirement"},
            {"source_type": "Document:conclusion", "target_type": "ArchitectureElement"},
            {"source_type": "Document:conclusion", "target_type": "StakeholderNeed"},
            {"source_type": "Document:review", "target_type": "Requirement"},
            {"source_type": "Document:review", "target_type": "ArchitectureElement"},
            {"source_type": "Document:review", "target_type": "StakeholderNeed"},
            {"source_type": "Document:auditreport", "target_type": "Requirement"},
            {"source_type": "Document:auditreport", "target_type": "ArchitectureElement"},
            {"source_type": "Document:auditreport", "target_type": "StakeholderNeed"},
        ],
        "coverage_relevant": False,
        "suspect_rule": "target_change_flags_source",
        "impact_weight": 0.5,
        "manual_creatable": True,
        "system_owned": False,
        "active": True,
        "built_in": True,
    },
    "depends-on": {
        "label": {
            "de": {
                "downstream": "hängt ab von",
                "upstream": "ist Voraussetzung für",
                "neutral": "Abhängigkeit",
            },
            "en": {
                "downstream": "depends on",
                "upstream": "is prerequisite for",
                "neutral": "Dependency",
            },
        },
        "allowed_pairs": [{"source_type": "WorkItem", "target_type": "WorkItem"}],
        "coverage_relevant": False,
        "suspect_rule": "target_change_flags_source",
        "impact_weight": 0.5,
        "manual_creatable": True,
        "system_owned": False,
        "active": True,
        "built_in": True,
    },
}

#: The two edges this migration appends to ``references``, in the
#: ``allowed_pairs`` shape stored in ``definition_json``.
REFERENCES_WANTED_PAIRS = [
    {"source_type": "Document", "target_type": "*"},
    {"source_type": "*", "target_type": "Document"},
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
    is missing, so the caller can skip the write. Duplicated from ``0012`` on
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


def seed_document_link_types(apps, schema_editor):
    """Create the three global templates and workspace copies, tenant by tenant."""
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
            workspace_ids = list(
                Workspace.objects.filter(tenant_id=tenant_id).values_list(
                    "id", flat=True
                )
            )
            for key in NEW_KEYS:
                global_row, created = GlobalLinkTypeDefinition.unscoped.get_or_create(
                    tenant_id=tenant_id,
                    key=key,
                    defaults={
                        "definition_json": copy.deepcopy(DEFINITIONS[key]),
                        "version": 1,
                    },
                )
                total_globals += int(created)

                for workspace_id in workspace_ids:
                    _row, row_created = WorkspaceLinkTypeDefinition.unscoped.get_or_create(
                        tenant_id=tenant_id,
                        workspace_id=workspace_id,
                        key=key,
                        defaults={
                            "definition_json": copy.deepcopy(
                                global_row.definition_json
                            ),
                            "source_global": global_row,
                            "is_customized": False,
                            "version": 1,
                        },
                    )
                    total_rows += int(row_created)
    finally:
        _disarm(schema_editor)

    logger.info(
        "LinkTypeCatalog document seed (%s): %d global templates, "
        "%d workspace rows created.",
        ", ".join(NEW_KEYS),
        total_globals,
        total_rows,
    )


def merge_references_pairs(apps, schema_editor):
    """Append Document as source/target to global + non-customized ``references`` rows."""
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
                    tenant_id=tenant_id, key=REFERENCES_KEY
                )
            ) + list(
                WorkspaceLinkTypeDefinition.unscoped.filter(
                    tenant_id=tenant_id,
                    key=REFERENCES_KEY,
                    is_customized=False,
                )
            )
            for row in rows:
                current = row.definition_json or {}
                merged = _merge_missing_pairs(current, REFERENCES_WANTED_PAIRS)
                if merged is current:
                    continue
                row.definition_json = merged
                row.save(update_fields=["definition_json"])
                updated += 1
    finally:
        _disarm(schema_editor)

    logger.info(
        "LinkTypeCatalog: Document pairs backfilled into %d '%s' rows.",
        updated,
        REFERENCES_KEY,
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
            linked_by_key = {
                key: TraceLink.objects.filter(
                    tenant_id=tenant_id, link_type=key
                ).count()
                for key in NEW_KEYS
            }
            linked_by_key = {key: n for key, n in linked_by_key.items() if n}
            if linked_by_key:
                total = sum(linked_by_key.values())
                detail = ", ".join(
                    f"'{key}' ({count})" for key, count in linked_by_key.items()
                )
                raise RuntimeError(
                    f"Cannot reverse 0014_seed_document_link_types: {total} "
                    f"TraceLink row(s) still reference the {detail} link "
                    "type(s). Delete or re-type those links before rolling back."
                )
            WorkspaceLinkTypeDefinition.unscoped.filter(
                tenant_id=tenant_id, key__in=NEW_KEYS, is_customized=False
            ).delete()
            GlobalLinkTypeDefinition.unscoped.filter(
                tenant_id=tenant_id, key__in=NEW_KEYS
            ).delete()
    finally:
        _disarm(schema_editor)


class Migration(migrations.Migration):

    dependencies = [
        ("link_types", "0013_seed_issue_risk_link_types"),
    ]

    operations = [
        migrations.RunPython(seed_document_link_types, unseed),
        # The ``references`` pair merge is deliberately irreversible
        # (``RunPython.noop``), same justification as ``0012``: removing a pair
        # on reverse could delete a tenant customization and would leave
        # existing Document reference links on a no-longer-allowed pair.
        migrations.RunPython(merge_references_pairs, migrations.RunPython.noop),
    ]
