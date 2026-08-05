"""
COMP-WE-002 (extension) — Data preconditions for workflow transitions.

Two *content* preconditions that complement the four structural rules already
implemented in :mod:`workflow.transition_validator` (transition exists, role
allowed, change_reason present, signature gate). Both are composed into
``TransitionValidator.validate`` and both are strictly tier-aware, reusing the
tier primitives that already exist — they introduce no new tier model:

Rule 5 — Mandatory-field completeness (SE-conformance lever 1)
    ``presets.registry`` declares ``mandatory_fields`` per rigor tier but had
    zero consumers. This rule consumes it at the one point SE practice cares
    about: the moment an artifact is declared baseline-ready, i.e. a transition
    whose *target* state is the workflow's approval state. Every other
    transition (draft-internal edits, deprecation, rework) is untouched.

Rule 6 — Verification evidence (SE-conformance lever 3)
    ``docs/se/V_AND_V_STRATEGY.md`` §3 defines "Passed" as *Covered AND the
    most recent Test Run for all linked Test Cases is successful*. The
    ``implemented -> verified`` transition previously checked role and
    change_reason only, so "verified" was a pure human claim. This rule derives
    the judgement from data, reusing
    ``traceability.coverage_calculator.CoverageCalculator._latest_testrun_status``
    (the single existing implementation of "latest run status per TestCase").

Tier awareness (verified against ``presets/registry.py`` and
``workflow/definition_store.PRESET_SCHEMAS``, not assumed):

    minimal   mandatory_fields = ("title",)  and the minimal workflow schema is
              ``draft -> done`` — it has no approval state at all, so rule 5 is
              structurally unreachable. Rule 6 likewise: "verified" does not
              exist in the minimal schema.
    standard  mandatory_fields = title, description, acceptance_criteria,
              priority; schema is ``draft -> approved -> deprecated``, so
              rule 5 gates ``draft -> approved``. "verified" does not exist,
              so rule 6 is unreachable.
    extended  mandatory_fields adds classification, traceability_target,
              change_reason; schema is
              ``draft -> in_review -> approved -> implemented -> verified``,
              so rule 5 gates ``in_review -> approved`` and rule 6 gates
              ``implemented -> verified``.

Fail-open policy
----------------
Both rules are *additional* gates on shared infrastructure used by 12+ entity
types. Whenever a precondition cannot be evaluated with certainty (unknown
entity type, unresolvable row, preset lookup failure, unexpected DB error) the
rule returns "no violation" and logs. Blocking a legitimate transition because
of an internal lookup glitch is a worse failure mode than letting one through;
the SE-Auditor (lever 2, at baseline build) is the backstop.
"""
from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Error codes
# ---------------------------------------------------------------------------

EC_MANDATORY_FIELDS_MISSING = "MANDATORY_FIELDS_MISSING"
EC_VERIFICATION_EVIDENCE_MISSING = "VERIFICATION_EVIDENCE_MISSING"

# ---------------------------------------------------------------------------
# State recognition
# ---------------------------------------------------------------------------

#: Target states that mean "this artifact is now considered baseline-ready".
#: Compared case-insensitively because the per-entity schemas in
#: ``definition_store.PRESET_SCHEMAS`` use both spellings ("approved" for
#: Requirement/StakeholderNeed/ArchitectureElement/Icd/Diagram/GlossaryTerm,
#: "Approved" for Adr/TestCase).
_APPROVAL_TARGET_STATES = frozenset({"approved"})

#: Target state that means "verification is claimed" (V&V strategy §3).
_VERIFICATION_TARGET_STATES = frozenset({"verified"})

#: Display label of a successful ``TestRunResult`` — ``_latest_testrun_status``
#: returns display labels, and ``TestRunResult.status`` maps
#: ``"passed" -> "Passed"`` (persistence/models.py).
_PASSED_LABEL = "Passed"


def is_approval_transition(target_state: str) -> bool:
    """Return True if *target_state* is the workflow's approval/baseline gate.

    Deliberate non-matches (checked against every schema in
    ``definition_store.PRESET_SCHEMAS``):
      * ``minimal``: ``done`` — the Minimal tier has no approval concept;
      * ``risk_default`` (``Mitigated``/``Accepted``/``Closed``) and
        ``issue_default`` (``Resolved``/``Closed``) — these are *disposition*
        states for process records, not artefact-readiness declarations;
      * ``goal_default`` / ``main_goal_default`` (``Freigegeben``) — the German
        label is intentionally left out rather than aliased: a Goal is a
        planning statement whose "release" is not a baseline claim, and
        inventing a synonym table here would put a second, divergent
        definition of "approved" next to ``PRESET_SCHEMAS``.
    """
    return (target_state or "").strip().lower() in _APPROVAL_TARGET_STATES


def is_verification_transition(target_state: str) -> bool:
    """Return True if *target_state* claims verification (V&V strategy §3)."""
    return (target_state or "").strip().lower() in _VERIFICATION_TARGET_STATES


# ---------------------------------------------------------------------------
# Entity resolution
# ---------------------------------------------------------------------------

#: ``item_type`` -> (module path, class name). Superset of
#: ``lifecycle_manager._STATUS_MIRROR_MODELS``: that registry only lists types
#: with a denormalized ``status`` mirror column, while field completeness is
#: meaningful for every workflow-enabled type. Types absent here are skipped
#: (fail-open), never blocked.
_ENTITY_MODELS: dict[str, tuple[str, str]] = {
    "Requirement": ("persistence.models", "Requirement"),
    "StakeholderNeed": ("persistence.models", "StakeholderNeed"),
    "TestCase": ("persistence.models", "TestCase"),
    "ArchitectureElement": ("persistence.models", "ArchitectureElement"),
    "Adr": ("application.models", "Adr"),
    "Risk": ("application.models", "Risk"),
    "Issue": ("application.models", "Issue"),
    "ChangeRequest": ("application.models", "ChangeRequest"),
    "Goal": ("application.models", "Goal"),
    "MainGoal": ("application.models", "MainGoal"),
    "GlossaryTerm": ("persistence.models", "GlossaryTerm"),
    "Icd": ("icd.models", "Icd"),
    "Diagram": ("diagram.models", "Diagram"),
}

#: Entity types whose "approved" state is a *decision*, not a declaration that
#: the artefact itself is complete and baseline-ready.
#:
#: ChangeRequest runs the ``ccb_approval`` schema: ``approved`` there means
#: "the Configuration Control Board accepted this proposed change", a
#: governance verdict about the change's *subject*. Applying an
#: artefact-completeness policy to it would conflate two different meanings of
#: the same word and would, for example, block a CCB decision on a
#: Standard-tier workspace because the CR's free-text ``description`` is
#: empty — CCB decision rigor is already governed by ``ccb_approval``'s own
#: role + change_reason gates.
_APPROVAL_GATE_EXEMPT_TYPES = frozenset({"ChangeRequest"})

#: Policy field name (``presets.registry.mandatory_fields``) -> ordered tuple of
#: concrete model attribute candidates. The registry names are *policy* names,
#: not column names: e.g. Requirement stores its classification in ``type``
#: (help_text: "Requirement classification") and StakeholderNeed stores its
#: priority in ``moscow_priority``. The first candidate that exists on the
#: entity's model wins; if none exists the policy field is **not applicable**
#: to that entity type and is skipped — this is what keeps the
#: Requirement-shaped ``mandatory_fields`` list from newly blocking
#: Adr/Risk/Issue/TestCase approvals over fields they do not have.
_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "priority": ("priority", "moscow_priority"),
    "classification": ("classification", "type"),
}

#: Policy fields that are not entity columns at all.
#: ``change_reason`` is supplied per transition (checked against the request);
#: ``traceability_target`` is a *graph* property (does this artifact trace
#: upward?) and is deliberately NOT enforced here — trace completeness is the
#: SE-Auditor's mandate (TRACE-P1..P7, enforced at baseline build), and
#: duplicating it in a scalar field check would produce two divergent
#: definitions of the same policy.
_REQUEST_LEVEL_FIELDS = frozenset({"change_reason"})
_GRAPH_LEVEL_FIELDS = frozenset({"traceability_target"})


def _load_entity(item_type: str, item_id: UUID):
    """Return the ORM row for *item_type*/*item_id*, or ``None``.

    Uses the tenant-scoped default manager, so row-level isolation applies
    (the caller has already set ``TenantContext``).
    """
    mapping = _ENTITY_MODELS.get(item_type)
    if mapping is None:
        return None
    try:
        from importlib import import_module

        model = getattr(import_module(mapping[0]), mapping[1])
        return model.objects.filter(pk=item_id).first()
    except Exception:  # noqa: BLE001 — fail-open, never block on a lookup glitch
        logger.exception(
            "precondition_rules: could not load %s pk=%s", item_type, item_id
        )
        return None


def _is_blank(value: object) -> bool:
    """Return True if *value* counts as "not filled in"."""
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple, dict, set)):
        return len(value) == 0
    return False


def _resolve_attribute(entity: object, policy_field: str) -> Optional[str]:
    """Return the concrete attribute name on *entity* for *policy_field*.

    ``None`` means the policy field is not applicable to this entity type.
    """
    for candidate in _FIELD_ALIASES.get(policy_field, (policy_field,)):
        if hasattr(entity, candidate):
            return candidate
    return None


# ---------------------------------------------------------------------------
# Rule 5 — mandatory-field completeness
# ---------------------------------------------------------------------------


def check_mandatory_fields(
    *,
    workspace_id: str,
    item_type: str,
    item_id: UUID,
    target_state: str,
    change_reason: str = "",
) -> Optional[tuple[str, str]]:
    """Check the tier's ``mandatory_fields`` on an approval transition.

    Args:
        workspace_id: Workspace UUID string (drives the tier lookup).
        item_type: Entity type being transitioned (e.g. ``"Requirement"``).
        item_id: UUID of the entity being transitioned.
        target_state: Requested target state.
        change_reason: The transition's change_reason (satisfies the
            ``change_reason`` policy field on the Extended tier).

    Returns:
        ``None`` when the precondition holds (including every non-approval
        transition and every case that cannot be evaluated), otherwise an
        ``(error_code, error_message)`` tuple naming the missing fields.
    """
    if not is_approval_transition(target_state):
        return None
    if item_type in _APPROVAL_GATE_EXEMPT_TYPES:
        return None

    try:
        from presets.services import get_preset

        rules = get_preset(str(workspace_id))
        tier = rules.preset
        mandatory = tuple(rules.mandatory_fields or ())
    except Exception:  # noqa: BLE001 — fail-open (see module docstring)
        logger.exception(
            "precondition_rules: preset lookup failed for ws=%s", workspace_id
        )
        return None

    if not mandatory:
        return None

    entity = _load_entity(item_type, item_id)
    if entity is None:
        return None

    missing: list[str] = []
    for policy_field in mandatory:
        if policy_field in _GRAPH_LEVEL_FIELDS:
            # Owned by the SE-Auditor, not by field completeness.
            continue
        if policy_field in _REQUEST_LEVEL_FIELDS:
            if _is_blank(change_reason):
                missing.append(policy_field)
            continue
        attribute = _resolve_attribute(entity, policy_field)
        if attribute is None:
            # Not applicable to this entity type.
            continue
        if _is_blank(getattr(entity, attribute, None)):
            missing.append(policy_field)

    if not missing:
        return None

    return (
        EC_MANDATORY_FIELDS_MISSING,
        (
            f"Cannot approve this {item_type}: the '{tier}' preset requires "
            f"the following field(s) to be filled in first: "
            f"{', '.join(sorted(missing))}."
        ),
    )


# ---------------------------------------------------------------------------
# Rule 6 — verification evidence
# ---------------------------------------------------------------------------

#: Entity types for which the V&V "Passed" derivation is defined. The strategy
#: doc scopes it to Requirements; ``SE_LINK_SEMANTICS`` also allows
#: ``verifies: TestCase -> ArchitectureElement``, but no shipped workflow
#: schema gives ArchitectureElement a "verified" state, so extending this set
#: would be dead policy. Kept explicit so adding a type is a deliberate act.
_VERIFICATION_ENFORCED_TYPES = frozenset({"Requirement"})


def check_verification_evidence(
    *,
    item_type: str,
    item_id: UUID,
    target_state: str,
) -> Optional[tuple[str, str]]:
    """Derive the V&V "Passed" judgement for a ``-> verified`` transition.

    A Requirement may only be declared verified when it satisfies
    ``docs/se/V_AND_V_STRATEGY.md`` §3 "Passed":

      1. at least one non-outdated TestCase is linked to it via a ``verifies``
         trace link (TestCase = source, Requirement = target — the convention
         in ``traceability.types.SE_LINK_SEMANTICS``), and
      2. the most recent ``TestRunResult`` of *every* such TestCase is
         ``passed``.

    Returns:
        ``None`` when the precondition holds (including every non-verification
        transition and every entity type outside
        :data:`_VERIFICATION_ENFORCED_TYPES`), otherwise an
        ``(error_code, error_message)`` tuple naming the offending TestCases.
    """
    if not is_verification_transition(target_state):
        return None
    if item_type not in _VERIFICATION_ENFORCED_TYPES:
        return None

    try:
        from persistence.models import Requirement
        from traceability.coverage_calculator import CoverageCalculator
        from traceability.types import LinkType

        requirement = Requirement.objects.filter(pk=item_id).first()
        if requirement is None:
            return None

        from persistence.models import TraceLink

        # TestCase is the SOURCE, Requirement the TARGET of a `verifies` link.
        testcase_artifact_ids: set[str] = {
            str(v)
            for v in TraceLink.objects.filter(
                link_type=LinkType.VERIFIES.value,
                target_id=requirement.artifact_id,
            ).values_list("source_id", flat=True)
        }

        calculator = CoverageCalculator()
        # An outdated TestCase is not valid evidence.
        if testcase_artifact_ids:
            testcase_artifact_ids = calculator._exclude_outdated_testcase_ids(
                testcase_artifact_ids
            )

        if not testcase_artifact_ids:
            return (
                EC_VERIFICATION_EVIDENCE_MISSING,
                (
                    "Cannot mark this Requirement as verified: it has no active "
                    "TestCase linked via a 'verifies' trace link. Link at least "
                    "one TestCase and record a passing test run first."
                ),
            )

        latest = calculator._latest_testrun_status(testcase_artifact_ids)
        not_passed = sorted(
            f"{tc_id} ({latest.get(tc_id, 'Not Run')})"
            for tc_id in testcase_artifact_ids
            if latest.get(tc_id) != _PASSED_LABEL
        )
    except Exception:  # noqa: BLE001 — fail-open (see module docstring)
        logger.exception(
            "precondition_rules: verification evidence check failed for %s",
            item_id,
        )
        return None

    if not_passed:
        return (
            EC_VERIFICATION_EVIDENCE_MISSING,
            (
                "Cannot mark this Requirement as verified: the latest test run "
                "of the following verifying TestCase(s) is not 'Passed': "
                f"{', '.join(not_passed)}."
            ),
        )
    return None


__all__ = [
    "EC_MANDATORY_FIELDS_MISSING",
    "EC_VERIFICATION_EVIDENCE_MISSING",
    "check_mandatory_fields",
    "check_verification_evidence",
    "is_approval_transition",
    "is_verification_transition",
]
