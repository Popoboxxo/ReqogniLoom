"""
Issue #652 — AiDerivationService cold-start retry tests.

Covers:
  * One automatic retry on empty or malformed LLM completion.
  * Distinct error messages for empty completion vs malformed JSON.
  * Bounded retry (gives up after max_retries).
"""
from unittest.mock import patch

import pytest

from application.ai_derivation_service import AiDerivationService, LlmResponseError


class TestColdStartRetry:
    def test_retries_once_on_empty_completion_then_succeeds(self):
        service = AiDerivationService()
        empty_then_valid = [
            ("", "cache-key-1"),
            ('[{"title": "Derived requirement"}]', "cache-key-2"),
        ]
        with patch.object(service, "_complete", side_effect=empty_then_valid):
            result = service._complete_json_list(
                prompt="derive from need X",
                purpose="need_to_sysreq",
                artifact_id="test-artifact-id",
            )
        assert result == [{"title": "Derived requirement"}]

    def test_raises_a_distinct_error_for_empty_completion_vs_malformed_json(self):
        service = AiDerivationService()
        with patch.object(service, "_complete", return_value=("", "cache-key")):
            with pytest.raises(LlmResponseError, match="empty completion"):
                service._complete_json_list(
                    prompt="x",
                    purpose="need_to_sysreq",
                    artifact_id="test-artifact-id",
                    max_retries=0,
                )

    def test_raises_malformed_json_error_for_non_empty_unparsable_content(self):
        service = AiDerivationService()
        with patch.object(
            service, "_complete", return_value=("not json at all", "cache-key")
        ):
            with pytest.raises(LlmResponseError, match="not valid JSON"):
                service._complete_json_list(
                    prompt="x",
                    purpose="need_to_sysreq",
                    artifact_id="test-artifact-id",
                    max_retries=0,
                )

    def test_gives_up_after_one_retry_if_still_failing(self):
        service = AiDerivationService()
        with patch.object(
            service, "_complete", return_value=("", "cache-key")
        ) as mocked:
            with pytest.raises(LlmResponseError):
                service._complete_json_list(
                    prompt="x",
                    purpose="need_to_sysreq",
                    artifact_id="test-artifact-id",
                )
        assert mocked.call_count == 2  # original attempt + exactly 1 retry

    def test_does_not_retry_on_valid_json_with_wrong_structure(self):
        service = AiDerivationService()
        with patch.object(
            service, "_complete", return_value=('["not an object"]', "cache-key")
        ) as mocked:
            with pytest.raises(LlmResponseError, match="none of them was an object"):
                service._complete_json_list(
                    prompt="x",
                    purpose="need_to_sysreq",
                    artifact_id="test-artifact-id",
                )
        assert mocked.call_count == 1  # no retry — data quality issue, not parse error
