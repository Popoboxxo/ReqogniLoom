"""
Tests for COMP-AS-010 SearchService.

leaf_id : COMP-AS-010
req_id  : REQ-L1-020, REQ-L3-SEARCH-001..009

Static tests: QueryParser (operators, prefix, phrase), SearchService
validation (empty query, bad type filter, pagination), tenant isolation
by verifying tenant_id in SQL params.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch, call

import pytest

from application.base import ValidationError
from application.search_service import QueryParser, SearchResult, SearchService


# ---------- QueryParser ----------


class TestQueryParser:
    def test_simple_token(self):
        assert QueryParser.parse("authentication") == "authentication"

    def test_and_operator(self):
        result = QueryParser.parse("req AND ui")
        assert "&" in result

    def test_or_operator(self):
        result = QueryParser.parse("req OR ui")
        assert "|" in result

    def test_not_operator(self):
        result = QueryParser.parse("NOT deleted")
        assert "!" in result

    def test_prefix_search(self):
        result = QueryParser.parse("req*")
        assert "req:*" in result

    def test_phrase_search(self):
        result = QueryParser.parse('"exact phrase"')
        # Should produce phrase-match syntax
        assert "<->" in result

    def test_empty_query_raises(self):
        with pytest.raises(ValidationError, match="empty"):
            QueryParser.parse("")

    def test_whitespace_only_raises(self):
        with pytest.raises(ValidationError, match="empty"):
            QueryParser.parse("   ")


# ---------- SearchService validation ----------


class TestSearchServiceValidation:
    def _make_ctx(self):
        ctx = MagicMock()
        ctx.active_roles = ("viewer",)
        ctx.tenant_id = uuid.uuid4()
        ctx.user_id = uuid.uuid4()
        return ctx

    def test_empty_query_raises(self):
        svc = SearchService()
        ctx = self._make_ctx()

        with patch("application.search_service.TenantContext"):
            with pytest.raises(ValidationError, match="empty"):
                svc.search(query="", ctx=ctx)

    def test_invalid_type_filter_raises(self):
        svc = SearchService()
        ctx = self._make_ctx()

        with patch("application.search_service.TenantContext"):
            with pytest.raises(ValidationError, match="Invalid type_filter"):
                svc.search(query="foo", ctx=ctx, type_filter=["UnknownType"])

    def test_page_less_than_1_raises(self):
        svc = SearchService()
        ctx = self._make_ctx()

        with patch("application.search_service.TenantContext"):
            with pytest.raises(ValidationError, match="page must be"):
                svc.search(query="foo", ctx=ctx, page=0)

    def test_limit_exceeds_max_raises(self):
        svc = SearchService()
        ctx = self._make_ctx()

        with patch("application.search_service.TenantContext"):
            with pytest.raises(ValidationError, match="limit must be"):
                svc.search(query="foo", ctx=ctx, limit=101)

    def test_limit_zero_raises(self):
        svc = SearchService()
        ctx = self._make_ctx()

        with patch("application.search_service.TenantContext"):
            with pytest.raises(ValidationError, match="limit must be"):
                svc.search(query="foo", ctx=ctx, limit=0)


# ---------- SearchService — search execution ----------


class TestSearchServiceExecution:
    def _make_ctx(self, tenant_id=None):
        ctx = MagicMock()
        ctx.active_roles = ("viewer",)
        ctx.tenant_id = tenant_id or uuid.uuid4()
        ctx.user_id = uuid.uuid4()
        return ctx

    def test_returns_search_result(self):
        svc = SearchService()
        ctx = self._make_ctx()

        with (
            patch("application.search_service.TenantContext"),
            patch(
                "application.search_service.SearchService._search_entity_type",
                return_value=[],
            ),
        ):
            result = svc.search(query="auth", ctx=ctx)

        assert isinstance(result, SearchResult)
        assert result.page == 1
        assert result.limit == 20

    def test_type_filter_restricts_entity_types(self):
        """Only the specified entity type is searched."""
        svc = SearchService()
        ctx = self._make_ctx()

        with (
            patch("application.search_service.TenantContext"),
            patch(
                "application.search_service.SearchService._search_entity_type",
                return_value=[],
            ) as mock_search,
        ):
            svc.search(query="auth", ctx=ctx, type_filter=["Requirement"])

        called_types = [c.kwargs["entity_type"] for c in mock_search.call_args_list]
        assert called_types == ["Requirement"]

    def test_all_types_searched_without_filter(self):
        svc = SearchService()
        ctx = self._make_ctx()

        with (
            patch("application.search_service.TenantContext"),
            patch(
                "application.search_service.SearchService._search_entity_type",
                return_value=[],
            ) as mock_search,
        ):
            svc.search(query="auth", ctx=ctx)

        called_types = {c.kwargs["entity_type"] for c in mock_search.call_args_list}
        assert called_types == {"Requirement", "ArchitectureElement", "TestCase"}

    def test_pagination_slices_results(self):
        """REQ-L3-SEARCH-006: page and limit correctly slice hits."""
        from application.search_service import SearchHit

        svc = SearchService()
        ctx = self._make_ctx(tenant_id=uuid.uuid4())

        fake_hits = [
            SearchHit(
                id=str(uuid.uuid4()),
                artifact_type="Requirement",
                title=f"Req {i}",
                description="",
                relevance_score=1.0 / (i + 1),
                workspace_id=str(uuid.uuid4()),
            )
            for i in range(10)
        ]

        with (
            patch("application.search_service.TenantContext"),
            patch(
                "application.search_service.SearchService._search_entity_type",
                return_value=fake_hits,
            ),
        ):
            result = svc.search(query="req", ctx=ctx, page=2, limit=3)

        assert result.total_count == 10
        assert result.page == 2
        assert result.limit == 3
        assert len(result.results) == 3

    def test_tenant_isolation_passes_tenant_id(self):
        """REQ-L3-SEARCH-005: tenant_id from ctx is forwarded to _search_entity_type."""
        svc = SearchService()
        tenant_uuid = uuid.uuid4()
        ctx = self._make_ctx(tenant_id=tenant_uuid)

        with (
            patch("application.search_service.TenantContext"),
            patch(
                "application.search_service.SearchService._search_entity_type",
                return_value=[],
            ) as mock_search,
        ):
            svc.search(query="auth", ctx=ctx, type_filter=["Requirement"])

        assert mock_search.call_args.kwargs["tenant_id"] == tenant_uuid

    def test_entity_type_failure_degrades_gracefully(self):
        """REQ-L3-SEARCH-009: error in one type yields empty hits for that type."""
        svc = SearchService()
        ctx = self._make_ctx()

        def _side_effect(entity_type, **kw):
            if entity_type == "Requirement":
                raise RuntimeError("DB timeout")
            return []

        with (
            patch("application.search_service.TenantContext"),
            patch(
                "application.search_service.SearchService._search_entity_type",
                side_effect=_side_effect,
            ),
        ):
            result = svc.search(query="auth", ctx=ctx)

        assert isinstance(result, SearchResult)
        assert result.total_count == 0
