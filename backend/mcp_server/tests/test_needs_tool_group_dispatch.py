"""
Dispatch-level tests for the StakeholderNeeds tool group (COMP-MC-005, 8 tools).

``test_tool_groups.py`` pins ``needs.query`` against a mocked service and
``test_own_tool_groups_lifecycle.py`` drives the outdate/reactivate round trip
by calling the PRIVATE handlers directly. What neither covers is the public
boundary a real MCP call arrives through: this module drives EVERY ``needs.*``
tool through :meth:`BaseToolGroup.execute_tool`:

* real-DB round trips (create -> read -> query -> update -> traces ->
  outdate/reactivate),
* parameter validation for every tool's required ``id`` / ``workspace_id`` /
  ``title`` (missing value and non-UUID value),
* the RBAC fence of a real viewer context (write refused, read allowed),
* the cross-tenant read fence (another tenant's id -> NOT_FOUND, another
  tenant's workspace -> empty list),
* service-error -> MCP-code mapping (NotFoundError -> NOT_FOUND,
  ValidationError -> VALIDATION_ERROR, unmapped exception -> masked
  INTERNAL_ERROR),
* the CWE-209 masking contract: an unmapped error never leaks its message,
* the ``needs.derive_requirements`` delegation to the shared
  ``derive_requirements_from_need`` implementation (fix #112) — the ``id``
  parameter is forwarded as ``need_id`` and the shared preview path answers.

The tenant context is armed through ``persistence.middleware.set_request_tenant``
(thread-local + PostgreSQL RLS session variable), exactly like the production
``ToolRegistry.dispatch_request`` does.

leaf_id : COMP-MC-005
req_id  : REQ-L2-MC-005
"""
from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from application.base import (
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from application.requirement_service import RequirementService
from application.stakeholder_need_service import StakeholderNeedService
from auth_tenancy.context import AuthContext, AuthMethod
from link_types.workspace_store import provision_workspace_link_types
from mcp_server.tools.needs import StakeholderNeedsToolGroup
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User
from persistence.models import Workspace as PersistenceWorkspace
from traceability.types import LinkType
from workflow.services import create_default_workflow

pytestmark = pytest.mark.django_db

_API_KEY = "reqlo_testkey_needs_dispatch"

# Tools whose handler validates a required ``id`` parameter first.
_ID_TOOLS = (
    "needs.read",
    "needs.get_traces",
    "needs.update",
    "needs.outdate",
    "needs.reactivate",
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def caller():
    """Tenant + workspace + workflows + editor AuthContext, tenant-scoped.

    Both isolation layers are armed (``set_request_tenant``) so the RLS fence
    of the test database applies while the tool runs. The StakeholderNeed
    workflow is provisioned (lifecycle tools) and the link-type catalog is
    seeded (trace links are always validated).
    """
    suffix = uuid4().hex[:8]
    tenant = Tenant.objects.create(
        name=f"MCP needs dispatch {suffix}", slug=f"mcp-needs-{suffix}"
    )
    user = User.objects.create(
        username=f"mcpneeds-{suffix}-user",
        email=f"mcpneeds-{suffix}@t.test",
        tenant=tenant,
    )
    set_request_tenant(tenant.id)
    try:
        workspace = PersistenceWorkspace.objects.create(tenant=tenant, name=f"ws-{suffix}")
        provision_workspace_link_types(workspace_id=workspace.id, tenant_id=tenant.id)
        create_default_workflow(
            workspace_id=workspace.id,
            preset="need_default",
            item_type="StakeholderNeed",
            tenant_id=tenant.id,
        )
        # The trace-link fixture links a Requirement to the need.
        create_default_workflow(
            workspace_id=workspace.id,
            preset="standard",
            item_type="Requirement",
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


def _create_need(caller, title="Dispatch Need", **extra):
    """needs.create through the public interface; returns the payload."""
    _tenant, workspace, ctx, _user_id = caller
    group = StakeholderNeedsToolGroup()
    result = _exec(
        group,
        "needs.create",
        {"workspace_id": str(workspace.id), "title": title, **extra},
        ctx,
    )
    assert result.success is True, result.message
    return result.data["need"]


def _viewer_ctx(tenant, user_id) -> AuthContext:
    """A viewer context inside the same tenant (write must be refused)."""
    return AuthContext(
        user_id=user_id,
        tenant_id=tenant.id,
        active_roles=("viewer",),
        auth_method=AuthMethod.API_KEY,
        api_key_id=None,
    )


def _make_foreign_need(caller, title="Foreign need"):
    """A need in ANOTHER tenant, created under that tenant's own context.

    Returns ``(need, foreign_ctx, foreign_tenant_id)``. Re-arms the caller's
    tenant afterwards so the RLS session variable of the shared test
    connection points back at the caller when the dispatch runs.
    """
    tenant, _workspace, _ctx, _user_id = caller
    suffix = uuid4().hex[:8]
    foreign_tenant = Tenant.objects.create(
        name=f"MCP needs foreign {suffix}", slug=f"mcp-needs-f-{suffix}"
    )
    foreign_user = User.objects.create(
        username=f"mcpneedsf-{suffix}-user",
        email=f"mcpneedsf-{suffix}@t.test",
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
        create_default_workflow(
            workspace_id=foreign_ws.id,
            preset="need_default",
            item_type="StakeholderNeed",
            tenant_id=foreign_tenant.id,
        )
        need = StakeholderNeedService().create(
            ctx=foreign_ctx, workspace_id=foreign_ws.id, title=title
        )
    finally:
        clear_request_tenant()
        # Back to the caller's tenant: both isolation layers.
        set_request_tenant(tenant.id)
    return need, foreign_ctx, foreign_tenant.id


def _group_with_service() -> tuple[StakeholderNeedsToolGroup, MagicMock]:
    """A group whose StakeholderNeedService is a MagicMock."""
    service = MagicMock()
    return StakeholderNeedsToolGroup(service=service), service


# ---------------------------------------------------------------------------
# Real-DB round trip: create -> read -> query -> update
# ---------------------------------------------------------------------------


def test_create_then_read_round_trip_through_dispatch(caller):
    """The create payload (incl. custom_fields) survives and reads back."""
    _tenant, workspace, ctx, _user_id = caller
    group = StakeholderNeedsToolGroup()
    result = _exec(
        group,
        "needs.create",
        {
            "workspace_id": str(workspace.id),
            "title": "Roundtrip Need",
            "description": "As a stakeholder I want traceability.",
            "category": "business",
            "moscow_priority": "Must",
            "custom_fields": {"origin": "workshop"},
        },
        ctx,
    )

    assert result.success is True, result.message
    payload = result.data["need"]
    assert payload["title"] == "Roundtrip Need"
    assert payload["description"] == "As a stakeholder I want traceability."
    assert payload["category"] == "business"
    assert payload["moscow_priority"] == "Must"
    assert payload["custom_fields"]["origin"] == "workshop"
    assert payload["workspace_id"] == str(workspace.id)
    assert payload["version"] == 1
    assert payload["uid"]

    fetched = _exec(group, "needs.read", {"id": payload["id"]}, ctx)
    assert fetched.success is True, fetched.message
    assert fetched.data["need"]["custom_fields"]["origin"] == "workshop"
    assert fetched.data["need"]["id"] == payload["id"]


def test_create_unknown_workspace_returns_not_found(caller):
    """The service's workspace lookup answers NOT_FOUND for an unknown id."""
    _tenant, _workspace, ctx, _user_id = caller
    group = StakeholderNeedsToolGroup()
    result = _exec(
        group,
        "needs.create",
        {"workspace_id": str(uuid4()), "title": "Orphan Need"},
        ctx,
    )

    assert result.success is False
    assert result.error_code == "NOT_FOUND"


def test_query_lists_created_needs_with_count(caller):
    """needs.query returns the created needs plus a matching count."""
    _tenant, workspace, ctx, _user_id = caller
    group = StakeholderNeedsToolGroup()
    first = _create_need(caller, title="First Need")
    second = _create_need(caller, title="Second Need")

    result = _exec(group, "needs.query", {"workspace_id": str(workspace.id)}, ctx)

    assert result.success is True
    ids = {n["id"] for n in result.data["needs"]}
    assert ids == {first["id"], second["id"]}
    assert result.data["count"] == 2


def test_query_include_deleted_hides_outdated_by_default(caller):
    """include_deleted=False hides and True re-shows a soft-deleted need."""
    _tenant, workspace, ctx, _user_id = caller
    group = StakeholderNeedsToolGroup()
    kept = _create_need(caller, title="Kept Need")
    dropped = _create_need(caller, title="Dropped Need")

    _exec(group, "needs.outdate", {"id": dropped["id"], "reason": "obsolete"}, ctx)

    visible = _exec(group, "needs.query", {"workspace_id": str(workspace.id)}, ctx)
    assert {n["id"] for n in visible.data["needs"]} == {kept["id"]}

    all_rows = _exec(
        group,
        "needs.query",
        {"workspace_id": str(workspace.id), "include_deleted": True},
        ctx,
    )
    assert {n["id"] for n in all_rows.data["needs"]} == {kept["id"], dropped["id"]}
    assert all_rows.data["count"] == 2


def test_update_round_trip_ignores_client_sent_status(caller):
    """REQ-143: a client-sent ``status`` is ignored, not an error."""
    _tenant, _workspace, ctx, _user_id = caller
    group = StakeholderNeedsToolGroup()
    created = _create_need(caller, title="Before Update")

    result = _exec(
        group,
        "needs.update",
        {
            "id": created["id"],
            "title": "After Update",
            "description": "Updated description",
            "moscow_priority": "Should",
            # REQ-143: read-only on the wire — the WorkflowEngine owns it.
            "status": "closed",
            "change_reason": "dispatch test",
        },
        ctx,
    )

    assert result.success is True, result.message
    payload = result.data["need"]
    assert payload["title"] == "After Update"
    assert payload["description"] == "Updated description"
    assert payload["moscow_priority"] == "Should"
    assert payload["status"] != "closed"

    fetched = _exec(group, "needs.read", {"id": created["id"]}, ctx)
    assert fetched.data["need"]["title"] == "After Update"


# ---------------------------------------------------------------------------
# needs.get_traces
# ---------------------------------------------------------------------------


def test_get_traces_reports_incoming_link(caller):
    """A Requirement deriving FROM the need is an incoming trace of the need."""
    from application.trace_link_service import TraceLinkService

    _tenant, workspace, ctx, _user_id = caller
    group = StakeholderNeedsToolGroup()
    need = _create_need(caller, title="Traced Need")
    requirement = RequirementService().create_requirement(
        workspace_id=workspace.id, title="Derived Req", ctx=ctx
    )
    TraceLinkService().create_trace_link(
        source_id=requirement.artifact_id,
        target_id=need["id"],
        link_type=LinkType.DERIVES_FROM.value,
        ctx=ctx,
    )

    result = _exec(group, "needs.get_traces", {"id": need["id"]}, ctx)

    assert result.success is True, result.message
    assert result.data["source_need"] == need["id"]
    incoming = result.data["incoming_traces"]
    assert [t["type"] for t in incoming] == [LinkType.DERIVES_FROM.value]
    assert [t["source"] for t in incoming] == [str(requirement.artifact_id)]
    assert result.data["outgoing_traces"] == []


def test_get_traces_empty_for_unlinked_need(caller):
    """An unlinked need yields empty trace lists, not an error."""
    _tenant, _workspace, ctx, _user_id = caller
    group = StakeholderNeedsToolGroup()
    need = _create_need(caller, title="Lonely Need")

    result = _exec(group, "needs.get_traces", {"id": need["id"]}, ctx)

    assert result.success is True
    assert result.data["incoming_traces"] == []
    assert result.data["outgoing_traces"] == []


# ---------------------------------------------------------------------------
# Lifecycle: outdate / reactivate
# ---------------------------------------------------------------------------


def test_outdate_then_reactivate_round_trip_through_dispatch(caller):
    """The soft-delete escape hatch works over the public dispatch interface."""
    _tenant, _workspace, ctx, _user_id = caller
    group = StakeholderNeedsToolGroup()
    need = _create_need(caller, title="Lifecycle Need")

    outdated = _exec(
        group, "needs.outdate", {"id": need["id"], "reason": "superseded"}, ctx
    )
    assert outdated.success is True, outdated.message
    assert outdated.data == {"id": need["id"], "status": "outdated"}

    hidden = _exec(group, "needs.query", {"workspace_id": need["workspace_id"]}, ctx)
    assert hidden.data["count"] == 0

    restored = _exec(group, "needs.reactivate", {"id": need["id"]}, ctx)
    assert restored.success is True, restored.message
    assert restored.data["id"] == need["id"]
    assert restored.data["status"] != "outdated"

    visible = _exec(group, "needs.query", {"workspace_id": need["workspace_id"]}, ctx)
    assert visible.data["count"] == 1


# ---------------------------------------------------------------------------
# Parameter validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tool", _ID_TOOLS)
def test_missing_id_returns_validation_error(caller, tool):
    """Every id-taking tool refuses a call without ``id``."""
    _tenant, workspace, ctx, _user_id = caller
    group = StakeholderNeedsToolGroup()

    result = _exec(group, tool, {"workspace_id": str(workspace.id)}, ctx)

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"
    assert "'id'" in result.message


@pytest.mark.parametrize("tool", _ID_TOOLS)
def test_non_uuid_id_returns_validation_error(caller, tool):
    """Every id-taking tool refuses an unparseable ``id`` value."""
    _tenant, _workspace, ctx, _user_id = caller
    group = StakeholderNeedsToolGroup()

    result = _exec(group, tool, {"id": "not-a-uuid"}, ctx)

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"
    assert result.message == "Parameter 'id' is not a valid UUID: 'not-a-uuid'"


def test_create_missing_title_returns_validation_error(caller):
    """``title`` is required — an empty value never reaches the service."""
    _tenant, workspace, ctx, _user_id = caller
    group = StakeholderNeedsToolGroup()

    result = _exec(group, "needs.create", {"workspace_id": str(workspace.id)}, ctx)

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"
    assert "'title'" in result.message


def test_create_non_uuid_workspace_id_returns_validation_error(caller):
    _tenant, _workspace, ctx, _user_id = caller
    group = StakeholderNeedsToolGroup()

    result = _exec(
        group,
        "needs.create",
        {"workspace_id": "not-a-uuid", "title": "Broken Need"},
        ctx,
    )

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"
    assert "workspace_id" in result.message


def test_query_requires_workspace_id(caller):
    """The handler's own stable message is part of the tool contract."""
    _tenant, _workspace, ctx, _user_id = caller
    group = StakeholderNeedsToolGroup()

    result = _exec(group, "needs.query", {}, ctx)

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"
    assert result.message == "Parameter 'workspace_id' is required for needs.query."


def test_query_non_uuid_workspace_id_returns_validation_error(caller):
    _tenant, _workspace, ctx, _user_id = caller
    group = StakeholderNeedsToolGroup()

    result = _exec(group, "needs.query", {"workspace_id": "not-a-uuid"}, ctx)

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"
    assert "workspace_id" in result.message


# ---------------------------------------------------------------------------
# needs.derive_requirements (fix #112 delegation)
# ---------------------------------------------------------------------------


def _ai_service() -> MagicMock:
    """An AiDerivationService double for the shared preview path."""
    ai = MagicMock()
    ai.derive_requirements_from_need.return_value = {
        "need_id": str(uuid4()),
        "drafts": [{"title": "Derived Req", "description": "AI draft"}],
        "total": 1,
    }
    return ai


def test_derive_preview_forwards_need_id_to_shared_implementation(caller):
    """``id`` is forwarded as ``need_id``; the preview payload is passed through."""
    _tenant, _workspace, ctx, _user_id = caller
    ai = _ai_service()
    group = StakeholderNeedsToolGroup(ai_derivation_service=ai)
    need_id = uuid4()

    result = _exec(
        group,
        "needs.derive_requirements",
        {"id": str(need_id), "mode": "preview"},
        ctx,
    )

    assert result.success is True, result.message
    assert result.data["total"] == 1
    call = ai.derive_requirements_from_need.call_args
    assert call.args[0] is ctx
    assert call.args[1] == need_id
    assert call.kwargs["n"] is None


def test_derive_rejects_non_integer_n(caller):
    """``n`` must be an integer — the shared implementation owns that check."""
    _tenant, _workspace, ctx, _user_id = caller
    ai = _ai_service()
    group = StakeholderNeedsToolGroup(ai_derivation_service=ai)

    result = _exec(
        group,
        "needs.derive_requirements",
        {"id": str(uuid4()), "n": "many"},
        ctx,
    )

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"
    ai.derive_requirements_from_need.assert_not_called()


def test_derive_unknown_need_returns_not_found(caller):
    """The service's NotFoundError maps to NOT_FOUND, not INTERNAL_ERROR."""
    from application.base import NotFoundError as ServiceNotFoundError

    _tenant, _workspace, ctx, _user_id = caller
    ai = _ai_service()
    ai.derive_requirements_from_need.side_effect = ServiceNotFoundError(
        "StakeholderNeed not found."
    )
    group = StakeholderNeedsToolGroup(ai_derivation_service=ai)

    result = _exec(
        group, "needs.derive_requirements", {"id": str(uuid4())}, ctx
    )

    assert result.success is False
    assert result.error_code == "NOT_FOUND"


# ---------------------------------------------------------------------------
# RBAC fence
# ---------------------------------------------------------------------------


def test_viewer_write_is_refused_and_persists_nothing(caller):
    """A viewer context is refused on the write path (service RBAC fence).

    The needs group — unlike its sibling ``mcp_server.tools.tests`` — does not
    catch ``PermissionDeniedError``, so the dispatcher's own mask applies: the
    write fails closed and the caller only sees a static message. What matters
    here is that nothing is persisted.
    """
    tenant, workspace, ctx, user_id = caller
    viewer = _viewer_ctx(tenant, user_id)
    group = StakeholderNeedsToolGroup()

    result = _exec(
        group,
        "needs.create",
        {"workspace_id": str(workspace.id), "title": "Viewer Need"},
        viewer,
    )

    assert result.success is False
    assert result.error_code == "INTERNAL_ERROR"
    assert result.message == "An internal error occurred."
    listed = _exec(group, "needs.query", {"workspace_id": str(workspace.id)}, ctx)
    assert listed.data["count"] == 0


def test_viewer_read_is_allowed(caller):
    """Reads are not write-gated: a viewer can read and query."""
    tenant, _workspace, _ctx, user_id = caller
    viewer = _viewer_ctx(tenant, user_id)
    group = StakeholderNeedsToolGroup()
    created = _create_need(caller, title="Readable Need")

    single = _exec(group, "needs.read", {"id": created["id"]}, viewer)
    assert single.success is True, single.message
    assert single.data["need"]["title"] == "Readable Need"

    listed = _exec(group, "needs.query", {"workspace_id": created["workspace_id"]}, viewer)
    assert listed.success is True
    assert listed.data["count"] == 1


# ---------------------------------------------------------------------------
# Cross-tenant read fence
# ---------------------------------------------------------------------------


def test_read_foreign_tenant_need_returns_not_found(caller):
    """Another tenant's need id is NOT_FOUND under the caller's tenant."""
    _tenant, _workspace, ctx, _user_id = caller
    foreign_need, _foreign_ctx, _foreign_tenant_id = _make_foreign_need(caller)
    group = StakeholderNeedsToolGroup()

    result = _exec(group, "needs.read", {"id": str(foreign_need.id)}, ctx)

    assert result.success is False
    assert result.error_code == "NOT_FOUND"


def test_update_foreign_tenant_need_returns_not_found(caller):
    """The update path looks the need up first — a foreign id never writes."""
    _tenant, _workspace, ctx, _user_id = caller
    foreign_need, _foreign_ctx, _foreign_tenant_id = _make_foreign_need(caller)
    group = StakeholderNeedsToolGroup()

    result = _exec(
        group,
        "needs.update",
        {"id": str(foreign_need.id), "title": "Hijacked"},
        ctx,
    )

    assert result.success is False
    assert result.error_code == "NOT_FOUND"


def test_outdate_foreign_tenant_need_returns_not_found(caller):
    """The soft-delete escape hatch cannot reach a foreign tenant's need."""
    _tenant, _workspace, ctx, _user_id = caller
    foreign_need, _foreign_ctx, _foreign_tenant_id = _make_foreign_need(caller)
    group = StakeholderNeedsToolGroup()

    result = _exec(group, "needs.outdate", {"id": str(foreign_need.id)}, ctx)

    assert result.success is False
    assert result.error_code == "NOT_FOUND"


def test_get_traces_foreign_tenant_need_returns_not_found(caller):
    """Trace enumeration is fenced by the same need lookup."""
    _tenant, _workspace, ctx, _user_id = caller
    foreign_need, _foreign_ctx, _foreign_tenant_id = _make_foreign_need(caller)
    group = StakeholderNeedsToolGroup()

    result = _exec(group, "needs.get_traces", {"id": str(foreign_need.id)}, ctx)

    assert result.success is False
    assert result.error_code == "NOT_FOUND"


def test_query_foreign_tenant_workspace_returns_empty_list(caller):
    """needs.query is tenant-scoped: a foreign workspace yields zero rows."""
    tenant, _workspace, ctx, _user_id = caller
    foreign_need, foreign_ctx, foreign_tenant_id = _make_foreign_need(caller)
    group = StakeholderNeedsToolGroup()

    result = _exec(
        group,
        "needs.query",
        {"workspace_id": str(foreign_need.workspace_id)},
        ctx,
    )

    assert result.success is True
    assert result.data["needs"] == []
    assert result.data["count"] == 0

    # Sanity: the row exists for its own tenant — the fence is the tenant
    # boundary, not a missing row.
    set_request_tenant(foreign_tenant_id)
    try:
        own = _exec(
            group,
            "needs.query",
            {"workspace_id": str(foreign_need.workspace_id)},
            foreign_ctx,
        )
    finally:
        clear_request_tenant()
        set_request_tenant(tenant.id)
    assert own.data["count"] == 1


# ---------------------------------------------------------------------------
# Service-error -> MCP-code mapping
# ---------------------------------------------------------------------------


def test_service_validation_error_maps_to_validation_error(caller):
    _tenant, workspace, ctx, _user_id = caller
    group, service = _group_with_service()
    service.create.side_effect = ValidationError("Title exceeds 500 characters.")

    result = _exec(
        group,
        "needs.create",
        {"workspace_id": str(workspace.id), "title": "Too Long Need"},
        ctx,
    )

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"
    assert result.message == "Title exceeds 500 characters."


def test_service_not_found_maps_to_not_found(caller):
    _tenant, _workspace, ctx, _user_id = caller
    group, service = _group_with_service()
    service.get.side_effect = NotFoundError("StakeholderNeed x not found.")

    result = _exec(group, "needs.update", {"id": str(uuid4())}, ctx)

    assert result.success is False
    assert result.error_code == "NOT_FOUND"


def test_service_permission_denied_is_not_mapped_to_ok(caller):
    """A PermissionDeniedError from the service never yields a success."""
    _tenant, _workspace, ctx, _user_id = caller
    group, service = _group_with_service()
    service.create.side_effect = PermissionDeniedError("editor required")

    result = _exec(
        group,
        "needs.create",
        {"workspace_id": str(uuid4()), "title": "Denied Need"},
        ctx,
    )

    assert result.success is False


def test_unmapped_service_error_is_masked(caller):
    """CWE-209 / fix #108: an unmapped exception never leaks its message."""
    _tenant, _workspace, ctx, _user_id = caller
    group, service = _group_with_service()
    service.get.side_effect = RuntimeError("SELECT * FROM secret_needs failed")

    result = _exec(group, "needs.update", {"id": str(uuid4())}, ctx)

    assert result.success is False
    assert result.error_code == "INTERNAL_ERROR"
    assert result.message == "An internal error occurred."
    assert "secret_needs" not in result.message


def test_unknown_tool_returns_unknown_tool(caller):
    """The dispatcher answers an unknown tool name, it does not raise."""
    _tenant, _workspace, ctx, _user_id = caller
    group = StakeholderNeedsToolGroup()

    result = _exec(group, "needs.teleport", {"id": str(uuid4())}, ctx)

    assert result.success is False
    assert result.error_code == "UNKNOWN_TOOL"
