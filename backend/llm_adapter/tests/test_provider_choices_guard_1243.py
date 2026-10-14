"""Issue #1243 — guarded ``response.choices`` extraction in OpenAI-compatible providers.

The three OpenAI-compatible providers (OpenAI, AzureOpenAI and the OpenCode Go
gateway) all read ``response.choices[0].message.content`` bare. A malformed or
truncated SDK payload (empty/``None`` choices, a choice without a message, a
non-text payload) made that raise ``TypeError`` / ``IndexError`` /
``AttributeError`` *after* the resilience policy had already reported success —
an unhandled 500 instead of the provider error the CapabilityRouter maps.

These tests pin the shared ``_BaseHttpProvider._extract_choice_text`` guard for
all three providers, plus one end-to-end ``_chat`` run proving a bad choices
list surfaces as ``LlmTransportError`` (not a bare ``TypeError``).
"""
from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch

import pytest

from llm_adapter.providers import (
    AzureOpenAiProvider,
    OpencodeGoProvider,
    OpenAiProvider,
    ProviderConfig,
)
from llm_adapter.resilient_transport import LlmTransportError


def _config(name: str) -> ProviderConfig:
    return ProviderConfig(provider_name=name, api_key="sk-dummy")


def _provider_classes():
    return [
        pytest.param(OpenAiProvider, "openai", id="openai"),
        pytest.param(AzureOpenAiProvider, "azure", id="azure"),
        pytest.param(OpencodeGoProvider, "opencode_go", id="opencode_go"),
    ]


def _response_with(choices):
    response = MagicMock()
    response.choices = choices
    response.usage = MagicMock(total_tokens=1)
    return response


@pytest.mark.parametrize("provider_cls, name", _provider_classes())
def test_none_choices_raises_transport_error(provider_cls, name):
    provider = provider_cls(_config(name))
    with pytest.raises(LlmTransportError, match="no completion choices"):
        provider._extract_choice_text(_response_with(None))


@pytest.mark.parametrize("provider_cls, name", _provider_classes())
def test_empty_choices_raises_transport_error(provider_cls, name):
    provider = provider_cls(_config(name))
    with pytest.raises(LlmTransportError, match="no completion choices"):
        provider._extract_choice_text(_response_with([]))


@pytest.mark.parametrize("provider_cls, name", _provider_classes())
def test_choice_without_message_raises_transport_error(provider_cls, name):
    provider = provider_cls(_config(name))
    choice = MagicMock()
    choice.message = None
    with pytest.raises(LlmTransportError, match="without a message"):
        provider._extract_choice_text(_response_with([choice]))


@pytest.mark.parametrize("provider_cls, name", _provider_classes())
def test_non_text_content_raises_transport_error(provider_cls, name):
    provider = provider_cls(_config(name))
    choice = MagicMock(message=MagicMock(content=[{"type": "text"}]))
    with pytest.raises(LlmTransportError, match="non-text"):
        provider._extract_choice_text(_response_with([choice]))


@pytest.mark.parametrize("provider_cls, name", _provider_classes())
def test_none_content_is_a_valid_empty_completion(provider_cls, name):
    provider = provider_cls(_config(name))
    choice = MagicMock(message=MagicMock(content=None))
    assert provider._extract_choice_text(_response_with([choice])) == ""


@pytest.mark.parametrize("provider_cls, name", _provider_classes())
def test_text_content_is_returned(provider_cls, name):
    provider = provider_cls(_config(name))
    choice = MagicMock(message=MagicMock(content="hello"))
    assert provider._extract_choice_text(_response_with([choice])) == "hello"


def _fake_openai_module(choices) -> types.ModuleType:
    """Fake ``openai`` module whose client returns *choices*."""

    def _ctor(**_kwargs):
        client = MagicMock()
        client.chat.completions.create.return_value = _response_with(choices)
        return client

    module = types.ModuleType("openai")
    module.OpenAI = _ctor
    return module


def test_chat_with_empty_choices_surfaces_transport_error_not_typeerror():
    """End-to-end proof: the guard runs inside ``_chat``, after resilience."""
    provider = OpenAiProvider(_config("openai"))
    fake_module = _fake_openai_module([])
    with patch.dict(sys.modules, {"openai": fake_module}):
        with pytest.raises(LlmTransportError, match="no completion choices"):
            provider._chat("hello")
