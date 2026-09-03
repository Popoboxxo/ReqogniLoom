"""Tests for LlmResult score normalization (REQ-L3-LA001-002, R5/R7)."""
import pytest

from llm_adapter.interface import LlmResult


@pytest.mark.parametrize(
    "raw_score,expected",
    [(0.85, 0.85), (8.5, 0.85), (85.0, 0.85)],
)
def test_llm_result_normalizes_score_scale(raw_score, expected):
    result = LlmResult(
        score=raw_score, suggestions=[], provider="mock", model="mock", token_usage=None
    )
    assert result.score == pytest.approx(expected)


def test_llm_result_rejects_score_above_100():
    with pytest.raises(ValueError):
        LlmResult(
            score=250.0, suggestions=[], provider="mock", model="mock", token_usage=None
        )
