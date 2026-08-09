"""
RequirementBundleToolGroup requirement_bundle.* MCP tests (Requirement
Bundle Export, Plan 1 Task 6).

Exercises both tools through the tool group's ``execute_tool`` entry
(bypassing the full auth pipeline, like test_architecture_decompose_tool.py
and test_ai_derivation_tool_group.py): export of an ALLOCATED_TO-grouped
requirement bundle in all three output formats, depth scoping, and
attribute-schema discovery. No network access.
"""
from __future__ import annotations

import json
import uuid

import pytest

from auth_tenancy.context import AuthContext, AuthMethod
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import (
    Artifact,
    ArchitectureElement,
    Requirement,
    Tenant,
    TraceLink,
    User,
    Workspace,
)
from persistence.tenancy import TenantContext
from traceability.types import LinkType

from mcp_server.tools.requirement_bundle import RequirementBundleToolGroup

_API_KEY = "reqlo_testkey_rb"


@pytest.fixture
def rb_ctx(db):
    """Tenant + workspace + AuthContext with the TenantContext activated."""
    tenant = Tenant.objects.create(name="MCP RB", slug="mcp-rb", is_active=True)
    user = User.objects.create(username="mcprbuser", email="mcprb@t.test", tenant=tenant)
    set_request_tenant(tenant.id)
    TenantContext.set_tenant(tenant.id)
    workspace = Workspace.objects.create(tenant=tenant, name="mcp-rb-ws")
    ctx = AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=("editor",),
        auth_method=AuthMethod.API_KEY,
        api_key_id=None,
    )
    try:
        yield tenant, ctx, workspace
    finally:
        TenantContext.clear_tenant()
        clear_request_tenant()


def _make_element(tenant, workspace, title):
    artifact = Artifact.objects.create(
        workspace=workspace, artifact_type="ArchitectureElement", tenant_id=tenant.id
    )
    return ArchitectureElement.objects.create(
        artifact=artifact, tenant_id=tenant.id, title=title
    )


def _make_requirement(tenant, workspace, title):
    artifact = Artifact.objects.create(
        workspace=workspace, artifact_type="Requirement", tenant_id=tenant.id
    )
    return Requirement.objects.create(
        # ``workspace`` is Requirement's denormalized copy of
        # artifact.workspace_id (#133), which RequirementService populates on
        # every real create. Set it here too so exported rows carry the same
        # shape as production data — bundle export publishes workspace_id.
        artifact=artifact, tenant_id=tenant.id, title=title, workspace=workspace
    )


def _allocate(tenant, source_artifact, target_artifact):
    """Create an ALLOCATED_TO TraceLink (source -> target), matching the
    direction application/tests/test_allocation.py proves for
    Requirement->ArchitectureElement edges (and, by symmetry, for
    ArchitectureElement->ArchitectureElement edges)."""
    return TraceLink.objects.create(
        tenant=tenant,
        source=source_artifact,
        target=target_artifact,
        link_type=LinkType.ALLOCATED_TO.value,
    )


def _exec(group, tool, params, ctx):
    return group.execute_tool(
        tool_name=tool, params=params, auth_context=ctx, api_key=_API_KEY
    )


class TestRequirementBundleExportTool:
    def test_export_returns_json_by_default(self, rb_ctx):
        tenant, ctx, workspace = rb_ctx
        root = _make_element(tenant, workspace, "Root")
        req = _make_requirement(tenant, workspace, "Req A")
        _allocate(tenant, req.artifact, root.artifact)

        result = _exec(
            RequirementBundleToolGroup(),
            "requirement_bundle.export",
            {"root_id": str(root.id), "workspace_id": str(workspace.id)},
            ctx,
        )

        assert result.success is True
        assert "items" in result.data
        assert len(result.data["items"]) == 1
        assert result.data["items"][0]["requirement_id"] == str(req.id)
        assert result.data["truncated_at_depth"] is False

    @pytest.mark.parametrize("filter_mode", [None, "all", "visible"])
    def test_export_payload_survives_stdlib_json_dumps(self, rb_ctx, filter_mode):
        """The MCP transport serialises with the *stdlib* encoder.

        ``protocol_handler`` calls ``json.dumps(result.data, ...)`` directly,
        so any non-primitive left in the payload raises ``TypeError`` and
        propagates as an unhandled 500 — which is exactly what the default
        invocation (no ``format``, no ``filter_mode``) did: ``filter_mode``
        defaults to ``"all"``, whose field set carries raw ``uuid.UUID``
        (``id``, ``workspace_id``) and ``datetime`` (``created_at``,
        ``modified_at``) objects straight out of ``QuerySet.values()``. Every
        pre-existing test asserted on ``result.data`` in-process and never
        serialised it, so nothing caught it. Runs against a real Requirement
        row, not a mock, because the offending values come from the DB
        driver.
        """
        tenant, ctx, workspace = rb_ctx
        root = _make_element(tenant, workspace, "Root")
        req = _make_requirement(tenant, workspace, "Req A")
        _allocate(tenant, req.artifact, root.artifact)

        params = {"root_id": str(root.id), "workspace_id": str(workspace.id)}
        if filter_mode is not None:
            params["filter_mode"] = filter_mode

        result = _exec(
            RequirementBundleToolGroup(), "requirement_bundle.export", params, ctx
        )

        assert result.success is True
        encoded = json.dumps(result.data)  # must not raise
        decoded = json.loads(encoded)
        fields = decoded["items"][0]["fields"]
        assert fields["id"] == str(req.id)
        assert fields["workspace_id"] == str(workspace.id)
        assert isinstance(fields["created_at"], str)
        assert isinstance(fields["modified_at"], str)

    @pytest.mark.parametrize("output_format", ["markdown", "csv"])
    def test_export_non_json_payload_survives_stdlib_json_dumps(
        self, rb_ctx, output_format
    ):
        """Same guard for the markdown/CSV branches, whose payloads wrap a
        plain string but are serialised by the same transport."""
        tenant, ctx, workspace = rb_ctx
        root = _make_element(tenant, workspace, "Root")
        req = _make_requirement(tenant, workspace, "Req A")
        _allocate(tenant, req.artifact, root.artifact)

        result = _exec(
            RequirementBundleToolGroup(),
            "requirement_bundle.export",
            {
                "root_id": str(root.id),
                "workspace_id": str(workspace.id),
                "format": output_format,
            },
            ctx,
        )

        assert result.success is True
        json.dumps(result.data)  # must not raise

    def test_export_depth_param_scopes_to_direct_children(self, rb_ctx):
        tenant, ctx, workspace = rb_ctx
        root = _make_element(tenant, workspace, "Root")
        child = _make_element(tenant, workspace, "Child")
        _allocate(tenant, child.artifact, root.artifact)
        req = _make_requirement(tenant, workspace, "Req under child")
        _allocate(tenant, req.artifact, child.artifact)

        result0 = _exec(
            RequirementBundleToolGroup(),
            "requirement_bundle.export",
            {"root_id": str(root.id), "workspace_id": str(workspace.id), "depth": 0},
            ctx,
        )
        assert result0.success is True
        assert result0.data["items"] == []

        result1 = _exec(
            RequirementBundleToolGroup(),
            "requirement_bundle.export",
            {"root_id": str(root.id), "workspace_id": str(workspace.id), "depth": 1},
            ctx,
        )
        assert result1.success is True
        assert len(result1.data["items"]) == 1
        assert result1.data["items"][0]["requirement_id"] == str(req.id)

    def test_export_unknown_root_returns_not_found_error(self, rb_ctx):
        _tenant, ctx, _workspace = rb_ctx

        result = _exec(
            RequirementBundleToolGroup(),
            "requirement_bundle.export",
            {"root_id": str(uuid.uuid4()), "workspace_id": str(uuid.uuid4())},
            ctx,
        )

        assert result.success is False
        assert result.error_code == "NOT_FOUND"

    def test_export_invalid_format_returns_validation_error(self, rb_ctx):
        tenant, ctx, workspace = rb_ctx
        root = _make_element(tenant, workspace, "Root")

        result = _exec(
            RequirementBundleToolGroup(),
            "requirement_bundle.export",
            {"root_id": str(root.id), "workspace_id": str(workspace.id), "format": "xml"},
            ctx,
        )

        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"

    def test_export_invalid_depth_returns_validation_error(self, rb_ctx):
        tenant, ctx, workspace = rb_ctx
        root = _make_element(tenant, workspace, "Root")

        result = _exec(
            RequirementBundleToolGroup(),
            "requirement_bundle.export",
            {"root_id": str(root.id), "workspace_id": str(workspace.id), "depth": "not-a-number"},
            ctx,
        )

        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"

    def test_export_depth_over_max_returns_validation_error(self, rb_ctx):
        """Parity with rest_api's test_depth_over_max_returns_400 (Task 5):
        depth beyond RequirementBundleQueryService.MAX_DEPTH (20) is rejected
        by BundleDepthExceededError, a ValidationError subclass."""
        tenant, ctx, workspace = rb_ctx
        root = _make_element(tenant, workspace, "Root")

        result = _exec(
            RequirementBundleToolGroup(),
            "requirement_bundle.export",
            {"root_id": str(root.id), "workspace_id": str(workspace.id), "depth": 99},
            ctx,
        )

        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"

    def test_export_custom_filter_mode_unknown_field_returns_validation_error(self, rb_ctx):
        """filter_mode='custom' with a field name not in REQUIREMENT_ALL_FIELDS
        must fail loudly (typo protection), not silently drop it."""
        tenant, ctx, workspace = rb_ctx
        root = _make_element(tenant, workspace, "Root")

        result = _exec(
            RequirementBundleToolGroup(),
            "requirement_bundle.export",
            {
                "root_id": str(root.id),
                "workspace_id": str(workspace.id),
                "filter_mode": "custom",
                "fields": ["not_a_real_field"],
            },
            ctx,
        )

        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"

    def test_export_markdown_format(self, rb_ctx):
        tenant, ctx, workspace = rb_ctx
        root = _make_element(tenant, workspace, "Root")
        req = _make_requirement(tenant, workspace, "Req A")
        _allocate(tenant, req.artifact, root.artifact)

        result = _exec(
            RequirementBundleToolGroup(),
            "requirement_bundle.export",
            {"root_id": str(root.id), "workspace_id": str(workspace.id), "format": "markdown"},
            ctx,
        )

        assert result.success is True
        assert result.data["format"] == "markdown"
        assert "# Requirement Bundle" in result.data["content"]

    def test_export_csv_format(self, rb_ctx):
        tenant, ctx, workspace = rb_ctx
        root = _make_element(tenant, workspace, "Root")
        req = _make_requirement(tenant, workspace, "Req A")
        _allocate(tenant, req.artifact, root.artifact)

        result = _exec(
            RequirementBundleToolGroup(),
            "requirement_bundle.export",
            {"root_id": str(root.id), "workspace_id": str(workspace.id), "format": "csv"},
            ctx,
        )

        assert result.success is True
        assert result.data["format"] == "csv"
        assert "requirement_id" in result.data["content"]
        assert str(req.id) in result.data["content"]

    def test_export_custom_filter_mode_with_fields(self, rb_ctx):
        tenant, ctx, workspace = rb_ctx
        root = _make_element(tenant, workspace, "Root")
        req = _make_requirement(tenant, workspace, "Req A")
        _allocate(tenant, req.artifact, root.artifact)

        result = _exec(
            RequirementBundleToolGroup(),
            "requirement_bundle.export",
            {
                "root_id": str(root.id),
                "workspace_id": str(workspace.id),
                "filter_mode": "custom",
                "fields": ["title"],
            },
            ctx,
        )

        assert result.success is True
        assert set(result.data["items"][0]["fields"].keys()) == {"title"}


class TestAttributeSchemaTool:
    def test_attribute_schema_returns_requirement_fields(self, rb_ctx):
        _tenant, ctx, _workspace = rb_ctx

        result = _exec(
            RequirementBundleToolGroup(),
            "requirement_bundle.attribute_schema",
            {"entity_type": "Requirement"},
            ctx,
        )

        assert result.success is True
        names = {row["attribute_name"] for row in result.data["attributes"]}
        assert "title" in names
        assert all(row["entity_type"] == "Requirement" for row in result.data["attributes"])

    def test_attribute_schema_omitted_entity_type_returns_all_known_types(self, rb_ctx):
        _tenant, ctx, _workspace = rb_ctx

        result = _exec(
            RequirementBundleToolGroup(),
            "requirement_bundle.attribute_schema",
            {},
            ctx,
        )

        assert result.success is True
        assert result.data["count"] == len(result.data["attributes"])
        assert result.data["count"] > 0

    def test_attribute_schema_unknown_entity_type_returns_not_found_error(self, rb_ctx):
        _tenant, ctx, _workspace = rb_ctx

        result = _exec(
            RequirementBundleToolGroup(),
            "requirement_bundle.attribute_schema",
            {"entity_type": "Bogus"},
            ctx,
        )

        assert result.success is False
        assert result.error_code == "NOT_FOUND"


class TestToolSchemas:
    def test_get_tool_schemas_matches_tool_map(self):
        group = RequirementBundleToolGroup()
        schema_names = {schema["name"] for schema in group.get_tool_schemas()}
        assert schema_names == set(group._TOOL_MAP.keys())
