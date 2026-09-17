"""Regression test for GitHub issue #736: ``interview.formalize`` returned
an unresolvable ``resulting_artifact_ids`` entry.

Root cause: ``InterviewService._formalize_single`` serialized the newly
created/updated ``Requirement``'s backing ``Artifact`` id
(``Requirement.artifact_id``) into ``resulting_artifact_ids`` instead of the
Requirement's own id (``Requirement.id``). Both are real, distinct UUIDs
(``Requirement.artifact`` is a ``OneToOneField``), so the response looked
correct (a well-formed UUID, 200 status) while pointing at a row
``requirement.get()``/``RequirementService.get_requirement()`` can never
resolve, because that lookup filters on ``Requirement.id``, not
``Requirement.artifact_id``.

Style mirrors ``test_goal_lifecycle_issue346.py``: drives the real
``InterviewService``/``RequirementService`` through the MCP tool groups
against the DB, rather than mocking the service away -- the existing
``test_interview_tool_group.py`` suite mocks ``InterviewService`` entirely
and therefore could never have caught this: it only checked that the
formalize call was dispatched and its (mocked) return value passed through
unchanged, never that the id inside it actually resolves to a real
artifact.
"""
from __future__ import annotations

import uuid

import pytest

from auth_tenancy.context import AuthContext, AuthMethod
from mcp_server.tools.interview import InterviewToolGroup
from mcp_server.tools.requirements import RequirementsToolGroup
from persistence.models import Tenant, Workspace
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db

VALID_API_KEY = "reqlo_testkey1234"


def _ctx(*, tenant_id, roles=("editor",)) -> AuthContext:
    return AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=tenant_id,
        active_roles=roles,
        auth_method=AuthMethod.API_KEY,
        api_key_id=uuid.uuid4(),
    )


def _tenant_and_workspace(tenant_name: str) -> tuple:
    tenant = Tenant.objects.create(name=tenant_name)
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(tenant=tenant, name=tenant_name)
    finally:
        TenantContext.clear_tenant()
    return tenant, workspace


def test_formalize_resulting_artifact_id_resolves_via_requirement_get():
    """Full repro from issue #736: start -> answer (title, rationale) ->
    formalize -> the returned id must be directly usable with
    requirement.get(), and the resolved content must match the answers."""
    tenant, workspace = _tenant_and_workspace("I736-Formalize")
    ctx = _ctx(tenant_id=tenant.id)

    interview_group = InterviewToolGroup()
    started = interview_group.execute_tool(
        tool_name="interview.start",
        params={"artifact_type": "Requirement", "workspace_id": str(workspace.id)},
        auth_context=ctx,
        api_key=VALID_API_KEY,
    )
    assert started.success is True, started.message
    session_id = started.data["id"]

    for field, value in (
        ("title", "SSO login support"),
        ("rationale", "Reduce password fatigue"),
    ):
        answered = interview_group.execute_tool(
            tool_name="interview.answer",
            params={"session_id": session_id, "field": field, "value": value},
            auth_context=ctx,
            api_key=VALID_API_KEY,
        )
        assert answered.success is True, answered.message
    assert answered.data["phase"] == "formalization"

    formalized = interview_group.execute_tool(
        tool_name="interview.formalize",
        params={"session_id": session_id},
        auth_context=ctx,
        api_key=VALID_API_KEY,
    )
    assert formalized.success is True, formalized.message
    assert formalized.data["status"] == "completed"
    resulting_ids = formalized.data["resulting_artifact_ids"]
    assert len(resulting_ids) == 1

    # This is the actual bug: the id in resulting_artifact_ids used to be
    # the backing Artifact's id, not the Requirement's own id, so
    # requirement.get() reported "not found" for a Requirement that really
    # existed with different content-bearing id.
    fetched = RequirementsToolGroup().execute_tool(
        tool_name="requirement.get",
        params={"id": resulting_ids[0]},
        auth_context=ctx,
        api_key=VALID_API_KEY,
    )
    assert fetched.success is True, fetched.message
    requirement = fetched.data["requirement"]
    assert requirement["id"] == resulting_ids[0]
    assert requirement["title"] == "SSO login support"
    assert requirement["description"] == "Reduce password fatigue"
    assert requirement["status"] == "draft"
