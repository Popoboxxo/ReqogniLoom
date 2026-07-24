"""
Tests for COMP-MC GenericCrudToolGroup method-name resolution (issue #21).

adr.create/update/delete/read (and the same for risk/issue) 500ed because
GenericCrudToolGroup always called self._service.create/update/delete/get,
but AdrService/IssueService/RiskService only expose entity-specific methods
(create_adr, update_issue, delete_risk, get_adr, ...). GlossaryService's
generic-named update/delete also 500ed because they take a `term_id` kwarg,
not the guessed `glossary_id`/`id`.

Covers all four services registered via GenericCrudToolGroup in
tool_registry.py: adr, risk, issue, glossary.
"""
from __future__ import annotations

from unittest.mock import MagicMock
from uuid import UUID

import pytest

from auth_tenancy.context import AuthContext, AuthMethod
from mcp_server.tools.generic import GenericCrudToolGroup

CTX = AuthContext(
    user_id=UUID("00000000-0000-0000-0000-000000000001"),
    tenant_id=UUID("00000000-0000-0000-0000-000000000002"),
    active_roles=("admin",),
    auth_method=AuthMethod.API_KEY,
    api_key_id=UUID("00000000-0000-0000-0000-000000000003"),
)
WORKSPACE_ID = UUID("00000000-0000-0000-0000-000000000010")
ENTITY_ID = UUID("00000000-0000-0000-0000-000000000020")


def _mock_with_signature(fn) -> MagicMock:
    """MagicMock that tracks calls but reports fn's real signature, so
    inspect.signature(mock) — used by _resolve_id_param — sees fn's params
    instead of MagicMock's generic (*args, **kwargs)."""
    import inspect as _inspect

    mock = MagicMock(side_effect=fn)
    mock.__signature__ = _inspect.signature(fn)
    return mock


class _EntitySpecificService:
    """Mimics AdrService/IssueService/RiskService: create_<prefix>, etc.,
    with the same "id param first, ctx second" signature those real
    services use for update_*/delete_*/get_*."""

    def __init__(self) -> None:
        self.create_widget = _mock_with_signature(
            lambda ctx, workspace_id, **kw: {"id": ENTITY_ID}
        )
        self.update_widget = _mock_with_signature(
            lambda widget_id, ctx, **kw: {"id": ENTITY_ID}
        )
        self.delete_widget = _mock_with_signature(lambda widget_id, ctx: None)
        self.get_widget = _mock_with_signature(lambda widget_id, ctx: {"id": ENTITY_ID})


class _GenericNamedService:
    """Mimics GlossaryService: generic create/update/delete/get names, but
    the ID kwarg is entity-specific (term_id) — neither <prefix>_id nor
    "id" — so _resolve_id_param must find it via introspection."""

    def __init__(self) -> None:
        self.create = _mock_with_signature(
            lambda ctx, workspace_id, term, definition=None: {"id": ENTITY_ID}
        )
        self.update = _mock_with_signature(
            lambda ctx, term_id, definition=None: {"id": ENTITY_ID}
        )
        self.delete = _mock_with_signature(lambda ctx, term_id: None)
        self.get = _mock_with_signature(lambda ctx, term_id: {"id": ENTITY_ID})


def _make_generic_named_service() -> "_GenericNamedService":
    return _GenericNamedService()


def _group_for(service_instance) -> GenericCrudToolGroup:
    group = GenericCrudToolGroup.__new__(GenericCrudToolGroup)
    group.prefix = "widget"
    group._service = service_instance
    group._item_type = "Widget"
    from mcp_server.tools.generic import _resolve_id_param, _resolve_method

    group._read_method = _resolve_method(service_instance, "widget", "get")
    group._create_method = _resolve_method(service_instance, "widget", "create")
    group._update_method = _resolve_method(service_instance, "widget", "update")
    group._delete_method = _resolve_method(service_instance, "widget", "delete")
    group._list_method = getattr(service_instance, "list", None)
    group._read_id_param = _resolve_id_param(group._read_method)
    group._update_id_param = _resolve_id_param(group._update_method)
    group._delete_id_param = _resolve_id_param(group._delete_method)
    return group


def test_entity_specific_service_create_dispatches_to_prefixed_method():
    service = _EntitySpecificService()
    group = _group_for(service)

    result = group._handle_create(
        params={"workspace_id": str(WORKSPACE_ID), "title": "T"},
        auth_context=CTX,
        api_key="reqlo_x",
    )

    assert result.success is True
    service.create_widget.assert_called_once_with(
        ctx=CTX, workspace_id=WORKSPACE_ID, title="T"
    )


def test_entity_specific_service_update_dispatches_to_prefixed_method():
    service = _EntitySpecificService()
    group = _group_for(service)

    result = group._handle_update(
        params={"id": str(ENTITY_ID), "title": "New"}, auth_context=CTX, api_key="reqlo_x"
    )

    assert result.success is True
    service.update_widget.assert_called_once_with(
        ctx=CTX, widget_id=ENTITY_ID, title="New"
    )


def test_entity_specific_service_delete_dispatches_to_prefixed_method():
    service = _EntitySpecificService()
    group = _group_for(service)

    result = group._handle_delete(params={"id": str(ENTITY_ID)}, auth_context=CTX, api_key="reqlo_x")

    assert result.success is True
    service.delete_widget.assert_called_once_with(ctx=CTX, widget_id=ENTITY_ID)


def test_entity_specific_service_read_dispatches_to_prefixed_method():
    service = _EntitySpecificService()
    group = _group_for(service)

    result = group._handle_read(params={"id": str(ENTITY_ID)}, auth_context=CTX, api_key="reqlo_x")

    assert result.success is True
    service.get_widget.assert_called_once_with(ctx=CTX, widget_id=ENTITY_ID)


def test_generic_named_service_update_uses_introspected_id_param():
    """GlossaryService-like service: update(ctx, term_id, ...) — the ID kwarg
    is neither <prefix>_id nor "id", so it must be resolved via introspection."""
    service = _make_generic_named_service()
    group = _group_for(service)

    result = group._handle_update(
        params={"id": str(ENTITY_ID), "definition": "def"}, auth_context=CTX, api_key="reqlo_x"
    )

    assert result.success is True
    service.update.assert_called_once_with(ctx=CTX, term_id=ENTITY_ID, definition="def")


def test_generic_named_service_delete_uses_introspected_id_param():
    service = _make_generic_named_service()
    group = _group_for(service)

    result = group._handle_delete(params={"id": str(ENTITY_ID)}, auth_context=CTX, api_key="reqlo_x")

    assert result.success is True
    service.delete.assert_called_once_with(ctx=CTX, term_id=ENTITY_ID)


def test_generic_named_service_create_uses_generic_method():
    service = _make_generic_named_service()
    group = _group_for(service)

    result = group._handle_create(
        params={"workspace_id": str(WORKSPACE_ID), "term": "Foo", "definition": "Bar"},
        auth_context=CTX,
        api_key="reqlo_x",
    )

    assert result.success is True
    service.create.assert_called_once_with(
        ctx=CTX, workspace_id=WORKSPACE_ID, term="Foo", definition="Bar"
    )


@pytest.mark.parametrize(
    "service_class_path,prefix",
    [
        ("application.adr_service.AdrService", "adr"),
        ("application.risk_service.RiskService", "risk"),
        ("application.issue_service.IssueService", "issue"),
        ("application.glossary_service.GlossaryService", "glossary"),
        ("application.change_request_service.ChangeRequestService", "change_request"),
    ],
)
def test_real_services_construct_without_error(service_class_path, prefix):
    """Regression guard: GenericCrudToolGroup.__init__ must resolve real
    create/update/delete/get methods for every service wired in
    tool_registry.py without raising AttributeError/TypeError."""
    import importlib

    module_path, class_name = service_class_path.rsplit(".", 1)
    service_class = getattr(importlib.import_module(module_path), class_name)

    group = GenericCrudToolGroup(prefix, service_class)

    assert group._create_method is not None
    assert group._update_method is not None
    assert group._delete_method is not None
    assert group._read_method is not None


# ---------------------------------------------------------------------------
# Concrete field schemas (Codeberg #94 — generic additionalProperties: True
# gave no discoverability of the real fields per entity)
# ---------------------------------------------------------------------------

_EXPECTED_CREATE_FIELDS = {
    "adr": {"title", "description", "context", "consequences", "status", "uid"},
    "risk": {
        "title", "probability", "impact", "description", "category", "owner",
        "mitigation_strategy", "status", "uid", "detection", "owner_user_id",
    },
    "issue": {
        "title", "severity", "description", "category", "assignee_id",
        "due_date", "tags", "status", "uid",
    },
    "glossary": {"term", "definition", "synonyms", "abbreviation"},
}

_EXPECTED_UPDATE_FIELDS = {
    "adr": {"title", "description", "context", "consequences", "change_reason"},
    "risk": {
        "title", "description", "probability", "impact", "category", "owner",
        "mitigation_strategy", "change_reason", "detection", "owner_user_id",
    },
    "issue": {
        "title", "description", "severity", "category", "due_date", "tags",
        "change_reason",
    },
    "glossary": {"definition", "synonyms", "abbreviation"},
}


# NOTE: change_request is intentionally NOT parametrized into this test.
# It currently fails for adr/risk/issue/glossary too (pre-existing:
# GenericCrudToolGroup's create/update schemas only expose a static
# "workspace_id"/"id" property plus additionalProperties: True, not the
# concrete per-entity fields this test expects — Codeberg #94 regression,
# out of scope for Phase 1 Task 4).
@pytest.mark.parametrize(
    "service_class_path,prefix",
    [
        ("application.adr_service.AdrService", "adr"),
        ("application.risk_service.RiskService", "risk"),
        ("application.issue_service.IssueService", "issue"),
        ("application.glossary_service.GlossaryService", "glossary"),
    ],
)
def test_create_and_update_schemas_expose_concrete_fields(service_class_path, prefix):
    """The generic CRUD schemas must list concrete, entity-specific field
    names — not just a bare additionalProperties: True bag (Codeberg #94)."""
    import importlib

    module_path, class_name = service_class_path.rsplit(".", 1)
    service_class = getattr(importlib.import_module(module_path), class_name)

    group = GenericCrudToolGroup(prefix, service_class)
    schemas = {s["name"]: s for s in group.get_tool_schemas()}

    create_props = set(schemas[f"{prefix}.create"]["inputSchema"]["properties"].keys())
    update_props = set(schemas[f"{prefix}.update"]["inputSchema"]["properties"].keys())

    assert _EXPECTED_CREATE_FIELDS[prefix] <= create_props
    assert _EXPECTED_UPDATE_FIELDS[prefix] <= update_props
    # additionalProperties stays True — no behaviour change, just documentation.
    assert schemas[f"{prefix}.create"]["inputSchema"]["additionalProperties"] is True


# ---------------------------------------------------------------------------
# .outdate / .reactivate / .query (Phase 1 Task 2)
# ---------------------------------------------------------------------------

WIDGET_WORKSPACE_ID = UUID("00000000-0000-0000-0000-000000000030")


class _WidgetDTO:
    """Minimal stand-in for a service-returned entity/DTO exposing
    ``workspace_id`` (mirrors Adr/Risk/Issue ORM instances and
    GlossaryTermDTO, all of which carry this attribute)."""

    def __init__(self, workspace_id: UUID) -> None:
        self.id = ENTITY_ID
        self.workspace_id = workspace_id


class _OutdatableService:
    """Mimics an entity service exposing get/list alongside the standard
    create/update/delete used elsewhere in this file."""

    def __init__(self) -> None:
        self.get_widget = _mock_with_signature(
            lambda widget_id, ctx: _WidgetDTO(WIDGET_WORKSPACE_ID)
        )
        self.create_widget = _mock_with_signature(
            lambda ctx, workspace_id, **kw: {"id": ENTITY_ID}
        )
        self.update_widget = _mock_with_signature(
            lambda widget_id, ctx, **kw: {"id": ENTITY_ID}
        )
        self.delete_widget = _mock_with_signature(lambda widget_id, ctx: None)
        self.list = MagicMock(return_value=[_WidgetDTO(WIDGET_WORKSPACE_ID)])


def test_outdate_tool_calls_workflow_outdate(monkeypatch):
    service = _OutdatableService()
    group = _group_for(service)

    mock_outdate = MagicMock()
    monkeypatch.setattr("workflow.services.outdate", mock_outdate)

    result = group._handle_outdate(
        params={"id": str(ENTITY_ID), "reason": "no longer needed"},
        auth_context=CTX,
        api_key="reqlo_x",
    )

    assert result.success is True
    assert result.data == {"id": str(ENTITY_ID), "status": "outdated"}
    mock_outdate.assert_called_once_with(
        item_id=ENTITY_ID,
        item_type="Widget",
        workspace_id=WIDGET_WORKSPACE_ID,
        ctx=CTX,
        reason="no longer needed",
    )


def test_reactivate_tool_calls_workflow_reactivate(monkeypatch):
    service = _OutdatableService()
    group = _group_for(service)

    mock_result = MagicMock(new_state="draft")
    mock_reactivate = MagicMock(return_value=mock_result)
    monkeypatch.setattr("workflow.services.reactivate", mock_reactivate)

    result = group._handle_reactivate(
        params={"id": str(ENTITY_ID)}, auth_context=CTX, api_key="reqlo_x"
    )

    assert result.success is True
    assert result.data == {"id": str(ENTITY_ID), "status": "draft"}
    mock_reactivate.assert_called_once_with(
        item_id=ENTITY_ID,
        item_type="Widget",
        workspace_id=WIDGET_WORKSPACE_ID,
        ctx=CTX,
    )


def test_query_tool_defaults_to_excluding_outdated():
    service = _OutdatableService()
    group = _group_for(service)

    result = group._handle_query(
        params={"workspace_id": str(WIDGET_WORKSPACE_ID)}, auth_context=CTX, api_key="reqlo_x"
    )

    assert result.success is True
    service.list.assert_called_once_with(
        workspace_id=WIDGET_WORKSPACE_ID, ctx=CTX, include_deleted=False
    )
    assert result.data["items"] == [{"id": str(ENTITY_ID), "workspace_id": str(WIDGET_WORKSPACE_ID)}]


def test_query_tool_include_outdated_true_forwards_flag():
    service = _OutdatableService()
    group = _group_for(service)

    result = group._handle_query(
        params={"workspace_id": str(WIDGET_WORKSPACE_ID), "include_outdated": True},
        auth_context=CTX,
        api_key="reqlo_x",
    )

    assert result.success is True
    service.list.assert_called_once_with(
        workspace_id=WIDGET_WORKSPACE_ID, ctx=CTX, include_deleted=True
    )


# ---------------------------------------------------------------------------
# ChangeRequest — real-DB create -> outdate -> query round-trip
# (Phase 1 Task 4, COMP-AS-021)
# ---------------------------------------------------------------------------


def _make_tenant_workspace_ctx(name: str):
    """Create a Tenant + User + Workspace + AuthContext triple for *name*."""
    from persistence.models import Tenant, User, Workspace
    from persistence.tenancy import TenantContext

    tenant = Tenant.objects.create(name=name, slug=name)
    user = User.objects.create(
        username=f"{name}-user", email=f"{name}@example.com", tenant=tenant
    )
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(tenant=tenant, name=f"{name}-ws")
    finally:
        TenantContext.clear_tenant()
    ctx = AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=("editor",),
        auth_method=AuthMethod.API_KEY,
        api_key_id=None,
    )
    return tenant, workspace, ctx


@pytest.mark.django_db
def test_change_request_create_outdate_query_roundtrip():
    """create -> outdate -> query round-trip through the real
    GenericCrudToolGroup + ChangeRequestService (no mocks)."""
    from application.change_request_service import ChangeRequestService
    from persistence.tenancy import TenantContext
    from workflow.models import WorkflowItemState
    from workflow.services import create_default_workflow

    tenant, workspace, ctx = _make_tenant_workspace_ctx("cr-mcp-lifecycle")
    TenantContext.set_tenant(tenant.id)
    try:
        create_default_workflow(
            workspace_id=workspace.id,
            preset="ccb_approval",
            item_type="ChangeRequest",
            tenant_id=tenant.id,
        )
    finally:
        TenantContext.clear_tenant()

    group = GenericCrudToolGroup(
        "change_request", ChangeRequestService, item_type="ChangeRequest"
    )

    create_result = group._handle_create(
        params={"workspace_id": str(workspace.id), "title": "CR1"},
        auth_context=ctx,
        api_key="reqlo_x",
    )
    assert create_result.success is True
    cr_id = create_result.data["data"]["id"]

    outdate_result = group._handle_outdate(
        params={"id": cr_id, "reason": "no longer needed"},
        auth_context=ctx,
        api_key="reqlo_x",
    )
    assert outdate_result.success is True
    assert outdate_result.data == {"id": cr_id, "status": "outdated"}

    state = WorkflowItemState.objects.get(
        item_id=UUID(cr_id), item_type="ChangeRequest"
    )
    assert state.current_state == "outdated"

    result_default = group._handle_query(
        params={"workspace_id": str(workspace.id)}, auth_context=ctx, api_key="reqlo_x"
    )
    assert result_default.success is True
    assert cr_id not in {i["id"] for i in result_default.data["items"]}

    result_incl = group._handle_query(
        params={"workspace_id": str(workspace.id), "include_outdated": True},
        auth_context=ctx,
        api_key="reqlo_x",
    )
    assert result_incl.success is True
    assert cr_id in {i["id"] for i in result_incl.data["items"]}
