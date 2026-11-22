"""Issue #1965 — bounded, TTL'd query-embedding cache.

`artifact.search` (hybrid/vector) used to call ``generate_embedding(query)``
uncached on every request, paying full model inference each time. These tests
pin the cache contract: identical text under the same resolved config is
computed once, config changes invalidate it, entries expire and are LRU-bounded,
failures are never cached, and callers cannot mutate a cached vector in place.
"""
from __future__ import annotations

import time

import pytest

from llm_adapter import embedding_service as es


@pytest.fixture(autouse=True)
def _isolated_cache(monkeypatch):
    """Every test starts and ends with an empty cache and known limits."""
    es.clear_embedding_cache()
    monkeypatch.setattr(es, "EMBEDDING_QUERY_CACHE_TTL_SECONDS", 60.0)
    monkeypatch.setattr(es, "EMBEDDING_QUERY_CACHE_MAX_ENTRIES", 256)
    yield
    es.clear_embedding_cache()


@pytest.fixture
def mock_config(monkeypatch):
    """Bypass the DB-backed settings override; all tests use the mock provider."""
    config = es.EmbeddingProviderConfig(provider_name="mock")
    monkeypatch.setattr(es, "_read_config", lambda: config)
    return config


class TestQueryEmbeddingCache:
    def test_identical_text_is_embedded_once(self, monkeypatch, mock_config):
        calls: list[str] = []

        def _embed(self, text):  # provider method seam
            calls.append(text)
            return [0.25, 0.5]

        monkeypatch.setattr(es.MockEmbeddingProvider, "embed", _embed)

        first = es.generate_embedding("repeated query")
        second = es.generate_embedding("repeated query")

        assert calls == ["repeated query"]
        assert first == [0.25, 0.5]
        assert second == first

    def test_different_texts_are_not_confused(self, monkeypatch, mock_config):
        calls: list[str] = []

        def _embed(self, text):
            calls.append(text)
            return [float(len(text))]

        monkeypatch.setattr(es.MockEmbeddingProvider, "embed", _embed)

        es.generate_embedding("alpha")
        es.generate_embedding("beta")

        assert calls == ["alpha", "beta"]

    def test_config_change_invalidates_cached_vector(self, monkeypatch, mock_config):
        """A model/provider switch must never serve a stale-model vector."""
        calls: list[str] = []

        def _embed(self, text):
            calls.append(text)
            return [0.5]

        monkeypatch.setattr(es.MockEmbeddingProvider, "embed", _embed)

        es.generate_embedding("same text")
        mock_config.model_name = "a-different-model"
        es.generate_embedding("same text")

        assert len(calls) == 2

    def test_entries_expire_after_ttl(self, monkeypatch, mock_config):
        monkeypatch.setattr(es, "EMBEDDING_QUERY_CACHE_TTL_SECONDS", 0.01)
        calls: list[str] = []

        def _embed(self, text):
            calls.append(text)
            return [0.5]

        monkeypatch.setattr(es.MockEmbeddingProvider, "embed", _embed)

        es.generate_embedding("short lived")
        time.sleep(0.03)
        es.generate_embedding("short lived")

        assert len(calls) == 2

    def test_cache_is_lru_bounded(self, monkeypatch, mock_config):
        monkeypatch.setattr(es, "EMBEDDING_QUERY_CACHE_MAX_ENTRIES", 2)
        calls: list[str] = []

        def _embed(self, text):
            calls.append(text)
            return [0.5]

        monkeypatch.setattr(es.MockEmbeddingProvider, "embed", _embed)

        for text in ("one", "two", "three"):
            es.generate_embedding(text)

        assert len(es._embedding_cache) == 2
        # `one` was the least-recently-used entry and must have been evicted.
        es.generate_embedding("one")
        assert calls == ["one", "two", "three", "one"]

    def test_failures_are_not_cached(self, monkeypatch, mock_config):
        """A transient provider failure must be retryable on the next call."""
        responses = [None, [0.75]]

        def _embed(self, text):
            return responses.pop(0)

        monkeypatch.setattr(es.MockEmbeddingProvider, "embed", _embed)

        assert es.generate_embedding("retry me") is None
        assert es.generate_embedding("retry me") == [0.75]
        assert responses == []

    def test_cached_vector_is_returned_as_a_copy(self, monkeypatch, mock_config):
        def _embed(self, text):
            return [0.5]

        monkeypatch.setattr(es.MockEmbeddingProvider, "embed", _embed)

        first = es.generate_embedding("immutable")
        first[0] = 999.0

        assert es.generate_embedding("immutable") == [0.5]

    def test_clear_embedding_cache_drops_entries(self, monkeypatch, mock_config):
        calls: list[str] = []

        def _embed(self, text):
            calls.append(text)
            return [0.5]

        monkeypatch.setattr(es.MockEmbeddingProvider, "embed", _embed)

        es.generate_embedding("flush me")
        es.clear_embedding_cache()
        es.generate_embedding("flush me")

        assert len(calls) == 2
