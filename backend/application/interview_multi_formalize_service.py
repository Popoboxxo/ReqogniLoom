"""Multi-mode interview formalization + proposal validation (R2S-010).

Owns the caller-supplied ``confirmed_proposal`` gate (structure, allowlist,
type/length ceilings) and the atomic multi-artifact creation pipeline. The
validation helpers keep their original module-level names and are re-exported
from ``interview_service`` for import compatibility.
"""
from __future__ import annotations

import logging
from typing import Any

from django.db import transaction
from django.db.models import F

from application.base import ValidationError
from application.models import DomainEventOutbox
from persistence.models import InterviewSession, InterviewSessionArtifact

# Keep the original log category: operators filter on it, and the split must
# not change observable logging behaviour.
logger = logging.getLogger("application.interview_service")

# Link type rejected at multi-mode proposal-parse level (Task 3): owned by
# the diagram reconciler, never hand-authored -- see _formalize_multi.
_DIAGRAM_REF_LINK_TYPE = "diagram-ref"

# AI-005 write-path hardening: a multi-mode ``confirmed_proposal`` arrives from
# an LLM's parsed JSON *or* straight from a caller (REST body / MCP AUTHOR key).
# Its ``fields`` dict is splatted into a production create_X() via
# ARTIFACT_CREATION_ADAPTERS, so without a gate a model/caller could set
# server-owned fields or smuggle oversized strings into a domain write. This
# module is the service layer -- the single choke point REST, UI and MCP all
# pass through -- so the validation lives here and no transport can bypass it.
#
# Reserved field names: status is workflow-owned; owner/reporter/priority are
# Artifact-level system fields written through their own gateway; the rest are
# internal identity/audit columns. This small BLOCKLIST is applied on top of
# the derived allowlist so a create_X() that happens to accept `status`
# (StakeholderNeed) or `owner` (Risk) still cannot be driven by model output.
# Deliberately narrow: legitimate classification fields such as Issue.severity
# or Risk.probability are NOT reserved and keep working.
_RESERVED_PROPOSAL_FIELDS: frozenset[str] = frozenset({
    "status", "owner", "reporter", "priority",
    "id", "tenant", "tenant_id", "workspace", "workspace_id",
    "artifact", "artifact_id", "created_by", "created_at", "modified_at",
    "version", "ctx",
})

# Conservative string ceilings. 5000 matches the largest free-text column
# max_length on the in-scope models (e.g. Adr.context/decision), so legitimate
# long answers survive while a 10k-char payload is refused. Short name fields
# (title/term/name) use the largest model CharField max_length across the nine
# serializers (Requirement/StakeholderNeed/ArchitectureElement/TestCase = 500).
MAX_PROPOSAL_STRING_LENGTH = 5000
MAX_PROPOSAL_TITLE_LENGTH = 500
_SHORT_STRING_FIELDS: frozenset[str] = frozenset({"title", "term", "name"})

# Bound structured values (steps/tags/synonyms/custom_fields) so a huge nested
# payload cannot reach a domain write either.
MAX_PROPOSAL_CONTAINER_ITEMS = 200


def _validate_confirmed_proposal(confirmed_proposal: list[dict]) -> None:
    """Structure-validate a multi-mode proposal (pre-transaction, fail fast).

    Every item must be a dict with ``type: str`` and ``fields: dict``; every
    link (if present) must be a dict with ``from: int`` / ``to: int``
    (indices into the proposal item list) plus ``type: str``. ``links`` may
    be explicitly null (normalised to an empty list in place) but any other
    non-list value is rejected. Anything else raises ValidationError BEFORE
    transaction.atomic() opens, so malformed caller input can never abort an
    already half-applied batch.
    """
    for index, item in enumerate(confirmed_proposal):
        _validate_confirmed_proposal_item(index, item, len(confirmed_proposal))


def _validate_confirmed_proposal_item(item_index: int, item: Any, item_count: int) -> None:
    """Validate one multi-mode proposal item (pre-transaction, fail fast).

    ``item_count`` is the total number of items in the proposal -- link
    endpoints index into that list.
    """
    if not isinstance(item, dict):
        raise ValidationError(
            f"proposal item #{item_index} must be a dict, got {type(item).__name__}"
        )
    item_type = item.get("type")
    if not isinstance(item_type, str):
        raise ValidationError(
            f"proposal item #{item_index}: 'type' must be a string, got {item_type!r}"
        )
    if not isinstance(item.get("fields"), dict):
        raise ValidationError(
            f"proposal item {item_type!r} must carry a 'fields' dict"
        )
    # Review-2 fix m1: 'links' may be explicitly null in caller JSON.
    # dict.get(key, default) does NOT help here -- it returns None (not
    # the default) when the key exists with value None, so enumerate(None)
    # used to raise a bare TypeError. Normalise None to [] IN PLACE so
    # _formalize_multi's later item.get("links", []) loops see a real
    # list too; anything non-list is a clean ValidationError instead.
    raw_links = item.get("links")
    if raw_links is None:
        # Normalise in place so _formalize_multi's later
        # item.get("links", []) loops see a real list too.
        item["links"] = []
    elif not isinstance(raw_links, list):
        raise ValidationError(
            f"proposal item {item_type!r}: 'links' must be a list or null, "
            f"got {type(raw_links).__name__}"
        )
    else:
        for link_index, link in enumerate(raw_links):
            _validate_confirmed_proposal_link(item_type, link_index, link, item_count)


def _validate_confirmed_proposal_link(
    item_type: str, link_index: int, link: Any, item_count: int
) -> None:
    """Validate one link of a multi-mode proposal item (pre-transaction)."""
    if not isinstance(link, dict):
        raise ValidationError(
            f"proposal item {item_type!r}, link #{link_index} must be a dict"
        )
    for endpoint in ("from", "to"):
        value = link.get(endpoint)
        # bool is an int subclass -- True/False must not pass as
        # link endpoints via created_refs[True] indexing.
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValidationError(
                f"proposal item {item_type!r}, link #{link_index}: "
                f"'{endpoint}' must be an int index into the proposal items, "
                f"got {value!r}"
            )
        if not 0 <= value < item_count:
            raise ValidationError(
                f"proposal item {item_type!r}, link #{link_index}: "
                f"'{endpoint}' index {value} is out of range "
                f"(0..{item_count - 1})"
            )
    if not isinstance(link.get("type"), str):
        raise ValidationError(
            f"proposal item {item_type!r}, link #{link_index}: "
            f"'type' must be a string, got {link.get('type')!r}"
        )


def _tenant_custom_attribute_names(ctx, workspace_id, artifact_type: str) -> frozenset[str]:
    """Tenant-defined attribute names for *artifact_type* in *workspace_id*.

    Read from the same resolved attribute definition every create/update
    transport uses, so a workspace-custom attribute stays writable through an
    interview. A workspace that has not run ``bootstrap_attribute_definitions``
    has no definition: return an empty set and let the create-signature
    allowlist carry the standard fields (production self_init always bootstraps,
    so this is only the fresh-workspace/test-fixture case).
    """
    from application.attribute_definition_service import AttributeDefinitionService

    try:
        definition = AttributeDefinitionService().resolve(ctx, artifact_type, workspace_id)
    except Exception:  # noqa: BLE001 — a config read must not turn a write into a 500
        logger.warning(
            "Could not resolve attribute definitions for %s in workspace %s; "
            "using create-signature allowlist only",
            artifact_type,
            workspace_id,
            exc_info=True,
        )
        return frozenset()
    return frozenset(
        attribute["name"]
        for attribute in definition.get("attributes", [])
        if isinstance(attribute, dict) and isinstance(attribute.get("name"), str)
    )


def _validate_proposal_field_value(item_type: str, key: str, value: Any) -> None:
    """Type + length validation of one proposal field value (AI-005)."""
    if isinstance(value, str):
        limit = (
            MAX_PROPOSAL_TITLE_LENGTH
            if key in _SHORT_STRING_FIELDS
            else MAX_PROPOSAL_STRING_LENGTH
        )
        if len(value) > limit:
            raise ValidationError(
                f"proposal item {item_type!r}: field {key!r} exceeds the "
                f"{limit}-character limit"
            )
        return
    if value is None or isinstance(value, (int, float, bool)):
        return
    if isinstance(value, (list, dict)):
        # Structured values (steps/tags/synonyms/custom_fields) are legal, but
        # still bounded recursively so no oversized string hides inside them.
        pending: list[Any] = [value]
        visited = 0
        while pending:
            node = pending.pop()
            visited += 1
            if visited > MAX_PROPOSAL_CONTAINER_ITEMS:
                raise ValidationError(
                    f"proposal item {item_type!r}: field {key!r} is too large "
                    f"(more than {MAX_PROPOSAL_CONTAINER_ITEMS} nested values)"
                )
            if isinstance(node, str):
                if len(node) > MAX_PROPOSAL_STRING_LENGTH:
                    raise ValidationError(
                        f"proposal item {item_type!r}: field {key!r} contains a "
                        f"string exceeding the {MAX_PROPOSAL_STRING_LENGTH}-character limit"
                    )
            elif isinstance(node, dict):
                for sub_key, sub_value in node.items():
                    if not isinstance(sub_key, str):
                        raise ValidationError(
                            f"proposal item {item_type!r}: field {key!r} has a "
                            "non-string nested key"
                        )
                    pending.append(sub_value)
            elif isinstance(node, list):
                pending.extend(node)
            elif node is None or isinstance(node, (int, float, bool)):
                continue
            else:
                raise ValidationError(
                    f"proposal item {item_type!r}: field {key!r} has an unsupported "
                    f"value type {type(node).__name__}"
                )
        return
    raise ValidationError(
        f"proposal item {item_type!r}: field {key!r} has an unsupported value "
        f"type {type(value).__name__}"
    )


def validate_confirmed_proposal_fields(
    ctx, workspace_id, confirmed_proposal: list[dict]
) -> None:
    """Allowlist + type/length gate on every proposal item's ``fields`` (AI-005).

    Runs in the SERVICE layer (``InterviewService._formalize_multi``), so REST,
    UI and MCP callers -- including an AUTHOR-scoped MCP key that supplies
    ``confirmed_proposal`` directly -- are all protected by the same check.
    Policy is REJECT (fail closed): a reserved, unknown or oversized field
    raises ``ValidationError`` BEFORE any ``create_X()`` is called.

    Allowed names are DERIVED, not hardcoded: the writable kwargs of the
    artifact type's production ``create_X()`` (``allowed_fields_for``) plus the
    workspace's tenant-defined attribute names. The small reserved blocklist
    above is subtracted. Unknown artifact types are intentionally skipped here
    so ``_create_proposal_items`` keeps reporting its canonical "unknown
    artifact type" error; they still reach no ``create_X()``.
    """
    from application.interview_artifact_adapters import (
        ARTIFACT_CREATION_ADAPTERS,
        allowed_fields_for,
    )

    allowed_cache: dict[str, frozenset[str]] = {}
    for item_index, item in enumerate(confirmed_proposal):
        item_type = item["type"]  # already structure-validated
        if item_type not in ARTIFACT_CREATION_ADAPTERS:
            continue
        allowed = allowed_cache.get(item_type)
        if allowed is None:
            allowed = allowed_fields_for(item_type) | _tenant_custom_attribute_names(
                ctx, workspace_id, item_type
            )
            allowed_cache[item_type] = allowed
        for key, value in item["fields"].items():
            if not isinstance(key, str):
                raise ValidationError(
                    f"proposal item #{item_index}: field names must be strings"
                )
            if key in _RESERVED_PROPOSAL_FIELDS:
                raise ValidationError(
                    f"proposal item {item_type!r}: field {key!r} is server-owned "
                    "and cannot be set by an interview proposal"
                )
            if key not in allowed:
                raise ValidationError(
                    f"proposal item {item_type!r}: field {key!r} is not an allowed "
                    f"field for this artifact type"
                )
            _validate_proposal_field_value(item_type, key, value)

class InterviewMultiFormalizationMixin:
    """Multi-kind formalize path; mixed into :class:`InterviewService`."""

    def _formalize_multi(self, ctx, session, confirmed_proposal: list[dict]) -> dict[str, Any]:
        """Multi-kind path: create every confirmed-proposal item atomically.

        Each item is created through its production service method via
        ARTIFACT_CREATION_ADAPTERS (never a shortcut insert path, so
        workflow state initialization etc. stays correct). Provenance rows
        (InterviewSessionArtifact) and the proposal's trace links are written
        inside ONE transaction.atomic() block: a failure on any item rolls
        back the entire batch and leaves the session in_progress.

        'diagram-ref' links are rejected BEFORE that block, at the
        proposal-parse level: they are reconciler-owned
        (diagram.traceability_connector) and would be silently deleted on
        the next node_graph save -- creating them here can only produce
        unexplained data loss later.

        AI-005: ``validate_confirmed_proposal_fields`` also runs before the
        block and REJECTS (fail closed) any proposal field that is
        server-owned (``status``/``owner``/...), not an allowed field for the
        type, or an oversized string. Allowed names are derived from the
        production create_X() signatures plus the workspace's tenant-defined
        attribute definitions, so custom attributes keep working. Because the
        gate lives here in the service layer, an AUTHOR MCP caller supplying
        ``confirmed_proposal`` directly cannot bypass it.

        Staged into ``_reject_diagram_ref_links`` (pre-transaction gate),
        ``_create_proposal_items`` / ``_create_proposal_trace_links`` (the
        batch writes), ``_complete_multi_formalization_workflow`` (engine
        transition) and ``_record_multi_formalization`` (audit + event);
        the stage order and every side effect below are the original
        inline sequence.
        """
        if not confirmed_proposal:
            raise ValidationError("confirmed_proposal is required for a multi-mode interview")

        # Fail fast on malformed caller input BEFORE the transaction opens.
        # AI-005: field allowlist + type/length validation runs here, in the
        # service layer, so every transport (REST, UI, MCP) is protected and no
        # create_X() is reached with a reserved or oversized field.
        _validate_confirmed_proposal(confirmed_proposal)
        validate_confirmed_proposal_fields(ctx, session.workspace_id, confirmed_proposal)
        self._reject_diagram_ref_links(confirmed_proposal)

        with transaction.atomic():
            # Review finding M2 / M4: re-read the session under a row lock so two
            # concurrent formalize() calls cannot both pass the in_progress
            # guard above and commit duplicate batches (check-then-act race).
            # Delegates to the shared guard (the single owner of this
            # invariant) instead of repeating it inline — the inline copy was
            # byte-identical, error message included, and had already begun to
            # drift.
            session = self._lock_in_progress_session(session)

            created_refs = self._create_proposal_items(ctx, session, confirmed_proposal)
            self._create_proposal_trace_links(ctx, created_refs, confirmed_proposal)
            transition_applied = self._complete_multi_formalization_workflow(ctx, session)
            self._record_multi_formalization(ctx, session, created_refs, transition_applied)

        return {
            "created": [
                {"artifact_id": str(ref.artifact_id), "artifact_type": ref.artifact_type}
                for ref in created_refs
            ],
            "status": "completed",
        }

    @staticmethod
    def _reject_diagram_ref_links(confirmed_proposal: list[dict]) -> None:
        """Reject reconciler-owned ``diagram-ref`` links in a proposal.

        They are owned by the diagram reconciler
        (diagram.traceability_connector) and would be silently deleted on
        the next node_graph save -- creating them here can only produce
        unexplained data loss later. Runs before the transaction opens.
        """
        for item in confirmed_proposal:
            for link in item.get("links", []):
                if link.get("type") == _DIAGRAM_REF_LINK_TYPE:
                    raise ValidationError(
                        "invalid link type in proposal: 'diagram-ref' is system-managed "
                        "and cannot be created by an interview"
                    )

    @staticmethod
    def _create_proposal_items(ctx, session, confirmed_proposal: list[dict]) -> list:
        """Create every confirmed-proposal item via its production adapter.

        Each item is created through ARTIFACT_CREATION_ADAPTERS (never a
        shortcut insert path, so workflow state initialization etc. stays
        correct) and its provenance row (InterviewSessionArtifact) is
        written in the same transaction. Must run inside the caller's
        ``transaction.atomic()`` block: a failure on any item rolls back
        the entire batch and leaves the session in_progress.

        Malformed caller input surfaces as a clear ValidationError instead
        of KeyError/TypeError (review finding M1): missing required fields
        (e.g. Risk without probability/impact) raise KeyError, field names
        the target create_X() signature does not accept raise TypeError --
        both come straight from client JSON via confirmed_proposal, so
        neither may escape as an unhandled 500. Raised INSIDE the atomic
        block, so rollback semantics are unchanged -- the whole batch
        reverts.
        """
        from application.interview_artifact_adapters import ARTIFACT_CREATION_ADAPTERS

        created_refs = []
        for item in confirmed_proposal:
            adapter = ARTIFACT_CREATION_ADAPTERS.get(item["type"])
            if adapter is None:
                raise ValidationError(f"unknown artifact type in proposal: {item['type']!r}")
            try:
                ref = adapter(item["fields"], ctx, session.workspace_id)
            except (KeyError, TypeError) as exc:
                raise ValidationError(
                    f"invalid fields for {item['type']!r} in proposal item: {exc}"
                ) from exc
            InterviewSessionArtifact.objects.create(
                session=session, artifact_id=ref.artifact_id, artifact_type=ref.artifact_type
            )
            created_refs.append(ref)
        return created_refs

    @staticmethod
    def _create_proposal_trace_links(
        ctx, created_refs: list, confirmed_proposal: list[dict]
    ) -> None:
        """Create the proposal's trace links between the created artifacts.

        Links reference proposal items by index (``from``/``to``); the
        indices were range-checked by ``_validate_confirmed_proposal``
        before the transaction opened and resolve against *created_refs*.
        """
        from application.trace_link_service import TraceLinkService

        for item in confirmed_proposal:
            for link in item.get("links", []):
                source = created_refs[link["from"]]
                target = created_refs[link["to"]]
                TraceLinkService().create_trace_link(
                    source_id=source.artifact_id,
                    target_id=target.artifact_id,
                    link_type=link["type"],
                    ctx=ctx,
                )

    @staticmethod
    def _complete_multi_formalization_workflow(ctx, session) -> bool:
        """Workflow stage: best-effort transition to completed; report
        whether the engine actually moved (CR-07).

        Datenmodell-Konsolidierung Task 12: start() now registers a
        WorkflowItemState for multi-mode sessions too (same item_type
        "Interview" as single-mode), so this transitions through the
        engine exactly like _formalize_single -- the `status` column is
        dropped, so a direct column write is no longer possible, and is no
        longer the only record of completion. Same best-effort fallback as
        _lazily_abandon_if_stale/_write_single_artifact for a session whose
        init above failed (or predates this fix): the engine has nothing to
        transition, so completion is only reflected by the hardcoded
        "completed" in the caller's return value, not by a future
        state_reader lookup.

        CR-07: same "did it reach the engine?" tracking as
        _write_single_artifact -- the broad except below is a deliberate
        legacy-session fallback and must stay, but its effect has to stay
        legible (log level + audit detail flag).
        """
        from workflow.services import transition as workflow_transition

        transition_applied = True
        try:
            workflow_transition(
                item_id=session.id,
                target_state=InterviewSession.STATUS_COMPLETED,
                change_reason="Multi-mode interview formalized into real artifacts",
                ctx=ctx,
                item_type="Interview",
                workspace_id=session.workspace_id,
            )
        except Exception:
            transition_applied = False
            logger.warning(
                "InterviewService: workflow transition unavailable for "
                "multi-mode session=%s", session.id, exc_info=True
            )
        # Same optimistic-concurrency bump as _write_single_artifact.
        session.version = F("version") + 1
        session.save(update_fields=["modified_at", "version"])
        return transition_applied

    def _record_multi_formalization(
        self, ctx, session, created_refs: list, transition_applied: bool
    ) -> None:
        """Record stage: write the audit entry and the
        INTERVIEW_FORMALIZED event.

        Both run inside the caller's ``transaction.atomic()`` block (and,
        like the audit entry above, not merely inside _formalize_multi's
        caller) so the event is bound to the exact transaction that created
        the batch -- a rollback anywhere above (adapter/link failure) means
        these writes never run, so audit entry and outbox row can never
        disagree about whether the batch committed. Mirrors
        WorkflowFacade.transition's seam.
        """
        self._audit(
            ctx=ctx,
            operation="transition",
            entity_type="Interview",
            entity_id=session.id,
            change_reason="Multi-mode interview formalized into real artifacts",
            details={
                "session_kind": InterviewSession.SESSION_KIND_MULTI,
                "artifact_type": None,
                "resulting_artifact_ids": [
                    str(ref.artifact_id) for ref in created_refs
                ],
                "new_state": InterviewSession.STATUS_COMPLETED,
                "workflow_transition_applied": transition_applied,
            },
        )

        # Emitted inside this same atomic() block (and, like the audit
        # entry above, not merely inside _formalize_multi's caller) so
        # the event is bound to the exact transaction that created the
        # batch -- a rollback anywhere above (adapter/link failure) means
        # this line never runs.
        self._emit_event(
            self._make_event(
                event_type=DomainEventOutbox.EventType.INTERVIEW_FORMALIZED,
                entity_id=session.id,
                workspace_id=session.workspace_id,
                payload={
                    # m4: see the single-path payload — session_kind is the
                    # discriminator that makes single vs. multi readable
                    # from the event alone.
                    "session_kind": InterviewSession.SESSION_KIND_MULTI,
                    "artifact_type": None,
                    "created": [
                        {"artifact_id": str(ref.artifact_id), "artifact_type": ref.artifact_type}
                        for ref in created_refs
                    ],
                },
            )
        )
