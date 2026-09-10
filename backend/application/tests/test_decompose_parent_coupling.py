# backend/application/tests/test_decompose_parent_coupling.py
"""Artifact.parent and the decomposes link are written together or not at all."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from persistence.errors import ValidationError
from persistence.tenancy import TenantContext


@pytest.fixture
def env(db):
    from auth_tenancy.context import AuthContext
    from link_types.workspace_store import provision_workspace_link_types
    from persistence.models import Artifact, Requirement, Tenant, User, Workspace

    tenant = Tenant.objects.create(name="decompose-coupling")
    TenantContext.set_tenant(tenant.id)
    ws = Workspace.objects.create(tenant=tenant, name="ws")
    provision_workspace_link_types(workspace_id=ws.id, tenant_id=tenant.id)
    # TraceLink.created_by FKs to a real User row (RLS/audit trail) — a bare
    # uuid4() user_id fails the FK constraint on the first trace link write.
    user = User.objects.create(
        username="decompose-coupling-user",
        email="decompose-coupling@example.com",
        tenant=tenant,
    )

    art = Artifact.objects.create(
        tenant=tenant, workspace=ws, artifact_type="Requirement"
    )
    parent = Requirement.objects.create(
        tenant=tenant, workspace=ws, artifact=art, title="parent"
    )
    ctx = AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=("admin",),
        auth_method="test",
        workspace_id=ws.id,
    )
    yield {"tenant": tenant, "workspace": ws, "parent": parent, "ctx": ctx}
    TenantContext.clear_tenant()


from application.trace_link_service import TraceLinkService  # noqa: E402

# Captured before any test patches the class attribute below, so the
# pass-through call in _fail_only_decomposes_link always reaches the real
# implementation instead of recursing into the patched mock.
_REAL_CREATE_TRACE_LINK = TraceLinkService.create_trace_link


def _fail_only_decomposes_link(*, source_id, target_id, link_type, ctx, **kwargs):
    """Fail exactly the 'decomposes' create_trace_link call.

    Deliberately narrower than mocking the whole method: the 'derives-from'
    call right after it must still be free to succeed, so this reproduces
    the exact old bug — a swallowed 'decomposes' failure next to a
    successfully created 'derives-from' link and parent FK — instead of
    also breaking 'derives-from' and rolling back for the wrong reason.
    """
    if link_type == "decomposes":
        raise ValidationError("catalog rejected it")
    return _REAL_CREATE_TRACE_LINK(
        TraceLinkService(),
        source_id=source_id,
        target_id=target_id,
        link_type=link_type,
        ctx=ctx,
        **kwargs,
    )


@pytest.mark.django_db
def test_decompose_sets_both_the_parent_fk_and_the_link(env):
    from application.requirement_service import RequirementService
    from persistence.models import Artifact, Requirement, TraceLink

    result = RequirementService().decompose(
        requirement_id=env["parent"].id,
        ctx=env["ctx"],
        children=[{"title": "child A"}, {"title": "child B"}],
    )

    for child in result.children:
        artifact_id = Requirement.objects.get(id=child.id).artifact_id
        artifact = Artifact.objects.get(id=artifact_id)
        assert artifact.parent_id == env["parent"].artifact_id
        assert TraceLink.objects.filter(
            source_id=env["parent"].artifact_id,
            target_id=artifact_id,
            link_type="decomposes",
        ).exists()


@pytest.mark.django_db
def test_a_failing_link_rolls_back_the_parent_fk(env):
    from application.requirement_service import RequirementService
    from persistence.models import Artifact, TraceLink

    with patch(
        "application.trace_link_service.TraceLinkService.create_trace_link",
        side_effect=_fail_only_decomposes_link,
    ):
        with pytest.raises(ValidationError):
            RequirementService().decompose(
                requirement_id=env["parent"].id,
                ctx=env["ctx"],
                children=[{"title": "child"}],
            )

    assert not Artifact.objects.filter(
        parent_id=env["parent"].artifact_id
    ).exists()
    assert not TraceLink.objects.filter(link_type="decomposes").exists()
    assert not TraceLink.objects.filter(link_type="derives-from").exists()


@pytest.mark.django_db
def test_decompose_no_longer_swallows_link_failures(env):
    """The old code logged a warning and returned a half-built hierarchy:
    parent FK + 'derives-from' link present, 'decomposes' link silently
    missing. The fix must propagate the failure instead."""
    from application.requirement_service import RequirementService

    with patch(
        "application.trace_link_service.TraceLinkService.create_trace_link",
        side_effect=_fail_only_decomposes_link,
    ):
        with pytest.raises(ValidationError):
            RequirementService().decompose(
                requirement_id=env["parent"].id,
                ctx=env["ctx"],
                children=[{"title": "child"}],
            )
