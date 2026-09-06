"""
Tests for GlossaryService soft-delete behavior (REQ-006).

leaf_id : COMP-AS-020
req_id  : REQ-006, REQ-L1-044

Covers:
  - delete() sets lifecycle_status='deleted' instead of hard-deleting (REQ-006)
  - list_by_workspace() excludes deleted terms by default (REQ-006)
  - list_by_workspace(include_deleted=True) includes all terms (REQ-006)
  - GlossaryTermDTO.from_orm maps lifecycle_status correctly
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from application.base import NotFoundError
from application.glossary_service import GlossaryService, GlossaryTermDTO
from persistence.models import Tenant, User, Workspace

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ctx(*, roles=("editor",), tenant_id=None):
    ctx = MagicMock()
    ctx.active_roles = roles
    ctx.tenant_id = tenant_id or uuid.uuid4()
    ctx.user_id = uuid.uuid4()
    ctx.has_role = lambda role: role in roles
    return ctx


TERM_ID = uuid.uuid4()
WS_ID = uuid.uuid4()


def _make_term(**kwargs):
    """Return a MagicMock shaped like a GlossaryTerm ORM instance.

    Datenmodell-Konsolidierung Task 24: the per-entity `lifecycle_status`
    mirror column is gone; `GlossaryTermDTO.from_orm` reads
    `term.artifact.lifecycle_status` instead, so the mock exposes it there.
    """
    term = MagicMock()
    term.id = kwargs.get("id", TERM_ID)
    term.workspace_id = kwargs.get("workspace_id", WS_ID)
    term.term = kwargs.get("term", "Requirement")
    term.definition = kwargs.get("definition", "A stated need.")
    term.synonyms = kwargs.get("synonyms", [])
    term.abbreviation = kwargs.get("abbreviation", "REQ")
    term.version = kwargs.get("version", 1)
    term.artifact_id = kwargs.get("artifact_id", uuid.uuid4())
    term.artifact.lifecycle_status = kwargs.get("lifecycle_status", "active")
    return term


# ---------------------------------------------------------------------------
# GlossaryTermDTO.from_orm
# ---------------------------------------------------------------------------


class TestGlossaryTermDTO:
    def test_from_orm_maps_lifecycle_status(self):
        """from_orm copies lifecycle_status from ORM instance (REQ-006)."""
        term = _make_term(lifecycle_status="deprecated")
        dto = GlossaryTermDTO.from_orm(term)
        assert dto.lifecycle_status == "deprecated"

    def test_from_orm_defaults_to_active(self):
        """from_orm defaults lifecycle_status to 'active' for a term with no
        backing Artifact yet (workspace-less legacy row, Task 20)."""
        term = _make_term()
        term.artifact_id = None
        dto = GlossaryTermDTO.from_orm(term)
        assert dto.lifecycle_status == "active"


# ---------------------------------------------------------------------------
# GlossaryService.delete — REQ-006 soft-delete
# ---------------------------------------------------------------------------


class TestGlossaryServiceSoftDelete:
    """REQ-006: delete() must soft-delete (lifecycle_status='deleted'), not hard-delete."""

    def test_delete_calls_outdate(self):
        """delete() routes the soft-delete through workflow.services.outdate()
        instead of writing lifecycle_status directly (REQ-006, Phase 0)."""
        svc = GlossaryService()
        ctx = _make_ctx()
        mock_term = _make_term()
        mock_term.save = MagicMock()

        with (
            patch("application.glossary_service.GlossaryTerm.objects") as mock_mgr,
            patch("workflow.services.outdate") as mock_outdate,
        ):
            mock_mgr.filter.return_value.first.return_value = mock_term
            svc.delete(ctx, TERM_ID)

        mock_outdate.assert_called_once_with(
            item_id=mock_term.id,
            item_type="GlossaryTerm",
            workspace_id=mock_term.workspace_id,
            ctx=ctx,
            reason="deleted via glossary.delete",
        )
        # Hard-delete must NOT be called, lifecycle_status must not be written directly
        mock_term.delete.assert_not_called()
        mock_term.save.assert_not_called()

    def test_delete_not_found_raises(self):
        """delete() raises NotFoundError when term does not exist."""
        svc = GlossaryService()
        ctx = _make_ctx()

        with patch("application.glossary_service.GlossaryTerm.objects") as mock_mgr:
            mock_mgr.filter.return_value.first.return_value = None
            with pytest.raises(NotFoundError, match="GlossaryTerm"):
                svc.delete(ctx, TERM_ID)


# ---------------------------------------------------------------------------
# GlossaryService.update — #82 regression: `term` was silently dropped
# ---------------------------------------------------------------------------


class TestGlossaryServiceUpdate:
    """Regression test for #82: PATCH must be able to update the `term` label.

    POST /api/v1/glossary/ accepts `term` + `definition`, but PATCH previously
    only forwarded `definition`/`synonyms`/`abbreviation` — the `term` field
    silently was never persisted, so a glossary term's label was immutable
    after creation via REST.
    """

    def test_update_changes_term_label(self):
        from persistence.tenancy import TenantContext

        tenant = Tenant.objects.create(name="Test Tenant", slug=f"test-{uuid.uuid4().hex[:8]}")
        workspace = Workspace.unscoped.create(tenant=tenant, name="WS", preset={"tier": "standard"})
        user = User.objects.create(
            username=f"testuser-{uuid.uuid4().hex[:8]}",
            email=f"test-{uuid.uuid4().hex[:8]}@example.com",
            tenant=tenant,
        )
        TenantContext.set_tenant(tenant.id)
        ctx = _make_ctx(roles=("editor",), tenant_id=tenant.id)
        ctx.user_id = user.id

        svc = GlossaryService()
        created = svc.create(ctx, workspace.id, "Requirement", "A stated need.")

        updated = svc.update(ctx, created.id, term="System Requirement")

        assert updated.term == "System Requirement"
        # definition must be untouched when not supplied
        assert updated.definition == "A stated need."

    def test_update_without_term_leaves_label_unchanged(self):
        """Omitting `term` (definition-only PATCH) must not clear the label."""
        from persistence.tenancy import TenantContext

        tenant = Tenant.objects.create(name="Test Tenant", slug=f"test-{uuid.uuid4().hex[:8]}")
        workspace = Workspace.unscoped.create(tenant=tenant, name="WS", preset={"tier": "standard"})
        user = User.objects.create(
            username=f"testuser-{uuid.uuid4().hex[:8]}",
            email=f"test-{uuid.uuid4().hex[:8]}@example.com",
            tenant=tenant,
        )
        TenantContext.set_tenant(tenant.id)
        ctx = _make_ctx(roles=("editor",), tenant_id=tenant.id)
        ctx.user_id = user.id

        svc = GlossaryService()
        created = svc.create(ctx, workspace.id, "Requirement", "A stated need.")

        updated = svc.update(ctx, created.id, definition="Updated definition.")

        assert updated.term == "Requirement"
        assert updated.definition == "Updated definition."


# ---------------------------------------------------------------------------
# GlossaryService.list_by_workspace — exclude deleted by default
# ---------------------------------------------------------------------------


class TestGlossaryServiceList:
    """REQ-006: list_by_workspace() excludes deleted terms by default."""

    def test_list_include_deleted_skips_exclude(self):
        """list_by_workspace(include_deleted=True) does NOT call .exclude() (REQ-006)."""
        svc = GlossaryService()
        ctx = _make_ctx()
        mock_term = _make_term(lifecycle_status="deleted")

        # Chain: select_related() → filter() → order_by() → [terms] (no exclude)
        mock_qs = MagicMock()
        mock_qs.select_related.return_value = mock_qs
        mock_qs.filter.return_value = mock_qs
        mock_qs.order_by.return_value = [mock_term]

        with patch("application.glossary_service.GlossaryTerm.objects", mock_qs):
            results = svc.list_by_workspace(ctx, WS_ID, include_deleted=True)

        # .exclude() must NOT be called when include_deleted=True
        mock_qs.exclude.assert_not_called()
        assert len(results) == 1


# ---------------------------------------------------------------------------
# Regression: list_by_workspace()/create()/delete() end-to-end via the
# workflow engine (Phase 0 fix — GlossaryTerm is not wired into
# workflow._STATUS_MIRROR_MODELS, so the source of truth is WorkflowItemState;
# create() must seed one so delete()'s outdate() call has something to
# transition, and list_by_workspace() must filter on it).
# ---------------------------------------------------------------------------


@pytest.fixture
def glossary_tenant():
    from persistence.models import Tenant

    return Tenant.objects.create(name="glossary-tenant", slug="glossary-tenant")


@pytest.fixture
def glossary_user(glossary_tenant):
    from persistence.models import User

    return User.objects.create(
        username="glossary-user", email="glossary@example.com", tenant=glossary_tenant
    )


@pytest.fixture
def glossary_workspace(glossary_tenant):
    from persistence.models import Workspace
    from persistence.tenancy import TenantContext

    TenantContext.set_tenant(glossary_tenant.id)
    try:
        return Workspace.objects.create(tenant=glossary_tenant, name="glossary-workspace")
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def glossary_real_ctx(glossary_user):
    from auth_tenancy.context import AuthContext

    return AuthContext(
        user_id=glossary_user.id,
        tenant_id=glossary_user.tenant.id,
        active_roles=("editor",),
        auth_method="test",
        api_key_id=None,
        tenant_name="glossary-tenant",
    )


class TestGlossaryServiceCreateDeleteWorkflowIntegration:
    """REQ-006/Phase 0: create() seeds a WorkflowItemState so delete() (via
    outdate()) does not crash, and list_by_workspace() excludes the result."""

    def test_create_then_delete_does_not_raise_and_updates_workflow_state(
        self, glossary_real_ctx, glossary_workspace
    ):
        from persistence.tenancy import TenantContext
        from workflow.models import WorkflowItemState
        from workflow.services import create_default_workflow

        TenantContext.set_tenant(glossary_workspace.tenant_id)
        try:
            create_default_workflow(
                workspace_id=glossary_workspace.id,
                preset="glossary_term_default",
                item_type="GlossaryTerm",
                tenant_id=glossary_workspace.tenant_id,
            )
        finally:
            TenantContext.clear_tenant()

        # GlossaryService does not call _set_tenant_context itself (unlike
        # Requirement/Adr/Architecture) — in production the DRF request
        # middleware sets it; here we set it explicitly around the calls.
        TenantContext.set_tenant(glossary_workspace.tenant_id)
        try:
            svc = GlossaryService()
            term = svc.create(
                ctx=glossary_real_ctx,
                workspace_id=glossary_workspace.id,
                term="Requirement",
                definition="A stated need.",
            )

            # create() must have seeded a WorkflowItemState (previously it never did).
            item_state = WorkflowItemState.objects.get(
                item_id=term.id, item_type="GlossaryTerm"
            )
            assert item_state.current_state != "outdated"

            # delete() must not raise WorkflowItemState.DoesNotExist anymore.
            svc.delete(glossary_real_ctx, term.id)

            # Phase 4 (D-3): soft-delete is the Artifact flag; the workflow
            # state is deliberately preserved. Task 24 dropped the per-term
            # mirror column -- Artifact.lifecycle_status is what
            # GlossaryTermSerializer exposes on the wire now (via the DTO).
            from persistence.models import Artifact, GlossaryTerm

            row = GlossaryTerm.objects.get(pk=term.id)
            assert Artifact.objects.get(pk=row.artifact_id).lifecycle_status == "outdated"
            item_state.refresh_from_db()
            assert item_state.current_state != "outdated"
        finally:
            TenantContext.clear_tenant()

    def test_get_reflects_outdated_status_after_delete(
        self, glossary_real_ctx, glossary_workspace
    ):
        """Issue #440: get() must reflect the workflow-tracked 'outdated'
        state after delete() — previously the detail view kept reporting
        lifecycle_status='active' forever (the model column is never written
        by outdate() for GlossaryTerm), so a soft-deleted term stayed fully
        visible (200, status 'active') via GET even though it had already
        disappeared from the list.
        """
        from persistence.tenancy import TenantContext
        from workflow.services import create_default_workflow

        TenantContext.set_tenant(glossary_workspace.tenant_id)
        try:
            create_default_workflow(
                workspace_id=glossary_workspace.id,
                preset="glossary_term_default",
                item_type="GlossaryTerm",
                tenant_id=glossary_workspace.tenant_id,
            )
        finally:
            TenantContext.clear_tenant()

        TenantContext.set_tenant(glossary_workspace.tenant_id)
        try:
            svc = GlossaryService()
            term = svc.create(
                ctx=glossary_real_ctx,
                workspace_id=glossary_workspace.id,
                term="Requirement",
                definition="A stated need.",
            )

            # Before delete: detail GET reports 'active'.
            before = svc.get(glossary_real_ctx, term.id)
            assert before.lifecycle_status == "active"

            svc.delete(glossary_real_ctx, term.id)

            # After delete: still retrievable (no 404), but status must be
            # 'outdated' — consistent with TestCase/Issue/ADR/Risk/Need,
            # which report status='outdated' via their mirrored column.
            after = svc.get(glossary_real_ctx, term.id)
            assert after.lifecycle_status == "outdated"
        finally:
            TenantContext.clear_tenant()

    def test_deleted_term_excluded_from_default_list(
        self, glossary_real_ctx, glossary_workspace
    ):
        from persistence.tenancy import TenantContext
        from workflow.services import create_default_workflow

        TenantContext.set_tenant(glossary_workspace.tenant_id)
        try:
            create_default_workflow(
                workspace_id=glossary_workspace.id,
                preset="glossary_term_default",
                item_type="GlossaryTerm",
                tenant_id=glossary_workspace.tenant_id,
            )
        finally:
            TenantContext.clear_tenant()

        TenantContext.set_tenant(glossary_workspace.tenant_id)
        try:
            svc = GlossaryService()
            kept = svc.create(
                ctx=glossary_real_ctx,
                workspace_id=glossary_workspace.id,
                term="Kept Term",
                definition="Stays visible.",
            )
            deleted = svc.create(
                ctx=glossary_real_ctx,
                workspace_id=glossary_workspace.id,
                term="Deleted Term",
                definition="Gets soft-deleted.",
            )
            svc.delete(glossary_real_ctx, deleted.id)

            results = svc.list_by_workspace(glossary_real_ctx, glossary_workspace.id)
            ids = {r.id for r in results}
            assert kept.id in ids
            assert deleted.id not in ids

            results_incl = svc.list_by_workspace(
                glossary_real_ctx, glossary_workspace.id, include_deleted=True
            )
            ids_incl = {r.id for r in results_incl}
            assert deleted.id in ids_incl
        finally:
            TenantContext.clear_tenant()
