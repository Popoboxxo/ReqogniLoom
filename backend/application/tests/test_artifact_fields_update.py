"""The ``update_artifact_fields`` seam (Tabellenansicht S1, Task 1.2).

Pins the composition the plan specifies: the workflow/structural guard, the
item-level write right, the optimistic lock, the typed service call and the
gateway write happen in **one** function, in that order, so a second transport
cannot skip a step.

The bulk path (``BulkUpdateService``) already dispatches to the typed services
directly (merged in #1854) — this seam is the documented single entry point for
the inline/bulk writes that follow, and the regression here is the contract, not
a rewrite of the merged service.
"""
from __future__ import annotations

import pytest

from application.artifact_fields_update import (
    ArtifactFrozenError,
    FieldUpdateResult,
    update_artifact_fields,
)
from application.artifact_freeze import FreezeInfo
from application.base import (
    NotFoundError,
    OptimisticLockError,
    PermissionDeniedError,
    ValidationError,
)
from auth_tenancy.context import AuthContext, AuthMethod
from auth_tenancy.models import ITEM_PERMISSION_NONE, ITEM_PERMISSION_READ, ItemPermission
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Artifact, Requirement, Tenant, User, Workspace
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db


@pytest.fixture
def env(db):
    from django.core.management import call_command

    tenant = Tenant.objects.create(name="seam", slug="seam")
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="seam-ws", preset={"name": "standard"}
        )
        user = User.objects.create(
            tenant=tenant, username="seam-user", email="seam@example.com"
        )
        other = User.objects.create(
            tenant=tenant, username="seam-other", email="seam-other@example.com"
        )
    finally:
        clear_request_tenant()

    call_command("bootstrap_attribute_definitions", tenant=str(tenant.id))
    TenantContext.set_tenant(tenant.id)

    def ctx(roles=("editor",), user_id=None):
        return AuthContext(
            user_id=user_id or user.id,
            tenant_id=tenant.id,
            active_roles=roles,
            auth_method=AuthMethod.BEARER_TOKEN,
        )

    data = {
        "tenant": tenant,
        "workspace": workspace,
        "user": user,
        "other": other,
        "ctx": ctx(),
        "viewer": ctx(roles=("viewer",)),
        "other_ctx": ctx(user_id=other.id),
        "ctx_factory": ctx,
    }
    try:
        yield data
    finally:
        TenantContext.clear_tenant()


def _requirement(env, title="T1", *, workspace=None, tenant=None) -> Requirement:
    tenant = tenant or env["tenant"]
    artifact = Artifact.objects.create(
        tenant=tenant,
        workspace=workspace or env["workspace"],
        artifact_type="Requirement",
    )
    return Requirement.objects.create(
        tenant=tenant,
        artifact=artifact,
        title=title,
        uid=f"R-{title}",
        description="D1",
    )


def _reload(requirement: Requirement) -> Requirement:
    return Requirement.objects.get(id=requirement.id)


# ---------------------------------------------------------------------------
# Happy paths / version behaviour
# ---------------------------------------------------------------------------


def test_updates_title_and_bumps_version_once(env):
    requirement = _requirement(env)
    assert requirement.version == 1

    result = update_artifact_fields(
        env["ctx"],
        "Requirement",
        requirement.artifact_id,
        {"title": "T2", "description": "D2"},
        requirement.version,
        change_reason="test",
    )

    assert isinstance(result, FieldUpdateResult)
    assert result.artifact_id == requirement.artifact_id
    assert result.entity_id == requirement.id
    assert result.item_type == "Requirement"
    assert result.version == 2
    stored = _reload(requirement)
    assert (stored.title, stored.description, stored.version) == ("T2", "D2", 2)


def test_expected_version_mismatch_raises_and_writes_nothing(env):
    requirement = _requirement(env)
    with pytest.raises(OptimisticLockError):
        update_artifact_fields(
            env["ctx"],
            "Requirement",
            requirement.artifact_id,
            {"title": "T9"},
            requirement.version + 5,
            change_reason="test",
        )
    assert _reload(requirement).title == "T1"


def test_none_expected_version_skips_the_lock(env):
    requirement = _requirement(env)
    result = update_artifact_fields(
        env["ctx"],
        "Requirement",
        requirement.artifact_id,
        {"title": "T3"},
        None,
        change_reason="test",
    )
    assert result.version == 2


def test_gateway_only_change_bumps_entity_version(env):
    requirement = _requirement(env)
    result = update_artifact_fields(
        env["ctx"],
        "Requirement",
        requirement.artifact_id,
        {"priority": "high"},
        requirement.version,
        change_reason="test",
    )
    assert result.version == requirement.version + 1
    assert _reload(requirement).version == result.version
    assert Artifact.objects.get(id=requirement.artifact_id).priority == "high"


def test_replaying_same_expected_version_after_gateway_only_change_conflicts(env):
    requirement = _requirement(env)
    update_artifact_fields(
        env["ctx"],
        "Requirement",
        requirement.artifact_id,
        {"priority": "high"},
        requirement.version,
        change_reason="test",
    )
    with pytest.raises(OptimisticLockError):
        update_artifact_fields(
            env["ctx"],
            "Requirement",
            requirement.artifact_id,
            {"priority": "low"},
            requirement.version,
            change_reason="test",
        )


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------


def test_workflow_field_and_parent_id_rejected_before_any_write(env):
    requirement = _requirement(env)
    for payload in ({"status": "approved"}, {"parent_id": None}, {"uid": "X-1"}):
        with pytest.raises(ValidationError):
            update_artifact_fields(
                env["ctx"],
                "Requirement",
                requirement.artifact_id,
                payload,
                requirement.version,
                change_reason="test",
            )
    stored = _reload(requirement)
    assert (stored.title, stored.version) == ("T1", 1)


def test_unknown_field_rejected(env):
    requirement = _requirement(env)
    with pytest.raises(ValidationError, match="nope"):
        update_artifact_fields(
            env["ctx"],
            "Requirement",
            requirement.artifact_id,
            {"nope": "x"},
            requirement.version,
            change_reason="test",
        )


def test_empty_fields_rejected(env):
    requirement = _requirement(env)
    with pytest.raises(ValidationError, match="No fields"):
        update_artifact_fields(
            env["ctx"], "Requirement", requirement.artifact_id, {}, requirement.version
        )


def test_item_type_mismatch_rejected(env):
    requirement = _requirement(env)
    with pytest.raises(ValidationError, match="Requirement"):
        update_artifact_fields(
            env["ctx"],
            "Adr",
            requirement.artifact_id,
            {"title": "x"},
            requirement.version,
        )


def test_other_tenant_artifact_not_found(env):
    foreign = Tenant.objects.create(name="foreign-seam", slug="foreign-seam")
    TenantContext.set_tenant(foreign.id)
    try:
        foreign_workspace = Workspace.objects.create(tenant=foreign, name="fw")
    finally:
        TenantContext.clear_tenant()
    TenantContext.set_tenant(foreign.id)
    try:
        requirement = _requirement(env, tenant=foreign, workspace=foreign_workspace)
    finally:
        TenantContext.set_tenant(env["tenant"].id)
    with pytest.raises(NotFoundError):
        update_artifact_fields(
            env["ctx"],
            "Requirement",
            requirement.artifact_id,
            {"title": "x"},
            requirement.version,
        )


def test_outdated_artifact_rejected(env):
    requirement = _requirement(env)
    Artifact.objects.filter(id=requirement.artifact_id).update(
        lifecycle_status="outdated"
    )
    with pytest.raises(ValidationError, match="outdated"):
        update_artifact_fields(
            env["ctx"],
            "Requirement",
            requirement.artifact_id,
            {"title": "x"},
            requirement.version,
        )


def test_viewer_role_permission_denied(env):
    requirement = _requirement(env)
    with pytest.raises(PermissionDeniedError):
        update_artifact_fields(
            env["viewer"],
            "Requirement",
            requirement.artifact_id,
            {"title": "x"},
            requirement.version,
        )


# ---------------------------------------------------------------------------
# Item-level rules
# ---------------------------------------------------------------------------


def _rule(env, level, artifact_id=None):
    return ItemPermission.objects.create(
        tenant=env["tenant"],
        user=env["user"],
        workspace=env["workspace"],
        artifact_id=artifact_id,
        permission_level=level,
    )


def test_item_rule_read_blocks_write(env):
    requirement = _requirement(env)
    _rule(env, ITEM_PERMISSION_READ, artifact_id=requirement.artifact_id)
    with pytest.raises(PermissionDeniedError):
        update_artifact_fields(
            env["ctx"],
            "Requirement",
            requirement.artifact_id,
            {"title": "x"},
            requirement.version,
        )
    assert _reload(requirement).title == "T1"


def test_item_rule_none_blocks_write_as_not_found(env):
    requirement = _requirement(env)
    _rule(env, ITEM_PERMISSION_NONE, artifact_id=requirement.artifact_id)
    with pytest.raises(NotFoundError):
        update_artifact_fields(
            env["ctx"],
            "Requirement",
            requirement.artifact_id,
            {"title": "x"},
            requirement.version,
        )
    assert _reload(requirement).title == "T1"


# ---------------------------------------------------------------------------
# Freeze
# ---------------------------------------------------------------------------


def test_frozen_artifact_raises_artifact_frozen_error(env, monkeypatch):
    requirement = _requirement(env)

    def _frozen(artifact):
        return FreezeInfo(state_name="Freigegeben")

    monkeypatch.setattr(
        "application.artifact_freeze.is_frozen", _frozen, raising=True
    )
    with pytest.raises(ArtifactFrozenError) as excinfo:
        update_artifact_fields(
            env["ctx"],
            "Requirement",
            requirement.artifact_id,
            {"title": "x"},
            requirement.version,
            change_reason="test",
        )
    assert excinfo.value.state_name == "Freigegeben"
    assert _reload(requirement).title == "T1"
