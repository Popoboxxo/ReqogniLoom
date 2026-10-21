"""Text length limits are published to the client (GitHub #1392).

ROOT CAUSE this module pins
---------------------------
Every create dialog renders 43 text fields and **none** of them carries a
``maxlength``. The renderer was never the problem — ``TextField``/``TextArea``
have mirrored ``attribute.validation.length`` onto the control's ``maxLength``
since #1282. The problem is that the built-in attribute definitions published no
``validation`` block at all: ``introspect_core_attributes`` enumerated the
model's text columns without forwarding their ``max_length``, so the client had
nothing to mirror and the server's boundary (``Adr.title`` 200,
``Risk.title`` 255, ...) was only discoverable by triggering a 400.

The fix is strictly additive DATA: the bootstrap copies each text column's own
``max_length`` into ``validation.length``. Nothing is invented — a column
without a ``max_length`` (every ``TextField``, e.g. ``Adr.description``) stays
unbounded exactly as the server treats it.

These tests read the *generated preset definition*, not a serializer, so a
future field addition that forgets the limit fails here.
"""
from __future__ import annotations

import pytest

from attribute_definitions.management.commands.bootstrap_attribute_definitions import (
    introspect_core_attributes,
)

# ``introspect_core_attributes`` only walks the (already imported) model
# metadata — it touches no database, so these stay pure unit tests.


def _attributes(item_type: str, preset: str = "standard") -> dict[str, dict]:
    return {a["name"]: a for a in introspect_core_attributes(item_type, preset)}


def _length(attributes: dict[str, dict], name: str) -> int | None:
    attribute = attributes[name]
    return attribute.get("validation", {}).get("length")


class TestTextColumnsPublishTheirMaxLength:
    """The number must equal the model/serializer boundary verbatim."""

    @pytest.mark.parametrize(
        ("item_type", "field", "expected"),
        [
            # AdrSerializer.title = SanitizedCharField(max_length=200);
            # Adr.title = CharField(max_length=200). The issue measured the
            # server boundary at 200 (201 for 255/256/300 characters).
            ("Adr", "title", 200),
            ("Risk", "title", 255),
            ("Issue", "title", 255),
            ("Goal", "title", 255),
            ("TestCase", "title", 500),
            ("StakeholderNeed", "title", 500),
            ("ArchitectureElement", "title", 500),
            ("Requirement", "title", 500),
            # Icd has no dedicated DRF serializer (the view builds its DTO by
            # hand), so the model column is the only server boundary.
            ("Icd", "name", 500),
            ("GlossaryTerm", "term", 255),
            ("GlossaryTerm", "abbreviation", 64),
        ],
    )
    def test_publishes_the_column_limit(
        self, item_type: str, field: str, expected: int
    ) -> None:
        assert _length(_attributes(item_type), field) == expected

    def test_bounded_text_fields_publish_their_limit_too(self) -> None:
        # ``Adr`` models its narrative fields as TextField(max_length=...),
        # which is a real bound (and the serializer mirrors it), so those are
        # published as well — the rule is "the column's own max_length", not
        # "CharField only".
        adr = _attributes("Adr")
        assert _length(adr, "description") == 10000
        assert _length(adr, "context") == 5000
        assert _length(adr, "decision") == 5000
        assert _length(adr, "consequences") == 5000

    def test_truly_unbounded_text_columns_stay_unbounded(self) -> None:
        # A TextField without a max_length cannot be bounded client-side without
        # inventing a number the model does not enforce — the client would then
        # refuse text the server happily stores.
        assert _length(_attributes("Risk"), "description") is None
        assert _length(_attributes("Issue"), "description") is None
        assert _length(_attributes("GlossaryTerm"), "definition") is None


class TestLimitsAreAdditive:
    def test_required_flags_are_unchanged(self) -> None:
        """The length fix must not move the #912/#1192 required contract."""
        required = {
            name
            for name, attribute in _attributes("Adr").items()
            if attribute["required"]
        }
        assert required == {"title", "status"}

    def test_validation_block_only_carries_length(self) -> None:
        # #1392 is a length publication, not a new rule vocabulary: a stray
        # `regex`/`min`/`max` would change what the write path enforces.
        for attribute in _attributes("TestCase").values():
            assert set(attribute.get("validation", {})) <= {"length"}
