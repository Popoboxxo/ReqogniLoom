"""P1 ratchet: the artifact-transfer contract must cover every other registry.

Failures here mean a new artifact/entity type was added to one of the existing
inventories without being added to the transfer contract — exactly the drift
that made CSV export/import cover 3–7 of 15 artifact types and left ~17 REST/MCP
entities without any export path (see docs/plans/2026-11-21-artifact-transfer-plan.md, F1/F3).
"""
from __future__ import annotations

import pytest

from application.artifact_transfer_contract import (
    ARTIFACT_RELATIONS,
    REMAP_ALWAYS,
    SNAPSHOT_EXCLUSIONS,
    TRANSFER_SPECS,
    ArtifactTransferSpec,
    artifact_specs,
    missing_artifact_types,
    reqif_specs,
    spec_for_type,
)
from application.export_service import ENTITY_FIELD_SPECS
from mcp_server.tests.entity_surface_matrix import ENTITY_SPECS
from persistence.artifact_backing import ARTIFACT_TYPE_MODELS

_VALID_SCOPES = {"artifact", "workspace_config", "global_config"}
_RECONCILE_STATES = {"outdated", "deprecated", None}


def test_contract_covers_every_rest_mcp_entity() -> None:
    assert set(TRANSFER_SPECS) == set(ENTITY_SPECS), (
        "transfer contract and REST/MCP entity surface drifted: "
        f"contract-only={sorted(set(TRANSFER_SPECS) - set(ENTITY_SPECS))}, "
        f"surface-only={sorted(set(ENTITY_SPECS) - set(TRANSFER_SPECS))}"
    )


def test_contract_covers_every_artifact_backed_type() -> None:
    assert missing_artifact_types() == ()
    for type_name in ARTIFACT_TYPE_MODELS:
        spec = spec_for_type(type_name)
        assert spec is not None
        assert spec.is_artifact, f"{type_name} must be an artifact-scoped transfer entity"
        assert spec.roundtrip is True


def test_current_csv_registry_is_a_subset() -> None:
    """The 7 existing CSV types must remain round-trippable (no silent shrink)."""
    assert set(ENTITY_FIELD_SPECS) <= {s.type_name for s in artifact_specs()}
    for type_name in ENTITY_FIELD_SPECS:
        assert spec_for_type(type_name).roundtrip is True  # type: ignore[union-attr]


@pytest.mark.parametrize("key,spec", sorted(TRANSFER_SPECS.items()))
def test_spec_shape(key: str, spec: ArtifactTransferSpec) -> None:
    assert spec.entity_key == key
    assert spec.type_name
    assert spec.scope in _VALID_SCOPES
    assert spec.formats, f"{key} has no export format"
    assert len(spec.formats) == len(set(spec.formats)), f"{key} has duplicate formats"
    assert spec.status_reconcile in _RECONCILE_STATES
    assert spec.exclusions == SNAPSHOT_EXCLUSIONS
    assert isinstance(spec.roundtrip, bool)


def test_identity_columns_are_always_remapped() -> None:
    """D12b: no snapshot may overwrite target tenant/workspace/artifact identity."""
    assert {"tenant_id", "workspace_id", "artifact_id"} <= REMAP_ALWAYS
    assert "id" not in REMAP_ALWAYS  # D12: source id is authoritative in updates
    assert "version" not in REMAP_ALWAYS


def test_all_relations_are_in_scope() -> None:
    """D10: comments and test runs are part of the relation graph, not optional."""
    assert {"trace_links", "parent_hierarchy", "allocation", "group_membership"} <= set(
        ARTIFACT_RELATIONS
    )
    assert {"comments", "test_runs"} <= set(ARTIFACT_RELATIONS)
    for spec in artifact_specs():
        assert set(ARTIFACT_RELATIONS) <= set(spec.relations)


def test_reqif_mapping_is_standard_conformant_and_explicit() -> None:
    """D14d: only the four mapped types carry ReqIF; no non-standard type leaks in."""
    assert {s.type_name for s in reqif_specs()} == {
        "StakeholderNeed",
        "Requirement",
        "TestCase",
        "Icd",
    }
    for spec in reqif_specs():
        assert spec.roundtrip is True
        assert spec.is_artifact


def test_non_artifact_scopes_are_explicit() -> None:
    """The non-artifact (configuration) entities are named, never implicit."""
    config = [s for s in TRANSFER_SPECS.values() if not s.is_artifact]
    assert {s.entity_key for s in config} == {"workspace", "link_type", "workflow_default"}
    assert all(s.roundtrip is False for s in config)
    assert len(artifact_specs()) == 22
