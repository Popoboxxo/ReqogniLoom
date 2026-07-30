import uuid
from django.test import TestCase

from application.models import Goal, MainGoal
from persistence.models import Artifact, Tenant, Workspace


class GoalModelTests(TestCase):
    """Test Goal model."""

    def test_goal_model_creates_dedicated_artifact(self):
        tenant = Tenant.objects.create(name="T1")
        workspace = Workspace.objects.create(tenant=tenant, name="W1")
        artifact = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="Goal"
        )
        lineage_id = uuid.uuid4()
        goal = Goal.objects.create(
            artifact=artifact,
            tenant_id=tenant.id,
            workspace_id=workspace.id,
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

    def test_main_goal_model_creates_dedicated_artifact(self):
        tenant = Tenant.objects.create(name="T1")
        workspace = Workspace.objects.create(tenant=tenant, name="W1")
        artifact = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="MainGoal"
        )
        main_goal = MainGoal.objects.create(
            artifact=artifact,
            tenant_id=tenant.id,
            workspace_id=workspace.id,
            sequence_number=1,
            content="Become the market leader in onboarding speed within 12 months.",
            source="ai",
            generated_from_goal_ids=[],
            status="Entwurf",
        )
        self.assertEqual(main_goal.artifact_id, artifact.id)
        self.assertEqual(main_goal.source, "ai")
