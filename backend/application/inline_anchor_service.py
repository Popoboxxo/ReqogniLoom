"""COMP-AS-024 InlineAnchorService — inline-reference anchors (Plan F F3-T7).

leaf_id : COMP-AS-024
req_id  : REQ-L2-PL-004, REQ-L2-PL-010

The *content side* of an inline reference. The stored markdown keeps the
existing glossary token (ENT-F3 = a)::

    [[glossary:<global-uuid>]]
    [[glossary:<global-uuid>@<revision>]]

The display form ``[[Begriff]]`` is an editor concern and is **never** stored.
For every token in a markdown field this service keeps one ``InlineAnchor`` row
that records the source Artifact, the field and the TraceLink the token
implies. Anchors and edges are synchronised in the service write path, which is
the only entry point for a document/work-item edit (ADR-01):

* **I-1** — a token creates its trace edge automatically.
* **I-2** — removing the last token of an edge removes the edge (unless another
  anchor still references it).
* **I-3** — deleting an edge through the API first answers ``409
  ANCHORS_PRESENT`` with the affected count; the confirmed retry removes the
  anchors and the link (``TraceLinkService.delete_trace_link``).
* **I-4** — an edge without anchors stays valid and is not touched by a sync
  (the service never deletes an edge it did not orphan).
* **I-5** — a soft-deleted/archived target keeps its anchor; ``DOC-P7`` reports
  it as a dead reference, the projection renders plain text plus a warning.

Grammar is deliberately **fail-closed**: a ``[[…]]`` span that is not a valid
glossary token is rejected at the service boundary instead of being silently
ignored. Storing two syntaxes in one field would make the register ambiguous
(ENT-F3 = a, R6).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from application.base import NotFoundError, ServiceBase, ValidationError
from application.glossary_reference_service import (
    GLOSSARY_REFERENCE_PATTERN,
    GlossaryReferenceService,
    parse_references,
)
from auth_tenancy.context import AuthContext
from persistence.models import Artifact, InlineAnchor, TraceLink
from persistence.transactions import atomic_transaction

logger = logging.getLogger(__name__)

#: The markdown fields the current write paths synchronise.
ANCHOR_FIELD_BODY = "body"
ANCHOR_FIELD_DESCRIPTION = "description"

#: Any closed ``[[…]]`` span. Used only for the fail-closed grammar gate; the
#: authoritative token grammar is ``GLOSSARY_REFERENCE_PATTERN``.
_BRACKET_SPAN_PATTERN = re.compile(r"\[\[[^\[\]]*\]\]")

#: Rationale recorded on an edge created by an anchor.
ANCHOR_LINK_RATIONALE = "inline reference anchor (#1374)"


@dataclass(frozen=True)
class ResolvedAnchor:
    """One token resolved for the projection/render layer."""

    token: str
    global_uuid: UUID
    revision: int | None
    resolved: bool
    dead: bool


def assert_storable_grammar(text: str | None, field: str) -> None:
    """Reject a ``[[…]]`` span that is not a glossary token (fail-closed).

    ``[[Begriff]]`` is valid *editor* input, but ENT-F3 = a keeps the stored
    form as the glossary token only. Accepting both would create two
    grammars — and the anchor register stores the token text, so the resolver
    could no longer tell which form it is looking at.

    Raises:
        ValidationError: a closed bracket span is not a valid glossary token.
    """
    if not text:
        return
    for match in _BRACKET_SPAN_PATTERN.finditer(text):
        span = match.group(0)
        if GLOSSARY_REFERENCE_PATTERN.fullmatch(span):
            continue
        raise ValidationError(
            f"{field} contains an inline reference with unsupported grammar: "
            f"{span!r}. Only the stored glossary token form "
            "[[glossary:<uuid>@<revision>]] is supported."
        )


class InlineAnchorService(ServiceBase):
    """Keep inline anchors and their trace edges in sync (F3-T7)."""

    # ---------- Synchronisation (I-1 / I-2) ----------

    @atomic_transaction
    def sync_text(
        self,
        ctx: AuthContext,
        source_artifact_id: UUID | str,
        field: str,
        text: str | None,
    ) -> list[InlineAnchor]:
        """Synchronise the anchors of one markdown field.

        The field's current anchors become exactly the tokens present in
        ``text``: missing anchors are created with their edge (I-1) and anchors
        whose token disappeared are removed. An edge is then removed only if no
        anchor anywhere still references it (I-2) — an edge without anchors
        (I-4) is never touched because it never had an anchor to remove.

        Args:
            ctx: Resolved AuthContext.
            source_artifact_id: Artifact owning the markdown field.
            field: Field name (``body``/``description``).
            text: Current markdown; ``None`` is treated as empty.

        Returns:
            The field's anchors after the sync, ordered by token.

        Raises:
            NotFoundError: The source artifact does not exist in this tenant.
            ValidationError: The text carries an unsupported ``[[…]]`` grammar.
        """
        self._set_tenant_context(ctx)
        source_id = UUID(str(source_artifact_id))
        artifact = Artifact.objects.filter(
            id=source_id, tenant_id=ctx.tenant_id
        ).first()
        if artifact is None:
            raise NotFoundError(f"Artifact {source_artifact_id} not found")

        assert_storable_grammar(text, field)
        parsed = parse_references(text)
        desired: dict[str, UUID] = {}
        for ref in parsed:
            desired.setdefault(ref.raw, ref.global_uuid)

        existing = {
            anchor.token: anchor
            for anchor in InlineAnchor.objects.filter(
                source_artifact_id=artifact.id,
                field=field,
                tenant_id=ctx.tenant_id,
            )
        }

        orphaned_link_ids: set[UUID] = set()
        for token, anchor in existing.items():
            if token in desired:
                continue
            orphaned_link_ids.add(anchor.link_id)
            anchor.delete()

        for token, global_uuid in desired.items():
            if token in existing:
                continue
            link = self._ensure_link(ctx, artifact, global_uuid)
            InlineAnchor.objects.create(
                tenant_id=ctx.tenant_id,
                source_artifact=artifact,
                field=field,
                target_artifact_id=global_uuid,
                link=link,
                token=token,
            )

        # After all creations/deletions of this field, drop edges that no
        # anchor references any more. Checking the *whole* register (not just
        # this document) is the safe reading of I-2: a link shared by another
        # document's anchor must stay.
        for link_id in sorted(orphaned_link_ids):
            self._delete_link_if_unreferenced(ctx, link_id)

        return list(
            InlineAnchor.objects.filter(
                source_artifact_id=artifact.id,
                field=field,
                tenant_id=ctx.tenant_id,
            ).order_by("token")
        )

    def sync_document(self, ctx: AuthContext, document: Any) -> None:
        """Synchronise the two markdown fields of a ``Document``."""
        self.sync_text(
            ctx,
            document.artifact_id,
            ANCHOR_FIELD_DESCRIPTION,
            getattr(document, "description", "") or "",
        )
        self.sync_text(
            ctx,
            document.artifact_id,
            ANCHOR_FIELD_BODY,
            getattr(document, "body", "") or "",
        )

    def sync_work_item(self, ctx: AuthContext, item: Any) -> None:
        """Synchronise the markdown body of a ``WorkItem``."""
        self.sync_text(
            ctx,
            item.artifact_id,
            ANCHOR_FIELD_BODY,
            getattr(item, "body", "") or "",
        )

    def _ensure_link(
        self, ctx: AuthContext, source: Artifact, target_artifact_id: UUID
    ) -> TraceLink:
        """Return the existing edge for the token, creating it when absent."""
        target = Artifact.objects.filter(
            id=target_artifact_id, tenant_id=ctx.tenant_id
        ).first()
        if target is None:
            raise NotFoundError(
                f"Referenced artifact {target_artifact_id} not found"
            )

        link_type = GlossaryReferenceService().reference_link_type(
            source.workspace_id
        )
        existing = TraceLink.objects.filter(
            source_id=source.id,
            target_id=target.id,
            link_type=link_type,
        ).first()
        if existing is not None:
            return existing

        from application.trace_link_service import TraceLinkService

        return TraceLinkService().create_trace_link(
            source_id=source.id,
            target_id=target.id,
            link_type=link_type,
            ctx=ctx,
            rationale=ANCHOR_LINK_RATIONALE,
        )

    @staticmethod
    def _delete_link_if_unreferenced(ctx: AuthContext, link_id: UUID) -> bool:
        """Delete *link_id* when no anchor references it any more (I-2).

        Uses the trace manager directly rather than
        ``TraceLinkService.delete_trace_link``: that public path is the user's
        I-3 delete and carries the anchor-confirmation gate plus the
        agent-proposal guard. This is the internal consequence of the last
        anchor disappearing, not a user DELETE, so it must not ask for a
        confirmation it just produced. No new event is emitted (F3-T7 scope;
        ``ITEM_*``/anchor events are F3-T8).
        """
        if InlineAnchor.objects.filter(link_id=link_id).exists():
            return False
        from traceability.trace_link_manager import TraceLinkManager

        try:
            TraceLinkManager().delete(link_id)
        except TraceLink.DoesNotExist:
            return False
        return True

    # ---------- Resolution / inspection ----------

    def list_anchors(
        self,
        ctx: AuthContext,
        source_artifact_id: UUID | str,
        *,
        field: str | None = None,
    ) -> list[InlineAnchor]:
        """Return the anchors of one source artifact, deterministically ordered."""
        self._set_tenant_context(ctx)
        queryset = InlineAnchor.objects.filter(
            source_artifact_id=UUID(str(source_artifact_id)),
            tenant_id=ctx.tenant_id,
        )
        if field is not None:
            queryset = queryset.filter(field=field)
        return list(queryset.order_by("field", "token"))

    def resolve_text(
        self, ctx: AuthContext, workspace_id: UUID, text: str | None
    ) -> dict[str, Any]:
        """Resolve every token in *text* and flag dead targets (I-5).

        Resolution of the glossary term/definition itself belongs to
        :class:`GlossaryReferenceService`; this method adds the anchor axis:
        whether the target artifact still exists in an active state. A token
        whose target was soft-deleted or whose term is in an
        outdated-equivalent workflow state is rendered as plain text plus a
        warning by the projection (``DOC-P7``).
        """
        self._set_tenant_context(ctx)
        mode, resolutions = GlossaryReferenceService().resolve_references(
            ctx, workspace_id, text
        )
        by_uuid = {resolution.global_uuid: resolution for resolution in resolutions}
        resolved: list[ResolvedAnchor] = []
        for ref in parse_references(text):
            resolution = by_uuid.get(ref.global_uuid)
            dead = self._target_is_dead(ctx, ref.global_uuid)
            resolved.append(
                ResolvedAnchor(
                    token=ref.raw,
                    global_uuid=ref.global_uuid,
                    revision=ref.revision,
                    resolved=bool(resolution and resolution.resolved),
                    dead=dead,
                )
            )
        return {
            "mode": mode,
            "has_dead_reference": any(entry.dead for entry in resolved),
            "anchors": [
                {
                    "token": entry.token,
                    "global_uuid": str(entry.global_uuid),
                    "revision": entry.revision,
                    "resolved": entry.resolved,
                    "dead": entry.dead,
                }
                for entry in resolved
            ],
        }

    @staticmethod
    def _target_is_dead(ctx: AuthContext, target_artifact_id: UUID) -> bool:
        """Whether the referenced artifact is soft-deleted or archived."""
        from workflow.services import get_workflow_json
        from workflow.definition_store import get_state_meta
        from workflow import state_reader

        artifact = Artifact.objects.filter(
            id=target_artifact_id, tenant_id=ctx.tenant_id
        ).first()
        if artifact is None:
            return True
        if artifact.lifecycle_status != "active":
            return True

        # The supported grammar targets GlossaryTerms; resolve the entity row
        # (WorkflowItemState is keyed by entity id, not Artifact id).
        from persistence.models import GlossaryTerm

        term = GlossaryTerm.objects.filter(
            artifact_id=artifact.id, tenant_id=ctx.tenant_id
        ).first()
        if term is None:
            return False
        state = state_reader.current_states(
            "GlossaryTerm", [term.id], tenant_id=ctx.tenant_id
        ).get(str(term.id))
        if state is None:
            return False
        workflow_json = get_workflow_json(term.workspace_id, "GlossaryTerm") or {}
        return bool(get_state_meta(workflow_json, state).get("is_outdated_equivalent"))


__all__ = [
    "ANCHOR_FIELD_BODY",
    "ANCHOR_FIELD_DESCRIPTION",
    "ANCHOR_LINK_RATIONALE",
    "InlineAnchorService",
    "ResolvedAnchor",
    "assert_storable_grammar",
]
