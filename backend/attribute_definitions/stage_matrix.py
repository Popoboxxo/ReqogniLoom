"""Declarative 3-stage attribute matrix (Epic #934 WS6, #939).

Single source of truth for the *staged* part of a bootstrapped attribute
definition, transcribed from ``docs/se/attribut/attribut-matrix-3-stufen.md``.
The bootstrap command (:mod:`attribute_definitions.management.commands.
bootstrap_attribute_definitions`) already derives every model-backed *core*
attribute from Django introspection. This module adds the two things the model
walk cannot know:

1. **New attributes** that have no dedicated model column yet and therefore
   live in ``Artifact.custom_fields`` (``kind="extended"``) — the ``**Neu**``
   rows of the matrix.
2. **Per-stage metadata** for the attributes that already exist: at which rigor
   stage an attribute becomes visible, whether it is required at that stage for
   approval/baseline readiness, and which ISO/SE section it belongs to.

Stages map 1:1 onto the rigor presets (spec section 13)::

    minimal  -> stage 1 (Basissatz)
    standard -> stage 2 (gehobene Stringenz)
    extended -> stage 3 (Full-SE)

``required`` vs ``stage_mandatory``
-----------------------------------
The attribute property ``required`` is, and stays, the **create-payload**
contract enforced by ``field_validation.validate_values`` ("the client must
send this; the server cannot fill it in"). The matrix's ``P`` (Pflicht) is a
different thing: "this must be filled in before the artifact may be approved /
declared baseline-ready". Enforcing that as a create gate was explicitly
rejected once already (see the bootstrap command's ``introspect_core_attributes``
docstring and migration ``0005_relax_requirement_create_required``): it 400s
every existing client, every quick-create dialog and every E2E flow.

The matrix's ``P`` is therefore carried by the additive ``stage_mandatory``
property. It is **seeded and discoverable but deliberately not yet consumed**
by ``attribute_definitions.mandatory_fields``: turning it into an approval gate
requires the WS7/AWMS value migration (#940) to first backfill the new fields on
existing artifacts, otherwise every already-approved artifact becomes
un-reapprovable overnight — the same grandfathering rule ``required`` obeys.
This deviation is documented in the WS6 report and covered by
``tests/test_stage_matrix.py``.

Carrier rule (spec section 2 / ADR-004)
---------------------------------------
Only attributes whose carrier is ``core``/``ext``/``system`` are seeded here.
``link`` rows (``allocated-to``, ``derives-from``, ``verifies``, ``affects`` …)
are ``TraceLink`` edges and are *not* definition attributes (spec section 14);
``entity`` rows (``Measure``, #393) have no table yet. Both are intentionally
absent and listed in the report as open points.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

from attribute_definitions.schema import normalize_attribute

#: Preset tier -> stage number (spec section 13 / matrix header).
PRESET_STAGE: Mapping[str, int] = {
    "minimal": 1,
    "standard": 2,
    "extended": 3,
}

#: Section names reused across item types (matrix "Gruppe" column). Existing
#: core attributes keep their introspected section; only new attributes use
#: these richer ISO-oriented groups.
SEC_IDENTIFICATION = "identification"
SEC_CONTENT = "content"
SEC_CLASSIFICATION = "classification"
SEC_ATTRIBUTION = "attribution"
SEC_VERIFICATION = "verification"
SEC_TRACEABILITY = "traceability"
SEC_CHANGE = "change_control"
SEC_TYPE_SPECIFIC = "type_specific"


def _opt(value: str, de: str, en: str) -> dict[str, str]:
    """One enum option in the schema's normalized shape."""
    return {"value": value, "label_de": de, "label_en": en}


# -- Shared option sets ------------------------------------------------------

PRIORITY_OPTIONS: tuple[dict[str, str], ...] = (
    _opt("low", "Niedrig", "Low"),
    _opt("medium", "Mittel", "Medium"),
    _opt("high", "Hoch", "High"),
    _opt("critical", "Kritisch", "Critical"),
)

CRITICALITY_OPTIONS: tuple[dict[str, str], ...] = PRIORITY_OPTIONS

DIFFICULTY_OPTIONS: tuple[dict[str, str], ...] = (
    _opt("low", "Niedrig", "Low"),
    _opt("medium", "Mittel", "Medium"),
    _opt("high", "Hoch", "High"),
)

VERIFICATION_STATUS_OPTIONS: tuple[dict[str, str], ...] = (
    _opt("not_verified", "Nicht verifiziert", "Not verified"),
    _opt("in_progress", "In Arbeit", "In progress"),
    _opt("verified", "Verifiziert", "Verified"),
    _opt("failed", "Fehlgeschlagen", "Failed"),
)

VERIFICATION_METHOD_OPTIONS: tuple[dict[str, str], ...] = (
    _opt("inspection", "Inspektion", "Inspection"),
    _opt("analysis", "Analyse", "Analysis"),
    _opt("demonstration", "Demonstration", "Demonstration"),
    _opt("test", "Test", "Test"),
)

TEST_LEVEL_OPTIONS: tuple[dict[str, str], ...] = (
    _opt("unit", "Unit", "Unit"),
    _opt("integration", "Integration", "Integration"),
    _opt("system", "System", "System"),
    _opt("acceptance", "Abnahme", "Acceptance"),
)

REVIEW_STATUS_OPTIONS: tuple[dict[str, str], ...] = (
    _opt("draft", "Entwurf", "Draft"),
    _opt("in_review", "In Prüfung", "In review"),
    _opt("approved", "Freigegeben", "Approved"),
    _opt("rejected", "Abgelehnt", "Rejected"),
)

VIEWPOINT_OPTIONS: tuple[dict[str, str], ...] = (
    _opt("logical", "Logisch", "Logical"),
    _opt("functional", "Funktional", "Functional"),
    _opt("physical", "Physisch", "Physical"),
    _opt("operational", "Betrieblich", "Operational"),
    _opt("deployment", "Deployment", "Deployment"),
)

RISK_TYPE_OPTIONS: tuple[dict[str, str], ...] = (
    _opt("threat", "Bedrohung", "Threat"),
    _opt("opportunity", "Chance", "Opportunity"),
)

RESIDUAL_RISK_OPTIONS: tuple[dict[str, str], ...] = (
    _opt("low", "Niedrig", "Low"),
    _opt("medium", "Mittel", "Medium"),
    _opt("high", "Hoch", "High"),
)

RESPONSE_STRATEGY_OPTIONS: tuple[dict[str, str], ...] = (
    _opt("avoid", "Vermeiden", "Avoid"),
    _opt("reduce", "Reduzieren", "Reduce"),
    _opt("transfer", "Übertragen", "Transfer"),
    _opt("accept", "Akzeptieren", "Accept"),
)

CHANGE_CLASS_OPTIONS: tuple[dict[str, str], ...] = (
    _opt("major", "Major", "Major"),
    _opt("minor", "Minor", "Minor"),
)

CCB_DECISION_OPTIONS: tuple[dict[str, str], ...] = (
    _opt("approved", "Angenommen", "Approved"),
    _opt("rejected", "Abgelehnt", "Rejected"),
    _opt("deferred", "Zurückgestellt", "Deferred"),
)

SAFETY_CLASSIFICATION_OPTIONS: tuple[dict[str, str], ...] = (
    _opt("qm", "QM", "QM"),
    _opt("asil_a", "ASIL A", "ASIL A"),
    _opt("asil_b", "ASIL B", "ASIL B"),
    _opt("asil_c", "ASIL C", "ASIL C"),
    _opt("asil_d", "ASIL D", "ASIL D"),
)

#: Stages on which the artifact-level ``owner`` system field is mandatory.
OWNER_MANDATORY_STAGES = frozenset({3})
#: Stages on which ``priority`` is mandatory.
PRIORITY_MANDATORY_STAGES = frozenset({2, 3})


def _new(
    name: str,
    type_: str,
    *,
    section: str,
    order: int,
    label_de: str,
    label_en: str,
    visible_stages: Iterable[int],
    mandatory_stages: Iterable[int] = (),
    options: tuple[dict[str, str], ...] | None = None,
    multiple: bool = False,
    allow_external: bool = False,
    editable: Any = True,
    help_de: str = "",
    help_en: str = "",
    ai_elicit: bool = False,
    export: bool = True,
    validation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one raw matrix attribute entry (pre-normalization).

    ``visible_stages``/``mandatory_stages`` are consumed by
    :func:`build_stage_attributes` and stripped before normalization; every
    other key is a documented schema key.
    """
    return {
        "name": name,
        "kind": "extended",
        "type": type_,
        "section": section,
        "order": order,
        "label": {"de": label_de, "en": label_en},
        "help_text": {"de": help_de, "en": help_en},
        "options": list(options or ()),
        "multiple": multiple,
        "allow_external": allow_external,
        "editable": editable,
        "ai_elicit": ai_elicit,
        "export": export,
        "validation": validation or {},
        # Consumed by build_stage_attributes, never stored.
        "_visible_stages": frozenset(visible_stages),
        "_mandatory_stages": frozenset(mandatory_stages),
    }


# ---------------------------------------------------------------------------
# New attributes per item type (matrix ``**Neu**`` rows, core/ext/system only)
# ---------------------------------------------------------------------------

MATRIX_ATTRIBUTES: Mapping[str, tuple[dict[str, Any], ...]] = {
    "Requirement": (
        _new("difficulty", "enum", section=SEC_CLASSIFICATION, order=120,
             label_de="Schwierigkeit", label_en="Difficulty",
             visible_stages={2, 3}, mandatory_stages={3}, options=DIFFICULTY_OPTIONS),
        _new("criticality", "enum", section=SEC_CLASSIFICATION, order=121,
             label_de="Kritikalität", label_en="Criticality",
             visible_stages={2, 3}, mandatory_stages={3}, options=CRITICALITY_OPTIONS),
        _new("verification_status", "enum", section=SEC_VERIFICATION, order=120,
             label_de="Verifikationsstatus", label_en="Verification status",
             visible_stages={2, 3}, mandatory_stages={3},
             options=VERIFICATION_STATUS_OPTIONS),
        _new("validation_method", "enum", section=SEC_VERIFICATION, order=121,
             label_de="Validierungsmethode", label_en="Validation method",
             visible_stages={3}, mandatory_stages={3},
             options=VERIFICATION_METHOD_OPTIONS),
        _new("rationale", "textarea", section=SEC_ATTRIBUTION, order=120,
             label_de="Begründung", label_en="Rationale",
             visible_stages={2, 3}, mandatory_stages={2, 3},
             help_de="Warum diese Anforderung existiert (ISO 29148).",
             help_en="Why this requirement exists (ISO 29148)."),
        _new("source", "text", section=SEC_ATTRIBUTION, order=121,
             label_de="Quelle", label_en="Source",
             visible_stages={2, 3}, mandatory_stages={3},
             help_de="Herkunft/Stakeholder der Anforderung.",
             help_en="Origin/stakeholder of the requirement."),
        _new("origin_link", "text", section=SEC_TRACEABILITY, order=120,
             label_de="Quellverweis", label_en="Origin link",
             visible_stages={2, 3}, mandatory_stages={3},
             help_de="Referenz auf die Quellpassage (ISO 29148 §5.2.8).",
             help_en="Reference to the source passage (ISO 29148 §5.2.8)."),
    ),
    "StakeholderNeed": (
        # Matrix carrier is ``actor``. ``Artifact.custom_fields`` is deliberately
        # flat (REQ-L2-AS-037 rejects nested dicts/lists), so the structured
        # Actor value cannot round-trip through the extended carrier yet; the
        # interim scalar text form keeps the attribute discoverable/writable and
        # is upgraded when the Actor carrier lands (WS7/AWMS, #940).
        _new("stakeholder", "text", section=SEC_ATTRIBUTION, order=120,
             label_de="Stakeholder", label_en="Stakeholder",
             visible_stages={2, 3}, mandatory_stages={2, 3},
             help_de="Rolle/Gruppe, die den Bedarf hat (ISO 42010). "
                     "Interim als Text, bis der Actor-Träger greift.",
             help_en="Role/group that owns the need (ISO 42010). "
                     "Interim text until the Actor carrier lands."),
        _new("rationale", "textarea", section=SEC_ATTRIBUTION, order=121,
             label_de="Begründung", label_en="Rationale",
             visible_stages={2, 3}, mandatory_stages={3}),
        _new("validation_criteria", "textarea", section=SEC_VERIFICATION, order=120,
             label_de="Validierungskriterien", label_en="Validation criteria",
             visible_stages={2, 3}, mandatory_stages={3}),
        # Matrix carrier is ``multi-enum``; the flat custom_fields map rejects
        # list values, so the interim carrier is a comma-separated text.
        _new("concern", "text", section=SEC_CLASSIFICATION, order=120,
             label_de="Concern", label_en="Concern",
             visible_stages={3}, mandatory_stages={3},
             help_de="ISO 42010 Concern(s) dieses Bedarfs "
                     "(kommasepariert, Interim bis zum strukturierten Träger).",
             help_en="ISO 42010 concern(s) of this need "
                     "(comma-separated, interim until the structured carrier)."),
    ),
    "ArchitectureElement": (
        _new("rationale", "textarea", section=SEC_ATTRIBUTION, order=120,
             label_de="Begründung", label_en="Rationale",
             visible_stages={2, 3}, mandatory_stages={3},
             help_de="Architecture Rationale (ISO 42010).",
             help_en="Architecture rationale (ISO 42010)."),
        _new("viewpoint", "enum", section=SEC_CLASSIFICATION, order=120,
             label_de="Viewpoint", label_en="Viewpoint",
             visible_stages={3}, mandatory_stages={3}, options=VIEWPOINT_OPTIONS),
        _new("technology", "text", section=SEC_CLASSIFICATION, order=121,
             label_de="Technologie", label_en="Technology",
             visible_stages={2, 3}, mandatory_stages={3}),
        _new("verification_method", "enum", section=SEC_VERIFICATION, order=120,
             label_de="Verifikationsmethode", label_en="Verification method",
             visible_stages={2, 3}, mandatory_stages={3},
             options=VERIFICATION_METHOD_OPTIONS),
        _new("performance_budget", "number", section=SEC_CLASSIFICATION, order=122,
             label_de="Performance-Budget", label_en="Performance budget",
             visible_stages={3}, mandatory_stages={3}),
    ),
    "TestCase": (
        _new("objective", "textarea", section=SEC_CONTENT, order=120,
             label_de="Ziel", label_en="Objective",
             visible_stages={2, 3}, mandatory_stages={3}),
        _new("preconditions", "textarea", section=SEC_CONTENT, order=121,
             label_de="Vorbedingungen", label_en="Preconditions",
             visible_stages={2, 3}, mandatory_stages={2, 3}),
        _new("postconditions", "textarea", section=SEC_CONTENT, order=122,
             label_de="Nachbedingungen", label_en="Postconditions",
             visible_stages={2, 3}, mandatory_stages={3}),
        _new("expected_result", "textarea", section=SEC_CONTENT, order=123,
             label_de="Erwartetes Ergebnis", label_en="Expected result",
             visible_stages={2, 3}, mandatory_stages={2, 3}),
        _new("test_level", "enum", section=SEC_CLASSIFICATION, order=120,
             label_de="Testebene", label_en="Test level",
             visible_stages={2, 3}, mandatory_stages={3}, options=TEST_LEVEL_OPTIONS),
        _new("test_data", "textarea", section=SEC_VERIFICATION, order=120,
             label_de="Testdaten", label_en="Test data",
             visible_stages={2, 3}, mandatory_stages={3}),
        _new("test_environment", "textarea", section=SEC_VERIFICATION, order=121,
             label_de="Testumgebung", label_en="Test environment",
             visible_stages={3}, mandatory_stages={3}),
        _new("review_status", "enum", section=SEC_ATTRIBUTION, order=120,
             label_de="Review-Status", label_en="Review status",
             visible_stages={2, 3}, mandatory_stages={3},
             options=REVIEW_STATUS_OPTIONS),
    ),
    "Adr": (
        _new("alternatives", "textarea", section=SEC_CONTENT, order=120,
             label_de="Alternativen", label_en="Alternatives",
             visible_stages={2, 3}, mandatory_stages={2, 3},
             help_de="Betrachtete und verworfene Optionen (ISO 42010/MADR).",
             help_en="Considered and rejected options (ISO 42010/MADR)."),
        # ``multi-enum``/``actor`` list/object values are rejected by the flat
        # custom_fields map (REQ-L2-AS-037); interim comma-separated text.
        _new("decision_drivers", "text", section=SEC_CLASSIFICATION, order=120,
             label_de="Entscheidungstreiber", label_en="Decision drivers",
             visible_stages={2, 3}, mandatory_stages={3},
             help_de="Kommasepariert (Interim bis zum strukturierten Träger).",
             help_en="Comma-separated (interim until the structured carrier)."),
        _new("deciders", "text", section=SEC_ATTRIBUTION, order=120,
             label_de="Entscheider", label_en="Deciders",
             visible_stages={2, 3}, mandatory_stages={3},
             help_de="Kommasepariert (Interim bis zum Actor-Träger).",
             help_en="Comma-separated (interim until the Actor carrier)."),
        _new("decided_at", "date", section=SEC_ATTRIBUTION, order=121,
             label_de="Entschieden am", label_en="Decided at",
             visible_stages={2, 3}, mandatory_stages={3}),
        _new("supersedes", "reference", section=SEC_TRACEABILITY, order=120,
             label_de="Ersetzt", label_en="Supersedes",
             visible_stages={2, 3}, mandatory_stages={3}),
    ),
    "Risk": (
        _new("risk_type", "enum", section=SEC_CLASSIFICATION, order=120,
             label_de="Risikoart", label_en="Risk type",
             visible_stages={2, 3}, mandatory_stages={3}, options=RISK_TYPE_OPTIONS),
        _new("residual_risk", "enum", section=SEC_CLASSIFICATION, order=121,
             label_de="Restrisiko", label_en="Residual risk",
             visible_stages={2, 3}, mandatory_stages={3},
             options=RESIDUAL_RISK_OPTIONS),
        _new("response_strategy", "enum", section=SEC_ATTRIBUTION, order=120,
             label_de="Behandlungsstrategie", label_en="Response strategy",
             visible_stages={2, 3}, mandatory_stages={3},
             options=RESPONSE_STRATEGY_OPTIONS),
        _new("review_cycle", "date", section=SEC_ATTRIBUTION, order=121,
             label_de="Review-Zyklus", label_en="Review cycle",
             visible_stages={2, 3}, mandatory_stages={3}),
        # Matrix carrier is `ext` with an `automation` edit policy (RPN-derived).
        # ``Risk.severity`` is a persisted derived column and stays excluded from
        # introspection (PER_ITEM_TYPE_EXCLUDED_FIELDS); this extended twin is
        # the future AWMS-owned carrier and is writable today only so the
        # contract matrix can exercise it.
        _new("severity", "number", section=SEC_CLASSIFICATION, order=122,
             label_de="Schweregrad (RPN)", label_en="Severity (RPN)",
             visible_stages={2, 3}, mandatory_stages={3},
             editable="automation",
             help_de="Automatisch aus der Risikomatrix abgeleitet (RPN).",
             help_en="Derived from the risk matrix (RPN)."),
    ),
    "Issue": (
        # Matrix carrier is ``actor``; flat custom_fields rejects the entry
        # object (REQ-L2-AS-037) — interim scalar text until the Actor carrier.
        _new("assignee", "text", section=SEC_ATTRIBUTION, order=120,
             label_de="Zugewiesen an", label_en="Assignee",
             visible_stages={2, 3}, mandatory_stages={3},
             help_de="Interim als Text, bis der Actor-Träger greift.",
             help_en="Interim text until the Actor carrier lands."),
        _new("resolution", "textarea", section=SEC_CONTENT, order=120,
             label_de="Lösung", label_en="Resolution",
             visible_stages={2, 3}, mandatory_stages={3}),
        _new("root_cause", "textarea", section=SEC_CONTENT, order=121,
             label_de="Ursache", label_en="Root cause",
             visible_stages={2, 3}, mandatory_stages={3}),
    ),
    "Goal": (
        _new("timeframe", "date", section=SEC_ATTRIBUTION, order=120,
             label_de="Zeitrahmen", label_en="Timeframe",
             visible_stages={2, 3}, mandatory_stages={3}),
        _new("measure_name", "text", section=SEC_CLASSIFICATION, order=120,
             label_de="Messgröße", label_en="Measure name",
             visible_stages={2, 3}, mandatory_stages={3},
             help_de="Interim bis zur Measure-Entität (#393).",
             help_en="Interim until the Measure entity lands (#393)."),
        _new("target_value", "number", section=SEC_CLASSIFICATION, order=121,
             label_de="Zielwert", label_en="Target value",
             visible_stages={2, 3}, mandatory_stages={3}),
        _new("unit", "text", section=SEC_CLASSIFICATION, order=122,
             label_de="Einheit", label_en="Unit",
             visible_stages={2, 3}, mandatory_stages={3}),
        _new("threshold", "number", section=SEC_CLASSIFICATION, order=123,
             label_de="Schwellwert", label_en="Threshold",
             visible_stages={2, 3}, mandatory_stages={3}),
        _new("parent_goal", "reference", section=SEC_TRACEABILITY, order=120,
             label_de="Übergeordnetes Ziel", label_en="Parent goal",
             visible_stages={2, 3}, mandatory_stages={3}),
    ),
    "Icd": (
        _new("data_elements", "textarea", section=SEC_CONTENT, order=120,
             label_de="Datenelemente", label_en="Data elements",
             visible_stages={2, 3}, mandatory_stages={2, 3},
             help_de="Payload/Struktur der Schnittstelle.",
             help_en="Interface payload/structure."),
        _new("protocol", "text", section=SEC_CLASSIFICATION, order=120,
             label_de="Protokoll", label_en="Protocol",
             visible_stages={2, 3}, mandatory_stages={3}),
        _new("version", "text", section=SEC_CLASSIFICATION, order=121,
             label_de="Version", label_en="Version",
             visible_stages={2, 3}, mandatory_stages={3}),
        _new("timing", "text", section=SEC_CLASSIFICATION, order=122,
             label_de="Timing", label_en="Timing",
             visible_stages={3}, mandatory_stages={3}),
        _new("safety_classification", "enum", section=SEC_CLASSIFICATION, order=123,
             label_de="Sicherheitsklassifikation", label_en="Safety classification",
             visible_stages={3}, mandatory_stages={3},
             options=SAFETY_CLASSIFICATION_OPTIONS),
    ),
    "GlossaryTerm": (
        # Matrix carrier is ``multi-enum``; free-form synonyms cannot be
        # expressed as a closed option list, so the honest schema type here is
        # ``text`` (comma-separated). Documented deviation in the WS6 report.
        _new("synonyms", "text", section=SEC_CONTENT, order=120,
             label_de="Synonyme", label_en="Synonyms",
             visible_stages={2, 3}, mandatory_stages={}),
        _new("source", "text", section=SEC_ATTRIBUTION, order=120,
             label_de="Quelle", label_en="Source",
             visible_stages={2, 3}, mandatory_stages={3}),
    ),
    "ChangeRequest": (
        _new("change_class", "enum", section=SEC_CLASSIFICATION, order=120,
             label_de="Änderungsklasse", label_en="Change class",
             visible_stages={2, 3}, mandatory_stages={2, 3},
             options=CHANGE_CLASS_OPTIONS),
        _new("ccb_decision", "enum", section=SEC_CHANGE, order=120,
             label_de="CCB-Entscheidung", label_en="CCB decision",
             visible_stages={2, 3}, mandatory_stages={2, 3},
             options=CCB_DECISION_OPTIONS),
        _new("decided_at", "date", section=SEC_CHANGE, order=121,
             label_de="Entschieden am", label_en="Decided at",
             visible_stages={2, 3}, mandatory_stages={3}),
        _new("target_baseline", "reference", section=SEC_TRACEABILITY, order=120,
             label_de="Ziel-Baseline", label_en="Target baseline",
             visible_stages={2, 3}, mandatory_stages={3}),
        _new("verification_of_change", "textarea", section=SEC_VERIFICATION, order=120,
             label_de="Verifikation der Änderung", label_en="Verification of change",
             visible_stages={3}, mandatory_stages={3}),
    ),
}


# ---------------------------------------------------------------------------
# Per-stage overrides for attributes that already exist (model introspection or
# the artifact-level system fields).
# ---------------------------------------------------------------------------
#
# ``visible``/``mandatory`` are stage sets; ``section``/``audience`` optionally
# correct their metadata. Only attributes the matrix actually stages are listed
# — an attribute the matrix omits keeps its introspected defaults untouched.

MATRIX_OVERRIDES: Mapping[str, Mapping[str, Mapping[str, Any]]] = {
    "Requirement": {
        "description": {"visible": {1, 2, 3}, "mandatory": {2, 3}},
        "type": {"visible": {2, 3}, "mandatory": {3}},
        "level": {"visible": {2, 3}, "mandatory": {3}},
        "acceptance_criteria": {"visible": {1, 2, 3}, "mandatory": {2, 3}},
        "verification_method": {"visible": {2, 3}, "mandatory": {2, 3}},
        "complexity_fibonacci": {"visible": {2, 3}, "mandatory": {}},
        "change_reason": {"visible": {2, 3}, "mandatory": {3}},
    },
    "StakeholderNeed": {
        "description": {"visible": {1, 2, 3}, "mandatory": {2, 3}},
        # moscow_priority stays a *core* model column until the AWMS fold (WS7,
        # #940); the matrix's extended carrier only governs its staged
        # visibility/mandatory-ness here.
        "moscow_priority": {"visible": {2, 3}, "mandatory": {2, 3}},
    },
    "ArchitectureElement": {
        "element_type": {"visible": {1, 2, 3}, "mandatory": {3}},
        "description": {"visible": {1, 2, 3}, "mandatory": {2, 3}},
        "parent_id": {"visible": {1, 2, 3}, "mandatory": {2, 3}},
        "asil_level": {"visible": {2, 3}, "mandatory": {3}},
        "make_or_buy": {"visible": {2, 3}, "mandatory": {3}},
    },
    "TestCase": {
        "description": {"visible": {1, 2, 3}, "mandatory": {3}},
        "steps": {"visible": {1, 2, 3}, "mandatory": {2, 3}},
        "test_type": {"visible": {1, 2, 3}, "mandatory": {2, 3}},
    },
    "Adr": {
        "consequences": {"visible": {1, 2, 3}, "mandatory": {2, 3}},
    },
    "Risk": {
        "description": {"visible": {1, 2, 3}, "mandatory": {2, 3}},
        "probability": {"visible": {1, 2, 3}, "mandatory": {2, 3}},
        "impact": {"visible": {1, 2, 3}, "mandatory": {2, 3}},
        "detection": {"visible": {2, 3}, "mandatory": {}},
        "risk_matrix": {"visible": {2, 3}, "mandatory": {3}},
        "mitigation_strategy": {"visible": {1, 2, 3}, "mandatory": {2, 3}},
    },
    "Issue": {
        "description": {"visible": {1, 2, 3}, "mandatory": {2, 3}},
        "severity": {"visible": {1, 2, 3}, "mandatory": {2, 3}},
        "due_date": {"visible": {2, 3}, "mandatory": {3}},
        "tag_list": {"visible": {2, 3}, "mandatory": {}},
    },
    "Goal": {
        "description": {"visible": {1, 2, 3}, "mandatory": {2, 3}},
    },
    "Icd": {
        "semantic_description": {"visible": {1, 2, 3}, "mandatory": {2, 3}},
    },
    "ChangeRequest": {
        "impact_assessment": {"visible": {1, 2, 3}, "mandatory": {2, 3}},
        "change_reason": {"visible": {1, 2, 3}, "mandatory": {2, 3}},
    },
}


#: Names the matrix marks ``P`` at **every** stage (S1/S2/S3) for the given
#: item type. They are already create-required where the model says so; this
#: set only records their stage-readiness explicitly so the staged model is
#: complete. Identity names that differ per type (``term``/``name``) included.
_ALWAYS_MANDATORY_NAMES: Mapping[str, frozenset[str]] = {
    "Requirement": frozenset({"title"}),
    "StakeholderNeed": frozenset({"title"}),
    "ArchitectureElement": frozenset({"title"}),
    "TestCase": frozenset({"title"}),
    "Adr": frozenset({"title", "context", "decision"}),
    "Risk": frozenset({"title"}),
    "Issue": frozenset({"title"}),
    "Goal": frozenset({"title"}),
    "Icd": frozenset(
        {
            "name",
            "source_element_id",
            "target_element_id",
            "direction",
            "interface_type",
        }
    ),
    "GlossaryTerm": frozenset({"term", "definition"}),
    "ChangeRequest": frozenset({"title", "description"}),
}


def _audience_for(visible_stages: frozenset[int]) -> str:
    """Rigor audience of a staged attribute (spec section 14.3).

    An attribute first shown at Full-SE is ``expert``; anything visible at an
    earlier stage is ``basic`` — the same "Stufe 3 = audience expert" rule the
    matrix's rollout note states.
    """
    return "expert" if visible_stages == frozenset({3}) else "basic"


def build_stage_attributes(
    item_type: str, preset: str
) -> list[dict[str, Any]]:
    """Return the matrix's **new** attributes for ``(item_type, preset)``.

    Every entry is normalized (``normalize_attribute``) and carries the
    concrete ``visible``/``stage_mandatory``/``audience`` of *preset*'s stage.
    An attribute not visible at the stage is still emitted — hidden
    (``visible=False``) so an admin can reveal it without a schema round-trip,
    exactly how the artifact-level carrier fields behave.
    """
    stage = PRESET_STAGE[preset]
    out: list[dict[str, Any]] = []
    for raw in MATRIX_ATTRIBUTES.get(item_type, ()):
        entry = {k: v for k, v in raw.items() if not k.startswith("_")}
        visible_stages = raw["_visible_stages"]
        entry["visible"] = stage in visible_stages
        entry["stage_mandatory"] = stage in raw["_mandatory_stages"]
        entry["audience"] = _audience_for(visible_stages)
        out.append(normalize_attribute(entry))
    return out


def apply_stage_overrides(
    item_type: str, preset: str, attributes: list[dict[str, Any]]
) -> None:
    """Apply the matrix's per-stage metadata to *attributes* in place.

    *attributes* must be the already-normalized introspection result. Only the
    keys ``visible``/``stage_mandatory``/``audience``/``section`` are touched;
    ``required`` is deliberately left alone (see the module docstring).
    """
    stage = PRESET_STAGE[preset]
    by_name = {a["name"]: a for a in attributes}
    for name in _ALWAYS_MANDATORY_NAMES.get(item_type, frozenset()):
        attribute = by_name.get(name)
        if attribute is not None:
            attribute["stage_mandatory"] = True
    overrides = MATRIX_OVERRIDES.get(item_type)
    if not overrides:
        return
    for name, override in overrides.items():
        attribute = by_name.get(name)
        if attribute is None:
            continue
        visible_stages = override.get("visible")
        if visible_stages is not None:
            attribute["visible"] = stage in visible_stages
            attribute["audience"] = _audience_for(frozenset(visible_stages))
        mandatory_stages = override.get("mandatory")
        if mandatory_stages is not None:
            attribute["stage_mandatory"] = stage in mandatory_stages
        if "section" in override:
            attribute["section"] = override["section"]


def stage_mandatory_names(
    attributes: list[dict[str, Any]],
    sections: list[dict[str, Any]] | None = None,
) -> tuple[str, ...]:
    """Names of *attributes* the resolved definition marks mandatory for its stage.

    Mirrors :func:`attribute_definitions.mandatory_fields.required_attribute_names`
    (visible + non-hidden-section + client-fillable) but reads ``stage_mandatory``
    instead of ``required``. Exposed so a later wave (WS7/AWMS) can wire it into
    the approval/baseline gates without re-deriving the predicate.
    """
    hidden_sections = {
        section["name"] for section in (sections or []) if not section.get("visible", True)
    }
    return tuple(
        attribute["name"]
        for attribute in attributes
        if attribute.get("stage_mandatory", False)
        and attribute["visible"]
        and attribute["section"] not in hidden_sections
        and attribute["type"] != "widget"
        and attribute["editable"] not in ("workflow", "system")
    )


__all__ = [
    "MATRIX_ATTRIBUTES",
    "MATRIX_OVERRIDES",
    "OWNER_MANDATORY_STAGES",
    "PRESET_STAGE",
    "PRIORITY_MANDATORY_STAGES",
    "SEC_ATTRIBUTION",
    "SEC_CHANGE",
    "SEC_CLASSIFICATION",
    "SEC_CONTENT",
    "SEC_IDENTIFICATION",
    "SEC_TRACEABILITY",
    "SEC_TYPE_SPECIFIC",
    "SEC_VERIFICATION",
    "apply_stage_overrides",
    "build_stage_attributes",
    "stage_mandatory_names",
]
