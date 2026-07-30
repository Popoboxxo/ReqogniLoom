import uuid
from unittest.mock import MagicMock

from django.test import TestCase

from application.base import NotFoundError, ValidationError
from application.goal_service import GoalService
from application.main_goal_service import MainGoalService
from application.models import MainGoal
from persistence.models import Artifact, Tenant, Workspace
from persistence.tenancy import TenantContext


def _make_ctx(*, tenant_id, roles=("editor",), user_id=None):
    """Build a lightweight AuthContext-compatible ctx for MainGoalService tests.

    Mirrors backend/application/tests/test_goal_service.py's ``_make_ctx``
    helper (MagicMock with the AuthContext attributes ServiceBase reads:
    ``tenant_id``, ``user_id``, ``active_roles``, ``has_role``).
    """
    ctx = MagicMock()
    ctx.tenant_id = tenant_id
    ctx.user_id = user_id or uuid.uuid4()
    ctx.active_roles = roles
    ctx.has_role = lambda role: role in roles
    return ctx


def _provision_main_goal_workflow(workspace):
    """Create a real WorkflowEngineDefinition for MainGoal on *workspace*.

    Mirrors test_risk_service.py's ``risk`` fixture: the ``main_goal_default``
    preset is backfilled for *pre-existing* workspaces by migration 0012, but
    workspaces created ad hoc in tests (bypassing
    ``application.workspace_provisioning.provision_workspace_defaults``, which
    does not include Goal/MainGoal) need it created explicitly, otherwise
    ``approve``'s WorkflowEngine call has no WorkflowItemState to transition.
    """
    from workflow.services import create_default_workflow

    TenantContext.set_tenant(workspace.tenant_id)
    try:
        create_default_workflow(
            workspace_id=workspace.id,
            preset="main_goal_default",
            item_type="MainGoal",
            tenant_id=workspace.tenant_id,
        )
    finally:
        TenantContext.clear_tenant()


class MainGoalModelTests(TestCase):
    """Test MainGoal model (sanity, mirrors test_goal_service.py)."""

    def setUp(self):
        self.tenant = Tenant.objects.create(name="T1")
        TenantContext.set_tenant(self.tenant.id)
        self.workspace = Workspace.objects.create(tenant=self.tenant, name="W1")

    def tearDown(self):
        TenantContext.clear_tenant()

    def test_main_goal_model_creates_dedicated_artifact(self):
        artifact = Artifact.objects.create(
            tenant=self.tenant, workspace=self.workspace, artifact_type="MainGoal"
        )
        main_goal = MainGoal.objects.create(
            artifact=artifact,
            tenant_id=self.tenant.id,
            workspace_id=self.workspace.id,
            sequence_number=1,
            content="Become the market leader in onboarding speed within 12 months.",
            source="manual",
            generated_from_goal_ids=[],
            status="Entwurf",
        )
        self.assertEqual(main_goal.artifact_id, artifact.id)
        self.assertEqual(main_goal.source, "manual")


class MainGoalServiceCreateManualTests(TestCase):
    """Test MainGoalService.create_manual and the goals_enabled gate."""

    def setUp(self):
        self.tenant = Tenant.objects.create(name="T1")
        TenantContext.set_tenant(self.tenant.id)

    def tearDown(self):
        TenantContext.clear_tenant()

    def test_create_manual_raises_when_goals_disabled(self):
        """Workspace.goals_enabled defaults to False; create_manual must reject it."""
        workspace = Workspace.objects.create(tenant=self.tenant, name="W-disabled")
        ctx = _make_ctx(tenant_id=self.tenant.id)

        with self.assertRaises(ValidationError):
            MainGoalService().create_manual(
                workspace_id=workspace.id,
                content="Manually authored main goal.",
                ctx=ctx,
            )

    def test_create_manual_creates_main_goal_in_entwurf(self):
        workspace = Workspace.objects.create(
            tenant=self.tenant, name="W-enabled", goals_enabled=True
        )
        ctx = _make_ctx(tenant_id=self.tenant.id)

        result = MainGoalService().create_manual(
            workspace_id=workspace.id,
            content="Manually authored main goal.",
            ctx=ctx,
        )

        self.assertEqual(result["source"], "manual")
        self.assertEqual(result["status"], "Entwurf")
        self.assertEqual(result["sequence_number"], 1)

        main_goal = MainGoal.objects.get(id=result["id"])
        self.assertIsNotNone(main_goal.artifact_id)
        self.assertEqual(main_goal.content, "Manually authored main goal.")

    def test_create_manual_increments_sequence_number(self):
        workspace = Workspace.objects.create(
            tenant=self.tenant, name="W-enabled-2", goals_enabled=True
        )
        ctx = _make_ctx(tenant_id=self.tenant.id)
        svc = MainGoalService()

        first = svc.create_manual(
            workspace_id=workspace.id, content="Draft v1.", ctx=ctx
        )
        second = svc.create_manual(
            workspace_id=workspace.id, content="Draft v2.", ctx=ctx
        )

        self.assertEqual(first["sequence_number"], 1)
        self.assertEqual(second["sequence_number"], 2)
        self.assertEqual(
            MainGoal.objects.filter(workspace_id=workspace.id).count(), 2
        )

    def test_create_manual_raises_when_content_empty(self):
        workspace = Workspace.objects.create(
            tenant=self.tenant, name="W-enabled-3", goals_enabled=True
        )
        ctx = _make_ctx(tenant_id=self.tenant.id)

        with self.assertRaises(ValidationError):
            MainGoalService().create_manual(
                workspace_id=workspace.id, content="", ctx=ctx
            )


class MainGoalServiceGenerateAiTests(TestCase):
    """Test MainGoalService.generate_ai and the goals_enabled/goals_ai_enabled gates."""

    def setUp(self):
        self.tenant = Tenant.objects.create(name="T1")
        TenantContext.set_tenant(self.tenant.id)

    def tearDown(self):
        TenantContext.clear_tenant()

    def test_generate_ai_raises_when_goals_disabled(self):
        """goals_enabled=False must block AI generation even if goals_ai_enabled=True."""
        workspace = Workspace.objects.create(
            tenant=self.tenant,
            name="W-goals-disabled",
            goals_enabled=False,
            goals_ai_enabled=True,
        )
        ctx = _make_ctx(tenant_id=self.tenant.id)

        with self.assertRaises(ValidationError):
            MainGoalService().generate_ai(workspace_id=workspace.id, ctx=ctx)

    def test_generate_ai_raises_when_ai_disabled(self):
        workspace = Workspace.objects.create(
            tenant=self.tenant,
            name="W-ai-disabled",
            goals_enabled=True,
            goals_ai_enabled=False,
        )
        ctx = _make_ctx(tenant_id=self.tenant.id)

        with self.assertRaisesMessage(ValidationError, "AI generation is disabled"):
            MainGoalService().generate_ai(workspace_id=workspace.id, ctx=ctx)

    def test_generate_ai_raises_when_no_goals_exist(self):
        workspace = Workspace.objects.create(
            tenant=self.tenant,
            name="W-no-goals",
            goals_enabled=True,
            goals_ai_enabled=True,
        )
        ctx = _make_ctx(tenant_id=self.tenant.id)

        with self.assertRaises(ValidationError):
            MainGoalService().generate_ai(workspace_id=workspace.id, ctx=ctx)

    def test_generate_ai_aggregates_current_goals_into_main_goal(self):
        workspace = Workspace.objects.create(
            tenant=self.tenant,
            name="W-ai-enabled",
            goals_enabled=True,
            goals_ai_enabled=True,
        )
        ctx = _make_ctx(tenant_id=self.tenant.id)

        goal = GoalService().create_version(
            workspace_id=workspace.id,
            title="Reduce onboarding time",
            description="Cut onboarding from 5 days to 2 days.",
            lineage_id=None,
            ctx=ctx,
        )

        result = MainGoalService().generate_ai(workspace_id=workspace.id, ctx=ctx)

        self.assertEqual(result["source"], "ai")
        self.assertEqual(result["status"], "Entwurf")
        self.assertEqual(result["generated_from_goal_ids"], [goal["id"]])
        self.assertTrue(result["content"])

        main_goal = MainGoal.objects.get(id=result["id"])
        self.assertEqual(main_goal.source, "ai")
        self.assertEqual(main_goal.generated_from_goal_ids, [goal["id"]])


class MainGoalServiceApproveTests(TestCase):
    """Test MainGoalService.approve — must go through the WorkflowEngine."""

    def setUp(self):
        self.tenant = Tenant.objects.create(name="T1")
        TenantContext.set_tenant(self.tenant.id)

    def tearDown(self):
        TenantContext.clear_tenant()

    def test_approve_transitions_to_freigegeben_and_becomes_current(self):
        workspace = Workspace.objects.create(
            tenant=self.tenant, name="W-approve", goals_enabled=True
        )
        _provision_main_goal_workflow(workspace)
        editor_ctx = _make_ctx(tenant_id=self.tenant.id, roles=("editor",))
        approver_ctx = _make_ctx(tenant_id=self.tenant.id, roles=("approver",))
        svc = MainGoalService()

        created = svc.create_manual(
            workspace_id=workspace.id, content="Draft main goal.", ctx=editor_ctx
        )
        approved = svc.approve(
            uuid.UUID(created["id"]),
            approver_ctx,
            change_reason="Reviewed and approved.",
        )

        self.assertEqual(approved["status"], "Freigegeben")

        current = svc.get_current(workspace.id, approver_ctx)
        self.assertIsNotNone(current)
        self.assertEqual(str(current.id), created["id"])

    def test_approve_rejects_role_without_approver_permission(self):
        """The main_goal_default preset gates Entwurf->Freigegeben to approver/admin.

        The WorkflowEngine's TransitionValidator rejects the role with
        ``EC_ROLE_NOT_ALLOWED``; ``WorkflowFacade._remap_workflow_exc`` maps
        that (alongside every other transition rejection) to
        ``application.base.ValidationError`` — verified against real test
        output rather than assumed from the brief.
        """
        workspace = Workspace.objects.create(
            tenant=self.tenant, name="W-approve-denied", goals_enabled=True
        )
        _provision_main_goal_workflow(workspace)
        editor_ctx = _make_ctx(tenant_id=self.tenant.id, roles=("editor",))
        svc = MainGoalService()

        created = svc.create_manual(
            workspace_id=workspace.id, content="Draft main goal.", ctx=editor_ctx
        )

        with self.assertRaises(ValidationError):
            svc.approve(
                uuid.UUID(created["id"]),
                editor_ctx,
                change_reason="Trying without approver role.",
            )

    def test_approve_raises_not_found_for_unknown_id(self):
        workspace = Workspace.objects.create(
            tenant=self.tenant, name="W-approve-404", goals_enabled=True
        )
        _provision_main_goal_workflow(workspace)
        ctx = _make_ctx(tenant_id=self.tenant.id, roles=("approver",))

        with self.assertRaises(NotFoundError):
            MainGoalService().approve(uuid.uuid4(), ctx, change_reason="n/a")

    def test_approve_uses_real_workflow_engine_not_raw_field_write(self):
        """Approving without a provisioned WorkflowEngineDefinition must fail hard.

        A raw ``main_goal.status = "Freigegeben"; main_goal.save(...)`` would
        succeed unconditionally regardless of workflow configuration; going
        through the real WorkflowEngine (WorkflowStateError when no
        WorkflowItemState/definition exists) must instead raise.
        """
        workspace = Workspace.objects.create(
            tenant=self.tenant, name="W-no-workflow", goals_enabled=True
        )
        # Intentionally NOT calling _provision_main_goal_workflow(workspace).
        editor_ctx = _make_ctx(tenant_id=self.tenant.id, roles=("editor",))
        approver_ctx = _make_ctx(tenant_id=self.tenant.id, roles=("approver",))
        svc = MainGoalService()

        created = svc.create_manual(
            workspace_id=workspace.id, content="Draft main goal.", ctx=editor_ctx
        )

        with self.assertRaises(Exception):
            svc.approve(
                uuid.UUID(created["id"]),
                approver_ctx,
                change_reason="No workflow provisioned.",
            )

        main_goal = MainGoal.objects.get(id=created["id"])
        self.assertEqual(main_goal.status, "Entwurf")


class MainGoalServiceReadTests(TestCase):
    """Test MainGoalService.get_current and list_versions."""

    def setUp(self):
        self.tenant = Tenant.objects.create(name="T1")
        TenantContext.set_tenant(self.tenant.id)

    def tearDown(self):
        TenantContext.clear_tenant()

    def test_get_current_returns_none_when_never_approved(self):
        workspace = Workspace.objects.create(
            tenant=self.tenant, name="W-never-approved", goals_enabled=True
        )
        ctx = _make_ctx(tenant_id=self.tenant.id)
        svc = MainGoalService()

        svc.create_manual(workspace_id=workspace.id, content="Draft only.", ctx=ctx)

        self.assertIsNone(svc.get_current(workspace.id, ctx))

    def test_get_current_returns_newest_freigegeben_row(self):
        workspace = Workspace.objects.create(
            tenant=self.tenant, name="W-versions", goals_enabled=True
        )
        _provision_main_goal_workflow(workspace)
        editor_ctx = _make_ctx(tenant_id=self.tenant.id, roles=("editor",))
        approver_ctx = _make_ctx(tenant_id=self.tenant.id, roles=("approver",))
        svc = MainGoalService()

        first = svc.create_manual(
            workspace_id=workspace.id, content="Draft v1.", ctx=editor_ctx
        )
        svc.approve(uuid.UUID(first["id"]), approver_ctx, change_reason="v1 approved.")

        second = svc.create_manual(
            workspace_id=workspace.id, content="Draft v2.", ctx=editor_ctx
        )
        svc.approve(uuid.UUID(second["id"]), approver_ctx, change_reason="v2 approved.")

        current = svc.get_current(workspace.id, approver_ctx)
        self.assertEqual(str(current.id), second["id"])

    def test_list_versions_returns_all_versions_ordered(self):
        workspace = Workspace.objects.create(
            tenant=self.tenant, name="W-list-versions", goals_enabled=True
        )
        ctx = _make_ctx(tenant_id=self.tenant.id)
        svc = MainGoalService()

        svc.create_manual(workspace_id=workspace.id, content="Draft v1.", ctx=ctx)
        svc.create_manual(workspace_id=workspace.id, content="Draft v2.", ctx=ctx)

        versions = svc.list_versions(workspace.id, ctx)

        self.assertEqual([v["sequence_number"] for v in versions], [1, 2])
        self.assertEqual(versions[0]["label"], "v1")
        self.assertEqual(versions[1]["label"], "v2")
