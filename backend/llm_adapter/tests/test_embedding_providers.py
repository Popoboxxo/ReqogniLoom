from unittest.mock import MagicMock, patch

import pytest

from llm_adapter.embedding_service import (
    EMBEDDING_PROVIDER_REGISTRY,
    EmbeddingProviderConfig,
    _read_config,
    generate_embedding,
    get_embedding_provider,
)


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
        assert len(result) == 384  # mock provider dimension, matches sentence-transformers default

    def test_empty_text_returns_none(self):
        assert generate_embedding("") is None
        assert generate_embedding("   ") is None


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
