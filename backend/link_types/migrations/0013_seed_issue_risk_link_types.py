"""Seed the Issue/Risk built-ins ``blocks`` / ``resolves`` / ``threatens`` (#1374).

Plan F, F1.1-T2 (decision ENT-F1 = b): the Issue/Risk vocabulary stops being an
alias set and becomes three own built-in link types. ``BUILTIN_LINK_TYPES`` is
only read when a tenant or workspace is *provisioned*, so extending the dict
leaves every pre-existing tenant and workspace without the rows. This migration
materialises the three definitions for every tenant (global template) and every
workspace of that tenant, leaving any customized row untouched — the form of
``0008_seed_satisfaction_link_types`` with the pinned-definition shape of
``0011``/``0012``.

The three definitions are **pinned** here instead of being imported from
``link_types.builtin``: a data migration must reproduce the state of the commit
that introduced it, so reading the live dict would make the row content drift
with later catalog edits (and turn the seed into a silent no-op on a database
whose code predates the entries — the lesson in ``0009``).

Same RLS handling as ``0003``/``0008``/``0011``/``0012``: both ``lt_*`` tables
carry FORCE ROW LEVEL SECURITY, which binds the table owner too, so the
migration iterates tenants and arms ``app.current_tenant`` per tenant before
touching either table. ``pl_tenant`` is deliberately outside RLS, so
enumerating tenants needs no arming.

Reverse deletes only the rows this migration created — the three keys' global
templates plus their non-customized workspace copies. It refuses to run at all
while a ``TraceLink`` still references any of the three keys: dropping the type
would leave those links on a key no workspace catalog can resolve, which is
silent data loss.
"""
from __future__ import annotations

import copy
import logging
from typing import Any

from django.db import migrations

logger = logging.getLogger(__name__)

#: The keys this migration creates, in the order they are seeded.
NEW_KEYS: tuple[str, ...] = ("blocks", "resolves", "threatens")

#: Verbatim copies of the ``blocks``/``resolves``/``threatens`` entries in
#: ``link_types/builtin.py`` — see the module docstring for why they are pinned
#: rather than imported.
DEFINITIONS: dict[str, dict[str, Any]] = {
    "blocks": {
        "label": {
            "de": {
                "downstream": "blockiert",
                "upstream": "wird blockiert durch",
                "neutral": "Blockade",
            },
            "en": {
                "downstream": "blocks",
                "upstream": "is blocked by",
                "neutral": "Blocker",
            },
        },
        "allowed_pairs": [{"source_type": "Issue", "target_type": "*"}],
        "coverage_relevant": False,
        "suspect_rule": "none",
        "impact_weight": 0.5,
        "manual_creatable": True,
        "system_owned": False,
        "active": True,
        "built_in": True,
    },
    "resolves": {
        "label": {
            "de": {
                "downstream": "löst",
                "upstream": "wird gelöst durch",
                "neutral": "Lösung",
            },
            "en": {
                "downstream": "resolves",
                "upstream": "is resolved by",
                "neutral": "Resolution",
            },
        },
        "allowed_pairs": [{"source_type": "*", "target_type": "Issue"}],
        "coverage_relevant": False,
        "suspect_rule": "none",
        "impact_weight": 0.3,
        "manual_creatable": True,
        "system_owned": False,
        "active": True,
        "built_in": True,
    },
    "threatens": {
        "label": {
            "de": {
                "downstream": "bedroht",
                "upstream": "wird bedroht durch",
                "neutral": "Bedrohung",
            },
            "en": {
                "downstream": "threatens",
                "upstream": "is threatened by",
                "neutral": "Threat",
            },
        },
        "allowed_pairs": [{"source_type": "Risk", "target_type": "*"}],
        "coverage_relevant": False,
        "suspect_rule": "none",
        "impact_weight": 0.5,
        "manual_creatable": True,
        "system_owned": False,
        "active": True,
        "built_in": True,
    },
}


def _arm(schema_editor, tenant_id) -> None:
    """Point the RLS policies at *tenant_id* for the rest of this transaction."""
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("SET app.current_tenant = %s", [str(tenant_id)])


def _disarm(schema_editor) -> None:
    """Clear the tenant GUC again so no later statement inherits it."""
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("RESET app.current_tenant")


def seed_issue_risk_link_types(apps, schema_editor):
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
        "LinkTypeCatalog Issue/Risk seed (%s): %d global templates, "
        "%d workspace rows created.",
        ", ".join(NEW_KEYS),
        total_globals,
        total_rows,
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
                    f"Cannot reverse 0013_seed_issue_risk_link_types: {total} "
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
        ("link_types", "0012_seed_performs_and_satisfies_function_pair"),
    ]

    operations = [
        migrations.RunPython(seed_issue_risk_link_types, unseed),
    ]
