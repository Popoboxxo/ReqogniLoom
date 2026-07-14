"""
Contract tests: verify all LLM providers fully implement LlmCapabilityInterface.

[REQ-085] Every provider class registered in the plugin registry must:
  - Extend LlmCapabilityInterface (ABC)
  - Implement all five abstract methods (no remaining @abstractmethod stubs)
  - Be instantiable given a ProviderConfig (or without one, for MockLlmProvider)
  - Be present in the plugin registry under its canonical provider name

These tests are pure unit tests — no network calls, no DB access required.
The concrete HTTP providers (Anthropic, OpenAI, Ollama, Azure) are instantiated
with a dummy ProviderConfig; their _chat / SDK methods are never invoked.
"""
from __future__ import annotations

import inspect

import pytest

from llm_adapter.interface import LlmCapabilityInterface
from llm_adapter.providers import (
    AnthropicProvider,
    AzureOpenAiProvider,
    MockLlmProvider,
    OllamaProvider,
    OpenAiProvider,
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
