import pytest

from application.search_service import SearchService
from persistence.tests.factories import active_tenant, make_requirement, make_user, make_workspace, editor_ctx


@pytest.mark.django_db
class TestSearchServiceTenantScope:
    def test_tenant_scope_only_returns_accessible_workspaces(self):
        with active_tenant() as tenant:
            user = make_user(tenant)
            ws_a = make_workspace(tenant)
            ws_b = make_workspace(tenant)  # no access
            make_requirement(ws_a, title="Findable requirement A")
            make_requirement(ws_b, title="Findable requirement B")

            # editor_ctx() assigns the "editor" role on ws_a itself; an
            # additional explicit assign_role() call here would duplicate it
            # and violate the (workspace, user, role) unique constraint.
            ctx = editor_ctx(tenant, ws_a, user=user)
            result = SearchService().search("Findable", ctx, scope="tenant")

            titles = {hit.title for hit in result.results}
            assert "Findable requirement A" in titles
            assert "Findable requirement B" not in titles

    def test_workspace_scope_is_unchanged_default(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            make_requirement(ws, title="Scoped requirement")
            ctx = editor_ctx(tenant, ws)
            result = SearchService().search("Scoped", ctx, workspace_id=ws.id)
            assert len(result.results) == 1
