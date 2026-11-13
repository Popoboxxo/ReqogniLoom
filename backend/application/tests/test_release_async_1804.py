"""GH-1804 — the release cascade as a Celery job.

``ReleaseService.release_element`` refuses more than
``MAX_SYNC_RELEASE_ITEMS`` transitions on a request thread and raises
``ReleaseTooLargeError``; ``application.tasks.release_element_async`` runs the
same cascade in a worker. These tests pin the worker half:

* the tenant context is re-armed (ADR-03: only ids cross the queue boundary),
* the caller's *roles* are re-resolved in the workspace — the payload cannot
  carry ``active_roles``, and a worker must not invent them,
* the rebuilt context is the caller's (user, tenant, bearer token, no API key),
  so the audit entry and the tier pin are attributed correctly,
* a second run is a no-op: no duplicate content snapshot (the idempotency
  contract lives in ``_stamp_release``, not in the task).

The transport half (202 / polling) is covered in
``rest_api/tests/test_release_views.py``.
"""

from __future__ import annotations

import contextlib
import uuid
from collections.abc import Iterator
from unittest.mock import patch

import pytest

from application.base import ValidationError
from application.release_service import ReleaseService
from application.tasks import release_element_async
from auth_tenancy.context import AuthMethod
from auth_tenancy.models import UserRole
from persistence.models import (
    Allocation,
    AllocationStatus,
    ArchitectureElement,
    Artifact,
    ArtifactVersion,
    Requirement,
    Tenant,
    User,
    Workspace,
)
from persistence.tenancy import TenantContext
from workflow.definition_store import WorkflowDefinitionStore
from workflow.lifecycle_manager import StateLifecycleManager
from workflow.models import WorkflowItemState

pytestmark = pytest.mark.django_db


@contextlib.contextmanager
def _active(tenant: Tenant) -> Iterator[None]:
    """Arm the tenant for fixture/assertion code that runs outside the task."""
    TenantContext.set_tenant(tenant.id)
    try:
        yield
    finally:
        TenantContext.clear_tenant()


@pytest.fixture(autouse=True)
def _clean_tenant_context() -> Iterator[None]:
    """The task must leave no armed tenant behind; start from a clean thread."""
    TenantContext.clear_tenant()
    yield
    TenantContext.clear_tenant()


@pytest.fixture
def tenant() -> Tenant:
    return Tenant.objects.create(name="Release Async", slug="release-async-tenant")


@pytest.fixture
def user(tenant: Tenant) -> User:
    return User.objects.create(
        username="release-async-user", email="release-async@example.com", tenant=tenant
    )


@pytest.fixture
def workspace(tenant: Tenant) -> Workspace:
    with _active(tenant):
        workspace = Workspace.objects.create(
            tenant=tenant, name="Release-Async-WS", preset={"name": "extended"}
        )
        store = WorkflowDefinitionStore()
        for item_type in ("ArchitectureElement", "Requirement"):
            store.create_workspace_default_workflow(
                workspace_id=workspace.id,
                preset="extended",
                item_type=item_type,
                tenant_id=tenant.id,
            )
    return workspace


@pytest.fixture
def admin_role(tenant: Tenant, user: User, workspace: Workspace) -> UserRole:
    # ``TenantManager.create`` resolves its queryset (and therefore the tenant
    # context) before the explicit ``tenant`` kwarg is applied.
    with _active(tenant):
        return UserRole.objects.create(
            tenant=tenant, user=user, workspace=workspace, role="admin"
        )


@pytest.fixture
def tree(tenant: Tenant, workspace: Workspace):
    """Root + child element, one approved requirement allocated to the child.

    Built *outside* any armed tenant context: the task under test must arm it
    itself, and a leaked fixture context would hide that.
    """
    with _active(tenant):
        built = _build_tree(tenant, workspace)
    return built


def _set_state(item_id, item_type: str, workspace: Workspace, state: str) -> None:
    StateLifecycleManager().ensure_item_state(item_id, item_type, workspace.id, "draft")
    WorkflowItemState.objects.filter(
        item_id=item_id, item_type=item_type, workspace_id=workspace.id
    ).update(current_state=state)


def _element(tenant: Tenant, workspace: Workspace, title: str, parent=None):
    artifact = Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type="ArchitectureElement"
    )
    return ArchitectureElement.objects.create(
        tenant=tenant,
        workspace=workspace,
        artifact=artifact,
        title=title,
        parent=parent,
    )


def _build_tree(tenant: Tenant, workspace: Workspace):
    root = _element(tenant, workspace, "System")
    child = _element(tenant, workspace, "Subsystem", parent=root)
    for element in (root, child):
        _set_state(element.id, "ArchitectureElement", workspace, "approved")

    requirement_artifact = Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type="Requirement"
    )
    requirement = Requirement.objects.create(
        tenant=tenant,
        workspace=workspace,
        artifact=requirement_artifact,
        title="R",
        type="SyReq",
        tier_key="L2",
    )
    _set_state(requirement.id, "Requirement", workspace, "approved")
    Allocation.objects.create(
        tenant=tenant,
        workspace=workspace,
        requirement_artifact=requirement_artifact,
        element_artifact=child.artifact,
        status=AllocationStatus.DRAFT,
        is_primary=True,
    )
    return root, child, requirement


class TestWorkerContext:
    def test_the_task_rebuilds_the_callers_context_before_releasing(
        self,
        tenant: Tenant,
        user: User,
        workspace: Workspace,
        admin_role: UserRole,
    ) -> None:
        element_id = uuid.uuid4()
        captured: dict = {}

        def _capture(*, element_id, ctx, change_reason):
            captured["element_id"] = element_id
            captured["ctx"] = ctx
            captured["change_reason"] = change_reason
            # The tenant must already be armed for the ORM/RLS layers.
            captured["armed_tenant"] = TenantContext.get_tenant()
            return {"element_id": str(element_id), "elements_released": 2}

        with patch.object(ReleaseService, "release_element", side_effect=_capture):
            result = release_element_async(
                str(tenant.id),
                str(workspace.id),
                str(element_id),
                str(user.id),
                "Release for milestone M1",
            )

        assert result == {"element_id": str(element_id), "elements_released": 2}
        assert captured["element_id"] == element_id
        assert captured["change_reason"] == "Release for milestone M1"
        assert captured["armed_tenant"] == tenant.id

        ctx = captured["ctx"]
        assert ctx.user_id == user.id
        assert ctx.tenant_id == tenant.id
        assert ctx.workspace_id == workspace.id
        # Roles are re-resolved in the workspace, never taken from the payload.
        assert ctx.active_roles == ("admin",)
        # Rebuilt as the caller's bearer session — never a system/agent context.
        assert ctx.auth_method == AuthMethod.BEARER_TOKEN
        assert ctx.api_key_id is None
        assert ctx.actor_type == "user"

    def test_the_task_clears_the_tenant_it_armed(
        self,
        tenant: Tenant,
        user: User,
        workspace: Workspace,
        admin_role: UserRole,
    ) -> None:
        with patch.object(ReleaseService, "release_element", return_value={}):
            release_element_async(
                str(tenant.id),
                str(workspace.id),
                str(uuid.uuid4()),
                str(user.id),
                "Release",
            )

        assert not TenantContext.is_set()

    def test_a_tenant_armed_by_the_caller_is_not_cleared(
        self,
        tenant: Tenant,
        user: User,
        workspace: Workspace,
        admin_role: UserRole,
    ) -> None:
        """#522: under CELERY_TASK_ALWAYS_EAGER the body runs inline."""
        other = Tenant.objects.create(name="Other", slug="release-async-other")
        TenantContext.set_tenant(other.id)

        with patch.object(ReleaseService, "release_element", return_value={}):
            release_element_async(
                str(tenant.id),
                str(workspace.id),
                str(uuid.uuid4()),
                str(user.id),
                "Release",
            )

        assert TenantContext.is_set()

    def test_the_requests_auth_method_is_carried_through(
        self,
        tenant: Tenant,
        user: User,
        workspace: Workspace,
        admin_role: UserRole,
    ) -> None:
        with patch.object(ReleaseService, "release_element") as service:
            service.return_value = {}
            release_element_async(
                str(tenant.id),
                str(workspace.id),
                str(uuid.uuid4()),
                str(user.id),
                "Release",
                auth_method=AuthMethod.BEARER_TOKEN.value,
            )

        assert service.call_args.kwargs["ctx"].auth_method == AuthMethod.BEARER_TOKEN

    def test_an_unknown_auth_method_falls_back_to_bearer(
        self,
        tenant: Tenant,
        user: User,
        workspace: Workspace,
        admin_role: UserRole,
    ) -> None:
        with patch.object(ReleaseService, "release_element") as service:
            service.return_value = {}
            release_element_async(
                str(tenant.id),
                str(workspace.id),
                str(uuid.uuid4()),
                str(user.id),
                "Release",
                auth_method="not-a-method",
            )

        assert service.call_args.kwargs["ctx"].auth_method == AuthMethod.BEARER_TOKEN

    def test_an_api_key_caller_degrades_to_a_bearer_context(
        self,
        tenant: Tenant,
        user: User,
        workspace: Workspace,
        admin_role: UserRole,
    ) -> None:
        """No credential crosses the queue, so ``API_KEY`` is not claimable."""
        with patch.object(ReleaseService, "release_element") as service:
            service.return_value = {}
            release_element_async(
                str(tenant.id),
                str(workspace.id),
                str(uuid.uuid4()),
                str(user.id),
                "Release",
                auth_method=AuthMethod.API_KEY.value,
            )

        ctx = service.call_args.kwargs["ctx"]
        assert ctx.auth_method == AuthMethod.BEARER_TOKEN
        assert ctx.api_key_id is None


class TestWorkerRelease:
    def test_the_task_releases_the_cascade(
        self,
        tenant: Tenant,
        user: User,
        workspace: Workspace,
        admin_role: UserRole,
        tree,
    ) -> None:
        root, child, requirement = tree

        result = release_element_async(
            str(tenant.id),
            str(workspace.id),
            str(root.id),
            str(user.id),
            "Release for milestone M1",
        )

        assert result["release_state"] == "released"
        assert result["elements_released"] == 2
        assert result["requirements_released"] == 1

        with _active(tenant):
            states = dict(
                WorkflowItemState.objects.filter(
                    workspace_id=workspace.id, item_type="ArchitectureElement"
                ).values_list("item_id", "current_state")
            )
            requirement.refresh_from_db()
        assert states == {root.id: "released", child.id: "released"}
        assert requirement.released_tier_key == "L2"

    def test_a_second_run_creates_no_duplicate_content_snapshot(
        self,
        tenant: Tenant,
        user: User,
        workspace: Workspace,
        admin_role: UserRole,
        tree,
    ) -> None:
        root, _child, requirement = tree

        first = release_element_async(
            str(tenant.id), str(workspace.id), str(root.id), str(user.id), "Release"
        )
        second = release_element_async(
            str(tenant.id), str(workspace.id), str(root.id), str(user.id), "Release"
        )

        assert first["content_snapshots"] == 1
        assert second["content_snapshots"] == 0
        assert second["elements_released"] == 0
        assert second["requirements_released"] == 0
        with _active(tenant):
            snapshots = ArtifactVersion.objects.filter(
                artifact=requirement.artifact
            ).count()
        assert snapshots == 1

    def test_a_caller_without_a_release_role_is_refused_in_the_worker(
        self,
        tenant: Tenant,
        user: User,
        workspace: Workspace,
        tree,
    ) -> None:
        """No ``UserRole`` row for the workspace: the rebuilt context has no role."""
        root, _child, _requirement = tree

        with pytest.raises(ValidationError) as excinfo:
            release_element_async(
                str(tenant.id),
                str(workspace.id),
                str(root.id),
                str(user.id),
                "Release",
            )

        assert "approver or admin" in str(excinfo.value)
        # The refusal happened before the first transition.
        with _active(tenant):
            released = WorkflowItemState.objects.filter(
                workspace_id=workspace.id, current_state="released"
            ).exists()
        assert released is False

    def test_an_unexpected_error_surfaces_once_and_is_not_retried(
        self,
        tenant: Tenant,
        user: User,
        workspace: Workspace,
        admin_role: UserRole,
    ) -> None:
        with patch.object(
            ReleaseService, "release_element", side_effect=RuntimeError("boom")
        ) as service:
            with pytest.raises(RuntimeError, match="boom"):
                release_element_async(
                    str(tenant.id),
                    str(workspace.id),
                    str(uuid.uuid4()),
                    str(user.id),
                    "Release",
                )

        # No ``autoretry_for``: one attempt, then Celery records FAILURE — the
        # status route reports it instead of a retry loop hammering the engine.
        assert service.call_count == 1
        assert not TenantContext.is_set()
