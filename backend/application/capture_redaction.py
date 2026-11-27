"""Secret redaction for ``suggestion.capture`` (ADR-032, plan P2 step 2).

The listen-mode contract (spec §4.2 step 2, §6) requires two things *before*
anything is stored or sent to a model provider:

1. credentials are removed, and
2. a message that is mostly credentials is dropped entirely instead of being
   stored as a redaction-pocked skeleton.

Keeping the patterns here — not in the service — is what makes them testable and
reviewable as one list (spec §6: "Muster zentral und testbar"). The service adds
no pattern of its own.

Design notes
------------
* Every pattern is anchored on a *shape*, never on a single vendor. A missed
  vendor is a leak, so the list errs towards over-redaction: a false positive
  costs one suggestion, a false negative costs a credential.
* Replacement tokens are stable and greppable, so an operator can tell *which*
  class of secret was removed without seeing the value.
* ``redacted_ratio`` compares removed characters with the original length, which
  is what "überwiegend geschwärzt" (spec §4.2 step 2) means operationally.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

__all__ = [
    "RedactionResult",
    "redact",
    "MOSTLY_REDACTED_RATIO",
]

#: Threshold above which a message counts as "mostly redacted" and is dropped.
#: Half the message being secret material is not a message worth proposing from.
MOSTLY_REDACTED_RATIO = 0.5


@dataclass(frozen=True)
class RedactionResult:
    """Outcome of one redaction pass.

    Attributes:
        text: The redacted text (unchanged when ``hits`` is empty).
        hits: ``label -> match count``, for the audit trail and the
            ``skipped.redacted`` counter. Never contains a match value.
        redacted_chars: Characters removed from the original. Used for the
            "mostly redacted" decision, never for a ratio the caller stores.
    """

    text: str
    hits: dict[str, int] = field(default_factory=dict)
    redacted_chars: int = 0

    @property
    def found(self) -> bool:
        """Return whether at least one secret-shaped token was removed."""
        return bool(self.hits)

    def ratio(self, original_length: int) -> float:
        """Return the share of the original that was redacted (0..1)."""
        if original_length <= 0:
            return 0.0
        return min(1.0, self.redacted_chars / original_length)


#: ``(label, pattern, replacement)`` in application order.
#:
#: PEM blocks come first so a key body is removed as a whole rather than being
#: partially caught by the base64-ish JSON-Web-Token rule.
_RULES: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "private_key",
        re.compile(
            r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?-----END [A-Z0-9 ]*PRIVATE KEY-----",
            re.DOTALL,
        ),
        "[REDACTED_PRIVATE_KEY]",
    ),
    (
        # ReqogniLoom's own API keys: ``reqlo_`` + opaque suffix. This is the
        # shape the project mints, so leaking one into a suggestion payload
        # would hand out a working credential.
        "api_key",
        re.compile(r"\breqlo_[A-Za-z0-9_\-]{6,}\b"),
        "[REDACTED_API_KEY]",
    ),
    (
        "auth_header",
        re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=\-]{12,}"),
        r"\1 [REDACTED_TOKEN]",
    ),
    (
        # Provider credential shapes. The hyphenated families MUST come first:
        # ``sk-ant-…`` / ``sk-proj-…`` cannot match the classic ``sk-[A-Za-z0-9]``
        # alternative (the internal hyphens break it), and those are the formats
        # this project's own primary providers issue.
        "cloud_key",
        re.compile(
            r"\b(?:sk-(?:ant|proj|or)-[A-Za-z0-9_\-]{10,}"
            r"|sk-[A-Za-z0-9]{16,}"
            r"|AKIA[0-9A-Z]{16}"
            r"|AIza[0-9A-Za-z_\-]{35}"
            r"|gh[pousr]_[A-Za-z0-9]{20,}"
            r"|github_pat_[A-Za-z0-9_]{20,}"
            r"|xox[abprs]-[A-Za-z0-9\-]{10,})\b"
        ),
        "[REDACTED_TOKEN]",
    ),
    (
        "jwt",
        re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\b"),
        "[REDACTED_JWT]",
    ),
    (
        # Labelled assignments: ``password=…``, ``api_key: …``,
        # ``AccountKey="<32 hex>"``. A raw opaque blob without a label is not
        # detectable without guessing, so the label is the signal — and the label
        # is kept so the excerpt stays readable.
        "secret_assignment",
        re.compile(
            r"(?i)\b([A-Za-z0-9_.\-]*(?:password|passwd|secret|token|key))"
            # 12+ characters: short values ("key: value", "token: refresh") are
            # ordinary prose, not credentials. Over-redaction costs a
            # suggestion; redacting a whole sentence's meaning costs trust.
            r"\s*[:=]\s*[\"']?([^\s\"',;]{12,})"
        ),
        r"\1=[REDACTED_SECRET]",
    ),
    (
        # Decision D4 keeps capture off by default; the address is still
        # personal data, so it is redacted rather than stored (spec §6
        # "Schwärzung … E-Mail-Adressen").
        "email",
        re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"),
        "[REDACTED_EMAIL]",
    ),
)


def redact(text: str) -> RedactionResult:
    """Return *text* with every recognised secret shape replaced.

    Args:
        text: The (already length-checked) message text.

    Returns:
        A :class:`RedactionResult`. ``text`` equals the input when nothing
        matched. Never raises: a redaction failure must not turn a capture
        attempt into a 500, and the patterns are compile-time constants.
    """
    if not text:
        return RedactionResult(text="")

    result = text
    hits: dict[str, int] = {}
    redacted_chars = 0
    for label, pattern, replacement in _RULES:
        removed = 0
        count = 0

        def _substitute(match: re.Match[str], _replacement: str = replacement) -> str:
            nonlocal removed, count
            count += 1
            rendered = match.expand(_replacement)
            # Only what actually disappeared counts as redacted: the
            # replacement token stays visible in the stored excerpt.
            removed += max(0, len(match.group(0)) - len(rendered))
            return rendered

        result = pattern.sub(_substitute, result)
        if not count:
            continue
        hits[label] = count
        redacted_chars += removed

    return RedactionResult(text=result, hits=hits, redacted_chars=redacted_chars)
