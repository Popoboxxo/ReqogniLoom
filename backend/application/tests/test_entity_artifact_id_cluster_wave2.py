"""Targeted regressions for the entity-id / artifact-id cluster (#2005-#2010).

Each fix delegates id resolution to the same canonical helper
(``TraceLinkService._resolve_artifact_id``) so an artifact id keeps working
while a user-facing entity id is now accepted too. The tests below pin both
halves of that contract at the layer where the bug lived.
"""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest

from application.base import NotFoundError, OptimisticLockError, ValidationError
from application.change_request_service import ChangeRequestService
from application.interview_service import InterviewService
from application.models import ChangeRequest, ChangeRequestAffectedItem
from application.optimistic_lock import assert_expected_version
from application.requirement_service import RequirementService
from application.trace_link_service import TraceLinkService
from auth_tenancy.context import AuthContext
from persistence.models import (
    ArchitectureElement,
    Artifact,
    Requirement,
    Tenant,
    User,
    Workspace,
)
from persistence.tenancy import TenantContext

# ---------------------------------------------------------------------------
# Fixtures / helpers (mirrors test_change_request_cm_traceability.py)
# ---------------------------------------------------------------------------


@pytest.fixture
def tenant() -> Tenant:
    return Tenant.objects.create(name="id-cluster", slug="id-cluster")


@pytest.fixture
def user(tenant: Tenant) -> User:
    return User.objects.create(
        username="id-cluster-user", email="id-cluster@example.com", tenant=tenant
    )


@pytest.fixture
def workspace(tenant: Tenant) -> Workspace:
    TenantContext.set_tenant(tenant.id)
    try:
        return Workspace.objects.create(
            tenant=tenant, name="ws-id-cluster", preset={"name": "standard"}
        )
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def ctx(user: User) -> AuthContext:
    return AuthContext(
        user_id=user.id,
        tenant_id=user.tenant.id,
        active_roles=("editor",),
        auth_method="test",
        api_key_id=None,
        tenant_name="id-cluster",
    )


def _requirement(tenant: Tenant, workspace: Workspace, title: str) -> Requirement:
    """Create a Requirement with a real backing Artifact."""
    TenantContext.set_tenant(tenant.id)
    try:
        artifact = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="requirement"
        )
        return Requirement.objects.create(
            tenant=tenant, artifact=artifact, title=title
        )
    finally:
        TenantContext.clear_tenant()


# ---------------------------------------------------------------------------
# #2010 — stale-version error names the Artifact id the caller holds
# ---------------------------------------------------------------------------


def test_stale_version_reports_artifact_id_not_entity_pk() -> None:
    entity_pk = uuid.uuid4()
    artifact_id = uuid.uuid4()

    class _Stub:
        pk = entity_pk
        version = 1

    # Assigned outside the class body: a class-body assignment named
    # ``artifact_id = artifact_id`` shadows the enclosing local and raises
    # NameError before the class is even built.
    _Stub.artifact_id = artifact_id

    with pytest.raises(OptimisticLockError) as exc_info:
        assert_expected_version(_Stub(), 7, entity_type="Requirement")

    message = str(exc_info.value)
    assert str(artifact_id) in message
    assert str(entity_pk) not in message


def test_stale_version_falls_back_to_pk_without_artifact() -> None:
    entity_pk = uuid.uuid4()

    class _Stub:
        pk = entity_pk
        version = 1

    with pytest.raises(OptimisticLockError) as exc_info:
        assert_expected_version(_Stub(), 7, entity_type="Goal")

    assert str(entity_pk) in str(exc_info.value)


# ---------------------------------------------------------------------------
# #2009 — affected items accept both id kinds and are readable
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_affected_items_accept_entity_id(tenant, workspace, ctx) -> None:
    requirement = _requirement(tenant, workspace, "Entity id prefill")

    cr = ChangeRequestService().create_change_request(
        workspace_id=workspace.id,
        title="CR from entity id",
        ctx=ctx,
        affected_item_ids=[requirement.id],
    )

    stored = [row.item_id for row in ChangeRequestAffectedItem.objects.filter(change_request_id=cr.id)]
    assert stored == [str(requirement.artifact_id)]
    assert str(requirement.id) != str(requirement.artifact_id)


@pytest.mark.django_db
def test_affected_items_dedup_mixed_id_kinds(tenant, workspace, ctx) -> None:
    requirement = _requirement(tenant, workspace, "Mixed id prefill")

    cr = ChangeRequestService().create_change_request(
        workspace_id=workspace.id,
        title="CR from both ids",
        ctx=ctx,
        affected_item_ids=[requirement.id, requirement.artifact_id],
    )

    assert ChangeRequestAffectedItem.objects.filter(change_request_id=cr.id).count() == 1


@pytest.mark.django_db
def test_affected_items_unknown_id_still_validation_error(tenant, workspace, ctx) -> None:
    with pytest.raises(ValidationError, match="not found in workspace"):
        ChangeRequestService().create_change_request(
            workspace_id=workspace.id,
            title="Bad prefill",
            ctx=ctx,
            affected_item_ids=[uuid.uuid4()],
        )
    assert not ChangeRequest.objects.filter(workspace_id=workspace.id).exists()


@pytest.mark.parametrize(
    "resolver_error",
    [
        NotFoundError("no such entity"),
        ValueError("null artifact FK"),
        TypeError("unusable artifact FK"),
    ],
)
@pytest.mark.django_db
def test_affected_items_resolver_errors_stay_400(resolver_error, tenant, workspace) -> None:
    """The resolver can raise ValueError/TypeError on a NULL artifact FK.

    All three failures must land in ``unresolved`` and surface as the usual
    ValidationError (400); only NotFoundError used to be caught, so the other
    two escaped as an unhandled 500.
    """
    with patch.object(
        TraceLinkService, "_resolve_artifact_id", side_effect=resolver_error
    ):
        with pytest.raises(ValidationError, match="not found in workspace"):
            ChangeRequestService._validate_affected_items(
                [uuid.uuid4()], workspace.id, tenant.id
            )


# ---------------------------------------------------------------------------
# #2005 — set_target accepts a Requirement entity id
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_set_target_accepts_entity_id(tenant, workspace, ctx) -> None:
    requirement = _requirement(tenant, workspace, "Grounding target")
    TenantContext.set_tenant(tenant.id)
    try:
        from persistence.models import InterviewSession

        session = InterviewSession.objects.create(
            tenant=tenant,
            workspace=workspace,
            artifact_type="Requirement",
            session_kind=InterviewSession.SESSION_KIND_SINGLE,
        )
    finally:
        TenantContext.clear_tenant()

    InterviewService().set_target(ctx, session.id, requirement.id)

    session.refresh_from_db()
    assert str(session.target_artifact_id) == str(requirement.artifact_id)


@pytest.mark.django_db
def test_set_target_still_accepts_artifact_id(tenant, workspace, ctx) -> None:
    requirement = _requirement(tenant, workspace, "Grounding target artifact id")
    TenantContext.set_tenant(tenant.id)
    try:
        from persistence.models import InterviewSession

        session = InterviewSession.objects.create(
            tenant=tenant,
            workspace=workspace,
            artifact_type="Requirement",
            session_kind=InterviewSession.SESSION_KIND_SINGLE,
        )
    finally:
        TenantContext.clear_tenant()

    InterviewService().set_target(ctx, session.id, requirement.artifact_id)

    session.refresh_from_db()
    assert str(session.target_artifact_id) == str(requirement.artifact_id)


# ---------------------------------------------------------------------------
# #2008 — re-parent accepts a Requirement entity id
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_parent_update_accepts_entity_id(tenant, workspace, ctx) -> None:
    parent = _requirement(tenant, workspace, "Parent")
    child = _requirement(tenant, workspace, "Child")

    RequirementService().update_requirement(
        child.id, ctx, parent_id=parent.id, change_reason="reparent by entity id"
    )

    child.artifact.refresh_from_db()
    assert str(child.artifact.parent_id) == str(parent.artifact_id)


@pytest.mark.django_db
def test_parent_update_unknown_id_is_actionable(tenant, workspace, ctx) -> None:
    child = _requirement(tenant, workspace, "Child with bad parent")

    with pytest.raises(NotFoundError, match="Artifact id or a Requirement id"):
        RequirementService().update_requirement(
            child.id, ctx, parent_id=uuid.uuid4(), change_reason="bad parent"
        )


@pytest.mark.django_db
def test_parent_update_rejects_non_requirement_entity_id(tenant, workspace, ctx) -> None:
    """A resolved ADR/ArchitectureElement id must not become a Requirement parent.

    The canonical resolver accepts every artifact-backed entity type, so the
    resolved Artifact FK has to be checked for an actual Requirement row.
    """
    child = _requirement(tenant, workspace, "Child with foreign parent")
    TenantContext.set_tenant(tenant.id)
    try:
        artifact = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="ArchitectureElement"
        )
        element = ArchitectureElement.objects.create(
            tenant=tenant, artifact=artifact, title="Not a Requirement"
        )
    finally:
        TenantContext.clear_tenant()

    with pytest.raises(ValidationError, match="does not name a Requirement"):
        RequirementService().update_requirement(
            child.id, ctx, parent_id=element.id, change_reason="bad parent type"
        )

    child.artifact.refresh_from_db()
    assert child.artifact.parent_id is None


# ---------------------------------------------------------------------------
# #2006 — multi formalize returns the user-facing entity id
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_multi_formalize_returns_entity_id(tenant, workspace, ctx) -> None:
    from persistence.models import InterviewSession

    TenantContext.set_tenant(tenant.id)
    try:
        session = InterviewSession.objects.create(
            tenant=tenant,
            workspace=workspace,
            artifact_type=None,
            session_kind=InterviewSession.SESSION_KIND_MULTI,
            collected_fields={},
        )
    finally:
        TenantContext.clear_tenant()

    proposal = [
        {
            "type": "Requirement",
            "fields": {
                "title": "Multi-created requirement",
                "rationale": "Because",
                "acceptance_criteria": "It exists",
                "verification_method": "Test",
            },
            "links": [],
        }
    ]
    result = InterviewService().formalize(ctx, session.id, proposal)

    created = Requirement.objects.filter(title="Multi-created requirement").first()
    assert created is not None
    assert result["created"][0]["artifact_id"] == str(created.id)
    # The returned id must be usable with the entity-keyed read service.
    assert str(RequirementService().get_requirement(uuid.UUID(result["created"][0]["artifact_id"]), ctx).id) == str(created.id)
