"""
SysEng 2.0 SE-Auditor — rule interface, preset mapping and self-registration.

UMSETZUNGSPLAN_SYSENG_2.0.md §2.2 (Pflichtmatrix), Phase 2 (RuleEngine Core).

Design (mirrors application/validators.py ``RIGOR_INVARIANT_PRESETS``):
- ``RULE_PRESET_MAP`` is the data-driven single source of truth for which rule
  ids are active per rigor tier — the same "tier → frozenset of codes" shape
  the invariant validator already uses.
- Each rule is a small class deriving from :class:`Rule`, decorated with
  ``@register_rule``. Registration is import-triggered: importing the
  ``traceability.audit.rules`` package registers every rule, and the RuleEngine
  iterates the registry. A new rule therefore never touches the engine or this
  module — see the "Adding a new rule" guide below.
- Minimal is empty *by construction*: ``RULE_PRESET_MAP["minimal"]`` is a
  literal empty frozenset and the settings-override path re-empties it
  unconditionally, so "Minimal = no SE-Auditor mandate" cannot regress by
  accident (§2.2).

Adding a new rule (for the follow-up rule-implementer agents)
-------------------------------------------------------------
1. Create ``traceability/audit/rules/<rule>.py``.
2. Subclass :class:`Rule`, set the class attributes:
       rule_id       = TRACE_P3            # a constant from this module
       is_scope_aware = False              # True only if it needs a baseline
                                            # scope (like TRACE-P7)
   and implement ``check(self, context) -> list[Finding]``.
3. Override ``severity_for_tier(tier)`` only if the severity varies per tier.
   The default is BLOCKER whenever the rule is active, and BLOCKER is the
   right default: it means "blocks baseline creation", which is exactly what a
   rule in this registry can do (see the enforcement-point section below).
4. Decorate the class with ``@register_rule``.
5. Add ``from . import <rule>`` to ``rules/__init__.py`` so it self-registers.
6. Ensure ``rule_id`` is listed in ``RULE_PRESET_MAP`` for every tier it must
   run in. ``register_rule`` rejects unknown ids, so a typo fails loudly.
7. If the check would require a data-model prerequisite that does not exist
   yet (e.g. a missing ``LinkType`` enum member), do NOT implement it against
   a string-literal workaround — set ``deferred_reason`` instead (see the
   "Deferred rules" section of :class:`Rule`) and let ``check`` return ``[]``.

Do NOT re-implement endpoint-type legality — call
``traceability.types.check_se_link_semantics`` instead (§2.1).

Where a rule is ENFORCED (read this before picking a severity)
------------------------------------------------------------
This registry is the only rule vocabulary, and the **baseline gate is the only
enforcement point**. A BLOCKER finding reaches the user through exactly one
producer — ``application/baseline_facade.py:488`` ->
``AuditService.blocking_findings`` (``application/audit_service.py:406-441``)
— and that producer is the only one with a remediation path: a waiver **per
finding** (``baseline/waivers.py``, ``BaselineGateWaiver``,
``baseline/models.py:190-215``). So "BLOCKER" in this module means "this blocks
baseline creation until it is fixed or waived", never "this rejects a POST".

Do NOT add a create/update gate for relation rules. That was tried once and is
documented as refuted: enforcing ``mandatory_fields`` as a create gate 400'd
every existing client, every quick-create dialog and roughly fifteen E2E specs
(migration ``0005_relax_requirement_create_required``; regression test
``rest_api/tests/test_bootstrapped_definition_allows_creates.py``). A gate that
has to be taken back is not a gate. This question reopens only through a
decision that supersedes ADR-007 — not by adding a rule file.

Field-level obligations are a **different mechanism** and stay with
``attribute_definitions/field_validation.py``, which already rejects on create
*and* update with field-precise 400 details. Keep the two apart: a field
obligation refused at the payload and a relation obligation waived per finding
are two different error contracts for the same user, and mixing them is what
produced the create-gate break.

One vocabulary, one owner: the second, purely documented rule vocabulary is
retired (ADR-007). The allocation obligation is carried by ``TRACE-P2``, the
test-link obligation by ``TRACE-P6`` + ``VERIF-P8``, and ``source`` is a
*coverage convention* rather than a rule — no writer in the codebase ever
fills that field, so a rule rejecting an artifact for it would only be
satisfied on paper. Severity for those inherited obligations is deliberately
un-promoted where the evidence says so; see
``rules/trace_derivation_allocation.py`` for the ``TRACE-P2`` calibration
(#581: a BLOCKER there produced a 100% blocker rate and an unpassable gate).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, FrozenSet, List, Mapping

from traceability.audit.types import AuditContext, Finding, Severity

# ---------------------------------------------------------------------------
# Rule id constants (§2.2 Pflichtmatrix)
# ---------------------------------------------------------------------------

TRACE_P1 = "TRACE-P1"
TRACE_P1B = "TRACE-P1b"
TRACE_P2 = "TRACE-P2"
TRACE_P3 = "TRACE-P3"
TRACE_P4 = "TRACE-P4"
TRACE_P5 = "TRACE-P5"
TRACE_P6 = "TRACE-P6"
TRACE_P7 = "TRACE-P7"
ARCH_003 = "ARCH-003"
#: TRACE-P6 and VERIF-P8 together carry the "a Requirement needs verification
#: evidence" obligation that used to exist as a second, documented rule id with
#: no implementation (ADR-007). No new id was added for it — that is the point
#: of the decision.
VERIF_P8 = "VERIF-P8"
CONS_P9 = "CONS-P9"
CONS_P10 = "CONS-P10"
#: ADR-005 removed CONS-P11 (V-model level progression). It asserted that
#: ``Requirement.level`` agrees with the decomposition graph, and the same ADR
#: made ``level`` **derived from** that graph — the rule could never fire. Its
#: id is deliberately gone from every tier set below, not merely unregistered:
#: a rule id that is still listed but has no implementation is a preset that
#: promises a check it cannot run.
#: #402 (cluster 5) — Stakeholder-Goal traceability. Not part of the original
#: §2.2 Pflichtmatrix: it is the validation-pillar rule the Goals feature was
#: missing. Advisory (WARNING) at every tier it runs in; see
#: rules/validation_goals.py.
VAL_P1 = "VAL-P1"

# ---------------------------------------------------------------------------
# Preset → active rule ids (single source of truth, §2.2)
# ---------------------------------------------------------------------------

# Standard and Extended share this baseline set.
_STANDARD_RULES: FrozenSet[str] = frozenset(
    {
        TRACE_P1,
        TRACE_P1B,
        TRACE_P2,  # active at standard too, but as WARNING (see severity_for_tier)
        TRACE_P4,
        TRACE_P6,
        CONS_P9,
        CONS_P10,
    }
)

#: Extended adds the stricter SE-only rules on top of the standard set.
_EXTENDED_ONLY_RULES: FrozenSet[str] = frozenset(
    {
        TRACE_P3,
        TRACE_P5,
        TRACE_P7,
        ARCH_003,
        VERIF_P8,
        VAL_P1,
    }
)

#: The "Full-SE" mandate, coupled to **stage 3 / Extended only** (Epic #934
#: WS6, #939). These are the rules that demand a complete SE chain —
#: architecture derivation (TRACE-P3/P5), baseline-scope consistency (TRACE-P7),
#: architecture decomposition (ARCH-003) and leaf-requirement verification
#: (VERIF-P8). A stage-1 (Minimal) or stage-2 (Standard) workspace must never
#: fail on them: Minimal maps to the empty rule set structurally, and Standard's
#: baseline set is disjoint from this one by construction.
#: ``test_se_auditor_stage_coupling`` pins both.
FULL_SE_RULE_IDS: FrozenSet[str] = _EXTENDED_ONLY_RULES

#: Tier → set of active rule ids. Minimal is intentionally empty ("Minimal =
#: no SE-Auditor mandate", §2.2) and this emptiness is enforced structurally
#: (see _get_rule_preset_map).
RULE_PRESET_MAP: Mapping[str, FrozenSet[str]] = {
    "minimal": frozenset(),
    "standard": _STANDARD_RULES,
    "extended": _STANDARD_RULES | _EXTENDED_ONLY_RULES,
}

#: Every rule id known to the catalogue (union across all tiers).
ALL_RULE_IDS: FrozenSet[str] = frozenset().union(*RULE_PRESET_MAP.values())

#: Fallback tier for unknown tier names — mid-rigor "standard" is the safest
#: default (matches the ArchitectureElement invariant validator). Minimal is
#: never a fallback so a typo can never silently disable auditing.
_FALLBACK_TIER = "standard"

# Structural guarantee, asserted at import time: Minimal has zero rules.
assert not RULE_PRESET_MAP["minimal"], "Minimal preset must have no audit rules"


def _get_rule_preset_map() -> Mapping[str, FrozenSet[str]]:
    """Return the effective tier→rule-ids mapping.

    Reads the optional ``SE_AUDITOR_RULE_PRESETS`` Django setting (dict of tier
    name → iterable of rule ids) and merges it over the built-in defaults,
    intersected with :data:`ALL_RULE_IDS` so a misconfiguration can never
    introduce an unknown rule id. The Minimal tier is forced empty regardless
    of any override — the "Minimal = no mandate" guarantee is structural, not
    configurable.
    """
    try:
        from django.conf import settings

        override = getattr(settings, "SE_AUDITOR_RULE_PRESETS", None)
    except Exception:  # pragma: no cover — settings not configured (tooling)
        override = None

    if not isinstance(override, dict):
        merged: Dict[str, FrozenSet[str]] = dict(RULE_PRESET_MAP)
    else:
        merged = dict(RULE_PRESET_MAP)
        for tier, ids in override.items():
            try:
                merged[tier] = frozenset(ids) & ALL_RULE_IDS
            except TypeError:
                continue

    # Structural enforcement: Minimal is always empty.
    merged["minimal"] = frozenset()
    return merged


def full_se_rule_ids() -> FrozenSet[str]:
    """Return the Full-SE rule ids (stage 3 / Extended only). See the constant."""
    return FULL_SE_RULE_IDS


def active_rule_ids_for_tier(tier: str) -> FrozenSet[str]:
    """Return the set of active rule ids for *tier*.

    Unknown tiers fall back to the standard set. Minimal always returns the
    empty set.
    """
    presets = _get_rule_preset_map()
    active = presets.get(tier)
    if active is None:
        active = presets[_FALLBACK_TIER]
    return active


# ---------------------------------------------------------------------------
# Rule interface
# ---------------------------------------------------------------------------


class Rule(ABC):
    """Base class for a single SE-Auditor rule.

    Subclasses set two class attributes and implement :meth:`check`:

        rule_id: str          — a constant from this module (e.g. ``TRACE_P7``).
        is_scope_aware: bool  — ``True`` if the rule needs a baseline scope in
                                the context (the RuleEngine then runs it once
                                per requested scope); ``False`` (default) if it
                                is a graph-wide, scope-agnostic check.

    Instances are stateless and constructed once at registration time.

    Deferred rules
    --------------
    A rule whose check logic depends on a data-model prerequisite that does
    not exist yet (e.g. a ``LinkType`` enum member that was never added)
    should NOT be implemented against an unvalidated workaround (raw string
    literals bypassing ``TraceLinkManager`` validation, ad-hoc DB flags,
    etc.). Instead, set the class attribute ``deferred_reason`` to a
    non-empty, human- and machine-readable string explaining what is
    missing. The rule stays registered and visible in the catalogue (see
    :func:`get_registered_rules`), but :class:`~traceability.audit.rule_engine.RuleEngine`
    short-circuits it to an empty finding list for every rigor tier — its
    ``check`` method is never invoked, so it can never raise or query the
    database. Once the missing prerequisite lands, clear ``deferred_reason``
    and implement ``check`` for real; the rule id, its ``RULE_PRESET_MAP``
    placement and every caller stay unchanged.
    """

    rule_id: str = ""
    is_scope_aware: bool = False
    #: ``None`` (default) = the rule runs normally. A non-empty string marks
    #: the rule as deferred: it is registered/visible but the RuleEngine
    #: guarantees zero findings and skips ``check`` entirely for every tier.
    #: See the "Deferred rules" section above.
    deferred_reason: str | None = None

    def applies_to_preset(self, tier: str) -> bool:
        """Return True if this rule is active for rigor *tier*.

        Default implementation consults the central :data:`RULE_PRESET_MAP`
        via the rule's own ``rule_id``. Rules should not normally override
        this — keep the tier mapping in one place.
        """
        return self.rule_id in active_rule_ids_for_tier(tier)

    def severity_for_tier(self, tier: str) -> Severity:
        """Return the severity this rule emits at rigor *tier*.

        Default is :attr:`Severity.BLOCKER` whenever the rule is active —
        which, per the module's enforcement-point section, means the finding
        blocks baseline creation (waivable per finding), not that a write is
        rejected. Override only for rules whose severity genuinely varies per
        tier, or that are advisory at every tier they run in: ``TRACE-P2`` is
        a WARNING in *all* tiers by decision (#581), not a tier-dependent one.
        """
        return Severity.BLOCKER

    @abstractmethod
    def check(self, context: AuditContext) -> List[Finding]:
        """Run the check and return findings (empty list = conformant)."""
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Registry + self-registration
# ---------------------------------------------------------------------------

_REGISTRY: Dict[str, Rule] = {}


def register_rule(cls: type[Rule]) -> type[Rule]:
    """Class decorator: instantiate *cls* and add it to the registry.

    Rejects a missing ``rule_id``, an id unknown to :data:`ALL_RULE_IDS`
    (guards against typos) and duplicate registrations.
    """
    instance = cls()
    rule_id = instance.rule_id
    if not rule_id:
        raise ValueError(f"{cls.__name__} must define a non-empty rule_id")
    if rule_id not in ALL_RULE_IDS:
        raise ValueError(
            f"{cls.__name__} has unknown rule_id {rule_id!r}; "
            f"add it to RULE_PRESET_MAP first. Known ids: {sorted(ALL_RULE_IDS)}"
        )
    if rule_id in _REGISTRY:
        raise ValueError(f"Rule {rule_id!r} is already registered")
    _REGISTRY[rule_id] = instance
    return cls


def get_registered_rules() -> list[Rule]:
    """Return all registered rule instances (registration order preserved)."""
    return list(_REGISTRY.values())


def clear_registry() -> None:  # pragma: no cover — test/tooling helper
    """Empty the registry (used by tests that register throwaway rules)."""
    _REGISTRY.clear()


__all__ = [
    "Rule",
    "register_rule",
    "get_registered_rules",
    "clear_registry",
    "active_rule_ids_for_tier",
    "full_se_rule_ids",
    "RULE_PRESET_MAP",
    "ALL_RULE_IDS",
    "FULL_SE_RULE_IDS",
    "TRACE_P1",
    "TRACE_P1B",
    "TRACE_P2",
    "TRACE_P3",
    "TRACE_P4",
    "TRACE_P5",
    "TRACE_P6",
    "TRACE_P7",
    "ARCH_003",
    "VERIF_P8",
    "CONS_P9",
    "CONS_P10",
    "VAL_P1",
]
