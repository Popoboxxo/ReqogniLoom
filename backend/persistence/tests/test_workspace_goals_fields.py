from django.test import TestCase

from persistence.models import PROMPT_TEMPLATE_DEFAULTS, Tenant, Workspace
from persistence.tenancy import TenantContext


class WorkspaceGoalsFieldsTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="T1")
        TenantContext.set_tenant(self.tenant.id)

    def tearDown(self):
        TenantContext.clear_tenant()

    def test_workspace_goals_fields_default(self):
        """#402 (cluster 5, spec D2): ``goals_enabled`` now defaults to True.

        ``goals_ai_enabled`` deliberately stays False — flipping it would mean
        unannounced LLM generation on tenant provisioning. The flag gates only
        additive write-CRUD (GoalService/MainGoalService + the goal REST
        endpoints), so enabling it by default activates a purely additive
        capability; ``VAL-P1`` stays advisory and is additionally gated on the
        existence of at least one Goal.
        """
        workspace = Workspace.objects.create(tenant=self.tenant, name="W1")
        self.assertTrue(workspace.goals_enabled)
        self.assertFalse(workspace.goals_ai_enabled)

    def test_workspace_goals_enabled_can_still_be_disabled(self):
        workspace = Workspace.objects.create(
            tenant=self.tenant, name="W2", goals_enabled=False
        )
        self.assertFalse(workspace.goals_enabled)

    def test_goal_aggregate_prompt_default_exists(self):
        self.assertIn("goal_aggregate", PROMPT_TEMPLATE_DEFAULTS)
        self.assertIsInstance(PROMPT_TEMPLATE_DEFAULTS["goal_aggregate"], str)
        self.assertGreater(len(PROMPT_TEMPLATE_DEFAULTS["goal_aggregate"]), 0)
