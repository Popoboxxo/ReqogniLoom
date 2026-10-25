"""Export promptfoo configs for every prompt-regression case (plan D / D2.2).

Why render here and not in promptfoo
------------------------------------
promptfoo evaluates its own ``{{mustache}}`` templating on every prompt it
receives. ReqogniLoom's ``render_template`` deliberately is not a generic
template engine (JSON braces must survive byte-identically, REQ-046), so a raw
``{var}`` body handed to promptfoo would be a second, divergent render path.
This command therefore resolves and renders each scenario through the real
production path (``application.prompt_resolver.resolve_and_render``) and hands
promptfoo a **literal** prompt that contains no placeholder anymore.

Determinism
-----------
Rendering runs under the nil tenant (``UUID(int=0)``) and without a workspace,
so ``resolve_and_render`` falls back to the factory defaults. There is nothing
tenant-specific in the generated config: the same cases always produce the same
prompts, which is exactly what a regression net needs.

Provider
--------
``echo`` (preliminary, ENT-D8 = A): it returns the rendered prompt, so a
regression is a diff in the prompt, no model call and no grading are involved.
``--deep`` additionally exports ``deep_assert`` blocks for a human-triggered run
against a real provider; it is refused whenever ``CI`` is set (QR-S12) so a
mis-invocation in CI cannot spend real LLM keys.

req_id: REQ-L2-PT-001
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from uuid import UUID

import yaml
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from application.prompt_resolver import (
    extract_placeholders,
    resolve_and_render,
    resolve_config_values,
)
from application.prompt_slots import get_prompt_slots, get_slot_data_variables
from application.prompt_testing.cases import CASES_DIR, PromptScenario, load_cases
from auth_tenancy.context import AuthContext
from persistence.tenancy import TenantContext

#: Nil tenant: no rows exist for it, so every template/variable resolves to its
#: factory default (see the module docstring).
NIL_TENANT = UUID(int=0)

#: Values of ``CI`` that mean "we are in CI". Anything else (unset, "false",
#: "0") leaves ``--deep`` available for a deliberate local deep run.
_CI_TRUTHY = frozenset({"1", "true", "yes"})

#: The preliminary provider (ENT-D8 = A). ``echo`` returns the rendered prompt
#: and therefore asserts on rendering, not on model quality.
DEFAULT_PROVIDER = "echo"


def _default_out_dir() -> Path:
    """``<repo>/promptfoo/generated`` (``BASE_DIR`` is ``backend/``)."""
    return Path(settings.BASE_DIR).parent / "promptfoo" / "generated"


def _in_ci() -> bool:
    return os.environ.get("CI", "").strip().lower() in _CI_TRUTHY


def _config_payload(
    slot: str,
    scenario: PromptScenario,
    rendered: str,
    *,
    provider: str,
    deep: bool,
) -> dict[str, Any]:
    """Build one config for exactly one ``(slot, scenario)`` pair.

    One prompt and one test per file is deliberate: promptfoo evaluates the
    cross-product of ``prompts`` × ``tests`` within a config, so a file holding
    two scenarios ran every assertion against both prompts (measured: 1,341 of
    1,444 cases failed in CI even though the rendered text was correct). A
    per-scenario file makes the pairing structural; the job then evaluates each
    file separately.
    """
    assertions = list(scenario.asserts)
    if deep:
        assertions.extend(scenario.deep_asserts)
    return {
        "description": f"reqogniloom prompt {slot}::{scenario.name}",
        "prompts": [{"id": f"{slot}::{scenario.name}", "raw": rendered}],
        "providers": [provider],
        "tests": [{"description": scenario.name, "assert": assertions}],
    }

class Command(BaseCommand):
    help = (
        "Render every prompt-regression scenario and write one promptfoo "
        "config per (slot, scenario) pair (LLM-free, provider 'echo')."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--out",
            default=None,
            help=(
                "Output directory (default: <repo>/promptfoo/generated). In a "
                "container pass a writable path such as /tmp/pf."
            ),
        )
        parser.add_argument(
            "--cases-dir",
            default=str(CASES_DIR),
            help="Directory holding <slot>.yaml case files.",
        )
        parser.add_argument(
            "--slot",
            action="append",
            default=None,
            help="Restrict the export to this slot (repeatable).",
        )
        parser.add_argument(
            "--check",
            action="store_true",
            help="Validate only: write nothing, fail on an incomplete set.",
        )
        parser.add_argument(
            "--deep",
            action="store_true",
            help=(
                "Also export deep_assert (grader) blocks. Refused when CI is "
                "set. Never part of the blocking CI gate."
            ),
        )
        parser.add_argument(
            "--provider",
            default=DEFAULT_PROVIDER,
            help=(
                "promptfoo provider id written into the config "
                "(default: echo; e.g. anthropic:messages:<model> with --deep)."
            ),
        )

    def handle(self, *args, **options) -> None:
        if options["deep"] and _in_ci():
            raise CommandError("--deep is refused in CI")

        slots = get_prompt_slots()
        # ``call_command`` hands an ``action="append"`` option through as
        # whatever the caller passed (a string for a single value, a list for
        # several), so normalise before iterating.
        raw_selected = options["slot"]
        if isinstance(raw_selected, str):
            selected = [raw_selected]
        elif raw_selected:
            selected = list(raw_selected)
        else:
            selected = sorted(slots)
        unknown = [name for name in selected if name not in slots]
        if unknown:
            raise CommandError(
                f"Unknown prompt slot(s): {', '.join(sorted(unknown))}"
            )

        cases = load_cases(Path(options["cases_dir"]))
        out_dir = Path(options["out"]) if options["out"] else _default_out_dir()

        ctx = AuthContext.system(tenant_id=NIL_TENANT)
        missing = 0
        unresolved = 0
        exported = 0
        memory_slots: list[str] = []
        memory_covered = 0

        TenantContext.set_tenant(NIL_TENANT)
        try:
            for name in selected:
                spec = slots[name]
                scenarios = cases.get(name) or []
                if not scenarios:
                    missing += 1
                    continue

                known = set(get_slot_data_variables(name))
                known.update(resolve_config_values(ctx, None))

                rendered: dict[str, str] = {}
                slot_unresolved = 0
                for scenario in scenarios:
                    prompt = resolve_and_render(
                        name,
                        ctx,
                        None,
                        config_overrides=scenario.config or None,
                        **scenario.data,
                    )
                    leftover = set(extract_placeholders(prompt)) & known
                    if leftover:
                        slot_unresolved += 1
                        self.stderr.write(
                            f"{name}/{scenario.name}: unresolved "
                            f"{sorted(leftover)}"
                        )
                    rendered[scenario.name] = prompt
                unresolved += slot_unresolved

                if "{memory_context}" in spec.default_content:
                    memory_slots.append(name)
                    if any(s.data.get("memory_context") for s in scenarios):
                        memory_covered += 1

                if not options["check"]:
                    out_dir.mkdir(parents=True, exist_ok=True)
                    for scenario in scenarios:
                        payload = _config_payload(
                            name,
                            scenario,
                            rendered[scenario.name],
                            provider=options["provider"],
                            deep=options["deep"],
                        )
                        target = (
                            out_dir
                            / f"{name}__{scenario.name}.promptfooconfig.yaml"
                        )
                        target.write_text(
                            yaml.safe_dump(
                                payload,
                                sort_keys=False,
                                allow_unicode=True,
                                default_flow_style=False,
                                width=4096,
                            ),
                            encoding="utf-8",
                        )
                exported += 1
        finally:
            TenantContext.clear_tenant()

        total = len(selected)
        self.stdout.write(
            f"promptfoo export: {exported}/{total} slots, {missing} missing "
            f"cases, {unresolved} unresolved placeholders, memory slots "
            f"covered {memory_covered}/{len(memory_slots)}"
        )

        if missing or unresolved or exported < total or memory_covered < len(memory_slots):
            raise CommandError(
                "promptfoo export incomplete: "
                f"{missing} missing cases, {unresolved} unresolved placeholders, "
                f"memory slots covered {memory_covered}/{len(memory_slots)}"
            )
