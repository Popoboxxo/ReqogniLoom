"""Workspace scoping of the MCP dispatch RBAC gate.

Regression tests for Systemaudit 2026-08-29
(``docs/SYSTEMAUDIT_2026-08-29_GESAMTTEST_MCP.md`` §6.5):

    "requirement.query with workspace_id = a foreign workspace B (same tenant,
    NO role assignment for the test user there) returns 200 OK with the real
    requirement data from workspace B."

and for the mirror-image write hole that mapping the surface turned up: 71 of
106 write tools take no ``workspace_id`` at all, so their RBAC gate ran against
the caller's tenant-wide role union — an Editor in workspace A could
``requirement.update`` an object living in workspace B.

The tests drive the real :class:`~mcp_server.tool_registry.ToolRegistry`
against real database rows on purpose. A mocked ``AuthorizationService``
returns a truthy ``MagicMock`` from ``decide_access``, which makes *every* gate
pass and would have kept this file green against the unfixed code.

Since security finding #4 (``.tmp/security-audit-rest-mcp-2026-11-25.md``) the
write side is **fail-closed** as well: a write tool whose target workspace
cannot be resolved is denied instead of being gated against the tenant-wide role
union. The read side is deliberately unchanged — an unknown id still answers
NOT_FOUND there.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from django.utils import timezone

from application.models import Comment
from audit.models import AuditEntry
from auth_tenancy.models import UserRole
from auth_tenancy.services.authentication import AuthenticationService
from mcp_server.tool_registry import ToolRegistry
from mcp_server.workspace_scope import (
    TENANT_SCOPED_READ_TOOLS,
    TENANT_SCOPED_WRITE_TOOLS,
    resolve_target_workspace_id,
    target_param_error,
)
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Artifact, Requirement, Tenant, User, Workspace
from presets.models import WorkspacePresetConfig

# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------


def _make_workspace(tenant: Tenant, name: str, preset: dict[str, Any]) -> Workspace:
    """Create an extended-preset workspace in *tenant*."""
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
    """Create a Requirement (plus its backing Artifact) in *workspace*."""
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
            description="seeded by test_mcp_workspace_scope",
        )
    finally:
        clear_request_tenant()


def _make_comment(requirement: Requirement, author: User, text: str) -> Comment:
    return Comment.unscoped.create(
        tenant=requirement.tenant,
        artifact=requirement.artifact,
        author=author,
        text=text,
    )


def _comment_audits(comment_id: UUID) -> int:
    return AuditEntry.unscoped.filter(
        entity_type="Comment", entity_id=comment_id
    ).count()


def _make_suggestion(workspace: Workspace):
    """Create one ``open`` trace_link Suggestion in *workspace* (B-01 setup)."""
    from persistence.models import Suggestion

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


@pytest.fixture
def foreign_workspace(
    e2e_tenant: Tenant, e2e_preset: dict[str, Any]
) -> Workspace:
    """Workspace B — same tenant, no role assignment for any e2e user."""
    return _make_workspace(e2e_tenant, "Foreign Workspace B", e2e_preset)


@pytest.fixture
def foreign_requirement(foreign_workspace: Workspace) -> Requirement:
    """A requirement that only exists in workspace B."""
    return _make_requirement(foreign_workspace, "Secret req in workspace B")


@pytest.fixture
def home_requirement(
    e2e_workspace: Workspace, e2e_userrole_member: UserRole
) -> Requirement:
    """A requirement in workspace A, where the member holds Editor."""
    return _make_requirement(e2e_workspace, "Req in workspace A")


def _dispatch(tool_name: str, params: dict[str, Any], api_key: str):
    """Run one dispatch through a fully real (unmocked) ToolRegistry."""
    return ToolRegistry().dispatch_request(
        tool_name=tool_name, params=params, api_key=api_key
    )


# ---------------------------------------------------------------------------
# READ path — the finding itself
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestReadToolsAreWorkspaceScoped:
    """A read tool must not serve a workspace the caller holds no role in."""

    def test_query_against_foreign_workspace_is_denied(
        self,
        e2e_userrole_viewer: UserRole,
        e2e_api_key_viewer: str,
        foreign_workspace: Workspace,
        foreign_requirement: Requirement,
    ) -> None:
        """§6.5 verbatim: viewer in A, ``requirement.query`` against B."""
        result = _dispatch(
            "requirement.query",
            {"workspace_id": str(foreign_workspace.id)},
            e2e_api_key_viewer,
        )

        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED"
        # Fail-closed, not "silently empty": the caller must be told, and the
        # foreign title must not appear anywhere in the envelope.
        assert foreign_requirement.title not in str(result.data or "")

    def test_query_against_own_workspace_still_works(
        self,
        e2e_userrole_viewer: UserRole,
        e2e_api_key_viewer: str,
        e2e_workspace: Workspace,
    ) -> None:
        """The gate must not lock a Viewer out of their own workspace."""
        result = _dispatch(
            "requirement.query",
            {"workspace_id": str(e2e_workspace.id)},
            e2e_api_key_viewer,
        )

        assert result.success is True, result.message
        assert "requirements" in (result.data or {})

    def test_detail_read_by_id_in_foreign_workspace_is_denied(
        self,
        e2e_userrole_viewer: UserRole,
        e2e_api_key_viewer: str,
        foreign_requirement: Requirement,
    ) -> None:
        """``requirement.get`` names no workspace — it must still be scoped.

        Without the object-level resolution this is the trivial bypass of the
        ``workspace_id``-based gate: omit the parameter, pass the id.
        """
        result = _dispatch(
            "requirement.get", {"id": str(foreign_requirement.id)}, e2e_api_key_viewer
        )

        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED"

    def test_detail_read_by_id_in_own_workspace_still_works(
        self,
        e2e_api_key_member: str,
        home_requirement: Requirement,
    ) -> None:
        result = _dispatch(
            "requirement.get", {"id": str(home_requirement.id)}, e2e_api_key_member
        )

        assert result.success is True, result.message
        assert result.data["requirement"]["title"] == home_requirement.title

    def test_unknown_id_is_not_denied_but_reported_as_not_found(
        self,
        e2e_userrole_viewer: UserRole,
        e2e_api_key_viewer: str,
    ) -> None:
        """Resolution is fail-soft: an unresolvable id keeps the old path.

        Turning "no such object" into PERMISSION_DENIED would leak the
        existence of ids and would break every not-found test in the suite.
        """
        result = _dispatch("requirement.get", {"id": str(uuid4())}, e2e_api_key_viewer)

        assert result.success is False
        assert result.error_code == "NOT_FOUND"


# ---------------------------------------------------------------------------
# WRITE path — the mirror-image hole
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestWriteToolsWithoutWorkspaceParamAreScoped:
    """An Editor in A must not mutate an object living in B."""

    def test_update_of_foreign_object_is_denied(
        self,
        e2e_userrole_member: UserRole,
        e2e_api_key_member: str,
        foreign_requirement: Requirement,
    ) -> None:
        result = _dispatch(
            "requirement.update",
            {
                "id": str(foreign_requirement.id),
                "data": {"title": "hijacked", "change_reason": "test"},
            },
            e2e_api_key_member,
        )

        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED"

        foreign_requirement.refresh_from_db()
        assert foreign_requirement.title == "Secret req in workspace B"

    def test_update_of_own_object_still_works(
        self,
        e2e_api_key_member: str,
        home_requirement: Requirement,
    ) -> None:
        result = _dispatch(
            "requirement.update",
            {
                "id": str(home_requirement.id),
                "data": {"title": "renamed by owner", "change_reason": "test"},
            },
            e2e_api_key_member,
        )

        assert result.success is True, result.message
        home_requirement.refresh_from_db()
        assert home_requirement.title == "renamed by owner"


# ---------------------------------------------------------------------------
# WRITE path — fail-closed when no workspace can be resolved (finding #4)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestUnscopedWritesAreDenied:
    """Finding #4: a write tool with no resolvable target is denied.

    ``_TOOL_TARGETS`` was the only mapping from a write call to its owning
    workspace, and a missing/unresolvable entry fell back to the caller's
    tenant-wide role union. These tests pin the new contract on the real,
    unmocked gate: the denial happens before the handler, and it never becomes
    an existence oracle — no id and no value is ever echoed.

    The *class* of the answer depends on what is wrong (review finding
    2026-11-25, MAJOR): a malformed call (missing/typo'd/unparseable target id)
    gets ``VALIDATION_ERROR`` naming the expected parameter, because that is a
    request-shape defect the caller can fix; a well-formed call that resolves to
    no row keeps the fail-closed ``PERMISSION_DENIED`` scope text, because a
    nonexistent object must stay indistinguishable from a foreign one.
    """

    #: The wording ``ToolRegistry._unscoped_write_denial`` answers with. Asserted
    #: by substring so a future rewording does not have to touch five tests.
    _MESSAGE = "could not be scoped to a workspace"

    def test_write_with_no_target_param_is_denied_before_the_handler(
        self,
        e2e_userrole_member: UserRole,
        e2e_api_key_member: str,
    ) -> None:
        """No ``id`` and no ``workspace_id``: the *call* is what is wrong.

        Review finding (2026-11-25, MAJOR): a missing target parameter used to
        be answered with the generic workspace-scope text, which sent the caller
        debugging its API key. It is now the validation class naming the
        parameter. Fail-closed is unchanged: the handler is never called.
        """
        with patch(
            "application.requirement_service.RequirementService.get_requirement"
        ) as handler:
            result = _dispatch(
                "requirement.update",
                {"data": {"title": "no target", "change_reason": "test"}},
                e2e_api_key_member,
            )

        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"
        assert "'id'" in (result.message or "")
        assert self._MESSAGE not in (result.message or "")
        handler.assert_not_called()

    def test_malformed_target_id_is_a_validation_error_without_echoing_it(
        self,
        e2e_userrole_member: UserRole,
        e2e_api_key_member: str,
    ) -> None:
        """An unparseable id is a parameter defect, not a scope problem.

        Both transports now answer the same class as the fenced path
        (``TestFencedWriteDiagnosis``): the diagnosis names the parameter and
        never echoes the malformed value. The handler still never runs.
        """
        with patch(
            "application.requirement_service.RequirementService.get_requirement"
        ) as handler:
            result = _dispatch(
                "requirement.update",
                {"id": "not-a-uuid", "data": {"change_reason": "test"}},
                e2e_api_key_member,
            )

        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"
        assert "'id'" in (result.message or "")
        assert "not-a-uuid" not in (result.message or "")
        assert self._MESSAGE not in (result.message or "")
        handler.assert_not_called()

    def test_unknown_or_deleted_target_id_is_denied_without_existence_leak(
        self,
        e2e_userrole_member: UserRole,
        e2e_api_key_member: str,
    ) -> None:
        """A well-formed id with no row is denied, and the id is not echoed.

        This is the deliberate write/read asymmetry: ``requirement.get`` keeps
        answering NOT_FOUND for an unknown id (see
        ``test_unknown_id_is_not_denied_but_reported_as_not_found``), because a
        read cannot mutate anything and hiding "no such row" would break every
        not-found path. A write must not have a fallback role set, so an
        unresolvable target is denied instead — and the message must look
        exactly like the one for a foreign id, or the denial becomes the
        existence oracle it is meant to avoid. It must also stay
        ``PERMISSION_DENIED``: the parameter diagnosis is silent here (the id is
        well-formed and was really looked up), so a nonexistent object cannot be
        told apart from a fenced one by the error class.
        """
        missing = str(uuid4())

        with patch(
            "application.requirement_service.RequirementService.get_requirement"
        ) as handler:
            result = _dispatch(
                "requirement.update",
                {"id": missing, "data": {"change_reason": "test"}},
                e2e_api_key_member,
            )

        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED"
        assert self._MESSAGE in (result.message or "")
        assert missing not in (result.message or "")
        handler.assert_not_called()

    def test_foreign_target_is_denied_and_left_unchanged(
        self,
        e2e_userrole_member: UserRole,
        e2e_api_key_member: str,
        foreign_requirement: Requirement,
    ) -> None:
        """A foreign id resolves to workspace B, so the RBAC matrix denies it.

        Unlike an unknown id (which the scope gate denies), this id *does*
        resolve — the answer therefore comes from the role check against
        workspace B. What matters either way: the row is untouched, and the
        message names neither the object nor its workspace.
        """
        result = _dispatch(
            "requirement.update",
            {"id": str(foreign_requirement.id), "data": {"change_reason": "test"}},
            e2e_api_key_member,
        )

        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED"
        assert str(foreign_requirement.id) not in (result.message or "")
        assert str(foreign_requirement.workspace_id) not in (result.message or "")
        assert "hijacked" not in (result.message or "")

        foreign_requirement.refresh_from_db()
        assert foreign_requirement.title == "Secret req in workspace B"

    @pytest.mark.parametrize("tool_name", ["artifact.bulk_transition"])
    def test_batch_write_with_no_resolvable_id_is_denied(
        self,
        tool_name: str,
        e2e_userrole_member: UserRole,
        e2e_api_key_member: str,
    ) -> None:
        """A batch write whose ids all resolve to nothing has no workspace.

        ``artifact.bulk_transition`` names its targets as a list; the registry
        probes every id, so an all-unknown batch resolves nothing and is
        denied. A mixed batch still resolves (its reachable rows keep the
        partial-success contract) — see ``test_bulk_transition_tool.py``.
        """
        result = _dispatch(
            tool_name,
            {
                "item_type": "Requirement",
                "ids": [str(uuid4()), str(uuid4())],
                "to_state": "In Review",
                "change_reason": "test",
            },
            e2e_api_key_member,
        )

        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED"
        assert self._MESSAGE in (result.message or "")


@pytest.mark.django_db
class TestFencedWriteDiagnosis:
    """The fenced path keeps its #1357 parameter diagnosis.

    A workspace-fenced key is denied by the fence before the write-scope gate
    runs, so its answer is the one #1357 introduced: a parameter-level defect
    (missing or malformed target id) is a ``VALIDATION_ERROR`` naming the
    parameter, not the generic scope text. The unfenced path answers the same
    class since the 2026-11-25 review (see ``TestUnscopedWritesAreDenied``).
    """

    def test_fenced_key_with_a_malformed_target_gets_the_param_diagnosis(
        self,
        e2e_tenant: Tenant,
        e2e_workspace: Workspace,
        e2e_userrole_member: UserRole,
        e2e_user_member: User,
    ) -> None:
        key = AuthenticationService().create_api_key(
            user_id=e2e_user_member.id,
            tenant_id=e2e_tenant.id,
            name="fenced-malformed-target",
            principal_type="agent",
            agent_label="audit-agent",
            scope="write",
            workspace_ids=[str(e2e_workspace.id)],
            expires_at=timezone.now() + timedelta(days=1),
        )

        result = _dispatch(
            "requirement.update",
            {"id": "not-a-uuid", "data": {"change_reason": "test"}},
            key.plaintext,
        )

        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"
        assert "'id'" in (result.message or "")

    def test_fenced_key_with_no_target_gets_the_param_diagnosis(
        self,
        e2e_tenant: Tenant,
        e2e_workspace: Workspace,
        e2e_userrole_member: UserRole,
        e2e_user_member: User,
    ) -> None:
        key = AuthenticationService().create_api_key(
            user_id=e2e_user_member.id,
            tenant_id=e2e_tenant.id,
            name="fenced-missing-target",
            principal_type="agent",
            agent_label="audit-agent",
            scope="write",
            workspace_ids=[str(e2e_workspace.id)],
            expires_at=timezone.now() + timedelta(days=1),
        )

        result = _dispatch(
            "requirement.update",
            {"data": {"change_reason": "test"}},
            key.plaintext,
        )

        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"
        assert "'id'" in (result.message or "")


@pytest.mark.django_db
def test_comment_resolve_uses_the_comments_workspace(
    e2e_userrole_member: UserRole,
    e2e_api_key_member: str,
    e2e_user_member: User,
    home_requirement: Requirement,
):
    comment = _make_comment(home_requirement, e2e_user_member, "own comment")

    result = _dispatch("comment.resolve", {"id": str(comment.id)}, e2e_api_key_member)

    assert result.success is True, result.message
    comment.refresh_from_db()
    assert comment.resolved is True
    assert _comment_audits(comment.id) == 1


@pytest.mark.django_db
def test_comment_resolve_rejects_cross_workspace_before_mutation(
    e2e_userrole_member: UserRole,
    e2e_api_key_member: str,
    e2e_user_member: User,
    foreign_requirement: Requirement,
):
    comment = _make_comment(foreign_requirement, e2e_user_member, "foreign comment")
    audits_before = _comment_audits(comment.id)

    result = _dispatch("comment.resolve", {"id": str(comment.id)}, e2e_api_key_member)

    assert result.success is False
    assert result.error_code == "PERMISSION_DENIED"
    comment.refresh_from_db()
    assert comment.resolved is False
    assert _comment_audits(comment.id) == audits_before


@pytest.mark.django_db
def test_fenced_agent_key_rejects_workspace_b_before_comment_handler(
    e2e_tenant: Tenant,
    e2e_workspace: Workspace,
    e2e_userrole_member: UserRole,
    e2e_user_member: User,
    foreign_requirement: Requirement,
):
    comment = _make_comment(foreign_requirement, e2e_user_member, "fenced agent")
    key = AuthenticationService().create_api_key(
        user_id=e2e_user_member.id,
        tenant_id=e2e_tenant.id,
        name="fenced-agent-key",
        principal_type="agent",
        agent_label="audit-agent",
        scope="write",
        workspace_ids=[str(e2e_workspace.id)],
        expires_at=timezone.now() + timedelta(days=1),
    )
    audits_before = _comment_audits(comment.id)

    with patch("mcp_server.tools.comment.CommentService.resolve_comment") as handler:
        result = _dispatch("comment.resolve", {"id": str(comment.id)}, key.plaintext)

    assert result.success is False
    assert result.error_code == "PERMISSION_DENIED"
    handler.assert_not_called()
    comment.refresh_from_db()
    assert comment.resolved is False
    assert _comment_audits(comment.id) == audits_before


@pytest.mark.django_db
def test_explicit_workspace_cannot_bypass_fenced_comment_target(
    e2e_tenant: Tenant,
    e2e_workspace: Workspace,
    e2e_userrole_member: UserRole,
    e2e_user_member: User,
    foreign_requirement: Requirement,
):
    comment = _make_comment(foreign_requirement, e2e_user_member, "explicit scope")
    key = AuthenticationService().create_api_key(
        user_id=e2e_user_member.id,
        tenant_id=e2e_tenant.id,
        name="explicit-scope-agent-key",
        principal_type="agent",
        scope="write",
        workspace_ids=[str(e2e_workspace.id)],
        expires_at=timezone.now() + timedelta(days=1),
    )
    audits_before = _comment_audits(comment.id)

    with patch("mcp_server.tools.comment.CommentService.resolve_comment") as handler:
        result = _dispatch(
            "comment.resolve",
            {"id": str(comment.id), "workspace_id": str(e2e_workspace.id)},
            key.plaintext,
        )

    # #1376: the undeclared workspace_id no longer activates the Case-1
    # shortcut; the gate resolves the comment's own workspace and the fence
    # denies before the handler (was VALIDATION_ERROR via the W13b guard).
    assert result.success is False
    assert result.error_code == "PERMISSION_DENIED"
    handler.assert_not_called()
    comment.refresh_from_db()
    assert comment.resolved is False
    assert _comment_audits(comment.id) == audits_before


@pytest.mark.django_db
@pytest.mark.parametrize("tool_name", ["comment.create", "comment.list"])
def test_comment_create_and_list_reject_explicit_workspace_bypass(
    e2e_tenant: Tenant,
    e2e_workspace: Workspace,
    e2e_userrole_member: UserRole,
    e2e_user_member: User,
    foreign_requirement: Requirement,
    tool_name: str,
):
    key = AuthenticationService().create_api_key(
        user_id=e2e_user_member.id,
        tenant_id=e2e_tenant.id,
        name=f"explicit-{tool_name}",
        principal_type="agent",
        agent_label="audit-agent",
        scope="write",
        workspace_ids=[str(e2e_workspace.id)],
        expires_at=timezone.now() + timedelta(days=1),
    )
    params = {
        "artifact_id": str(foreign_requirement.artifact_id),
        "workspace_id": str(e2e_workspace.id),
    }
    method_name = (
        "create_comment" if tool_name == "comment.create" else "list_for_artifact"
    )
    if tool_name == "comment.create":
        params["text"] = "blocked"

    with patch(f"mcp_server.tools.comment.CommentService.{method_name}") as handler:
        result = _dispatch(tool_name, params, key.plaintext)

    # #1376: undeclared workspace_id is stripped, the target artifact's own
    # workspace drives the fence, and the handler is never reached.
    assert result.success is False
    assert result.error_code == "PERMISSION_DENIED"
    handler.assert_not_called()


@pytest.mark.django_db
def test_comment_resolve_rejects_suspended_target_role_without_mutation(
    e2e_userrole_member: UserRole,
    e2e_api_key_member: str,
    e2e_user_member: User,
    home_requirement: Requirement,
):
    e2e_userrole_member.suspended_at = timezone.now()
    e2e_userrole_member.save(update_fields=["suspended_at"])
    comment = _make_comment(home_requirement, e2e_user_member, "suspended role")
    audits_before = _comment_audits(comment.id)

    result = _dispatch("comment.resolve", {"id": str(comment.id)}, e2e_api_key_member)

    assert result.success is False
    assert result.error_code == "PERMISSION_DENIED"
    comment.refresh_from_db()
    assert comment.resolved is False
    assert _comment_audits(comment.id) == audits_before


@pytest.mark.django_db
def test_comment_resolve_rejects_removed_target_role_without_mutation(
    e2e_userrole_member: UserRole,
    e2e_api_key_member: str,
    e2e_user_member: User,
    home_requirement: Requirement,
):
    e2e_userrole_member.delete()
    comment = _make_comment(home_requirement, e2e_user_member, "removed role")
    audits_before = _comment_audits(comment.id)

    result = _dispatch("comment.resolve", {"id": str(comment.id)}, e2e_api_key_member)

    assert result.success is False
    assert result.error_code == "PERMISSION_DENIED"
    comment.refresh_from_db()
    assert comment.resolved is False
    assert _comment_audits(comment.id) == audits_before


@pytest.mark.django_db
def test_comment_resolve_rejects_inactive_user_without_mutation(
    e2e_user_member: User,
    e2e_api_key_member: str,
    home_requirement: Requirement,
):
    comment = _make_comment(home_requirement, e2e_user_member, "inactive user")
    audits_before = _comment_audits(comment.id)
    e2e_user_member.is_active = False
    e2e_user_member.save(update_fields=["is_active"])

    result = _dispatch("comment.resolve", {"id": str(comment.id)}, e2e_api_key_member)

    assert result.success is False
    assert result.error_code == "AUTH_FAILED"
    comment.refresh_from_db()
    assert comment.resolved is False
    assert _comment_audits(comment.id) == audits_before


@pytest.mark.django_db
def test_fenced_key_fails_closed_for_cross_tenant_comment_before_handler(
    e2e_tenant: Tenant,
    e2e_workspace: Workspace,
    e2e_user_member: User,
):
    foreign_tenant = Tenant.objects.create(
        name="foreign-comment-tenant", is_active=True
    )
    set_request_tenant(foreign_tenant.id)
    try:
        foreign_workspace = Workspace.objects.create(
            tenant=foreign_tenant, name="foreign-comment-workspace"
        )
        foreign_user = User.objects.create(
            username="foreign-comment-user",
            email="foreign-comment@example.com",
            tenant=foreign_tenant,
            is_active=True,
        )
        foreign_artifact = Artifact.objects.create(
            tenant=foreign_tenant,
            workspace=foreign_workspace,
            artifact_type="Requirement",
        )
        foreign_comment = Comment.unscoped.create(
            tenant=foreign_tenant,
            artifact=foreign_artifact,
            author=foreign_user,
            text="cross tenant",
        )
    finally:
        clear_request_tenant()

    key = AuthenticationService().create_api_key(
        user_id=e2e_user_member.id,
        tenant_id=e2e_tenant.id,
        name="fenced-comment-key",
        scope="write",
        workspace_ids=[str(e2e_workspace.id)],
        expires_at=timezone.now() + timedelta(days=1),
    )
    audits_before = _comment_audits(foreign_comment.id)

    with patch("mcp_server.tools.comment.CommentService.resolve_comment") as handler:
        result = _dispatch(
            "comment.resolve", {"id": str(foreign_comment.id)}, key.plaintext
        )

    assert result.success is False
    assert result.error_code == "PERMISSION_DENIED"
    handler.assert_not_called()
    foreign_comment.refresh_from_db()
    assert foreign_comment.resolved is False
    assert _comment_audits(foreign_comment.id) == audits_before


@pytest.mark.django_db
class TestOptionalWorkspaceIdReadsAreScoped:
    """Declaring ``workspace_id`` is not the same as enforcing it.

    These two tools accept the parameter and used to fall through to a
    tenant-wide read when it was omitted. The dispatcher gate cannot help
    there: no workspace is named and there is no target object to resolve, so
    the fix has to live in the handler.
    """

    def test_artifact_search_without_workspace_id_uses_accessible_scope(self) -> None:
        """The handler must ask for ``scope="tenant"``, not the unscoped path.

        Asserted at the seam rather than through the tsvector index: the point
        of the fix is *which scope is requested*, and pinning that is immune to
        whether the FTS column happens to be populated for a freshly inserted
        row.
        """
        from unittest.mock import MagicMock

        from auth_tenancy.context import AuthContext, AuthMethod
        from mcp_server.tools.cross_cutting import CrossCuttingToolGroup

        search_service = MagicMock()
        search_service.search.return_value = MagicMock(
            results=[], total_count=0, page=1, limit=20, query=""
        )
        group = CrossCuttingToolGroup(search_service=search_service)
        ctx = AuthContext(
            user_id=uuid4(),
            tenant_id=uuid4(),
            active_roles=("viewer",),
            auth_method=AuthMethod.API_KEY,
        )

        group._handle_artifact_search(
            params={"query": "anything"}, auth_context=ctx, api_key="reqlo_x"
        )
        assert search_service.search.call_args.kwargs["scope"] == "tenant"

        # With an explicit workspace the dispatcher has already gated
        # membership, so the single-workspace path must stay untouched.
        workspace_id = uuid4()
        group._handle_artifact_search(
            params={"query": "anything", "workspace_id": str(workspace_id)},
            auth_context=ctx,
            api_key="reqlo_x",
        )
        kwargs = search_service.search.call_args.kwargs
        assert kwargs["scope"] == "workspace"
        assert kwargs["workspace_id"] == workspace_id

    def test_prompt_template_list_hides_foreign_workspace_templates(
        self,
        e2e_userrole_viewer: UserRole,
        e2e_api_key_viewer: str,
        e2e_workspace: Workspace,
        foreign_workspace: Workspace,
    ) -> None:
        """Tenant-wide + own-workspace rows only, never another workspace's."""
        from persistence.models import PromptTemplate

        set_request_tenant(e2e_tenant_id := e2e_workspace.tenant_id)
        try:
            PromptTemplate.objects.create(
                tenant_id=e2e_tenant_id,
                workspace_id=None,
                name="tenant_wide_slot",
                content="tenant default",
                version=1,
                is_active=True,
            )
            PromptTemplate.objects.create(
                tenant_id=e2e_tenant_id,
                workspace_id=e2e_workspace.id,
                name="own_slot",
                content="own override",
                version=1,
                is_active=True,
            )
            PromptTemplate.objects.create(
                tenant_id=e2e_tenant_id,
                workspace_id=foreign_workspace.id,
                name="foreign_slot",
                content="FOREIGN SECRET PROMPT",
                version=1,
                is_active=True,
            )
        finally:
            clear_request_tenant()

        result = _dispatch("prompt_template.list", {}, e2e_api_key_viewer)

        assert result.success is True, result.message
        names = {t["name"] for t in result.data["templates"]}
        assert "tenant_wide_slot" in names
        assert "own_slot" in names
        assert "foreign_slot" not in names
        assert "FOREIGN SECRET PROMPT" not in str(result.data)


# ---------------------------------------------------------------------------
# Resolver unit tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestResolveTargetWorkspaceId:
    def test_resolves_requirement_id_to_its_workspace(
        self, foreign_workspace: Workspace, foreign_requirement: Requirement
    ) -> None:
        set_request_tenant(foreign_workspace.tenant_id)
        try:
            resolved = resolve_target_workspace_id(
                "requirement.get", {"id": str(foreign_requirement.id)}
            )
        finally:
            clear_request_tenant()
        assert resolved == str(foreign_workspace.id)

    def test_resolves_comment_id_to_artifact_workspace(
        self, e2e_user_member: User, home_requirement: Requirement
    ) -> None:
        comment = _make_comment(home_requirement, e2e_user_member, "resolver comment")
        set_request_tenant(home_requirement.tenant_id)
        try:
            resolved = resolve_target_workspace_id(
                "comment.resolve", {"id": str(comment.id)}
            )
        finally:
            clear_request_tenant()
        assert resolved == str(home_requirement.workspace_id)

    def test_unregistered_tool_resolves_to_none(self) -> None:
        assert resolve_target_workspace_id("workspace.list", {"id": str(uuid4())}) is None

    def test_malformed_uuid_resolves_to_none(self) -> None:
        assert resolve_target_workspace_id("requirement.get", {"id": "not-a-uuid"}) is None

    def test_missing_param_resolves_to_none(self) -> None:
        assert resolve_target_workspace_id("requirement.get", {}) is None

    def test_first_resolvable_candidate_wins(
        self, foreign_workspace: Workspace, foreign_requirement: Requirement
    ) -> None:
        """``context.change_impact`` probes four entity types for one param."""
        set_request_tenant(foreign_workspace.tenant_id)
        try:
            resolved = resolve_target_workspace_id(
                "context.change_impact",
                {"entity_id": str(foreign_requirement.id), "entity_type": "Requirement"},
            )
        finally:
            clear_request_tenant()
        assert resolved == str(foreign_workspace.id)

    def test_batch_param_resolves_from_the_first_reachable_id(
        self, foreign_workspace: Workspace, foreign_requirement: Requirement
    ) -> None:
        """``artifact.bulk_transition`` names a list; probe every element.

        An unresolvable element must not stop the scan — a batch with one
        deleted row still names the workspace of its reachable rows.
        """
        set_request_tenant(foreign_workspace.tenant_id)
        try:
            resolved = resolve_target_workspace_id(
                "artifact.bulk_transition",
                {"ids": [str(uuid4()), str(foreign_requirement.artifact_id)]},
            )
        finally:
            clear_request_tenant()
        assert resolved == str(foreign_workspace.id)

    def test_batch_param_with_no_reachable_id_resolves_to_none(self) -> None:
        assert (
            resolve_target_workspace_id(
                "artifact.bulk_transition", {"ids": [str(uuid4())]}
            )
            is None
        )

    def test_nested_target_path_resolves(
        self, foreign_workspace: Workspace
    ) -> None:
        """``architecture.decompose_commit`` names its root inside ``draft``."""
        from persistence.models import ArchitectureElement

        set_request_tenant(foreign_workspace.tenant_id)
        try:
            artifact = Artifact.objects.create(
                tenant=foreign_workspace.tenant,
                workspace=foreign_workspace,
                artifact_type="ArchitectureElement",
            )
            element = ArchitectureElement.objects.create(
                tenant=foreign_workspace.tenant,
                artifact=artifact,
                title="root in B",
            )
            resolved = resolve_target_workspace_id(
                "architecture.decompose_commit",
                {"draft": {"root_element_id": str(element.id)}},
            )
        finally:
            clear_request_tenant()
        assert resolved == str(foreign_workspace.id)

    def test_nested_target_path_absent_resolves_to_none(self) -> None:
        assert (
            resolve_target_workspace_id(
                "architecture.decompose_commit", {"draft": {"nodes": []}}
            )
            is None
        )


# ---------------------------------------------------------------------------
# Coverage ratchet
# ---------------------------------------------------------------------------


class TestTargetParamError:
    """Unit contract of the parameter-level diagnosis (extended by finding #4).

    The diagnosis decides the message on both write paths now: the fenced key
    hits it in ``_authorize_tool_call`` (finding #1357) and the unfenced key in
    ``_authorize_write_tool`` (review finding 2026-11-25, MAJOR). These cases pin
    that a batch list and a nested target path are understood, so a caller is
    never told its well-formed ids are "malformed".
    """

    def test_batch_ids_are_well_formed_and_keep_the_scope_text(self) -> None:
        assert (
            target_param_error(
                "artifact.bulk_transition", {"ids": [str(uuid4()), str(uuid4())]}
            )
            is None
        )

    def test_batch_ids_that_all_fail_to_parse_are_a_param_defect(self) -> None:
        message = target_param_error(
            "artifact.bulk_transition", {"ids": ["nope", "still-nope"]}
        )
        assert message is not None
        assert "'ids'" in message

    def test_one_parseable_id_in_a_batch_is_not_a_param_defect(self) -> None:
        assert (
            target_param_error(
                "artifact.bulk_transition", {"ids": ["nope", str(uuid4())]}
            )
            is None
        )

    def test_nested_target_path_is_diagnosed_by_its_top_level_param(self) -> None:
        message = target_param_error("architecture.decompose_commit", {"draft": {}})
        assert message is not None
        assert "'draft.root_element_id'" in message

    def test_nested_target_path_supplied_is_not_a_param_defect(self) -> None:
        assert (
            target_param_error(
                "architecture.decompose_commit",
                {"draft": {"root_element_id": str(uuid4())}},
            )
            is None
        )


def _live_tools() -> dict[str, dict[str, Any]]:
    """Every tool the live registry advertises, indexed by name."""
    from mcp_server.management.commands.export_tool_manifest import build_manifest

    return {tool["name"]: tool for tool in build_manifest()["tools"]}


class TestWorkspaceScopeCoverage:
    """Every read tool must be *explicitly* classified.

    A new read tool that is none of (a) ``workspace_id``-**required**,
    (b) registered in ``_TOOL_TARGETS``, (c) listed in
    ``TOOL_ENFORCED_WORKSPACE_SCOPE``, (d) listed in
    ``TENANT_SCOPED_READ_TOOLS`` would ship unscoped and silently reintroduce
    the finding. This is the ratchet that stops that; the fix for a red run is
    a registry entry or a real scoping fix, never a change to the assertion.
    """

    def test_every_read_tool_is_classified(self) -> None:
        """A *declared* ``workspace_id`` is not scoping — it must be required.

        The first cut of this ratchet skipped any tool whose schema merely
        mentioned ``workspace_id``. That let ``artifact.search`` through while
        it was still passing ``workspace_id=None`` into
        ``SearchService.search(scope="workspace")`` — documented as "the whole
        tenant with no RBAC narrowing", i.e. a live instance of the very bug
        this file exists to prevent. Requiring the parameter to be *required*
        is what makes the skip mean "the dispatcher will always have a
        workspace to gate on".
        """
        from mcp_server.workspace_scope import (
            _TOOL_TARGETS,
            TOOL_ENFORCED_WORKSPACE_SCOPE,
        )

        unclassified = []
        for name, tool in _live_tools().items():
            if tool["is_write"]:
                continue
            schema = tool.get("inputSchema") or {}
            if "workspace_id" in (schema.get("required") or []):
                continue
            if (
                name in _TOOL_TARGETS
                or name in TOOL_ENFORCED_WORKSPACE_SCOPE
                or name in TENANT_SCOPED_READ_TOOLS
            ):
                continue
            unclassified.append(name)

        assert not unclassified, (
            "Read tools with no enforced workspace scoping: "
            f"{sorted(unclassified)}. Make workspace_id required, add a target "
            "to mcp_server.workspace_scope._TOOL_TARGETS, or list the tool in "
            "TOOL_ENFORCED_WORKSPACE_SCOPE / TENANT_SCOPED_READ_TOOLS with a "
            "documented reason. Do not relax this assertion."
        )

    def test_every_write_tool_is_classified(self) -> None:
        """Every write tool must name a workspace one of four ways.

        Finding #4 (``.tmp/security-audit-rest-mcp-2026-11-25.md``): a write
        tool missing from ``_TOOL_TARGETS`` fell back to the caller's
        tenant-wide role union, so an Editor in workspace A could mutate an
        object in workspace B. The runtime gate
        (``ToolRegistry._unscoped_write_denial``) now denies such a tool; this
        ratchet is what stops a *new* tool from shipping denied-but-unusable
        instead of properly scoped.

        Deliberately stricter than the read ratchet in one direction only: an
        *optional* ``workspace_id`` does not classify a write either (the caller
        can omit it), so only a **required** one counts.
        """
        from mcp_server.tool_registry import _INSTANCE_LEVEL_TOOLS
        from mcp_server.workspace_scope import _TOOL_TARGETS

        unclassified = []
        for name, tool in _live_tools().items():
            if not tool["is_write"]:
                continue
            schema = tool.get("inputSchema") or {}
            if "workspace_id" in (schema.get("required") or []):
                continue
            if (
                name in _TOOL_TARGETS
                or name in TENANT_SCOPED_WRITE_TOOLS
                or name in _INSTANCE_LEVEL_TOOLS
            ):
                continue
            unclassified.append(name)

        assert not unclassified, (
            "Write tools that cannot be scoped to a workspace: "
            f"{sorted(unclassified)}. They are denied at dispatch — add a "
            "target to mcp_server.workspace_scope._TOOL_TARGETS, make "
            "workspace_id required, or justify the tool in "
            "TENANT_SCOPED_WRITE_TOOLS with a documented reason. Do not relax "
            "this assertion."
        )

    def test_write_classification_buckets_do_not_contradict(self) -> None:
        """One write tool, one claim — two buckets mean two answers.

        Read and write are separate namespaces: a tool may appear in
        ``_TOOL_TARGETS`` (which serves both) without that being a conflict,
        and ``TENANT_SCOPED_READ_TOOLS`` is not compared here. What must never
        happen is a tool claimed by two *write* mechanisms — ``_TOOL_TARGETS``
        says "the object decides", ``TENANT_SCOPED_WRITE_TOOLS`` says "there is
        no object", and ``_INSTANCE_LEVEL_TOOLS`` says "not even tenant-scoped".
        """
        from mcp_server.tool_registry import _INSTANCE_LEVEL_TOOLS
        from mcp_server.workspace_scope import _TOOL_TARGETS

        write_buckets = {
            "_TOOL_TARGETS": set(_TOOL_TARGETS),
            "TENANT_SCOPED_WRITE_TOOLS": set(TENANT_SCOPED_WRITE_TOOLS),
            "_INSTANCE_LEVEL_TOOLS": set(_INSTANCE_LEVEL_TOOLS),
        }
        names = sorted(write_buckets)
        for i, left in enumerate(names):
            for right in names[i + 1 :]:
                overlap = write_buckets[left] & write_buckets[right]
                assert not overlap, (
                    f"{left} and {right} both claim {sorted(overlap)} — a write "
                    "tool must be classified by exactly one mechanism"
                )

    def test_tenant_scoped_write_tools_are_real_write_tools(self) -> None:
        tools = _live_tools()
        for name in TENANT_SCOPED_WRITE_TOOLS:
            assert name in tools, f"{name} is not a live tool"
            assert tools[name]["is_write"], f"{name} is not a write tool"

    def test_every_live_write_tool_has_an_inspectable_schema(self) -> None:
        """The write gate is only fail-closed on *published* tools.

        ``_unscoped_write_denial`` skips a name whose ``inputSchema`` the
        registry cannot see — that is what keeps an unknown tool name answering
        UNKNOWN_TOOL instead of leaking a 403, and what leaves unit-test doubles
        on their pre-existing path. In production every routable tool is a
        ``BaseToolGroup`` schema, so this must hold for the whole live catalogue;
        if it ever stops holding, the gate would silently stop applying.
        """
        registry = ToolRegistry()
        registry._ensure_groups()
        uninspectable = sorted(
            name
            for name, tool in _live_tools().items()
            if tool["is_write"] and registry._published_input_schema(name) is None
        )
        assert not uninspectable, (
            "Live write tools without a published inputSchema: "
            f"{uninspectable} — the fail-closed write gate cannot classify them"
        )

    def test_classification_sets_are_disjoint(self) -> None:
        """A tool in two buckets means two contradictory claims about it."""
        from mcp_server.workspace_scope import (
            _TOOL_TARGETS,
            TOOL_ENFORCED_WORKSPACE_SCOPE,
        )

        buckets = {
            "_TOOL_TARGETS": set(_TOOL_TARGETS),
            "TOOL_ENFORCED_WORKSPACE_SCOPE": set(TOOL_ENFORCED_WORKSPACE_SCOPE),
            "TENANT_SCOPED_READ_TOOLS": set(TENANT_SCOPED_READ_TOOLS),
        }
        names = sorted(buckets)
        for i, left in enumerate(names):
            for right in names[i + 1 :]:
                overlap = buckets[left] & buckets[right]
                assert not overlap, f"{left} and {right} both claim {sorted(overlap)}"

    def test_tool_enforced_scope_tools_are_real_read_tools(self) -> None:
        from mcp_server.workspace_scope import TOOL_ENFORCED_WORKSPACE_SCOPE

        tools = _live_tools()
        for name in TOOL_ENFORCED_WORKSPACE_SCOPE:
            assert name in tools, f"{name} is not a live tool"
            assert not tools[name]["is_write"], f"{name} is a write tool"

    def test_registry_targets_reference_known_tools(self) -> None:
        """A typo'd tool name in the registry is dead weight — catch it."""
        from mcp_server.workspace_scope import _TOOL_TARGETS

        live = set(_live_tools())
        unknown = sorted(set(_TOOL_TARGETS) - live)
        assert not unknown, f"_TOOL_TARGETS names non-existent tools: {unknown}"

    def test_registry_targets_reference_declared_params(self) -> None:
        """A target param the tool never accepts can never resolve.

        A dotted target path (``draft.root_element_id``) is checked by its first
        segment: that is the top-level parameter the caller must send.
        """
        from mcp_server.workspace_scope import _TOOL_TARGETS

        tools = _live_tools()
        bad: list[tuple[str, str]] = []
        for tool_name, targets in _TOOL_TARGETS.items():
            properties = (tools[tool_name].get("inputSchema") or {}).get(
                "properties"
            ) or {}
            for param_name, _entity_key in targets:
                root_param = param_name.split(".", 1)[0]
                if root_param not in properties:
                    bad.append((tool_name, param_name))
        assert not bad, f"_TOOL_TARGETS names undeclared params: {sorted(bad)}"

    def test_every_entity_key_is_declared(self) -> None:
        from application.workspace_lookup import ENTITY_SPECS
        from mcp_server.workspace_scope import _TOOL_TARGETS

        used = {key for targets in _TOOL_TARGETS.values() for _p, key in targets}
        assert used <= set(ENTITY_SPECS), sorted(used - set(ENTITY_SPECS))

    def test_tenant_scoped_read_tools_are_real_read_tools(self) -> None:
        tools = _live_tools()
        for name in TENANT_SCOPED_READ_TOOLS:
            assert name in tools, f"{name} is not a live tool"
            assert not tools[name]["is_write"], f"{name} is a write tool"

    @pytest.mark.django_db
    def test_every_entity_spec_resolves_against_the_real_schema(
        self, e2e_tenant: Tenant
    ) -> None:
        """Every spec's model/field pair must be a valid ORM query.

        A renamed column would otherwise degrade silently to "unresolvable",
        i.e. back to the unscoped behaviour this module exists to remove —
        and, because resolution is fail-soft by design, nothing else would
        notice.
        """
        from application.workspace_lookup import ENTITY_SPECS, import_entity_model

        set_request_tenant(e2e_tenant.id)
        try:
            for key, spec in ENTITY_SPECS.items():
                model = import_entity_model(spec.model_path)
                manager = getattr(model, "unscoped", model.objects)
                # Executing the query is what validates both field paths; no
                # rows are needed for the ORM to reject an unknown column.
                assert (
                    list(
                        manager.filter(
                            **{spec.lookup_field: UUID(int=0)}
                        ).values_list(spec.workspace_field, flat=True)[:1]
                    )
                    == []
                ), key
        finally:
            clear_request_tenant()


# ---------------------------------------------------------------------------
# suggestion.accept/reject — decision tools scoped by the suggestion's workspace
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestSuggestionDecisionToolsAreWorkspaceScoped:
    """B-01: ``suggestion.accept``/``reject`` must gate on the suggestion row.

    Both tools take only the suggestion ``id``. Without an entry in
    ``mcp_server.workspace_scope._TOOL_TARGETS`` the dispatcher resolves no
    target workspace and the WRITE gate runs on the caller's tenant-wide role
    union, so an editor in workspace A could decide a suggestion of workspace B
    (same tenant). The registry entry closes that; these tests pin it against
    the real (unmocked) gate.
    """

    @pytest.mark.parametrize("tool_name", ["suggestion.accept", "suggestion.reject"])
    def test_decision_of_a_foreign_workspace_suggestion_is_denied(
        self,
        tool_name: str,
        e2e_userrole_member: UserRole,
        e2e_api_key_member: str,
        foreign_workspace: Workspace,
    ) -> None:
        suggestion = _make_suggestion(foreign_workspace)

        with patch(
            "application.suggestion_service.SuggestionService.accept"
        ) as accept_handler, patch(
            "application.suggestion_service.SuggestionService.reject"
        ) as reject_handler:
            result = _dispatch(
                tool_name, {"id": str(suggestion.id)}, e2e_api_key_member
            )

        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED"
        # The handler must never be reached (denied before any domain work).
        accept_handler.assert_not_called()
        reject_handler.assert_not_called()
        suggestion.refresh_from_db()
        assert suggestion.status == "open"

    @pytest.mark.parametrize("tool_name", ["suggestion.accept", "suggestion.reject"])
    def test_explicit_workspace_cannot_bypass_fenced_suggestion_target(
        self,
        tool_name: str,
        e2e_tenant: Tenant,
        e2e_workspace: Workspace,
        e2e_userrole_member: UserRole,
        e2e_user_member: User,
        foreign_workspace: Workspace,
    ) -> None:
        """B-01 residual: an explicit ``workspace_id`` must not reopen the hole.

        A caller fenced (WRITE only) to workspace A can send
        ``workspace_id=A`` alongside a workspace-B suggestion id. Since #1376
        the undeclared parameter is dropped before the gate, so the
        suggestion's real workspace drives the fence and the call is denied
        before the handler (the W13b handler guard remains as defense in depth
        for direct calls).
        """
        suggestion = _make_suggestion(foreign_workspace)
        key = AuthenticationService().create_api_key(
            user_id=e2e_user_member.id,
            tenant_id=e2e_tenant.id,
            name="explicit-scope-suggestion-key",
            principal_type="agent",
            agent_label="audit-agent",
            scope="write",
            workspace_ids=[str(e2e_workspace.id)],
            expires_at=timezone.now() + timedelta(days=1),
        )

        with patch(
            "application.suggestion_service.SuggestionService.accept"
        ) as accept_handler, patch(
            "application.suggestion_service.SuggestionService.reject"
        ) as reject_handler:
            result = _dispatch(
                tool_name,
                {"id": str(suggestion.id), "workspace_id": str(e2e_workspace.id)},
                key.plaintext,
            )

        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED"
        # Denied before any domain work.
        accept_handler.assert_not_called()
        reject_handler.assert_not_called()
        suggestion.refresh_from_db()
        assert suggestion.status == "open"

    @pytest.mark.parametrize("tool_name", ["suggestion.accept", "suggestion.reject"])
    def test_decision_of_own_workspace_suggestion_is_admitted(
        self,
        tool_name: str,
        e2e_userrole_member: UserRole,
        e2e_api_key_member: str,
        e2e_workspace: Workspace,
    ) -> None:
        """Positive control: the same caller/key, suggestion in their workspace."""
        suggestion = _make_suggestion(e2e_workspace)
        method = "accept" if tool_name == "suggestion.accept" else "reject"

        with patch(
            f"application.suggestion_service.SuggestionService.{method}",
            return_value={"id": str(suggestion.id), "status": "accepted"},
        ) as handler:
            result = _dispatch(
                tool_name, {"id": str(suggestion.id)}, e2e_api_key_member
            )

        assert result.success is True, result.message
        handler.assert_called_once()
