"""Issue #276 — environment-variable naming contract for ProviderConfig.

Finding 2 (high): ``docker-compose.yml`` (and ``.env.example`` /
``deployment/docker-compose.ghcr.yml``) pass ``LLM_MODEL`` and
``LLM_BASE_URL`` through to the backend, but ``_read_env_config`` only read
``LLM_MODEL_NAME`` / ``LLM_API_BASE_URL``. Every model / base-URL value a
deployment configured in ``.env`` was therefore silently dropped.

The fix accepts BOTH spellings, with the historical ``LLM_MODEL_NAME`` /
``LLM_API_BASE_URL`` taking precedence so existing environments that set them
keep their behaviour. ``OllamaProvider`` / ``OpencodeGoProvider`` already read
``LLM_MODEL`` directly — that is the precedent for the shorter alias.
"""
from __future__ import annotations

import pytest

from llm_adapter.providers import _read_env_config

_MODEL_VARS = ("LLM_MODEL_NAME", "LLM_MODEL")
_BASE_URL_VARS = ("LLM_API_BASE_URL", "LLM_BASE_URL")


@pytest.fixture(autouse=True)
def _clean_llm_env(monkeypatch):
    """Start every test from an environment with no model/base-url vars set."""
    for name in (*_MODEL_VARS, *_BASE_URL_VARS):
        monkeypatch.delenv(name, raising=False)


# ---------------------------------------------------------------------------
# model name
# ---------------------------------------------------------------------------


def test_model_name_read_from_llm_model_name(monkeypatch):
    """The historical spelling keeps working (no regression)."""
    monkeypatch.setenv("LLM_MODEL_NAME", "claude-3-5-sonnet-20241022")

    assert _read_env_config().model_name == "claude-3-5-sonnet-20241022"


def test_model_name_falls_back_to_llm_model(monkeypatch):
    """[#276] ``LLM_MODEL`` — the name docker-compose.yml passes — is honoured."""
    monkeypatch.setenv("LLM_MODEL", "llama3.1")

    assert _read_env_config().model_name == "llama3.1"


def test_llm_model_name_wins_over_llm_model(monkeypatch):
    """When both are set the explicit ``LLM_MODEL_NAME`` takes precedence."""
    monkeypatch.setenv("LLM_MODEL_NAME", "gpt-4o")
    monkeypatch.setenv("LLM_MODEL", "llama3.1")

    assert _read_env_config().model_name == "gpt-4o"


def test_empty_llm_model_name_falls_through_to_llm_model(monkeypatch):
    """An empty (present-but-blank) value must not shadow the alias.

    ``.env.example`` ships ``LLM_MODEL=`` / ``LLM_MODEL_NAME`` unset, so the
    "defined but empty" case is the common one — ``os.environ.get(name, x)``
    would return "" here, which is why the fix uses ``or``.
    """
    monkeypatch.setenv("LLM_MODEL_NAME", "")
    monkeypatch.setenv("LLM_MODEL", "llama3.1")

    assert _read_env_config().model_name == "llama3.1"


def test_model_name_defaults_to_empty_string():
    """With neither variable set the config falls back to the empty string.

    ``_BaseHttpProvider.__init__`` then applies the class-level ``MODEL_NAME``
    default, so unconfigured deployments are unaffected.
    """
    assert _read_env_config().model_name == ""


# ---------------------------------------------------------------------------
# base url
# ---------------------------------------------------------------------------


def test_base_url_read_from_llm_api_base_url(monkeypatch):
    """The historical spelling keeps working (no regression)."""
    monkeypatch.setenv("LLM_API_BASE_URL", "http://ollama:11434")

    assert _read_env_config().api_base_url == "http://ollama:11434"


def test_base_url_falls_back_to_llm_base_url(monkeypatch):
    """[#276] ``LLM_BASE_URL`` — the name docker-compose.yml passes — is honoured."""
    monkeypatch.setenv("LLM_BASE_URL", "http://localhost:11434")

    assert _read_env_config().api_base_url == "http://localhost:11434"


def test_llm_api_base_url_wins_over_llm_base_url(monkeypatch):
    """When both are set the explicit ``LLM_API_BASE_URL`` takes precedence."""
    monkeypatch.setenv("LLM_API_BASE_URL", "http://explicit:11434")
    monkeypatch.setenv("LLM_BASE_URL", "http://fallback:11434")

    assert _read_env_config().api_base_url == "http://explicit:11434"


def test_empty_llm_api_base_url_falls_through_to_llm_base_url(monkeypatch):
    """An empty (present-but-blank) value must not shadow the alias."""
    monkeypatch.setenv("LLM_API_BASE_URL", "")
    monkeypatch.setenv("LLM_BASE_URL", "http://localhost:11434")

    assert _read_env_config().api_base_url == "http://localhost:11434"


def test_base_url_defaults_to_none():
    """With neither variable set ``api_base_url`` stays ``None``.

    ``OllamaProvider`` relies on this to raise ``LlmNotConfiguredError``
    instead of POSTing to an empty URL.
    """
    assert _read_env_config().api_base_url is None
