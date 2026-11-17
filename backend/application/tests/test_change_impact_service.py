"""Tests for the R2S-003 change-impact query façade.

Pins the exact persistence filters, the preserved ``TenantContext`` arming
and the byte-identical DTO shapes that ``context.change_impact`` emits.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

from application.change_impact_service import (
    ChangeImpactService,
    legacy_decomposition_children,
    legacy_get_anchor,
    legacy_resolve_architecture_neighbors,
    legacy_resolve_mirrored_neighbors,
)


class _FakeDoesNotExist(Exception):
    """Stand-in for Django's ``Model.DoesNotExist``."""


class _FakeModel:
    """Minimal model stand-in carrying a real exception class + manager."""

    DoesNotExist = _FakeDoesNotExist
    objects = MagicMock()


def _neighbor(
    artifact_id: object, *, link_type: str = "verifies", relation: str = "upstream"
) -> dict[str, object]:
    return {
        "artifact_id": artifact_id,
        "entity_type": "TestCase",
        "link_type": link_type,
        "relation": relation,
    }


# ---------------------------------------------------------------------------
# get_anchor — TenantContext arming + tenant-fenced lookup + NOT_FOUND signal
# ---------------------------------------------------------------------------


def test_get_anchor_arms_tenant_context_and_filters_by_tenant() -> None:
    entity_type, entity_id, tenant_id = "Requirement", uuid4(), uuid4()
    fake = _FakeModel()
    entity = object()
    fake.objects.get.return_value = entity
    with patch(
        "application.change_impact_service._ANCHOR_MODELS",
        {entity_type: fake},
    ), patch(
        "application.change_impact_service.TenantContext.set_tenant"
    ) as set_tenant:
        assert legacy_get_anchor(entity_type, entity_id, tenant_id=tenant_id) is entity
    set_tenant.assert_called_once_with(tenant_id)
    fake.objects.get.assert_called_once_with(id=entity_id, tenant_id=tenant_id)


def test_get_anchor_returns_none_for_missing_row() -> None:
    entity_id, tenant_id = uuid4(), uuid4()
    fake = _FakeModel()
    fake.objects.get.side_effect = _FakeDoesNotExist()
    with patch(
        "application.change_impact_service._ANCHOR_MODELS",
        {"Requirement": fake},
    ):
        assert legacy_get_anchor("Requirement", entity_id, tenant_id=tenant_id) is None


# ---------------------------------------------------------------------------
# decomposition children
# ---------------------------------------------------------------------------


def test_decomposition_children_exact_query_and_dto() -> None:
    entity_id, tenant_id = uuid4(), uuid4()
    child = MagicMock()
    child.artifact_id = uuid4()
    with patch("application.change_impact_service.ArchitectureElement") as model:
        model.objects.filter.return_value = [child]
        children = legacy_decomposition_children(
            entity_id, tenant_id=tenant_id
        )
    model.objects.filter.assert_called_once_with(
        parent_id=entity_id, tenant_id=tenant_id
    )
    assert children == [
        {
            "artifact_id": child.artifact_id,
            "entity_type": "ArchitectureElement",
            "link_type": "decomposes",
            "relation": "child",
        }
    ]


# ---------------------------------------------------------------------------
# mirrored neighbours — WorkflowItemState resolution + exact DTO
# ---------------------------------------------------------------------------


def test_resolve_mirrored_neighbors_dto() -> None:
    art_id, business_id = uuid4(), uuid4()
    fake = _FakeModel()
    fake.objects.filter.return_value.values.return_value = [
        {"id": business_id, "artifact_id": art_id, "title": "Verifying Test"}
    ]
    with patch(
        "application.change_impact_service._MIRRORED_MODELS", {"TestCase": fake}
    ), patch("workflow.state_reader.current_states", return_value={}) as states, patch(
        "workflow.state_reader.initial_state", return_value="draft"
    ) as initial:
        resolved = legacy_resolve_mirrored_neighbors(
            [_neighbor(art_id)], "TestCase"
        )
    fake.objects.filter.assert_called_once_with(artifact_id__in=[art_id])
    fake.objects.filter.return_value.values.assert_called_once_with(
        "id", "artifact_id", "title"
    )
    states.assert_called_once()
    initial.assert_called_once_with("TestCase")
    assert resolved == [
        {
            "id": str(business_id),
            "entity_type": "TestCase",
            "title": "Verifying Test",
            "link_type": "verifies",
            "relation": "upstream",
            "outdated": False,
        }
    ]


def test_resolve_mirrored_neighbors_skips_unresolved_rows() -> None:
    fake = _FakeModel()
    fake.objects.filter.return_value.values.return_value = []
    with patch(
        "application.change_impact_service._MIRRORED_MODELS", {"TestCase": fake}
    ), patch("workflow.state_reader.current_states", return_value={}), patch(
        "workflow.state_reader.initial_state", return_value="draft"
    ):
        assert legacy_resolve_mirrored_neighbors([_neighbor(uuid4())], "TestCase") == []


# ---------------------------------------------------------------------------
# architecture neighbours — outdated set + exact DTO
# ---------------------------------------------------------------------------


def test_resolve_architecture_neighbors_dto() -> None:
    art_id, business_id, tenant_id = uuid4(), uuid4(), uuid4()
    with patch("application.change_impact_service.ArchitectureElement") as model, patch(
        "workflow.services.outdated_item_ids", return_value=[business_id]
    ) as outdated:
        model.objects.filter.return_value.values.return_value = [
            {"id": business_id, "artifact_id": art_id, "title": "Child"}
        ]
        neighbor = {
            "artifact_id": art_id,
            "entity_type": "ArchitectureElement",
            "link_type": "decomposes",
            "relation": "child",
        }
        resolved = legacy_resolve_architecture_neighbors(
            [neighbor], tenant_id=tenant_id
        )
    outdated.assert_called_once_with("ArchitectureElement", tenant_id=tenant_id)
    model.objects.filter.assert_called_once_with(artifact_id__in=[art_id])
    assert resolved == [
        {
            "id": str(business_id),
            "entity_type": "ArchitectureElement",
            "title": "Child",
            "link_type": "decomposes",
            "relation": "child",
            "outdated": True,
        }
    ]


# ---------------------------------------------------------------------------
# Façade delegates to the relocated queries
# ---------------------------------------------------------------------------


def test_facade_delegates_to_legacy_queries() -> None:
    service = ChangeImpactService()
    entity_id, tenant_id, art_id = uuid4(), uuid4(), uuid4()
    neighbors = [_neighbor(art_id)]
    with patch(
        "application.change_impact_service.legacy_get_anchor", return_value=None
    ) as anchor, patch(
        "application.change_impact_service.legacy_decomposition_children",
        return_value=[],
    ) as children, patch(
        "application.change_impact_service.legacy_resolve_mirrored_neighbors",
        return_value=[],
    ) as mirrored, patch(
        "application.change_impact_service.legacy_resolve_architecture_neighbors",
        return_value=[],
    ) as arch:
        assert service.get_anchor("Requirement", entity_id, tenant_id=tenant_id) is None
        assert service.decomposition_children(entity_id, tenant_id=tenant_id) == []
        assert service.resolve_mirrored_neighbors(neighbors, "TestCase") == []
        assert service.resolve_architecture_neighbors(neighbors, tenant_id=tenant_id) == []
    anchor.assert_called_once_with("Requirement", entity_id, tenant_id=tenant_id)
    children.assert_called_once_with(entity_id, tenant_id=tenant_id)
    mirrored.assert_called_once_with(neighbors, "TestCase")
    arch.assert_called_once_with(neighbors, tenant_id=tenant_id)
