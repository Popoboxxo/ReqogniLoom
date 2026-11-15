"""Pure Markdown chapter splitter for the document reading view (R1).

The document reading view (``GET /api/v1/documents/{id}/view/``) shows a
``Document.body`` chapter by chapter instead of one opaque Markdown blob. This
module is the one place that decides what a chapter *is*: the headings of the
Markdown body — nothing else. There is deliberately no per-document chapter
configuration and no second artifact source (plan O1 = (a), triage E1(b)).

Design constraints (plan R1.1):

* **No Django import.** Only ``re`` and ``dataclasses`` — the splitter is a
  plain text function, testable without a database, and reusable by any
  renderer.
* **No HTML rendering.** The consumer renders Markdown itself; this module only
  slices text and never interprets inline markup.
* **Stable anchors.** ``anchor`` is a GitHub-style slug of the heading title,
  unique within the body (``-2``/``-3`` suffixes on repetition), so the same
  body always yields the same anchors — a client-side deep link survives a
  reload.
* **Fail-soft parsing.** A body without headings, an empty body, headings inside
  fenced code blocks and heading-level jumps all degrade to sensible chapters
  instead of raising.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "MAX_CHAPTER_LEVEL",
    "Chapter",
    "slugify_heading",
    "split_chapters",
]

#: Deepest heading level that becomes its own chapter. ``####`` and below stay
#: body text: a document that uses five levels of headings reads as a list of
#: fragments, not as chapters (plan R1.1).
MAX_CHAPTER_LEVEL = 3

#: ATX heading: ``## Title``. At least one space is required — ``##`` alone is
#: not a heading in CommonMark and must not silently become one here.
_ATX_RE = re.compile(r"^(#{1,6})[ \t]+(.*)$")
#: Trailing ``###`` of an ATX heading (``## Title ##``).
_ATX_TRAILING_RE = re.compile(r"[ \t]+#+[ \t]*$")
#: Setext underline: a line of ``=`` (level 1) or ``-`` (level 2).
_SETEXT_RE = re.compile(r"^ {0,3}(=+|-+)[ \t]*$")
#: Opening/closing fence of a fenced code block (``` or ~~~, at least three).
_FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
#: Everything that is not a lowercase ASCII letter or digit collapses into one
#: separator when slugifying.
_SLUG_SEPARATOR_RE = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class Chapter:
    """One Markdown chapter of a document body.

    Attributes:
        number: Hierarchical number ("1", "1.1", "1.1.1") derived from the
            heading levels; empty for the unnumbered level-0 chapter.
        level: Heading level (1..``MAX_CHAPTER_LEVEL``) or 0 for the text
            before the first heading.
        title: Heading text without the leading ``#``s; empty for level 0.
        anchor: Stable, document-unique slug for deep linking.
        body: Markdown of this chapter *without* its heading and without its
            subsections — every chapter is a flat leaf, so no text is repeated.
    """

    number: str
    level: int
    title: str
    anchor: str
    body: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "number": self.number,
            "level": self.level,
            "title": self.title,
            "anchor": self.anchor,
            "body": self.body,
        }


@dataclass
class _NumberingNode:
    """One entry of the numbering stack (a chapter that may still get children)."""

    level: int
    number: str
    children: dict[int, int] = field(default_factory=dict)


def slugify_heading(title: str) -> str:
    """Return the GitHub-style slug of *title* (``""`` for a titleless one).

    Deliberately ASCII-only and punctuation-free: the slug is used as a DOM id
    by the reading view, so it must stay a stable, URL-safe token. Transparent
    limit: non-ASCII letters (``Ä``, ``ß``) do not survive the lowercase-ASCII
    filter — a German heading therefore gets a shorter but still stable anchor.
    """
    lowered = (title or "").strip().lower()
    return _SLUG_SEPARATOR_RE.sub("-", lowered).strip("-")


def split_chapters(
    markdown: str, *, max_level: int = MAX_CHAPTER_LEVEL
) -> tuple[Chapter, ...]:
    """Split *markdown* into a flat, numbered tuple of :class:`Chapter`.

    Args:
        markdown: The document body (Markdown). ``None``/empty input is treated
            as an empty body.
        max_level: Deepest heading level that becomes a chapter (1..6). Levels
            beyond it stay body text (plan R1.1 — a ``####`` inside an ``##``
            chapter is text, not a chapter).

    Returns:
        One :class:`Chapter` per heading, in document order, plus a leading
        level-0 chapter when text precedes the first heading. An empty body
        yields exactly one empty level-0 chapter, so the reading view never has
        to special-case "no chapters".

    Raises:
        ValueError: *max_level* is outside 1..6.
    """
    if not 1 <= max_level <= 6:
        raise ValueError("max_level must be between 1 and 6.")

    text = markdown or ""
    if not text.strip():
        return (Chapter(number="", level=0, title="", anchor="section", body=""),)

    drafts: list[tuple[int, str, list[str]]] = []
    current_level = 0
    current_title = ""
    body_lines: list[str] = []
    fence: str | None = None
    lines = text.splitlines()

    def close_current() -> None:
        drafts.append((current_level, current_title, body_lines))

    index = 0
    while index < len(lines):
        line = lines[index]
        fence_match = _FENCE_RE.match(line)
        if fence is not None:
            # Inside a fenced block every line is literal text — including a
            # line that looks like a heading.
            body_lines.append(line)
            if (
                fence_match is not None
                and fence_match.group(1)[0] == fence[0]
                and len(fence_match.group(1)) >= len(fence)
            ):
                fence = None
            index += 1
            continue
        if fence_match is not None:
            fence = fence_match.group(1)
            body_lines.append(line)
            index += 1
            continue

        heading: tuple[int, str] | None = None
        consumed = 1
        atx_match = _ATX_RE.match(line)
        if atx_match is not None:
            title = _ATX_TRAILING_RE.sub("", atx_match.group(2)).strip()
            if title:
                heading = (len(atx_match.group(1)), title)
        elif line.strip() and index + 1 < len(lines):
            # Setext heading: the underline belongs to the *previous* line, so
            # the pair is consumed here and the text line never becomes body.
            underline = _SETEXT_RE.match(lines[index + 1])
            if underline is not None:
                level = 1 if underline.group(1).startswith("=") else 2
                heading = (level, line.strip())
                consumed = 2

        if heading is not None and heading[0] <= max_level:
            close_current()
            current_level, current_title = heading
            body_lines = []
        else:
            # No heading, a heading deeper than ``max_level``, or a heading-shaped
            # line that cannot be one: the raw lines stay body text.
            body_lines.extend(lines[index : index + consumed])
        index += consumed
    close_current()

    chapters: list[Chapter] = []
    anchors: dict[str, int] = {}
    stack: list[_NumberingNode] = []
    for level, title, chunk in drafts:
        body = "\n".join(chunk).strip()
        if level == 0:
            if not body:
                # A body that starts with a heading has no preamble — an empty
                # leading chapter would only add a phantom entry to the TOC.
                continue
            number = ""
            anchor = _unique_anchor("section", anchors)
        else:
            number = _next_number(stack, level)
            anchor = _unique_anchor(slugify_heading(title) or "section", anchors)
        chapters.append(
            Chapter(number=number, level=level, title=title, anchor=anchor, body=body)
        )
    return tuple(chapters)


def _unique_anchor(base: str, seen: dict[str, int]) -> str:
    """Return *base* or ``base-<n>``, recording the occurrence in *seen*."""
    count = seen.get(base, 0) + 1
    seen[base] = count
    return base if count == 1 else f"{base}-{count}"


def _next_number(stack: list[_NumberingNode], level: int) -> str:
    """Advance the numbering stack for a chapter of *level* and return its number.

    A heading that skips levels (``#`` followed by ``###``) keeps the skipped
    level empty instead of emitting a ``0`` segment: the number is the join of
    the counters actually on the stack, so ``1`` is followed by ``1.1``, never
    by ``1.0.1``. Transparent limit: a skipped level means two chapters can
    share a number in that rare case — the ``anchor`` is the stable identity,
    the number is display only.
    """
    while stack and stack[-1].level >= level:
        stack.pop()
    if not stack:
        stack.append(_NumberingNode(level=0, number=""))
    parent = stack[-1]
    parent.children[level] = parent.children.get(level, 0) + 1
    segment = str(parent.children[level])
    number = f"{parent.number}.{segment}" if parent.number else segment
    stack.append(_NumberingNode(level=level, number=number))
    return number
