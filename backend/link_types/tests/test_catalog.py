"""Workspace catalog resolution + always-on endpoint validation."""
from __future__ import annotations

import uuid

import pytest

from link_types.builtin import builtin_definition
from link_types.catalog import (
    get_definition,
    invalidate_workspace,
    resolve_catalog,
    validate_link_pair,
)
from link_types.models import WorkspaceLinkTypeDefinition
from persistence.errors import ValidationError
from persistence.models import Tenant
from persistence.tenancy import TenantContext


@pytest.fixture
def workspace(db):
    """Activate a real tenant row — ``tenant`` is a PROTECT FK, not a loose UUID.

    Deviation from the plan draft (bare ``uuid.uuid4()`` tenant id), same class
    of issue already documented for Task 1/Task 2 fixtures.
    """
    tenant = Tenant.objects.create(name="LinkType Catalog Tests", slug=f"lt-cat-{uuid.uuid4().hex}")
    TenantContext.set_tenant(tenant.id)
    ws = uuid.uuid4()
    for key in ("derives-from", "verifies", "allocated-to", "references", "diagram-ref"):
        WorkspaceLinkTypeDefinition.objects.create(
            workspace_id=ws, key=key, definition_json=builtin_definition(key)
        )
    invalidate_workspace(str(ws))
    yield ws
    invalidate_workspace(str(ws))
    TenantContext.clear_tenant()


@pytest.mark.django_db
def test_resolve_returns_every_seeded_key(workspace):
    assert set(resolve_catalog(workspace)) == {
        "derives-from",
        "verifies",
        "allocated-to",
        "references",
        "diagram-ref",
    }


@pytest.mark.django_db
def test_inactive_definitions_are_excluded(workspace):
    row = WorkspaceLinkTypeDefinition.objects.get(workspace_id=workspace, key="verifies")
    row.definition_json = {**row.definition_json, "active": False}
    row.save(update_fields=["definition_json"])
    invalidate_workspace(str(workspace))
    assert "verifies" not in resolve_catalog(workspace)


@pytest.mark.django_db
def test_get_definition_returns_none_for_an_unknown_key(workspace):
    assert get_definition(workspace, "conflicts-with") is None


@pytest.mark.django_db
def test_a_valid_pair_passes(workspace):
    validate_link_pair(
        workspace, "verifies", "TestCase", "Requirement", manual=True
    )


@pytest.mark.django_db
def test_an_invalid_pair_is_rejected_and_lists_the_allowed_pairs(workspace):
    with pytest.raises(ValidationError) as exc:
        validate_link_pair(
            workspace, "verifies", "Risk", "Requirement", manual=True
        )
    message = str(exc.value)
    assert "verifies" in message
    assert "TestCase->Requirement" in message


@pytest.mark.django_db
def test_validation_applies_to_non_core_artifact_types_too(workspace):
    """The old SE_CORE_ARTIFACT_TYPES escape hatch is gone.

    Risk was outside the core set, so `verifies` from a Risk used to pass
    unchecked (audit finding U2). It must now be rejected — covered above —
    and an artifact type nobody constrained must be rejected as well.
    """
    with pytest.raises(ValidationError):
        validate_link_pair(
            workspace, "derives-from", "Issue", "Interview", manual=True
        )


@pytest.mark.django_db
def test_wildcards_match_any_artifact_type(workspace):
    validate_link_pair(workspace, "references", "Requirement", "Diagram", manual=True)
    validate_link_pair(workspace, "references", "Risk", "Diagram", manual=True)


@pytest.mark.django_db
def test_subtyped_artifact_types_are_normalized(workspace):
    """'TestCase:unit' must match a 'TestCase' pair."""
    validate_link_pair(
        workspace, "verifies", "TestCase:unit", "Requirement", manual=True
    )


@pytest.mark.django_db
def test_unknown_link_type_is_rejected_and_lists_the_catalog(workspace):
    with pytest.raises(ValidationError) as exc:
        validate_link_pair(
            workspace, "satisfies", "ArchitectureElement", "Requirement", manual=True
        )
    message = str(exc.value)
    assert "satisfies" in message
    assert "derives-from" in message


@pytest.mark.django_db
def test_system_owned_types_are_rejected_on_the_manual_path_only(workspace):
    with pytest.raises(ValidationError, match="system-managed"):
        validate_link_pair(workspace, "diagram-ref", "Diagram", "Requirement", manual=True)
    validate_link_pair(workspace, "diagram-ref", "Diagram", "Requirement", manual=False)


@pytest.mark.django_db
def test_a_customized_workspace_row_overrides_the_builtin_pairs(workspace):
    row = WorkspaceLinkTypeDefinition.objects.get(workspace_id=workspace, key="verifies")
    row.definition_json = {
        **row.definition_json,
        "allowed_pairs": [{"source_type": "Risk", "target_type": "Requirement"}],
    }
    row.is_customized = True
    row.save(update_fields=["definition_json", "is_customized"])
    invalidate_workspace(str(workspace))

    validate_link_pair(workspace, "verifies", "Risk", "Requirement", manual=True)
    with pytest.raises(ValidationError):
        validate_link_pair(workspace, "verifies", "TestCase", "Requirement", manual=True)


@pytest.mark.django_db
def test_a_workspace_without_any_rows_resolves_to_an_empty_catalog():
    tenant = Tenant.objects.create(name="Empty Catalog Test", slug=f"lt-cat-{uuid.uuid4().hex}")
    TenantContext.set_tenant(tenant.id)
    try:
        assert resolve_catalog(uuid.uuid4()) == {}
    finally:
        TenantContext.clear_tenant()
