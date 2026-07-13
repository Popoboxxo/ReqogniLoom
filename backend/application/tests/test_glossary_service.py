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
    """Return a MagicMock shaped like a GlossaryTerm ORM instance."""
    term = MagicMock()
    term.id = kwargs.get("id", TERM_ID)
    term.workspace_id = kwargs.get("workspace_id", WS_ID)
    term.term = kwargs.get("term", "Requirement")
    term.definition = kwargs.get("definition", "A stated need.")
    term.synonyms = kwargs.get("synonyms", [])
    term.abbreviation = kwargs.get("abbreviation", "REQ")
    term.version = kwargs.get("version", 1)
    term.lifecycle_status = kwargs.get("lifecycle_status", "active")
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
        """from_orm defaults lifecycle_status to 'active' when attribute absent."""
        term = _make_term()
        # Simulate pre-migration row with no lifecycle_status attribute
        del term.lifecycle_status
        dto = GlossaryTermDTO.from_orm(term)
        assert dto.lifecycle_status == "active"


# ---------------------------------------------------------------------------
# GlossaryService.delete — REQ-006 soft-delete
# ---------------------------------------------------------------------------


class TestGlossaryServiceSoftDelete:
    """REQ-006: delete() must soft-delete (lifecycle_status='deleted'), not hard-delete."""

    def test_soft_delete_sets_lifecycle_status(self):
        """delete() sets lifecycle_status='deleted', NOT gt.delete() (REQ-006)."""
        svc = GlossaryService()
        ctx = _make_ctx()
        mock_term = _make_term()
        mock_term.save = MagicMock()

        with patch("application.glossary_service.GlossaryTerm.objects") as mock_mgr:
            mock_mgr.filter.return_value.first.return_value = mock_term
            svc.delete(ctx, TERM_ID)

        # REQ-006: lifecycle_status set to 'deleted'
        assert mock_term.lifecycle_status == "deleted"
        mock_term.save.assert_called_once_with(update_fields=["lifecycle_status"])
        # Hard-delete must NOT be called
        mock_term.delete.assert_not_called()

    def test_delete_not_found_raises(self):
        """delete() raises NotFoundError when term does not exist."""
        svc = GlossaryService()
        ctx = _make_ctx()

        with patch("application.glossary_service.GlossaryTerm.objects") as mock_mgr:
            mock_mgr.filter.return_value.first.return_value = None
            with pytest.raises(NotFoundError, match="GlossaryTerm"):
                svc.delete(ctx, TERM_ID)


# ---------------------------------------------------------------------------
# GlossaryService.list_by_workspace — exclude deleted by default
# ---------------------------------------------------------------------------


class TestGlossaryServiceList:
    """REQ-006: list_by_workspace() excludes deleted terms by default."""

    def test_list_excludes_deleted_by_default(self):
        """list_by_workspace() calls .exclude(lifecycle_status='deleted') (REQ-006)."""
        svc = GlossaryService()
        ctx = _make_ctx()
        mock_term = _make_term()

        # Chain: filter() → exclude() → order_by() → [terms]
        mock_qs = MagicMock()
        mock_qs.filter.return_value = mock_qs
        mock_qs.exclude.return_value = mock_qs
        mock_qs.order_by.return_value = [mock_term]

        with patch("application.glossary_service.GlossaryTerm.objects", mock_qs):
            results = svc.list_by_workspace(ctx, WS_ID)

        # REQ-006: deleted terms must be excluded by default
        mock_qs.exclude.assert_called_once_with(lifecycle_status="deleted")
        # order_by must be called AFTER exclude (not before)
        mock_qs.order_by.assert_called_once_with("term")
        assert len(results) == 1
        assert results[0].term == mock_term.term

    def test_list_include_deleted_skips_exclude(self):
        """list_by_workspace(include_deleted=True) does NOT call .exclude() (REQ-006)."""
        svc = GlossaryService()
        ctx = _make_ctx()
        mock_term = _make_term(lifecycle_status="deleted")

        # Chain: filter() → order_by() → [terms] (no exclude)
        mock_qs = MagicMock()
        mock_qs.filter.return_value = mock_qs
        mock_qs.order_by.return_value = [mock_term]

        with patch("application.glossary_service.GlossaryTerm.objects", mock_qs):
            results = svc.list_by_workspace(ctx, WS_ID, include_deleted=True)

        # .exclude() must NOT be called when include_deleted=True
        mock_qs.exclude.assert_not_called()
        assert len(results) == 1
