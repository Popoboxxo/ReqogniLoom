"""GitHub #1163 — ``score: null`` in valid provider JSON crashed the parser.

``float(data.get("score", default))`` only applies ``default`` when the key is
*missing*. A model that answers with valid JSON but an explicit ``"score": null``
— the realistic degraded case, e.g. a ``workspace-access-error`` issue with no
artifacts to score — therefore raised an uncaught ``TypeError`` and turned the
Celery task into a ``FAILURE`` instead of a reportable ``0.0`` result.

Two layers are pinned here:

* the shared normaliser :func:`_score_or_default` (null / non-numeric values fall
  back to the caller's default, numeric values pass through);
* the provider-facing outcome: ``check_consistency`` and ``validate_artifact``
  return a scored result instead of raising, for a completion that is otherwise
  valid JSON.
"""
from __future__ import annotations

import pytest

from llm_adapter.providers import (
    OpencodeGoProvider,
    ProviderConfig,
    _score_or_default,
)

# ---------------------------------------------------------------------------
# The normaliser, in isolation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value,expected",
    [
        (None, 0.0),
        ("not-a-number", 0.0),
        ([], 0.0),
        ({}, 0.0),
        (True, 1.0),
        (0, 0.0),
        (0.42, 0.42),
        ("0.75", 0.75),
    ],
)
def test_score_or_default_coerces_or_falls_back(value, expected) -> None:
    assert _score_or_default(value, 0.0) == expected


def test_score_or_default_honours_the_caller_default() -> None:
    """Derivation uses 1.0; consistency/validation use 0.0 (regression guard)."""
    assert _score_or_default(None, 1.0) == 1.0
    assert _score_or_default(None, 0.0) == 0.0
    # A real numeric score must never be overwritten by the default.
    assert _score_or_default(0.9, 1.0) == 0.9


# ---------------------------------------------------------------------------
# The provider path that reproduced the bug
# ---------------------------------------------------------------------------


def _provider() -> OpencodeGoProvider:
    return OpencodeGoProvider(
        ProviderConfig(provider_name="opencode_go", api_key="sk-dummy")
    )


def test_check_consistency_tolerates_null_score() -> None:
    provider = _provider()
    provider._invoke_chat = lambda prompt, timeout=None: (  # type: ignore[method-assign]
        '{"score": null, "suggestions": [], "issues": [{"id": "x"}]}',
        3,
    )

    result = provider.check_consistency("11111111-1111-1111-1111-111111111111")

    assert result.score == 0.0
    assert result.issues


def test_validate_artifact_tolerates_null_score() -> None:
    provider = _provider()
    provider._invoke_chat = lambda prompt, timeout=None: (  # type: ignore[method-assign]
        '{"score": null, "suggestions": ["could not score"]}',
        3,
    )

    result = provider.validate_artifact("11111111-1111-1111-1111-111111111111")

    assert result.score == 0.0
    assert result.suggestions == ["could not score"]


def test_numeric_score_is_preserved_through_the_provider() -> None:
    provider = _provider()
    provider._invoke_chat = lambda prompt, timeout=None: (  # type: ignore[method-assign]
        '{"score": 0.63, "suggestions": [], "issues": []}',
        3,
    )

    result = provider.check_consistency("11111111-1111-1111-1111-111111111111")

    assert result.score == pytest.approx(0.63)
