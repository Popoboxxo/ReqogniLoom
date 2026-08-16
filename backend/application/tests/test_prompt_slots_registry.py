"""Canonical slot registry: one entry per slot, with declared data variables."""
from __future__ import annotations

from application.ai_derivation_service import PROMPT_TEMPLATE_DEFAULTS
from application.interview_protocol import INTERVIEW_PROTOCOL_DEFAULTS
from application.prompt_slots import (
    PromptSlotSpec,
    get_prompt_slots,
    get_slot_data_variables,
    get_slot_default,
)
from application.prompt_variables import PROMPT_VARIABLE_DEFAULTS


def test_registry_covers_both_source_registries():
    slots = get_prompt_slots()

    for name in PROMPT_TEMPLATE_DEFAULTS:
        assert name in slots
    for name in INTERVIEW_PROTOCOL_DEFAULTS:
        assert name in slots


def test_every_entry_is_a_spec_keyed_by_its_own_name():
    for name, spec in get_prompt_slots().items():
        assert isinstance(spec, PromptSlotSpec)
        assert spec.name == name
        assert spec.default_content


def test_default_content_matches_the_source_registry():
    assert get_slot_default("need_to_sysreq") == PROMPT_TEMPLATE_DEFAULTS["need_to_sysreq"]


def test_unknown_slot_has_no_default_and_no_data_variables():
    assert get_slot_default("nope_not_a_slot") is None
    assert get_slot_data_variables("nope_not_a_slot") == ()


def test_declared_data_variables_are_registered_in_the_variable_catalog():
    for name, spec in get_prompt_slots().items():
        for var in spec.data_variables:
            assert var in PROMPT_VARIABLE_DEFAULTS, f"{name} declares unknown {var}"
            assert PROMPT_VARIABLE_DEFAULTS[var].kind == "data"


def test_need_to_sysreq_declares_its_two_data_variables():
    """``n`` became the ``max_requirements_per_need`` config variable (spec §4)."""
    assert set(get_slot_data_variables("need_to_sysreq")) == {
        "need_title",
        "need_description",
    }


def test_interview_protocol_slots_share_one_data_variable_set():
    for name in INTERVIEW_PROTOCOL_DEFAULTS:
        assert "artifact_type" in get_slot_data_variables(name)
