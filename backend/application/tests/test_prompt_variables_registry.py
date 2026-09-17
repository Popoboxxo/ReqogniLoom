"""Factory prompt-variable registry + value (de)serialisation (spec §3.1)."""
from __future__ import annotations

import pytest

from application.prompt_variables import (
    PROMPT_VARIABLE_DEFAULTS,
    PromptVariableSpec,
    VariableTypeError,
    deserialize_variable_value,
    serialize_variable_value,
)


def test_every_entry_is_a_spec_keyed_by_its_own_name():
    for name, spec in PROMPT_VARIABLE_DEFAULTS.items():
        assert isinstance(spec, PromptVariableSpec)
        assert spec.name == name
        assert spec.kind in ("config", "data")
        assert spec.var_type in ("int", "str", "bool", "json")
        assert spec.description, f"{name} has no description"


def test_known_data_variables_are_registered():
    for name in ("req_title", "need_description", "arch_elements_json"):
        assert PROMPT_VARIABLE_DEFAULTS[name].kind == "data"


def test_data_variables_default_to_an_empty_string():
    assert PROMPT_VARIABLE_DEFAULTS["req_title"].default_value == ""


@pytest.mark.parametrize(
    ("var_type", "raw", "expected"),
    [
        ("int", "5", 5),
        ("str", '"abc"', "abc"),
        ("bool", "true", True),
        ("json", '{"a": 1}', {"a": 1}),
    ],
)
def test_deserialize_returns_the_typed_value(var_type, raw, expected):
    assert deserialize_variable_value(var_type, raw) == expected


def test_serialize_roundtrips_through_deserialize():
    for var_type, value in (("int", 5), ("str", "abc"), ("bool", False), ("json", [1, 2])):
        assert deserialize_variable_value(var_type, serialize_variable_value(value)) == value


def test_deserialize_falls_back_to_the_raw_string_for_str_type():
    """Legacy/hand-edited rows may hold a bare, unquoted string."""
    assert deserialize_variable_value("str", "plain text") == "plain text"


def test_deserialize_rejects_a_wrongly_typed_value():
    with pytest.raises(VariableTypeError):
        deserialize_variable_value("int", '"not a number"')


def test_deserialize_rejects_an_unknown_var_type():
    with pytest.raises(VariableTypeError):
        deserialize_variable_value("decimal", "1")
