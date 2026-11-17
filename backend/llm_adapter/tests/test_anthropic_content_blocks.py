"""AI-006 regression tests — Anthropic content-block extraction hardening.

The four Anthropic call sites used ``message.content[0].text``. If the first
block was a ``thinking`` or ``tool_use`` block, that raised ``AttributeError``
*after* the resilience policy had already reported success — an unclassified
failure that downstream error handling could mistake for a provider outage and
silently degrade to the mock provider. These tests pin the hardened extraction
that mirrors ``_BaseHttpProvider._extract_choice_text``.
"""
from __future__ import annotations

import sys
import types
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from llm_adapter.providers import AnthropicProvider, ProviderConfig
from llm_adapter.resilient_transport import LlmTransportError


def _provider() -> AnthropicProvider:
    return AnthropicProvider(ProviderConfig(provider_name="anthropic"))


def _text(value: str) -> SimpleNamespace:
    return SimpleNamespace(type="text", text=value)


def _thinking() -> SimpleNamespace:
    return SimpleNamespace(type="thinking", thinking="let me think")


def _tool_use() -> SimpleNamespace:
    return SimpleNamespace(type="tool_use", id="1", name="a_tool", input={})


def _message(blocks) -> SimpleNamespace:
    return SimpleNamespace(
        content=blocks,
        usage=SimpleNamespace(input_tokens=1, output_tokens=1),
    )


# ---------------------------------------------------------------------------
# _extract_anthropic_text unit behaviour
# ---------------------------------------------------------------------------


def test_thinking_then_text_yields_the_text_block():
    msg = _message([_thinking(), _text('{"score": 0.8, "suggestions": []}')])
    assert _provider()._extract_anthropic_text(msg) == '{"score": 0.8, "suggestions": []}'


def test_concatenates_multiple_text_blocks():
    assert _provider()._extract_anthropic_text(_message([_text("a"), _text("b")])) == "ab"


def test_tool_use_only_raises_transport_error():
    with pytest.raises(LlmTransportError):
        _provider()._extract_anthropic_text(_message([_tool_use()]))


def test_thinking_only_raises_transport_error():
    with pytest.raises(LlmTransportError):
        _provider()._extract_anthropic_text(_message([_thinking()]))


@pytest.mark.parametrize("content", [[], None])
def test_empty_or_missing_content_is_empty_string(content):
    assert _provider()._extract_anthropic_text(_message(content)) == ""


def test_legacy_mock_block_without_string_type_is_accepted():
    """Existing tests build ``MagicMock(text=...)`` without a string ``type``."""
    msg = MagicMock()
    msg.content = [MagicMock(text="hello")]
    assert _provider()._extract_anthropic_text(msg) == "hello"


# ---------------------------------------------------------------------------
# Integration: all four sites use the helper; no silent mock fallback
# ---------------------------------------------------------------------------


def _fake_anthropic_module(captured: dict, blocks) -> types.ModuleType:
    def _ctor(**kwargs):
        client = MagicMock()
        msg = _message(blocks)
        client.messages.create.return_value = msg
        captured["client"] = client
        return client

    mod = types.ModuleType("anthropic")
    mod.Anthropic = _ctor
    return mod


def test_check_consistency_tool_use_only_propagates_without_mock_fallback():
    captured: dict = {}
    fake = _fake_anthropic_module(captured, [_tool_use()])
    provider = _provider()
    with patch.dict(sys.modules, {"anthropic": fake}):
        with pytest.raises(LlmTransportError):
            provider.check_consistency("ws-1")


def test_all_four_sites_route_through_extract_helper(monkeypatch):
    """The helper is invoked by _chat and all three structured methods."""
    calls: list[str] = []
    original = AnthropicProvider._extract_anthropic_text

    def _counting(self, message):
        calls.append("called")
        return original(self, message)

    monkeypatch.setattr(AnthropicProvider, "_extract_anthropic_text", _counting)

    blocks = [_text('{"score": 0.5, "suggestions": [], "children": [], "issues": []}')]
    fake = _fake_anthropic_module({}, blocks)
    provider = _provider()
    with patch.dict(sys.modules, {"anthropic": fake}):
        provider._chat("hello")
        provider.validate_artifact("REQ-1", title="t", content="c")
        provider.decompose_requirement("REQ-1", title="t", content="c")
        provider.check_consistency("ws-1")

    assert len(calls) == 4, f"expected four extraction calls, got {len(calls)}"
