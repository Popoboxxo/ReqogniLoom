import uuid
from unittest.mock import MagicMock

from django.test import TestCase

from application.base import ValidationError
from application.goal_service import GoalService
from application.models import Goal, MainGoal
from persistence.models import Artifact, Tenant, Workspace
from persistence.tenancy import TenantContext


def _make_ctx(*, tenant_id, roles=("editor",), user_id=None):
    """Build a lightweight AuthContext-compatible ctx for GoalService tests.

    Mirrors backend/application/tests/test_risk_service.py's ``_make_ctx``
    helper (MagicMock with the AuthContext attributes ServiceBase reads:
    ``tenant_id``, ``user_id``, ``active_roles``, ``has_role``).
    """
    ctx = MagicMock()
    ctx.tenant_id = tenant_id
    ctx.user_id = user_id or uuid.uuid4()
    ctx.active_roles = roles
    ctx.has_role = lambda role: role in roles
    return ctx


class GoalModelTests(TestCase):
    """Test Goal model."""

    def setUp(self):
        """Set up test fixtures with TenantContext."""
        self.tenant = Tenant.objects.create(name="T1")
        TenantContext.set_tenant(self.tenant.id)
        self.workspace = Workspace.objects.create(tenant=self.tenant, name="W1")

    def tearDown(self):
        """Clean up TenantContext after each test."""
        TenantContext.clear_tenant()

    def test_goal_model_creates_dedicated_artifact(self):
        artifact = Artifact.objects.create(
            tenant=self.tenant, workspace=self.workspace, artifact_type="Goal"
        )
        lineage_id = uuid.uuid4()
        goal = Goal.objects.create(
            artifact=artifact,
            tenant_id=self.tenant.id,
            workspace_id=self.workspace.id,
            lineage_id=lineage_id,
            sequence_number=1,
            title="Reduce onboarding time",
            description="Cut onboarding from 5 days to 2 days.",
            status="Entwurf",
        )
        self.assertEqual(goal.artifact_id, artifact.id)
        self.assertEqual(goal.lineage_id, lineage_id)
        self.assertEqual(goal.sequence_number, 1)


class MainGoalModelTests(TestCase):
    """Test MainGoal model."""

    def setUp(self):
        """Set up test fixtures with TenantContext."""
        self.tenant = Tenant.objects.create(name="T1")
        TenantContext.set_tenant(self.tenant.id)
        self.workspace = Workspace.objects.create(tenant=self.tenant, name="W1")

    def tearDown(self):
        """Clean up TenantContext after each test."""
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
            source="ai",
            generated_from_goal_ids=[],
            status="Entwurf",
        )
        self.assertEqual(main_goal.artifact_id, artifact.id)
        self.assertEqual(main_goal.source, "ai")


class GoalServiceTests(TestCase):
    """Test GoalService — lineage-based versioning and the goals_enabled gate."""

    def setUp(self):
        """Set up test fixtures with TenantContext."""
        self.tenant = Tenant.objects.create(name="T1")
        TenantContext.set_tenant(self.tenant.id)

    def tearDown(self):
        """Clean up TenantContext after each test."""
        TenantContext.clear_tenant()

    def test_create_version_raises_when_goals_disabled(self):
        """Workspace.goals_enabled defaults to False; create_version must reject it."""
        workspace = Workspace.objects.create(tenant=self.tenant, name="W-disabled")
        ctx = _make_ctx(tenant_id=self.tenant.id)

        with self.assertRaises(ValidationError):
            GoalService().create_version(
                workspace_id=workspace.id,
                title="Reduce onboarding time",
                description="Cut onboarding from 5 days to 2 days.",
                lineage_id=None,
                ctx=ctx,
            )

    def test_create_version_creates_goal_with_dedicated_artifact(self):
        workspace = Workspace.objects.create(
            tenant=self.tenant, name="W-enabled", goals_enabled=True
        )
        ctx = _make_ctx(tenant_id=self.tenant.id)

        result = GoalService().create_version(
            workspace_id=workspace.id,
            title="Reduce onboarding time",
            description="Cut onboarding from 5 days to 2 days.",
            lineage_id=None,
            ctx=ctx,
        )

        self.assertEqual(result["sequence_number"], 1)
        self.assertEqual(result["status"], "Entwurf")

        goal = Goal.objects.get(id=result["id"])
        self.assertIsNotNone(goal.artifact_id)
        self.assertEqual(str(goal.lineage_id), result["lineage_id"])

    def test_create_version_reuses_lineage_and_increments_sequence(self):
        workspace = Workspace.objects.create(
            tenant=self.tenant, name="W-enabled-2", goals_enabled=True
        )
        ctx = _make_ctx(tenant_id=self.tenant.id)
        svc = GoalService()

        first = svc.create_version(
            workspace_id=workspace.id,
            title="Goal A",
            description="",
            lineage_id=None,
            ctx=ctx,
        )
        second = svc.create_version(
            workspace_id=workspace.id,
            title="Goal A revised",
            description="",
            lineage_id=uuid.UUID(first["lineage_id"]),
            ctx=ctx,
        )

        self.assertEqual(second["lineage_id"], first["lineage_id"])
        self.assertEqual(second["sequence_number"], 2)
        # Both versions persist as separate rows (immutable-row-per-version).
        self.assertEqual(
            Goal.objects.filter(lineage_id=uuid.UUID(first["lineage_id"])).count(), 2
        )

    def test_list_versions_returns_all_versions_for_lineage(self):
        workspace = Workspace.objects.create(
            tenant=self.tenant, name="W-enabled-3", goals_enabled=True
        )
        ctx = _make_ctx(tenant_id=self.tenant.id)
        svc = GoalService()

        first = svc.create_version(
            workspace_id=workspace.id,
            title="Goal A",
            description="",
            lineage_id=None,
            ctx=ctx,
        )
        svc.create_version(
            workspace_id=workspace.id,
            title="Goal A revised",
            description="",
            lineage_id=uuid.UUID(first["lineage_id"]),
            ctx=ctx,
        )

        versions = svc.list_versions(
            lineage_id=uuid.UUID(first["lineage_id"]), ctx=ctx
        )
        self.assertEqual([v["sequence_number"] for v in versions], [1, 2])
        self.assertEqual(versions[0]["label"], "v1")
        self.assertEqual(versions[1]["label"], "v2")

    def test_list_current_returns_latest_version_per_lineage(self):
        workspace = Workspace.objects.create(
            tenant=self.tenant, name="W-enabled-4", goals_enabled=True
        )
        ctx = _make_ctx(tenant_id=self.tenant.id)
        svc = GoalService()

        first = svc.create_version(
            workspace_id=workspace.id,
            title="Goal A",
            description="",
            lineage_id=None,
            ctx=ctx,
        )
        svc.create_version(
            workspace_id=workspace.id,
            title="Goal A revised",
            description="",
            lineage_id=uuid.UUID(first["lineage_id"]),
            ctx=ctx,
        )
        svc.create_version(
            workspace_id=workspace.id,
            title="Goal B",
            description="",
            lineage_id=None,
            ctx=ctx,
        )

        current = svc.list_current(workspace_id=workspace.id, ctx=ctx)
        titles = sorted(g.title for g in current)
        self.assertEqual(titles, ["Goal A revised", "Goal B"])

    def test_get_returns_single_goal_version(self):
        workspace = Workspace.objects.create(
            tenant=self.tenant, name="W-enabled-5", goals_enabled=True
        )
        ctx = _make_ctx(tenant_id=self.tenant.id)
        svc = GoalService()

        created = svc.create_version(
            workspace_id=workspace.id,
            title="Goal A",
            description="",
            lineage_id=None,
            ctx=ctx,
        )

        goal = svc.get(uuid.UUID(created["id"]), ctx=ctx)
        self.assertEqual(str(goal.id), created["id"])
        self.assertEqual(goal.title, "Goal A")
