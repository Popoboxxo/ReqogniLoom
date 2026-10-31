"""Plan F F4.1 — the single source of truth for what a baseline rollback may restore.

ADR-025 (additiver Baseline-Rollback) restores **only** the fields declared in
:data:`RESTORABLE_FIELDS`. Everything else a snapshot may carry is deliberately
out of scope, and :data:`NON_RESTORABLE` says why per field, so a reader never
has to infer the reason from the capture code.

The two lists answer two different questions:

* :data:`RESTORABLE_FIELDS` — **captured AND writable through a domain service**.
  These are exactly the keys an additive rollback (F4.4) writes back; a key that
  is captured but not writable here would be a rollback that silently does
  nothing, so the two are kept in lockstep by
  ``baseline.tests.test_state_capture_completeness_1374``.
* :data:`NON_RESTORABLE` — **captured-or-derived, but never written by a
  rollback**: identity (``uid``), governance (``status``), locking
  (``version``), derived values (``level``, ``suspect``, ``risk_score``,
  ``severity``), structural keys, and state that only a dedicated lifecycle
  transition may change (``lifecycle_status`` via ``reactivate``).

``RESTORABLE_FIELDS`` names **captured keys** (not model attribute names), so a
rollback can address the snapshot dict directly. The two differ in exactly one
published alias: ``Risk.owner_name`` is captured as ``owner`` (Attribut v3 WS7
#940 kept the published baseline key). Because the shared Artifact hull also
owns an ``owner`` key, the hull merge uses ``setdefault`` — for Risk the legacy
free-text owner wins and the Artifact-level Actor owner is not captured (see
the ``Risk.actor_owner`` entry in :data:`NON_RESTORABLE`).

Only one deliberate capture gap remains, and it is system-owned rather than
editable content:

* ``embedding_model`` — provenance of the embedding vector, system-owned.

No Django model is imported here: these are plain constants, so any layer
(service, REST, MCP) can import them without an app-load cycle.
"""
from __future__ import annotations

__all__ = ["NON_RESTORABLE", "RESTORABLE_FIELDS"]

#: Captured Artifact-hull keys (see ``state_capture._capture_items``) that a
#: rollback may write back through the type's domain service.
_ARTIFACT_HULL_RESTORABLE: tuple[str, ...] = (
    "owner",
    "reporter",
    "priority",
    "stakeholder",
    "custom_fields",
)

#: Captured hull keys that are structural rather than content.
_ARTIFACT_HULL_NON_RESTORABLE: dict[str, str] = {
    "artifact_type": "identity/type discriminator",
    "artifact_parent_id": "structural hierarchy, not additive content",
}

#: ``artifact_type -> captured keys a rollback may write back``.
#:
#: Only content a user can author and a domain service can write is listed.
#: Identity, governance, derived and locking keys live in NON_RESTORABLE.
RESTORABLE_FIELDS: dict[str, tuple[str, ...]] = {
    "Requirement": (
        "title",
        "description",
        # #871/#583 and #1288/#1289 requirement attributes (Plan F F4.1).
        "rationale",
        "source",
        "acceptance_criteria",
        "acceptance_criteria_items",
        "category",
        "type",
        "complexity_fibonacci",
        "verification_method",
        "level_source",
        *_ARTIFACT_HULL_RESTORABLE,
    ),
    "StakeholderNeed": (
        "title",
        "description",
        "category",
        "moscow_priority",
        *_ARTIFACT_HULL_RESTORABLE,
    ),
    "ArchitectureElement": (
        "title",
        "description",
        "element_type",
        # Captured as the FK's ``parent_id`` attname (a plain element UUID).
        "parent_id",
        "asil_level",
        "make_or_buy",
        *_ARTIFACT_HULL_RESTORABLE,
    ),
    "TestCase": (
        "title",
        "description",
        "steps",
        "test_type",
        # #424 / #402: provenance, in-content review flag and the
        # nominal/off-nominal categorisation are editable content.
        "origin",
        "reviewed",
        "scenario_kind",
        *_ARTIFACT_HULL_RESTORABLE,
    ),
    "Adr": (
        "title",
        "description",
        "context",
        "decision",
        "consequences",
        *_ARTIFACT_HULL_RESTORABLE,
    ),
    "Risk": (
        "title",
        "description",
        "category",
        "probability",
        "impact",
        "detection",
        "mitigation_strategy",
        # Legacy published keys: ``owner`` is ``Risk.owner_name`` (WS7 #940),
        # ``owner_user_id`` is the User FK.
        "owner",
        "owner_user_id",
        *_ARTIFACT_HULL_RESTORABLE,
    ),
    "Issue": (
        "title",
        "description",
        "severity",
        "category",
        "assignee_id",
        # Plan F F4.1: bookkeeping of the last reassignment; the capture stores
        # it as an ISO-8601 string (or None), so it round-trips as content.
        "assignee_changed_date",
        "due_date",
        "tags",
        *_ARTIFACT_HULL_RESTORABLE,
    ),
    # Restored from the ``glossary_term`` entry, never from the bare ``item``
    # hull (see baseline.state_capture's module docstring).
    "GlossaryTerm": (
        "term",
        "definition",
        "synonyms",
        "abbreviation",
    ),
}

#: ``artifact_type -> {field: reason}`` — captured (or model-level) fields a
#: rollback must not write back, each with the reason it is excluded.
NON_RESTORABLE: dict[str, dict[str, str]] = {
    "Requirement": {
        "level": "derived (ADR-005)",
        "status": "workflow governance",
        "uid": "identity",
        "version": "optimistic lock",
        "suspect": "derived",
        "lifecycle_status": "via reactivate",
        "embedding_model": "system-owned (embedding provenance)",
        **_ARTIFACT_HULL_NON_RESTORABLE,
    },
    "StakeholderNeed": {
        "status": "workflow governance",
        "uid": "identity",
        "version": "optimistic lock",
        "suspect": "derived",
        "lifecycle_status": "via reactivate",
        **_ARTIFACT_HULL_NON_RESTORABLE,
    },
    "ArchitectureElement": {
        "uid": "identity",
        "version": "optimistic lock",
        "suspect": "derived",
        "lifecycle_status": "via reactivate",
        **_ARTIFACT_HULL_NON_RESTORABLE,
    },
    "TestCase": {
        "status": "workflow governance",
        "uid": "identity",
        "version": "optimistic lock",
        "suspect": "derived",
        "lifecycle_status": "via reactivate",
        **_ARTIFACT_HULL_NON_RESTORABLE,
    },
    "Adr": {
        "status": "workflow governance",
        "uid": "identity",
        "version": "optimistic lock",
        "lifecycle_status": "via reactivate",
        **_ARTIFACT_HULL_NON_RESTORABLE,
    },
    "Risk": {
        "status": "workflow governance",
        "uid": "identity",
        "version": "optimistic lock",
        "risk_score": "derived (probability x impact)",
        "severity": "derived (risk_score)",
        "lifecycle_status": "via reactivate",
        # Documented capture gap, not a captured key: the shared Artifact hull's
        # Actor ``owner`` is suppressed for Risk by the ``setdefault`` merge
        # because the published ``owner`` key already carries ``Risk.owner_name``
        # (WS7 #940). A rollback therefore cannot restore the Actor owner.
        "actor_owner": "key occupied by owner_name; actor owner not captured",
        **_ARTIFACT_HULL_NON_RESTORABLE,
    },
    "Issue": {
        "status": "workflow governance",
        "uid": "identity",
        "version": "optimistic lock",
        "lifecycle_status": "via reactivate",
        **_ARTIFACT_HULL_NON_RESTORABLE,
    },
    "GlossaryTerm": {
        "version": "optimistic lock",
        "lifecycle_status": "via reactivate",
        "artifact_type": "identity/type discriminator",
    },
}
