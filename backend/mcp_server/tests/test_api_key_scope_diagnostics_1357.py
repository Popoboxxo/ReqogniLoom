"""#1357 — workspace-restricted key: artifact-derived scope + honest diagnostics.

Repro from the issue (beta.21 QA pipeline):

* a key fenced to workspace A failed ``requirement.suggest_level`` for a
  requirement **in workspace A** with the workspace-scope message, because the
  tool was missing from ``mcp_server.workspace_scope._TOOL_TARGETS`` — no
  target workspace resolved, so the fail-closed fence denied;
* the same scope text masked a wrong parameter name
  (``suggestion.accept {"suggestion_id": ...}`` instead of ``{"id": ...}``),
  sending the agent debugging the key instead of the call.

Contract pinned here:

1. the fence resolves against the target **object's own workspace** (fix for
   ``requirement.suggest_level`` and the #1288 acceptance-criteria write pair),
2. genuinely foreign objects stay denied, fail-closed, with the scope message,
3. parameter-level defects (missing/typo'd/malformed target id) answer with the
   validation class (JSON-RPC ``-32602``) — and the call is still never
   executed, so fail-closed is preserved,
4. a well-formed id that simply resolves to no row keeps the scope denial
   (a nonexistent object must not become distinguishable from a fenced one),
5. an unfenced key's behaviour is unchanged,
6. security review (HIGH): an undeclared ``workspace_id`` in the call must not
   reopen the fence through the dispatcher's workspace shortcut. Since #1376
   the dispatcher itself drops such a parameter before the gate, so the target
   object's workspace drives the fence and the call is denied before the
   handler; the W13b/W13c handler guards remain as defense in depth for direct
   (non-dispatch) calls,
7. security review (advisory): ``target_param_error`` inspects **every** target
   candidate — a malformed one stays diagnosed even when another candidate is
   well-formed.
"""
from __future__ import annotations

import json
from datetime import timedelta
from typing import Any
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.utils import timezone

from auth_tenancy.services.authentication import AuthenticationService
from mcp_server.tool_registry import ToolRegistry
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Artifact, Requirement, Suggestion, Tenant, Workspace
from presets.models import WorkspacePresetConfig

pytestmark = pytest.mark.django_db

SCOPE_MESSAGE_FRAGMENT = "restricted to specific workspaces"


# ---------------------------------------------------------------------------
# Seed helpers (mirror test_mcp_workspace_scope.py)
# ---------------------------------------------------------------------------


def _make_workspace(tenant: Tenant, name: str, preset: dict[str, Any]) -> Workspace:
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name=name, is_active=True, preset=preset
        )
    finally:
        clear_request_tenant()
    WorkspacePresetConfig.unscoped.create(
        tenant=tenant,
        workspace=workspace,
        active_tier="extended",
        terminology_profile="dev_mode",
        downgrade_policy="allow",
    )
    return workspace


def _make_requirement(workspace: Workspace, title: str) -> Requirement:
    set_request_tenant(workspace.tenant_id)
    try:
        artifact = Artifact.objects.create(
            tenant=workspace.tenant, workspace=workspace, artifact_type="Requirement"
        )
        return Requirement.objects.create(
            tenant=workspace.tenant,
            workspace=workspace,
            artifact=artifact,
            title=title,
            description="seeded by #1357 diagnostics test",
        )
    finally:
        clear_request_tenant()


def _make_suggestion(workspace: Workspace) -> Suggestion:
    set_request_tenant(workspace.tenant_id)
    try:
        return Suggestion.unscoped.create(
            tenant=workspace.tenant,
            workspace=workspace,
            kind="trace_link",
            status=Suggestion.Status.OPEN,
            producer="test",
            payload={},
            target_item_type="",
        )
    finally:
        clear_request_tenant()


def _dispatch(tool_name: str, params: dict[str, Any], api_key: str):
    return ToolRegistry().dispatch_request(
        tool_name=tool_name, params=params, api_key=api_key
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def foreign_workspace(e2e_tenant: Tenant, e2e_preset: dict[str, Any]) -> Workspace:
    """Workspace B — same tenant, no role for any e2e user."""
    return _make_workspace(e2e_tenant, "W13b Foreign Workspace B", e2e_preset)


@pytest.fixture
def foreign_requirement(foreign_workspace: Workspace) -> Requirement:
    return _make_requirement(foreign_workspace, "W13b secret req in B")


@pytest.fixture
def home_requirement(e2e_workspace: Workspace) -> Requirement:
    return _make_requirement(e2e_workspace, "W13b req in A")


@pytest.fixture
def fenced_key(
    e2e_tenant: Tenant,
    e2e_workspace: Workspace,
    e2e_user_member,
    e2e_userrole_member,
) -> str:
    """Write-scoped agent key fenced to workspace A.

    The owner (``e2e_user_member``) holds Editor **in A** via
    ``e2e_userrole_member`` — so for the fenced key every successful call must
    pass both the fence and the workspace-scoped RBAC gate, and every denial is
    attributable to the fence / parameter diagnosis, not to missing roles.
    """
    return (
        AuthenticationService()
        .create_api_key(
            user_id=e2e_user_member.id,
            tenant_id=e2e_tenant.id,
            name=f"w13b-fenced-{uuid4().hex[:8]}",
            principal_type="agent",
            agent_label="w13b-agent",
            scope="write",
            workspace_ids=[str(e2e_workspace.id)],
            expires_at=timezone.now() + timedelta(days=1),
        )
        .plaintext
    )


# ---------------------------------------------------------------------------
# 1+2. Fence resolves against the artifact's workspace; foreign stays denied
# ---------------------------------------------------------------------------


class TestFencedKeyResolvesTargetWorkspace:
    def test_suggest_level_for_object_in_own_workspace_is_allowed(
        self,
        e2e_tenant: Tenant,
        e2e_workspace: Workspace,
        fenced_key: str,
        home_requirement: Requirement,
    ) -> None:
        """The #1357 repro, positive control: object in the key's workspace."""
        result = _dispatch(
            "requirement.suggest_level", {"id": str(home_requirement.id)}, fenced_key
        )

        assert result.success is True, result.message
        assert result.data["suggestion"]["kind"] == "requirement_level"
        assert (
            Suggestion.unscoped.filter(
                tenant=e2e_tenant,
                workspace=e2e_workspace,
                kind="requirement_level",
                status=Suggestion.Status.OPEN,
            ).count()
            == 1
        )

    @pytest.mark.parametrize(
        "tool_name",
        [
            "requirement.suggest_level",
            "requirement.acceptance_criteria.set",
            "requirement.acceptance_criteria.check",
        ],
    )
    def test_requirement_target_tools_deny_foreign_workspace_fail_closed(
        self,
        tool_name: str,
        fenced_key: str,
        foreign_requirement: Requirement,
    ) -> None:
        with patch(
            "application.requirement_level_service.RequirementLevelService.propose_level"
        ) as suggest_handler, patch(
            "application.requirement_service.RequirementService.set_acceptance_criteria"
        ) as set_handler, patch(
            "application.requirement_service.RequirementService.update_acceptance_criterion"
        ) as check_handler:
            result = _dispatch(tool_name, {"id": str(foreign_requirement.id)}, fenced_key)

        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED"
        assert SCOPE_MESSAGE_FRAGMENT in result.message
        suggest_handler.assert_not_called()
        set_handler.assert_not_called()
        check_handler.assert_not_called()

    def test_acceptance_criteria_set_allowed_in_own_workspace(
        self,
        fenced_key: str,
        home_requirement: Requirement,
    ) -> None:
        """The #1288 write sibling resolves through the requirement's workspace."""
        with patch(
            "application.requirement_service.RequirementService.set_acceptance_criteria",
            return_value={"criteria": [], "total": 0},
        ) as handler:
            result = _dispatch(
                "requirement.acceptance_criteria.set",
                {"id": str(home_requirement.id), "criteria": []},
                fenced_key,
            )

        assert result.success is True, result.message
        handler.assert_called_once()

    def test_acceptance_criteria_check_allowed_in_own_workspace(
        self,
        fenced_key: str,
        home_requirement: Requirement,
    ) -> None:
        with patch(
            "application.requirement_service.RequirementService.update_acceptance_criterion",
            return_value={"criteria": [], "total": 0},
        ) as handler:
            result = _dispatch(
                "requirement.acceptance_criteria.check",
                {"id": str(home_requirement.id), "index": 0, "fulfilled": True},
                fenced_key,
            )

        assert result.success is True, result.message
        handler.assert_called_once()


# ---------------------------------------------------------------------------
# 3. Parameter defects answer -32602-class, not the scope text
# ---------------------------------------------------------------------------


class TestParameterErrorsAreNotScopeText:
    def test_wrong_parameter_name_is_a_validation_error(
        self,
        fenced_key: str,
        e2e_workspace: Workspace,
    ) -> None:
        """Issue repro #2: ``suggestion_id`` sent where ``id`` is required."""
        suggestion = _make_suggestion(e2e_workspace)

        with patch(
            "application.suggestion_service.SuggestionService.accept"
        ) as handler:
            result = _dispatch(
                "suggestion.accept", {"suggestion_id": str(suggestion.id)}, fenced_key
            )

        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"
        assert "suggestion_id" in result.message
        assert SCOPE_MESSAGE_FRAGMENT not in result.message
        handler.assert_not_called()
        suggestion.refresh_from_db()
        assert suggestion.status == "open"

    def test_missing_target_parameter_is_a_validation_error(
        self,
        fenced_key: str,
    ) -> None:
        result = _dispatch("requirement.suggest_level", {}, fenced_key)

        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"
        assert "'id'" in result.message
        assert SCOPE_MESSAGE_FRAGMENT not in result.message

    def test_malformed_target_id_is_a_validation_error(
        self,
        fenced_key: str,
    ) -> None:
        result = _dispatch("requirement.suggest_level", {"id": "not-a-uuid"}, fenced_key)

        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"
        assert "'id'" in result.message
        assert SCOPE_MESSAGE_FRAGMENT not in result.message

    def test_validation_error_class_maps_to_jsonrpc_invalid_params(self) -> None:
        """The issue's ``-32602`` demand, pinned at the wire mapping."""
        from mcp_server.protocol_handler import ErrorFormatter

        assert ErrorFormatter.format_error("VALIDATION_ERROR")["code"] == -32602

    def test_resolved_but_foreign_target_keeps_the_scope_message(
        self,
        fenced_key: str,
    ) -> None:
        """A well-formed id resolving to *no row* must not turn into a param error.

        Fail-closed branch (the object is either gone or fenced out): the
        parameter diagnosis must stay silent so a nonexistent object never
        becomes distinguishable from a fenced-out one through the error class.
        """
        result = _dispatch("requirement.suggest_level", {"id": str(uuid4())}, fenced_key)

        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED"
        assert SCOPE_MESSAGE_FRAGMENT in result.message


# ---------------------------------------------------------------------------
# 4. Wire contract: the JSON-RPC codes the issue names, via ProtocolHandler
# ---------------------------------------------------------------------------


class TestWireErrorContract:
    """Observe the codes on the direct-method surface the QA pipeline used."""

    @staticmethod
    def _handle(method: str, params: dict[str, Any], api_key: str) -> dict[str, Any]:
        from mcp_server.protocol_handler import ProtocolHandler
        from mcp_server.tool_registry import ToolRegistry

        handler = ProtocolHandler(tool_registry=ToolRegistry())
        frame = {"jsonrpc": "2.0", "method": method, "id": 7, "params": params}
        return handler.handle_http_request(
            body=json.dumps(frame).encode(), headers={"HTTP_X_API_KEY": api_key}
        )

    def test_parameter_defect_surfaces_as_invalid_params(self, fenced_key: str) -> None:
        response = self._handle(
            "suggestion.accept", {"suggestion_id": str(uuid4())}, fenced_key
        )

        assert response["error"]["code"] == -32602  # Invalid params
        assert SCOPE_MESSAGE_FRAGMENT not in response["error"]["message"]

    def test_foreign_workspace_denial_surfaces_as_permission_denied(
        self, fenced_key: str
    ) -> None:
        response = self._handle(
            "requirement.suggest_level", {"id": str(uuid4())}, fenced_key
        )

        assert response["error"]["code"] == -32001  # Permission denied
        assert SCOPE_MESSAGE_FRAGMENT in response["error"]["message"]


# ---------------------------------------------------------------------------
# 5. Unfenced key path unchanged
# ---------------------------------------------------------------------------


class TestUnfencedKeyUnchanged:
    def test_unfenced_key_still_uses_the_new_requirement_mapping(
        self,
        e2e_api_key_member: str,
        e2e_userrole_member,
        home_requirement: Requirement,
    ) -> None:
        """No fence: the added ``_TOOL_TARGETS`` entries change nothing for it.

        Exercises the new ``requirement.acceptance_criteria.set`` mapping end to
        end with a real service call: object-derived resolution, workspace-scoped
        roles (Editor in A), handler executes.
        """
        result = _dispatch(
            "requirement.acceptance_criteria.set",
            {
                "id": str(home_requirement.id),
                "criteria": [{"text": "W13b criterion", "fulfilled": False}],
            },
            e2e_api_key_member,
        )

        assert result.success is True, result.message
        assert result.data["total"] == 1

    def test_unfenced_key_wrong_param_keeps_the_handler_validation(
        self,
        e2e_api_key_member: str,
        e2e_userrole_member,
        e2e_workspace: Workspace,
    ) -> None:
        """No fence: the tool group's own unknown-parameter error is unchanged."""
        suggestion = _make_suggestion(e2e_workspace)

        result = _dispatch(
            "suggestion.accept",
            {"suggestion_id": str(suggestion.id)},
            e2e_api_key_member,
        )

        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"
        assert "suggestion_id" in result.message
        assert SCOPE_MESSAGE_FRAGMENT not in result.message
        suggestion.refresh_from_db()
        assert suggestion.status == "open"


# ---------------------------------------------------------------------------
# 6. Security review (HIGH): the undeclared-workspace_id shortcut
# ---------------------------------------------------------------------------


class TestExplicitWorkspaceCannotBypassFencedTarget:
    """A caller-supplied ``workspace_id`` must not bypass the fence.

    The dispatch gate used to short-circuit to the caller-supplied workspace
    when that param was present and never resolve the object's real workspace
    (``_scoped_gate_context`` Case 1). Since #1376 the dispatcher drops an
    undeclared ``workspace_id`` before the gate, so the requirement's own
    workspace drives the fence: the call is denied before the handler, with no
    domain work and no existence oracle. The handler-side
    ``reject_unknown_params`` guards remain as defense in depth for direct
    calls that bypass dispatch.
    """

    @pytest.mark.parametrize(
        "tool_name",
        [
            "requirement.suggest_level",
            "requirement.acceptance_criteria.set",
            "requirement.acceptance_criteria.check",
        ],
    )
    def test_explicit_workspace_cannot_bypass_fenced_requirement_target(
        self,
        tool_name: str,
        fenced_key: str,
        e2e_workspace: Workspace,
        foreign_workspace: Workspace,
        foreign_requirement: Requirement,
    ) -> None:
        before = foreign_requirement.acceptance_criteria_items
        params: dict[str, Any] = {
            "id": str(foreign_requirement.id),
            "workspace_id": str(e2e_workspace.id),
        }
        if tool_name == "requirement.acceptance_criteria.set":
            params["criteria"] = [{"text": "bypass", "fulfilled": False}]
        elif tool_name == "requirement.acceptance_criteria.check":
            params["index"] = 0

        with patch(
            "application.requirement_level_service.RequirementLevelService.propose_level"
        ) as suggest_handler, patch(
            "application.requirement_service.RequirementService.set_acceptance_criteria"
        ) as set_handler, patch(
            "application.requirement_service.RequirementService.update_acceptance_criterion"
        ) as check_handler:
            result = _dispatch(tool_name, params, fenced_key)

        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED"
        assert SCOPE_MESSAGE_FRAGMENT in result.message
        # No domain work: the undecided foreign object stays untouched.
        suggest_handler.assert_not_called()
        set_handler.assert_not_called()
        check_handler.assert_not_called()
        foreign_requirement.refresh_from_db()
        assert foreign_requirement.acceptance_criteria_items == before
        assert (
            Suggestion.unscoped.filter(
                tenant=foreign_requirement.tenant,
                workspace=foreign_workspace,
                kind="requirement_level",
            ).count()
            == 0
        )

    def test_explicit_workspace_with_nonexistent_id_is_no_existence_oracle(
        self,
        fenced_key: str,
        e2e_workspace: Workspace,
    ) -> None:
        """A nonexistent id and a foreign one must yield the same denial.

        Since #1376 the undeclared ``workspace_id`` is dropped, so neither id
        resolves a target inside the fence and both take the fail-closed
        workspace-scope branch — the parameter can no longer produce a
        NOT_FOUND for one and a mutation for the other.
        """
        result = _dispatch(
            "requirement.suggest_level",
            {"workspace_id": str(e2e_workspace.id), "id": str(uuid4())},
            fenced_key,
        )

        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED"
        assert SCOPE_MESSAGE_FRAGMENT in result.message


# ---------------------------------------------------------------------------
# 7. Security review (advisory): every target candidate is inspected
# ---------------------------------------------------------------------------


class TestTargetParamErrorDiagnostics:
    """Unit contract of ``mcp_server.workspace_scope.target_param_error``."""

    def test_malformed_candidate_wins_over_well_formed_one(self) -> None:
        from mcp_server.workspace_scope import target_param_error

        msg = target_param_error(
            "test.link", {"test_id": "not-a-uuid", "req_id": str(uuid4())}
        )

        assert msg is not None
        assert "'test_id'" in msg
        assert SCOPE_MESSAGE_FRAGMENT not in msg

    def test_silent_when_every_supplied_id_is_well_formed(self) -> None:
        from mcp_server.workspace_scope import target_param_error

        assert target_param_error("test.link", {"req_id": str(uuid4())}) is None

    def test_missing_when_no_candidate_was_supplied(self) -> None:
        from mcp_server.workspace_scope import target_param_error

        msg = target_param_error("test.link", {})

        assert msg is not None
        assert "'test_id'" in msg
        assert "'req_id'" in msg

    def test_malformed_multi_target_param_surfaces_through_dispatch(
        self, fenced_key: str
    ) -> None:
        """The advisory case end to end: scope text must not mask the defect."""
        result = _dispatch(
            "test.link",
            {"test_id": "not-a-uuid", "req_id": str(uuid4())},
            fenced_key,
        )

        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"
        assert "'test_id'" in result.message
        assert SCOPE_MESSAGE_FRAGMENT not in result.message
