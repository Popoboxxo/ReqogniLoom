import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from llm_adapter.embedding_service import (
    EMBEDDING_PROVIDER_REGISTRY,
    EmbeddingProviderConfig,
    _read_config,
    generate_embedding,
    get_embedding_provider,
)
from persistence.embedding_dimensions import EMBEDDING_VECTOR_DIMENSIONS


class TestEmbeddingProviderRegistry:
    def test_registry_has_sentence_transformers_ollama_openai_mock(self):
        assert set(EMBEDDING_PROVIDER_REGISTRY.keys()) == {
            "sentence-transformers", "ollama", "openai", "mock",
        }

    def test_default_provider_is_sentence_transformers(self, monkeypatch):
        monkeypatch.delenv("EMBEDDING_PROVIDER", raising=False)
        provider = get_embedding_provider()
        assert provider.__class__.__name__ == "SentenceTransformersEmbeddingProvider"

    def test_env_var_selects_provider(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        provider = get_embedding_provider()
        assert provider.__class__.__name__ == "MockEmbeddingProvider"

    def test_unknown_provider_raises(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "does-not-exist")
        with pytest.raises(ValueError, match="unknown embedding provider"):
            get_embedding_provider()

    def test_mock_provider_is_deterministic(self):
        config = EmbeddingProviderConfig(provider_name="mock")
        provider = get_embedding_provider(config)
        assert provider.embed("hello") == provider.embed("hello")
        assert provider.embed("hello") != provider.embed("world")

    def test_generate_embedding_delegates_to_registry(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        result = generate_embedding("some text")
        assert result is not None
        # #1149: the produced width follows EMBEDDING_VECTOR_DIMENSIONS
        # (384 by default, 768 when the environment says so) instead of a
        # hardcoded literal that can drift from the embedding columns.
        assert len(result) == EMBEDDING_VECTOR_DIMENSIONS

    def test_empty_text_returns_none(self):
        assert generate_embedding("") is None
        assert generate_embedding("   ") is None


class TestEmbeddingDimensionsFollowConfiguration:
    """Issue #1149: mock/sentence-transformers emit the configured width.

    Both providers hardcoded 384 while every embedding column is sized from
    ``EMBEDDING_VECTOR_DIMENSIONS``. With the ambient 768 that made every
    test/dev embedding write fail its dimension guard and log
    ``warn_dimension_mismatch``. These tests assert the *produced length*, not
    just the class constant, so a future regression cannot hide behind a
    matching attribute.
    """

    def test_mock_provider_emits_the_configured_width(self):
        from llm_adapter.embedding_service import MockEmbeddingProvider

        assert MockEmbeddingProvider.dimensions == EMBEDDING_VECTOR_DIMENSIONS
        provider = get_embedding_provider(EmbeddingProviderConfig(provider_name="mock"))
        vector = provider.embed("prove the configured width")
        assert vector is not None
        assert len(vector) == EMBEDDING_VECTOR_DIMENSIONS

    def test_sentence_transformers_reports_the_configured_width(self):
        from llm_adapter.embedding_service import (
            SentenceTransformersEmbeddingProvider,
        )

        assert (
            SentenceTransformersEmbeddingProvider.dimensions
            == EMBEDDING_VECTOR_DIMENSIONS
        )

    def test_fit_vector_to_dimensions_pads_and_truncates(self):
        from llm_adapter.embedding_service import _fit_vector_to_dimensions

        assert _fit_vector_to_dimensions([1.0, 2.0], 4) == [1.0, 2.0, 0.0, 0.0]
        assert _fit_vector_to_dimensions([1.0, 2.0, 3.0], 2) == [1.0, 2.0]
        assert _fit_vector_to_dimensions([1.0], 1) == [1.0]

    def test_zero_padding_preserves_cosine_similarity(self):
        """The padding strategy is only sound because zero components change
        neither the dot product nor the L2 norm. Assert it, do not assume it."""
        from llm_adapter.embedding_service import _fit_vector_to_dimensions

        def cosine(a, b):
            dot = sum(x * y for x, y in zip(a, b))
            norm_a = sum(x * x for x in a) ** 0.5
            norm_b = sum(y * y for y in b) ** 0.5
            return dot / (norm_a * norm_b)

        a = [0.2, -0.5, 0.9, 0.1]
        b = [-0.3, 0.8, 0.4, -0.6]
        assert cosine(
            _fit_vector_to_dimensions(a, 8),
            _fit_vector_to_dimensions(b, 8),
        ) == pytest.approx(cosine(a, b))


#: Run in a fresh interpreter so ``EMBEDDING_VECTOR_DIMENSIONS`` is bound at
#: import time exactly as a container would bind it (mirrors the subprocess
#: pattern in ``persistence/tests/test_embedding_dimensions_env.py``).
_FRESH_PROCESS_CODE = """
from llm_adapter.embedding_service import (
    EmbeddingProviderConfig,
    MockEmbeddingProvider,
    SentenceTransformersEmbeddingProvider,
    _fit_vector_to_dimensions,
)

mock = MockEmbeddingProvider(EmbeddingProviderConfig(provider_name="mock"))
print(f"MOCK_DIMENSIONS={mock.dimensions}")
print(f"MOCK_VECTOR_LENGTH={len(mock.embed('configured width'))}")

st = SentenceTransformersEmbeddingProvider(
    EmbeddingProviderConfig(provider_name="sentence-transformers")
)
print(f"ST_DIMENSIONS={st.dimensions}")
# all-MiniLM-L6-v2 emits 384 native components; emulate that without loading
# the model and assert the adapter pads to the configured width.
print(f"ST_FITTED_LENGTH={len(_fit_vector_to_dimensions([0.1] * 384, st.dimensions))}")
"""


def _run_fresh_process(embedding_dimensions: str | None) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    if embedding_dimensions is None:
        env.pop("EMBEDDING_VECTOR_DIMENSIONS", None)
    else:
        env["EMBEDDING_VECTOR_DIMENSIONS"] = embedding_dimensions
    return subprocess.run(
        [sys.executable, "-c", _FRESH_PROCESS_CODE],
        # ``backend/`` — llm_adapter + persistence are importable from there.
        cwd=Path(__file__).resolve().parents[2],
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )


class TestFreshProcessFollowsConfiguredWidth:
    def test_768_reaches_mock_and_sentence_transformers(self):
        result = _run_fresh_process("768")

        assert result.returncode == 0, result.stderr
        observed = {}
        for line in result.stdout.splitlines():
            if "=" in line:
                key, _, value = line.partition("=")
                observed[key] = int(value)
        assert observed["MOCK_DIMENSIONS"] == 768
        assert observed["MOCK_VECTOR_LENGTH"] == 768
        assert observed["ST_DIMENSIONS"] == 768
        assert observed["ST_FITTED_LENGTH"] == 768

    def test_default_process_is_384(self):
        result = _run_fresh_process(None)

        assert result.returncode == 0, result.stderr
        assert "MOCK_VECTOR_LENGTH=384" in result.stdout
        assert "ST_FITTED_LENGTH=384" in result.stdout


class TestSentenceTransformersModelCache:
    """The class-level model singleton must be KEYED by model name.

    Without the key, an ``EMBEDDING_MODEL_NAME`` change (env var or a
    ``SystemMemorySettings`` override made through the admin UI) is silently
    ignored by every worker that already loaded some model, while the UI
    reports the new name as active (final whole-branch review I-2).
    """

    @staticmethod
    def _fake_sentence_transformers(monkeypatch, loaded: list[str]):
        """Install a fake ``sentence_transformers`` module recording every
        model construction, so no real (~90MB) model is downloaded here."""
        import sys
        import types

        module = types.ModuleType("sentence_transformers")

        class _FakeSentenceTransformer:
            def __init__(self, model_name):
                loaded.append(model_name)
                self.model_name = model_name

        module.SentenceTransformer = _FakeSentenceTransformer
        monkeypatch.setitem(sys.modules, "sentence_transformers", module)

    def test_same_model_name_is_loaded_once(self, monkeypatch):
        from llm_adapter.embedding_service import SentenceTransformersEmbeddingProvider

        monkeypatch.setattr(SentenceTransformersEmbeddingProvider, "_model", None)
        monkeypatch.setattr(SentenceTransformersEmbeddingProvider, "_loaded_model_name", None)
        loaded: list[str] = []
        self._fake_sentence_transformers(monkeypatch, loaded)

        cfg = EmbeddingProviderConfig(provider_name="sentence-transformers", model_name="model-a")
        SentenceTransformersEmbeddingProvider(cfg)._get_model()
        SentenceTransformersEmbeddingProvider(cfg)._get_model()

        assert loaded == ["model-a"]

    def test_changed_model_name_triggers_a_reload(self, monkeypatch):
        from llm_adapter.embedding_service import SentenceTransformersEmbeddingProvider

        monkeypatch.setattr(SentenceTransformersEmbeddingProvider, "_model", None)
        monkeypatch.setattr(SentenceTransformersEmbeddingProvider, "_loaded_model_name", None)
        loaded: list[str] = []
        self._fake_sentence_transformers(monkeypatch, loaded)

        first = SentenceTransformersEmbeddingProvider(
            EmbeddingProviderConfig(provider_name="sentence-transformers", model_name="model-a")
        )
        first._get_model()

        second = SentenceTransformersEmbeddingProvider(
            EmbeddingProviderConfig(provider_name="sentence-transformers", model_name="model-b")
        )
        model = second._get_model()

        assert loaded == ["model-a", "model-b"]
        assert model.model_name == "model-b"
        assert SentenceTransformersEmbeddingProvider._loaded_model_name == "model-b"


class TestEmbeddingServiceDbOverride:
    @pytest.mark.django_db
    def test_db_override_wins_over_env(self, monkeypatch):
        from memory.models import SystemMemorySettings

        monkeypatch.setenv("EMBEDDING_PROVIDER", "sentence-transformers")
        SystemMemorySettings.objects.create(embedding_provider="mock")
        cfg = _read_config()
        assert cfg.provider_name == "mock"

    @pytest.mark.django_db
    def test_falls_back_to_env_when_no_override_row(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        cfg = _read_config()
        assert cfg.provider_name == "mock"

    @pytest.mark.django_db
    def test_falls_back_to_env_when_field_is_null(self, monkeypatch):
        from memory.models import SystemMemorySettings

        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        SystemMemorySettings.objects.create()  # every field NULL
        cfg = _read_config()
        assert cfg.provider_name == "mock"
