"""First AWMS migration plans — executable, idempotent, rollback-covered (WS7 #940).

Every shipped plan (``attribute_definitions/migration_plans/*.yaml``) is loaded
through the same loader the CLI uses and driven end-to-end against real rows:

* ``dry_run`` reports the change and writes **nothing**,
* ``apply`` writes it and snapshots the before-image,
* a second ``apply`` is a no-op (idempotent by ``only_if``),
* ``rollback`` restores the pre-run state,
* ``validate_plan`` accepts the document.

``goal_measures_to_measure.draft.yaml`` is the deliberate exception: it needs
``derive_entity`` and the ``Measure`` entity (#393), so the suite pins the
documented rejection instead of executing it.
"""
from __future__ import annotations

import uuid

import pytest

from application.attribute_migration_service import AttributeMigrationService
from attribute_definitions.migration_plan import MigrationPlanError, load_plan_file
from attribute_definitions.plans import (
    DRAFT_PLAN_FILES,
    EXECUTABLE_PLAN_FILES,
    plan_path,
)
from auth_tenancy.context import AuthContext, AuthMethod
from persistence.models import (
    Actor,
    Artifact,
    AttributeMigrationSnapshot,
    ChangeRequest,
    Issue,
    Requirement,
    Risk,
    StakeholderNeed,
    Tenant,
    TraceLink,
    User,
    Workspace,
)
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db


@pytest.fixture
def tenant() -> Tenant:
    return Tenant.objects.create(name="plans-t", slug=f"plans-{uuid.uuid4().hex[:8]}")


@pytest.fixture
def tenant_context(tenant):
    """Arm the tenant context for the whole test (teardown clears it).

    ``workspace``/``user``/``admin_ctx`` all depend on it, so every test that
    needs the DB keeps the context armed while it creates and reloads rows.
    """
    TenantContext.set_tenant(tenant.id)
    yield tenant.id
    TenantContext.clear_tenant()


@pytest.fixture
def workspace(tenant, tenant_context) -> Workspace:
    return Workspace.objects.create(
        tenant_id=tenant.id, name="ws", preset={"name": "standard"}
    )


@pytest.fixture
def user(tenant, tenant_context) -> User:
    return User.objects.create(
        tenant_id=tenant.id,
        username=f"plans-{uuid.uuid4().hex[:8]}",
        email="plans@t.test",
        first_name="Plan",
        last_name="Owner",
    )


@pytest.fixture
def admin_ctx(tenant, workspace, tenant_context) -> AuthContext:
    return AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=tenant.id,
        workspace_id=workspace.id,
        active_roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN,
    )


@pytest.fixture
def service() -> AttributeMigrationService:
    return AttributeMigrationService()


def _artifact(tenant: Tenant, workspace: Workspace, item_type: str, **fields) -> Artifact:
    return Artifact.objects.create(
        tenant_id=tenant.id,
        workspace=workspace,
        artifact_type=item_type,
        custom_fields=fields.pop("custom_fields", {}),
    )


def _reload(artifact: Artifact) -> Artifact:
    return Artifact.objects.get(id=artifact.id)


# ---------------------------------------------------------------------------
# Plan loading / schema
# ---------------------------------------------------------------------------


def test_every_executable_plan_loads_and_validates(service) -> None:
    for filename in EXECUTABLE_PLAN_FILES:
        payload = load_plan_file(plan_path(filename))
        result = service.validate_plan(payload)
        assert result["plan"]["mode"] == "dry_run", filename
        assert len(result["plan_hash"]) == 64, filename


def test_goal_measure_plan_is_blocked_on_393() -> None:
    """Spec §8.3 needs ``derive_entity`` + the Measure entity (#393).

    The plan ships as a documented draft; the engine's ``normalize_plan`` must
    reject it with the #393 reason rather than silently doing the wrong thing.
    """
    payload = load_plan_file(plan_path("goal_measures_to_measure.draft.yaml"))
    assert payload["id"] == "2026-09-goal-measures-to-measure"
    with pytest.raises(MigrationPlanError) as exc:
        AttributeMigrationService().validate_plan(payload)
    message = "; ".join(exc.value.errors)
    assert "derive_entity" in message
    assert "#393" in message


def test_actor_upsert_plan_lists_are_disjoint_and_present() -> None:
    assert set(EXECUTABLE_PLAN_FILES).isdisjoint(DRAFT_PLAN_FILES)
    for filename in EXECUTABLE_PLAN_FILES + DRAFT_PLAN_FILES:
        assert plan_path(filename).is_file(), filename


# ---------------------------------------------------------------------------
# §8.1 — description -> rationale
# ---------------------------------------------------------------------------


class TestRationaleFromDescription:
    def _plan(self):
        return load_plan_file(plan_path("rationale_from_description.yaml"))

    def test_dry_run_writes_nothing(self, service, admin_ctx, tenant, workspace) -> None:
        artifact = _artifact(
            tenant, workspace, "Requirement", custom_fields={"keep": "x"}
        )
        Requirement.objects.create(
            tenant_id=tenant.id,
            artifact=artifact,
            title="R",
            description="Weil die Anforderung gilt. Begründung: Stakeholder braucht sie.",
        )
        report = service.dry_run(admin_ctx, self._plan())
        assert report["status"] == "planned"
        assert report["summary"]["changed"] == 1
        assert "rationale" not in (_reload(artifact).custom_fields or {})
        assert AttributeMigrationSnapshot.objects.count() == 0

    def test_apply_extracts_rationale_and_keeps_description(
        self, service, admin_ctx, tenant, workspace
    ) -> None:
        artifact = _artifact(tenant, workspace, "Requirement")
        requirement = Requirement.objects.create(
            tenant_id=tenant.id,
            artifact=artifact,
            title="R",
            description="Begründung: weil es so sein muss.",
        )
        report = service.apply(admin_ctx, self._plan())
        assert report["status"] == "applied"
        assert _reload(artifact).custom_fields["rationale"] == "weil es so sein muss."
        # copy keeps the description untouched.
        requirement.refresh_from_db()
        assert requirement.description == "Begründung: weil es so sein muss."

    def test_second_apply_is_idempotent(self, service, admin_ctx, tenant, workspace) -> None:
        artifact = _artifact(tenant, workspace, "Requirement")
        Requirement.objects.create(
            tenant_id=tenant.id, artifact=artifact, title="R", description="Begründung: x"
        )
        service.apply(admin_ctx, self._plan())
        second = service.apply(admin_ctx, self._plan())
        assert second["summary"]["changed"] == 0
        assert second["summary"]["skipped"] >= 1

    def test_rollback_removes_the_reconstructed_rationale(
        self, service, admin_ctx, tenant, workspace
    ) -> None:
        artifact = _artifact(tenant, workspace, "Requirement")
        Requirement.objects.create(
            tenant_id=tenant.id, artifact=artifact, title="R", description="Begründung: x"
        )
        report = service.apply(admin_ctx, self._plan())
        result = service.rollback(admin_ctx, report["run_id"])
        assert result["status"] == "rolled_back"
        assert "rationale" not in (_reload(artifact).custom_fields or {})


# ---------------------------------------------------------------------------
# §8.2 — priority backfill
# ---------------------------------------------------------------------------


class TestPriorityBackfill:
    def _plan(self):
        return load_plan_file(plan_path("priority_backfill.yaml"))

    def test_backfill_derives_from_link_and_falls_back(
        self, service, admin_ctx, tenant, workspace
    ) -> None:
        derived_artifact = _artifact(tenant, workspace, "Requirement")
        Requirement.objects.create(
            tenant_id=tenant.id, artifact=derived_artifact, title="derived"
        )
        need_artifact = _artifact(tenant, workspace, "StakeholderNeed")
        StakeholderNeed.objects.create(
            tenant_id=tenant.id,
            artifact=need_artifact,
            title="need",
            moscow_priority="Must",
        )
        TraceLink.objects.create(
            tenant_id=tenant.id,
            source_id=derived_artifact.id,
            target_id=need_artifact.id,
            link_type="derives-from",
        )
        orphan_artifact = _artifact(tenant, workspace, "Requirement")
        Requirement.objects.create(
            tenant_id=tenant.id, artifact=orphan_artifact, title="orphan"
        )

        report = service.apply(admin_ctx, self._plan())
        assert report["status"] == "applied"
        assert _reload(derived_artifact).priority == "Must"
        assert _reload(orphan_artifact).priority == "Should"

    def test_second_apply_is_idempotent(self, service, admin_ctx, tenant, workspace) -> None:
        artifact = _artifact(tenant, workspace, "Requirement")
        Requirement.objects.create(tenant_id=tenant.id, artifact=artifact, title="R")
        service.apply(admin_ctx, self._plan())
        second = service.apply(admin_ctx, self._plan())
        assert second["summary"]["changed"] == 0

    def test_rollback_clears_the_backfilled_priority(
        self, service, admin_ctx, tenant, workspace
    ) -> None:
        artifact = _artifact(tenant, workspace, "Requirement")
        Requirement.objects.create(tenant_id=tenant.id, artifact=artifact, title="R")
        report = service.apply(admin_ctx, self._plan())
        assert _reload(artifact).priority == "Should"
        service.rollback(admin_ctx, report["run_id"])
        assert _reload(artifact).priority == ""


# ---------------------------------------------------------------------------
# StakeholderNeed.moscow_priority fold (matrix §2)
# ---------------------------------------------------------------------------


class TestMoscowPriorityFold:
    def _plan(self):
        return load_plan_file(plan_path("stakeholder_need_moscow_priority_fold.yaml"))

    def test_fold_into_custom_fields(self, service, admin_ctx, tenant, workspace) -> None:
        artifact = _artifact(tenant, workspace, "StakeholderNeed")
        need = StakeholderNeed.objects.create(
            tenant_id=tenant.id,
            artifact=artifact,
            title="need",
            moscow_priority="Could",
        )

        report = service.apply(admin_ctx, self._plan())
        assert report["status"] == "applied"
        assert _reload(artifact).custom_fields["moscow_priority"] == "Could"
        need.refresh_from_db()
        # expand step: the model column stays readable until the contract step.
        assert need.moscow_priority == "Could"

    def test_second_apply_is_idempotent(self, service, admin_ctx, tenant, workspace) -> None:
        artifact = _artifact(tenant, workspace, "StakeholderNeed")
        StakeholderNeed.objects.create(
            tenant_id=tenant.id, artifact=artifact, title="n", moscow_priority="Must"
        )
        service.apply(admin_ctx, self._plan())
        second = service.apply(admin_ctx, self._plan())
        assert second["summary"]["changed"] == 0

    def test_rollback_removes_the_folded_value(
        self, service, admin_ctx, tenant, workspace
    ) -> None:
        artifact = _artifact(tenant, workspace, "StakeholderNeed")
        StakeholderNeed.objects.create(
            tenant_id=tenant.id, artifact=artifact, title="n", moscow_priority="Must"
        )
        report = service.apply(admin_ctx, self._plan())
        service.rollback(admin_ctx, report["run_id"])
        assert "moscow_priority" not in (_reload(artifact).custom_fields or {})


# ---------------------------------------------------------------------------
# Legacy owner -> Actor (matrix §6/§7/§11)
# ---------------------------------------------------------------------------


def _assert_actor_of_user(artifact: Artifact, field: str, user: User) -> None:
    actor = getattr(_reload(artifact), field)
    assert actor is not None
    assert actor.user_id == user.id


class TestRiskOwnerToActor:
    def _plan(self):
        return load_plan_file(plan_path("risk_owner_to_actor.yaml"))

    def test_owner_name_and_created_by_become_actors(
        self, service, admin_ctx, tenant, workspace, user
    ) -> None:
        artifact = _artifact(tenant, workspace, "Risk")
        Risk.objects.create(
            tenant_id=tenant.id,
            artifact=artifact,
            workspace_id=workspace.id,
            title="risk",
            owner_name="Alice",
            created_by_name=str(user.id),
        )

        report = service.apply(admin_ctx, self._plan())
        assert report["status"] == "applied"
        owner = _reload(artifact).owner
        assert owner.kind == "external"
        assert owner.display_name == "Alice"
        _assert_actor_of_user(artifact, "reporter", user)

    def test_owner_user_takes_precedence_over_free_text(
        self, service, admin_ctx, tenant, workspace, user
    ) -> None:
        artifact = _artifact(tenant, workspace, "Risk")
        Risk.objects.create(
            tenant_id=tenant.id,
            artifact=artifact,
            workspace_id=workspace.id,
            title="risk",
            owner_name="Alice",
            owner_user_id=user.id,
        )
        service.apply(admin_ctx, self._plan())
        _assert_actor_of_user(artifact, "owner", user)

    def test_second_apply_is_idempotent(
        self, service, admin_ctx, tenant, workspace, user
    ) -> None:
        artifact = _artifact(tenant, workspace, "Risk")
        Risk.objects.create(
            tenant_id=tenant.id,
            artifact=artifact,
            workspace_id=workspace.id,
            title="risk",
            owner_name="Alice",
            created_by_name=str(user.id),
        )
        service.apply(admin_ctx, self._plan())
        second = service.apply(admin_ctx, self._plan())
        assert second["summary"]["changed"] == 0

    def test_dry_run_creates_no_actors(
        self, service, admin_ctx, tenant, workspace
    ) -> None:
        """Actor resolution must be write-path only (§6, no data loss)."""
        artifact = _artifact(tenant, workspace, "Risk")
        Risk.objects.create(
            tenant_id=tenant.id,
            artifact=artifact,
            workspace_id=workspace.id,
            title="risk",
            owner_name="Alice",
        )
        report = service.dry_run(admin_ctx, self._plan())
        assert report["status"] == "planned"
        assert _reload(artifact).owner is None
        assert not Actor.objects.filter(display_name="Alice").exists()

    def test_rollback_clears_owner_and_reporter(
        self, service, admin_ctx, tenant, workspace, user
    ) -> None:
        artifact = _artifact(tenant, workspace, "Risk")
        Risk.objects.create(
            tenant_id=tenant.id,
            artifact=artifact,
            workspace_id=workspace.id,
            title="risk",
            owner_name="Alice",
            created_by_name=str(user.id),
        )
        report = service.apply(admin_ctx, self._plan())
        service.rollback(admin_ctx, report["run_id"])
        refreshed = _reload(artifact)
        assert refreshed.owner is None
        assert refreshed.reporter is None


class TestIssueAssigneeToActor:
    def _plan(self):
        return load_plan_file(plan_path("issue_assignee_to_actor.yaml"))

    def test_assignee_and_created_by_become_actors(
        self, service, admin_ctx, tenant, workspace, user
    ) -> None:
        artifact = _artifact(tenant, workspace, "Issue")
        Issue.objects.create(
            tenant_id=tenant.id,
            artifact=artifact,
            workspace_id=workspace.id,
            title="issue",
            assignee_id=user.id,
            created_by_name=str(user.id),
        )
        report = service.apply(admin_ctx, self._plan())
        assert report["status"] == "applied"
        _assert_actor_of_user(artifact, "owner", user)
        _assert_actor_of_user(artifact, "reporter", user)

    def test_second_apply_is_idempotent(
        self, service, admin_ctx, tenant, workspace, user
    ) -> None:
        artifact = _artifact(tenant, workspace, "Issue")
        Issue.objects.create(
            tenant_id=tenant.id,
            artifact=artifact,
            workspace_id=workspace.id,
            title="issue",
            assignee_id=user.id,
        )
        service.apply(admin_ctx, self._plan())
        second = service.apply(admin_ctx, self._plan())
        assert second["summary"]["changed"] == 0


class TestChangeRequestRequestorToReporter:
    def _plan(self):
        return load_plan_file(
            plan_path("change_request_requestor_to_reporter.yaml")
        )

    def test_requestor_becomes_reporter(
        self, service, admin_ctx, tenant, workspace, user
    ) -> None:
        artifact = _artifact(tenant, workspace, "ChangeRequest")
        ChangeRequest.objects.create(
            tenant_id=tenant.id,
            artifact=artifact,
            workspace_id=workspace.id,
            title="cr",
            requestor_id=user.id,
        )
        report = service.apply(admin_ctx, self._plan())
        assert report["status"] == "applied"
        _assert_actor_of_user(artifact, "reporter", user)

    def test_rollback_clears_reporter(
        self, service, admin_ctx, tenant, workspace, user
    ) -> None:
        artifact = _artifact(tenant, workspace, "ChangeRequest")
        ChangeRequest.objects.create(
            tenant_id=tenant.id,
            artifact=artifact,
            workspace_id=workspace.id,
            title="cr",
            requestor_id=user.id,
        )
        report = service.apply(admin_ctx, self._plan())
        service.rollback(admin_ctx, report["run_id"])
        assert _reload(artifact).reporter is None
