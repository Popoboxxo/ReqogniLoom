"""COMP-AS-0xx GlossaryReferenceService — version-bound glossary references (#1266).

Markdown description fields (``Artifact`` descriptions, ADR context/decision,
…) may embed a stable **glossary reference token**::

    [[glossary:<global-uuid>]]           # head-following reference
    [[glossary:<global-uuid>@<revision>]] # version-pinned reference

``<global-uuid>`` is the term's stable global identity
(``GlossaryTerm.artifact_id`` — exposed on the wire as ``global_uuid`` since
#1261/#1270). It is the same id a TraceLink endpoint carries, so a reference is
directly addressable in the trace graph.

Version pinning
===============

The issue text proposes a bare ``[[glossary:<uuid>]]`` and states the UUID
"pins the version". That cannot literally hold: ``global_uuid`` is the
``Artifact`` primary key and is *identical for every revision* of a term (a new
revision is a new ``ArtifactVersion`` row, not a new Artifact). A token that
carries only the UUID therefore always resolves to **head**.

The pin is therefore carried explicitly as an ``@<revision>`` suffix. The
renderer resolves a pinned token against the snapshot stored for that revision,
and the workspace setting ``glossary_reference_mode`` decides what happens next:

* ``pinned`` (default) — the stored revision wins; a pinned revision that is
  older than head is reported as **drift** (``drift=True``), which is what the
  UI's "term was updated — raise the version?" hint is built on.
* ``always_head`` — the ``@<revision>`` suffix is ignored at *resolution* time
  and the current head is served; the token text is left untouched so switching
  the mode is non-destructive and reversible.

A bare token (no suffix) resolves to head in both modes.

Traceability
============

:meth:`GlossaryReferenceService.insert_reference` also writes the
usage trace link (``Artifact --uses-term--> GlossaryTerm``). The catalog is
tenant-extensible, so the link type is resolved per workspace: a tenant that
still has the historical ``uses-term`` key keeps using it; otherwise the modern
successor ``references`` (its ``("*", "GlossaryTerm")`` pair) is used. Both
carry the same meaning and make the usage visible in the trace graph.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from auth_tenancy.context import AuthContext
from link_types.builtin import GLOSSARY_TERM_LEGACY_LINK_TYPE
from persistence.models import ArtifactVersion, GlossaryTerm
from persistence.transactions import atomic_transaction

from application.base import NotFoundError, ServiceBase, ValidationError

logger = logging.getLogger(__name__)

#: The one reference grammar. The UUID group is the term's ``global_uuid``;
#: the optional ``@<digits>`` group is the pinned revision.
GLOSSARY_REFERENCE_PATTERN = re.compile(
    r"\[\[\s*glossary:"
    r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})"
    r"(?:@(\d+))?"
    r"\s*\]\]"
)

#: Valid ``glossary_reference_mode`` values (mirrors the Workspace model choices).
GLOSSARY_REFERENCE_MODES: frozenset[str] = frozenset({"pinned", "always_head"})
DEFAULT_GLOSSARY_REFERENCE_MODE = "pinned"

#: Modern catalog key whose ``("*", "GlossaryTerm")`` pair expresses a term use.
REFERENCE_LINK_TYPE = "references"

#: Historical key ``uses-term`` was absorbed into ``references`` by the
#: link-type consolidation (``link_types.builtin.LEGACY_LINK_TYPE_MAPPING``).
#: The catalog is tenant-extensible, so a workspace that re-added it keeps it.
#: The literal lives only in its sanctioned home (``link_types.builtin``); the
#: key is taken from that module's exported constant, never typed here.
PREFERRED_REFERENCE_LINK_TYPE = GLOSSARY_TERM_LEGACY_LINK_TYPE


@dataclass(frozen=True)
class ParsedReference:
    """One ``[[glossary:…]]`` token found in a text."""

    raw: str
    global_uuid: UUID
    revision: Optional[int]
    start: int
    end: int


@dataclass
class ResolvedReference:
    """A parsed reference resolved against the stored term history."""

    global_uuid: UUID
    requested_revision: Optional[int]
    resolved_revision: int
    head_revision: int
    term: str
    definition: str
    resolved: bool
    drift: bool
    mode: str


def parse_references(text: Optional[str]) -> List[ParsedReference]:
    """Return every glossary reference token in *text*, in document order.

    Pure function — no DB access — so the grammar is testable in isolation and
    the same parser backs both the resolver and the bulk-upgrade rewriter.
    """
    if not text:
        return []
    parsed: List[ParsedReference] = []
    for match in GLOSSARY_REFERENCE_PATTERN.finditer(text):
        parsed.append(
            ParsedReference(
                raw=match.group(0),
                global_uuid=UUID(match.group(1)),
                revision=int(match.group(2)) if match.group(2) else None,
                start=match.start(),
                end=match.end(),
            )
        )
    return parsed


def build_reference_token(global_uuid: UUID | str, revision: Optional[int] = None) -> str:
    """Render the canonical token text for *global_uuid* (and optional revision)."""
    uid = str(global_uuid)
    if revision is None:
        return f"[[glossary:{uid}]]"
    return f"[[glossary:{uid}@{int(revision)}]]"


class GlossaryReferenceService(ServiceBase):
    """Resolve / insert / upgrade glossary references (#1266)."""

    # ---------- workspace configuration ----------

    def reference_mode(self, ctx: AuthContext, workspace_id: UUID) -> str:
        """Return the workspace's ``glossary_reference_mode`` (default ``pinned``)."""
        from persistence.models import Workspace

        self._set_tenant_context(ctx)
        mode = (
            Workspace.objects.filter(id=workspace_id)
            .values_list("glossary_reference_mode", flat=True)
            .first()
        )
        return mode if mode in GLOSSARY_REFERENCE_MODES else DEFAULT_GLOSSARY_REFERENCE_MODE

    # ---------- resolution ----------

    def resolve_references(
        self, ctx: AuthContext, workspace_id: UUID, text: Optional[str]
    ) -> Tuple[str, List[ResolvedReference]]:
        """Resolve every token in *text* against the pinned revision or head.

        Returns ``(mode, resolutions)`` where *resolutions* holds one entry per
        **distinct** ``(global_uuid, revision)`` pair — a token repeated in a
        text is resolved once, so the renderer can build a lookup map without
        re-querying.
        """
        self._set_tenant_context(ctx)
        parsed = parse_references(text)
        if not parsed:
            return self.reference_mode(ctx, workspace_id), []

        mode = self.reference_mode(ctx, workspace_id)
        seen: set[Tuple[UUID, Optional[int]]] = set()
        resolutions: List[ResolvedReference] = []
        for ref in parsed:
            key = (ref.global_uuid, ref.revision)
            if key in seen:
                continue
            seen.add(key)
            resolutions.append(self._resolve_one(workspace_id, ref, mode))
        return mode, resolutions

    def _resolve_one(
        self, workspace_id: UUID, ref: ParsedReference, mode: str
    ) -> ResolvedReference:
        term = GlossaryTerm.objects.filter(artifact_id=ref.global_uuid).first()
        if term is None:
            # Unknown/foreign/legacy (no backing Artifact) — surfaced as an
            # unresolved reference so the renderer can flag it instead of
            # silently dropping the token text.
            return ResolvedReference(
                global_uuid=ref.global_uuid,
                requested_revision=ref.revision,
                resolved_revision=ref.revision or 0,
                head_revision=0,
                term="",
                definition="",
                resolved=False,
                drift=False,
                mode=mode,
            )

        head_revision = int(term.version or 1)
        if mode == "always_head" or ref.revision is None:
            resolved_revision = head_revision
        else:
            resolved_revision = ref.revision

        definition = self._definition_at(term, resolved_revision, head_revision)
        return ResolvedReference(
            global_uuid=ref.global_uuid,
            requested_revision=ref.revision,
            resolved_revision=resolved_revision,
            head_revision=head_revision,
            term=term.term,
            definition=definition,
            resolved=True,
            # Drift is never reported in always_head mode — the workspace has
            # explicitly opted out of pinning there.
            drift=(
                mode == "pinned"
                and ref.revision is not None
                and ref.revision < head_revision
            ),
            mode=mode,
        )

    @staticmethod
    def _definition_at(term: GlossaryTerm, revision: int, head_revision: int) -> str:
        """Definition of *term* at *revision*, falling back to the live row.

        The snapshot is the authoritative source (that is the point of pinning);
        the live row is the fallback for a term whose snapshot predates the
        field or whose requested revision has no stored row.
        """
        if revision == head_revision:
            # Cheapest correct answer — the live row *is* the head snapshot.
            return term.definition
        payload = (
            ArtifactVersion.objects.filter(
                artifact_id=term.artifact_id, revision=revision
            )
            .values_list("payload", flat=True)
            .first()
        )
        if isinstance(payload, dict):
            definition = payload.get("definition")
            if isinstance(definition, str):
                return definition
        return term.definition

    # ---------- insertion (+ usage trace link) ----------

    @atomic_transaction
    def insert_reference(
        self,
        ctx: AuthContext,
        workspace_id: UUID,
        source_artifact_id: UUID,
        global_uuid: UUID,
    ) -> Dict[str, Any]:
        """Create the usage trace link and return the token + resolved term.

        Pinned by default: the returned ``token`` carries the term's current
        ``@<revision>``. In ``always_head`` mode a bare token is returned, so
        the text does not claim a pin the workspace will not honour.

        Raises:
            NotFoundError: no term with that ``global_uuid`` in this workspace.
            ValidationError: the source artifact or the usage link is rejected
                by the workspace's link-type catalog.
        """
        self._set_tenant_context(ctx)
        term = GlossaryTerm.objects.filter(
            artifact_id=global_uuid, workspace_id=workspace_id
        ).first()
        if term is None:
            raise NotFoundError(f"Glossary term {global_uuid} not found.")

        link_type = self.reference_link_type(workspace_id)
        self._ensure_reference_link(
            ctx, link_type, source_artifact_id, term.artifact_id
        )

        mode = self.reference_mode(ctx, workspace_id)
        head_revision = int(term.version or 1)
        token = (
            build_reference_token(global_uuid)
            if mode == "always_head"
            else build_reference_token(global_uuid, head_revision)
        )
        return {
            "token": token,
            "global_uuid": str(global_uuid),
            "term": term.term,
            "definition": term.definition,
            "version": head_revision,
            "link_type": link_type,
            "mode": mode,
        }

    def reference_link_type(self, workspace_id: UUID) -> str:
        """Resolve the link type used for a term usage in *workspace_id*.

        The tenant catalog wins: ``uses-term`` when the workspace still carries
        it, ``references`` (its catalog successor) otherwise.
        """
        from link_types.catalog import get_definition

        if get_definition(workspace_id, PREFERRED_REFERENCE_LINK_TYPE) is not None:
            return PREFERRED_REFERENCE_LINK_TYPE
        return REFERENCE_LINK_TYPE

    def _ensure_reference_link(
        self,
        ctx: AuthContext,
        link_type: str,
        source_artifact_id: UUID,
        target_artifact_id: UUID,
    ) -> None:
        """Write the usage link, tolerating an already-existing edge.

        A duplicate is not an error here: a description may reference the same
        term twice, and re-inserting after an edit must not fail the save. The
        edge is unique per ``(source, target, link_type)``
        (``uq_tracelink_edge``), so "already exists" means the traceability
        goal — the usage is visible in the trace graph — is already met.
        """
        from application.trace_link_service import TraceLinkService

        try:
            TraceLinkService().create_trace_link(
                source_id=source_artifact_id,
                target_id=target_artifact_id,
                link_type=link_type,
                ctx=ctx,
                rationale="glossary reference inserted in a text field (#1266)",
            )
        except ValidationError as exc:
            if "already exists" in str(exc):
                return
            raise

    # ---------- bulk upgrade to head ----------

    def upgrade_text_to_head(
        self, ctx: AuthContext, workspace_id: UUID, text: Optional[str]
    ) -> Tuple[str, int]:
        """Rewrite every pinned token in *text* to the term's current head.

        Bare tokens and tokens whose term is unknown are left untouched. Returns
        ``(new_text, upgraded_count)``.
        """
        self._set_tenant_context(ctx)
        parsed = parse_references(text)
        if not parsed or text is None:
            return text or "", 0

        cache: Dict[UUID, Optional[int]] = {}
        out = text
        upgraded = 0
        # Replace right-to-left so earlier match offsets stay valid.
        for ref in reversed(parsed):
            if ref.revision is None:
                continue
            if ref.global_uuid not in cache:
                cache[ref.global_uuid] = (
                    GlossaryTerm.objects.filter(artifact_id=ref.global_uuid)
                    .values_list("version", flat=True)
                    .first()
                )
            head = cache[ref.global_uuid]
            if head is None or head == ref.revision:
                continue
            out = out[: ref.start] + build_reference_token(ref.global_uuid, head) + out[ref.end :]
            upgraded += 1
        return out, upgraded

    # ---------- render helper ----------

    def resolve_text(
        self, ctx: AuthContext, workspace_id: UUID, text: Optional[str]
    ) -> Dict[str, Any]:
        """Resolve *text* and report the drift summary the UI needs.

        The renderer keeps the original text and swaps each token for a
        highlighted mark; this payload is what it renders inside the tooltip.
        """
        mode, resolutions = self.resolve_references(ctx, workspace_id, text)
        return {
            "mode": mode,
            "has_drift": any(r.drift for r in resolutions),
            "references": [
                {
                    "global_uuid": str(r.global_uuid),
                    "requested_revision": r.requested_revision,
                    "resolved_revision": r.resolved_revision,
                    "head_revision": r.head_revision,
                    "term": r.term,
                    "definition": r.definition,
                    "resolved": r.resolved,
                    "drift": r.drift,
                }
                for r in resolutions
            ],
        }


__all__ = [
    "DEFAULT_GLOSSARY_REFERENCE_MODE",
    "GLOSSARY_REFERENCE_MODES",
    "GLOSSARY_REFERENCE_PATTERN",
    "PREFERRED_REFERENCE_LINK_TYPE",
    "REFERENCE_LINK_TYPE",
    "GlossaryReferenceService",
    "ParsedReference",
    "ResolvedReference",
    "build_reference_token",
    "parse_references",
]
