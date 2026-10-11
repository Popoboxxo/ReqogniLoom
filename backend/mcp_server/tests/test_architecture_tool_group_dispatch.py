"""
Dispatch-level tests for the ArchitectureToolGroup (COMP-MC-004, 8 tools).

``test_tool_groups.py`` pins the handlers against mocked services and
``test_own_tool_groups_lifecycle.py`` drives the lifecycle by calling the
PRIVATE handlers directly. What neither covers is the public boundary a real
MCP call arrives through: this module drives every ``architecture.*`` tool
through :meth:`BaseToolGroup.execute_tool` with a real database:

* real-DB round trips (create -> get -> query -> update -> link ->
  outdate/reactivate),
* parameter validation for every tool's required ``id`` / ``arch_id`` /
  ``target_id`` / ``link_type`` / ``title`` / ``workspace_id`` (missing value
  and non-UUID value),
* optimistic-lock and lifecycle failures (``expected_version`` conflict ->
  VALIDATION_ERROR, reactivate on an active item -> INVALID_STATE),
* the RBAC fence at the registry layer (viewer API key: write refused,
  read allowed),
* the cross-tenant read fence (another tenant's id -> NOT_FOUND, another
  tenant's workspace -> empty list),
* service-error -> MCP-code mapping (NotFoundError -> NOT_FOUND,
  ValidationError -> VALIDATION_ERROR, PermissionDeniedError ->
  PERMISSION_DENIED, unmapped exception -> masked INTERNAL_ERROR),
* the CWE-209 masking contract: an unmapped error never leaks its message.

The two ``architecture.decompose*`` tools are deliberately excluded — they
have dedicated coverage in ``test_architecture_decompose_tool.py``.

The tenant context is armed through ``persistence.middleware.set_request_tenant``
(thread-local + PostgreSQL RLS session variable), exactly like the production
``ToolRegistry.dispatch_request`` does.

leaf_id : COMP-MC-004
req_id  : REQ-L2-MC-002
"""
from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from application.architecture_service import ArchitectureService
from application.base import (
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from auth_tenancy.context import AuthContext, AuthMethod
from link_types.workspace_store import provision_workspace_link_types
from mcp_server.tool_registry import ToolRegistry
from mcp_server.tools.architecture import ArchitectureToolGroup
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, TraceLink, User
from persistence.models import Workspace as PersistenceWorkspace
from traceability.types import LinkType
from workflow.services import create_default_workflow

pytestmark = pytest.mark.django_db

_API_KEY = "reqlo_testkey_arch_dispatch"

# Tools whose handler validates a required ``id`` parameter first.
_ID_TOOLS = (
    "architecture.get",
    "architecture.update",
    "architecture.outdate",
    "architecture.reactivate",
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def caller():
    """Tenant + workspace + workflows + editor AuthContext, tenant-scoped.

    Both isolation layers are armed (``set_request_tenant``) so the RLS fence
    of the test database applies while the tool runs. The ArchitectureElement
    and Requirement workflows are provisioned (lifecycle tools, link target)
    and the link-type catalog is seeded (trace links are always validated).
    """
    suffix = uuid4().hex[:8]
    tenant = Tenant.objects.create(
        name=f"MCP arch dispatch {suffix}", slug=f"mcp-arch-{suffix}"
    )
    user = User.objects.create(
        username=f"mcparch-{suffix}-user",
        email=f"mcparch-{suffix}@t.test",
        tenant=tenant,
    )
    set_request_tenant(tenant.id)
    try:
        workspace = PersistenceWorkspace.objects.create(
            tenant=tenant, name=f"ws-{suffix}"
        )
        provision_workspace_link_types(
            workspace_id=workspace.id, tenant_id=tenant.id
        )
        create_default_workflow(
            workspace_id=workspace.id,
            preset="architecture_default",
            item_type="ArchitectureElement",
            tenant_id=tenant.id,
        )
        ctx = AuthContext(
            user_id=user.id,
            tenant_id=tenant.id,
            active_roles=("editor",),
            auth_method=AuthMethod.API_KEY,
            api_key_id=None,
        )
        yield tenant, workspace, ctx, user.id
    finally:
        clear_request_tenant()


def _exec(group, tool, params, ctx):
    """Run *tool* through the public tool-group dispatch interface."""
    return group.execute_tool(
        tool_name=tool, params=params, auth_context=ctx, api_key=_API_KEY
    )


def _create_element(caller, title="Dispatch Element", **extra):
    """architecture.create through the public interface; returns the payload.

    I5 allows exactly one root per workspace, so the first element becomes the
    root and every further element attaches under it.
    """
    _tenant, workspace, ctx, _user_id = caller
    group = ArchitectureToolGroup()
    existing = _exec(
        group,
        "architecture.query",
        {"workspace_id": str(workspace.id), "include_outdated": True},
        ctx,
    )
    params = {"workspace_id": str(workspace.id), "title": title}
    if existing.data["count"]:
        params["parent_id"] = existing.data["architecture_elements"][0]["id"]
    params.update(extra)
    result = _exec(group, "architecture.create", params, ctx)
    assert result.success is True, result.message
    return result.data["architecture_element"]


def _viewer_ctx(tenant, user_id) -> AuthContext:
    """A viewer context inside the same tenant."""
    return AuthContext(
        user_id=user_id,
        tenant_id=tenant.id,
        active_roles=("viewer",),
        auth_method=AuthMethod.API_KEY,
        api_key_id=None,
    )


def _make_foreign_element(caller, title="Foreign Element"):
    """An element in ANOTHER tenant, created under that tenant's own context.

    Returns ``(element_id, foreign_ctx, foreign_tenant_id)``. Re-arms the
    caller's tenant afterwards so the RLS session variable of the shared test
    connection points back at the caller when the dispatch runs.
    """
    tenant, _workspace, _ctx, _user_id = caller
    suffix = uuid4().hex[:8]
    foreign_tenant = Tenant.objects.create(
        name=f"MCP arch foreign {suffix}", slug=f"mcp-arch-f-{suffix}"
    )
    foreign_user = User.objects.create(
        username=f"mcparchf-{suffix}-user",
        email=f"mcparchf-{suffix}@t.test",
        tenant=foreign_tenant,
    )
    foreign_ctx = AuthContext(
        user_id=foreign_user.id,
        tenant_id=foreign_tenant.id,
        active_roles=("editor",),
        auth_method=AuthMethod.API_KEY,
        api_key_id=None,
    )
    set_request_tenant(foreign_tenant.id)
    try:
        foreign_ws = PersistenceWorkspace.objects.create(
            tenant=foreign_tenant, name=f"ws-{suffix}"
        )
        provision_workspace_link_types(
            workspace_id=foreign_ws.id, tenant_id=foreign_tenant.id
        )
        create_default_workflow(
            workspace_id=foreign_ws.id,
            preset="architecture_default",
            item_type="ArchitectureElement",
            tenant_id=foreign_tenant.id,
        )
        element = ArchitectureService().create_architecture_element(
            workspace_id=foreign_ws.id, title=title, ctx=foreign_ctx
        )
    finally:
        clear_request_tenant()
        # Back to the caller's tenant: both isolation layers.
        set_request_tenant(tenant.id)
    return element, foreign_ctx, foreign_tenant.id


def _group_with_service() -> tuple[ArchitectureToolGroup, MagicMock]:
    """A group whose ArchitectureService and TraceLinkService are doubles."""
    service = MagicMock()
    return (
        ArchitectureToolGroup(service=service, trace_service=MagicMock()),
        service,
    )


# ---------------------------------------------------------------------------
# Real-DB round trip: create -> get -> query -> update -> link
# ---------------------------------------------------------------------------


def test_create_then_get_round_trip_through_dispatch(caller):
    """The create payload (incl. custom_fields and SE attributes) survives."""
    _tenant, _workspace, ctx, _user_id = caller
    group = ArchitectureToolGroup()
    created = _create_element(
        caller,
        title="Roundtrip Element",
        description="A subsystem",
        element_type="subsystem",
        asil_level="B",
        make_or_buy="make",
        custom_fields={"origin": "workshop"},
    )

    assert created["title"] == "Roundtrip Element"
    assert created["description"] == "A subsystem"
    assert created["element_type"] == "subsystem"
    assert created["asil_level"] == "B"
    assert created["make_or_buy"] == "make"
    assert created["custom_fields"] == {"origin": "workshop"}
    assert created["version"] == 1
    assert created["artifact_id"]

    fetched = _exec(group, "architecture.get", {"id": created["id"]}, ctx)
    assert fetched.success is True, fetched.message
    payload = fetched.data["architecture_element"]
    assert payload["id"] == created["id"]
    assert payload["artifact_id"] == created["artifact_id"]
    assert payload["custom_fields"] == {"origin": "workshop"}
    assert payload["asil_level"] == "B"
    assert payload["make_or_buy"] == "make"


def test_create_unknown_workspace_returns_not_found(caller):
    """The service's workspace lookup answers NOT_FOUND for an unknown id."""
    _tenant, _workspace, ctx, _user_id = caller
    group = ArchitectureToolGroup()

    result = _exec(
        group,
        "architecture.create",
        {"workspace_id": str(uuid4()), "title": "Orphan Element"},
        ctx,
    )

    assert result.success is False
    assert result.error_code == "NOT_FOUND"


def test_query_lists_elements_with_count(caller):
    """architecture.query returns the created elements plus a count."""
    _tenant, workspace, ctx, _user_id = caller
    group = ArchitectureToolGroup()
    root = _create_element(caller, title="Root Element")
    child = _create_element(caller, title="Child Element")
    assert child["parent_id"] == root["id"]

    result = _exec(group, "architecture.query", {"workspace_id": str(workspace.id)}, ctx)

    assert result.success is True
    ids = {el["id"] for el in result.data["architecture_elements"]}
    assert ids == {root["id"], child["id"]}
    assert result.data["count"] == 2


def test_query_include_outdated_filters_soft_deleted(caller):
    """include_outdated=False hides and True re-shows an outdated element."""
    _tenant, workspace, ctx, _user_id = caller
    group = ArchitectureToolGroup()
    root = _create_element(caller, title="Kept Element")
    dropped = _create_element(caller, title="Dropped Element")

    _exec(group, "architecture.outdate", {"id": dropped["id"], "reason": "obsolete"}, ctx)

    visible = _exec(group, "architecture.query", {"workspace_id": str(workspace.id)}, ctx)
    assert {el["id"] for el in visible.data["architecture_elements"]} == {root["id"]}

    all_rows = _exec(
        group,
        "architecture.query",
        {"workspace_id": str(workspace.id), "include_outdated": True},
        ctx,
    )
    assert {el["id"] for el in all_rows.data["architecture_elements"]} == {
        root["id"],
        dropped["id"],
    }
    assert all_rows.data["count"] == 2


def test_update_round_trip_updates_title_and_description(caller):
    """The update payload survives and reads back via the public interface."""
    _tenant, _workspace, ctx, _user_id = caller
    group = ArchitectureToolGroup()
    created = _create_element(caller, title="Before Update")

    result = _exec(
        group,
        "architecture.update",
        {
            "id": created["id"],
            "data": {
                "expected_version": 1,
                "title": "After Update",
                "description": "Updated description",
                "asil_level": "C",
            },
        },
        ctx,
    )

    assert result.success is True, result.message
    payload = result.data["architecture_element"]
    assert payload["title"] == "After Update"
    assert payload["description"] == "Updated description"
    assert payload["asil_level"] == "C"
    assert payload["version"] == 2

    fetched = _exec(group, "architecture.get", {"id": created["id"]}, ctx)
    assert fetched.data["architecture_element"]["title"] == "After Update"


def test_update_without_expected_version_falls_back_to_one(caller):
    """Agents that do not track versions get the documented fallback."""
    _tenant, _workspace, ctx, _user_id = caller
    group = ArchitectureToolGroup()
    created = _create_element(caller, title="Fallback Version")

    result = _exec(
        group,
        "architecture.update",
        {"id": created["id"], "data": {"title": "Fallback Updated"}},
        ctx,
    )

    assert result.success is True, result.message
    assert result.data["architecture_element"]["title"] == "Fallback Updated"


def test_update_version_conflict_maps_to_validation_error(caller):
    """A stale expected_version is a VALIDATION_ERROR, not an internal crash."""
    _tenant, _workspace, ctx, _user_id = caller
    group = ArchitectureToolGroup()
    created = _create_element(caller, title="Conflicted Element")

    result = _exec(
        group,
        "architecture.update",
        {"id": created["id"], "data": {"expected_version": 999, "title": "Stale"}},
        ctx,
    )

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"
    assert "Version conflict" in result.message


def test_link_creates_trace_link_against_real_catalog(caller):
    """architecture.link persists a catalog-validated TraceLink (real DB).

    ``allocated-to`` is Requirement -> ArchitectureElement only, so the
    canonical arch-side link is ``decomposes`` between a parent element and
    its child (the same edge the built-in catalog provisions).
    """
    _tenant, _workspace, ctx, _user_id = caller
    group = ArchitectureToolGroup()
    parent = _create_element(caller, title="Parent Element")
    child = _create_element(caller, title="Child Element")

    result = _exec(
        group,
        "architecture.link",
        {
            "arch_id": parent["id"],
            "target_id": child["id"],
            "link_type": LinkType.DECOMPOSES.value,
        },
        ctx,
    )

    assert result.success is True, result.message
    trace = result.data["trace_link"]
    assert trace["source_id"] == parent["id"]
    assert trace["target_id"] == child["id"]
    assert trace["link_type"] == LinkType.DECOMPOSES.value
    assert TraceLink.objects.filter(
        source_id=parent["artifact_id"],
        target_id=child["artifact_id"],
        link_type=LinkType.DECOMPOSES.value,
    ).exists()


def test_link_unknown_link_type_returns_validation_error(caller):
    """The workspace catalog is the sole validation authority (real DB)."""
    _tenant, _workspace, ctx, _user_id = caller
    group = ArchitectureToolGroup()
    parent = _create_element(caller, title="Catalog Source")
    child = _create_element(caller, title="Catalog Target")

    result = _exec(
        group,
        "architecture.link",
        {
            "arch_id": parent["id"],
            "target_id": child["id"],
            "link_type": "no-such-link-type",
        },
        ctx,
    )

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"


# ---------------------------------------------------------------------------
# Lifecycle: outdate / reactivate
# ---------------------------------------------------------------------------


def test_outdate_then_reactivate_round_trip_through_dispatch(caller):
    """The soft-delete escape hatch works over the public dispatch interface."""
    _tenant, workspace, ctx, _user_id = caller
    group = ArchitectureToolGroup()
    root = _create_element(caller, title="Lifecycle Root")
    doomed = _create_element(caller, title="Lifecycle Element")

    outdated = _exec(
        group, "architecture.outdate", {"id": doomed["id"], "reason": "superseded"}, ctx
    )
    assert outdated.success is True, outdated.message
    assert outdated.data == {"id": doomed["id"], "status": "outdated"}

    hidden = _exec(group, "architecture.query", {"workspace_id": str(workspace.id)}, ctx)
    assert {el["id"] for el in hidden.data["architecture_elements"]} == {root["id"]}

    restored = _exec(group, "architecture.reactivate", {"id": doomed["id"]}, ctx)
    assert restored.success is True, restored.message
    assert restored.data["id"] == doomed["id"]
    assert restored.data["status"] != "outdated"

    visible = _exec(group, "architecture.query", {"workspace_id": str(workspace.id)}, ctx)
    assert visible.data["count"] == 2


def test_reactivate_active_element_returns_invalid_state(caller):
    """Reactivating an item that is not soft-deleted fails with INVALID_STATE."""
    _tenant, _workspace, ctx, _user_id = caller
    group = ArchitectureToolGroup()
    created = _create_element(caller, title="Active Element")

    result = _exec(group, "architecture.reactivate", {"id": created["id"]}, ctx)

    assert result.success is False
    assert result.error_code == "INVALID_STATE"


# ---------------------------------------------------------------------------
# Parameter validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tool", _ID_TOOLS)
def test_missing_id_returns_validation_error(caller, tool):
    """Every id-taking tool refuses a call without ``id``."""
    _tenant, workspace, ctx, _user_id = caller
    group = ArchitectureToolGroup()

    result = _exec(group, tool, {"workspace_id": str(workspace.id)}, ctx)

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"
    assert "'id'" in result.message


@pytest.mark.parametrize("tool", _ID_TOOLS)
def test_non_uuid_id_returns_validation_error(caller, tool):
    """Every id-taking tool refuses an unparseable ``id`` value."""
    _tenant, _workspace, ctx, _user_id = caller
    group = ArchitectureToolGroup()

    result = _exec(group, tool, {"id": "not-a-uuid"}, ctx)

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"
    assert result.message == "Parameter 'id' is not a valid UUID: 'not-a-uuid'"


@pytest.mark.parametrize("missing", ["arch_id", "target_id", "link_type"])
def test_link_missing_required_param_returns_validation_error(caller, missing):
    """architecture.link validates arch_id, target_id and link_type itself."""
    _tenant, _workspace, ctx, _user_id = caller
    group = ArchitectureToolGroup()
    params = {
        "arch_id": str(uuid4()),
        "target_id": str(uuid4()),
        "link_type": LinkType.ALLOCATED_TO.value,
    }
    del params[missing]

    result = _exec(group, "architecture.link", params, ctx)

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"
    assert f"'{missing}'" in result.message


def test_create_missing_title_returns_validation_error(caller):
    """``title`` is required — an empty value never reaches the service."""
    _tenant, workspace, ctx, _user_id = caller
    group = ArchitectureToolGroup()

    result = _exec(group, "architecture.create", {"workspace_id": str(workspace.id)}, ctx)

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"
    assert "'title'" in result.message


def test_create_non_uuid_workspace_id_returns_validation_error(caller):
    _tenant, _workspace, ctx, _user_id = caller
    group = ArchitectureToolGroup()

    result = _exec(
        group,
        "architecture.create",
        {"workspace_id": "not-a-uuid", "title": "Broken Element"},
        ctx,
    )

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"
    assert "workspace_id" in result.message


def test_query_requires_workspace_id(caller):
    """The handler's own stable message is part of the tool contract."""
    _tenant, _workspace, ctx, _user_id = caller
    group = ArchitectureToolGroup()

    result = _exec(group, "architecture.query", {}, ctx)

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"
    assert result.message == "Parameter 'workspace_id' is required for architecture.query."


def test_query_non_uuid_workspace_id_returns_validation_error(caller):
    _tenant, _workspace, ctx, _user_id = caller
    group = ArchitectureToolGroup()

    result = _exec(group, "architecture.query", {"workspace_id": "not-a-uuid"}, ctx)

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"
    assert "workspace_id" in result.message


def test_update_non_integer_expected_version_returns_validation_error(caller):
    """The optimistic-lock version must be an integer."""
    _tenant, _workspace, ctx, _user_id = caller
    group = ArchitectureToolGroup()

    result = _exec(
        group,
        "architecture.update",
        {"id": str(uuid4()), "data": {"expected_version": "soon", "title": "X"}},
        ctx,
    )

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"
    assert result.message == "'expected_version' must be an integer."


def test_update_invalid_parent_id_returns_validation_error(caller):
    """A non-UUID ``parent_id`` inside ``data`` is rejected before the service."""
    _tenant, _workspace, ctx, _user_id = caller
    group = ArchitectureToolGroup()

    result = _exec(
        group,
        "architecture.update",
        {"id": str(uuid4()), "data": {"expected_version": 1, "parent_id": "root?"}},
        ctx,
    )

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"
    assert "parent_id" in result.message


# ---------------------------------------------------------------------------
# RBAC fence (registry layer: API key -> role -> tool)
# ---------------------------------------------------------------------------


def test_registry_viewer_write_is_refused(e2e_workspace, e2e_userrole_viewer, e2e_api_key_viewer):
    """A viewer-role API key is refused on architecture.create at the registry."""
    result = ToolRegistry().dispatch_request(
        tool_name="architecture.create",
        params={"workspace_id": str(e2e_workspace.id), "title": "Viewer Element"},
        api_key=e2e_api_key_viewer,
    )

    assert result.success is False
    assert result.error_code == "PERMISSION_DENIED"


def test_registry_viewer_read_is_allowed(
    e2e_workspace, e2e_userrole_member, e2e_userrole_viewer, e2e_api_key_member, e2e_api_key_viewer
):
    """architecture.get is read-exempt: a viewer may read, a member may write."""
    created = ToolRegistry().dispatch_request(
        tool_name="architecture.create",
        params={"workspace_id": str(e2e_workspace.id), "title": "Readable Element"},
        api_key=e2e_api_key_member,
    )
    assert created.success is True, created.message
    element_id = created.data["architecture_element"]["id"]

    read = ToolRegistry().dispatch_request(
        tool_name="architecture.get",
        params={"id": element_id},
        api_key=e2e_api_key_viewer,
    )

    assert read.success is True, read.message
    assert read.data["architecture_element"]["id"] == element_id


# ---------------------------------------------------------------------------
# Cross-tenant read fence
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "tool,params",
    [
        ("architecture.get", {}),
        ("architecture.update", {"data": {"expected_version": 1, "title": "Hijack"}}),
        ("architecture.outdate", {"reason": "nope"}),
        ("architecture.reactivate", {}),
    ],
)
def test_foreign_tenant_element_is_not_found(caller, tool, params):
    """Another tenant's element id is NOT_FOUND under the caller's tenant."""
    _tenant, _workspace, ctx, _user_id = caller
    foreign_element, _foreign_ctx, _foreign_tenant_id = _make_foreign_element(caller)
    group = ArchitectureToolGroup()

    result = _exec(group, tool, {"id": str(foreign_element.id), **params}, ctx)

    assert result.success is False
    assert result.error_code == "NOT_FOUND"


def test_link_foreign_tenant_element_is_not_found(caller):
    """The link path cannot use a foreign tenant's element as its source."""
    _tenant, _workspace, ctx, _user_id = caller
    foreign_element, _foreign_ctx, _foreign_tenant_id = _make_foreign_element(caller)
    group = ArchitectureToolGroup()

    result = _exec(
        group,
        "architecture.link",
        {
            "arch_id": str(foreign_element.id),
            "target_id": str(uuid4()),
            "link_type": LinkType.DECOMPOSES.value,
        },
        ctx,
    )

    assert result.success is False
    assert result.error_code == "NOT_FOUND"


def test_create_in_foreign_tenant_workspace_returns_not_found(caller):
    """A foreign workspace id never creates an element for the caller."""
    _tenant, _workspace, ctx, _user_id = caller
    foreign_element, _foreign_ctx, _foreign_tenant_id = _make_foreign_element(caller)
    group = ArchitectureToolGroup()

    result = _exec(
        group,
        "architecture.create",
        {"workspace_id": str(foreign_element.artifact.workspace_id), "title": "Ghost"},
        ctx,
    )

    assert result.success is False
    assert result.error_code == "NOT_FOUND"


def test_query_foreign_tenant_workspace_returns_empty_list(caller):
    """architecture.query is tenant-scoped: a foreign workspace yields zero rows."""
    tenant, _workspace, ctx, _user_id = caller
    foreign_element, _foreign_ctx, foreign_tenant_id = _make_foreign_element(caller)
    group = ArchitectureToolGroup()

    result = _exec(
        group,
        "architecture.query",
        {"workspace_id": str(foreign_element.artifact.workspace_id)},
        ctx,
    )

    assert result.success is True
    assert result.data["architecture_elements"] == []
    assert result.data["count"] == 0

    # Sanity: the row exists for its own tenant — the fence is the tenant
    # boundary, not a missing row.
    set_request_tenant(foreign_tenant_id)
    try:
        own = _exec(
            group,
            "architecture.query",
            {"workspace_id": str(foreign_element.artifact.workspace_id)},
            _foreign_ctx,
        )
    finally:
        clear_request_tenant()
        set_request_tenant(tenant.id)
    assert own.data["count"] == 1


# ---------------------------------------------------------------------------
# Service-error -> MCP-code mapping
# ---------------------------------------------------------------------------


def test_service_not_found_maps_to_not_found(caller):
    _tenant, _workspace, ctx, _user_id = caller
    group, service = _group_with_service()
    service.get_architecture_element.side_effect = NotFoundError("Element x not found.")

    result = _exec(group, "architecture.get", {"id": str(uuid4())}, ctx)

    assert result.success is False
    assert result.error_code == "NOT_FOUND"


def test_service_permission_denied_maps_to_permission_denied(caller):
    _tenant, _workspace, ctx, _user_id = caller
    group, service = _group_with_service()
    service.get_architecture_element.side_effect = PermissionDeniedError(
        "editor required"
    )

    result = _exec(group, "architecture.get", {"id": str(uuid4())}, ctx)

    assert result.success is False
    assert result.error_code == "PERMISSION_DENIED"


def test_service_validation_error_maps_to_validation_error(caller):
    _tenant, workspace, ctx, _user_id = caller
    group, service = _group_with_service()
    service.create_architecture_element.side_effect = ValidationError(
        "Title exceeds 500 characters."
    )

    result = _exec(
        group,
        "architecture.create",
        {"workspace_id": str(workspace.id), "title": "Too Long"},
        ctx,
    )

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"
    assert result.message == "Title exceeds 500 characters."


def test_trace_service_validation_error_maps_to_validation_error(caller):
    """The link path maps the catalog ValidationError, not an internal crash."""
    _tenant, _workspace, ctx, _user_id = caller
    group = ArchitectureToolGroup(
        service=MagicMock(), trace_service=MagicMock()
    )
    group._trace_service.create_trace_link.side_effect = ValidationError(
        "unknown link_type 'conflicts-with'"
    )

    result = _exec(
        group,
        "architecture.link",
        {"arch_id": str(uuid4()), "target_id": str(uuid4()), "link_type": "conflicts-with"},
        ctx,
    )

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"


def test_unmapped_service_error_is_masked(caller):
    """CWE-209 / fix #108: an unmapped exception never leaks its message."""
    _tenant, _workspace, ctx, _user_id = caller
    group, service = _group_with_service()
    service.get_architecture_element.side_effect = RuntimeError(
        "SELECT * FROM secret_elements failed"
    )

    result = _exec(group, "architecture.get", {"id": str(uuid4())}, ctx)

    assert result.success is False
    assert result.error_code == "INTERNAL_ERROR"
    assert result.message == "An internal error occurred."
    assert "secret_elements" not in result.message


def test_unknown_tool_returns_unknown_tool(caller):
    """The dispatcher answers an unknown tool name, it does not raise."""
    _tenant, _workspace, ctx, _user_id = caller
    group = ArchitectureToolGroup()

    result = _exec(group, "architecture.teleport", {"id": str(uuid4())}, ctx)

    assert result.success is False
    assert result.error_code == "UNKNOWN_TOOL"


def test_tool_map_covers_every_published_schema():
    """Every advertised schema name resolves to a handler (registry guard)."""
    names = {schema["name"] for schema in ArchitectureToolGroup().get_tool_schemas()}
    assert names == set(ArchitectureToolGroup._TOOL_MAP)
    assert "architecture.decompose" in names
