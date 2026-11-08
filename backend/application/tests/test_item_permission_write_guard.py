"""ItemPermission on the write paths of every artifact CRUD service (#1716).

Before this guard, ``ServiceBase._assert_write_permission`` only checked the
coarse RBAC matrix. An item-level rule (``read``/``none``) therefore stopped
*reads* in the search layer but never a REST/MCP **update or delete** — an
editor could edit or soft-delete an artifact an admin had explicitly locked
down, and ``none`` was indistinguishable from "no rule".

The matrix below runs each of the eight services named in the plan through
both write paths with a real rule row and a real ORM row:

* ``read`` rule → ``PermissionDeniedError`` (REST 403),
* ``none`` rule → ``NotFoundError`` (REST 404),
* no rule → the helper returns (RBAC alone decides; unchanged),
* artifact-scoped rule beats the workspace-wide rule.

``test_rest_requirement_patch_and_delete_are_blocked`` and the MCP test at the
bottom prove both transports inherit the service-level gate.
"""
from __future__ import annotations

import uuid
from collections.abc import Callable

import pytest

from application.adr_service import AdrService
from application.architecture_service import ArchitectureService
from application.base import NotFoundError, PermissionDeniedError
from application.change_request_service import ChangeRequestService
from application.glossary_service import GlossaryService
from application.issue_service import IssueService
from application.requirement_service import RequirementService
from application.risk_service import RiskService
from application.test_service import TestService
from auth_tenancy.context import AuthContext, AuthMethod
from auth_tenancy.models import (
    ITEM_PERMISSION_NONE,
    ITEM_PERMISSION_READ,
    ITEM_PERMISSION_WRITE,
    ItemPermission,
)
from auth_tenancy.services.item_permission import ItemPermissionService
from auth_tenancy.services.permission_cache import PermissionCache
from persistence.models import (
    Adr,
    ArchitectureElement,
    Artifact,
    ChangeRequest,
    GlossaryTerm,
    Issue,
    Requirement,
    Risk,
    Tenant,
    TestCase,
    User,
    Workspace,
)
from persistence.tenancy import TenantContext

_ARTIFACT_TYPE = {
    "Requirement": "requirement",
    "ArchitectureElement": "architecture_element",
    "Risk": "risk",
    "Issue": "issue",
    "Adr": "adr",
    "TestCase": "test_case",
    "GlossaryTerm": "glossary_term",
    "ChangeRequest": "change_request",
}


@pytest.fixture(autouse=True)
def _clear_permission_cache():
    PermissionCache.clear_thread()
    yield
    PermissionCache.clear_thread()


@pytest.fixture
def tenant(db) -> Tenant:
    return Tenant.objects.create(name="IPW-T", slug="ipw-t", is_active=True)


@pytest.fixture
def workspace(tenant) -> Workspace:
    TenantContext.set_tenant(tenant.id)
    try:
        return Workspace.objects.create(
            tenant=tenant, name="IPW-WS", preset={"name": "extended"}
        )
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def member(tenant) -> User:
    TenantContext.set_tenant(tenant.id)
    try:
        user = User.objects.create(
            username="ipw-editor", email="ipw-editor@t.test", tenant=tenant
        )
        user.set_password("hunter2pass")
        user.save(update_fields=["password"])
        return user
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def ctx(tenant, member) -> AuthContext:
    return AuthContext(
        user_id=member.id,
        tenant_id=tenant.id,
        active_roles=("editor",),
        auth_method=AuthMethod.BEARER_TOKEN,
    )


def _create_row(kind: str, tenant: Tenant, workspace: Workspace):
    """Create a real Artifact + entity row for *kind* (no service call needed).

    The item-level guard runs immediately after the entity is loaded and before
    any mutation, which is exactly what these tests assert — so the row only has
    to be loadable, not fully provisioned through its create service.
    """
    TenantContext.set_tenant(tenant.id)
    try:
        artifact = Artifact.objects.create(
            tenant=tenant,
            workspace=workspace,
            artifact_type=_ARTIFACT_TYPE[kind],
        )
        common = {"tenant": tenant, "artifact": artifact}
        if kind == "Requirement":
            return Requirement.objects.create(
                **common, workspace=workspace, title="Req"
            )
        if kind == "ArchitectureElement":
            return ArchitectureElement.objects.create(**common, title="Element")
        if kind == "Risk":
            return Risk.objects.create(
                **common, workspace_id=workspace.id, title="Risk"
            )
        if kind == "Issue":
            return Issue.objects.create(
                **common, workspace_id=workspace.id, title="Issue"
            )
        if kind == "Adr":
            return Adr.objects.create(
                **common, workspace_id=workspace.id, title="ADR"
            )
        if kind == "TestCase":
            return TestCase.objects.create(**common, title="Case")
        if kind == "GlossaryTerm":
            return GlossaryTerm.objects.create(
                **common, workspace=workspace, term="Term", definition="Def"
            )
        if kind == "ChangeRequest":
            return ChangeRequest.objects.create(
                **common, workspace_id=workspace.id, title="CR"
            )
        raise AssertionError(f"unknown kind {kind}")
    finally:
        TenantContext.clear_tenant()


def _grant(
    tenant: Tenant,
    workspace: Workspace,
    member: User,
    artifact: Artifact | None,
    level: str,
) -> None:
    ItemPermission.unscoped.create(
        tenant=tenant,
        user=member,
        workspace=workspace,
        artifact=artifact,
        permission_level=level,
    )


#: ``kind`` → (update callable, delete callable). Table-driven so a future
#: service addition is a one-line change and cannot be forgotten silently.
_CALLERS: dict[str, tuple[Callable, Callable]] = {
    "Requirement": (
        lambda row, ctx: RequirementService().update_requirement(
            row.id, ctx, title="changed"
        ),
        lambda row, ctx: RequirementService().delete_requirement(row.id, ctx),
    ),
    "ArchitectureElement": (
        lambda row, ctx: ArchitectureService().update_architecture_element(
            row.id, ctx, title="changed"
        ),
        lambda row, ctx: ArchitectureService().delete_architecture_element(
            row.id, ctx
        ),
    ),
    "Risk": (
        lambda row, ctx: RiskService().update_risk(row.id, ctx, title="changed"),
        lambda row, ctx: RiskService().delete_risk(row.id, ctx),
    ),
    "Issue": (
        lambda row, ctx: IssueService().update_issue(row.id, ctx, title="changed"),
        lambda row, ctx: IssueService().delete_issue(row.id, ctx),
    ),
    "Adr": (
        lambda row, ctx: AdrService().update_adr(row.id, ctx, title="changed"),
        lambda row, ctx: AdrService().delete_adr(row.id, ctx),
    ),
    "TestCase": (
        lambda row, ctx: TestService().update_test_case(row.id, ctx, title="c"),
        lambda row, ctx: TestService().delete_test_case(row.id, ctx),
    ),
    "GlossaryTerm": (
        lambda row, ctx: GlossaryService().update(ctx, row.id, term="changed"),
        lambda row, ctx: GlossaryService().delete(ctx, row.id),
    ),
    "ChangeRequest": (
        lambda row, ctx: ChangeRequestService().update_change_request(
            row.id, ctx, title="changed"
        ),
        lambda row, ctx: ChangeRequestService().delete_change_request(row.id, ctx),
    ),
}

_KINDS = tuple(_CALLERS)


@pytest.mark.django_db
@pytest.mark.parametrize("kind", _KINDS)
@pytest.mark.parametrize("action", ("update", "delete"))
def test_read_rule_denies_the_write_path(kind, action, tenant, workspace, member, ctx):
    row = _create_row(kind, tenant, workspace)
    _grant(tenant, workspace, member, row.artifact, ITEM_PERMISSION_READ)

    with pytest.raises(PermissionDeniedError):
        _CALLERS[kind][0 if action == "update" else 1](row, ctx)


@pytest.mark.django_db
@pytest.mark.parametrize("kind", _KINDS)
@pytest.mark.parametrize("action", ("update", "delete"))
def test_none_rule_answers_not_found(kind, action, tenant, workspace, member, ctx):
    row = _create_row(kind, tenant, workspace)
    _grant(tenant, workspace, member, row.artifact, ITEM_PERMISSION_NONE)

    # 404, not 403: an explicit denial must not confirm the artifact exists.
    with pytest.raises(NotFoundError):
        _CALLERS[kind][0 if action == "update" else 1](row, ctx)


@pytest.mark.django_db
def test_update_test_status_is_gated_too(tenant, workspace, member, ctx):
    """``update_test_status`` does not match the ``update_*`` naming convention,
    so the explicit method list is what protects it."""
    row = _create_row("TestCase", tenant, workspace)
    _grant(tenant, workspace, member, row.artifact, ITEM_PERMISSION_READ)

    with pytest.raises(PermissionDeniedError):
        TestService().update_test_status(row.id, "Passed", ctx)


@pytest.mark.django_db
def test_no_rule_lets_the_helper_pass(tenant, workspace, member, ctx):
    row = _create_row("Requirement", tenant, workspace)
    TenantContext.set_tenant(tenant.id)
    try:
        # No exception: RBAC alone decides, exactly as before the change.
        RequirementService()._assert_item_write_permission(
            ctx, row.artifact_id, workspace_id=workspace.id
        )
    finally:
        TenantContext.clear_tenant()


@pytest.mark.django_db
def test_write_rule_lets_the_helper_pass(tenant, workspace, member, ctx):
    row = _create_row("Requirement", tenant, workspace)
    _grant(tenant, workspace, member, row.artifact, ITEM_PERMISSION_WRITE)
    TenantContext.set_tenant(tenant.id)
    try:
        RequirementService()._assert_item_write_permission(
            ctx, row.artifact_id, workspace_id=workspace.id
        )
    finally:
        TenantContext.clear_tenant()


@pytest.mark.django_db
def test_artifact_scoped_rule_beats_the_workspace_rule_in_both_directions(
    tenant, workspace, member, ctx
):
    """Resolution order is artifact-scoped → workspace-wide (item_permission §1.4)."""
    first = _create_row("Requirement", tenant, workspace)
    second = _create_row("Requirement", tenant, workspace)

    # Workspace-wide write, artifact-scoped read → denied for that artifact.
    _grant(tenant, workspace, member, None, ITEM_PERMISSION_WRITE)
    _grant(tenant, workspace, member, first.artifact, ITEM_PERMISSION_READ)

    TenantContext.set_tenant(tenant.id)
    try:
        with pytest.raises(PermissionDeniedError):
            RequirementService()._assert_item_write_permission(
                ctx, first.artifact_id, workspace_id=workspace.id
            )
        # The second artifact falls back to the workspace rule → allowed.
        RequirementService()._assert_item_write_permission(
            ctx, second.artifact_id, workspace_id=workspace.id
        )
    finally:
        TenantContext.clear_tenant()


@pytest.mark.django_db
def test_workspace_wide_read_rule_blocks_an_artifact_scoped_write_rule(
    tenant, workspace, member, ctx
):
    row = _create_row("Requirement", tenant, workspace)
    _grant(tenant, workspace, member, None, ITEM_PERMISSION_READ)
    _grant(tenant, workspace, member, row.artifact, ITEM_PERMISSION_WRITE)
    other = _create_row("Requirement", tenant, workspace)

    TenantContext.set_tenant(tenant.id)
    try:
        # The artifact-scoped rule wins → allowed.
        RequirementService()._assert_item_write_permission(
            ctx, row.artifact_id, workspace_id=workspace.id
        )
        # A different artifact only sees the workspace-wide read rule.
        with pytest.raises(PermissionDeniedError):
            RequirementService()._assert_item_write_permission(
                ctx, other.artifact_id, workspace_id=workspace.id
            )
    finally:
        TenantContext.clear_tenant()


@pytest.mark.django_db
def test_mcp_requirement_update_maps_the_denial():
    """The MCP tool inherits the gate and maps it to ``PERMISSION_DENIED``."""
    from mcp_server.tools.requirements import RequirementsToolGroup

    tenant = Tenant.objects.create(name="IPW-MCP", slug="ipw-mcp", is_active=True)
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="IPW-MCP-WS", preset={"name": "extended"}
        )
        member = User.objects.create(
            username="ipw-mcp-editor", email="ipw-mcp@t.test", tenant=tenant
        )
        user_ctx = AuthContext(
            user_id=member.id,
            tenant_id=tenant.id,
            active_roles=("editor",),
            auth_method=AuthMethod.BEARER_TOKEN,
        )
        row = _create_row("Requirement", tenant, workspace)
        _grant(tenant, workspace, member, row.artifact, ITEM_PERMISSION_READ)

        result = RequirementsToolGroup().execute_tool(
            tool_name="requirement.update",
            params={"id": str(row.id), "data": {"title": "changed"}},
            auth_context=user_ctx,
            api_key="reqlo_test_key_placeholder",
        )
    finally:
        TenantContext.clear_tenant()

    assert result.success is False
    assert result.error_code == "PERMISSION_DENIED"


@pytest.mark.django_db
def test_rest_requirement_patch_and_delete_are_blocked():
    """Both REST verbs inherit the service gate (403 on read, 404 on none)."""
    from rest_framework.test import APIClient

    from auth_tenancy.models import ROLE_EDITOR, UserRole

    tenant = Tenant.objects.create(name="IPW-REST", slug="ipw-rest", is_active=True)
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="IPW-REST-WS", preset={"name": "extended"}
        )
        member = User.objects.create(
            username="ipw-rest-editor", email="ipw-rest@t.test", tenant=tenant
        )
        member.set_password("hunter2pass")
        member.save(update_fields=["password"])
        UserRole.objects.create(
            tenant=tenant, user=member, workspace=workspace, role=ROLE_EDITOR
        )
        row = _create_row("Requirement", tenant, workspace)
    finally:
        TenantContext.clear_tenant()

    client = APIClient()
    login = client.post(
        "/api/v1/auth/login/",
        {"username": "ipw-rest-editor", "password": "hunter2pass"},
        format="json",
    )
    assert login.status_code == 200, login.content

    _grant(tenant, workspace, member, row.artifact, ITEM_PERMISSION_READ)
    patch_read = client.patch(
        f"/api/v1/requirements/{row.id}/", {"title": "nope"}, format="json"
    )
    assert patch_read.status_code == 403, patch_read.content

    # A `none` rule answers 404 on update and delete.
    ItemPermission.unscoped.filter(
        user=member, artifact=row.artifact
    ).update(permission_level=ITEM_PERMISSION_NONE)
    PermissionCache.clear_thread()

    patch_none = client.patch(
        f"/api/v1/requirements/{row.id}/", {"title": "nope"}, format="json"
    )
    assert patch_none.status_code == 404, patch_none.content
    delete_none = client.delete(f"/api/v1/requirements/{row.id}/")
    assert delete_none.status_code == 404, delete_none.content
