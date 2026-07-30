from django.test import TestCase

from persistence.models import PROMPT_TEMPLATE_DEFAULTS, Tenant, Workspace
from persistence.tenancy import TenantContext


class WorkspaceGoalsFieldsTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="T1")
        TenantContext.set_tenant(self.tenant.id)

    def tearDown(self):
        TenantContext.clear_tenant()

    def test_workspace_goals_fields_default_false(self):
        workspace = Workspace.objects.create(tenant=self.tenant, name="W1")
        self.assertFalse(workspace.goals_enabled)
        self.assertFalse(workspace.goals_ai_enabled)

    def test_goal_aggregate_prompt_default_exists(self):
        self.assertIn("goal_aggregate", PROMPT_TEMPLATE_DEFAULTS)
        self.assertIsInstance(PROMPT_TEMPLATE_DEFAULTS["goal_aggregate"], str)
        self.assertGreater(len(PROMPT_TEMPLATE_DEFAULTS["goal_aggregate"]), 0)
