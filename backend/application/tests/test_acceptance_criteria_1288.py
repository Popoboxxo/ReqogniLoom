"""#1288 — structured acceptance criteria through the application service.

The single-criterion write path (``GET/PATCH .../acceptance-criteria/{index}/``)
and the MCP ``set`` path both go through :class:`RequirementService`; this pins
the service behaviour directly (no HTTP) so a failure points at the service.
"""
from __future__ import annotations

import pytest

from application.base import NotFoundError, ValidationError
from application.requirement_service import RequirementService
from auth_tenancy.context import AuthContext, AuthMethod
from persistence.models import Artifact, Requirement, Tenant, User, Workspace
from persistence.tenancy import TenantContext


@pytest.fixture
def env(db):
    tenant = Tenant.objects.create(name="t-criteria", slug="t-criteria")
    TenantContext.set_tenant(tenant.id)
    try:
        owner = User.objects.create(
            tenant=tenant, username="crit-owner", email="crit@example.com"
        )
        workspace = Workspace.objects.create(tenant=tenant, name="ws")
        artifact = Artifact.objects.create(
            tenant=tenant,
            workspace=workspace,
            artifact_type="Requirement",
        )
        requirement = Requirement.objects.create(
            tenant=tenant, artifact=artifact, title="R"
        )
        ctx = AuthContext(
            user_id=owner.id,
            tenant_id=tenant.id,
            active_roles=("editor",),
            auth_method=AuthMethod.BEARER_TOKEN,
        )
        yield {"tenant": tenant, "workspace": workspace, "requirement": requirement, "ctx": ctx}
    finally:
        TenantContext.clear_tenant()


def test_set_then_list_acceptance_criteria(env):
    service = RequirementService()
    result = service.set_acceptance_criteria(
        env["requirement"].id,
        env["ctx"],
        [
            {"text": "must be fast", "fulfilled": False},
            {"text": "must be safe", "fulfilled": True},
        ],
    )
    assert result["total"] == 2
    listed = service.list_acceptance_criteria(env["requirement"].id, env["ctx"])
    assert [c["text"] for c in listed] == ["must be fast", "must be safe"]


def test_get_acceptance_criterion_by_index(env):
    service = RequirementService()
    service.set_acceptance_criteria(
        env["requirement"].id,
        env["ctx"],
        [{"text": "a", "fulfilled": False}, {"text": "b", "fulfilled": False}],
    )
    item = service.get_acceptance_criterion(env["requirement"].id, env["ctx"], 1)
    assert item["index"] == 1
    assert item["criterion"]["text"] == "b"
    assert item["total"] == 2


def test_get_out_of_range_index_raises(env):
    service = RequirementService()
    service.set_acceptance_criteria(
        env["requirement"].id, env["ctx"], [{"text": "a", "fulfilled": False}]
    )
    with pytest.raises(NotFoundError):
        service.get_acceptance_criterion(env["requirement"].id, env["ctx"], 5)


def test_check_off_a_single_criterion(env):
    service = RequirementService()
    service.set_acceptance_criteria(
        env["requirement"].id,
        env["ctx"],
        [{"text": "a", "fulfilled": False}, {"text": "b", "fulfilled": False}],
    )
    result = service.update_acceptance_criterion(
        env["requirement"].id, env["ctx"], 0, fulfilled=True
    )
    assert result["criterion"]["fulfilled"] is True
    listed = service.list_acceptance_criteria(env["requirement"].id, env["ctx"])
    assert listed[0]["fulfilled"] is True
    assert listed[1]["fulfilled"] is False


def test_update_rejects_a_non_boolean_fulfilled(env):
    service = RequirementService()
    service.set_acceptance_criteria(
        env["requirement"].id, env["ctx"], [{"text": "a", "fulfilled": False}]
    )
    with pytest.raises(ValidationError):
        service.update_acceptance_criterion(
            env["requirement"].id, env["ctx"], 0, fulfilled="yes"
        )


def test_set_rejects_a_malformed_list(env):
    service = RequirementService()
    with pytest.raises(ValidationError):
        service.set_acceptance_criteria(
            env["requirement"].id, env["ctx"], [{"text": "", "fulfilled": False}]
        )
