"""
Contract tests: verify all LLM providers fully implement LlmCapabilityInterface.

[REQ-085] Every provider class registered in the plugin registry must:
  - Extend LlmCapabilityInterface (ABC)
  - Implement all five abstract methods (no remaining @abstractmethod stubs)
  - Be instantiable given a ProviderConfig (or without one, for MockLlmProvider)
  - Be present in the plugin registry under its canonical provider name

These tests are pure unit tests — no network calls, no DB access required.
The concrete HTTP providers (Anthropic, OpenAI, Ollama, Azure) are instantiated
with a dummy ProviderConfig. Most contract checks never invoke _chat / the
SDK methods; the model_name-precedence tests below do invoke them, against
patched fake HTTP/SDK clients (no real network access).
"""
from __future__ import annotations

import inspect
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

from llm_adapter.interface import LlmCapabilityInterface
from llm_adapter.providers import (
    AnthropicProvider,
    AzureOpenAiProvider,
    LlmNotConfiguredError,
    MockLlmProvider,
    OllamaProvider,
    OpenAiProvider,
    OpencodeGoProvider,
    ProviderConfig,
)

# ---------------------------------------------------------------------------
# Test data
# ---------------------------------------------------------------------------

# Minimal ProviderConfig sufficient to instantiate HTTP-backed providers
# without triggering network connections. Real credentials are never needed
# for interface / registration checks.
_DUMMY_CONFIG = ProviderConfig(
    provider_name="test-dummy",
    api_key="sk-dummy-key-for-contract-tests-only",
    api_base_url="http://localhost:11434",
    timeout=5,
)

# All provider classes that must satisfy the LlmCapabilityInterface contract.
PROVIDER_CLASSES = [
    MockLlmProvider,
    OpenAiProvider,
    AnthropicProvider,
    OllamaProvider,
    AzureOpenAiProvider,
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _abstract_method_names(interface_cls: type) -> frozenset[str]:
    """Return the names of all abstract methods declared on *interface_cls*."""
    return frozenset(
        name
        for name in dir(interface_cls)
        if getattr(getattr(interface_cls, name, None), "__isabstractmethod__", False)
    )


def _instantiate(provider_cls: type) -> LlmCapabilityInterface:
    """Instantiate *provider_cls* with an appropriate config."""
    if provider_cls is MockLlmProvider:
        return provider_cls()  # MockLlmProvider config is optional
    return provider_cls(_DUMMY_CONFIG)  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# Parametrized contract checks
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("provider_cls", PROVIDER_CLASSES, ids=lambda c: c.__name__)
def test_provider_extends_interface(provider_cls: type) -> None:
    """[REQ-085] All providers must subclass LlmCapabilityInterface."""
    assert issubclass(provider_cls, LlmCapabilityInterface), (
        f"{provider_cls.__name__} must extend LlmCapabilityInterface. "
        "The CapabilityRouter depends on this for type-safe dispatch."
    )


@pytest.mark.parametrize("provider_cls", PROVIDER_CLASSES, ids=lambda c: c.__name__)
def test_provider_implements_all_abstract_methods(provider_cls: type) -> None:
    """[REQ-085] All providers must implement every abstract method on the interface.

    Validates that no @abstractmethod stub remains unimplemented, which would
    prevent instantiation and cause runtime errors during dispatch.
    """
    abstract = _abstract_method_names(LlmCapabilityInterface)
    implemented = frozenset(dir(provider_cls))
    missing = abstract - implemented
    assert not missing, (
        f"{provider_cls.__name__} is missing interface methods: {missing}. "
        f"Required abstract methods: {abstract}"
    )


@pytest.mark.parametrize("provider_cls", PROVIDER_CLASSES, ids=lambda c: c.__name__)
def test_provider_is_concrete(provider_cls: type) -> None:
    """[REQ-085] Provider has no remaining abstract methods (can be instantiated)."""
    remaining_abstract = frozenset(
        name
        for name in dir(provider_cls)
        if getattr(getattr(provider_cls, name, None), "__isabstractmethod__", False)
    )
    assert not remaining_abstract, (
        f"{provider_cls.__name__} still has abstract methods: {remaining_abstract}. "
        "All methods must be concretely implemented."
    )


# ---------------------------------------------------------------------------
# Instantiation checks
# ---------------------------------------------------------------------------


def test_mock_provider_instantiable_without_config() -> None:
    """[REQ-085] MockLlmProvider is instantiable with no arguments (test/CI path)."""
    provider = MockLlmProvider()
    assert isinstance(provider, LlmCapabilityInterface)
    assert provider.PROVIDER_NAME == "mock"


@pytest.mark.parametrize(
    "provider_cls",
    [OpenAiProvider, AnthropicProvider, OllamaProvider, AzureOpenAiProvider],
    ids=lambda c: c.__name__,
)
def test_http_provider_instantiable_with_config(provider_cls: type) -> None:
    """[REQ-085] HTTP-backed providers are instantiable given a ProviderConfig."""
    provider = _instantiate(provider_cls)
    assert isinstance(provider, LlmCapabilityInterface)


@pytest.mark.parametrize("base_url", ["", "   ", None], ids=["empty", "blank", "none"])
def test_ollama_requires_base_url(base_url) -> None:
    """[REQ-132] OllamaProvider rejects a blank base_url instead of silently
    falling back to localhost — misconfiguration must surface at init time."""
    with pytest.raises(LlmNotConfiguredError):
        OllamaProvider(
            ProviderConfig(provider_name="ollama", api_base_url=base_url)
        )


def test_ollama_accepts_configured_base_url() -> None:
    """[REQ-132] A configured base_url instantiates OllamaProvider normally."""
    provider = OllamaProvider(
        ProviderConfig(
            provider_name="ollama", api_base_url="http://localhost:11434"
        )
    )
    assert isinstance(provider, LlmCapabilityInterface)


# ---------------------------------------------------------------------------
# Interface method signature checks
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("provider_cls", PROVIDER_CLASSES, ids=lambda c: c.__name__)
def test_validate_artifact_accepts_title_and_content(provider_cls: type) -> None:
    """[REQ-085] validate_artifact must accept 'title' and 'content' kwargs (REQ-046)."""
    sig = inspect.signature(provider_cls.validate_artifact)
    param_names = set(sig.parameters)
    assert "title" in param_names, (
        f"{provider_cls.__name__}.validate_artifact missing 'title' parameter (REQ-046)"
    )
    assert "content" in param_names, (
        f"{provider_cls.__name__}.validate_artifact missing 'content' parameter (REQ-046)"
    )


@pytest.mark.parametrize("provider_cls", PROVIDER_CLASSES, ids=lambda c: c.__name__)
def test_validate_artifact_accepts_timeout(provider_cls: type) -> None:
    """[REQ-085] validate_artifact must accept a 'timeout' kwarg (REQ-084)."""
    sig = inspect.signature(provider_cls.validate_artifact)
    assert "timeout" in sig.parameters, (
        f"{provider_cls.__name__}.validate_artifact missing 'timeout' parameter (REQ-084)"
    )


# ---------------------------------------------------------------------------
# Plugin registry checks
# ---------------------------------------------------------------------------


def test_provider_registry_covers_all_expected_names() -> None:
    """[REQ-085] Plugin registry contains the four real providers plus mock."""
    from llm_adapter.providers import _PROVIDER_REGISTRY

    expected = {"mock", "anthropic", "openai", "ollama", "azure"}
    registered = set(_PROVIDER_REGISTRY.keys())
    missing_from_registry = expected - registered
    assert not missing_from_registry, (
        f"These providers are missing from _PROVIDER_REGISTRY: {missing_from_registry}. "
        f"Registered: {registered}"
    )


def test_registry_values_are_llm_provider_subclasses() -> None:
    """[REQ-085] Every entry in the plugin registry extends LlmCapabilityInterface."""
    from llm_adapter.providers import _PROVIDER_REGISTRY

    for name, cls in _PROVIDER_REGISTRY.items():
        assert issubclass(cls, LlmCapabilityInterface), (
            f"Registry entry '{name}' ({cls.__name__}) "
            f"does not extend LlmCapabilityInterface"
        )


def test_mock_provider_validate_artifact_returns_llm_result() -> None:
    """[REQ-085] MockLlmProvider.validate_artifact returns a valid LlmResult."""
    from llm_adapter.interface import LlmResult

    provider = MockLlmProvider()
    result = provider.validate_artifact(
        "REQ-001",
        title="System shall provide login",
        content="Users must be able to authenticate using username and password.",
    )
    assert isinstance(result, LlmResult)
    assert 0.0 <= result.score <= 1.0
    assert isinstance(result.suggestions, list)
    assert result.provider == "mock"


def test_mock_provider_decompose_requirement_returns_children() -> None:
    """[REQ-085] MockLlmProvider.decompose_requirement returns at least one child."""
    from llm_adapter.interface import LlmDecompositionResult

    provider = MockLlmProvider()
    result = provider.decompose_requirement(
        "SYS-REQ-042",
        title="Authentication subsystem shall support OAuth 2.0",
        content="The system shall implement OAuth 2.0 authorization code flow.",
    )
    assert isinstance(result, LlmDecompositionResult)
    assert len(result.children) >= 1, "Expected at least one decomposed child"
    child = result.children[0]
    assert "id" in child or "title" in child, (
        "Child must have at least 'id' or 'title' key"
    )


@pytest.mark.parametrize(
    "provider_cls",
    [OpenAiProvider, AnthropicProvider, OllamaProvider, OpencodeGoProvider],
    ids=lambda c: c.__name__,
)
def test_http_provider_honours_configured_model_name(provider_cls: type) -> None:
    """[Issue #118, #196] A configured model_name must override the class
    default MODEL_NAME - providers must not silently ignore LLM_MODEL_NAME /
    the DB-configured LlmSettings.model_name.

    Ollama and OpencodeGo previously re-derived their own ``_model`` from
    ``os.environ.get("LLM_MODEL")`` instead of reading the config-resolved
    ``self.model_name``, so a DB-configured model_name (which never reaches
    the process environment) was silently ignored (issue #196). The shared
    ``api_base_url`` in this config satisfies OllamaProvider's mandatory
    base_url check without affecting the other providers.
    """
    config = ProviderConfig(
        provider_name="test-dummy",
        api_key="sk-dummy-key-for-contract-tests-only",
        api_base_url="http://localhost:11434",
        model_name="a-custom-configured-model",
    )
    provider = provider_cls(config)
    assert provider.model_name == "a-custom-configured-model"


@pytest.mark.parametrize(
    "provider_cls",
    [OpenAiProvider, AnthropicProvider, OllamaProvider, OpencodeGoProvider],
    ids=lambda c: c.__name__,
)
def test_http_provider_falls_back_to_default_model_name(provider_cls: type) -> None:
    """[Issue #118, #196] With no configured model_name, the provider still
    falls back to its own MODEL_NAME class default (no regression on
    unconfigured deployments)."""
    config = ProviderConfig(
        provider_name="test-dummy",
        api_key="sk-dummy-key-for-contract-tests-only",
        api_base_url="http://localhost:11434",
        model_name="",
    )
    provider = provider_cls(config)
    assert provider.model_name == provider_cls.MODEL_NAME


# ---------------------------------------------------------------------------
# MockLlmProvider model_name (issue #196): MockLlmProvider extends
# LlmCapabilityInterface directly (not _BaseHttpProvider) and had no
# model_name attribute at all, breaking interface parity for any generic
# caller that reads .model_name polymorphically (it is also the default
# provider).
# ---------------------------------------------------------------------------


def test_mock_provider_honours_configured_model_name() -> None:
    """[Issue #196] MockLlmProvider must expose model_name like every other
    provider, and its results must reflect the configured model."""
    provider = MockLlmProvider(
        ProviderConfig(provider_name="mock", model_name="custom-mock-model")
    )
    assert provider.model_name == "custom-mock-model"
    result = provider.validate_artifact("REQ-001")
    assert result.model == "custom-mock-model"


def test_mock_provider_falls_back_to_default_model_name() -> None:
    """[Issue #196] With no configured model_name, MockLlmProvider falls back
    to its own MODEL_NAME class default."""
    provider = MockLlmProvider(ProviderConfig(provider_name="mock", model_name=""))
    assert provider.model_name == MockLlmProvider.MODEL_NAME


# ---------------------------------------------------------------------------
# base_url passthrough (issue #212): AnthropicProvider / OpenAiProvider must
# forward a configured api_base_url to the underlying SDK client so custom
# endpoints (proxies, self-hosted gateways) are actually reachable. Both SDK
# modules are imported lazily inside the provider methods, so - mirroring the
# `requests` fake-module pattern in test_resilient_transport.py - a fake
# module is injected into sys.modules for the duration of the call.
# ---------------------------------------------------------------------------


def _fake_anthropic_module(captured: dict) -> types.ModuleType:
    """Build a fake `anthropic` module recording the Anthropic() kwargs."""

    def _anthropic_ctor(**kwargs):
        captured["kwargs"] = kwargs
        client = MagicMock()
        message = MagicMock()
        message.content = [MagicMock(text='{"score": 1.0, "suggestions": []}')]
        message.usage = MagicMock(input_tokens=1, output_tokens=1)
        client.messages.create.return_value = message
        return client

    fake_module = types.ModuleType("anthropic")
    fake_module.Anthropic = _anthropic_ctor
    return fake_module


def _fake_openai_module(captured: dict) -> types.ModuleType:
    """Build a fake `openai` module recording the OpenAI() kwargs."""

    def _openai_ctor(**kwargs):
        captured["kwargs"] = kwargs
        client = MagicMock()
        response = MagicMock()
        response.choices = [MagicMock(message=MagicMock(content="ok"))]
        response.usage = MagicMock(total_tokens=2)
        client.chat.completions.create.return_value = response
        return client

    fake_module = types.ModuleType("openai")
    fake_module.OpenAI = _openai_ctor
    return fake_module


def test_anthropic_provider_forwards_configured_base_url() -> None:
    """[Issue #212] A configured api_base_url must reach anthropic.Anthropic()."""
    captured: dict = {}
    fake_anthropic = _fake_anthropic_module(captured)
    config = ProviderConfig(
        provider_name="anthropic",
        api_key="sk-dummy",
        api_base_url="https://custom-anthropic-proxy.example.com",
    )
    provider = AnthropicProvider(config)
    with patch.dict(sys.modules, {"anthropic": fake_anthropic}):
        provider._chat("hello")
    assert captured["kwargs"]["base_url"] == "https://custom-anthropic-proxy.example.com"


def test_anthropic_provider_falls_back_to_sdk_default_when_base_url_unset() -> None:
    """[Issue #212] An unset/empty api_base_url must not pass a literal empty
    string to the SDK - it must pass None so the SDK's own default applies."""
    captured: dict = {}
    fake_anthropic = _fake_anthropic_module(captured)
    config = ProviderConfig(
        provider_name="anthropic", api_key="sk-dummy", api_base_url=""
    )
    provider = AnthropicProvider(config)
    with patch.dict(sys.modules, {"anthropic": fake_anthropic}):
        provider._chat("hello")
    assert captured["kwargs"]["base_url"] is None


def test_openai_provider_forwards_configured_base_url() -> None:
    """[Issue #212] A configured api_base_url must reach openai.OpenAI()."""
    captured: dict = {}
    fake_openai = _fake_openai_module(captured)
    config = ProviderConfig(
        provider_name="openai",
        api_key="sk-dummy",
        api_base_url="https://custom-openai-proxy.example.com",
    )
    provider = OpenAiProvider(config)
    with patch.dict(sys.modules, {"openai": fake_openai}):
        provider._chat("hello")
    assert captured["kwargs"]["base_url"] == "https://custom-openai-proxy.example.com"


def test_openai_provider_falls_back_to_sdk_default_when_base_url_unset() -> None:
    """[Issue #212] An unset/empty api_base_url must not pass a literal empty
    string to the SDK - it must pass None so the SDK's own default applies."""
    captured: dict = {}
    fake_openai = _fake_openai_module(captured)
    config = ProviderConfig(
        provider_name="openai", api_key="sk-dummy", api_base_url=""
    )
    provider = OpenAiProvider(config)
    with patch.dict(sys.modules, {"openai": fake_openai}):
        provider._chat("hello")
    assert captured["kwargs"]["base_url"] is None


# ---------------------------------------------------------------------------
# Call-site model= assertions (issue #196): the regression tests above only
# assert on provider.model_name resolution, not on the actual `model=` kwarg
# sent to the vendor SDK / HTTP payload - a call site that reintroduces
# `model=self.MODEL_NAME` (or a bypassing `self._model`) would not be caught
# by them. These tests stub the transport and assert on the outbound
# request/call directly, closing that gap for Ollama, OpencodeGo and Azure.
# ---------------------------------------------------------------------------


def _fake_openai_module_capturing_model(captured: dict) -> types.ModuleType:
    """Build a fake `openai` module recording the `model=` kwarg passed to
    chat.completions.create() (as opposed to _fake_openai_module, which only
    records the OpenAI() constructor kwargs)."""

    def _openai_ctor(**_kwargs):
        client = MagicMock()
        response = MagicMock()
        response.choices = [MagicMock(message=MagicMock(content="ok"))]
        response.usage = MagicMock(total_tokens=2)

        def _create(**create_kwargs):
            captured["model"] = create_kwargs.get("model")
            return response

        client.chat.completions.create.side_effect = _create
        return client

    fake_module = types.ModuleType("openai")
    fake_module.OpenAI = _openai_ctor
    return fake_module


def _fake_azure_openai_module(captured: dict) -> types.ModuleType:
    """Build a fake `openai` module exposing AzureOpenAI, recording the
    `model=` kwarg passed to chat.completions.create()."""

    def _azure_ctor(**_kwargs):
        client = MagicMock()
        response = MagicMock()
        response.choices = [MagicMock(message=MagicMock(content="ok"))]
        response.usage = MagicMock(total_tokens=2)

        def _create(**create_kwargs):
            captured["model"] = create_kwargs.get("model")
            return response

        client.chat.completions.create.side_effect = _create
        return client

    fake_module = types.ModuleType("openai")
    fake_module.AzureOpenAI = _azure_ctor
    return fake_module


def test_ollama_chat_sends_configured_model_in_request_payload() -> None:
    """[Issue #196] The actual outbound Ollama request must use the
    configured model_name, not a value re-derived from os.environ only."""
    captured: dict = {}

    def _post(url, json, timeout):  # noqa: A002 - matches requests.post signature
        captured["json"] = json
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"response": "ok", "eval_count": 1}
        return response

    fake_requests = types.ModuleType("requests")
    fake_requests.post = _post

    provider = OllamaProvider(
        ProviderConfig(
            provider_name="ollama",
            api_base_url="http://localhost:11434",
            model_name="llama3.1-custom",
        )
    )
    with patch.dict(sys.modules, {"requests": fake_requests}):
        provider._chat("prompt")

    assert captured["json"]["model"] == "llama3.1-custom"


def test_opencode_go_provider_sends_configured_model_in_request() -> None:
    """[Issue #196] OpencodeGoProvider must send the configured model_name to
    chat.completions.create(), not a value re-derived from os.environ only."""
    captured: dict = {}
    fake_openai = _fake_openai_module_capturing_model(captured)
    config = ProviderConfig(
        provider_name="opencode_go",
        api_key="sk-dummy",
        model_name="claude-custom-model",
    )
    provider = OpencodeGoProvider(config)
    with patch.dict(sys.modules, {"openai": fake_openai}):
        provider._chat("hello")
    assert captured["model"] == "claude-custom-model"


def test_azure_provider_sends_configured_model_when_no_deployment_set() -> None:
    """[Issue #196] Without an azure_deployment override, the actual
    create() call must fall back to the configured model_name, not the
    class-level MODEL_NAME default."""
    captured: dict = {}
    fake_openai = _fake_azure_openai_module(captured)
    config = ProviderConfig(
        provider_name="azure",
        api_key="sk-dummy",
        api_base_url="https://example.openai.azure.com",
        model_name="gpt-4o-custom",
    )
    provider = AzureOpenAiProvider(config)
    with patch.dict(sys.modules, {"openai": fake_openai}):
        provider._chat("hello")
    assert captured["model"] == "gpt-4o-custom"


def test_azure_provider_deployment_still_wins_over_configured_model_name() -> None:
    """[Issue #196] azure_deployment routing is unaffected by the fix - it
    must remain first in the fallback chain."""
    captured: dict = {}
    fake_openai = _fake_azure_openai_module(captured)
    config = ProviderConfig(
        provider_name="azure",
        api_key="sk-dummy",
        api_base_url="https://example.openai.azure.com",
        azure_deployment="my-deployment",
        model_name="gpt-4o-custom",
    )
    provider = AzureOpenAiProvider(config)
    with patch.dict(sys.modules, {"openai": fake_openai}):
        provider._chat("hello")
    assert captured["model"] == "my-deployment"
