"""R2S-008 golden characterization for the four LLM-JSON parser call sites.

Captured from the AS-IS behaviour *before* the parsers are centralized in
:mod:`llm_adapter.json_output`.  Every case pins the exact tolerance of its
family -- the refactor must not tighten (nor loosen) a single one:

* provider ``strict-strip`` (``_parse_derivation_response``,
  ``_parse_validation_response``, ``_parse_consistency_response`` and the
  inline ``OpenAiProvider.derive_requirements`` parser),
* application ``tolerant/prose-aware`` (``extract_json_payload``),
* interview ``list-only`` fence (``parse_multi_proposal``),
* the ``artifact_markdown`` emitter is import-only (no parse site to pin).

The golden values below were produced by probing the pre-refactor code; do not
"fix" surprising ones (e.g. the ``AttributeError`` on ``None`` inputs of the
provider parsers) -- preserving them is the point of this test.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from application.ai_derivation_service import (
    MOCK_FALLBACK_MARKER,
    LlmResponseError,
    extract_json_payload,
)
from application.interview_multi_protocol import parse_multi_proposal
from llm_adapter.providers import (
    OpenAiProvider,
    ProviderConfig,
    _parse_consistency_response,
    _parse_derivation_response,
    _parse_validation_response,
)

# Shared corpus.  ``None`` is included deliberately: only
# _parse_derivation_response / extract_json_payload guard against it today.
STRICT_CORPUS = [
    '{"score": 0.8, "suggestions": [], "children": []}',
    '```json\n{"score": 0.8}\n```',
    '```\n{"score": 0.8}\n```',
    'Sure: {"score": 0.5} thanks',
    '{"score": 1} extra',
    "[1, 2]",
    "",
    "   ",
    None,
    '{"a": 1, "b": }',
    '{"x":1} and }',
    '```json\n{"broken": \n```',
]

VALIDATION_FALLBACK = {
    "score": 0.0,
    "suggestions": [
        "LLM provider returned a non-JSON response; validation "
        "could not be scored automatically."
    ],
}
CONSISTENCY_FALLBACK = {
    "score": 0.0,
    "suggestions": [
        "LLM provider returned a non-JSON response; consistency check "
        "could not be scored automatically."
    ],
    "issues": [],
}


def _generated_req(text):
    return {"children": [{"title": "Generated Req", "description": text}]}


class TestProviderStrictStripGolden:
    """Pin each provider parser's exact strict-strip tolerance."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ('{"score": 0.8, "suggestions": [], "children": []}',
             {"score": 0.8, "suggestions": [], "children": []}),
            ('```json\n{"score": 0.8}\n```', {"score": 0.8}),
            ('```\n{"score": 0.8}\n```', {"score": 0.8}),
            ("Sure: {\"score\": 0.5} thanks",
             _generated_req('Sure: {"score": 0.5} thanks')),
            ('{"score": 1} extra', _generated_req('{"score": 1} extra')),
            ("[1, 2]", _generated_req("[1, 2]")),
            ("", _generated_req("")),
            ("   ", _generated_req("   ")),
            (None, _generated_req(None)),
            ('{"a": 1, "b": }', _generated_req('{"a": 1, "b": }')),
            ('{"x":1} and }', _generated_req('{"x":1} and }')),
            ('```json\n{"broken": \n```',
             _generated_req('```json\n{"broken": \n```')),
        ],
    )
    def test_derivation_response(self, raw, expected):
        assert _parse_derivation_response(raw) == expected

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ('{"score": 0.8, "suggestions": [], "children": []}',
             {"score": 0.8, "suggestions": [], "children": []}),
            ('```json\n{"score": 0.8}\n```', {"score": 0.8}),
            ('```\n{"score": 0.8}\n```', {"score": 0.8}),
            ("Sure: {\"score\": 0.5} thanks", VALIDATION_FALLBACK),
            ('{"score": 1} extra', VALIDATION_FALLBACK),
            ("[1, 2]", [1, 2]),  # non-dict passthrough is pre-existing behaviour
            ("", VALIDATION_FALLBACK),
            ("   ", VALIDATION_FALLBACK),
            ('{"a": 1, "b": }', VALIDATION_FALLBACK),
            ('{"x":1} and }', VALIDATION_FALLBACK),
        ],
    )
    def test_validation_response(self, raw, expected):
        assert _parse_validation_response(raw) == expected

    def test_validation_response_none_still_raises_attribute_error(self):
        with pytest.raises(AttributeError):
            _parse_validation_response(None)

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ('{"score": 0.8, "suggestions": [], "children": []}',
             {"score": 0.8, "suggestions": [], "children": []}),
            ('```json\n{"score": 0.8}\n```', {"score": 0.8}),
            ('```\n{"score": 0.8}\n```', {"score": 0.8}),
            ("Sure: {\"score\": 0.5} thanks", {"score": 0.5}),  # brace retry
            ('{"score": 1} extra', {"score": 1}),  # brace retry
            ("[1, 2]", [1, 2]),
            ("", CONSISTENCY_FALLBACK),
            ("   ", CONSISTENCY_FALLBACK),
            ('{"a": 1, "b": }', CONSISTENCY_FALLBACK),
            ('{"x":1} and }', CONSISTENCY_FALLBACK),
        ],
    )
    def test_consistency_response(self, raw, expected):
        assert _parse_consistency_response(raw) == expected

    def test_consistency_response_none_still_raises_attribute_error(self):
        with pytest.raises(AttributeError):
            _parse_consistency_response(None)


class TestInlineDeriveGolden:
    """Pin the inline strict-strip parser in ``OpenAiProvider.derive_requirements``.

    Note the two intentional differences to ``_parse_derivation_response``:
    the fallback ``description`` uses the *stripped* text, and the score
    default is ``1.0`` (not ``0.0``).
    """

    @pytest.mark.parametrize(
        ("raw", "score", "children"),
        [
            ('{"score": 0.7, "children": [{"title": "x"}]}',
             0.7, [{"title": "x"}]),
            ('```json\n{"score": 0.7}\n```', 0.7, []),
            ("Sure: {\"score\": 0.5} thanks", 1.0,
             [{"title": "Generated Req", "description": 'Sure: {"score": 0.5} thanks'}]),
            ("nonsense", 1.0,
             [{"title": "Generated Req", "description": "nonsense"}]),
            ("", 1.0, [{"title": "Generated Req", "description": ""}]),
            ("   ", 1.0, [{"title": "Generated Req", "description": ""}]),
        ],
    )
    def test_derive_requirements(self, raw, score, children):
        provider = OpenAiProvider(ProviderConfig(provider_name="openai"))
        with patch.object(provider, "_invoke_chat", return_value=(raw, 3)):
            result = provider.derive_requirements("need-id")
        assert result.score == score
        assert result.children == children
        assert result.token_usage == 3

    def test_derive_requirements_none_still_raises_attribute_error(self):
        provider = OpenAiProvider(ProviderConfig(provider_name="openai"))
        with patch.object(provider, "_invoke_chat", return_value=(None, 3)):
            with pytest.raises(AttributeError):
                provider.derive_requirements("need-id")


class TestTolerantExtractorGolden:
    """Pin the prose-aware ``extract_json_payload`` (issue #1240)."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ('[{"a": 1}]', [{"a": 1}]),
            ('{"a": 1}', {"a": 1}),
            ('Sure:\n```json\n[{"title": "x"}]\n```\nbye', [{"title": "x"}]),
            ("```\n[1,2,3]\n```", [1, 2, 3]),
            ('[{"a":1}] -- hope this helps!', [{"a": 1}]),
            ('The result: [{"a": 1}] later text', [{"a": 1}]),
            (f"{MOCK_FALLBACK_MARKER} [1]", [1]),
            ('Use the {braces} wisely: [{"a": 1}]', [{"a": 1}]),
        ],
    )
    def test_accepted(self, raw, expected):
        assert extract_json_payload(raw) == expected

    @pytest.mark.parametrize(
        ("raw", "message"),
        [
            ("", "empty completion"),
            (None, "empty completion"),
            ("I cannot comply with that request.", "not valid JSON"),
            ('```json\n[{"a": 1]\n```', "not valid JSON"),
        ],
    )
    def test_rejected_with_exact_message(self, raw, message):
        with pytest.raises(LlmResponseError) as exc_info:
            extract_json_payload(raw)
        assert message in str(exc_info.value)
        assert exc_info.value.is_mock_fallback is False


class TestListOnlyFenceGolden:
    """Pin ``parse_multi_proposal``'s list-only, case-sensitive fence."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ('```json\n[{"type":"Requirement","fields":{}}]\n```',
             [{"type": "Requirement", "fields": {}}]),
            ("preamble\n```json\n[{\"type\":\"Requirement\",\"fields\":{}}]\n```\ntrailing",
             [{"type": "Requirement", "fields": {}}]),
            ('```json\n[{"type":"Requirement","fields":{"title":"x"}}]\n```',
             [{"type": "Requirement", "fields": {"title": "x"}}]),
        ],
    )
    def test_accepted(self, raw, expected):
        assert parse_multi_proposal(raw) == expected

    @pytest.mark.parametrize(
        "raw",
        [
            '```JSON\n[{"type":"Requirement","fields":{}}]\n```',  # case-sensitive
            '```json\n{"a":1}\n```',  # object not list
            "```json\n[1,2]\n```",  # non-dict entries fail size/shape gate
            '```json\n[{"a": 1]\n```',  # malformed JSON
            "no fence at all",
            "x" * 200_001,  # AI-005 raw ceiling
        ],
    )
    def test_rejected(self, raw):
        assert parse_multi_proposal(raw) is None
