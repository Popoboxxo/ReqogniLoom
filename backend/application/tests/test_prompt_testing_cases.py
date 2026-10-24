"""Prompt-regression case files: coverage, format and render (plan D / D2.1).

The case files are the checked-in source of truth for the promptfoo gate. These
tests pin the three properties the export depends on:

* one case file per slot of the canonical registry (no orphan file, no slot
  without scenarios),
* a malformed file fails with a precise :class:`CaseFormatError` instead of
  silently shrinking the gate,
* every scenario renders through the real resolver without leaving a declared
  placeholder behind.

Path convention: ``backend/application/tests`` runs in the ``set-1-core`` CI
leg (index §f.4).
"""
from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest

from application.interview_protocol import IN_SCOPE_ARTIFACT_TYPES, parse_protocol_yaml
from application.prompt_resolver import extract_placeholders, resolve_and_render
from application.prompt_resolver import resolve_config_values
from application.prompt_slots import (
    get_prompt_slots,
    get_slot_data_variables,
    get_slot_default,
)
from application.prompt_testing.cases import (
    CASES_DIR,
    CaseFormatError,
    load_cases,
)
from auth_tenancy.context import AuthContext
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db

NIL_TENANT = UUID(int=0)


@pytest.fixture
def nil_tenant_ctx():
    """System context under the nil tenant (factory defaults only)."""
    TenantContext.set_tenant(NIL_TENANT)
    try:
        yield AuthContext.system(tenant_id=NIL_TENANT)
    finally:
        TenantContext.clear_tenant()


def _write_case(directory: Path, filename: str, body: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / filename
    path.write_text(body, encoding="utf-8")
    return path


def test_every_slot_has_exactly_one_case_file():
    """One case file per registry slot; the count can never be hard-coded.

    Case files are owned by plan D. A new prompt slot ships its case file in
    the same PR; other plans extend existing files with scenarios. Never merge
    a red case into ``main``.
    """
    slots = get_prompt_slots()
    files = sorted(path.stem for path in CASES_DIR.glob("*.yaml"))

    assert len(files) == len(slots)
    assert set(files) == set(slots)


def test_every_case_file_loads_without_error():
    loaded = load_cases()

    assert set(loaded) == set(get_prompt_slots())
    assert all(scenarios for scenarios in loaded.values())


def test_case_format_errors_are_reported(tmp_path):
    mismatched = _write_case(
        tmp_path / "mismatched",
        "alpha.yaml",
        "slot: beta\nscenarios:\n  - name: only\n",
    )
    with pytest.raises(CaseFormatError, match="filename"):
        load_cases(mismatched.parent)

    empty = _write_case(
        tmp_path / "empty",
        "alpha.yaml",
        "slot: alpha\nscenarios: []\n",
    )
    with pytest.raises(CaseFormatError, match="non-empty"):
        load_cases(empty.parent)

    unknown_assert = _write_case(
        tmp_path / "unknown_assert",
        "alpha.yaml",
        "slot: alpha\nscenarios:\n  - name: only\n"
        "    assert:\n      - {type: not-a-real-matcher, value: x}\n",
    )
    with pytest.raises(CaseFormatError, match="unknown assert type"):
        load_cases(unknown_assert.parent)

    grader_in_deterministic_tier = _write_case(
        tmp_path / "grader",
        "alpha.yaml",
        "slot: alpha\nscenarios:\n  - name: only\n"
        "    assert:\n      - {type: llm-rubric, value: x}\n",
    )
    with pytest.raises(CaseFormatError, match="deep_assert"):
        load_cases(grader_in_deterministic_tier.parent)

    duplicate_name = _write_case(
        tmp_path / "duplicate",
        "alpha.yaml",
        "slot: alpha\nscenarios:\n  - name: only\n  - name: only\n",
    )
    with pytest.raises(CaseFormatError, match="duplicate scenario name"):
        load_cases(duplicate_name.parent)


def test_llm_rubric_is_accepted_in_the_deep_tier(tmp_path):
    deep = _write_case(
        tmp_path,
        "alpha.yaml",
        "slot: alpha\nscenarios:\n  - name: only\n"
        "    deep_assert:\n      - {type: llm-rubric, value: x}\n",
    )

    loaded = load_cases(deep.parent)

    assert loaded["alpha"][0].deep_asserts == ({"type": "llm-rubric", "value": "x"},)
    assert loaded["alpha"][0].asserts == ()


def test_every_scenario_renders_without_unresolved_placeholders(nil_tenant_ctx):
    ctx = nil_tenant_ctx
    cases = load_cases()

    for name, scenarios in cases.items():
        known = set(get_slot_data_variables(name))
        known.update(resolve_config_values(ctx, None))
        for scenario in scenarios:
            rendered = resolve_and_render(
                name,
                ctx,
                None,
                config_overrides=scenario.config or None,
                **scenario.data,
            )
            leftover = set(extract_placeholders(rendered)) & known
            assert not leftover, (
                f"{name}/{scenario.name} left {sorted(leftover)} unresolved"
            )


def test_memory_slots_cover_a_filled_memory_block():
    cases = load_cases()

    for name, spec in get_prompt_slots().items():
        if "{memory_context}" not in spec.default_content:
            continue
        assert any(
            scenario.data.get("memory_context") for scenario in cases[name]
        ), f"{name} declares {{memory_context}} but no scenario fills it"


def test_protocol_defaults_are_valid_protocols():
    """The 8 per-type protocol slots are parsed, not rendered.

    ``interview.protocol.multi`` is deliberately excluded: it is a free-form
    chat prompt, not a ``phases:`` protocol (see interview_multi_protocol.py).
    """
    for artifact_type in IN_SCOPE_ARTIFACT_TYPES:
        slot = f"interview.protocol.{artifact_type}"
        body = get_slot_default(slot)

        assert body is not None
        protocol = parse_protocol_yaml(body)
        assert protocol.phases
