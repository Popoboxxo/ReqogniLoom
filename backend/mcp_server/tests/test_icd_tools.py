"""Epic #934 WS1 — MCP tool group for ICD (``icd.*``).

Drives the real ``ToolRegistry.dispatch_request`` stack (API-key auth -> RBAC ->
workspace gate -> tool group -> ``icd.services``) against a real DB, covering:

* ``icd.create`` / ``icd.read`` round-trip incl. ``custom_fields``
  (REQ-L2-AS-037 — the extended map lives on the backing Artifact);
* ``icd.update`` merge semantics for the extended map;
* ``icd.query`` listing;
* the shared attribute-definition gate rejecting an out-of-rule extended value;
* RBAC parity: a Viewer may read but not write.

The fixtures come from ``mcp_server.tests.conftest`` (real Tenant/Workspace/
UserRole/ApiKey wiring), so no collaborator is mocked.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

import pytest
from django.core.management import call_command

from attribute_definitions.global_definition_store import GlobalAttributeDefinitionStore
from attribute_definitions.schema import PRESETS, stored_attributes
from mcp_server.tool_registry import ToolRegistry

pytestmark = pytest.mark.django_db


def _dispatch(tool_name: str, params: Dict[str, Any], api_key: str):
    """Run one dispatch through a fully real (unmocked) ToolRegistry."""
    return ToolRegistry().dispatch_request(
        tool_name=tool_name, params=params, api_key=api_key
    )


def _create_architecture_pair(workspace_id: str, api_key: str) -> tuple[str, str]:
    """Create two ArchitectureElements (root + child) for use as ICD endpoints."""
    root = _dispatch(
        "architecture.create",
        {
            "workspace_id": workspace_id,
            "title": "icd-root",
            "element_type": "block",
        },
        api_key,
    )
    assert root.success is True, root.message
    root_id = root.data["architecture_element"]["id"]

    child = _dispatch(
        "architecture.create",
        {
            "workspace_id": workspace_id,
            "title": "icd-child",
            "element_type": "block",
            "parent_id": root_id,
        },
        api_key,
    )
    assert child.success is True, child.message
    return root_id, child.data["architecture_element"]["id"]


def _create_icd(
    workspace_id: str,
    api_key: str,
    *,
    custom_fields: Optional[Dict[str, Any]] = None,
):
    source_id, target_id = _create_architecture_pair(workspace_id, api_key)
    params: Dict[str, Any] = {
        "workspace_id": workspace_id,
        "name": "contract-matrix-icd",
        "source_element_id": source_id,
        "target_element_id": target_id,
    }
    if custom_fields is not None:
        params["custom_fields"] = custom_fields
    return _dispatch("icd.create", params, api_key)


def _inject_icd_probe(tenant_id: Any) -> None:
    """Add a validated ``ws0_probe`` extended attribute to every Icd definition.

    Mirrors ``test_transport_contract_matrix._inject_probe_attribute`` for the
    single item type this suite exercises, so an out-of-rule value has a rule to
    violate.
    """
    store = GlobalAttributeDefinitionStore()
    probe = {
        "name": "ws0_probe",
        "kind": "extended",
        "type": "text",
        "label": {"de": "WS1 Vertragsprobe", "en": "WS1 contract probe"},
        "validation": {"length": 64},
        "order": 9999,
    }
    for preset in PRESETS:
        row = store.get(tenant_id, "Icd", preset)
        assert row is not None, f"bootstrap produced no Icd/{preset} definition"
        attributes = stored_attributes(row.definition_json)
        if any(a["name"] == "ws0_probe" for a in attributes):
            continue
        attributes.append(dict(probe))
        store.update(tenant_id, "Icd", preset, attributes)


def test_icd_create_and_read_round_trip_custom_fields(
    e2e_workspace, e2e_userrole_member, e2e_api_key_member
) -> None:
    created = _create_icd(
        str(e2e_workspace.id),
        e2e_api_key_member,
        custom_fields={"ws0_probe": "probe-value"},
    )
    assert created.success is True, created.message
    icd_id = created.data["icd"]["id"]
    assert created.data["icd"]["custom_fields"] == {"ws0_probe": "probe-value"}

    read = _dispatch("icd.read", {"id": icd_id}, e2e_api_key_member)
    assert read.success is True, read.message
    assert read.data["icd"]["custom_fields"] == {"ws0_probe": "probe-value"}
    assert read.data["icd"]["workspace_id"] == str(e2e_workspace.id)


def test_icd_update_replaces_custom_fields_and_round_trips(
    e2e_workspace, e2e_userrole_member, e2e_api_key_member
) -> None:
    created = _create_icd(
        str(e2e_workspace.id),
        e2e_api_key_member,
        custom_fields={"ws0_probe": "before"},
    )
    assert created.success is True, created.message
    icd_id = created.data["icd"]["id"]

    updated = _dispatch(
        "icd.update",
        {
            "id": icd_id,
            "semantic_description": "updated contract",
            "custom_fields": {"ws0_probe": "after"},
        },
        e2e_api_key_member,
    )
    assert updated.success is True, updated.message
    assert updated.data["icd"]["custom_fields"] == {"ws0_probe": "after"}

    read = _dispatch("icd.read", {"id": icd_id}, e2e_api_key_member)
    assert read.success is True, read.message
    assert read.data["icd"]["custom_fields"] == {"ws0_probe": "after"}
    assert read.data["icd"]["semantic_description"] == "updated contract"


def test_icd_query_lists_workspace_icds(
    e2e_workspace, e2e_userrole_member, e2e_api_key_member
) -> None:
    created = _create_icd(str(e2e_workspace.id), e2e_api_key_member)
    assert created.success is True, created.message

    listed = _dispatch(
        "icd.query", {"workspace_id": str(e2e_workspace.id)}, e2e_api_key_member
    )
    assert listed.success is True, listed.message
    ids = {row["id"] for row in listed.data["icds"]}
    assert created.data["icd"]["id"] in ids
    assert listed.data["count"] == len(listed.data["icds"])


def test_icd_create_rejects_out_of_rule_extended_value(
    e2e_tenant, e2e_workspace, e2e_userrole_member, e2e_api_key_member
) -> None:
    call_command("bootstrap_attribute_definitions", tenant=str(e2e_tenant.id))
    _inject_icd_probe(e2e_tenant.id)

    rejected = _create_icd(
        str(e2e_workspace.id),
        e2e_api_key_member,
        custom_fields={"ws0_probe": "x" * 200},
    )
    assert rejected.success is False
    assert rejected.error_code == "VALIDATION_ERROR"


def test_icd_read_allowed_and_write_denied_for_viewer(
    e2e_workspace,
    e2e_userrole_member,
    e2e_userrole_viewer,
    e2e_api_key_member,
    e2e_api_key_viewer,
) -> None:
    created = _create_icd(str(e2e_workspace.id), e2e_api_key_member)
    assert created.success is True, created.message
    icd_id = created.data["icd"]["id"]

    read = _dispatch("icd.read", {"id": icd_id}, e2e_api_key_viewer)
    assert read.success is True, read.message

    denied = _dispatch(
        "icd.update",
        {"id": icd_id, "semantic_description": "viewer write attempt"},
        e2e_api_key_viewer,
    )
    assert denied.success is False
    assert denied.error_code == "PERMISSION_DENIED"
