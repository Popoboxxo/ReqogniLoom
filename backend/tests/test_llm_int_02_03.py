"""INT-02 / INT-03 regression tests (systemaudit 2026-09).

Focused, no-network regression tests for two work units of the INT epic:

INT-02 — LLM defaults / provider selection (findings 052, 053, 058, N8, 346):
  * malformed numeric env vars (``LLM_TIMEOUT`` & co.) must not raise;
  * a LlmSettings DB/RLS failure is logged at >= WARNING (not DEBUG-swallowed);
  * the Ollama misconfiguration error names the env var actually honoured;
  * ``azure`` is selectable through the DB enum / REST choice field;
  * provider model defaults are no longer the retired ids.

INT-03 — LLM parser hardening, retry amplification, usage (findings 057, 055,
059, 061, 062, 054):
  * ``decompose_requirement`` degrades gracefully on a malformed provider body
    for every HTTP provider (no raw ``JSONDecodeError`` text escapes);
  * every SDK client is constructed with ``max_retries=0`` so the SDK cannot
    multiply the policy retry budget (max 4 attempts x 1 SDK attempt);
  * Anthropic ``usage=None`` is handled safely (no ``AttributeError``);
  * Ollama returns ``prompt_eval_count + eval_count`` (input no longer lost);
  * a mock call is recorded with ``provider=mock``.

All provider transports are mocked (fake SDK modules / monkeypatched ``_chat``);
no real network access and no provider SDK is required.
"""
from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch

import pytest

from llm_adapter.providers import (
    AnthropicProvider,
    AzureOpenAiProvider,
    LlmNotConfiguredError,
    MockLlmProvider,
    OllamaProvider,
    OpenAiProvider,
    OpencodeGoProvider,
    ProviderConfig,
    _read_env_config,
)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


def _recording_anthropic_module(
    captured: dict,
    *,
    text: str = '{"score": 0.5, "suggestions": [], "children": []}',
    usage=None,
) -> types.ModuleType:
    """Fake ``anthropic`` module recording the ``Anthropic()`` kwargs."""

    def _ctor(**kwargs):
        captured["kwargs"] = kwargs
        client = MagicMock()
        message = MagicMock()
        message.content = [MagicMock(text=text)]
        # Explicitly set ``usage`` so ``hasattr(message, "usage")`` is True even
        # when it is None (the finding-059 trigger).
        message.usage = usage
        client.messages.create.return_value = message
        return client

    module = types.ModuleType("anthropic")
    module.Anthropic = _ctor
    return module


def _recording_openai_module(
    captured: dict, *, attr: str = "OpenAI", text: str = "ok"
) -> types.ModuleType:
    """Fake ``openai`` module exposing a recording ``OpenAI``/``AzureOpenAI``."""

    def _ctor(**kwargs):
        captured["kwargs"] = kwargs
        client = MagicMock()
        response = MagicMock()
        response.choices = [MagicMock(message=MagicMock(content=text))]
        response.usage = MagicMock(total_tokens=2)
        client.chat.completions.create.return_value = response
        return client

    module = types.ModuleType("openai")
    setattr(module, attr, _ctor)
    return module


def _chat_based_providers():
    """The four providers whose parsing goes through ``_chat``/``_invoke_chat``."""
    return [
        OpenAiProvider(ProviderConfig(provider_name="openai")),
        OllamaProvider(
            ProviderConfig(
                provider_name="ollama", api_base_url="http://localhost:11434"
            )
        ),
        AzureOpenAiProvider(
            ProviderConfig(provider_name="azure", azure_deployment="dep")
        ),
        OpencodeGoProvider(ProviderConfig(provider_name="opencode_go")),
    ]


# ===========================================================================
# INT-02 — configuration / provider selection
# ===========================================================================


def test_invalid_llm_timeout_falls_back_to_default(monkeypatch):
    """A non-numeric LLM_TIMEOUT must not raise (INT-02, providers.py:113)."""
    monkeypatch.setenv("LLM_TIMEOUT", "not-a-number")
    assert _read_env_config().timeout == 30


def test_blank_llm_timeout_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("LLM_TIMEOUT", "   ")
    assert _read_env_config().timeout == 30


def test_invalid_mock_delay_and_error_rate_fall_back(monkeypatch):
    """Malformed float env vars degrade to defaults (INT-02, :125-126)."""
    monkeypatch.setenv("MOCK_LLM_DELAY", "soon")
    monkeypatch.setenv("MOCK_LLM_ERROR_RATE", "lots")
    cfg = _read_env_config()
    assert cfg.mock_delay == 0.0
    assert cfg.mock_error_rate == 0.0


def test_db_settings_failure_is_logged_at_warning(monkeypatch, caplog):
    """A DB/RLS failure in the settings overlay is observable (INT-02)."""
    import persistence.models as pm

    class _BoomManager:
        def first(self):
            raise RuntimeError("database unavailable")

    class _BoomLlmSettings:
        objects = _BoomManager()

    monkeypatch.setattr(pm, "LlmSettings", _BoomLlmSettings)

    from llm_adapter.providers import _apply_db_settings

    with caplog.at_level("WARNING", logger="llm_adapter.providers"):
        cfg = _apply_db_settings(ProviderConfig(provider_name="mock"))

    # Still non-fatal: the env config is preserved ...
    assert cfg.provider_name == "mock"
    # ... but the failure is no longer silent.
    assert any(
        "LlmSettings lookup failed" in record.getMessage()
        for record in caplog.records
    )


def test_ollama_error_names_the_honoured_env_var():
    """The Ollama error must name LLM_BASE_URL, not the unused OLLAMA_BASE_URL."""
    with pytest.raises(LlmNotConfiguredError) as exc:
        OllamaProvider(ProviderConfig(provider_name="ollama", api_base_url=""))
    message = str(exc.value)
    assert "LLM_BASE_URL" in message
    assert "OLLAMA_BASE_URL" not in message


def test_azure_is_selectable_through_db_enum_and_rest_choices():
    """INT-02 (finding 058): azure must be a first-class selectable provider."""
    from application.settings_service import SettingsService
    from persistence.models import LlmProvider

    assert "azure" in LlmProvider.values
    assert "azure" in SettingsService.provider_choices()


def test_provider_model_defaults_are_not_retired_ids():
    """INT-02 (findings 052/053): defaults must not be retired model ids."""
    assert AnthropicProvider.MODEL_NAME != "claude-3-opus-20240229"
    assert OpenAiProvider.MODEL_NAME != "gpt-4"
    assert AzureOpenAiProvider.MODEL_NAME != "gpt-4"


def test_provider_model_defaults_stay_overridable():
    """The new defaults remain overridable via config (INT-02)."""
    provider = AnthropicProvider(
        ProviderConfig(provider_name="anthropic", model_name="my-model")
    )
    assert provider.model_name == "my-model"


# ===========================================================================
# INT-03 — parser hardening
# ===========================================================================


@pytest.mark.parametrize(
    "malformed",
    [
        "not json at all",
        "Here is the decomposition: { this is not valid JSON",
        "```json\n{broken\n```",
    ],
)
def test_decompose_malformed_body_degrades_for_chat_providers(
    monkeypatch, malformed
):
    """INT-03 (finding 057): no raw JSONDecodeError may escape decompose."""
    from llm_adapter.interface import LlmDecompositionResult

    for provider in _chat_based_providers():
        monkeypatch.setattr(provider, "_chat", lambda prompt: (malformed, None))
        result = provider.decompose_requirement("REQ-1", title="t", content="c")
        assert isinstance(result, LlmDecompositionResult)
        assert 0.0 <= result.score <= 1.0
        assert result.children, "expected a fallback child, not an empty list"
        rendered = str(result)
        assert "Expecting value" not in rendered
        assert "JSONDecodeError" not in rendered


def test_anthropic_decompose_malformed_body_degrades():
    from llm_adapter.interface import LlmDecompositionResult

    provider = AnthropicProvider(
        ProviderConfig(provider_name="anthropic", api_key="k")
    )
    fake = _recording_anthropic_module({}, text="not json at all", usage=None)
    with patch.dict(sys.modules, {"anthropic": fake}):
        result = provider.decompose_requirement("REQ-1")
    assert isinstance(result, LlmDecompositionResult)
    assert result.children
    assert "Expecting value" not in str(result)


def test_decompose_strips_markdown_fences_for_chat_providers(monkeypatch):
    """INT-03 (finding 057): fenced JSON is parsed, not treated as malformed."""
    fenced = (
        '```json\n{"score": 0.8, "suggestions": ["s"], '
        '"children": [{"id": "c1"}]}\n```'
    )
    for provider in _chat_based_providers():
        monkeypatch.setattr(provider, "_chat", lambda prompt: (fenced, None))
        result = provider.decompose_requirement("REQ-1")
        assert result.score == 0.8
        assert len(result.children) == 1
        assert result.children[0]["id"] == "c1"


# ===========================================================================
# INT-03 — retry amplification
# ===========================================================================


def test_policy_retry_budget_is_three_retries_i_e_four_attempts():
    """INT-03 (finding 055): the policy owns at most 4 attempts per call."""
    from llm_adapter.resilient_transport import (
        LLM_MAX_RETRIES,
        max_retries_for_timeout,
    )

    assert LLM_MAX_RETRIES == 3
    assert max_retries_for_timeout(30) == 3  # 1 initial + 3 retries = 4


def test_anthropic_client_disables_sdk_retries():
    captured: dict = {}
    provider = AnthropicProvider(
        ProviderConfig(provider_name="anthropic", api_key="k")
    )
    with patch.dict(
        sys.modules, {"anthropic": _recording_anthropic_module(captured)}
    ):
        provider._chat("hello")
    assert captured["kwargs"]["max_retries"] == 0


def test_openai_client_disables_sdk_retries():
    captured: dict = {}
    provider = OpenAiProvider(ProviderConfig(provider_name="openai", api_key="k"))
    with patch.dict(sys.modules, {"openai": _recording_openai_module(captured)}):
        provider._chat("hello")
    assert captured["kwargs"]["max_retries"] == 0


def test_azure_client_disables_sdk_retries():
    captured: dict = {}
    provider = AzureOpenAiProvider(
        ProviderConfig(
            provider_name="azure",
            api_key="k",
            api_base_url="https://example.openai.azure.com",
        )
    )
    with patch.dict(
        sys.modules,
        {"openai": _recording_openai_module(captured, attr="AzureOpenAI")},
    ):
        provider._chat("hello")
    assert captured["kwargs"]["max_retries"] == 0


def test_opencode_go_client_disables_sdk_retries():
    captured: dict = {}
    provider = OpencodeGoProvider(
        ProviderConfig(provider_name="opencode_go", api_key="k")
    )
    with patch.dict(sys.modules, {"openai": _recording_openai_module(captured)}):
        provider._chat("hello")
    assert captured["kwargs"]["max_retries"] == 0


# ===========================================================================
# INT-03 — usage handling
# ===========================================================================


def test_anthropic_usage_none_is_safe_for_all_capabilities():
    """INT-03 (finding 059): usage=None yields None, not AttributeError."""
    provider = AnthropicProvider(
        ProviderConfig(provider_name="anthropic", api_key="k")
    )
    fake = _recording_anthropic_module({}, usage=None)
    with patch.dict(sys.modules, {"anthropic": fake}):
        first = provider.validate_artifact("A1")
        second = provider.check_consistency("WS-1")
        third = provider.decompose_requirement("R1")
    assert first.token_usage is None
    assert second.token_usage is None
    assert third.token_usage is None


def test_ollama_sums_prompt_and_eval_count():
    """INT-03 (finding 054): input tokens are no longer discarded."""
    captured: dict = {}

    def _post(url, json, timeout):  # noqa: A002 - requests.post signature
        captured["json"] = json
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "response": "ok",
            "prompt_eval_count": 7,
            "eval_count": 3,
        }
        return response

    fake_requests = types.ModuleType("requests")
    fake_requests.post = _post

    provider = OllamaProvider(
        ProviderConfig(
            provider_name="ollama", api_base_url="http://localhost:11434"
        )
    )
    with patch.dict(sys.modules, {"requests": fake_requests}):
        _text, usage = provider._chat("prompt")

    assert usage == 10


# ===========================================================================
# INT-03 — mock usage marking (acceptance: mock records carry provider=mock)
# ===========================================================================


def test_mock_call_is_recorded_with_provider_mock():
    """The router must attribute a mock call to ``provider=mock`` (INT-03)."""
    from llm_adapter.audit_logger import LlmAuditLogger
    from llm_adapter.router import CapabilityRouter

    provider = MockLlmProvider(ProviderConfig(provider_name="mock"))
    audit = MagicMock(spec=LlmAuditLogger)

    with patch("llm_adapter.router.get_provider", return_value=provider), patch(
        "llm_adapter.router.record_token_usage"
    ) as mock_record:
        router = CapabilityRouter(
            enabled_capabilities={"validate_artifact"}, audit_logger=audit
        )
        result = router.execute_capability("validate_artifact", artifact_id="A1")

    assert result.provider == "mock"
    assert mock_record.call_args.kwargs["provider"] == "mock"
