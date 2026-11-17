"""R2S-008 — one home for LLM JSON-output extraction and decoding.

Before this module the same "get the JSON out of an LLM completion" problem was
solved three different ways, each with its own tolerance family:

* ``llm_adapter.providers`` stripped every ````` ```` / `````json`` marker with
  ``str.replace`` and called ``json.loads`` (``strict-strip``); the consistency
  helper additionally retried the first-``{``-to-last-``}`` substring.
* ``application.ai_derivation_service.extract_json_payload`` tolerated a mock
  marker, a Markdown fence surrounded by prose and trailing text via
  ``JSONDecoder.raw_decode`` (``tolerant/prose-aware``, issue #1240).
* ``application.interview_multi_protocol`` required a lowercase
  `````json [ ... ] ``` `` fence and parsed only its array body
  (``list-only``).

This module owns the regexes and the decode algorithms for all three families.
``mode=`` selects the *existing* tolerance -- nothing is tightened or loosened
by the move.  It is a Layer-1 (``llm_adapter``) module with no application-layer
dependency: typed application errors stay at their call sites, which translate
:class:`JsonOutputError` into their own exception types so public exception
identity is unchanged.
"""
from __future__ import annotations

import json
import re
from typing import Any

__all__ = [
    "MOCK_FALLBACK_MARKER",
    "JsonOutputError",
    "decode_json_value",
    "extract_json_block",
    "parse_json_list",
]

#: Prefix stamped onto completions served by the mock provider after a real
#: provider failed (REQ-078).  Single source for the tolerant mode; the
#: application layer re-exports it under the same name.
MOCK_FALLBACK_MARKER = "[MOCK FALLBACK] "

#: Matches a fenced Markdown code block (`` ```json ... ``` `` or a bare
#: `` ``` ... ``` `` fence) and captures its body (issue #1240).
_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)

#: The interview protocol is deliberately stricter: lowercase ``json`` tag and
#: an array body only.  Kept distinct from :data:`_JSON_FENCE_RE` so the
#: list-only family does not accidentally become tolerant.
_LIST_FENCE_RE = re.compile(r"```json\s*(\[.*?\])\s*```", re.DOTALL)

#: Reused for ``raw_decode`` (prose-aware mode): unlike ``json.loads`` it stops
#: at the end of the *first* complete JSON value, tolerating trailing prose.
_JSON_DECODER = json.JSONDecoder()

_MODES = frozenset({"strict", "strict_braces", "tolerant", "list_only"})


class JsonOutputError(ValueError):
    """Raised when a completion carries no decodable JSON under the chosen mode.

    ``empty`` marks the "empty completion" branch so an application caller can
    preserve the two distinct ``LlmResponseError`` messages of the tolerant
    family.  It is a plain ``ValueError`` subclass on purpose: call sites catch
    it and re-raise their own typed error (no cross-layer exception import).
    """

    def __init__(self, message: str, *, empty: bool = False) -> None:
        super().__init__(message)
        self.empty = empty


def _check_mode(mode: str) -> None:
    """Validate *mode*, raising ``ValueError`` for an unknown family."""
    if mode not in _MODES:
        raise ValueError(f"Unknown LLM JSON output mode: {mode!r}")


def extract_json_block(raw: str, *, mode: str = "strict") -> str:
    """Return the normalized text window to decode for *raw* under *mode*.

    Args:
        raw: The raw completion text.  ``None`` is intentionally *not* guarded
            in ``strict`` mode: the provider call sites relied on the
            ``AttributeError`` from ``str.replace`` and that is preserved.
        mode: ``"strict"`` removes every `````json`` / ````` marker and strips
            whitespace (provider family); ``"tolerant"`` strips a leading mock
            marker and prefers a fenced body (issue #1240); ``"list_only"``
            returns the array body of the first lowercase `````json`` fence.

    Returns:
        The text window that the matching decode step consumes.

    Raises:
        JsonOutputError: ``tolerant`` input was empty (``empty=True``) or
            ``list_only`` input had no matching array fence.  ``strict`` never
            raises here -- an empty string is still handed to ``json.loads``
            so the caller's existing fallback fires exactly as before.
    """
    _check_mode(mode)
    if mode in {"strict", "strict_braces"}:
        return raw.replace("```json", "").replace("```", "").strip()

    if mode == "list_only":
        match = _LIST_FENCE_RE.search(raw)
        if match is None:
            raise JsonOutputError("The LLM response carried no ```json array fence.")
        return match.group(1)

    # tolerant / prose-aware (issue #1240)
    text = (raw or "").strip()
    if text.startswith(MOCK_FALLBACK_MARKER):
        text = text[len(MOCK_FALLBACK_MARKER):].strip()
    fence = _JSON_FENCE_RE.search(text)
    if fence is not None and fence.group(1).strip():
        text = fence.group(1).strip()
    if not text:
        raise JsonOutputError(
            "The LLM response was empty completion (cold-start or truncation).",
            empty=True,
        )
    return text


def _decode_tolerant(raw: str) -> Any:
    """Decode the first JSON value under the prose-aware family (issue #1240)."""
    text = extract_json_block(raw, mode="tolerant")
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        pass
    # Jump to the first opening bracket/brace and let raw_decode consume exactly
    # one JSON value, tolerating leading *and* trailing prose.
    for index, char in enumerate(text):
        if char not in "{[":
            continue
        try:
            value, _end = _JSON_DECODER.raw_decode(text, index)
        except (json.JSONDecodeError, TypeError):
            continue
        return value
    raise JsonOutputError("The LLM response was not valid JSON.")


def _decode_strict(raw: str, *, braces: bool) -> Any:
    """Decode a strict-strip completion, optionally retrying the brace span.

    The ``braces`` retry is the ``check_consistency`` family: after the first
    ``json.loads`` fails, the substring between the first ``{`` and the last
    ``}`` is tried.  Both branches raise :class:`JsonOutputError` on failure so
    the caller can degrade to its own structured fallback.
    """
    cleaned = extract_json_block(raw, mode="strict")
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        if braces:
            start, end = cleaned.find("{"), cleaned.rfind("}")
            if start != -1 and end > start:
                try:
                    return json.loads(cleaned[start : end + 1])
                except json.JSONDecodeError:
                    pass
        raise JsonOutputError("The LLM response was not valid JSON.") from exc


def decode_json_value(raw: str, *, mode: str = "strict") -> Any:
    """Decode the first JSON value of *raw* using the tolerance family *mode*.

    This is the single entry point used by the provider parsers and the
    application extractor.  List-shaped flows should prefer
    :func:`parse_json_list`, which also enforces the list type.
    """
    _check_mode(mode)
    if mode == "tolerant":
        return _decode_tolerant(raw)
    if mode == "list_only":
        return parse_json_list(raw, mode="list_only")
    return _decode_strict(raw, braces=(mode == "strict_braces"))


def parse_json_list(raw: str, *, mode: str = "list_only") -> list[Any]:
    """Decode *raw* and return its JSON list under the tolerance family *mode*.

    ``list_only`` reproduces the interview protocol's case-sensitive
    `````json [ ... ] ``` `` fence; ``tolerant`` reuses the prose-aware decoder
    and only adds the list-type check.

    Raises:
        JsonOutputError: no matching fence, malformed JSON, or the decoded
            value was not a list.
    """
    _check_mode(mode)
    if mode == "list_only":
        candidate = extract_json_block(raw, mode="list_only")
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError as exc:
            raise JsonOutputError("The LLM response was not valid JSON.") from exc
    else:
        parsed = decode_json_value(raw, mode="tolerant")
    if not isinstance(parsed, list):
        raise JsonOutputError("The LLM response was not a JSON array as expected.")
    return parsed
