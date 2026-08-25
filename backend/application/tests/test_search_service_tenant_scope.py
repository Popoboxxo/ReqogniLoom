import pytest

from application.search_service import SearchService
from persistence.tests.factories import (
    active_tenant,
    assign_role,
    ctx_for_user,
    editor_ctx,
    make_requirement,
    make_user,
    make_workspace,
)


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

    def test_one_workspace_failure_does_not_drop_sibling_workspace_hits(self, monkeypatch):
        """A query failure for one accessible workspace must only drop that
        workspace's own contribution, not the results of the OTHER accessible
        workspaces for the same entity type (review-round fix: the original
        list-comprehension implementation aborted the whole per-type batch on
        the first exception).
        """
        with active_tenant() as tenant:
            user = make_user(tenant)
            ws_a = make_workspace(tenant)
            ws_b = make_workspace(tenant)  # the "middle" workspace: made to fail below
            ws_c = make_workspace(tenant)
            assign_role(user, ws_a, "editor")
            assign_role(user, ws_b, "editor")
            assign_role(user, ws_c, "editor")
            make_requirement(ws_a, title="Findable requirement A")
            make_requirement(ws_b, title="Findable requirement B")
            make_requirement(ws_c, title="Findable requirement C")

            ctx = ctx_for_user(tenant, user, workspace=None, roles=())
            # ctx_for_user with workspace=None persists no extra UserRole row
            # (the three assign_role() calls above already cover ws_a/b/c);
            # only the in-memory AuthContext is needed here.

            original_search_entity_type = SearchService._search_entity_type

            def flaky_search_entity_type(entity_type, tsquery_str, tenant_id, workspace_id, raw_query=""):
                if entity_type == "Requirement" and workspace_id == ws_b.id:
                    raise RuntimeError("simulated failure for the middle workspace")
                return original_search_entity_type(
                    entity_type=entity_type,
                    tsquery_str=tsquery_str,
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    raw_query=raw_query,
                )

            monkeypatch.setattr(
                SearchService, "_search_entity_type", staticmethod(flaky_search_entity_type)
            )

            result = SearchService().search(
                "Findable", ctx, scope="tenant", type_filter=["Requirement"]
            )

            titles = {hit.title for hit in result.results}
            assert "Findable requirement A" in titles
            assert "Findable requirement C" in titles
            assert "Findable requirement B" not in titles
