"""Issue #1965 — artifact.search hybrid/vector latency guards.

Covers the three latency changes without weakening any relevance assertion:

* a slow embedding degrades to the keyword legs (and says so on the wire);
* the per-type semantic candidate pool follows the requested page window;
* repeated searches reuse one cached query embedding;
* timing is instrumented for diagnosis.
"""
from __future__ import annotations

import logging
import time
from unittest.mock import patch

import pytest

from application import search_service as ss
from application.search_service import SearchService, _semantic_candidate_limit
from persistence.tests.factories import (
    active_tenant,
    editor_ctx,
    make_requirement,
    make_workspace,
)


@pytest.mark.django_db
class TestEmbeddingTimeoutFallback:
    def test_hybrid_serves_keyword_hits_when_embedding_times_out(
        self, monkeypatch, caplog
    ):
        """The request thread is released at the deadline, not after the slow
        provider finishes; the exact-title hit still comes back via the
        fulltext/lexical legs and the missing semantic leg is reported."""
        def _slow_embed(_text: str) -> list[float]:
            time.sleep(0.6)
            return [0.3] * 384

        monkeypatch.setattr(ss, "_embedding_timeout_seconds", lambda: 0.05)

        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            req = make_requirement(
                ws, title="Rest API timeout probe", description="keyword marker"
            )
            ctx = editor_ctx(tenant, ws)
            started = time.perf_counter()
            with (
                caplog.at_level(logging.WARNING, logger="application.search_service"),
                patch(
                    "application.search_service.generate_embedding",
                    side_effect=_slow_embed,
                ),
            ):
                result = SearchService().search(
                    "Rest API timeout probe",
                    ctx,
                    workspace_id=ws.id,
                    type_filter=["Requirement"],
                    mode="hybrid",
                )
            elapsed = time.perf_counter() - started

        assert any(hit.id == str(req.id) for hit in result.results)
        assert result.degraded is True
        assert result.degraded_reason == ss.DEGRADED_EMBEDDING_TIMEOUT
        # The provider sleeps 0.6s; the request must not wait for it.
        assert elapsed < 0.5
        assert any("timed out" in rec.message for rec in caplog.records)

    def test_vector_mode_degrades_to_empty_results_on_timeout(self, monkeypatch):
        """Vector mode has no keyword legs to fall back to; it must still
        return promptly and report why the result set is empty."""
        def _slow_embed(_text: str) -> list[float]:
            time.sleep(0.6)
            return [0.3] * 384

        monkeypatch.setattr(ss, "_embedding_timeout_seconds", lambda: 0.05)

        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            ctx = editor_ctx(tenant, ws)
            # Patch the provider too: the abandoned worker must not try to
            # import a real heavy embedding backend after pytest exits.
            with patch(
                "application.search_service.generate_embedding",
                side_effect=_slow_embed,
            ):
                result = SearchService().search(
                    "no keyword overlap here",
                    ctx,
                    workspace_id=ws.id,
                    type_filter=["Requirement"],
                    mode="vector",
                )

        assert result.results == []
        assert result.degraded is True
        assert result.degraded_reason == ss.DEGRADED_EMBEDDING_TIMEOUT

    def test_keyword_mode_never_calls_the_embedding_path(self, monkeypatch):
        """No weakening of the T-A3-1 contract: keyword skips both gates."""
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            ctx = editor_ctx(tenant, ws)
            with patch(
                "application.search_service.generate_embedding"
            ) as embed_spy:
                SearchService().search(
                    "rest", ctx, workspace_id=ws.id, mode="keyword"
                )

        embed_spy.assert_not_called()


class TestSemanticCandidatePool:
    def test_pool_follows_page_window_and_is_capped(self):
        # Default page: 1*20*2 = 40 (down from the fixed 50).
        assert _semantic_candidate_limit(1, 20) == 40
        # Small page: floor keeps a useful pool instead of 5 candidates.
        assert _semantic_candidate_limit(1, 5) == 20
        # Large page: historical ceiling, so worst case is unchanged.
        assert _semantic_candidate_limit(1, 100) == 50
        # Page 2 of a 20-page window needs the full 50.
        assert _semantic_candidate_limit(2, 20) == 50

    @pytest.mark.django_db
    def test_search_threads_bounded_pool_into_the_semantic_pass(self, monkeypatch):
        seen: dict[str, int | None] = {}

        def _semantic(_entity_type, *_args, **kwargs):
            seen["semantic_limit"] = kwargs.get("semantic_limit")
            return []

        monkeypatch.setattr(ss, "_run_semantic_query", _semantic)
        monkeypatch.setattr(
            ss, "generate_embedding", lambda _text: [0.3] * 384
        )

        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            ctx = editor_ctx(tenant, ws)
            SearchService().search(
                "probe",
                ctx,
                workspace_id=ws.id,
                type_filter=["Requirement"],
                mode="hybrid",
                limit=5,
            )

        assert seen["semantic_limit"] == 20


@pytest.mark.django_db
class TestReuseAndInstrumentation:
    def test_two_searches_with_same_query_generate_one_embedding(self, monkeypatch):
        """The cache lives in ``generate_embedding``; exercise the real path
        (not a patched search-level stub) through two complete searches."""
        from llm_adapter import embedding_service as es

        es.clear_embedding_cache()
        config = es.EmbeddingProviderConfig(provider_name="mock")
        monkeypatch.setattr(es, "_read_config", lambda: config)
        calls: list[str] = []

        def _embed(_self, text):
            calls.append(text)
            return [0.3] * 384

        monkeypatch.setattr(es.MockEmbeddingProvider, "embed", _embed)

        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            ctx = editor_ctx(tenant, ws)
            for _ in range(2):
                SearchService().search(
                    "cache probe",
                    ctx,
                    workspace_id=ws.id,
                    type_filter=["Requirement"],
                    mode="hybrid",
                )

        assert calls == ["cache probe"]
        es.clear_embedding_cache()

    def test_timing_is_logged(self, monkeypatch, caplog):
        monkeypatch.setattr(
            ss, "generate_embedding", lambda _text: [0.3] * 384
        )
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            ctx = editor_ctx(tenant, ws)
            with caplog.at_level(logging.DEBUG, logger="application.search_service"):
                SearchService().search(
                    "timing probe",
                    ctx,
                    workspace_id=ws.id,
                    type_filter=["Requirement"],
                    mode="hybrid",
                )

        assert any("artifact.search timing" in rec.message for rec in caplog.records)
