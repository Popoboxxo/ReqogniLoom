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
from application.search_service import (
    SEARCHABLE_ARTIFACT_TYPES,
    QueryParser,
    SearchHit,
    SearchResult,
    SearchService,
    _RRF_K,
    _SCORE_ID_SUBSTRING,
    _SCORE_MAX,
    _SCORE_TITLE_EXACT,
    _SCORE_TITLE_PREFIX,
    _normalize_cosine_similarity,
    _normalize_fulltext_score,
    _normalize_lexical_score,
    _rrf_fuse,
)


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


# ---------- Relevance normalization (issue #827) ----------


class TestRelevanceNormalization:
    """`relevance_score` is defined on [0, 1]. Each pass's native scale is
    mapped by a monotone transform at score-creation time, so the bounds hold
    everywhere the value is exported (REST view + MCP tool) without any
    clamping in those consumers, and no ranking order changes."""

    def test_fulltext_ts_rank_is_clamped_to_unit_interval(self):
        assert _normalize_fulltext_score(0.27) == pytest.approx(0.27)
        assert _normalize_fulltext_score(2.5) == 1.0
        assert _normalize_fulltext_score(-0.1) == 0.0

    def test_fulltext_clamp_is_monotone(self):
        raws = [-1.0, 0.0, 0.06, 0.27, 0.9, 1.0, 3.0]
        mapped = [_normalize_fulltext_score(r) for r in raws]
        assert mapped == sorted(mapped)
        assert all(0.0 <= m <= 1.0 for m in mapped)

    def test_lexical_tiers_are_normalized_by_scale_maximum(self):
        assert _normalize_lexical_score(_SCORE_TITLE_EXACT) == 1.0
        assert _normalize_lexical_score(_SCORE_ID_SUBSTRING) == pytest.approx(
            _SCORE_ID_SUBSTRING / _SCORE_MAX
        )
        assert all(
            0.0 <= _normalize_lexical_score(raw) <= 1.0
            for raw in (_SCORE_TITLE_EXACT, 2.9, _SCORE_TITLE_PREFIX, 2.0, _SCORE_ID_SUBSTRING)
        )

    def test_lexical_normalization_preserves_tier_order(self):
        raws = [_SCORE_ID_SUBSTRING, 2.0, _SCORE_TITLE_PREFIX, 2.9, _SCORE_TITLE_EXACT]
        mapped = [_normalize_lexical_score(r) for r in raws]
        assert mapped == sorted(mapped)
        assert mapped[0] < mapped[-1]

    def test_cosine_distance_maps_to_bounded_similarity(self):
        # Identical vectors -> distance 0 -> similarity 1.
        assert _normalize_cosine_similarity(0.0) == 1.0
        # Orthogonal -> distance 1 -> similarity 0.
        assert _normalize_cosine_similarity(1.0) == 0.0
        # Opposite direction -> distance 2 -> similarity -1, clamped to 0.
        assert _normalize_cosine_similarity(2.0) == 0.0

    def test_cosine_normalization_is_monotone_decreasing_in_distance(self):
        distances = [0.0, 0.25, 0.5, 1.0, 1.5, 2.0]
        mapped = [_normalize_cosine_similarity(d) for d in distances]
        assert mapped == sorted(mapped, reverse=True)
        assert all(0.0 <= m <= 1.0 for m in mapped)

    def test_rrf_fusion_scores_are_normalized_to_unit_interval(self):
        def _hit(hit_id: str) -> SearchHit:
            return SearchHit(
                id=hit_id,
                artifact_type="Requirement",
                title=hit_id,
                description="",
                relevance_score=0.0,
                workspace_id="",
            )

        # "a" ranks first in every list, "b"/"c"/"d" only in one each.
        fused = _rrf_fuse(
            [_hit("a"), _hit("b")],
            [_hit("a"), _hit("c")],
            [_hit("a"), _hit("d")],
        )

        scores = {hit.id: hit.relevance_score for hit in fused}
        assert all(0.0 <= score <= 1.0 for score in scores.values())
        # A rank-0 hit in all three lists hits the theoretical maximum -> 1.0.
        assert scores["a"] == pytest.approx(1.0)
        # A rank-1 hit in one of three lists stays below it and above zero.
        expected_rank1 = (1.0 / (_RRF_K + 2)) / (3.0 / (_RRF_K + 1))
        assert scores["b"] == pytest.approx(expected_rank1)
        assert scores["a"] > scores["b"] > 0.0


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
        assert called_types == set(SEARCHABLE_ARTIFACT_TYPES)

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

        assert result.total_count == 10 * len(SEARCHABLE_ARTIFACT_TYPES)
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

    def test_raw_query_forwarded_for_lexical_pass(self):
        """#345: the unparsed query string must reach the per-type search so
        the lexical pass can substring-match it (the tsquery form cannot)."""
        svc = SearchService()
        ctx = self._make_ctx()

        with (
            patch("application.search_service.TenantContext"),
            patch(
                "application.search_service.SearchService._search_entity_type",
                return_value=[],
            ) as mock_search,
        ):
            svc.search(query="QA-AI", ctx=ctx, type_filter=["Requirement"])

        assert mock_search.call_args.kwargs["raw_query"] == "QA-AI"

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


# ---------- type_filter coverage (#345 Finding 2b) ----------


class TestTypeFilterCoverage:
    """`type_filter` used to allow only Requirement/ArchitectureElement/
    TestCase, so Needs, Goals and ADRs were unfilterable (400) even though
    they are artifacts a user would search for."""

    def _make_ctx(self):
        ctx = MagicMock()
        ctx.active_roles = ("viewer",)
        ctx.tenant_id = uuid.uuid4()
        ctx.user_id = uuid.uuid4()
        return ctx

    @pytest.mark.parametrize(
        "entity_type",
        [
            "Requirement",
            "ArchitectureElement",
            "TestCase",
            "StakeholderNeed",
            "Adr",
            "Risk",
            "Issue",
            "ChangeRequest",
            "Goal",
            "GlossaryTerm",
        ],
    )
    def test_type_filter_accepts_every_searchable_type(self, entity_type):
        svc = SearchService()
        ctx = self._make_ctx()

        with (
            patch("application.search_service.TenantContext"),
            patch(
                "application.search_service.SearchService._search_entity_type",
                return_value=[],
            ) as mock_search,
        ):
            svc.search(query="foo", ctx=ctx, type_filter=[entity_type])

        assert entity_type in SEARCHABLE_ARTIFACT_TYPES
        assert mock_search.call_args.kwargs["entity_type"] == entity_type

    def test_main_goal_is_not_searchable(self):
        """MainGoal is deliberately excluded: it has no title, only a single
        aggregated ``content`` blob per workspace, and is a derived summary
        rather than an addressable artifact. Documented, not an oversight."""
        assert "MainGoal" not in SEARCHABLE_ARTIFACT_TYPES

        svc = SearchService()
        ctx = self._make_ctx()
        with patch("application.search_service.TenantContext"):
            with pytest.raises(ValidationError, match="Invalid type_filter"):
                svc.search(query="foo", ctx=ctx, type_filter=["MainGoal"])


# ---------- Lexical fallback against a real database (#345 Finding 2) ----------


def _seed_workspace(name: str):
    """Create Tenant + User + Workspace and a matching AuthContext."""
    from auth_tenancy.context import AuthContext, AuthMethod
    from persistence.models import Tenant, User, Workspace
    from persistence.tenancy import TenantContext

    tenant = Tenant.objects.create(name=name, slug=name)
    user = User.objects.create(
        username=f"{name}-user", email=f"{name}@example.com", tenant=tenant
    )
    TenantContext.set_tenant(tenant.id)
    workspace = Workspace.objects.create(tenant=tenant, name=f"{name}-ws")
    ctx = AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=("editor",),
        auth_method=AuthMethod.API_KEY,
        api_key_id=None,
    )
    return tenant, workspace, ctx


def _seed_requirement(tenant, workspace, *, title: str, description: str, uid: str):
    from persistence.models import Artifact, Requirement

    artifact = Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type="Requirement"
    )
    return Requirement.objects.create(
        tenant=tenant,
        artifact=artifact,
        workspace=workspace,
        title=title,
        description=description,
        uid=uid,
    )


@pytest.mark.django_db(transaction=True)
class TestLexicalFallback:
    """The QA repro: a search for an artifact's own title or ID returned
    total_count 0 because only the tsvector pass existed."""

    def test_exact_title_substring_is_found(self):
        from persistence.tenancy import TenantContext

        tenant, workspace, ctx = _seed_workspace("search-lex-title")
        req = _seed_requirement(
            tenant,
            workspace,
            title="QA-AI Monitoring der CPU-Last",
            description="Beschreibung ohne den gesuchten Namen.",
            uid="REQ-QA-042",
        )
        try:
            result = SearchService().search(
                query="QA-AI", ctx=ctx, workspace_id=workspace.id
            )
        finally:
            TenantContext.clear_tenant()

        assert result.total_count >= 1
        hit = next(h for h in result.results if h.id == str(req.id))
        assert hit.artifact_type == "Requirement"
        # A title match must outrank any ts_rank score (measured: 0.27 for
        # this row via the full-text pass alone). "QA-AI" is a prefix of the
        # title — the _SCORE_TITLE_PREFIX tier — normalized by _SCORE_MAX
        # (issue #827).
        assert hit.relevance_score == pytest.approx(_SCORE_TITLE_PREFIX / _SCORE_MAX)
        assert 0.0 <= hit.relevance_score <= 1.0

    def test_partial_word_in_title_is_found(self):
        """``plainto_tsquery`` matches whole lexemes, so a fragment inside a
        word ("onitoring") is invisible to the full-text pass."""
        from persistence.tenancy import TenantContext

        tenant, workspace, ctx = _seed_workspace("search-lex-partial")
        req = _seed_requirement(
            tenant,
            workspace,
            title="QA-AI Monitoring der CPU-Last",
            description="Beschreibung.",
            uid="REQ-QA-043",
        )
        try:
            result = SearchService().search(
                query="onitoring", ctx=ctx, workspace_id=workspace.id
            )
        finally:
            TenantContext.clear_tenant()

        assert [h.id for h in result.results] == [str(req.id)]

    def test_uid_substring_is_found(self):
        from persistence.tenancy import TenantContext

        tenant, workspace, ctx = _seed_workspace("search-lex-uid")
        req = _seed_requirement(
            tenant,
            workspace,
            title="Irgendein Titel",
            description="Beschreibung.",
            uid="REQ-QA-4711",
        )
        try:
            result = SearchService().search(
                query="QA-4711", ctx=ctx, workspace_id=workspace.id
            )
        finally:
            TenantContext.clear_tenant()

        assert [h.id for h in result.results] == [str(req.id)]

    def test_raw_id_fragment_is_found(self):
        """The QA report searched for "00436a35" — an ID prefix."""
        from persistence.tenancy import TenantContext

        tenant, workspace, ctx = _seed_workspace("search-lex-id")
        req = _seed_requirement(
            tenant,
            workspace,
            title="Titel ohne Bezug",
            description="Beschreibung.",
            uid="REQ-QA-1",
        )
        fragment = str(req.id)[:8]
        try:
            result = SearchService().search(
                query=fragment, ctx=ctx, workspace_id=workspace.id
            )
        finally:
            TenantContext.clear_tenant()

        assert str(req.id) in [h.id for h in result.results]

    def test_lexical_hit_ranks_above_semantic_hit(self):
        from persistence.tenancy import TenantContext

        tenant, workspace, ctx = _seed_workspace("search-lex-rank")
        titled = _seed_requirement(
            tenant,
            workspace,
            title="QA-AI Dashboard",
            description="Nichts weiter.",
            uid="REQ-RANK-1",
        )
        described = _seed_requirement(
            tenant,
            workspace,
            title="Anderer Titel",
            description="Dieses Requirement erwähnt Dashboard im Text.",
            uid="REQ-RANK-2",
        )
        try:
            result = SearchService().search(
                query="Dashboard", ctx=ctx, workspace_id=workspace.id
            )
        finally:
            TenantContext.clear_tenant()

        ids = [h.id for h in result.results]
        assert str(titled.id) in ids
        assert str(described.id) in ids
        assert ids.index(str(titled.id)) < ids.index(str(described.id))

    def test_hit_is_not_duplicated_when_both_passes_match(self):
        from persistence.tenancy import TenantContext

        tenant, workspace, ctx = _seed_workspace("search-lex-dedupe")
        req = _seed_requirement(
            tenant,
            workspace,
            title="Monitoring",
            description="Monitoring der Systemlast.",
            uid="REQ-DEDUPE-1",
        )
        try:
            result = SearchService().search(
                query="Monitoring", ctx=ctx, workspace_id=workspace.id
            )
        finally:
            TenantContext.clear_tenant()

        assert [h.id for h in result.results].count(str(req.id)) == 1

    def test_every_relevance_score_is_bounded_to_unit_interval(self):
        """Issue #827 regression pin: the lexical pass used to emit raw CASE
        tiers (up to 3.0) straight into the API/MCP payload. After the fix
        every hit — from any pass — is in [0, 1]."""
        from persistence.tenancy import TenantContext

        tenant, workspace, ctx = _seed_workspace("search-normalized-bounds")
        exact = _seed_requirement(
            tenant,
            workspace,
            title="Monitoring",
            description="Beschreibung ohne Suchwort.",
            uid="REQ-NORM-1",
        )
        substring = _seed_requirement(
            tenant,
            workspace,
            title="Systemweites Monitoring Dashboard",
            description="Beschreibung ohne Suchwort.",
            uid="REQ-NORM-2",
        )
        try:
            result = SearchService().search(
                query="Monitoring",
                ctx=ctx,
                workspace_id=workspace.id,
                type_filter=["Requirement"],
            )
        finally:
            TenantContext.clear_tenant()

        assert {h.id for h in result.results} == {str(exact.id), str(substring.id)}
        for hit in result.results:
            assert 0.0 <= hit.relevance_score <= 1.0
        # Exact title match is the strongest lexical tier -> normalized 1.0.
        exact_hit = next(h for h in result.results if h.id == str(exact.id))
        assert exact_hit.relevance_score == pytest.approx(1.0)

    def test_normalization_preserves_lexical_tier_ranking(self):
        """Issue #827: normalization must be monotone — exact > prefix >
        substring survives the mapping onto [0, 1], and the returned list
        stays sorted by descending relevance."""
        from persistence.tenancy import TenantContext

        tenant, workspace, ctx = _seed_workspace("search-normalized-order")
        exact = _seed_requirement(
            tenant, workspace, title="Monitoring", description="x", uid="REQ-ORD-1"
        )
        prefix = _seed_requirement(
            tenant,
            workspace,
            title="Monitoring Dashboard",
            description="x",
            uid="REQ-ORD-2",
        )
        substring = _seed_requirement(
            tenant,
            workspace,
            title="System Monitoring",
            description="x",
            uid="REQ-ORD-3",
        )
        try:
            result = SearchService().search(
                query="Monitoring",
                ctx=ctx,
                workspace_id=workspace.id,
                type_filter=["Requirement"],
            )
        finally:
            TenantContext.clear_tenant()

        scores = {h.id: h.relevance_score for h in result.results}
        assert scores[str(exact.id)] > scores[str(prefix.id)] > scores[str(substring.id)]
        assert all(0.0 <= score <= 1.0 for score in scores.values())
        assert [h.id for h in result.results] == [
            str(exact.id),
            str(prefix.id),
            str(substring.id),
        ]

    def test_other_tenant_rows_stay_invisible(self):
        """Tenant isolation must hold for the new lexical pass too."""
        from persistence.tenancy import TenantContext

        tenant_a, workspace_a, _ = _seed_workspace("search-lex-tenant-a")
        _seed_requirement(
            tenant_a,
            workspace_a,
            title="QA-AI Geheim",
            description="Fremder Mandant.",
            uid="REQ-A-1",
        )
        TenantContext.clear_tenant()
        _, workspace_b, ctx_b = _seed_workspace("search-lex-tenant-b")
        try:
            result = SearchService().search(query="QA-AI", ctx=ctx_b)
        finally:
            TenantContext.clear_tenant()

        assert result.total_count == 0

    def test_single_character_query_skips_lexical_pass(self):
        """A 1-char needle would substring-match nearly every row."""
        from persistence.tenancy import TenantContext

        tenant, workspace, ctx = _seed_workspace("search-lex-short")
        _seed_requirement(
            tenant,
            workspace,
            title="Abc",
            description="Beschreibung.",
            uid="REQ-SHORT-1",
        )
        try:
            result = SearchService().search(
                query="A", ctx=ctx, workspace_id=workspace.id
            )
        finally:
            TenantContext.clear_tenant()

        assert result.total_count == 0

    def test_glossary_term_is_searchable_by_its_term_column(self):
        """GlossaryTerm stores its name in `term`, not `title` — the type
        mapping has to know that, otherwise the SQL blows up and the type
        silently degrades to zero hits."""
        from persistence.models import GlossaryTerm
        from persistence.tenancy import TenantContext

        tenant, workspace, ctx = _seed_workspace("search-lex-glossary")
        term = GlossaryTerm.objects.create(
            tenant=tenant,
            workspace=workspace,
            term="QA-AI Pipeline",
            definition="Die Prüfstrecke.",
        )
        try:
            result = SearchService().search(
                query="QA-AI",
                ctx=ctx,
                workspace_id=workspace.id,
                type_filter=["GlossaryTerm"],
            )
        finally:
            TenantContext.clear_tenant()

        assert [h.id for h in result.results] == [str(term.id)]
        assert result.results[0].title == "QA-AI Pipeline"

    def test_like_wildcards_in_query_are_matched_literally(self):
        from persistence.tenancy import TenantContext

        tenant, workspace, ctx = _seed_workspace("search-lex-wildcard")
        _seed_requirement(
            tenant,
            workspace,
            title="Kein Prozentzeichen hier",
            description="Beschreibung.",
            uid="REQ-WILD-1",
        )
        try:
            result = SearchService().search(
                query="%z%", ctx=ctx, workspace_id=workspace.id
            )
        finally:
            TenantContext.clear_tenant()

        assert result.total_count == 0


# ---------- custom_fields from the backing Artifact (#934 WS1 follow-up) ----------


@pytest.mark.django_db(transaction=True)
class TestSearchCustomFieldsBackingArtifact:
    """Increment 1 required ``artifact.search`` to carry the backing Artifact's
    ``custom_fields``. Every type joined ``pl_artifact`` except ChangeRequest
    and GlossaryTerm, whose search rows have a nullable Artifact FK and so were
    silently left with ``{}``. These pin the two previously-missing types,
    including the NULL-FK row that a LEFT JOIN (not an inner join) must keep.
    """

    def test_glossary_term_hit_carries_backing_artifact_custom_fields(self):
        from persistence.models import Artifact, GlossaryTerm
        from persistence.tenancy import TenantContext

        tenant, workspace, ctx = _seed_workspace("search-cf-glossary")
        artifact = Artifact.objects.create(
            tenant=tenant,
            workspace=workspace,
            artifact_type="GlossaryTerm",
            custom_fields={"ws0_probe": "glossary-value"},
        )
        term = GlossaryTerm.objects.create(
            tenant=tenant,
            workspace=workspace,
            artifact=artifact,
            term="QA-AI Pipeline",
            definition="Die Prüfstrecke.",
        )
        try:
            result = SearchService().search(
                query="QA-AI",
                ctx=ctx,
                workspace_id=workspace.id,
                type_filter=["GlossaryTerm"],
            )
        finally:
            TenantContext.clear_tenant()

        assert [h.id for h in result.results] == [str(term.id)]
        assert result.results[0].custom_fields == {"ws0_probe": "glossary-value"}

    def test_change_request_hit_carries_backing_artifact_custom_fields(self):
        from persistence.models import Artifact, ChangeRequest
        from persistence.tenancy import TenantContext

        tenant, workspace, ctx = _seed_workspace("search-cf-change-request")
        artifact = Artifact.objects.create(
            tenant=tenant,
            workspace=workspace,
            artifact_type="ChangeRequest",
            custom_fields={"ws0_probe": "cr-value"},
        )
        cr = ChangeRequest.objects.create(
            tenant=tenant,
            workspace_id=workspace.id,
            artifact=artifact,
            title="QA-AI Rollout",
        )
        try:
            result = SearchService().search(
                query="QA-AI",
                ctx=ctx,
                workspace_id=workspace.id,
                type_filter=["ChangeRequest"],
            )
        finally:
            TenantContext.clear_tenant()

        assert [h.id for h in result.results] == [str(cr.id)]
        assert result.results[0].custom_fields == {"ws0_probe": "cr-value"}

    def test_row_without_backing_artifact_is_kept_and_empty(self):
        """The FK is nullable, so the join must be a LEFT JOIN: a CR/term with
        no backing Artifact still has to be found, with empty custom_fields."""
        from persistence.models import GlossaryTerm
        from persistence.tenancy import TenantContext

        tenant, workspace, ctx = _seed_workspace("search-cf-no-artifact")
        term = GlossaryTerm.objects.create(
            tenant=tenant,
            workspace=workspace,
            term="QA-AI Ohne Artefakt",
            definition="Kein backing Artifact.",
        )
        try:
            result = SearchService().search(
                query="QA-AI",
                ctx=ctx,
                workspace_id=workspace.id,
                type_filter=["GlossaryTerm"],
            )
        finally:
            TenantContext.clear_tenant()

        assert [h.id for h in result.results] == [str(term.id)]
        assert result.results[0].custom_fields == {}
