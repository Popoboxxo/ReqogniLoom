"""Generator: ``shares-term`` — REQ-L1-044 glossary co-occurrence (Task 5).

**Deviation from the 2026-08-07 implementation plan, documented here because
it changes the generator's data source:** the plan's primary approach was to
reuse existing ``uses-term`` TraceLinks between artifacts and
``GlossaryTerm`` rows. Verified against the current codebase (2026-08-19):
``LinkType.USES_TERM`` is declared in ``traceability/types.py`` but no
service ever creates a ``uses-term`` TraceLink, and ``GlossaryTerm`` has no
``Artifact``-backing relation at all (unlike Requirement/ArchitectureElement/
etc., it is absent from ``TraceLinkService._resolve_artifact``'s resolution
chain) — it cannot even be a TraceLink endpoint today. There is no data to
query. The plan's own documented fallback is used instead: literal
title-text matching against ``GlossaryTerm.term``/``.synonyms``.

Deterministic, no LLM, no embeddings — confidence is always ``1.0``.

Undirected-pair storage: two artifacts sharing a term produce exactly ONE
``ContextEdge`` row (not two), because ``ContextEdge``'s unique constraint is
``(source, target, edge_kind, origin)`` and a symmetric relationship stored
as two directed rows would double-write and complicate the projector's
per-artifact stale-cleanup (Task 4 step 5). The pair is canonicalised by
sorting the two artifact ids so the same row is produced regardless of which
artifact of the pair triggered (re-)generation.
"""
from __future__ import annotations

import re
from typing import Dict, List
from uuid import UUID

from context_graph.types import ContextEdgeCandidate

GENERATOR_NAME = "glossary-v1"
EDGE_KIND = "shares-term"
ORIGIN = "derived-glossary"

# Requirement/ArchitectureElement/StakeholderNeed/TestCase are OneToOne on
# Artifact and carry ``title`` directly (mirrors traceability/service.py's
# ``_enrich`` domain_models tuple). Adr lives in application.models and is
# looked up separately, same as ``_enrich``.
_PERSISTENCE_TITLE_MODELS = ("Requirement", "ArchitectureElement", "StakeholderNeed", "TestCase")


def _title_for_artifact(artifact_id: UUID) -> str:
    """Return the human-readable title for *artifact_id*, or "" if none.

    Small, self-contained lookup rather than importing
    ``traceability.service._enrich`` (module-private, and built for batch
    enrichment of many ids at once — this generator only ever needs one).
    """
    from persistence import models as pm

    for model_name in _PERSISTENCE_TITLE_MODELS:
        model = getattr(pm, model_name)
        row = model.objects.filter(artifact_id=artifact_id).values("title").first()
        if row is not None:
            return row["title"] or ""

    try:
        from application.models import Adr

        row = Adr.objects.filter(artifact_id=artifact_id).values("title").first()
        if row is not None:
            return row["title"] or ""
    except Exception:  # noqa: BLE001 — Adr model absent in some test configs
        pass

    return ""


def _title_lookup_for_workspace(workspace_id: UUID, exclude_artifact_id: UUID) -> Dict[UUID, str]:
    """Return {artifact_id: title} for every other titled artifact in the workspace."""
    from persistence import models as pm

    titles: Dict[UUID, str] = {}
    for model_name in _PERSISTENCE_TITLE_MODELS:
        model = getattr(pm, model_name)
        for row in (
            model.objects.filter(artifact__workspace_id=workspace_id)
            .exclude(artifact_id=exclude_artifact_id)
            .values("artifact_id", "title")
        ):
            if row["title"]:
                titles[row["artifact_id"]] = row["title"]

    try:
        from application.models import Adr

        for row in (
            Adr.objects.filter(artifact__workspace_id=workspace_id)
            .exclude(artifact_id=exclude_artifact_id)
            .values("artifact_id", "title")
        ):
            if row["title"]:
                titles[row["artifact_id"]] = row["title"]
    except Exception:  # noqa: BLE001 — Adr model absent in some test configs
        pass

    return titles


def _term_pattern(term_text: str) -> "re.Pattern[str]":
    """Whole-word, case-insensitive match for a single term/synonym string."""
    return re.compile(r"\b" + re.escape(term_text.strip()) + r"\b", re.IGNORECASE)


def generate_for_artifact(artifact_id: UUID) -> List[ContextEdgeCandidate]:
    """Return the full, current set of ``shares-term`` candidates for *artifact_id*.

    Full recomputation, not an incremental delta — required for the
    projector's replay-safe upsert design (Task 4). Pure DB queries, no
    network/LLM calls (Global Constraints: this runs on the latency-sensitive
    outbox ``events`` queue).
    """
    from persistence.models import Artifact, GlossaryTerm

    artifact = Artifact.objects.filter(id=artifact_id).only("id", "workspace_id").first()
    if artifact is None:
        return []

    title = _title_for_artifact(artifact_id)
    if not title:
        return []

    terms = list(
        GlossaryTerm.objects.filter(workspace_id=artifact.workspace_id).values(
            "id", "term", "synonyms"
        )
    )
    if not terms:
        return []

    matched_terms: List[dict] = []
    for term in terms:
        candidates_text = [term["term"], *(term["synonyms"] or [])]
        if any(_term_pattern(t).search(title) for t in candidates_text if t):
            matched_terms.append(term)

    if not matched_terms:
        return []

    other_titles = _title_lookup_for_workspace(artifact.workspace_id, exclude_artifact_id=artifact_id)
    if not other_titles:
        return []

    # other_artifact_id -> [{"term_id":..., "term_name":...}, ...] (Task 5:
    # "evidence must contain enough information for a human to verify the
    # claim by inspection — the term name, not just its id").
    shared: Dict[UUID, List[dict]] = {}
    for term in matched_terms:
        candidates_text = [term["term"], *(term["synonyms"] or [])]
        patterns = [_term_pattern(t) for t in candidates_text if t]
        for other_id, other_title in other_titles.items():
            if any(p.search(other_title) for p in patterns):
                shared.setdefault(other_id, []).append(
                    {"term_id": str(term["id"]), "term_name": term["term"]}
                )

    result: List[ContextEdgeCandidate] = []
    for other_id, term_hits in shared.items():
        # Canonicalise the unordered pair: same row regardless of which of
        # the two artifacts triggered (re-)generation.
        source_id, target_id = sorted((artifact_id, other_id), key=str)
        result.append(
            ContextEdgeCandidate(
                source_id=source_id,
                target_id=target_id,
                edge_kind=EDGE_KIND,
                origin=ORIGIN,
                confidence=1.0,
                generator=GENERATOR_NAME,
                evidence={"terms": term_hits},
            )
        )
    return result


__all__ = ["generate_for_artifact", "GENERATOR_NAME", "EDGE_KIND", "ORIGIN"]
