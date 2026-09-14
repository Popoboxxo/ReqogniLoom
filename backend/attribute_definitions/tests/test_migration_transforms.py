"""AWMS transform registry (WS7 #940, spec §5)."""
from __future__ import annotations

import pytest

from attribute_definitions.migration_transforms import (
    APPLIED,
    DEFAULT_REGISTRY,
    FAILED,
    SKIPPED,
    TRANSFORM_NAMES,
    TransformContext,
    TransformRegistry,
    build_default_registry,
    enum_map,
    extract_rationale,
    first_paragraph,
    identity,
    join_values,
    link_derive,
    split_values,
    to_actor,
    to_date,
    to_enum,
    to_number,
    trim,
)


def test_default_registry_contains_the_spec_transforms() -> None:
    expected = {
        "identity",
        "trim",
        "enum_map",
        "first_paragraph",
        "extract_rationale",
        "join",
        "split",
        "to_number",
        "to_enum",
        "to_date",
        "to_actor",
        "link_derive",
    }
    assert expected <= TRANSFORM_NAMES
    assert TRANSFORM_NAMES == DEFAULT_REGISTRY.names()


class TestToActor:
    """`to_actor` normalizes legacy owner/assignee values (spec §8)."""

    def test_passthrough_of_actor_wire_form(self) -> None:
        value = {"kind": "user", "id": "abc"}
        assert to_actor(value, TransformContext()).value == value

    def test_uuid_becomes_user_id(self) -> None:
        uid = "6f1e1d2a-0000-4000-8000-000000000000"
        out = to_actor(uid, TransformContext())
        assert out.status == APPLIED
        assert out.value == {"kind": "user", "id": uid}

    def test_free_text_becomes_external_name(self) -> None:
        out = to_actor("  Alice  ", TransformContext())
        assert out.status == APPLIED
        assert out.value == {"kind": "external", "name": "Alice"}

    def test_instance_pk_becomes_user_id(self) -> None:
        class _User:
            pk = "11111111-1111-4111-8111-111111111111"

        out = to_actor(_User(), TransformContext())
        assert out.value == {"kind": "user", "id": _User.pk}

    def test_empty_values_skip(self) -> None:
        assert to_actor(None, TransformContext()).status == SKIPPED
        assert to_actor("   ", TransformContext()).status == SKIPPED
        assert to_actor({}, TransformContext()).status == SKIPPED


def test_registry_rejects_unknown_name() -> None:
    with pytest.raises(KeyError):
        DEFAULT_REGISTRY.get("nope")


def test_registry_register_and_override() -> None:
    registry = build_default_registry()
    registry.register("shout", lambda value, ctx: identity(str(value).upper(), ctx))
    assert "shout" in registry.names()
    out = registry.get("shout")("hi", TransformContext())
    assert out.value == "HI"


def test_identity_returns_the_value() -> None:
    assert identity("x", TransformContext()).value == "x"


def test_trim_normalizes_whitespace() -> None:
    out = trim("  a \n  b  ", TransformContext())
    assert out.status == APPLIED
    assert out.value == "a b"


def test_trim_skips_non_strings() -> None:
    assert trim(7, TransformContext()).status == SKIPPED


def test_enum_map_maps_and_falls_back() -> None:
    context = TransformContext(value_map={"high": "Must"}, fallback="Should")
    assert enum_map("high", context).value == "Must"
    assert enum_map("nope", context).value == "Should"


def test_enum_map_without_fallback_skips() -> None:
    out = enum_map("nope", TransformContext(value_map={"high": "Must"}))
    assert out.status == SKIPPED


def test_first_paragraph() -> None:
    out = first_paragraph("first line\n\nsecond", TransformContext())
    assert out.value == "first line"


def test_extract_rationale_uses_marker() -> None:
    out = extract_rationale("Some text. Begründung: it must hold.", TransformContext())
    assert out.status == APPLIED
    assert out.value == "it must hold."


def test_extract_rationale_falls_back_to_first_paragraph() -> None:
    out = extract_rationale("just a paragraph\n\nrest", TransformContext())
    assert out.status == APPLIED
    assert out.value == "just a paragraph"
    assert "no marker" in out.message


def test_extract_rationale_skips_empty() -> None:
    assert extract_rationale("", TransformContext()).status == SKIPPED


def test_join_and_split_use_separator() -> None:
    joined = join_values(["a", "b"], TransformContext(options={"separator": "; "}))
    assert joined.value == "a; b"
    splitted = split_values("a, b ,c", TransformContext(options={"separator": ","}))
    assert splitted.value == ["a", "b", "c"]


def test_join_fails_on_non_list() -> None:
    assert join_values("x", TransformContext()).status == FAILED


def test_to_number_parses_int_and_float() -> None:
    assert to_number("42", TransformContext()).value == 42
    assert to_number("3.5", TransformContext()).value == 3.5


def test_to_number_fails_on_garbage() -> None:
    assert to_number("abc", TransformContext()).status == FAILED


def test_to_date_normalizes_iso() -> None:
    assert to_date("2026-01-02T03:04:05", TransformContext()).value == "2026-01-02"
    assert to_date("not-a-date", TransformContext()).status == FAILED


def test_to_enum_uses_allowed_and_fallback() -> None:
    context = TransformContext(options={"allowed": ["a", "b"]}, fallback="a")
    assert to_enum("b", context).value == "b"
    assert to_enum("z", context).value == "a"


def test_link_derive_without_resolver_skips() -> None:
    assert link_derive("x", TransformContext()).status == SKIPPED


def test_link_derive_uses_injected_resolver() -> None:
    from attribute_definitions.migration_transforms import TransformOutcome

    context = TransformContext(
        link_resolver=lambda value: TransformOutcome(APPLIED, "derived")
    )
    assert link_derive("x", context).value == "derived"


def test_custom_registry_is_isolated_from_the_default() -> None:
    registry = TransformRegistry()
    registry.register("only_here", identity)
    assert "only_here" in registry.names()
    assert "only_here" not in DEFAULT_REGISTRY.names()
