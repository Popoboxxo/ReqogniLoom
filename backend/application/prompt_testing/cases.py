"""Prompt-regression scenarios for ``export_promptfoo_configs`` (plan D / D2.1).

Case files are owned by plan D. A new prompt slot ships its case file in the
same PR; other plans extend existing files with scenarios. Never merge a red
case into ``main``.

Why the cases live in code and not in the database
--------------------------------------------------
A prompt regression scenario is a fixture, not tenant data. Keeping it next to
the slot registry means it is reviewed and versioned together with the prompt
it pins, and a fresh tenant (or the nil tenant used by the exporter) can run
the whole set without a seed step.

File format
-----------
One file per slot, named ``<slot>.yaml``. The ``slot`` key must repeat the
filename stem — a rename that forgets the body is a hard error instead of a
silently orphaned file::

    slot: need_to_sysreq
    scenarios:
      - name: payment-with-memory
        data:
          need_title: "Zahlung erfassen"
          need_description: "..."
          memory_context: "Memory: payments are settled in EUR."
        config:
          max_requirements_per_need: 3
        assert:
          - {type: contains, value: "Zahlung erfassen"}
          - {type: contains, value: "payments are settled in EUR"}
        deep_assert:
          - {type: llm-rubric, value: "Each requirement is testable."}

``assert`` is the LLM-free gate (deterministic matchers only). ``deep_assert``
is the optional, human-triggered tier for grader-based matchers such as
``llm-rubric`` — it needs a real model, so it must never reach the blocking
CI path (see ``export_promptfoo_configs --deep``).

req_id: REQ-L2-PT-001
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

#: Directory holding the checked-in scenario files.
CASES_DIR: Path = Path(__file__).parent / "cases"

#: Matchers that are decided without a model and are therefore safe in the
#: blocking CI gate. ``javascript`` is included because promptfoo evaluates it
#: in its own sandbox, not against an LLM.
DETERMINISTIC_ASSERT_TYPES = frozenset(
    {
        "contains",
        "not-contains",
        "icontains",
        "not-icontains",
        "contains-all",
        "contains-any",
        "regex",
        "not-regex",
        "starts-with",
        "equals",
        "javascript",
    }
)

#: The one grader-based matcher the deep tier is documented for.
_GRADER_ASSERT_TYPE = "llm-rubric"


class CaseFormatError(ValueError):
    """Raised when a case file is malformed or internally inconsistent."""


@dataclass(frozen=True)
class PromptScenario:
    """One render-plus-assert scenario for a prompt slot.

    Attributes:
        name:         Unique within its slot; becomes the promptfoo test label.
        data:         Keyword arguments fed to ``resolve_and_render`` as data
                      variables (must cover every declared data variable of the
                      slot, otherwise the exporter reports an unresolved
                      placeholder).
        config:       ``config`` variable overrides for this scenario only.
        asserts:      Deterministic matchers, always exported.
        deep_asserts: Grader-based matchers, exported only with ``--deep``.
    """

    name: str
    data: dict[str, Any] = field(default_factory=dict)
    config: dict[str, Any] = field(default_factory=dict)
    asserts: tuple[dict[str, Any], ...] = ()
    deep_asserts: tuple[dict[str, Any], ...] = ()


def _assert_entries(
    raw: Any, *, where: str, allow_graders: bool
) -> tuple[dict[str, Any], ...]:
    """Validate and freeze one ``assert``/``deep_assert`` list."""
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise CaseFormatError(f"{where}: expected a list of assertions.")
    entries: list[dict[str, Any]] = []
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict) or "type" not in item:
            raise CaseFormatError(
                f"{where}: assertion #{index} must be a mapping with a 'type'."
            )
        assert_type = item["type"]
        if not isinstance(assert_type, str) or not assert_type:
            raise CaseFormatError(
                f"{where}: assertion #{index} has a non-string 'type'."
            )
        if assert_type == _GRADER_ASSERT_TYPE and not allow_graders:
            raise CaseFormatError(
                f"{where}: assertion #{index} is 'llm-rubric', which needs a "
                "grader LLM and is only allowed in 'deep_assert'."
            )
        if not allow_graders and assert_type not in DETERMINISTIC_ASSERT_TYPES:
            raise CaseFormatError(
                f"{where}: assertion #{index} uses unknown assert type "
                f"{assert_type!r}; deterministic matchers are "
                f"{sorted(DETERMINISTIC_ASSERT_TYPES)}."
            )
        entries.append(dict(item))
    return tuple(entries)


def _parse_scenario(raw: dict[str, Any], *, where: str) -> PromptScenario:
    """Validate one scenario mapping into a :class:`PromptScenario`."""
    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        raise CaseFormatError(f"{where}: 'name' must be a non-empty string.")

    data = raw.get("data") or {}
    config = raw.get("config") or {}
    if not isinstance(data, dict):
        raise CaseFormatError(f"{where} ({name!r}): 'data' must be a mapping.")
    if not isinstance(config, dict):
        raise CaseFormatError(f"{where} ({name!r}): 'config' must be a mapping.")

    return PromptScenario(
        name=name,
        data=dict(data),
        config=dict(config),
        asserts=_assert_entries(
            raw.get("assert"), where=f"{where} ({name!r})", allow_graders=False
        ),
        deep_asserts=_assert_entries(
            raw.get("deep_assert"),
            where=f"{where} ({name!r}) deep_assert",
            allow_graders=True,
        ),
    )


def load_cases(cases_dir: Path | str = CASES_DIR) -> dict[str, list[PromptScenario]]:
    """Load every ``<slot>.yaml`` under *cases_dir*, keyed by slot name.

    Raises:
        CaseFormatError: A file is unreadable/malformed, declares a different
            slot than its filename, has an empty scenario list, a duplicate
            scenario name, or an assertion that cannot run without a model in
            the deterministic tier.
    """
    directory = Path(cases_dir)
    if not directory.is_dir():
        raise CaseFormatError(f"Case directory {directory} does not exist.")

    loaded: dict[str, list[PromptScenario]] = {}
    for path in sorted(directory.glob("*.yaml")):
        slot = path.stem
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise CaseFormatError(f"{path.name}: invalid YAML ({exc}).") from exc
        if not isinstance(raw, dict):
            raise CaseFormatError(f"{path.name}: top level must be a mapping.")

        declared_slot = raw.get("slot")
        if declared_slot != slot:
            raise CaseFormatError(
                f"{path.name}: 'slot' is {declared_slot!r} but the filename "
                f"implies {slot!r}."
            )

        raw_scenarios = raw.get("scenarios")
        if not isinstance(raw_scenarios, list) or not raw_scenarios:
            raise CaseFormatError(
                f"{path.name}: 'scenarios' must be a non-empty list."
            )

        scenarios: list[PromptScenario] = []
        seen_names: set[str] = set()
        for index, raw_scenario in enumerate(raw_scenarios, start=1):
            if not isinstance(raw_scenario, dict):
                raise CaseFormatError(
                    f"{path.name}: scenario #{index} must be a mapping."
                )
            scenario = _parse_scenario(
                raw_scenario, where=f"{path.name} scenario #{index}"
            )
            if scenario.name in seen_names:
                raise CaseFormatError(
                    f"{path.name}: duplicate scenario name {scenario.name!r}."
                )
            seen_names.add(scenario.name)
            scenarios.append(scenario)

        loaded[slot] = scenarios

    return loaded


__all__ = [
    "CASES_DIR",
    "DETERMINISTIC_ASSERT_TYPES",
    "CaseFormatError",
    "PromptScenario",
    "load_cases",
]
