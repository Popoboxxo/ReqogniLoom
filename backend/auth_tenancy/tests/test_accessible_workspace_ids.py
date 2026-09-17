import pytest

from auth_tenancy.services.authorization import AuthorizationService
from persistence.tests.factories import active_tenant, make_user, make_workspace, assign_role


@pytest.mark.django_db
class TestAccessibleWorkspaceIds:
    def test_returns_only_workspaces_user_has_a_role_in(self):
        with active_tenant() as tenant:
            user = make_user(tenant)
            ws_a = make_workspace(tenant)
            ws_b = make_workspace(tenant)
            ws_c = make_workspace(tenant)  # user has no role here
            assign_role(user, ws_a, "editor")
            assign_role(user, ws_b, "viewer")

            result = AuthorizationService().accessible_workspace_ids(user_id=user.id, tenant_id=tenant.id)

            assert set(result) == {ws_a.id, ws_b.id}
            assert ws_c.id not in result

    def test_excludes_suspended_roles(self):
        with active_tenant() as tenant:
            user = make_user(tenant)
            ws = make_workspace(tenant)
            assign_role(user, ws, "editor", suspended=True)
            result = AuthorizationService().accessible_workspace_ids(user_id=user.id, tenant_id=tenant.id)
            assert ws.id not in result
