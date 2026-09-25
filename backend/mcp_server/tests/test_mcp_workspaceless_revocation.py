"""Revocation on the MCP workspaceless fallback (CR-26, the untested branch).

Audit track CR-26 (``docs/se/reports/deep_audit/system-audit-2026-09/
09-evidence-register.md``). The pre-existing revocation coverage in
``test_mcp_workspace_scope.py`` (``test_comment_resolve_rejects_suspended_
target_role_without_mutation`` and its two siblings) all dispatch
``comment.resolve``, which names its target by id. ``comment.resolve`` has an
entry in ``mcp_server/workspace_scope._TOOL_TARGETS`` (line 173), so the
dispatcher resolves the comment's owning workspace and evaluates the RBAC gate
against it via ``_resolve_roles(ctx, workspace_id)`` — the *workspace-scoped*
branch.

That leaves the other branch untested: 21 of the 218 registered tools are WRITE
tools that carry no ``workspace_id`` parameter and no target-object entry. For
those, ``ToolRegistry._scoped_gate_context`` returns ``(ctx, None)`` and the gate
runs on the tenant-wide aggregate produced by
``ToolRegistry._resolve_global_roles`` (``tool_registry.py:1356-1370``, called at
line 1393). That helper reads roles live from the database on every dispatch and
degrades to ``()`` on any error (``except Exception: return ()``, line 1407), so
it is both security-critical and completely uncovered.

The claim under test is that a role revoked *after* the credential was issued
does not survive on this path: the fallback re-reads ``UserRole`` rather than
trusting anything cached in the key or the token.

The positive control matters as much as the denials: without it, a ``PERMISSION_
DENIED`` would also be produced by a tool that is simply broken or misrouted,
and the denials below would prove nothing. ``test_workspaceless_write_tool_is_
admitted_while_the_role_is_active`` therefore pins that the same tool, same key
and same setup are admitted when the role stands.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from django.utils import timezone

from auth_tenancy.context import AuthContext, AuthMethod
from auth_tenancy.models import UserRole
from mcp_server.tests.helpers import extract_error_code, extract_result, post_mcp
from mcp_server.tool_registry import ToolRegistry
from mcp_server.workspace_scope import resolve_target_workspace_id
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User

#: A WRITE tool with no ``workspace_id`` parameter and no ``_TOOL_TARGETS``
#: entry, so its gate runs on the workspaceless fallback. Its only required
#: parameters are ``key`` and ``definition``.
_TOOL = "link_type.create"

_PARAMS = {"key": "w1neg-workspaceless", "definition": {"kind": "DerivedFrom"}}


def _dispatch(api_key: str):
    """Run one dispatch through a fully real (unmocked) ToolRegistry."""
    return ToolRegistry().dispatch_request(
        tool_name=_TOOL, params=dict(_PARAMS), api_key=api_key
    )


# ---------------------------------------------------------------------------
# The tool really is on the workspaceless branch (guards for every test below)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_chosen_tool_takes_the_workspaceless_fallback_branch() -> None:
    """Pin the precondition: nothing in the call can resolve a target workspace.

    If a future change gave ``link_type.create`` a ``workspace_id`` parameter or
    a ``_TOOL_TARGETS`` entry, the denials below would silently start exercising
    the workspace-scoped branch again and would prove nothing about the
    fallback. This makes that a loud failure instead.
    """
    registry = ToolRegistry()
    registry._ensure_groups()
    group, route_error = registry._router.route(_TOOL)

    assert resolve_target_workspace_id(_TOOL, _PARAMS) is None
    assert registry._is_write_tool(_TOOL) is True
    assert route_error is None
    assert "workspace_id" not in group.schema_param_names(_TOOL)


# ---------------------------------------------------------------------------
# Positive control — the fallback does grant the role while it stands
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_workspaceless_write_tool_is_admitted_while_the_role_is_active(
    e2e_userrole_member: UserRole,
    e2e_api_key_member: str,
) -> None:
    """The fallback grants the write, so the denials below are not vacuous."""
    with patch(
        "application.link_type_facade.LinkTypeFacade.create_global",
        return_value={"key": _PARAMS["key"]},
    ) as handler:
        result = _dispatch(e2e_api_key_member)

    assert result.success is True, result.message
    handler.assert_called_once()


# ---------------------------------------------------------------------------
# Revocation on the workspaceless branch
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("revocation", ["suspended", "deleted"])
def test_workspaceless_write_tool_denies_a_role_revoked_after_the_key_was_issued(
    e2e_userrole_member: UserRole,
    e2e_api_key_member: str,
    revocation: str,
) -> None:
    """A role revoked after issuance must not survive on the fallback path.

    The key is minted while the role stands and is never touched afterwards —
    only the ``UserRole`` row changes. A cached-roles implementation would
    still admit this call; the live re-read does not.
    """
    assert e2e_userrole_member.suspended_at is None
    if revocation == "suspended":
        e2e_userrole_member.suspended_at = timezone.now()
        e2e_userrole_member.save(update_fields=["suspended_at"])
    else:
        e2e_userrole_member.delete()

    with patch(
        "application.link_type_facade.LinkTypeFacade.create_global"
    ) as handler:
        result = _dispatch(e2e_api_key_member)

    assert result.success is False
    assert result.error_code == "PERMISSION_DENIED"
    handler.assert_not_called()


@pytest.mark.django_db
def test_workspaceless_write_tool_denies_a_user_deactivated_after_the_key_was_issued(
    e2e_userrole_member: UserRole,
    e2e_api_key_member: str,
    e2e_user_member: User,
) -> None:
    """Deactivating the user must invalidate the already-issued key too.

    Distinct from the role cases above: this is caught one step earlier, at
    API-key validation, and must be reported as an auth failure rather than an
    authorisation one.
    """
    e2e_user_member.is_active = False
    e2e_user_member.save(update_fields=["is_active"])

    with patch(
        "application.link_type_facade.LinkTypeFacade.create_global"
    ) as handler:
        result = _dispatch(e2e_api_key_member)

    assert result.success is False
    assert result.error_code == "AUTH_FAILED"
    handler.assert_not_called()


# ---------------------------------------------------------------------------
# The fallback helper itself never yields a stale role
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("revocation", ["suspended", "deleted"])
def test_global_role_resolution_drops_a_role_revoked_after_issuance(
    e2e_tenant: Tenant,
    e2e_userrole_member: UserRole,
    e2e_user_member: User,
    revocation: str,
) -> None:
    """``_resolve_global_roles`` must not resurrect a revoked assignment.

    Pins the fail-soft branch at ``tool_registry.py:1393-1409`` directly: on both
    revocation kinds the helper returns an empty tuple, never the role the
    credential was originally issued against.
    """
    registry = ToolRegistry()
    probe = AuthContext(
        user_id=e2e_user_member.id,
        tenant_id=e2e_tenant.id,
        active_roles=(),
        auth_method=AuthMethod.API_KEY,
        api_key_id=None,
    )

    set_request_tenant(e2e_tenant.id)
    try:
        before = registry._resolve_global_roles(probe)
        if revocation == "suspended":
            e2e_userrole_member.suspended_at = timezone.now()
            e2e_userrole_member.save(update_fields=["suspended_at"])
        else:
            e2e_userrole_member.delete()
        after = registry._resolve_global_roles(probe)
    finally:
        clear_request_tenant()

    assert before == ("editor",)
    assert after == ()


@pytest.mark.django_db
def test_global_role_resolution_degrades_to_no_roles_when_the_lookup_fails(
    e2e_tenant: Tenant,
    e2e_userrole_member: UserRole,
    e2e_user_member: User,
) -> None:
    """The ``except -> ()`` branch must deny, not admit.

    A lookup that raises must cost the caller every role. If this branch ever
    changed to fall back to a cached or claimed role set, an outage in the
    authorisation service would become a privilege escalation.
    """
    registry = ToolRegistry()
    probe = AuthContext(
        user_id=e2e_user_member.id,
        tenant_id=e2e_tenant.id,
        active_roles=(),
        auth_method=AuthMethod.API_KEY,
        api_key_id=None,
    )

    set_request_tenant(e2e_tenant.id)
    try:
        with patch.object(
            type(registry._authz_service),
            "active_roles_across_workspaces",
            side_effect=RuntimeError("authz unavailable"),
        ):
            degraded = registry._resolve_global_roles(probe)
    finally:
        clear_request_tenant()

    assert degraded == ()


# ---------------------------------------------------------------------------
# The same claim over the real HTTP transport
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_transport_reports_permission_denied_after_revocation_without_the_header(
    member_client,
    e2e_userrole_member: UserRole,
) -> None:
    """End-to-end: the doubled assertion (status + error code) on the wire.

    ``test_mcp_workspace_scope.py`` asserts transport status *and* JSON-RPC
    error code; this keeps that convention for the workspaceless branch.
    """
    e2e_userrole_member.suspended_at = timezone.now()
    e2e_userrole_member.save(update_fields=["suspended_at"])

    response = post_mcp(member_client, _TOOL, dict(_PARAMS))

    assert response.status_code == 403, response.content
    assert extract_error_code(response) == "PERMISSION_DENIED"


@pytest.mark.django_db
def test_transport_admits_the_same_call_while_the_role_is_active(
    member_client,
    e2e_userrole_member: UserRole,
) -> None:
    """Positive control on the wire, so the denial above is attributable."""
    with patch(
        "application.link_type_facade.LinkTypeFacade.create_global",
        return_value={"key": _PARAMS["key"]},
    ):
        response = post_mcp(member_client, _TOOL, dict(_PARAMS))

    assert response.status_code == 200, response.content
    assert extract_result(response)["link_type"] == {"key": _PARAMS["key"]}
