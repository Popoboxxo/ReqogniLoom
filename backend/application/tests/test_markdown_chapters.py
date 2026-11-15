"""``application.markdown_chapters`` — the pure chapter splitter (plan R1.1).

The splitter is the one place that decides what a chapter is, so these tests
pin the contract the reading view relies on: stable anchors, hierarchical
numbers, fenced code blocks that never become chapters, and a fail-soft
behaviour for degenerate bodies.

No database and no Django: this module is a plain text function.
"""
from __future__ import annotations

import pytest

from application.markdown_chapters import (
    MAX_CHAPTER_LEVEL,
    Chapter,
    slugify_heading,
    split_chapters,
)

# ---------------------------------------------------------------------------
# Empty and heading-less bodies
# ---------------------------------------------------------------------------


def test_empty_body_yields_single_root() -> None:
    chapters = split_chapters("")

    assert len(chapters) == 1
    assert chapters[0] == Chapter(number="", level=0, title="", anchor="section", body="")


def test_whitespace_only_body_is_an_empty_root() -> None:
    chapters = split_chapters("   \n\n\t\n")

    assert len(chapters) == 1
    assert chapters[0].body == ""
    assert chapters[0].level == 0


def test_no_headings_yields_one_chapter() -> None:
    chapters = split_chapters("Just a paragraph.\n\nAnd a second one.")

    assert len(chapters) == 1
    assert chapters[0].level == 0
    assert chapters[0].title == ""
    assert chapters[0].number == ""
    assert chapters[0].body == "Just a paragraph.\n\nAnd a second one."


def test_preamble_before_the_first_heading_becomes_a_level_zero_chapter() -> None:
    chapters = split_chapters("Lead paragraph.\n\n# Title\n\nBody.")

    assert [c.level for c in chapters] == [0, 1]
    assert chapters[0].body == "Lead paragraph."
    assert chapters[1].title == "Title"
    assert chapters[1].body == "Body."


def test_a_body_starting_with_a_heading_has_no_phantom_preamble() -> None:
    chapters = split_chapters("# Title\n\nBody.")

    assert len(chapters) == 1
    assert chapters[0].level == 1


# ---------------------------------------------------------------------------
# Fenced code blocks
# ---------------------------------------------------------------------------


def test_heading_inside_fence_is_not_a_chapter() -> None:
    markdown = (
        "# Real\n\n"
        "```markdown\n"
        "# Not a heading\n"
        "## Also not\n"
        "```\n"
        "\n"
        "## After\n\n"
        "Text."
    )

    chapters = split_chapters(markdown)

    assert [c.title for c in chapters] == ["Real", "After"]
    assert "# Not a heading" in chapters[0].body
    assert "## Also not" in chapters[0].body


def test_tilde_fence_is_respected() -> None:
    chapters = split_chapters("# Real\n\n~~~\n# Not a heading\n~~~\n\n## Next\n")

    assert [c.title for c in chapters] == ["Real", "Next"]


def test_unclosed_fence_swallows_the_rest_as_body() -> None:
    chapters = split_chapters("# Real\n\n```\n# still code\n## also code\n")

    assert len(chapters) == 1
    assert "## also code" in chapters[0].body


# ---------------------------------------------------------------------------
# Levels, flattening and numbering
# ---------------------------------------------------------------------------


def test_levels_above_max_are_body_text() -> None:
    chapters = split_chapters("# One\n\n### Three\n\n#### Four\n\nText.\n")

    assert [c.title for c in chapters] == ["One", "Three"]
    assert "#### Four" in chapters[1].body


def test_level_jump_is_flattened() -> None:
    """``#`` followed by ``###`` still numbers as a single child (no ``1.0.1``)."""
    chapters = split_chapters("# One\n\n### Three\n")

    assert [c.number for c in chapters] == ["1", "1.1"]


def test_configurable_max_level_flattens_everything_deeper() -> None:
    chapters = split_chapters("# One\n\n## Two\n\n### Three\n", max_level=1)

    assert [c.title for c in chapters] == ["One"]
    assert "## Two" in chapters[0].body
    assert "### Three" in chapters[0].body


def test_max_level_out_of_range_is_rejected() -> None:
    with pytest.raises(ValueError):
        split_chapters("# One", max_level=0)
    with pytest.raises(ValueError):
        split_chapters("# One", max_level=7)


def test_default_max_level_is_three() -> None:
    assert MAX_CHAPTER_LEVEL == 3


def test_numbering_is_nested() -> None:
    markdown = (
        "# A\n\n## A1\n\n### A1a\n\n## A2\n\n# B\n\n## B1\n"
    )

    assert [c.number for c in split_chapters(markdown)] == [
        "1",
        "1.1",
        "1.1.1",
        "1.2",
        "2",
        "2.1",
    ]


def test_chapter_body_excludes_its_subsections() -> None:
    markdown = "# A\n\nIntro A.\n\n## A1\n\nIntro A1.\n"

    chapters = split_chapters(markdown)

    assert chapters[0].body == "Intro A."
    assert chapters[1].body == "Intro A1."


# ---------------------------------------------------------------------------
# Heading syntax
# ---------------------------------------------------------------------------


def test_atx_trailing_hashes_are_stripped() -> None:
    chapters = split_chapters("## Title ##\n\nBody.\n")

    assert chapters[0].title == "Title"


def test_setext_headings_are_recognised() -> None:
    markdown = "Top\n===\n\nBody.\n\nSecond\n------\n\nMore.\n"

    chapters = split_chapters(markdown)

    assert [(c.level, c.title) for c in chapters] == [(1, "Top"), (2, "Second")]
    assert [c.number for c in chapters] == ["1", "1.1"]
    assert chapters[0].body == "Body."
    assert chapters[1].body == "More."


def test_hash_without_space_is_not_a_heading() -> None:
    chapters = split_chapters("#NotAHeading\n\nBody.\n")

    assert len(chapters) == 1
    assert chapters[0].level == 0
    assert "#NotAHeading" in chapters[0].body


def test_headings_are_never_rendered_as_html() -> None:
    """The splitter slices text; it never interprets or escapes markup."""
    chapters = split_chapters("# <b>Title</b>\n\n<script>x</script>\n")

    assert chapters[0].title == "<b>Title</b>"
    assert chapters[0].body == "<script>x</script>"


# ---------------------------------------------------------------------------
# Anchors
# ---------------------------------------------------------------------------


def test_ids_are_stable_and_unique() -> None:
    markdown = "# Purpose\n\n## Purpose\n\n# Purpose\n"

    first = split_chapters(markdown)
    second = split_chapters(markdown)

    assert [c.anchor for c in first] == ["purpose", "purpose-2", "purpose-3"]
    assert first == second, "the same body must always yield the same anchors"


def test_anchor_is_a_url_safe_slug() -> None:
    chapters = split_chapters("# System Spec: Overview!\n")

    assert chapters[0].anchor == "system-spec-overview"


def test_titleless_chapters_get_a_shared_fallback_anchor_family() -> None:
    chapters = split_chapters("Lead.\n\n# Real\n")

    assert chapters[0].anchor == "section"
    assert chapters[1].anchor == "real"


def test_slugify_heading_drops_non_ascii_letters() -> None:
    """Transparent limit: the anchor stays ASCII, so umlauts collapse."""
    assert slugify_heading("Überblick") == "berblick"
    assert slugify_heading("") == ""
    assert slugify_heading("  --  ") == ""


# ---------------------------------------------------------------------------
# Wire shape
# ---------------------------------------------------------------------------


def test_chapter_to_dict_carries_the_wire_keys() -> None:
    chapter = split_chapters("# Title\n\nBody.\n")[0]

    assert chapter.to_dict() == {
        "number": "1",
        "level": 1,
        "title": "Title",
        "anchor": "title",
        "body": "Body.",
    }


def test_split_chapters_is_repeatable() -> None:
    markdown = "# A\n\nText.\n\n## B\n\nMore.\n"

    assert split_chapters(markdown) == split_chapters(markdown)
