"""
ARCH-L1-006 BaselineService — Tests for the Scope-Select preview feature.

leaf_id: COMP-BL-005 (ScopePreviewService)
req_id:  REQ-L1-049 (Baseline scope-select with 3 scopes)

Covers:
  - preview_scope_items() returns ScopePreview with count + sample
  - project / global / document scope filtering semantics
  - Document scope requires artifact_id; missing → ValueError
  - Sample is capped at 10 items, each with id/title/type
  - scope_preview endpoint requires workspace_id and scope
  - scope_preview endpoint returns JSON-serializable response

REQ-L1-049 — Baseline-Scope-Select (Phase 4 of the fix sprint).
"""
from __future__ import annotations

import uuid

import pytest
from django.test import RequestFactory

# ---------------------------------------------------------------------------
# Service-layer tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestPreviewScopeItems:
    """REQ-L1-049: preview_scope_items() returns count + sample."""

    def test_returns_scope_preview_for_project_scope(self):
        """REQ-L1-049: project scope returns ScopePreview with count + sample."""
        from baseline.services import preview_scope_items
        from baseline.types import ScopePreview

        workspace_id = uuid.uuid4()
        tenant_id = uuid.uuid4()

        result = preview_scope_items(
            scope="project",
            workspace_id=workspace_id,
            tenant_id=tenant_id,
        )

        assert isinstance(result, ScopePreview)
        assert result.scope == "project"
        assert result.count == 0
        assert result.sample == []

    def test_returns_scope_preview_for_global_scope(self):
        """REQ-L1-049: global scope returns ScopePreview with count + sample."""
        from baseline.services import preview_scope_items
        from baseline.types import ScopePreview

        result = preview_scope_items(
            scope="global",
            workspace_id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
        )

        assert isinstance(result, ScopePreview)
        assert result.scope == "global"
        assert result.count == 0
        assert result.sample == []

    def test_returns_scope_preview_for_document_scope(self):
        """REQ-L1-049: document scope with artifact_id returns ScopePreview."""
        from baseline.services import preview_scope_items
        from baseline.types import ScopePreview

        result = preview_scope_items(
            scope="document",
            workspace_id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            artifact_id=uuid.uuid4(),
        )

        assert isinstance(result, ScopePreview)
        assert result.scope == "document"
        assert result.count == 0
        assert result.sample == []

    def test_document_scope_requires_artifact_id(self):
        """REQ-L1-049: document scope without artifact_id raises ValueError."""
        from baseline.services import preview_scope_items

        with pytest.raises(ValueError, match="artifact_id is required"):
            preview_scope_items(
                scope="document",
                workspace_id=uuid.uuid4(),
                tenant_id=uuid.uuid4(),
                artifact_id=None,
            )

    def test_unknown_scope_raises(self):
        """REQ-L1-049: unknown scope raises ValueError."""
        from baseline.services import preview_scope_items

        with pytest.raises(ValueError, match="Unknown scope"):
            preview_scope_items(
                scope="invalid",
                workspace_id=uuid.uuid4(),
                tenant_id=uuid.uuid4(),
            )

    def test_sample_is_capped_at_10(self):
        """REQ-L1-049: sample list is capped at 10 items (preview only)."""
        from baseline.services import preview_scope_items

        workspace_id = uuid.uuid4()
        tenant_id = uuid.uuid4()

        result = preview_scope_items(
            scope="project",
            workspace_id=workspace_id,
            tenant_id=tenant_id,
        )

        assert len(result.sample) <= 10

    def test_sample_items_have_id_title_type(self):
        """REQ-L1-049: each sample item has id, title, type keys."""
        from baseline.services import preview_scope_items

        result = preview_scope_items(
            scope="project",
            workspace_id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
        )

        # Empty result must still expose the right shape contract
        for item in result.sample:
            assert "id" in item
            assert "title" in item
            assert "type" in item


# ---------------------------------------------------------------------------
# DB-backed happy-path tests (use Artifact model for realistic data)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestPreviewScopeItemsWithData:
    """REQ-L1-049: realistic DB test with seeded Artifacts."""

    def _make_tenant(self):
        from persistence.models import Tenant

        return Tenant.objects.create(
            name="ScopePreview-Tenant",
            slug=f"scope-prev-{uuid.uuid4().hex[:8]}",
        )

    def _make_workspace(self, tenant, name: str = "WS-1"):
        from persistence.models import Workspace

        return Workspace.unscoped.create(
            tenant=tenant,
            name=name,
            preset={"name": "extended"},
        )

    def test_project_scope_counts_only_workspace_artifacts(self):
        """REQ-L1-049: project scope counts only this workspace's artifacts."""
        from persistence.tenancy import TenantContext
        from persistence.models import Artifact
        from baseline.services import preview_scope_items

        tenant = self._make_tenant()
        TenantContext.set_tenant(tenant.id)
        try:
            ws1 = self._make_workspace(tenant, "WS-1")
            ws2 = self._make_workspace(tenant, "WS-2")
            for i in range(3):
                Artifact.unscoped.create(
                    tenant=tenant,
                    workspace=ws1,
                    artifact_type="requirement",
                )
            for i in range(2):
                Artifact.unscoped.create(
                    tenant=tenant,
                    workspace=ws2,
                    artifact_type="requirement",
                )

            result = preview_scope_items(
                scope="project",
                workspace_id=ws1.id,
                tenant_id=tenant.id,
            )
            assert result.count == 3
            assert len(result.sample) == 3
        finally:
            TenantContext.clear_tenant()

    def test_global_scope_counts_all_workspaces(self):
        """REQ-L1-049: global scope counts all artifacts in the tenant."""
        from persistence.tenancy import TenantContext
        from persistence.models import Artifact
        from baseline.services import preview_scope_items

        tenant = self._make_tenant()
        TenantContext.set_tenant(tenant.id)
        try:
            ws1 = self._make_workspace(tenant, "WS-1")
            ws2 = self._make_workspace(tenant, "WS-2")
            for i in range(4):
                Artifact.unscoped.create(
                    tenant=tenant,
                    workspace=ws1,
                    artifact_type="requirement",
                )
            for i in range(5):
                Artifact.unscoped.create(
                    tenant=tenant,
                    workspace=ws2,
                    artifact_type="requirement",
                )

            result = preview_scope_items(
                scope="global",
                workspace_id=ws1.id,
                tenant_id=tenant.id,
            )
            assert result.count == 9
            assert len(result.sample) == 9
        finally:
            TenantContext.clear_tenant()

    def test_project_scope_excludes_diagram_shadow_artifacts(self):
        """M3 (Codeberg #353 final review): a Diagram's shadow Artifact
        (artifact_type='Diagram', diagram.traceability_connector
        ._resolve_artifact_id) is an internal implementation detail, not a
        real domain artifact — it must not appear in a project-scope
        baseline preview."""
        from persistence.tenancy import TenantContext
        from persistence.models import Artifact
        from baseline.services import preview_scope_items

        tenant = self._make_tenant()
        TenantContext.set_tenant(tenant.id)
        try:
            ws1 = self._make_workspace(tenant, "WS-1")
            Artifact.unscoped.create(
                tenant=tenant, workspace=ws1, artifact_type="requirement"
            )
            Artifact.unscoped.create(
                tenant=tenant, workspace=ws1, artifact_type="Diagram"
            )

            result = preview_scope_items(
                scope="project",
                workspace_id=ws1.id,
                tenant_id=tenant.id,
            )
            assert result.count == 1
            assert len(result.sample) == 1
        finally:
            TenantContext.clear_tenant()

    def test_global_scope_excludes_diagram_shadow_artifacts(self):
        """M3 (Codeberg #353 final review): same Diagram-shadow-Artifact
        exclusion as the project-scope test above, applied to global scope."""
        from persistence.tenancy import TenantContext
        from persistence.models import Artifact
        from baseline.services import preview_scope_items

        tenant = self._make_tenant()
        TenantContext.set_tenant(tenant.id)
        try:
            ws1 = self._make_workspace(tenant, "WS-1")
            Artifact.unscoped.create(
                tenant=tenant, workspace=ws1, artifact_type="requirement"
            )
            Artifact.unscoped.create(
                tenant=tenant, workspace=ws1, artifact_type="Diagram"
            )

            result = preview_scope_items(
                scope="global",
                workspace_id=ws1.id,
                tenant_id=tenant.id,
            )
            assert result.count == 1
            assert len(result.sample) == 1
        finally:
            TenantContext.clear_tenant()

    def test_document_scope_counts_root_and_descendants(self):
        """REQ-L1-049: document scope counts root artifact + descendants."""
        from persistence.tenancy import TenantContext
        from persistence.models import Artifact
        from baseline.services import preview_scope_items

        tenant = self._make_tenant()
        TenantContext.set_tenant(tenant.id)
        try:
            ws = self._make_workspace(tenant, "WS-1")
            root = Artifact.unscoped.create(
                tenant=tenant,
                workspace=ws,
                artifact_type="system",
            )
            child1 = Artifact.unscoped.create(
                tenant=tenant,
                workspace=ws,
                artifact_type="subsystem",
                parent=root,
            )
            child2 = Artifact.unscoped.create(
                tenant=tenant,
                workspace=ws,
                artifact_type="subsystem",
                parent=root,
            )
            Artifact.unscoped.create(
                tenant=tenant,
                workspace=ws,
                artifact_type="requirement",
                parent=child1,
            )
            # unrelated artifact — must NOT be counted
            Artifact.unscoped.create(
                tenant=tenant,
                workspace=ws,
                artifact_type="requirement",
            )

            result = preview_scope_items(
                scope="document",
                workspace_id=ws.id,
                tenant_id=tenant.id,
                artifact_id=root.id,
            )
            assert result.count == 4  # root + 2 children + 1 grandchild
        finally:
            TenantContext.clear_tenant()

    def test_sample_caps_at_10_when_more_items(self):
        """REQ-L1-049: sample is capped at 10 even with more data."""
        from persistence.tenancy import TenantContext
        from persistence.models import Artifact
        from baseline.services import preview_scope_items

        tenant = self._make_tenant()
        TenantContext.set_tenant(tenant.id)
        try:
            ws = self._make_workspace(tenant, "WS-1")
            for i in range(15):
                Artifact.unscoped.create(
                    tenant=tenant,
                    workspace=ws,
                    artifact_type="requirement",
                )

            result = preview_scope_items(
                scope="project",
                workspace_id=ws.id,
                tenant_id=tenant.id,
            )
            assert result.count == 15
            assert len(result.sample) == 10
        finally:
            TenantContext.clear_tenant()


# ---------------------------------------------------------------------------
# View layer / endpoint tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestScopePreviewEndpoint:
    """REQ-L1-049: scope_preview endpoint returns the preview JSON."""

    def _get_view(self):
        from baseline.views import BaselineScopePreviewView
        return BaselineScopePreviewView.as_view()

    def _auth_context(self):
        """Build a minimal authenticated AuthContext for RBAC to allow READ.

        SA-23: scope_preview no longer accepts AllowAny, so requests must
        carry ``request.auth_context`` (set by BearerTokenAuthentication in
        production) for RbacPermission to grant access.
        """
        from auth_tenancy.context import AuthContext, AuthMethod

        return AuthContext(
            user_id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            active_roles=("admin",),
            auth_method=AuthMethod.BEARER_TOKEN,
        )

    def _make_request(self, params: dict | None = None, authenticated: bool = True):
        factory = RequestFactory()
        request = factory.get(
            "/api/v1/baselines/scope-preview/",
            data=params or {},
        )
        if authenticated:
            request.auth_context = self._auth_context()
        return request

    def test_endpoint_returns_count_and_sample(self):
        """REQ-L1-049: GET .../scope-preview/ returns count + sample."""
        view = self._get_view()
        request = self._make_request(
            {
                "scope": "project",
                "workspace_id": str(uuid.uuid4()),
            }
        )
        response = view(request)
        assert response.status_code == 200
        body = response.data
        assert "count" in body
        assert "sample" in body
        assert "scope" in body
        assert body["scope"] == "project"

    def test_endpoint_rejects_anonymous_caller(self):
        """SA-23: no ``auth_context`` (anonymous caller) → 401, not 200."""
        view = self._get_view()
        request = self._make_request(
            {
                "scope": "project",
                "workspace_id": str(uuid.uuid4()),
            },
            authenticated=False,
        )
        response = view(request)
        assert response.status_code == 401

    def test_endpoint_document_scope_requires_artifact_id(self):
        """REQ-L1-049: scope=document without artifact_id → 400."""
        view = self._get_view()
        request = self._make_request(
            {
                "scope": "document",
                "workspace_id": str(uuid.uuid4()),
            }
        )
        response = view(request)
        assert response.status_code == 400

    def test_endpoint_missing_scope_returns_400(self):
        """REQ-L1-049: missing scope query param → 400."""
        view = self._get_view()
        request = self._make_request(
            {"workspace_id": str(uuid.uuid4())}
        )
        response = view(request)
        assert response.status_code == 400

    def test_endpoint_missing_workspace_id_returns_400(self):
        """REQ-L1-049: missing workspace_id query param → 400."""
        view = self._get_view()
        request = self._make_request({"scope": "project"})
        response = view(request)
        assert response.status_code == 400

    def test_endpoint_invalid_scope_returns_400(self):
        """REQ-L1-049: unknown scope → 400."""
        view = self._get_view()
        request = self._make_request(
            {
                "scope": "invalid",
                "workspace_id": str(uuid.uuid4()),
            }
        )
        response = view(request)
        assert response.status_code == 400

    def test_endpoint_global_scope_rejects_non_admin(self):
        """REQ-L1-049: scope=global requires staff/superuser; else 403."""
        from unittest.mock import patch

        view = self._get_view()
        request = self._make_request(
            {
                "scope": "global",
                "workspace_id": str(uuid.uuid4()),
            }
        )
        # Authenticated (RBAC-admin) but not a Django staff/superuser, so the
        # view must reject the global scope with 403.
        with patch("baseline.views._user_is_global_admin", return_value=False):
            response = view(request)
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# Model-level scope field tests
# ---------------------------------------------------------------------------


class TestBaselineSnapshotScopeChoices:
    """REQ-L1-049: BaselineSnapshot.scope has 3 valid choices."""

    def test_scope_field_has_document_choice(self):
        from baseline.models import BaselineSnapshot

        choices = dict(BaselineSnapshot.SCOPE_CHOICES)
        assert "document" in choices
        assert "project" in choices
        assert "global" in choices

    def test_scope_field_max_length_is_at_least_32(self):
        from baseline.models import BaselineSnapshot

        field = BaselineSnapshot._meta.get_field("scope")
        assert field.max_length >= 8

    def test_scope_default_is_project(self):
        from baseline.models import BaselineSnapshot

        field = BaselineSnapshot._meta.get_field("scope")
        assert field.default == "project"
