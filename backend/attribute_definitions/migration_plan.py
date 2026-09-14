"""AWMS migration plan — declarative schema, validation and hashing (spec §3–§4).

AWMS (Attribut- & Wert-Migrationssystematik, Epic #934 WS7 / #940) makes
attribute *values* movable between definitions and fields with a reviewable,
versionable artefact: a plan file, not a script.

This module is deliberately **Django-free** (like :mod:`attribute_definitions.schema`)
so it can be unit-tested without a settings module, reused from a management
command, a REST view and an MCP handler, and hashed deterministically.

A normalized plan has the shape::

    {
      "version": 1,
      "id": "2026-09-rationale-recovery",
      "description": "...",
      "scope": {
        "tenant": "current",
        "item_type": "Requirement",
        "preset": ["standard", "extended"],
        "workspace": "*",
      },
      "mode": "dry_run",
      "options": {"idempotent": True, "abort_on_error": True, "audit": True},
      "steps": [ {"op": "migrate_value", ...}, ... ],
    }

The engine (:class:`application.attribute_migration_service.AttributeMigrationService`)
consumes the normalized form; nothing else re-parses the raw document.

Security: the schema is closed. An unknown key on a plan, scope, options or
step is a validation error, never silently dropped — the danger of a migration
tool is exactly the change the operator did not intend. Free SQL, Python hooks
and unconfirmed deletes are deliberately *not* part of the operation catalog
(spec §4).
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable

from attribute_definitions.migration_transforms import TRANSFORM_NAMES
from attribute_definitions.schema import ITEM_TYPES, PRESETS

# ---------------------------------------------------------------------------
# Operation catalog (spec §4)
# ---------------------------------------------------------------------------

OP_DEFINE_ATTRIBUTE = "define_attribute"
OP_RENAME_ATTRIBUTE = "rename_attribute"
OP_RETYPE_ATTRIBUTE = "retype_attribute"
OP_SPLIT_ATTRIBUTE = "split_attribute"
OP_MERGE_ATTRIBUTE = "merge_attribute"
OP_MIGRATE_VALUE = "migrate_value"
OP_MAP_VALUE = "map_value"
OP_BACKFILL_VALUE = "backfill_value"
OP_DERIVE_VALUE = "derive_value"
OP_DROP_ATTRIBUTE = "drop_attribute"
OP_REQUEUE_DEFINITION = "requeue_definition"
OP_VERIFY = "verify"
OP_EXPORT_SCOPE = "export_scope"
OP_IMPORT_SCOPE = "import_scope"

#: Every operation the engine executes. Anything else is a validation error —
#: in particular `deprecate_attribute`, `derive_entity` and `rollback` are
#: *not* here: the definition schema has no deprecation flag yet (see
#: :data:`UNSUPPORTED_OPS`), entity creation is spec §10 step 8, and rollback
#: is an operation on a *run*, not a plan step (CLI/REST/MCP expose it
#: directly).
OPS: frozenset[str] = frozenset(
    {
        OP_DEFINE_ATTRIBUTE,
        OP_RENAME_ATTRIBUTE,
        OP_RETYPE_ATTRIBUTE,
        OP_SPLIT_ATTRIBUTE,
        OP_MERGE_ATTRIBUTE,
        OP_MIGRATE_VALUE,
        OP_MAP_VALUE,
        OP_BACKFILL_VALUE,
        OP_DERIVE_VALUE,
        OP_DROP_ATTRIBUTE,
        OP_REQUEUE_DEFINITION,
        OP_VERIFY,
    }
)

#: Ops that exist in spec §4 but are intentionally outside the engine, each
#: with the concrete reason — so an author gets one actionable message instead
#: of "unknown op".
UNSUPPORTED_OPS: dict[str, str] = {
    "deprecate_attribute": (
        "the attribute definition schema has no 'deprecated' flag yet; "
        "retire the attribute by renaming/dropping it after 'verify' instead"
    ),
    "derive_entity": (
        "entity creation is spec §10 step 8 (bewusst zuletzt, braucht "
        "Rollback) and depends on the target entity existing; the Goal -> "
        "Measure plan (spec §8.3) is therefore blocked on #393 (Measure "
        "entity, Epic #934 non-goal) and ships as a documented draft"
    ),
    "rollback": (
        "rollback targets a run, not a plan; use the CLI --rollback <run_id> "
        "or POST /attribute-migration/runs/<id>/rollback/"
    ),
    "export_scope": (
        "definition-scope import/export is spec §10 step 7 and already served "
        "by the attribute-defaults REST/MCP surface; AWMS Teil A migrates values"
    ),
    "import_scope": (
        "definition-scope import/export is spec §10 step 7 and already served "
        "by the attribute-defaults REST/MCP surface; AWMS Teil A migrates values"
    ),
}

#: Value-copy mode of `migrate_value` (spec §3). `copy` is the safe default.
COPY = "copy"
MOVE = "move"
MIGRATE_MODES: frozenset[str] = frozenset({COPY, MOVE})

#: Backfill strategies (spec §4).
STRATEGY_CONSTANT = "constant"
STRATEGY_DERIVE_FROM_LINK = "derive_from_link"
STRATEGY_EXPRESSION = "expression"
BACKFILL_STRATEGIES: frozenset[str] = frozenset(
    {STRATEGY_CONSTANT, STRATEGY_DERIVE_FROM_LINK, STRATEGY_EXPRESSION}
)

#: `requeue_definition` actions (spec §8.4).
REQUEUE_RESET_UNCUSTOMIZED = "reset_uncustomized"
REQUEUE_ACTIONS: frozenset[str] = frozenset({REQUEUE_RESET_UNCUSTOMIZED})

#: Reference kinds. `model_field` may name a field on the type model **or** the
#: artifact-level system fields (`priority`, `owner`, `reporter`); the engine
#: resolves the carrier at execution time and fails the step with a precise
#: message when neither carries the name.
REF_MODEL_FIELD = "model_field"
REF_CUSTOM_FIELD = "custom_field"
REF_KINDS: frozenset[str] = frozenset({REF_MODEL_FIELD, REF_CUSTOM_FIELD})

#: Named predicate atoms an `only_if` expression may use. Evaluated against
#: facts the engine computes per row — never `eval()` (MCP-safety, spec §4).
CONDITION_ATOMS: frozenset[str] = frozenset(
    {
        "always",
        "source_is_empty",
        "source_has_text",
        "target_is_empty",
        "target_has_text",
        "to_is_empty",
        "to_has_text",
    }
)

_CONDITION_KEYWORDS = frozenset({"and", "or", "not"})
_CONDITION_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|[()]")

#: Named aggregates a `verify` assertion may compare. Deliberately report-based
#: (a safe subset of spec §3's illustrative `count(...) == N`): free SQL is
#: forbidden, and these five cover "nothing failed / something changed".
VERIFY_METRICS: frozenset[str] = frozenset(
    {"changed", "skipped", "failed", "matched", "steps", "steps_failed"}
)
_VERIFY_RE = re.compile(r"^\s*([a-z_]+)\s*(==|!=|<=|>=|<|>)\s*(-?\d+)\s*$")

MAX_SAMPLES = 100
PLAN_VERSION = 1

#: Closed key sets (spec §3). Unknown keys are a 400, never dropped.
_PLAN_KEYS = frozenset({"version", "id", "description", "scope", "mode", "options", "steps"})
_SCOPE_KEYS = frozenset({"tenant", "item_type", "preset", "workspace"})
_OPTION_KEYS = frozenset({"idempotent", "abort_on_error", "audit"})

_REF_KEYS = frozenset({"source", "target", "name"})
#: `transform:` accepts a bare name or a `{name, options}` object.
_TRANSFORM_KEYS = frozenset({"name", "options"})

#: Per-op allowed/required keys. `name`/`kind`/`type` etc. on `define_attribute`
#: are the attribute block itself and validated by `normalize_attribute`, so the
#: step-level check only guards the AWMS control keys.
_STEP_KEYS: dict[str, frozenset[str]] = {
    OP_DEFINE_ATTRIBUTE: frozenset(
        {"op", "attribute", "name", "kind", "type", "target", "section", "required_on"}
    ),
    OP_RENAME_ATTRIBUTE: frozenset({"op", "from", "to"}),
    OP_RETYPE_ATTRIBUTE: frozenset({"op", "name", "new_type", "value_map", "fallback"}),
    OP_SPLIT_ATTRIBUTE: frozenset({"op", "from", "targets", "separator"}),
    OP_MERGE_ATTRIBUTE: frozenset({"op", "sources", "to", "transform", "fallback"}),
    OP_MIGRATE_VALUE: frozenset(
        {"op", "from", "to", "mode", "only_if", "transform", "value_map", "fallback"}
    ),
    OP_MAP_VALUE: frozenset({"op", "target", "value_map", "fallback", "only_if"}),
    OP_BACKFILL_VALUE: frozenset(
        {"op", "target", "value_strategy", "value", "via", "fallback", "expression", "only_if"}
    ),
    OP_DERIVE_VALUE: frozenset({"op", "target", "expression", "only_if"}),
    OP_DROP_ATTRIBUTE: frozenset({"op", "name", "confirm"}),
    OP_REQUEUE_DEFINITION: frozenset({"op", "preset", "action"}),
    OP_VERIFY: frozenset({"op", "assertions"}),
}

#: Keys each op cannot run without.
_REQUIRED_STEP_KEYS: dict[str, frozenset[str]] = {
    OP_DEFINE_ATTRIBUTE: frozenset({"name"}),
    OP_RENAME_ATTRIBUTE: frozenset({"from", "to"}),
    OP_RETYPE_ATTRIBUTE: frozenset({"name", "new_type"}),
    OP_SPLIT_ATTRIBUTE: frozenset({"from", "targets"}),
    OP_MERGE_ATTRIBUTE: frozenset({"sources", "to"}),
    OP_MIGRATE_VALUE: frozenset({"from", "to"}),
    OP_MAP_VALUE: frozenset({"target", "value_map"}),
    OP_BACKFILL_VALUE: frozenset({"target", "value_strategy"}),
    OP_DERIVE_VALUE: frozenset({"target", "expression"}),
    OP_DROP_ATTRIBUTE: frozenset({"name", "confirm"}),
    OP_REQUEUE_DEFINITION: frozenset({"preset", "action"}),
    OP_VERIFY: frozenset({"assertions"}),
}

_ON_COLLISION_CHOICES = frozenset({"skip", "overwrite", "rename"})

_SCOPE_TENANT_CURRENT = "current"


class MigrationPlanError(ValueError):
    """Raised when a plan document is structurally invalid or unsafe.

    ``.errors`` lists every violation at once so an author sees the whole
    problem in one response instead of one JSON parse round-trip per typo.
    """

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


# ---------------------------------------------------------------------------
# Reference / transform normalization
# ---------------------------------------------------------------------------


def _ref_kind(raw: Any, label: str, errors: list[str]) -> str | None:
    if not isinstance(raw, str):
        errors.append(f"{label}: reference must be a string")
        return None
    value = raw.strip()
    if value not in REF_KINDS:
        errors.append(
            f"{label}: reference kind must be one of {sorted(REF_KINDS)}, got {value!r}"
        )
        return None
    return value


def normalize_reference(raw: Any, label: str, errors: list[str]) -> dict[str, str]:
    """Normalize a `{source|target: model_field|custom_field, name: <str>}` ref.

    Returns ``{"kind": ..., "name": ...}`` or a placeholder when invalid (the
    caller collects *errors* and raises once).
    """
    if not isinstance(raw, dict):
        errors.append(f"{label}: must be an object with 'name' and 'source'/'target'")
        return {"kind": REF_CUSTOM_FIELD, "name": ""}
    unknown = sorted(set(raw) - _REF_KEYS)
    if unknown:
        errors.append(f"{label}: unknown key(s): {', '.join(unknown)}")
    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        errors.append(f"{label}: 'name' is required")
        name = ""
    kind_raw = raw.get("source", raw.get("target"))
    if kind_raw is None:
        errors.append(f"{label}: 'source' or 'target' is required")
        kind_raw = REF_CUSTOM_FIELD
    kind = _ref_kind(kind_raw, label, errors)
    return {"kind": kind or REF_CUSTOM_FIELD, "name": name.strip()}


def normalize_transform(
    raw: Any, label: str, errors: list[str]
) -> dict[str, Any] | None:
    """Normalize `transform:` (bare name or ``{name, options}``) or ``None``."""
    if raw is None:
        return None
    if isinstance(raw, str):
        name: Any = raw
        options: Any = {}
    elif isinstance(raw, dict):
        unknown = sorted(set(raw) - _TRANSFORM_KEYS)
        if unknown:
            errors.append(f"{label}: unknown transform key(s): {', '.join(unknown)}")
        name = raw.get("name")
        options = raw.get("options", {})
    else:
        errors.append(f"{label}: 'transform' must be a name or an object")
        return None
    if not isinstance(name, str) or name.strip() not in TRANSFORM_NAMES:
        errors.append(
            f"{label}: unknown transform {name!r}; expected one of {sorted(TRANSFORM_NAMES)}"
        )
        return None
    if options is None:
        options = {}
    if not isinstance(options, dict):
        errors.append(f"{label}: transform 'options' must be an object")
        options = {}
    return {"name": name.strip(), "options": dict(options)}


def normalize_value_map(raw: Any, label: str, errors: list[str]) -> dict[str, Any] | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        errors.append(f"{label}: 'value_map' must be an object")
        return None
    return {str(key): value for key, value in raw.items()}


# ---------------------------------------------------------------------------
# Condition expressions
# ---------------------------------------------------------------------------


def condition_atoms(expression: str) -> set[str]:
    """Return the named atoms referenced by *expression* (no evaluation)."""
    return {
        token
        for token in _CONDITION_TOKEN_RE.findall(str(expression))
        if token not in _CONDITION_KEYWORDS and token == token.lower()
    }


def validate_condition(raw: Any, label: str, errors: list[str]) -> str | None:
    """Validate an `only_if` expression; return it normalized or ``None``."""
    if raw is None:
        return None
    if not isinstance(raw, str) or not raw.strip():
        errors.append(f"{label}: 'only_if' must be a non-empty string")
        return None
    expression = raw.strip()
    unknown = sorted(condition_atoms(expression) - CONDITION_ATOMS)
    if unknown:
        errors.append(
            f"{label}: unknown condition(s) {unknown}; expected one of "
            f"{sorted(CONDITION_ATOMS)}"
        )
        return None
    # Reject tokens the atom scan could not classify (e.g. '&&', '='): every
    # token must be an atom or one of and/or/not/parens.
    for token in _CONDITION_TOKEN_RE.findall(expression):
        if token in "()":
            continue
        if token in _CONDITION_KEYWORDS:
            continue
        if token not in CONDITION_ATOMS:
            errors.append(f"{label}: unsupported token {token!r} in 'only_if'")
            return None
    return expression


def parse_verify_assertion(assertion: str) -> tuple[str, str, int] | None:
    """Parse ``"<metric> <op> <int>"`` into ``(metric, op, number)`` or ``None``.

    The safe, report-based assertion vocabulary of :data:`VERIFY_METRICS`
    (spec §3's illustrative ``count(...) == N`` has no free-SQL form here).
    """
    match = _VERIFY_RE.match(str(assertion))
    if match is None:
        return None
    metric, operator, number = match.group(1), match.group(2), int(match.group(3))
    if metric not in VERIFY_METRICS:
        return None
    return metric, operator, number


def evaluate_condition(expression: str, facts: dict[str, bool]) -> bool:
    """Evaluate a validated `only_if` expression against per-row *facts*.

    Grammar (deliberately tiny, no ``eval`` — spec §4 forbids Python hooks)::

        expr   := term ('or' term)*
        term   := factor ('and' factor)*
        factor := 'not' factor | '(' expr ')' | atom

    Unknown atoms evaluate to ``False`` (fail-closed): a row whose condition
    cannot be decided is never changed. :func:`validate_condition` rejects
    unknown atoms at plan-validation time, so this is only a defensive default.
    """
    tokens = _CONDITION_TOKEN_RE.findall(str(expression))

    def parse_or(pos: int) -> tuple[bool, int]:
        value, pos = parse_and(pos)
        while pos < len(tokens) and tokens[pos] == "or":
            rhs, pos = parse_and(pos + 1)
            value = value or rhs
        return value, pos

    def parse_and(pos: int) -> tuple[bool, int]:
        value, pos = parse_factor(pos)
        while pos < len(tokens) and tokens[pos] == "and":
            rhs, pos = parse_factor(pos + 1)
            value = value and rhs
        return value, pos

    def parse_factor(pos: int) -> tuple[bool, int]:
        token = tokens[pos]
        if token == "not":
            value, pos = parse_factor(pos + 1)
            return (not value), pos
        if token == "always":
            return True, pos + 1
        if token == "(":
            value, pos = parse_or(pos + 1)
            if pos < len(tokens) and tokens[pos] == ")":
                pos += 1
            return value, pos
        return bool(facts.get(token, False)), pos + 1

    if not tokens:
        return True
    try:
        result, _ = parse_or(0)
    except IndexError:  # malformed expression — fail closed
        return False
    return result


# ---------------------------------------------------------------------------
# Plan normalization
# ---------------------------------------------------------------------------


def _scope_presets(raw: Any, errors: list[str]) -> list[str]:
    if raw is None:
        return list(PRESETS)
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list) or not raw:
        errors.append("scope.preset must be a preset name or a non-empty list")
        return list(PRESETS)
    presets: list[str] = []
    for entry in raw:
        if not isinstance(entry, str) or entry not in PRESETS:
            errors.append(f"scope.preset: unknown preset {entry!r}; expected {list(PRESETS)}")
            continue
        if entry not in presets:
            presets.append(entry)
    return presets or list(PRESETS)


def _scope_workspace(raw: Any, errors: list[str]) -> str | list[str]:
    if raw is None or raw == "*":
        return "*"
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list) or not raw:
        errors.append("scope.workspace must be '*' or a non-empty list of UUIDs")
        return "*"
    return [str(entry) for entry in raw]


def normalize_scope(raw: Any, errors: list[str]) -> dict[str, Any]:
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        errors.append("'scope' must be an object")
        raw = {}
    unknown = sorted(set(raw) - _SCOPE_KEYS)
    if unknown:
        errors.append(f"scope: unknown key(s): {', '.join(unknown)}")

    item_type = raw.get("item_type")
    if not isinstance(item_type, str) or item_type not in ITEM_TYPES:
        errors.append(
            f"scope.item_type must be one of {list(ITEM_TYPES)}, got {item_type!r}"
        )
        item_type = ITEM_TYPES[0]

    tenant = raw.get("tenant", _SCOPE_TENANT_CURRENT)
    if not isinstance(tenant, str) or not tenant.strip():
        errors.append("scope.tenant must be 'current' or a UUID string")
        tenant = _SCOPE_TENANT_CURRENT

    return {
        "tenant": tenant.strip(),
        "item_type": item_type,
        "preset": _scope_presets(raw.get("preset"), errors),
        "workspace": _scope_workspace(raw.get("workspace"), errors),
    }


def _normalize_step(
    raw: Any, index: int, errors: list[str]
) -> dict[str, Any]:
    label = f"steps[{index}]"
    if not isinstance(raw, dict):
        errors.append(f"{label}: step must be an object")
        return {"op": ""}
    op = raw.get("op")
    if not isinstance(op, str) or not op:
        errors.append(f"{label}: 'op' is required")
        return {"op": ""}
    if op in UNSUPPORTED_OPS:
        errors.append(f"{label}: op '{op}' is not supported — {UNSUPPORTED_OPS[op]}")
        return {"op": op}
    if op not in OPS:
        errors.append(f"{label}: unknown op {op!r}; expected one of {sorted(OPS)}")
        return {"op": op}

    unknown = sorted(set(raw) - _STEP_KEYS[op])
    if unknown:
        errors.append(f"{label} ({op}): unknown key(s): {', '.join(unknown)}")
    missing = sorted(k for k in _REQUIRED_STEP_KEYS[op] if raw.get(k) in (None, "", []))
    if missing:
        errors.append(f"{label} ({op}): missing required key(s): {', '.join(missing)}")

    step: dict[str, Any] = {"op": op}

    if op == OP_DEFINE_ATTRIBUTE:
        block = raw.get("attribute")
        if block is not None and not isinstance(block, dict):
            errors.append(f"{label}: 'attribute' must be an object")
            block = None
        step["attribute"] = block or {
            key: raw[key]
            for key in ("name", "kind", "type", "section", "target")
            if key in raw
        }
        step["required_on"] = _scope_presets(raw.get("required_on"), errors)
        step["attribute"].setdefault("kind", "extended")
        step["attribute"].setdefault("type", "text")
    elif op == OP_RENAME_ATTRIBUTE:
        step["from"] = normalize_reference(raw.get("from"), f"{label}.from", errors)
        step["to"] = normalize_reference(raw.get("to"), f"{label}.to", errors)
    elif op == OP_RETYPE_ATTRIBUTE:
        step["name"] = str(raw.get("name", ""))
        step["new_type"] = str(raw.get("new_type", ""))
        step["value_map"] = normalize_value_map(raw.get("value_map"), label, errors)
        step["fallback"] = raw.get("fallback")
    elif op == OP_SPLIT_ATTRIBUTE:
        step["from"] = normalize_reference(raw.get("from"), f"{label}.from", errors)
        separator = raw.get("separator")
        if separator is not None and not isinstance(separator, str):
            errors.append(f"{label}: 'separator' must be a string")
            separator = None
        step["separator"] = separator
        targets = raw.get("targets")
        if not isinstance(targets, list) or not targets:
            errors.append(f"{label}: 'targets' must be a non-empty list")
            targets = []
        normalized_targets = []
        for target_index, target in enumerate(targets):
            target_label = f"{label}.targets[{target_index}]"
            if not isinstance(target, dict):
                errors.append(f"{target_label}: must be an object")
                continue
            unknown_target = sorted(set(target) - {"to", "transform"})
            if unknown_target:
                errors.append(f"{target_label}: unknown key(s): {', '.join(unknown_target)}")
            normalized_targets.append(
                {
                    "to": normalize_reference(target.get("to"), f"{target_label}.to", errors),
                    "transform": normalize_transform(
                        target.get("transform"), target_label, errors
                    ),
                }
            )
        step["targets"] = normalized_targets
    elif op == OP_MERGE_ATTRIBUTE:
        sources = raw.get("sources")
        if not isinstance(sources, list) or not sources:
            errors.append(f"{label}: 'sources' must be a non-empty list")
            sources = []
        step["sources"] = [
            normalize_reference(source, f"{label}.sources[{i}]", errors)
            for i, source in enumerate(sources)
        ]
        step["to"] = normalize_reference(raw.get("to"), f"{label}.to", errors)
        step["transform"] = normalize_transform(raw.get("transform"), label, errors)
        step["fallback"] = raw.get("fallback")
    elif op == OP_MIGRATE_VALUE:
        step["from"] = normalize_reference(raw.get("from"), f"{label}.from", errors)
        step["to"] = normalize_reference(raw.get("to"), f"{label}.to", errors)
        mode = raw.get("mode", COPY)
        if not isinstance(mode, str) or mode not in MIGRATE_MODES:
            errors.append(f"{label}: 'mode' must be one of {sorted(MIGRATE_MODES)}")
            mode = COPY
        step["mode"] = mode
        step["only_if"] = validate_condition(raw.get("only_if"), label, errors)
        step["transform"] = normalize_transform(raw.get("transform"), label, errors)
        step["value_map"] = normalize_value_map(raw.get("value_map"), label, errors)
        step["fallback"] = raw.get("fallback")
    elif op == OP_MAP_VALUE:
        step["target"] = normalize_reference(raw.get("target"), f"{label}.target", errors)
        step["value_map"] = normalize_value_map(raw.get("value_map"), label, errors) or {}
        step["fallback"] = raw.get("fallback")
        step["only_if"] = validate_condition(raw.get("only_if"), label, errors)
    elif op == OP_BACKFILL_VALUE:
        step["target"] = normalize_reference(raw.get("target"), f"{label}.target", errors)
        strategy = raw.get("value_strategy")
        if not isinstance(strategy, str) or strategy not in BACKFILL_STRATEGIES:
            errors.append(
                f"{label}: 'value_strategy' must be one of {sorted(BACKFILL_STRATEGIES)}"
            )
            strategy = STRATEGY_CONSTANT
        step["value_strategy"] = strategy
        step["value"] = raw.get("value")
        step["fallback"] = raw.get("fallback")
        step["expression"] = raw.get("expression")
        via = raw.get("via")
        if via is not None and not isinstance(via, dict):
            errors.append(f"{label}: 'via' must be an object")
            via = None
        step["via"] = dict(via) if isinstance(via, dict) else {}
        step["only_if"] = validate_condition(raw.get("only_if"), label, errors)
    elif op == OP_DERIVE_VALUE:
        step["target"] = normalize_reference(raw.get("target"), f"{label}.target", errors)
        expression = raw.get("expression")
        if not isinstance(expression, str) or not expression.strip():
            errors.append(f"{label}: 'expression' must be a non-empty string")
            expression = ""
        step["expression"] = expression
        step["only_if"] = validate_condition(raw.get("only_if"), label, errors)
    elif op == OP_DROP_ATTRIBUTE:
        step["name"] = str(raw.get("name", ""))
        step["confirm"] = str(raw.get("confirm", ""))
        if step["confirm"] != step["name"]:
            errors.append(
                f"{label}: 'confirm' must repeat the attribute name {step['name']!r}"
            )
    elif op == OP_REQUEUE_DEFINITION:
        step["preset"] = _scope_presets(raw.get("preset"), errors)
        action = raw.get("action")
        if not isinstance(action, str) or action not in REQUEUE_ACTIONS:
            errors.append(f"{label}: 'action' must be one of {sorted(REQUEUE_ACTIONS)}")
            action = REQUEUE_RESET_UNCUSTOMIZED
        step["action"] = action
    elif op == OP_VERIFY:
        assertions = raw.get("assertions")
        if not isinstance(assertions, list) or not assertions:
            errors.append(f"{label}: 'assertions' must be a non-empty list")
            assertions = []
        normalized_assertions: list[str] = []
        for assertion_index, assertion in enumerate(assertions):
            parsed = _VERIFY_RE.match(str(assertion))
            if not parsed or parsed.group(1) not in VERIFY_METRICS:
                errors.append(
                    f"{label}.assertions[{assertion_index}]: expected "
                    f"'<metric> <op> <int>' with metric in {sorted(VERIFY_METRICS)}"
                )
                continue
            normalized_assertions.append(str(assertion).strip())
        step["assertions"] = normalized_assertions

    return step


def normalize_plan(payload: Any) -> dict[str, Any]:
    """Validate *payload* and return the normalized plan, or raise.

    Raises:
        MigrationPlanError: ``.errors`` lists every structural violation.
    """
    errors: list[str] = []
    if not isinstance(payload, dict):
        raise MigrationPlanError(["plan must be an object"])

    unknown = sorted(set(payload) - _PLAN_KEYS)
    if unknown:
        errors.append(f"plan: unknown key(s): {', '.join(unknown)}")

    plan_id = payload.get("id")
    if not isinstance(plan_id, str) or not plan_id.strip():
        errors.append("plan: 'id' is required")
        plan_id = "unnamed"

    version = payload.get("version", PLAN_VERSION)
    if not isinstance(version, int) or isinstance(version, bool) or version != PLAN_VERSION:
        errors.append(f"plan: unsupported 'version' {version!r}; expected {PLAN_VERSION}")

    description = payload.get("description", "")
    if not isinstance(description, str):
        errors.append("plan: 'description' must be a string")
        description = ""

    mode = payload.get("mode", "dry_run")
    if mode not in ("dry_run", "apply"):
        errors.append("plan: 'mode' must be 'dry_run' or 'apply'")
        mode = "dry_run"

    raw_options = payload.get("options", {})
    if raw_options is None:
        raw_options = {}
    if not isinstance(raw_options, dict):
        errors.append("plan: 'options' must be an object")
        raw_options = {}
    unknown_options = sorted(set(raw_options) - _OPTION_KEYS)
    if unknown_options:
        errors.append(f"plan.options: unknown key(s): {', '.join(unknown_options)}")
    options = {
        "idempotent": bool(raw_options.get("idempotent", True)),
        "abort_on_error": bool(raw_options.get("abort_on_error", True)),
        "audit": bool(raw_options.get("audit", True)),
    }

    raw_steps = payload.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        errors.append("plan: 'steps' must be a non-empty list")
        raw_steps = []

    steps = [_normalize_step(step, index, errors) for index, step in enumerate(raw_steps)]

    if errors:
        raise MigrationPlanError(errors)

    result: dict[str, Any] = {
        "version": PLAN_VERSION,
        "id": plan_id.strip(),
        "description": description,
        "scope": normalize_scope(payload.get("scope"), errors),
        "mode": mode,
        "options": options,
        "steps": steps,
    }
    if errors:
        raise MigrationPlanError(errors)
    return result


def plan_hash(normalized_plan: dict[str, Any]) -> str:
    """Return the deterministic SHA-256 of a normalized plan (spec §6).

    Stored on the run: the same plan executed twice is recognisable, and a
    changed plan carrying the same ``id`` is detectable instead of silently
    superseding the first run.
    """
    canonical = json.dumps(
        normalized_plan, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Document loading (JSON always; YAML when PyYAML is available)
# ---------------------------------------------------------------------------


def load_plan_document(text: str, *, filename: str = "") -> dict[str, Any]:
    """Parse a plan document from *text* (JSON, or YAML if PyYAML is present).

    The REST/MCP surfaces pass a decoded mapping; this loader exists for the
    CLI's file input. PyYAML is supplied transitively by ``drf-spectacular``;
    if it is missing a ``.yaml`` file still yields a precise error rather than
    an ``ImportError`` stack.
    """
    suffix = Path(filename).suffix.lower()
    stripped = text.strip()
    if suffix in (".json",) or (not suffix and stripped.startswith("{")):
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise MigrationPlanError([f"invalid JSON plan: {exc}"]) from exc
        return parsed
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError as exc:  # pragma: no cover - PyYAML ships with drf-spectacular
        raise MigrationPlanError(
            ["PyYAML is required to read a YAML plan; supply JSON instead"]
        ) from exc
    try:
        parsed = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise MigrationPlanError([f"invalid YAML plan: {exc}"]) from exc
    if parsed is None:
        raise MigrationPlanError(["plan document is empty"])
    return parsed


def load_plan_file(path: str | Path) -> dict[str, Any]:
    """Read and parse a plan file from disk."""
    file_path = Path(path)
    if not file_path.is_file():
        raise MigrationPlanError([f"plan file not found: {file_path}"])
    return load_plan_document(
        file_path.read_text(encoding="utf-8"), filename=file_path.name
    )


def iter_referenced_fields(step: dict[str, Any]) -> Iterable[dict[str, str]]:
    """Yield every value reference a step reads/writes (for snapshot planning)."""
    op = step.get("op")
    if op == OP_MIGRATE_VALUE:
        yield step.get("from", {})
        yield step.get("to", {})
    elif op in (OP_MAP_VALUE, OP_BACKFILL_VALUE, OP_DERIVE_VALUE):
        yield step.get("target", {})
    elif op == OP_SPLIT_ATTRIBUTE:
        yield step.get("from", {})
        for target in step.get("targets", []):
            yield target.get("to", {})
    elif op == OP_MERGE_ATTRIBUTE:
        for source in step.get("sources", []):
            yield source
        yield step.get("to", {})


__all__ = [
    "BACKFILL_STRATEGIES",
    "CONDITION_ATOMS",
    "COPY",
    "MAX_SAMPLES",
    "MIGRATE_MODES",
    "MOVE",
    "MigrationPlanError",
    "OP_BACKFILL_VALUE",
    "OP_DEFINE_ATTRIBUTE",
    "OP_DERIVE_VALUE",
    "OP_DROP_ATTRIBUTE",
    "OP_EXPORT_SCOPE",
    "OP_IMPORT_SCOPE",
    "OP_MAP_VALUE",
    "OP_MERGE_ATTRIBUTE",
    "OP_MIGRATE_VALUE",
    "OP_REQUEUE_DEFINITION",
    "OP_RENAME_ATTRIBUTE",
    "OP_RETYPE_ATTRIBUTE",
    "OP_SPLIT_ATTRIBUTE",
    "OP_VERIFY",
    "OPS",
    "PLAN_VERSION",
    "REF_CUSTOM_FIELD",
    "REF_KINDS",
    "REF_MODEL_FIELD",
    "REQUEUE_ACTIONS",
    "REQUEUE_RESET_UNCUSTOMIZED",
    "STRATEGY_CONSTANT",
    "STRATEGY_DERIVE_FROM_LINK",
    "STRATEGY_EXPRESSION",
    "TRANSFORM_NAMES",
    "UNSUPPORTED_OPS",
    "VERIFY_METRICS",
    "condition_atoms",
    "evaluate_condition",
    "iter_referenced_fields",
    "load_plan_document",
    "load_plan_file",
    "normalize_plan",
    "normalize_reference",
    "normalize_transform",
    "normalize_value_map",
    "parse_verify_assertion",
    "plan_hash",
    "validate_condition",
]
