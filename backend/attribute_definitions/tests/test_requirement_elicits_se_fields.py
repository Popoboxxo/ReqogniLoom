"""#272 / Plan B B1-T1 — Requirement's SE fields are elicited by the interview.

Two units:

* the source-level fix: ``introspect_core_attributes`` marks
  ``acceptance_criteria``/``verification_method``/``rationale`` ``ai_elicit``
  (tier 2 = ``get_protocol`` for every real, self_init-bootstrapped tenant);
* the repair of already-seeded rows: migration
  ``0011_requirement_interview_elicits_se_fields``, exercised through the real
  ``MigrationExecutor`` (names, never numbers) with a real ``Workspace`` row —
  same idiom as ``test_legacy_migration.py`` and 0007's executor test.
"""
from __future__ import annotations

import uuid

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from attribute_definitions.management.commands.bootstrap_attribute_definitions import (
    introspect_core_attributes,
)

_ATTR_DEF_APP = "attribute_definitions"
_PRE_TARGET = (_ATTR_DEF_APP, "0010_workspace_definition_workspace_fk")
_REPAIR = (_ATTR_DEF_APP, "0011_requirement_interview_elicits_se_fields")
_ELICITED = {"acceptance_criteria", "verification_method", "rationale"}


def test_extended_definition_marks_the_three_se_fields_ai_elicit() -> None:
    attributes = introspect_core_attributes("Requirement", "extended")
    flags = {a["name"]: a["ai_elicit"] for a in attributes}
    assert _ELICITED <= {name for name, flag in flags.items() if flag}
    # A Requirement attribute nobody asked to elicit must stay untouched --
    # guards against the flag becoming a blanket "all attributes" switch.
    assert flags["source"] is False


def test_minimal_keeps_the_se_fields_out_of_the_interview() -> None:
    """The repair migration is standard/extended-only; a fresh bootstrap must
    agree, or a minimal (lightweight-backlog) workspace would suddenly ask SE
    questions it never asked before."""
    flags = {
        a["name"]: a["ai_elicit"] for a in introspect_core_attributes("Requirement", "minimal")
    }
    assert not (_ELICITED & {name for name, flag in flags.items() if flag})


def _pre_fix_definition(extra_ai_elicit: str = "description") -> dict:
    """A stored workspace definition without the three SE flags."""
    return {
        "attributes": [
            {"name": "title", "type": "text", "ai_elicit": True},
            {"name": extra_ai_elicit, "type": "textarea", "ai_elicit": True},
            *(
                {"name": name, "type": "textarea", "ai_elicit": False}
                for name in sorted(_ELICITED)
            ),
        ]
    }


@pytest.mark.django_db(transaction=True)
def test_migration_repairs_a_seeded_workspace_definition() -> None:
    executor = MigrationExecutor(connection)
    latest_target = executor.loader.graph.leaf_nodes()

    try:
        executor.migrate([_PRE_TARGET])
        executor.loader.build_graph()
        historical = executor.loader.project_state([_PRE_TARGET]).apps
        Tenant = historical.get_model("persistence", "Tenant")
        Workspace = historical.get_model("persistence", "Workspace")
        WorkspaceDefinition = historical.get_model(
            _ATTR_DEF_APP, "WorkspaceAttributeDefinition"
        )

        tenant = Tenant.objects.create(
            name="Requirement SE Elicit Test", slug=f"req-se-{uuid.uuid4().hex[:8]}"
        )
        standard_ws = Workspace.objects.create(tenant_id=tenant.id, name="standard-ws")
        minimal_ws = Workspace.objects.create(tenant_id=tenant.id, name="minimal-ws")
        standard_row = WorkspaceDefinition.objects.create(
            tenant_id=tenant.id,
            workspace_id=standard_ws.id,
            item_type="Requirement",
            preset="standard",
            definition_json=_pre_fix_definition(),
        )
        minimal_row = WorkspaceDefinition.objects.create(
            tenant_id=tenant.id,
            workspace_id=minimal_ws.id,
            item_type="Requirement",
            preset="minimal",
            definition_json=_pre_fix_definition(),
        )

        executor.migrate([_REPAIR])
        executor.loader.build_graph()
        repaired = executor.loader.project_state([_REPAIR]).apps.get_model(
            _ATTR_DEF_APP, "WorkspaceAttributeDefinition"
        )

        flags = {
            a["name"]: a["ai_elicit"]
            for a in repaired.objects.get(pk=standard_row.pk).definition_json["attributes"]
        }
        assert {name for name, flag in flags.items() if flag} >= _ELICITED
        assert flags["description"] is True, "unrelated flags must not move"

        minimal_flags = {
            a["name"]: a["ai_elicit"]
            for a in repaired.objects.get(pk=minimal_row.pk).definition_json["attributes"]
        }
        assert not (_ELICITED & {name for name, flag in minimal_flags.items() if flag})
    finally:
        # Always restore the schema for every other test in the suite.
        executor = MigrationExecutor(connection)
        executor.migrate(latest_target)
