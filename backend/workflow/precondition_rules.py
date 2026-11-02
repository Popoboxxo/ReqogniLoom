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

Rule 7 — Verification coverage of a TestCase (GitHub #584)
    A TestCase could be created, reviewed and approved without ever being
    linked to what it verifies (0 of 30 TestCases carried a ``verifies`` link
    in the reported workspace), which breaks the ISO 15288 6.4.8/6.4.9 chain
    Requirement -> TestCase -> TestRun at its first hop. This rule is the
    mirror image of rule 6: rule 6 stops a *Requirement* claiming verification
    without evidence, rule 7 stops a *TestCase* being approved as verification
    evidence without a subject.

Rule 6 — Verification evidence (SE-conformance lever 3)
    ``docs/se/V_AND_V_STRATEGY.md`` §3 defines "Passed" as *Covered AND the
    most recent Test Run for all linked Test Cases is successful*. The
    ``implemented -> verified`` transition previously checked role and
    change_reason only, so "verified" was a pure human claim. This rule derives
    the judgement from data, reusing
    ``traceability.coverage_calculator.CoverageCalculator._latest_testrun_status``
    (the single existing implementation of "latest run status per TestCase").

Rule 8 — Requirement verification evidence + TestCase steps (#1267/#1269)
    Two additional approval gates, both switched on only by the Extended tier's
    ``require_verification_on_approval`` feature flag
    (``presets.registry``): a Requirement must carry a ``verifies`` link or
    declare a non-test ``verification_method`` before it is approved
    (:func:`check_requirement_verification_evidence`), and a TestCase that is
    not an inspection/analysis/demonstration must have a non-empty step list
    (:func:`check_testcase_steps`).

Rule 9 — document release gates G-1…G-4 (Plan F F2-T4, ADR-026 §4.2)
    A ``Document`` is "released" by entering the state its own workflow marks
    with ``state_meta.freeze_on_enter`` (spec §4) — not by any "approved" label.
    :func:`check_document_gates` runs the four gates from ADR-026 §4.2 there:
    no open WorkItem (G-1), every WorkItem traceable or informational (G-2), no
    open source drift (G-3, inert until F5 introduces a source binding) and the
    kind's mandatory fields filled (G-4, policy key
    ``document_mandatory_fields_by_kind``). Unlike the rules above it is
    fail-closed on *known* violations and reports every violated gate at once;
    an unevaluable gate is still fail-open, like every other rule here.

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
An explicit preset conflict is a known policy violation, not a lookup glitch:
approval is blocked until the workspace definition is reconciled or reset.
"""
from __future__ import annotations

import logging
from collections.abc import Iterable
from uuid import UUID

from attribute_definitions.schema import (
    AttributeDefinitionConflictError,
    AttributeSchemaError,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Error codes
# ---------------------------------------------------------------------------

EC_MANDATORY_FIELDS_MISSING = "MANDATORY_FIELDS_MISSING"
EC_VERIFICATION_EVIDENCE_MISSING = "VERIFICATION_EVIDENCE_MISSING"
EC_VERIFIES_LINK_MISSING = "VERIFIES_LINK_MISSING"
EC_REQUIREMENT_VERIFICATION_MISSING = "REQUIREMENT_VERIFICATION_MISSING"
EC_TEST_STEPS_MISSING = "TEST_STEPS_MISSING"
#: Plan F F2-T4 / ADR-026 §4.2: one or more of the document release gates
#: (G-1…G-4) failed. ``details`` names each violated gate.
EC_DOCUMENT_GATE_FAILED = "DOCUMENT_GATE_FAILED"

# ---------------------------------------------------------------------------
# State recognition
# ---------------------------------------------------------------------------

#: Target states that mean "this artifact is now considered baseline-ready".
#: Compared case-insensitively because the per-entity schemas in
#: ``definition_store.PRESET_SCHEMAS`` use both spellings ("approved" for
#: Requirement/StakeholderNeed/ArchitectureElement/Icd/Diagram/GlossaryTerm/
#: TestCase, "Approved" for Adr). TestCase moved to the lowercase spelling in
#: GH-453; Adr keeps Title Case, so the case-insensitive compare stays load-
#: bearing.
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
    # Plan F F2-T4: rule 9 (document release gates) loads the document row
    # through this registry. Rule 5 never fires for it — a document is released
    # by ``freeze_on_enter``, not by an "approved" target state.
    "Document": ("persistence.models", "Document"),
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


def _resolve_attribute(entity: object, policy_field: str) -> str | None:
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
) -> tuple[str, str] | None:
    """Check the tier's mandatory fields on an approval transition.

    The mandatory set is definition-scoped (#912): the workspace's resolved
    attribute definition (global default plus any workspace override, resolved
    through the same store the payload-validation path uses) and its
    ``required`` flags for ``(item_type, tier)``, with the legacy Requirement
    ``mandatory_fields`` list folded in so that item type's behaviour is
    unchanged (see :mod:`attribute_definitions.mandatory_fields`).

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
        ``(error_code, error_message)`` tuple naming the missing fields or an
        explicit preset conflict that requires reconciling/resetting the definition.
    """
    if not is_approval_transition(target_state):
        return None
    if item_type in _APPROVAL_GATE_EXEMPT_TYPES:
        return None

    try:
        from presets.services import get_preset

        tier = get_preset(str(workspace_id)).preset
    except Exception:  # noqa: BLE001 — fail-open (see module docstring)
        logger.exception(
            "precondition_rules: preset lookup failed for ws=%s", workspace_id
        )
        return None

    entity = _load_entity(item_type, item_id)
    if entity is None:
        return None

    try:
        from attribute_definitions.mandatory_fields import scoped_mandatory_fields

        mandatory = scoped_mandatory_fields(
            getattr(entity, "tenant_id", None),
            str(workspace_id),
            item_type,
            tier,
        )
    except AttributeDefinitionConflictError as exc:
        return (
            "ATTRIBUTE_DEFINITION_CONFLICT",
            f"Cannot approve this {item_type}: the workspace attribute definition "
            f"conflicts with the current '{tier}' preset. {exc}",
        )
    except AttributeSchemaError:
        # A malformed stored definition is a configuration error, not an
        # unexpected failure: log it at ERROR with the traceback so it is
        # visible, then fail open (post-review m6).
        logger.error(
            "precondition_rules: malformed attribute definition for %s/%s "
            "(workspace=%s) — failing open",
            item_type,
            tier,
            workspace_id,
            exc_info=True,
        )
        return None
    except Exception:  # noqa: BLE001 — fail-open (see module docstring)
        logger.exception(
            "precondition_rules: mandatory-field resolution failed for %s/%s",
            item_type,
            tier,
        )
        return None

    if not mandatory:
        return None

    missing: list[str] = []
    seen_attributes: set[str] = set()
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
        # Two policy names can resolve to the same concrete column (e.g. the
        # legacy ``classification`` and a definition ``type`` both name
        # ``Requirement.type``). Report each column once (post-review m7).
        if attribute in seen_attributes:
            continue
        seen_attributes.add(attribute)
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
) -> tuple[str, str] | None:
    """Derive the V&V "Passed" judgement for a ``-> verified`` transition.

    A Requirement may only be declared verified when it satisfies
    ``docs/se/V_AND_V_STRATEGY.md`` §3 "Passed":

      1. at least one non-outdated TestCase is linked to it via a ``verifies``
         trace link (TestCase = source, Requirement = target — the convention
         in ``traceability.types.SE_LINK_SEMANTICS``), and
      2. the most recent ``TestRunResult`` of *every* such TestCase is
         ``passed``.

    #424: "non-outdated" is now "counts as verification evidence" — an
    ``origin="ai_generated"``, unreviewed TestCase is not evidence either
    (the shared predicate lives in
    ``traceability.coverage_calculator.counts_as_verification_evidence``).

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
        # An outdated TestCase is not valid evidence — and neither is an
        # unreviewed AI-generated one (#424, the false-green path). Both
        # exclusions live in the shared predicate; this call names the wrapper
        # explicitly so the intent is visible at the call site.
        if testcase_artifact_ids:
            testcase_artifact_ids = calculator._exclude_outdated_testcase_ids(
                testcase_artifact_ids, include_unreviewed_ai=False
            )

        if not testcase_artifact_ids:
            return (
                EC_VERIFICATION_EVIDENCE_MISSING,
                (
                    "Cannot mark this Requirement as verified: it has no active "
                    "TestCase linked via a 'verifies' trace link, or its only "
                    "linked test case is an unreviewed AI-generated test case. "
                    "Link at least one TestCase, review it, and record a "
                    "passing test run first."
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


# ---------------------------------------------------------------------------
# Rule 7 — a TestCase must verify something before it can be approved (#584)
# ---------------------------------------------------------------------------

#: Policy field whose presence in the tier's ``mandatory_fields`` switches
#: rule 7 on. Only the Extended tier declares ``traceability_target``
#: (``presets/registry.py``), so this is the tier lever without inventing a
#: second tier model — exactly how rule 5 derives its tier awareness.
#:
#: Rule 5 *skips* this policy field on purpose (see ``_GRAPH_LEVEL_FIELDS``):
#: it is a graph property, not a scalar column, and for Requirements trace
#: completeness is the SE-Auditor's mandate (TRACE-P1..P7 at baseline build).
#: Rule 7 does not duplicate that — it applies the identical definition
#: TRACE-P6 uses (>=1 ``verifies`` link to a live Requirement or
#: ArchitectureElement) at the earlier, cheaper moment, so the author learns
#: about it while approving the TestCase instead of when the release baseline
#: is blocked. TRACE-P6 remains the backstop for everything that never
#: transitions.
_GRAPH_POLICY_FIELD = "traceability_target"

#: Entity types rule 7 applies to. ``verifies`` is a TestCase-sourced link in
#: ``traceability.types.SE_LINK_SEMANTICS``, so no other type can satisfy it.
_VERIFIES_LINK_ENFORCED_TYPES = frozenset({"TestCase"})

def check_verifies_link(
    *,
    workspace_id: str,
    item_type: str,
    item_id: UUID,
    target_state: str,
) -> tuple[str, str] | None:
    """Require a ``verifies`` link before a TestCase may be approved (#584).

    The link must point at a Requirement or ArchitectureElement that is alive
    (not soft-deleted) and lives in the same workspace — the same target pool
    ``traceability.audit.rules.coverage_consistency`` (TRACE-P6) evaluates.

    Args:
        workspace_id: Workspace UUID string (drives the tier lookup).
        item_type: Entity type being transitioned.
        item_id: UUID of the entity being transitioned.
        target_state: Requested target state.

    Returns:
        ``None`` when the precondition holds — including every non-approval
        transition, every entity type outside
        :data:`_VERIFIES_LINK_ENFORCED_TYPES`, every tier that does not declare
        :data:`_GRAPH_POLICY_FIELD`, and every case that cannot be evaluated
        (fail-open, see module docstring). Otherwise an
        ``(error_code, error_message)`` tuple.
    """
    if not is_approval_transition(target_state):
        return None
    if item_type not in _VERIFIES_LINK_ENFORCED_TYPES:
        return None

    try:
        from presets.services import get_preset

        rules = get_preset(str(workspace_id))
        tier = rules.preset
        # Rule 7 uses ``mandatory_fields`` purely as an Extended-tier lever
        # (``traceability_target``), not as a field-completeness policy — that
        # is rule 5's job and now reads the definition-scoped source (#912).
        # *tier* drives the user-facing message below.
        mandatory = tuple(rules.mandatory_fields or ())
    except Exception:  # noqa: BLE001 — fail-open (see module docstring)
        logger.exception(
            "precondition_rules: preset lookup failed for ws=%s", workspace_id
        )
        return None

    if _GRAPH_POLICY_FIELD not in mandatory:
        return None

    try:
        from persistence.models import (
            ArchitectureElement,
            Requirement,
            TestCase,
            TraceLink,
        )
        from traceability.types import LinkType
        from workflow.services import outdated_item_ids

        test_case = TestCase.objects.filter(pk=item_id).first()
        if test_case is None:
            return None

        target_ids = set(
            TraceLink.objects.filter(
                link_type=LinkType.VERIFIES.value,
                source_id=test_case.artifact_id,
            ).values_list("target_id", flat=True)
        )

        live_target_exists = False
        if target_ids:
            # Datenmodell-Konsolidierung Phase 1: Requirement "outdated" is
            # resolved through WorkflowItemState (batched). Task 12: the
            # ``status`` column is dropped, so a row never wired into one
            # falls back to the "draft" preset initial state instead
            # (documented, reviewed data-loss tradeoff, see Task 12 report
            # Finding 2).
            from workflow import state_reader

            req_rows = list(
                Requirement.objects.filter(
                    artifact_id__in=target_ids,
                    artifact__workspace_id=workspace_id,
                ).values("id")
            )
            req_states = state_reader.current_states(
                "Requirement", (row["id"] for row in req_rows)
            )
            requirement_initial_state = state_reader.initial_state("Requirement")
            live_target_exists = any(
                (req_states.get(str(row["id"])) or requirement_initial_state) != "outdated"
                for row in req_rows
            ) or (
                # ArchitectureElement has no status mirror — its soft-delete
                # state lives only in WorkflowItemState (see outdated_item_ids).
                ArchitectureElement.objects.filter(
                    artifact_id__in=target_ids,
                    artifact__workspace_id=workspace_id,
                )
                .exclude(id__in=outdated_item_ids("ArchitectureElement"))
                .exists()
            )
    except Exception:  # noqa: BLE001 — fail-open (see module docstring)
        logger.exception(
            "precondition_rules: verifies-link check failed for %s", item_id
        )
        return None

    if live_target_exists:
        return None

    return (
        EC_VERIFIES_LINK_MISSING,
        (
            f"Cannot approve this TestCase: the '{tier}' preset requires every "
            "TestCase to declare what it verifies. Link it to a Requirement or "
            "an Architecture Element with a 'verifies' trace link first."
        ),
    )


# ---------------------------------------------------------------------------
# Rule 8 — a Requirement must declare verification evidence before approval
# ---------------------------------------------------------------------------

#: Feature flag (``presets.registry``) that switches the two #1267/#1269
#: approval preconditions on. Extended is the only default tier that enables
#: it; Minimal/Standard keep their lightweight approval semantics.
_FEATURE_REQUIRE_VERIFICATION = "require_verification_on_approval"

#: ``Requirement.verification_method`` values that are *not* a test execution
#: and therefore count on their own as verification evidence at approval time
#: (#1267). ``Test`` and ``Review`` require a ``verifies`` link instead.
#: Compared case-insensitively against the canonical ``VerificationMethod``
#: values ("Analysis"/"Inspection"/"Demonstration").
_NON_TEST_VERIFICATION_METHODS = frozenset(
    {"analysis", "inspection", "demonstration"}
)

#: Entity types the requirement-verification gate applies to. Only a
#: Requirement carries ``verification_method``; the TestCase half of the
#: verification chain stays rule 7 (``check_verifies_link``).
_REQUIREMENT_VERIFICATION_ENFORCED_TYPES = frozenset({"Requirement"})

#: ``TestCase.test_type`` values for which a step list is not meaningful — an
#: inspection, analysis or demonstration is an activity, not a reproducible
#: procedure with steps (#1269). Canonical lowercase ``TestCaseType`` values.
_STEPLESS_TEST_TYPES = frozenset({"inspection", "analysis", "demonstration"})

#: Entity types the TestCase-steps gate applies to.
_TEST_STEPS_ENFORCED_TYPES = frozenset({"TestCase"})


def _require_verification_flag(workspace_id: str) -> bool | None:
    """Return the ``require_verification_on_approval`` feature flag value.

    ``None`` means the flag could not be resolved; callers treat that as
    "gate off" (fail-open, see the module docstring).
    """
    try:
        from presets.services import get_preset

        return bool(
            get_preset(str(workspace_id)).features.get(
                _FEATURE_REQUIRE_VERIFICATION, False
            )
        )
    except Exception:  # noqa: BLE001 — fail-open (see module docstring)
        logger.exception(
            "precondition_rules: preset lookup failed for ws=%s", workspace_id
        )
        return None


def check_requirement_verification_evidence(
    *,
    workspace_id: str,
    item_type: str,
    item_id: UUID,
    target_state: str,
) -> tuple[str, str] | None:
    """Require verification evidence before a Requirement may be approved (#1267).

    Active only when the workspace's preset sets the
    ``require_verification_on_approval`` feature flag (Extended). Evidence is
    either

      * a ``verifies`` trace link pointing *at* the Requirement (TestCase =
        source, Requirement = target — the convention in
        ``traceability.types.SE_LINK_SEMANTICS``), or
      * a declared ``verification_method`` that is a non-test method
        (``Analysis``/``Inspection``/``Demonstration``) — a method that does
        not rely on a separate executed TestCase.

    A Requirement whose method is ``Test``/``Review`` (or unset) has to carry a
    ``verifies`` link; the stricter "the linked TestCase actually passed"
    judgement stays rule 6 (:func:`check_verification_evidence`) on the
    ``-> verified`` transition.

    Returns:
        ``None`` when the precondition holds — including every non-approval
        transition, every entity type other than ``Requirement``, every tier
        without the flag, the non-test method values above, and every case that
        cannot be evaluated (fail-open). Otherwise an
        ``(error_code, error_message)`` tuple.
    """
    if not is_approval_transition(target_state):
        return None
    if item_type not in _REQUIREMENT_VERIFICATION_ENFORCED_TYPES:
        return None
    if not _require_verification_flag(workspace_id):
        return None

    try:
        from persistence.models import Requirement, TraceLink
        from traceability.types import LinkType

        requirement = Requirement.objects.filter(pk=item_id).first()
        if requirement is None:
            return None

        method = (
            (getattr(requirement, "verification_method", "") or "").strip().lower()
        )
        if method in _NON_TEST_VERIFICATION_METHODS:
            return None

        has_link = TraceLink.objects.filter(
            link_type=LinkType.VERIFIES.value,
            target_id=requirement.artifact_id,
        ).exists()
        if has_link:
            return None
    except Exception:  # noqa: BLE001 — fail-open (see module docstring)
        logger.exception(
            "precondition_rules: requirement verification check failed for %s",
            item_id,
        )
        return None

    return (
        EC_REQUIREMENT_VERIFICATION_MISSING,
        (
            "Cannot approve this Requirement: the workspace requires "
            "verification evidence. Either link a TestCase with a 'verifies' "
            "trace link, or set verification_method to one of "
            "'Analysis', 'Inspection' or 'Demonstration'."
        ),
    )


def check_testcase_steps(
    *,
    workspace_id: str,
    item_type: str,
    item_id: UUID,
    target_state: str,
) -> tuple[str, str] | None:
    """Require a non-empty step list before a TestCase may be approved (#1269).

    Active only when the workspace's preset sets the
    ``require_verification_on_approval`` feature flag (Extended). A TestCase
    whose ``test_type`` is ``inspection``/``analysis``/``demonstration`` is
    exempt: those are activities whose outcome is described, not a reproducible
    procedure with numbered steps.

    Returns:
        ``None`` when the precondition holds — including every non-approval
        transition, every entity type other than ``TestCase``, every tier
        without the flag, the step-less test types, and every case that cannot
        be evaluated (fail-open). Otherwise an ``(error_code, error_message)``
        tuple.
    """
    if not is_approval_transition(target_state):
        return None
    if item_type not in _TEST_STEPS_ENFORCED_TYPES:
        return None
    if not _require_verification_flag(workspace_id):
        return None

    test_type = ""
    try:
        from persistence.models import TestCase

        test_case = TestCase.objects.filter(pk=item_id).first()
        if test_case is None:
            return None

        test_type = (
            (getattr(test_case, "test_type", "") or "").strip().lower()
        )
        if test_type in _STEPLESS_TEST_TYPES:
            return None
        if not _is_blank(getattr(test_case, "steps", None)):
            return None
    except Exception:  # noqa: BLE001 — fail-open (see module docstring)
        logger.exception(
            "precondition_rules: testcase-steps check failed for %s", item_id
        )
        return None

    return (
        EC_TEST_STEPS_MISSING,
        (
            "Cannot approve this TestCase: it has no test steps. Record at "
            "least one step, or set test_type to 'Inspection', 'Analysis' or "
            "'Demonstration' if the test is not a step-based procedure."
        ),
    )


# ---------------------------------------------------------------------------
# Rule 9 — document release gates G-1…G-4 (Plan F F2-T4, ADR-026 §4.2)
# ---------------------------------------------------------------------------

#: The only entity type rule 9 applies to. A ``Document`` is released by
#: entering the state its workflow marks with ``freeze_on_enter`` (spec §4) —
#: not by entering a state named "approved", which is why this rule does not
#: reuse :func:`is_approval_transition`.
_DOCUMENT_ITEM_TYPE = "Document"

#: ``state_meta`` flag that marks the release state (spec §4, F-1). Resolved
#: from the workspace's *own* workflow document, so a customised Document
#: lifecycle (ADR-06) with a differently named release state is still gated.
_FREEZE_STATE_META_KEY = "freeze_on_enter"

#: WorkItem workflow states G-1 treats as "still open". Lower-case comparison
#: because F3's preset schemas use the lower-case spelling (``in_progress``,
#: ``blocked``) while the entity types' states use German/Title-Case labels.
_DOCUMENT_OPEN_ITEM_STATES = frozenset({"in_progress", "blocked"})


def is_freeze_transition(
    workspace_id: str, item_type: str, target_state: str
) -> bool:
    """Return True when *target_state* is *item_type*'s document release state.

    A document is released by entering the state its workflow definition marks
    with ``state_meta.freeze_on_enter`` (Plan F spec §4). Deliberately **not**
    name-based and **not** :func:`is_approval_transition`: ``goal_default`` and
    ``main_goal_default`` also call their approval state ``"Freigegeben"``, and
    aliasing the two would let the Goal release path trip the document gates.

    Fails open (``False``) when the definition cannot be read — the transition
    itself cannot happen without a definition (rule 1 answers
    ``DEFINITION_NOT_FOUND`` first), so there is nothing to gate.
    """
    if item_type != _DOCUMENT_ITEM_TYPE:
        return False
    try:
        from workflow.definition_store import get_state_meta
        from workflow.services import get_workflow_json

        workflow_json = get_workflow_json(workspace_id, item_type)
    except Exception:  # noqa: BLE001 — fail-open, see module docstring
        logger.exception(
            "precondition_rules: document workflow lookup failed for ws=%s",
            workspace_id,
        )
        return False
    if not workflow_json:
        return False
    return bool(
        get_state_meta(workflow_json, target_state).get(_FREEZE_STATE_META_KEY)
    )


def _document_work_items(document_id: UUID) -> list:
    """Return the document's ``WorkItem`` rows, or ``[]`` before F3 ships.

    G-1/G-2 evaluate WorkItems, which Plan F introduces in its own work package
    (F3). Until the model exists the gates are satisfied by construction — the
    spec's "bis F3: keine Items ⇒ erfüllt". Reading the model lazily (rather
    than hard-coding "no items") is what makes the gates switch on by
    themselves once F3 lands, instead of silently staying off.

    A missing model is the expected pre-F3 state (``ImportError``); any other
    failure is logged and treated as "no items", consistent with this module's
    fail-open policy.
    """
    try:
        from persistence.models import WorkItem
    except ImportError:
        return []
    try:
        return list(WorkItem.objects.filter(document_id=document_id))
    except Exception:  # noqa: BLE001 — fail-open, see module docstring
        logger.exception(
            "precondition_rules: document work-item lookup failed for %s",
            document_id,
        )
        return []


def _document_item_gate_violations(document_id: UUID) -> list[dict]:
    """Evaluate G-1 and G-2 over the document's WorkItems.

    Returns one ``{"gate", "message"}`` entry per violated gate (empty when the
    document has no items, the pre-F3 case).

    G-1: no item is ``in_progress``/``blocked``.
    G-2: every item carries at least one trace link or is flagged
         ``informational``. The flag is read via ``getattr`` because F3 owns the
         field; an item that has neither is a violation (fail-closed).
    """
    items = _document_work_items(document_id)
    if not items:
        return []

    from workflow import state_reader

    states = state_reader.current_states("WorkItem", [item.pk for item in items])
    violations: list[dict] = []

    open_items = sorted(
        str(item.pk)
        for item in items
        if (states.get(str(item.pk)) or "").strip().lower()
        in _DOCUMENT_OPEN_ITEM_STATES
    )
    if open_items:
        violations.append(
            {
                "gate": "G-1",
                "message": (
                    "The document still has WorkItems in progress or blocked: "
                    + ", ".join(open_items)
                ),
            }
        )

    unlinked = [
        item
        for item in items
        if not getattr(item, "informational", False)
        and getattr(item, "artifact_id", None) is not None
    ]
    if unlinked:
        from persistence.models import TraceLink

        artifact_ids = [item.artifact_id for item in unlinked]
        linked = set(
            TraceLink.objects.filter(source_id__in=artifact_ids).values_list(
                "source_id", flat=True
            )
        ) | set(
            TraceLink.objects.filter(target_id__in=artifact_ids).values_list(
                "target_id", flat=True
            )
        )
        dangling = sorted(
            str(item.pk) for item in unlinked if item.artifact_id not in linked
        )
        if dangling:
            violations.append(
                {
                    "gate": "G-2",
                    "message": (
                        "These WorkItems carry no trace link and are not marked "
                        "informational: " + ", ".join(dangling)
                    ),
                }
            )
    return violations


def _document_missing_required_fields(
    entity: object, policy: dict[str, tuple[str, ...]]
) -> list[str]:
    """Return the G-4 mandatory fields of *entity*'s kind that are not filled.

    The per-kind policy comes from the workspace preset
    (``document_mandatory_fields_by_kind``, Plan F F2-T4). ``"*"`` is the
    fallback for every kind without its own entry; when neither is configured
    the identity field is still demanded, so a missing policy can never turn
    G-4 into a no-op (fail-closed).
    """
    kind = str(getattr(entity, "kind", "") or "")
    required = policy.get(kind) or policy.get("*") or ("title",)
    return sorted(
        field for field in required if _is_blank(getattr(entity, field, None))
    )


def check_document_gates(
    *,
    workspace_id: str,
    item_type: str,
    item_id: UUID,
    target_state: str,
) -> tuple[str, str, list[dict]] | None:
    """Evaluate the document release gates G-1…G-4 (Plan F F2-T4).

    Runs only on the document *release* transition — the state the workspace's
    Document workflow marks with ``state_meta.freeze_on_enter`` (see
    :func:`is_freeze_transition`). Every other transition, every other entity
    type and every workspace without a Document workflow is untouched.

    Gates (ADR-026 §4.2):

    * **G-1** no ``WorkItem`` in ``in_progress``/``blocked``;
    * **G-2** every ``WorkItem`` has ≥ 1 trace link or is ``informational``;
    * **G-3** no open drift against a source — vacuously satisfied until F5
      gives a document a source binding at all (``owner_mode = loom``);
    * **G-4** the kind's mandatory fields are filled
      (``presets.registry.document_mandatory_fields_by_kind``).

    All violated gates are reported together, not fail-fast: a caller fixing a
    document should see the whole list in one answer.

    Returns:
        ``None`` when every gate holds (including every non-release
        transition, every non-document type and every case that cannot be
        evaluated — fail-open, see the module docstring). Otherwise
        ``(EC_DOCUMENT_GATE_FAILED, message, details)`` where ``details`` is a
        list of ``{"gate": "G-1"…"G-4", "message": str}`` entries, plus
        ``"missing_fields"`` on a G-4 entry.
    """
    if not is_freeze_transition(workspace_id, item_type, target_state):
        return None

    entity = _load_entity(item_type, item_id)
    if entity is None:
        # The row is unreadable: the transition's own state read is the
        # authority on existence, so do not invent a gate failure here.
        return None

    try:
        from presets.services import get_preset

        policy = get_preset(str(workspace_id)).document_mandatory_fields_by_kind
    except Exception:  # noqa: BLE001 — fail-open, see module docstring
        logger.exception(
            "precondition_rules: document gate policy lookup failed for ws=%s",
            workspace_id,
        )
        return None

    details = _document_item_gate_violations(entity.pk)

    missing = _document_missing_required_fields(entity, policy)
    if missing:
        details.append(
            {
                "gate": "G-4",
                "message": (
                    "The document's kind requires these field(s) to be filled "
                    "in before release: " + ", ".join(missing)
                ),
                "missing_fields": missing,
            }
        )

    if not details:
        return None

    gates = ", ".join(entry["gate"] for entry in details)
    return (
        EC_DOCUMENT_GATE_FAILED,
        f"Cannot release this document: {gates} not satisfied.",
        details,
    )


def policy_fields_without_consumer(
    policy_fields: Iterable[str],
    *,
    item_type: str,
    attribute_names: Iterable[str],
    model_field_names: Iterable[str],
) -> list[str]:
    """Return the preset ``mandatory_fields`` entries that mean nothing here.

    GitHub #912 follow-up: ``bootstrap_attribute_definitions`` warns about
    preset ``mandatory_fields`` names it could not match to an *attribute*. For
    Requirement that check was a permanent false positive — ``classification``
    resolves to the ``type`` column (``_FIELD_ALIASES``), ``change_reason`` is
    satisfied by the transition request (``_REQUEST_LEVEL_FIELDS``) and
    ``traceability_target`` is the Extended-tier lever for rule 7
    (``_GRAPH_LEVEL_FIELDS``) — yet the migrate log claimed all three were
    "ignored". The warning has to be scoped to what is actually *in force*, and
    this module is where that knowledge exists, so it is exposed here instead of
    being re-derived (badly) next to the introspector.

    A policy name is consumed when any of the following holds:

      * it names one of the item type's attributes (a definition-scoped
        ``required`` flag, see :mod:`attribute_definitions.mandatory_fields`);
      * it aliases a column on the entity's model (``_FIELD_ALIASES``);
      * it is a request-/graph-level field this module evaluates
        (``change_reason`` / ``traceability_target``).

    Everything else is dead configuration: rule 5 can never observe it, so the
    requirement it was meant to express is not enforced anywhere.

    Ordering is irrelevant to the caller (a set difference is what it wants),
    so the result is sorted and de-duplicated.

    Args:
        policy_fields: The raw ``mandatory_fields`` list (policy names).
        item_type: Entity type the policy would apply to. Types rule 5 skips
            entirely (unknown to :data:`_ENTITY_MODELS`, or exempt in
            :data:`_APPROVAL_GATE_EXEMPT_TYPES`) consume *nothing*; the caller
            decides whether the policy is meant to apply there at all.
        attribute_names: Attribute names present in the item type's stored
            definition.
        model_field_names: Field names on the entity's model.

    Returns:
        Sorted list of policy names with no consumer for *item_type*.
    """
    if item_type in _APPROVAL_GATE_EXEMPT_TYPES or item_type not in _ENTITY_MODELS:
        return sorted(set(policy_fields))

    attributes = set(attribute_names)
    columns = set(model_field_names)
    dead: list[str] = []
    for policy_field in policy_fields:
        if policy_field in _REQUEST_LEVEL_FIELDS or policy_field in _GRAPH_LEVEL_FIELDS:
            continue
        if policy_field in attributes:
            continue
        candidates = _FIELD_ALIASES.get(policy_field, (policy_field,))
        if any(candidate in columns for candidate in candidates):
            continue
        dead.append(policy_field)
    return sorted(set(dead))


__all__ = [
    "EC_DOCUMENT_GATE_FAILED",
    "EC_MANDATORY_FIELDS_MISSING",
    "EC_REQUIREMENT_VERIFICATION_MISSING",
    "EC_TEST_STEPS_MISSING",
    "EC_VERIFICATION_EVIDENCE_MISSING",
    "EC_VERIFIES_LINK_MISSING",
    "check_document_gates",
    "check_mandatory_fields",
    "check_requirement_verification_evidence",
    "check_testcase_steps",
    "check_verification_evidence",
    "check_verifies_link",
    "is_approval_transition",
    "is_freeze_transition",
    "is_verification_transition",
    "policy_fields_without_consumer",
]
