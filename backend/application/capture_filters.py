"""Deterministic pre-filter for ``suggestion.capture`` (ADR-032, plan P2 step 3).

The cheapest way to keep an inbox usable is to not spend a model call on
messages that cannot contain an artifact. The listen-mode spec (§4.2 step 3,
decision D7) fixes what is dropped: commands, short messages, and pure code or
log pastes. Everything here is a *rule*, not a classifier — D7 explicitly defers
a second classification stage to a later version, so a rule that is not
obviously right does not belong in this module.

The filter is deliberately conservative in the user's favour: a borderline
message is *kept* and goes to the model. Dropping a real requirement costs the
user a suggestion; passing a log paste costs one model call and lands in the
``skipped.filtered`` counter for tuning.

Ownership: the server owns this decision (spec G3). A client may run a cheap
pre-check to save a request, but it is not authoritative and must not be
trusted.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = [
    "MIN_MESSAGE_LENGTH",
    "FilterVerdict",
    "evaluate",
]

#: A message shorter than this cannot carry a requirement. 40 characters is the
#: threshold the Hermes plugin has been running with since 2026-09 (spec §2.2),
#: kept identical so the server and the client do not disagree about "short".
MIN_MESSAGE_LENGTH = 40

#: Characters that make a client treat the line as a command, not a message.
_COMMAND_PREFIXES = ("/", "!", "$", "#", ">")

#: A line that looks like source code or a log record. Used for the *paste*
#: rule: a message is a paste when MOST of its non-empty lines match.
_CODE_OR_LOG_LINE = re.compile(
    r"""^(?:
        \s{4,}\S                       # indented block
      | \s*(?:def|class|async\s+def|import|from|package|public|private|func|fn)\s
      | \s*(?:const|let|var|return|if|for|while|switch|try|catch|SELECT|INSERT|UPDATE|DELETE)\b
      | \s*[\]\}\)>]+\s*[;,]?$         # closing brackets / prompt markers
      | \s*[#*/]{2,}                   # comment banners
      | \s*[\[{].*[\]}]\s*[;,]?$        # json-ish line
      | \d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}          # timestamp
      | \s*(?:INFO|DEBUG|WARN|WARNING|ERROR|FATAL|TRACE)\b
      | \s*(?:Traceback|File\s+"|at\s+[\w.$]+\()
      | \s*[\w.$-]+\s*[:=]\s*\S+\s*$   # key: value / key=value line
    )""",
    re.VERBOSE,
)

#: Share of non-empty lines that must look like code/log for the *paste* rule.
_PASTE_LINE_RATIO = 0.6

#: Minimum number of lines before the paste rule may fire. Two-line answers like
#: "We use Postgres.\nBecause of transactions." are prose, not a paste.
_PASTE_MIN_LINES = 5


@dataclass(frozen=True)
class FilterVerdict:
    """Outcome of the rule filter.

    Attributes:
        keep: Whether the message should go on to the model.
        reason: ``""`` when kept, else the machine-stable reason label
            (``command``, ``too_short``, ``code_or_log_paste``,
            ``no_letters``). Used for logging and the ``skipped.filtered``
            counter, never as a user-facing error.
    """

    keep: bool
    reason: str = ""


def evaluate(text: str) -> FilterVerdict:
    """Decide whether *text* is worth a model call.

    Args:
        text: The redacted message text.

    Returns:
        A :class:`FilterVerdict`. Pure and cheap: no model, no database.
    """
    stripped = (text or "").strip()
    if not stripped:
        return FilterVerdict(False, "empty")

    if stripped.startswith(_COMMAND_PREFIXES):
        return FilterVerdict(False, "command")

    if len(stripped) < MIN_MESSAGE_LENGTH:
        return FilterVerdict(False, "too_short")

    if not any(character.isalpha() for character in stripped):
        return FilterVerdict(False, "no_letters")

    lines = [line for line in stripped.splitlines() if line.strip()]
    if len(lines) >= _PASTE_MIN_LINES:
        matching = sum(1 for line in lines if _CODE_OR_LOG_LINE.match(line))
        if matching / len(lines) >= _PASTE_LINE_RATIO:
            return FilterVerdict(False, "code_or_log_paste")

    return FilterVerdict(True)
