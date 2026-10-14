"""Issue #1240 — shared robust LLM-JSON extraction + mock-fallback error signal.

Covers the single :func:`extract_json_payload` extractor and every one of the
five call-sites the weak ``str.replace("```", "")`` cleanup used to live in:

* ``ai_derivation_service._is_empty_completion`` (the ``:492`` site),
* ``ai_derivation_service._parse_json_list`` (the ``:2843`` site),
* ``ai_derivation_service._parse_json_object`` (same module, same pattern),
* ``architecture_decompose_service._parse_tree``,
* ``ai_review_service._parse_packages``,
* ``traceability_suggest_service._parse_suggestions``.

The acceptance criterion is that a fenced or prose-wrapped array is parsed and
that trailing "extra data" no longer aborts the whole completion. The
degraded-provider signal (``is_mock_fallback``) must survive the *error* path,
so a caller's error mapping can offer a graceful fallback.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from application.ai_derivation_service import (
    MOCK_FALLBACK_MARKER,
    AiDerivationService,
    LlmResponseError,
    _is_empty_completion,
    extract_json_payload,
)
from application.ai_review_service import AiReviewResponseError, AiReviewService
from application.architecture_decompose_service import (
    ArchitectureDecomposeService,
)
from application.base import ValidationError
from application.traceability_suggest_service import (
    SuggestLinksResponseError,
    TraceabilitySuggestService,
)


class TestExtractJsonPayload:
    def test_bare_array(self):
        assert extract_json_payload('[{"a": 1}]') == [{"a": 1}]

    def test_bare_object(self):
        assert extract_json_payload('{"a": 1}') == {"a": 1}

    def test_json_fenced_array_wrapped_in_prose(self):
        raw = 'Sure, here you go:\n```json\n[{"title": "x"}]\n```\nLet me know.'
        assert extract_json_payload(raw) == [{"title": "x"}]

    def test_bare_fence_without_language_tag(self):
        assert extract_json_payload("```\n[1, 2, 3]\n```") == [1, 2, 3]

    def test_trailing_extra_data_is_tolerated(self):
        """The exact regression from #1240: ``json.loads`` raises "Extra data"."""
        assert extract_json_payload('[{"a": 1}] -- hope this helps!') == [{"a": 1}]

    def test_leading_prose_before_bare_array(self):
        assert extract_json_payload('The result: [{"a": 1}] later text') == [{"a": 1}]

    def test_mock_fallback_marker_is_stripped(self):
        assert extract_json_payload(f"{MOCK_FALLBACK_MARKER}[1]") == [1]

    def test_marker_and_fence_together(self):
        raw = f"{MOCK_FALLBACK_MARKER}```json\n[2]\n```"
        assert extract_json_payload(raw) == [2]

    def test_curly_prose_before_the_real_array(self):
        raw = 'Use the {braces} wisely: [{"a": 1}]'
        assert extract_json_payload(raw) == [{"a": 1}]

    def test_empty_completion_raises_distinct_message(self):
        with pytest.raises(LlmResponseError, match="empty completion"):
            extract_json_payload("")

    def test_whitespace_only_raises_empty_message(self):
        with pytest.raises(LlmResponseError, match="empty completion"):
            extract_json_payload("   ")

    def test_none_raises_empty_message(self):
        with pytest.raises(LlmResponseError, match="empty completion"):
            extract_json_payload(None)

    def test_non_json_raises_not_valid(self):
        with pytest.raises(LlmResponseError, match="not valid JSON"):
            extract_json_payload("I cannot comply with that request.")

    def test_unterminated_fence_payload_raises_not_valid(self):
        with pytest.raises(LlmResponseError, match="not valid JSON"):
            extract_json_payload("```json\n[{\"a\": 1]\n```")


class TestSharedExtractorCallSites:
    """The five weak call-sites, each exercised with a fence and extra data."""

    def test_parse_json_list_fence_and_extra_data(self):
        assert AiDerivationService._parse_json_list(
            '```json\n[{"title": "A"}]\n```'
        ) == [{"title": "A"}]
        assert AiDerivationService._parse_json_list('[{"title": "B"}] thanks') == [
            {"title": "B"}
        ]

    def test_parse_json_list_rejects_non_list(self):
        with pytest.raises(LlmResponseError, match="not a JSON array as expected"):
            AiDerivationService._parse_json_list('{"a": 1}')

    def test_parse_json_list_empty_message_unchanged(self):
        with pytest.raises(LlmResponseError, match="empty completion"):
            AiDerivationService._parse_json_list("")

    def test_parse_json_object_fence_and_extra_data(self):
        assert AiDerivationService._parse_json_object(
            '```json\n{"title": "A"}\n```'
        ) == {"title": "A"}
        assert AiDerivationService._parse_json_object('{"title": "B"} done') == {
            "title": "B"
        }

    def test_is_empty_completion_fenced_empty_array(self):
        assert _is_empty_completion("```json\n[]\n```") is True
        assert _is_empty_completion("```\n{}\n```") is True

    def test_is_empty_completion_prose_is_not_empty(self):
        assert _is_empty_completion("I could not find anything.") is False

    def test_parse_tree_fence_and_extra_data(self):
        assert ArchitectureDecomposeService._parse_tree(
            '```json\n[{"title": "Child A"}]\n```'
        ) == [{"title": "Child A"}]
        assert ArchitectureDecomposeService._parse_tree(
            '[{"title": "Child B"}] -- done'
        ) == [{"title": "Child B"}]

    def test_parse_tree_invalid_json_raises_validation_error(self):
        with pytest.raises(ValidationError, match="not valid JSON"):
            ArchitectureDecomposeService._parse_tree("I cannot comply.")

    def test_parse_tree_non_array_raises_validation_error(self):
        with pytest.raises(ValidationError, match="not a JSON array"):
            ArchitectureDecomposeService._parse_tree('{"children": []}')

    def test_parse_packages_fence_and_extra_data(self):
        assert AiReviewService._parse_packages(
            '```json\n[{"index": 1}]\n```'
        ) == [{"index": 1}]
        assert AiReviewService._parse_packages('[{"index": 2}] done') == [{"index": 2}]

    def test_parse_packages_invalid_raises_typed_error(self):
        with pytest.raises(AiReviewResponseError, match="not valid JSON"):
            AiReviewService._parse_packages("nope")

    def test_parse_suggestions_fence_and_extra_data(self):
        assert TraceabilitySuggestService._parse_suggestions(
            '```json\n[{"finding_index": 1}]\n```'
        ) == [{"finding_index": 1}]
        assert TraceabilitySuggestService._parse_suggestions(
            '[{"finding_index": 2}] done'
        ) == [{"finding_index": 2}]

    def test_parse_suggestions_invalid_raises_typed_error(self):
        with pytest.raises(SuggestLinksResponseError, match="not valid JSON"):
            TraceabilitySuggestService._parse_suggestions("nope")


class TestMockFallbackSignalSurvivesErrorPath:
    """Issue #1240 item 3 — ``is_mock_fallback`` must not be lost on failure."""

    def test_complete_json_list_stamps_flag_on_parse_failure(self):
        service = AiDerivationService()
        with patch.object(
            service,
            "_complete",
            return_value=(f"{MOCK_FALLBACK_MARKER}not json", "cache-key"),
        ):
            with pytest.raises(LlmResponseError) as exc_info:
                service._complete_json_list(
                    prompt="x",
                    purpose="need_to_sysreq",
                    artifact_id="artifact-id",
                    max_retries=0,
                )
        assert exc_info.value.is_mock_fallback is True

    def test_real_answer_parse_failure_leaves_flag_false(self):
        service = AiDerivationService()
        with patch.object(
            service, "_complete", return_value=("not json at all", "cache-key")
        ):
            with pytest.raises(LlmResponseError) as exc_info:
                service._complete_json_list(
                    prompt="x",
                    purpose="need_to_sysreq",
                    artifact_id="artifact-id",
                    max_retries=0,
                )
        assert exc_info.value.is_mock_fallback is False

    def test_default_error_flag_is_false(self):
        assert LlmResponseError("boom").is_mock_fallback is False

    def test_review_parse_error_carries_degraded_flag(self):
        with pytest.raises(AiReviewResponseError) as exc_info:
            AiReviewService._parse_packages("nope", is_mock_fallback=True)
        assert exc_info.value.is_mock_fallback is True

    def test_suggest_parse_error_carries_degraded_flag(self):
        with pytest.raises(SuggestLinksResponseError) as exc_info:
            TraceabilitySuggestService._parse_suggestions(
                "nope", is_mock_fallback=True
            )
        assert exc_info.value.is_mock_fallback is True
