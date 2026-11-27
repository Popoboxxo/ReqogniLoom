"""
COMP-AS-010 SearchService — PostgreSQL Full-Text Search.

leaf_id : COMP-AS-010
req_id  : REQ-L1-020, REQ-L3-SEARCH-001 through REQ-L3-SEARCH-009

Search over every artifact type listed in ``SEARCHABLE_ARTIFACT_TYPES``
(Requirement, ArchitectureElement, TestCase, StakeholderNeed, Adr, Risk,
Issue, ChangeRequest, Goal, GlossaryTerm, Icd, Document, WorkItem, TraceLink).
Two passes run per type and are merged (issue #345):

  1. full-text: PostgreSQL tsvector / tsquery, relevance-ranked via ts_rank
  2. lexical:   case-insensitive substring match on title, uid and IDs

Pass 2 exists because ``plainto_tsquery`` lexemizes its input, so literal
identifiers ("QA-AI", "00436a35") were previously unfindable. Lexical hits
always rank above full-text hits. Both passes enforce workspace and tenant
isolation. Supports type filtering, pagination, and safe query parsing.

Task 9 (REQ-L2-VS-004) adds a third, cosine-similarity pass over the
``embedding`` column of the entity types that have one (Requirement, TraceLink,
Icd — see ``_EMBEDDABLE_TYPES``/``_TABLE_SPECS``). When that pass contributes
a hit for a given entity type, all three passes are combined via Reciprocal
Rank Fusion (``_rrf_fuse``) instead of the plain max-score merge
(``_merge_hits``) — see ``SearchService._search_entity_type``'s docstring for
the fusion rule.

T-A3-2 (A-L21) pins an *exact* identifier hit (exact title, exact uid/ID) above
that fused list with ``relevance_score == 1.0``, so typing a readable ID ranks
that artifact first whenever RRF fusion is the algorithm in play. The pin is
carried by the internal ``SearchHit.pinned`` marker and resolved by the global
sort key — the score alone cannot express it, because RRF's own normalization
lets an unpinned hit reach 1.0 as well. T-A3-3 additionally checks every
TraceLink/Icd hit for item-level READ and masks a TraceLink target across
workspace boundaries (``_apply_row_visibility``).

Every ``SearchHit.relevance_score`` is normalized to the closed interval
``[0.0, 1.0]`` at the point of score creation (issue #827). The four native
scales — cosine similarity, ``ts_rank``, the lexical CASE tiers, and the RRF
fused score — are each mapped by a monotone transform (see
:func:`_normalize_cosine_similarity`, :func:`_normalize_fulltext_score`,
:func:`_normalize_lexical_score`, and :func:`_rrf_fuse`), so the normalized
values are bounded and comparable without changing any ranking: a higher raw
score never maps to a lower normalized score.

Interface contracts implemented:
  IF-AS-EXT-IN-001  — inbound: search(query, ...) → SearchResult
  IF-AS-EXT-OUT-007 — outbound: raw SQL via Django connection (tsvector queries)

Architecture:
  docs/se/L1/Gesamtsystem/L2/ApplicationServiceSystem/Components/
    COMP-AS-010_SearchService/

Note on tsvector columns:
  The persistence migration creates GIN indexes on
  to_tsvector('german', title || ' ' || description) for Requirement,
  ArchitectureElement, and TestCase. These are expression indexes — we reference
  the same expression in the WHERE clause rather than a stored column.
"""
from __future__ import annotations

import logging
import os
import re
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from dataclasses import replace as dataclass_replace
from typing import Any
from uuid import UUID

from django.db.models import F

from auth_tenancy.context import AuthContext

# Backward-compat alias used by tests that patch 'application.search_service.TenantContext'
TenantContext = AuthContext

from application.base import ServiceBase, ValidationError
from application.vector_port import (
    DEGRADED_CROSS_TYPE_QUERY_FAILED,
    TypedVectorHit,
    VectorHit,
    get_fallback_vector_port,
    hydrate_vector_hits,
    mark_request_degraded,
    serves_from_fallback,
)
from llm_adapter.embedding_service import generate_embedding
from persistence.custom_fields import coerce_custom_fields
from persistence.models import Requirement, TraceLink

logger = logging.getLogger(__name__)

# ---------- Constants ----------

_DEFAULT_PAGE = 1
_DEFAULT_LIMIT = 20
_MAX_LIMIT = 100

# #345 Finding 2: a lexical hit always outranks a full-text hit. ts_rank()
# with default weights stays well below 1.0 in practice (the QA report saw
# 0.06 for a semantic match), so the lexical tiers below deliberately span a
# scale wider than ts_rank's practical range: "the title literally contains
# what you typed" is a strictly stronger signal than any tsvector score. The
# raw tiers are normalized to [0, 1] before they leave this module (issue
# #827, see :func:`_normalize_lexical_score`); dividing by the scale maximum
# preserves their strict relative ordering.
_SCORE_TITLE_EXACT = 3.0
_SCORE_ID_EXACT = 2.9
_SCORE_TITLE_PREFIX = 2.5
_SCORE_TITLE_SUBSTRING = 2.0
_SCORE_ID_SUBSTRING = 1.5

#: Maximum raw lexical tier — the divisor that maps the lexical scale onto
#: [0, 1] (issue #827). Derived from the tier constants so it can never drift
#: out of sync with them.
_SCORE_MAX = max(
    _SCORE_TITLE_EXACT,
    _SCORE_ID_EXACT,
    _SCORE_TITLE_PREFIX,
    _SCORE_TITLE_SUBSTRING,
    _SCORE_ID_SUBSTRING,
)

# A single character would substring-match nearly every row; below this the
# lexical pass is skipped and only the full-text pass runs.
_MIN_LEXICAL_QUERY_LEN = 2

# The lexical pass has no supporting index (ILIKE '%x%' cannot use the FTS
# GIN index), so a very generic needle could otherwise stream a whole table
# into memory. Capping per type bounds the cost; the full-text pass — the
# relevance-ranked one — is uncapped for the non-``permission_scoped`` types
# and capped for TraceLink/Icd (see :func:`_run_fulltext_query`).
_MAX_LEXICAL_ROWS_PER_TYPE = 200

# ---------- Semantic pass (Task 9, REQ-L2-VS-004) ----------
#
# Entity types that carry an ``embedding`` VectorField. Since T-A3-3 all three
# are also fulltext/lexical searchable and therefore part of the public
# `type_filter` enum: TraceLink and Icd got their own _TableSpec entries (see
# _TABLE_SPECS). A TraceLink has no title of its own, so its synthetic
# "<link_type>: <source uid> → <target uid>" title is composed after the SQL
# passes in _apply_row_visibility, which also owns that type's endpoint
# permission masking.
#
# Task 28c-2: "IcdVersion" became "Icd" — the embedding moved onto the ICD
# header when the version table was retired, along with its HNSW index
# (icd_version_embedding_hnsw -> icd_embedding_hnsw).
_EMBEDDABLE_TYPES: frozenset[str] = frozenset({"Requirement", "TraceLink", "Icd"})

# Standard RRF constant (see e.g. Cormack et al. 2009) — large enough that a
# rank-1 hit in one list and a rank-1 hit in another contribute comparable
# amounts, so no single pass dominates purely by being first.
_RRF_K = 60

# Cap on rows considered per entity type for the semantic pass (mirrors the
# lexical pass's _MAX_LEXICAL_ROWS_PER_TYPE cap for the same reason: no
# supporting index bounds an unbounded scan/sort otherwise — the HNSW index
# does bound the *cost* here, but we still only need the top few dozen).
_SEMANTIC_TOP_K = 50

# #1965: the fixed 50 candidates were fetched even for a 5-result page. The
# semantic leg only needs enough candidates to populate the requested page
# after RRF fusion, so the per-type pool is bounded by the page window with a
# 2x over-fetch margin (fusion can reorder a rank-30 semantic hit into page 1
# when the other legs are sparse). The floor keeps tiny pages useful and the
# _SEMANTIC_TOP_K ceiling means large pages keep the historical pool size, so
# the worst case is byte-identical to before #1965.
_SEMANTIC_MIN_TOP_K = 20
_SEMANTIC_OVERFETCH_FACTOR = 2

# #1965: a slow embedding provider must not hold a web worker for the whole
# inference. The request thread waits at most this long for the query vector,
# then serves fulltext+lexical (hybrid) or an empty vector leg (vector) and
# reports the degradation instead of blocking. Env-configurable per 12-factor;
# tests monkeypatch _embedding_timeout_seconds directly.
_SEARCH_EMBEDDING_TIMEOUT_ENV = "SEARCH_EMBEDDING_TIMEOUT_SECONDS"
_SEARCH_EMBEDDING_TIMEOUT_DEFAULT = 8.0

#: Local degraded_reason tokens for a query vector that could not be produced
#: in time / at all. The request is still served (keyword-only), so the loss of
#: the semantic leg must be *loud*, not silent. A provider that is simply not
#: configured still returns ``None`` without a token, preserving the
#: pre-#1965 wire contract for that steady state.
DEGRADED_EMBEDDING_TIMEOUT = "embedding_timeout"
DEGRADED_EMBEDDING_FAILED = "embedding_failed"

#: T-A3-2 (A-L21): normalized lexical score at/above which a hit counts as an
#: *exact* identifier match and is pinned above the fused list. The exact-title
#: tier normalizes to 1.0 and the exact-uid/ID tiers to 2.9/3.0 ≈ 0.967, while
#: the next tier down (title prefix) sits at 2.5/3.0 ≈ 0.833 — 0.9 is the
#: natural cut between "the query IS the identifier" and "it merely starts
#: like it".
_PIN_MIN_NORMALIZED_LEXICAL_SCORE = 0.9

#: ORM path the semantic pass filters a type's rows by when a workspace is
#: supplied. Requirement joins through ``pl_artifact`` (NOT the denormalized
#: ``Requirement.workspace`` field -- see the port call in _run_semantic_query);
#: TraceLink has no workspace of its own and resolves through ``source``; Icd
#: carries ``workspace_id`` directly. ``None`` for a type with no such field.
_SEMANTIC_WORKSPACE_FIELDS: dict[str, str | None] = {
    "Requirement": "artifact__workspace_id",
    "TraceLink": "source__workspace_id",
    "Icd": "workspace_id",
}


@dataclass(frozen=True)
class _TableSpec:
    """Physical mapping of a searchable artifact type.

    ``title_col``/``description_col``/``workspace_col`` are trusted SQL
    fragments defined in this module only — never built from user input.

    ``permission_scoped`` marks the two T-A3-3 types whose hits are additionally
    filtered after the SQL passes for an item-level READ check through
    :class:`~application.effective_permission_service.EffectivePermissionService`
    (see :func:`_apply_row_visibility`). The soft-delete drop is NOT part of that
    per-type step: :func:`_filter_outdated_hits` is the single lifecycle filter
    for every type (P6 / D13). The other types keep their pre-T-A3-3 behaviour
    (workspace/tenant scoping only).
    """

    table: str
    title_col: str = "e.title"
    description_col: str = "COALESCE(e.description, '')"
    #: Extra column folded into the *full-text* expression only (#1374 /
    #: ADR-026 §11: Document's markdown ``body`` must be searchable without
    #: turning the hit's displayed ``description`` into description+body).
    extra_fulltext_col: str | None = None
    join_sql: str = ""
    workspace_col: str = "e.workspace_id"
    uid_col: str | None = "e.uid"
    artifact_id_col: str | None = None
    permission_scoped: bool = False


_ARTIFACT_JOIN = "JOIN pl_artifact a ON a.id = e.artifact_id"
#: LEFT JOIN variant for the ``as_*`` tables: their backing Artifact FK is
#: nullable (added later, additive migration), so an inner join would silently
#: drop pre-existing rows. Used only to surface ``custom_fields``.
_ARTIFACT_LEFT_JOIN = "LEFT JOIN pl_artifact a ON a.id = e.artifact_id"

# Every artifact type ``artifact.search`` can return (#345 Finding 2b: the
# type_filter enum used to allow only the first three, so Needs/Goals/ADRs
# were unfilterable even though they are searchable).
#
# Deliberately excluded:
#   MainGoal — has no title, only a single aggregated ``content`` blob per
#   workspace; it is a derived summary, not an addressable artifact.
_TABLE_SPECS: dict[str, _TableSpec] = {
    "Requirement": _TableSpec(
        table="pl_requirement",
        join_sql=_ARTIFACT_JOIN,
        workspace_col="a.workspace_id",
        artifact_id_col="e.artifact_id",
    ),
    "ArchitectureElement": _TableSpec(
        table="pl_architecture_element",
        join_sql=_ARTIFACT_JOIN,
        workspace_col="a.workspace_id",
        artifact_id_col="e.artifact_id",
    ),
    "TestCase": _TableSpec(
        table="pl_testcase",
        join_sql=_ARTIFACT_JOIN,
        workspace_col="a.workspace_id",
        artifact_id_col="e.artifact_id",
    ),
    "StakeholderNeed": _TableSpec(
        table="pl_stakeholder_need",
        join_sql=_ARTIFACT_JOIN,
        workspace_col="a.workspace_id",
        artifact_id_col="e.artifact_id",
    ),
    # as_* tables carry workspace_id on the row itself and their backing
    # Artifact FK is nullable (added later, additive migration), so this uses a
    # LEFT JOIN (never the inner ``_ARTIFACT_JOIN``, which would silently drop
    # pre-existing rows) — purely to surface the artifact's custom_fields.
    "Adr": _TableSpec(
        table="as_adr", artifact_id_col="e.artifact_id", join_sql=_ARTIFACT_LEFT_JOIN
    ),
    "Risk": _TableSpec(
        table="as_risk", artifact_id_col="e.artifact_id", join_sql=_ARTIFACT_LEFT_JOIN
    ),
    "Issue": _TableSpec(
        table="as_issue", artifact_id_col="e.artifact_id", join_sql=_ARTIFACT_LEFT_JOIN
    ),
    # ChangeRequest/GlossaryTerm also carry a nullable backing Artifact FK
    # (added by the data-model consolidation), so they use the same LEFT JOIN
    # as the other ``as_*`` tables to surface its ``custom_fields`` (#934 WS1
    # follow-up) — the LEFT JOIN cannot drop pre-existing rows with a NULL FK.
    "ChangeRequest": _TableSpec(
        table="as_change_request",
        uid_col=None,
        artifact_id_col="e.artifact_id",
        join_sql=_ARTIFACT_LEFT_JOIN,
    ),
    "Goal": _TableSpec(
        table="as_goal",
        uid_col=None,
        artifact_id_col="e.artifact_id",
        join_sql=_ARTIFACT_LEFT_JOIN,
    ),
    "GlossaryTerm": _TableSpec(
        table="pl_glossary_term",
        title_col="e.term",
        description_col="COALESCE(e.definition, '')",
        uid_col=None,
        artifact_id_col="e.artifact_id",
        join_sql=_ARTIFACT_LEFT_JOIN,
    ),
    # T-A3-3: the ICD header row. ``name`` is the interface name and the
    # current contract's ``semantic_description`` its description. The backing
    # Artifact FK is nullable (SET_NULL). The LEFT JOIN here discards nothing —
    # it exists only to surface the artifact's ``custom_fields``. The
    # soft-delete drop is NOT done in :func:`_filter_icd_hits` (which only
    # enforces the item-level READ check) but in the shared
    # :func:`_filter_outdated_hits` step (P6 / D13). A row whose
    # ``artifact_id`` is NULL — SET_NULL after the shadow artifact was removed —
    # is still dropped fail-closed in :func:`_filter_icd_hits` (review finding
    # F9; the earlier comment here wrongly implied the join performed the drop).
    "Icd": _TableSpec(
        table="icd_icd",
        title_col="e.name",
        description_col="COALESCE(e.semantic_description, '')",
        workspace_col="e.workspace_id",
        uid_col=None,
        artifact_id_col="e.artifact_id",
        join_sql=_ARTIFACT_LEFT_JOIN,
        permission_scoped=True,
    ),
    # Plan F F2-T7 (ADR-026 §11): a Document's markdown ``body`` is part of
    # the searchable text. It is folded in through ``extra_fulltext_col`` so
    # the hit's displayed ``description`` stays the summary rather than
    # "description + entire document". The backing Artifact FK is non-null,
    # so the inner join is correct here (unlike the ``as_*`` tables).
    "Document": _TableSpec(
        table="pl_document",
        join_sql=_ARTIFACT_JOIN,
        workspace_col="a.workspace_id",
        artifact_id_col="e.artifact_id",
        extra_fulltext_col="e.body",
    ),
    # Plan F F3-T8: a work item's markdown ``body`` is part of its searchable
    # text, folded in through ``extra_fulltext_col`` so the hit preview stays
    # the resume hint rather than "hint + entire section". ``pl_work_item`` has
    # no ``description`` column, so ``description_col`` points at
    # ``next_action`` — the field the resume contract shows next to the title.
    "WorkItem": _TableSpec(
        table="pl_work_item",
        description_col="COALESCE(e.next_action, '')",
        join_sql=_ARTIFACT_JOIN,
        workspace_col="a.workspace_id",
        artifact_id_col="e.artifact_id",
        extra_fulltext_col="e.body",
    ),
    # T-A3-3: a TraceLink has neither a title nor a uid of its own. The
    # fulltext/lexical SQL matches the link type (plus the raw endpoint ids, so
    # the usual "paste an ID fragment" behaviour holds); the human-readable
    # synthetic "<link_type>: <source local uid> → <target local uid>" title is
    # composed afterwards in :func:`_apply_row_visibility` — ``pl_artifact``
    # carries no ``uid`` column, the local uid lives on the endpoint's entity
    # table. Workspace scoping is the *source* side (TraceLinkViewSet's fence).
    # ``artifact_id_col`` stays None: there is no single backing artifact, so
    # ``_custom_fields_select`` yields NULL.
    #
    # KNOWN LIMITATION (review finding F6, documented rather than changed): the
    # *searched* title below embeds the endpoint **IDs**, while the *displayed*
    # title built in _apply_row_visibility embeds the endpoint **local uids**.
    # A link is therefore findable by an endpoint-ID fragment but NOT by an
    # endpoint uid ("REQ-L1-007" does not find the links pointing at it).
    # Resolving the uids in SQL would mean joining the endpoint's entity table
    # once per endpoint kind — out of scope here, recorded as a limitation.
    "TraceLink": _TableSpec(
        table="pl_tracelink",
        title_col=(
            "e.link_type || ': ' || e.source_id::text || ' → ' || e.target_id::text"
        ),
        description_col="COALESCE(e.rationale, '')",
        join_sql=(
            "JOIN pl_artifact s ON s.id = e.source_id "
            "JOIN pl_artifact t ON t.id = e.target_id"
        ),
        workspace_col="s.workspace_id",
        uid_col=None,
        permission_scoped=True,
    ),
}

_VALID_TYPES = set(_TABLE_SPECS)

#: Public, stable view of the searchable artifact types — the single source
#: of truth for the ``type_filter`` enum published by MCP ``artifact.search``.
SEARCHABLE_ARTIFACT_TYPES: frozenset[str] = frozenset(_TABLE_SPECS)

# ---------- DTOs ----------


@dataclass
class SearchHit:
    """Single search result item.

    Attributes:
        relevance_score: Normalized relevance in the closed interval
            ``[0.0, 1.0]``, where 1.0 is the strongest match (issue #827).
            Each search pass derives this from its own native scale
            (cosine similarity, ``ts_rank``, lexical CASE tiers, or the RRF
            fused score); normalization happens at score creation time, so
            every exported/persisted score is bounded and comparable across
            passes and entity types. The mapping is monotone, so the ranking
            is unchanged.
    """

    id: str
    artifact_type: str  # "Requirement" | "ArchitectureElement" | "TestCase"
    title: str
    description: str
    relevance_score: float
    workspace_id: str
    #: REQ-L2-AS-037 / Epic #934 WS1: extended attributes of the backing
    #: Artifact, so ``artifact.search`` result rows carry them too (spec
    #: section 9). Every searchable type now joins ``pl_artifact`` (LEFT JOIN
    #: for the ``as_*`` tables whose FK is nullable) and surfaces the artifact's
    #: ``custom_fields``; the empty default only covers rows with no backing
    #: artifact (e.g. a pre-migration row) or a non-object/absent value.
    custom_fields: dict[str, Any] = dataclass_field(default_factory=dict)
    #: Internal sort marker for the T-A3-2 pin — **not** part of the wire
    #: format. Both serialization surfaces whitelist their fields explicitly
    #: (``rest_api.views``' search view and ``mcp_server.tools.cross_cutting``'
    #: ``artifact.search``), so this never reaches a caller.
    #:
    #: It exists because ``relevance_score`` alone cannot express "pinned":
    #: ``_rrf_fuse`` normalizes by the theoretical maximum
    #: (``len(rank_lists) / (_RRF_K + 1)``), so an *unpinned* hit at rank 0 in
    #: every list scores exactly 1.0 too. Ranking the pin above that tie needs
    #: a signal outside the score (review finding F1).
    pinned: bool = False
    #: P6 / D13: the entity's projected workflow status — ``"outdated"`` when
    #: the backing artifact is soft-deleted. Resolved through
    #: :func:`workflow.state_reader.current_states`, the single status
    #: projection of the system (never a second status axis), for the returned
    #: page only. Empty for types without a workflow state, except ``TraceLink``
    #: which reports ``"outdated"`` when an enforced endpoint is outdated.
    status: str = ""
    #: P6 / D13: ``True`` when the hit is soft-deleted (``status ==
    #: "outdated"``). Outdated hits are excluded by default and only reach the
    #: caller with ``include_outdated=True``.
    outdated: bool = False


@dataclass
class SearchResult:
    """Paginated search result set.

    Attributes:
        results: List of SearchHit.
        total_count: Total matching records (for pagination UI).
        page: Current page (1-based).
        limit: Page size used.
        query: The parsed tsquery string for debugging.
    """

    results: list[SearchHit]
    total_count: int
    page: int
    limit: int
    query: str = ""
    #: T-A2-7: how THIS request was served. ``degraded`` is True when a Qdrant
    #: outage forced the pgvector fallback (``degraded_reason="qdrant_unavailable"``)
    #: or when the cross-type semantic leg failed and the request therefore
    #: served *partial* semantic results (``degraded_reason="cross_type_query_failed"``).
    #: ``vector_backend`` names the backend that actually served the query -- on
    #: the fallback it flips to ``"pgvector"``, on a cross-type-only failure it
    #: keeps naming the Qdrant backend, because no fallback happened. A default
    #: (non-Qdrant) deployment reports ``False``/``"pgvector"``/``""`` and is
    #: byte-identical to the pre-T-A2-7 output.
    degraded: bool = False
    vector_backend: str = "pgvector"
    degraded_reason: str = ""


# ---------- Query parser ----------


class QueryParser:
    """Translate user input to a safe PostgreSQL tsquery string.

    REQ-L3-SEARCH-002: operators, prefix search, phrase matching.
    SQL-injection safe via parameterized execution.

    Examples:
        "req"         → "req"          (simple token)
        "req*"        → "req:*"        (prefix)
        "req AND ui"  → "req & ui"
        "req OR ui"   → "req | ui"
        "NOT ui"      → "!ui"
        '"req ui"'    → "req <-> ui"   (phrase)
    """

    _PHRASE_RE = re.compile(r'"([^"]+)"')

    @classmethod
    def parse(cls, raw: str) -> str:
        """Return a tsquery-compatible string from *raw* user input.

        Raises:
            ValidationError: Query is blank or contains only special chars.
        """
        if not raw or not raw.strip():
            raise ValidationError("Search query must not be empty.")

        # Handle phrase matches first
        def _phrase_replace(m: re.Match) -> str:
            tokens = m.group(1).split()
            return " <-> ".join(cls._quote_token(t) for t in tokens if t)

        q = cls._PHRASE_RE.sub(_phrase_replace, raw)

        # Logical operators
        q = re.sub(r"\bAND\b", "&", q)
        q = re.sub(r"\bOR\b", "|", q)
        q = re.sub(r"\bNOT\b", "!", q)

        # Prefix search: "token*" → "token:*"
        def _prefix_replace(m: re.Match) -> str:
            token = m.group(1)
            return f"{token}:*"

        q = re.sub(r"(\w+)\*", _prefix_replace, q)

        # Remaining bare words (not operators)
        # Wrap remaining plain words as single-quoted tsquery tokens
        # (psycopg2 parameterization handles actual escaping)
        q = q.strip()
        if not q:
            raise ValidationError("Search query parsed to empty tsquery.")

        return q

    @staticmethod
    def _quote_token(token: str) -> str:
        return token.strip("'\"")


# ---------- SQL passes ----------


def _escape_like(value: str) -> str:
    """Neutralize LIKE wildcards so the query is matched literally.

    PostgreSQL's default LIKE escape character is the backslash; the escaped
    value is bound as a parameter, so no string-literal quoting applies.
    """
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# ---------- Relevance normalization (issue #827) ----------
#
# ``SearchHit.relevance_score`` is defined on the closed interval [0, 1].
# Each pass produces its raw score in a different, native scale; the helpers
# below map those scales at the point of score creation (not in a view). All
# of them are monotone, so a higher raw score never yields a lower normalized
# score and no ranking order changes.


def _clamp_unit_interval(value: float) -> float:
    """Clamp *value* to the closed unit interval ``[0.0, 1.0]``.

    Clamping is monotone non-decreasing, so it can only collapse values that
    were already outside the interval — it never swaps two in-range scores.
    """
    return max(0.0, min(1.0, value))


def _normalize_cosine_similarity(distance: float) -> float:
    """Map a pgvector cosine *distance* in ``[0, 2]`` onto ``[0, 1]``.

    ``1 - distance`` is the cosine similarity, which lies in ``[-1, 1]``:
    identical directions give 1, orthogonal vectors 0, opposite directions
    -1. Relevance is defined as non-negative, so negative similarities are
    clamped to 0. The map is monotone non-increasing in *distance*, so a pass
    ordered by ascending distance keeps its ranking.
    """
    return _clamp_unit_interval(1.0 - distance)


def _normalize_fulltext_score(raw_score: float) -> float:
    """Map a raw ``ts_rank`` score onto ``[0, 1]`` by clamping.

    ``ts_rank`` is a small, unbounded-above float; in practice it stays well
    below 1.0 (the QA report measured 0.27 and 0.06). Clamping is monotone
    non-decreasing, so the full-text pass's ``ORDER BY relevance_score DESC``
    ordering is preserved.
    """
    return _clamp_unit_interval(raw_score)


def _normalize_lexical_score(raw_score: float) -> float:
    """Map a raw lexical CASE tier onto ``[0, 1]``.

    The tiers span ``[_SCORE_ID_SUBSTRING=1.5, _SCORE_TITLE_EXACT=3.0]``;
    dividing by :data:`_SCORE_MAX` (the tier maximum) yields ``[0.5, 1.0]``
    while preserving the strict tier order. Division by a positive constant
    is strictly monotone, so no two lexical hits swap places.
    """
    return _clamp_unit_interval(raw_score / _SCORE_MAX)


def _merge_hits(*hit_lists: list[SearchHit]) -> list[SearchHit]:
    """Dedup ``hit_lists`` by ``hit.id``, keeping the highest relevance score.

    Shared by :meth:`SearchService._search_entity_type`'s two-pass
    (full-text + lexical) merge and :meth:`SearchService._search_multi_workspace`'s
    per-workspace merge -- same "keyed by id, keep max score" pattern either way.

    On a score *tie* the pinned duplicate wins (review finding F1): a
    multi-workspace merge must not be able to trade a pin away for an
    equivalent unpinned hit, which would re-open the A-L21 ordering gap the pin
    exists to close.
    """
    merged: dict[str, SearchHit] = {}
    for hits in hit_lists:
        for hit in hits:
            existing = merged.get(hit.id)
            if (
                existing is None
                or hit.relevance_score > existing.relevance_score
                or (hit.relevance_score == existing.relevance_score and hit.pinned)
            ):
                merged[hit.id] = hit
    return list(merged.values())


def _rrf_fuse(*rank_lists: list[SearchHit]) -> list[SearchHit]:
    """Reciprocal Rank Fusion of N independently-ranked hit lists (Task 9).

    ``score(hit) = sum over each rank_list containing hit of
    1 / (_RRF_K + rank_in_that_list + 1)`` — a hit near the top of several
    lists outranks one appearing only in a single list, without needing the
    lists' raw scores to be on comparable scales (ts_rank, the lexical CASE
    tiers, and cosine similarity are NOT comparable numbers, which is exactly
    why RRF -- rank-based, not score-based -- is used to combine them).

    Deliberately scoped: this is used by :meth:`SearchService._search_entity_type`
    ONLY when a semantic rank list is non-empty for that entity type (see call
    site). When only fulltext+lexical are present, :func:`_merge_hits` (keep
    max score per id) is used instead, unchanged from pre-Task-9 behaviour --
    replacing it universally would flatten the lexical tiers' normalized
    scores (>= 0.5, deliberately dominant, see module header) down into RRF's
    tiny range (at most ``len(rank_lists) / (_RRF_K + 1)`` -- roughly 0.049
    for the three lists used here), which would make an exact-title lexical
    match in a semantic-eligible type rank BELOW an unrelated full-text match
    in a type with no embedding column -- a real cross-type regression this
    task's brief explicitly warns against introducing.

    Returns hits sorted by fused score descending, each hit's
    ``relevance_score`` replaced with its fused RRF score normalized to
    ``[0, 1]`` (issue #827) by dividing by its theoretical maximum: the score
    a hit that ranks first (rank 0) in *every* ``rank_list`` would receive.
    The divisor is independent of the hit and strictly positive, so the fused
    ranking is preserved unchanged.
    """
    scores: dict[str, float] = {}
    hits_by_id: dict[str, SearchHit] = {}
    for rank_list in rank_lists:
        for rank, hit in enumerate(rank_list):
            scores[hit.id] = scores.get(hit.id, 0.0) + 1.0 / (_RRF_K + rank + 1)
            hits_by_id[hit.id] = hit
    max_score = len(rank_lists) / (_RRF_K + 1.0)
    ordered_ids = sorted(scores, key=lambda hit_id: -scores[hit_id])
    return [
        dataclass_replace(
            hits_by_id[hit_id],
            relevance_score=(
                _clamp_unit_interval(scores[hit_id] / max_score)
                if max_score > 0.0
                else 0.0
            ),
        )
        for hit_id in ordered_ids
    ]


def _embedding_field_dimensions(entity_type: str) -> int | None:
    """Return the declared ``VectorField(dimensions=...)`` for *entity_type*'s
    ``embedding`` column, or ``None`` if it has none / is unknown.

    Mirrors ``RequirementService._generate_and_store_embedding``'s identical
    ``Model._meta.get_field("embedding").dimensions`` lookup on the write
    side (Task 12) -- kept local to each call site rather than a shared
    helper module, since both are small, single-line lookups against
    already-imported models and a third module would be overkill for this.
    """
    if entity_type == "Requirement":
        return Requirement._meta.get_field("embedding").dimensions
    if entity_type == "TraceLink":
        return TraceLink._meta.get_field("embedding").dimensions
    if entity_type == "Icd":
        from icd.models import Icd  # local import, see _dispatch below

        return Icd._meta.get_field("embedding").dimensions
    return None


def _semantic_search_hits(entity_type: str, hits: list[VectorHit]) -> list[SearchHit]:
    """Hydrate port hits (id + distance) into SearchHit DTOs for *entity_type*.

    The port returns only the nearest ids and their cosine distances, so the
    rows are re-fetched by id and reordered to the port's closest-first order.
    Each type resolves the same fields its pre-port branch did: Requirement's
    ``title``/``description`` and its workspace through ``pl_artifact``;
    TraceLink's synthetic ``<type>: <source> -> <target>`` title and workspace
    through ``source``; Icd's name/description and own ``workspace_id``.
    """
    if not hits:
        return []
    ids = [hit.id for hit in hits]

    if entity_type == "Requirement":
        rows = {
            row.id: row
            for row in Requirement.objects.filter(id__in=ids).annotate(
                ws_id=F("artifact__workspace_id")
            )
        }
        return [
            SearchHit(
                id=str(hit.id),
                artifact_type=entity_type,
                title=rows[hit.id].title or "",
                description=rows[hit.id].description or "",
                relevance_score=_normalize_cosine_similarity(float(hit.distance)),
                workspace_id=str(rows[hit.id].ws_id) if rows[hit.id].ws_id else "",
            )
            for hit in hits
            if hit.id in rows
        ]

    if entity_type == "TraceLink":
        rows = {
            row.id: row
            for row in TraceLink.objects.filter(id__in=ids).annotate(
                ws_id=F("source__workspace_id")
            )
        }
        return [
            SearchHit(
                id=str(hit.id),
                artifact_type=entity_type,
                title=(
                    f"{rows[hit.id].link_type}: "
                    f"{rows[hit.id].source_id} -> {rows[hit.id].target_id}"
                ),
                description="",
                relevance_score=_normalize_cosine_similarity(float(hit.distance)),
                workspace_id=str(rows[hit.id].ws_id) if rows[hit.id].ws_id else "",
            )
            for hit in hits
            if hit.id in rows
        ]

    if entity_type == "Icd":
        # Local import: icd is an Ext-layer app (see _embedding_field_dimensions).
        from icd.models import Icd

        rows = {row.id: row for row in Icd.unscoped.filter(id__in=ids)}
        return [
            SearchHit(
                id=str(hit.id),
                artifact_type=entity_type,
                title=(
                    (rows[hit.id].name or rows[hit.id].semantic_description or "ICD")[:200]
                ),
                description=rows[hit.id].semantic_description or "",
                relevance_score=_normalize_cosine_similarity(float(hit.distance)),
                workspace_id=(
                    str(rows[hit.id].workspace_id) if rows[hit.id].workspace_id else ""
                ),
            )
            for hit in hits
            if hit.id in rows
        ]

    return []


def _run_semantic_query(
    entity_type: str,
    query_embedding: list[float] | None,
    tenant_id: Any,
    workspace_id: UUID | None,
    *,
    port: Any = None,
    query_text: str = "",
    ctx: Any = None,
    semantic_limit: int | None = None,
) -> list[SearchHit]:
    """Cosine-similarity pass over ``entity_type``'s ``embedding`` column.

    REQ-L2-VS-004 (Task 9). Only Requirement/TraceLink/Icd carry an
    ``embedding`` VectorField today -- everything else (and a missing/empty
    ``query_embedding``, e.g. no embedding provider configured) returns [].

    Uses the :class:`application.vector_port.VectorPort` (pgvector adapter by
    default, mirroring ``memory.backends.PgvectorMemoryBackend.query()``), NOT
    the raw-SQL ``_TableSpec`` machinery the fulltext/lexical passes use above:
    the cosine-distance operator needs the ORM's vector-aware query compiler,
    and ``_TableSpec`` only ever described plain string/id columns.

    Degrades to [] on ANY error and NEVER raises -- REQ-L3-SEARCH-009's
    "degrade gracefully" precedent (same philosophy as
    ``memory/context_builder.py``). This matters concretely, not just
    theoretically: pgvector raises a DB-level error the moment a
    dimension-mismatched query vector is compared against a non-NULL embedding
    row. Since #794 the shipped default no longer produces that mismatch (all
    embedding columns are sized from
    ``persistence.embedding_dimensions.EMBEDDING_VECTOR_DIMENSIONS``, which
    tracks the default provider), but an operator can still reintroduce it by
    switching ``EMBEDDING_PROVIDER`` to a different native width without
    resizing the columns. Semantic search must never take fulltext/lexical
    results down with it when that happens.

    The pgvector adapter runs the query inside its own ``transaction.atomic()``
    savepoint (the port owns it now): a dimension-mismatch error is a real
    Postgres-level error (``DataError``/``InternalError``, not a Python-level
    one), and an uncaught DB error inside an ambient transaction leaves that
    *transaction* aborted -- every subsequent query on the same connection
    would then raise "current transaction is aborted" until a rollback happens,
    silently breaking whichever entity types are searched *after* this one in
    :meth:`SearchService.search`'s loop (e.g. under pytest-django, which wraps
    each test in one transaction, or any production caller that wraps
    ``search()`` in its own ``atomic()`` block). The savepoint means only this
    one query's failure is rolled back, not the whole surrounding transaction.
    """
    if entity_type not in _EMBEDDABLE_TYPES or not query_embedding:
        return []

    # Final whole-branch review Finding 5: without this guard, EVERY search
    # request touching a non-NULL embedding row under a dimension-mismatched
    # configuration hits the DB-level DataError caught below and logs a full
    # traceback via logger.exception. Short-circuit BEFORE issuing the query,
    # exactly mirroring the write-side guard (RequirementService.
    # _generate_and_store_embedding): compare the vector length against the
    # column's declared dimension and skip cleanly instead of paying for a
    # doomed DB round-trip.
    field_dimensions = _embedding_field_dimensions(entity_type)
    if field_dimensions is not None and len(query_embedding) != field_dimensions:
        # #794: WARNING (deduplicated per process), not DEBUG. Until #794 this
        # branch was the *shipped default* path -- it swallowed 100% of
        # semantic passes and its DEBUG line was the only trace of an
        # `artifact.search` that could never return a semantic hit. It is now
        # strictly a misconfiguration signal, so it must be visible.
        from llm_adapter.embedding_service import warn_dimension_mismatch

        warn_dimension_mismatch(
            f"SearchService[{entity_type}]", len(query_embedding), field_dimensions
        )
        return []

    def _dispatch() -> list[SearchHit]:
        """Query the vector port for this type and hydrate the matching rows.

        The ANN query is delegated to the active
        :class:`~application.vector_port.VectorPort` (pgvector by default) and
        the returned ids are re-fetched to build the DTOs. ``iterative_scan``
        reproduces the pgvector hardening this path applied before the port
        split (issue #977); the port now owns the ``atomic()`` savepoint that
        used to wrap the query here.

        ``port`` is the request's single port instance so the T-A2-7 degraded
        flag is aggregated over every type; ``query_text``/``ctx`` feed the
        Qdrant hybrid leg and the QR-S07 READ check of hydrated hits.
        """
        request_port = port or get_fallback_vector_port()
        hits = request_port.query_similar(
            collection=entity_type,
            query_vector=query_embedding,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            workspace_field=_SEMANTIC_WORKSPACE_FIELDS.get(entity_type),
            # #1965: bound the per-type ANN pool by the requested page window
            # (2x over-fetch, capped at the historical 50). Direct callers
            # that omit semantic_limit keep the old fixed pool.
            limit=semantic_limit if semantic_limit is not None else _SEMANTIC_TOP_K,
            iterative_scan=True,
            # T-A2-6: the Qdrant adapter fuses this text as its BM25 leg; the
            # pgvector adapter ignores it (results stay byte-identical).
            query_text=query_text,
            # QR-S07: the READ gate for hydrated Qdrant hits needs the caller.
            ctx=ctx,
        )
        # QR-S07 on the FALLBACK path. A FallbackVectorPort that had to serve
        # this call from pgvector returns raw ORM rows: the pgvector adapter
        # ignores ``ctx`` entirely, so neither item-level READ nor the
        # ``OUTDATED`` exclusion applied -- the caller would see hits the Qdrant
        # path would have dropped, and any client able to make the server-side
        # BM25 inference fail could pick that weaker set on demand. Route those
        # hits through the same hydration gate the Qdrant adapter uses.
        #
        # Only when the port actually served from the fallback: the default
        # deployment is a bare PgVectorVectorPort (serves_from_fallback() is
        # False), so it takes no gate and stays byte-identical. A healthy Qdrant
        # wrapper flagged ``degraded`` by an unrelated cross-type failure is not
        # a fallback either -- its hits are already hydrated, and re-hydrating
        # them would cost an extra ORM lookup plus permission resolution per
        # embeddable type per workspace.
        if serves_from_fallback(request_port):
            hits = hydrate_vector_hits(
                collection=entity_type,
                hits=hits,
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                ctx=ctx,
            )
        return _semantic_search_hits(entity_type, hits)

    try:
        return _dispatch()
    except Exception:
        logger.exception(
            "SearchService: semantic pgvector query error entity_type=%s "
            "(commonly an embedding-provider/column dimension mismatch)",
            entity_type,
        )
        # REQ-L3-SEARCH-009: degrade gracefully -- a broken/mismatched
        # semantic pass must never take the fulltext/lexical results down.
        return []


def _custom_fields_select(spec: _TableSpec) -> str:
    """SQL expression for a hit's Artifact.custom_fields (or ``NULL``).

    Valid whenever the pass joins ``pl_artifact`` (``artifact_id_col`` set),
    which is now every searchable type: the ``pl_*`` entity tables
    (Requirement, ArchitectureElement, TestCase, StakeholderNeed) use an inner
    join and the ``as_*``/glossary tables use a LEFT JOIN onto their nullable
    FK, so a row without a backing Artifact yields ``NULL`` and falls back to
    ``{}`` in :func:`_rows_to_hits`.
    """
    return "a.custom_fields" if spec.artifact_id_col else "NULL"


def _rows_to_hits(
    rows: Any,
    entity_type: str,
    normalizer: Callable[[float], float],
) -> list[SearchHit]:
    """Map ``(id, workspace_id, title, description, score[, custom_fields])``
    rows to hits.

    ``normalizer`` maps this pass's raw SQL score onto the DTO's [0, 1]
    relevance scale (issue #827). It must be monotone, since the rows arrive
    in the pass's own ``ORDER BY ... DESC`` order and normalization must not
    reorder them.
    """
    hits: list[SearchHit] = []
    for row in rows:
        if len(row) == 6:
            eid, ws_id, title, description, score, custom_fields = row
        else:
            eid, ws_id, title, description, score = row
            custom_fields = None
        hits.append(
            SearchHit(
                id=str(eid),
                artifact_type=entity_type,
                title=title or "",
                description=description or "",
                relevance_score=normalizer(float(score)),
                workspace_id=str(ws_id) if ws_id is not None else "",
                custom_fields=coerce_custom_fields(custom_fields),
            )
        )
    return hits


# ---------- T-A3-3: per-hit visibility for permission-scoped types ----------


def _as_uuid(value: Any) -> UUID | None:
    """Coerce *value* to a UUID, or ``None`` for an unparsable/empty one."""
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None


def _local_uids_by_artifact(artifact_ids: set[UUID]) -> dict[UUID, str]:
    """Map ``pl_artifact.id`` -> local readable uid for the uid-carrying types.

    ``pl_artifact`` itself has no ``uid`` column — T-A3-3 verified this against
    the model and the live schema. The local identifier lives on the endpoint's
    entity table, so a synthetic TraceLink title resolves it here. Mirrors the
    uid-carrying models of ``application.reference_resolver_service`` (TestRun
    excluded: it is not a TraceLink endpoint of interest), one bounded ``IN``
    query per model instead of that service's full reference machinery.
    """
    from persistence.models import (
        Adr,
        ArchitectureElement,
        Issue,
        Requirement,
        Risk,
        StakeholderNeed,
        TestCase,
    )

    resolved: dict[UUID, str] = {}
    if not artifact_ids:
        # A TraceLink hit list can arrive here with no endpoints of interest
        # (and every caller filters by an id set that is empty when there are
        # no links). Seven ``IN ()`` queries would be pure overhead — review
        # finding F8. (The uid-carrying model list itself is kept local rather
        # than shared with ``application.reference_resolver_service``: importing
        # that service here would pull its whole reference machinery into the
        # search path, so the duplication stays.)
        return resolved
    for model in (
        Requirement,
        ArchitectureElement,
        TestCase,
        StakeholderNeed,
        Adr,
        Risk,
        Issue,
    ):
        resolved.update(
            model.objects.filter(artifact_id__in=artifact_ids)
            .exclude(uid__isnull=True)
            .exclude(uid="")
            .values_list("artifact_id", "uid")
        )
    return resolved


def _may_read_artifact(
    ctx: AuthContext | None,
    workspace_id: Any,
    artifact_id: Any,
    roles_cache: dict[str, tuple[str, ...]],
    decision_cache: dict[tuple[str, str | None], bool],
) -> bool:
    """Fail-closed READ check for one (workspace, artifact) pair (T-A3-3).

    Combines the three fences the REST TraceLink detail route already uses for
    cross-workspace metadata (QR-S20): the API key's workspace fence, the
    caller's roles *in that workspace* (RBAC), and the item-level rule layer
    (:class:`EffectivePermissionService`). Roles are resolved per workspace
    rather than taken from ``ctx.active_roles`` because ``active_roles`` is the
    caller's roles in the *current* workspace — using it for a foreign target
    workspace would let a role in one workspace authorize metadata of another.
    """
    from application.effective_permission_service import EffectivePermissionService
    from auth_tenancy.resource_scope import workspace_fence_denial
    from auth_tenancy.services.authorization import AuthorizationService

    if ctx is None:
        return False
    ws_uuid = _as_uuid(workspace_id)
    if ws_uuid is None:
        return False
    artifact_uuid = _as_uuid(artifact_id) if artifact_id is not None else None
    cache_key = (str(ws_uuid), str(artifact_uuid) if artifact_uuid else None)
    if cache_key in decision_cache:
        return decision_cache[cache_key]

    allowed = False
    try:
        fence = getattr(ctx, "api_key_workspace_ids", ())
        if workspace_fence_denial(fence, ws_uuid) is not None:
            decision_cache[cache_key] = False
            return False

        ws_key = str(ws_uuid)
        if ws_key not in roles_cache:
            roles_cache[ws_key] = AuthorizationService().active_roles_for(
                user_id=ctx.user_id, workspace_id=ws_uuid
            )
        decision = EffectivePermissionService().resolve_effective_permission(
            active_roles=roles_cache[ws_key],
            user_id=ctx.user_id,
            workspace_id=ws_uuid,
            artifact_id=artifact_uuid,
            level="read",
        )
        allowed = decision.is_allowed
    except Exception:  # noqa: BLE001 — hide the hit rather than leak it
        logger.debug(
            "SearchService: visibility lookup failed workspace=%s artifact=%s",
            workspace_id,
            artifact_id,
            exc_info=True,
        )
        allowed = False

    decision_cache[cache_key] = allowed
    return allowed


def _prepopulate_decision_cache(
    pairs: list[tuple[Any, Any]],
    ctx: AuthContext | None,
    roles_cache: dict[str, tuple[str, ...]],
    decision_cache: dict[tuple[str, str | None], bool],
) -> None:
    """Precompute READ decisions for many (workspace, artifact) pairs in bulk.

    PERF-006. Without this, every hit pays its own item-permission lookup (up
    to two queries) through :func:`_may_read_artifact`. Here all pairs are
    resolved with ONE item-level query per workspace via
    :meth:`EffectivePermissionService.resolve_effective_permissions_batch`, so
    the query count tracks the number of distinct workspaces, not hits.

    Workspaces outside the API key's fence are denied directly, exactly as the
    per-hit check would, and roles are resolved once per workspace into the
    shared ``roles_cache``. Any failure is swallowed: the signature-unchanged
    :func:`_may_read_artifact` fallback then decides every still-uncached pair
    fail-closed, so a batching problem can never widen visibility.
    """
    if ctx is None or not pairs:
        return

    from application.effective_permission_service import EffectivePermissionService
    from auth_tenancy.resource_scope import workspace_fence_denial
    from auth_tenancy.services.authorization import AuthorizationService

    try:
        fence = getattr(ctx, "api_key_workspace_ids", ())
        by_workspace: dict[UUID, list[UUID]] = {}
        for workspace_id, artifact_id in pairs:
            ws_uuid = _as_uuid(workspace_id)
            artifact_uuid = _as_uuid(artifact_id) if artifact_id is not None else None
            if ws_uuid is None or artifact_uuid is None:
                continue  # let the per-hit fallback resolve unparseable ids
            if workspace_fence_denial(fence, ws_uuid) is not None:
                decision_cache[(str(ws_uuid), str(artifact_uuid))] = False
                continue
            by_workspace.setdefault(ws_uuid, []).append(artifact_uuid)

        for ws_uuid, artifact_ids in by_workspace.items():
            ws_key = str(ws_uuid)
            if ws_key not in roles_cache:
                roles_cache[ws_key] = AuthorizationService().active_roles_for(
                    user_id=ctx.user_id, workspace_id=ws_uuid
                )
            effective = EffectivePermissionService().resolve_effective_permissions_batch(
                active_roles=roles_cache[ws_key],
                user_id=ctx.user_id,
                workspace_id=ws_uuid,
                artifact_ids=artifact_ids,
                level="read",
            )
            for artifact_id, decision in effective.items():
                decision_cache[(ws_key, str(artifact_id))] = decision.is_allowed
    except Exception:  # noqa: BLE001 — fall back to the fail-closed per-hit path
        logger.debug(
            "SearchService: batched visibility lookup failed; "
            "falling back to per-hit checks",
            exc_info=True,
        )


def _filter_icd_hits(hits: list[SearchHit], ctx: AuthContext | None) -> list[SearchHit]:
    """Drop ICD hits the caller may not READ.

    Also drops a row with no backing Artifact at all (review finding S2): the
    FK is ``SET_NULL``, so removing the shadow Artifact leaves a row that has
    nothing the item-permission check could be evaluated against. Such a row
    used to bypass the check and stay searchable forever; with no provable READ
    it is fail-closed like every other unprovable case.

    The lifecycle filter is **not** applied here: Icd is workflow-tracked, so
    the single shared filter :func:`_filter_outdated_hits` sets ``outdated`` and
    (by default) drops outdated rows — one filter decision for every type
    (P6 / D13).
    """
    from icd.models import Icd

    by_id = {
        row.id: row
        for row in Icd.objects.filter(id__in=[_as_uuid(hit.id) for hit in hits])
    }

    roles_cache: dict[str, tuple[str, ...]] = {}
    decision_cache: dict[tuple[str, str | None], bool] = {}
    # PERF-006: resolve every candidate artifact in one batched lookup before
    # the loop, so the permission query count does not scale with hit count.
    _prepopulate_decision_cache(
        [
            (row.workspace_id, row.artifact_id)
            for row in by_id.values()
            if row.artifact_id is not None
        ],
        ctx,
        roles_cache,
        decision_cache,
    )
    kept: list[SearchHit] = []
    for hit in hits:
        row = by_id.get(_as_uuid(hit.id))
        if row is None:  # deleted between the SQL pass and this lookup
            continue
        if row.artifact_id is None:
            continue
        if _may_read_artifact(
            ctx, row.workspace_id, row.artifact_id, roles_cache, decision_cache
        ):
            kept.append(hit)
    return kept


def _filter_tracelink_hits(
    hits: list[SearchHit], ctx: AuthContext | None
) -> list[SearchHit]:
    """Drop unreadable TraceLink hits, compose their title and annotate lifecycle.

    A link is kept only when its **source** artifact is readable (that is the
    link's own workspace). The **target** uid is shown only when the target
    workspace is readable too; otherwise the synthetic title carries ``'—'``, so
    cross-workspace metadata never leaks (QR-S20, T-A3-3).

    Lifecycle is annotated, not filtered, here. The shared filter
    (:func:`_filter_outdated_hits`) owns the only drop decision; this
    path is the one place that knows whether the target endpoint is readable, so
    it is the one place that can compute the hit's ``outdated`` flag:

    * the source's lifecycle is always folded in (it is the link's own
      workspace and always enforceable);
    * the target's only when the caller may actually read the target (review
      finding S1). Enforcing the target's unconditionally made a readable link
      vanish because of a state the caller cannot see anyway — and made that
      vanishing a 1-bit oracle over another workspace's lifecycle.

    An unreadable **source** still drops the hit: that is a permission
    decision, not a lifecycle one.
    """
    from persistence.models import Artifact, LifecycleStatus, TraceLink

    links = {
        row.id: row
        for row in TraceLink.objects.filter(
            id__in=[_as_uuid(hit.id) for hit in hits]
        ).select_related("source", "target")
    }
    endpoint_ids = {
        endpoint_id
        for link in links.values()
        for endpoint_id in (link.source_id, link.target_id)
    }
    statuses = dict(
        Artifact.objects.filter(id__in=endpoint_ids).values_list(
            "id", "lifecycle_status"
        )
    )
    uids = _local_uids_by_artifact(endpoint_ids)

    roles_cache: dict[str, tuple[str, ...]] = {}
    decision_cache: dict[tuple[str, str | None], bool] = {}
    # PERF-006: one batched lookup for every source/target endpoint. Endpoints
    # with a dangling FK are skipped here and left to the fail-closed per-hit
    # fallback (the original loop never touched outdated endpoints either).
    pairs: list[tuple[Any, Any]] = []
    for link in links.values():
        try:
            pairs.append((link.source.workspace_id, link.source_id))
            pairs.append((link.target.workspace_id, link.target_id))
        except Exception:  # noqa: BLE001 — dangling endpoint, let fallback deny
            continue
    _prepopulate_decision_cache(pairs, ctx, roles_cache, decision_cache)
    kept: list[SearchHit] = []
    for hit in hits:
        link = links.get(_as_uuid(hit.id))
        if link is None:  # deleted between the SQL pass and this lookup
            continue

        source = link.source
        target = link.target
        if not _may_read_artifact(
            ctx, source.workspace_id, source.id, roles_cache, decision_cache
        ):
            continue
        show_target = _may_read_artifact(
            ctx, target.workspace_id, target.id, roles_cache, decision_cache
        )

        source_outdated = statuses.get(link.source_id) == LifecycleStatus.OUTDATED
        target_outdated = show_target and (
            statuses.get(link.target_id) == LifecycleStatus.OUTDATED
        )
        outdated = source_outdated or target_outdated

        source_label = uids.get(source.id) or str(source.id)
        target_label = (uids.get(target.id) or str(target.id)) if show_target else "—"
        # The synthetic title is composed even when the shared filter will drop
        # the hit afterwards — the hit stays a truthful SearchHit either way.
        kept.append(
            dataclass_replace(
                hit,
                title=f"{link.link_type}: {source_label} → {target_label}",
                outdated=outdated,
                status=("outdated" if outdated else ""),
            )
        )
    return kept


def _apply_row_visibility(
    entity_type: str, hits: list[SearchHit], ctx: AuthContext | None
) -> list[SearchHit]:
    """Apply the T-A3-3 per-hit rules to a permission-scoped type's hits.

    Only ``Icd`` and ``TraceLink`` opt in via ``_TableSpec.permission_scoped``;
    every other type is returned unchanged (its workspace/tenant SQL scoping is
    unchanged from before T-A3-3). ``ctx`` is forwarded from
    :meth:`SearchService.search`; when it is missing the scoped types fail
    closed (no caller identity means no provable READ).
    """
    if not hits:
        return hits
    spec = _TABLE_SPECS.get(entity_type)
    if spec is None or not spec.permission_scoped:
        return hits
    if entity_type == "TraceLink":
        return _filter_tracelink_hits(hits, ctx)
    if entity_type == "Icd":
        return _filter_icd_hits(hits, ctx)
    return hits


#: Chunk size for the ``id__in`` lookups below. PostgreSQL's bind-parameter
#: ceiling is 65535; 1000 keeps every statement far below it and bounds the
#: statement size for a result set assembled from several search legs (F2).
_LIFECYCLE_CHUNK_SIZE = 1000


def _chunked(values: list[str]) -> list[list[str]]:
    """Split an id list into chunks below the bind-parameter ceiling (F2)."""
    return [
        values[start : start + _LIFECYCLE_CHUNK_SIZE]
        for start in range(0, len(values), _LIFECYCLE_CHUNK_SIZE)
    ]


def _filter_outdated_hits(
    hits: list[SearchHit],
    *,
    include_outdated: bool,
    tenant_id: Any,
) -> list[SearchHit]:
    """Set each hit's ``outdated`` flag and drop outdated hits by default.

    P6 / D13: the **single** lifecycle filter of ``artifact.search`` — applied
    once, after all search legs are merged and *before* ranking,
    ``total_count`` and pagination. Type-specific paths never drop outdated
    rows themselves; only this step decides. ``outdated`` is the filter axis;
    ``status`` is only the display projection (see
    :func:`_annotate_hit_status`), so a display-field failure cannot change
    which rows are visible.

    The flag is resolved from :func:`workflow.state_reader.outdated_ids`
    (entity ids — exactly what hits carry), intersected with the hit ids in
    chunks of :data:`_LIFECYCLE_CHUNK_SIZE`, so no ``__in`` grows unbounded
    (F2). ``TraceLink`` is skipped: :func:`_filter_tracelink_hits` already
    computed its flag, because only that path knows whether the target
    endpoint is readable.

    **Fail closed (F1).** If the outdated lookup for a type raises, every hit
    of that type is dropped and a WARNING is logged — the previous behaviour
    left them annotated as visible, which leaked possibly-outdated rows (and
    inverted Icd's earlier fail-closed drop).

    Known limitation (F4, deliberately not threaded through the vector port):
    the Qdrant adapter and the degraded pgvector-fallback hydration path
    (:func:`application.vector_port.hydrate_vector_hits`) drop outdated rows
    unconditionally. On those backends ``include_outdated=True`` restores an
    outdated hit only when a keyword leg (full-text/lexical) also matched it;
    a hit that ONLY the semantic leg matched stays absent. On pgvector all
    three legs feed this filter and every outdated hit is restored.
    """
    if not hits:
        return hits

    from workflow import state_reader

    ids_by_type: dict[str, list[str]] = {}
    for hit in hits:
        if hit.artifact_type == "TraceLink":
            continue
        ids_by_type.setdefault(hit.artifact_type, []).append(hit.id)

    outdated_by_type: dict[str, set[str]] = {}
    failed_types: set[str] = set()
    for entity_type, item_ids in ids_by_type.items():
        try:
            outdated_ids: set[str] = set()
            for chunk in _chunked(item_ids):
                outdated_ids.update(
                    str(item_id)
                    for item_id in state_reader.outdated_ids(
                        entity_type, tenant_id=tenant_id
                    ).filter(id__in=chunk)
                )
            outdated_by_type[entity_type] = outdated_ids
        except Exception:  # noqa: BLE001 — fail closed, see docstring
            failed_types.add(entity_type)
            logger.warning(
                "SearchService: outdated lookup failed entity_type=%s; "
                "dropping %d hit(s) (fail-closed)",
                entity_type,
                sum(1 for hit in hits if hit.artifact_type == entity_type),
                exc_info=True,
            )

    filtered: list[SearchHit] = []
    for hit in hits:
        if hit.artifact_type in failed_types:
            continue
        if hit.artifact_type == "TraceLink":
            outdated = hit.outdated
        else:
            outdated = hit.id in outdated_by_type.get(hit.artifact_type, set())
        if outdated and not include_outdated:
            continue
        filtered.append(dataclass_replace(hit, outdated=outdated))
    return filtered


def _annotate_hit_status(
    page_hits: list[SearchHit],
    *,
    tenant_id: Any,
) -> list[SearchHit]:
    """Set the display-only workflow ``status`` of the final page hits.

    Runs *after* pagination (at most ``limit`` ≤ 100 hits), so the status
    projection never scales with the corpus (F2) and cannot influence which
    rows are visible (that decision was made by
    :func:`_filter_outdated_hits`, F1). Resolution reuses
    :func:`workflow.state_reader.current_states` — the repository's single
    status projection — with :func:`state_reader.initial_state` as the fallback
    for items without a ``WorkflowItemState`` row; ids are batched in chunks of
    :data:`_LIFECYCLE_CHUNK_SIZE`.

    An existing non-empty ``status`` is preserved (``TraceLink``'s
    ``"outdated"``), and types without a workflow state keep ``""``.

    Failure policy (F1): a failing status lookup logs a WARNING and leaves that
    type's hits with ``status=""`` — the hits stay, because filtering already
    happened.
    """
    if not page_hits:
        return page_hits

    from workflow import state_reader
    from workflow.item_types import KNOWN_WORKFLOW_ITEM_TYPES

    ids_by_type: dict[str, list[str]] = {}
    for hit in page_hits:
        if hit.status or hit.artifact_type == "TraceLink":
            continue
        if hit.artifact_type not in KNOWN_WORKFLOW_ITEM_TYPES:
            continue
        ids_by_type.setdefault(hit.artifact_type, []).append(hit.id)

    statuses_by_type: dict[str, dict[str, str]] = {}
    for entity_type, item_ids in ids_by_type.items():
        try:
            fallback = state_reader.initial_state(entity_type)
            resolved: dict[str, str] = {}
            for chunk in _chunked(item_ids):
                states = state_reader.current_states(
                    entity_type, chunk, tenant_id=tenant_id
                )
                resolved.update(
                    {str(item_id): str(state) for item_id, state in states.items()}
                )
            statuses_by_type[entity_type] = {
                str(item_id): resolved.get(str(item_id), fallback)
                for item_id in item_ids
            }
        except Exception:  # noqa: BLE001 — display field only, see docstring
            logger.warning(
                "SearchService: status lookup failed entity_type=%s; "
                "leaving status empty",
                entity_type,
                exc_info=True,
            )

    annotated: list[SearchHit] = []
    for hit in page_hits:
        statuses = statuses_by_type.get(hit.artifact_type)
        status = hit.status or (
            statuses.get(hit.id, "") if statuses is not None else ""
        )
        # Keep ``outdated == (status == "outdated")`` even when the status
        # lookup degraded: an outdated hit must not report an empty status.
        # Visibility is unaffected — filtering already ran.
        if not status and hit.outdated:
            status = "outdated"
        annotated.append(dataclass_replace(hit, status=status))
    return annotated


def _run_fulltext_query(
    entity_type: str,
    spec: _TableSpec,
    tsquery_str: str,
    tenant_id: Any,
    workspace_id: UUID | None,
) -> list[SearchHit]:
    """tsvector/ts_rank pass for one entity type (REQ-L3-SEARCH-001/003)."""
    from django.db import connection

    tsv = (
        f"to_tsvector('german', COALESCE({spec.title_col}, '') || ' ' "
        f"|| {spec.description_col}"
    )
    if spec.extra_fulltext_col:
        tsv += f" || ' ' || COALESCE({spec.extra_fulltext_col}, '')"
    tsv += ")"

    where_parts = ["e.tenant_id = %s", f"{tsv} @@ plainto_tsquery('german', %s)"]
    params: list[Any] = [str(tenant_id), tsquery_str]
    if workspace_id is not None:
        where_parts.append(f"{spec.workspace_col} = %s")
        params.append(str(workspace_id))

    # Review finding F3: this pass used to be uncapped, and for the two
    # ``permission_scoped`` types every returned row costs its own visibility
    # query afterwards (see :func:`_apply_row_visibility`) — a generic term such
    # as "references" therefore drove an unbounded number of queries against
    # ``pl_tracelink``. Bound exactly those two to the row cap the lexical pass
    # already applies; the ``ORDER BY`` stays first, so the cap drops the
    # worst-ranked rows rather than an arbitrary slice.
    #
    # Deliberately NOT applied to the other types: there it would silently
    # change result sets (a caller could page past the cap into a truncated
    # list), which is a behaviour change outside this finding's scope.
    #
    # ``e.id`` makes the ORDER BY total: ``ts_rank`` and ``created_at`` both
    # tie easily, and on the capped types a tie at the LIMIT boundary would
    # otherwise decide arbitrarily which of two equal rows survives. It is
    # applied for every type, not just the capped ones — between rows that were
    # previously tied it is a pure tiebreak, so it changes no ranking, only
    # removes the non-determinism.
    limit_clause = (
        f"\n        LIMIT {_MAX_LEXICAL_ROWS_PER_TYPE}"
        if spec.permission_scoped
        else ""
    )

    sql = f"""
        SELECT
            e.id,
            {spec.workspace_col},
            COALESCE({spec.title_col}, '') AS title,
            {spec.description_col} AS description,
            ts_rank({tsv}, plainto_tsquery('german', %s)) AS relevance_score,
            {_custom_fields_select(spec)} AS custom_fields
        FROM {spec.table} e
        {spec.join_sql}
        WHERE {' AND '.join(where_parts)}
        ORDER BY relevance_score DESC, e.created_at DESC, e.id{limit_clause}
    """
    # The ts_rank parameter in the SELECT list is bound before the WHERE ones.
    final_params = [tsquery_str] + params

    try:
        with connection.cursor() as cursor:
            cursor.execute(sql, final_params)
            return _rows_to_hits(cursor.fetchall(), entity_type, _normalize_fulltext_score)
    except Exception:
        logger.exception(
            "SearchService: full-text SQL error entity_type=%s", entity_type
        )
        # REQ-L3-SEARCH-009: degrade gracefully.
        return []


def _run_lexical_query(
    entity_type: str,
    spec: _TableSpec,
    raw_query: str,
    tenant_id: Any,
    workspace_id: UUID | None,
) -> list[SearchHit]:
    """Case-insensitive substring pass over title, uid and IDs (#345).

    The full-text pass alone cannot find ``"QA-AI"`` or a raw ID fragment
    such as ``"00436a35"``: ``plainto_tsquery`` lexemizes the input, so an
    identifier that is not a German word (or only a *part* of a token) never
    matches. This pass answers "does what I typed literally occur in the
    name/ID of the artifact", which is what users expect from a search box.
    """
    from django.db import connection

    needle = (raw_query or "").strip().lower()
    if len(needle) < _MIN_LEXICAL_QUERY_LEN:
        return []

    escaped = _escape_like(needle)
    contains = f"%{escaped}%"
    starts_with = f"{escaped}%"

    title_lower = f"lower(COALESCE({spec.title_col}, ''))"
    uid_lower = (
        f"lower(COALESCE({spec.uid_col}, ''))" if spec.uid_col else None
    )

    # --- relevance CASE (bound first: it sits in the SELECT list) ---
    case_parts: list[str] = [f"WHEN {title_lower} = %s THEN {_SCORE_TITLE_EXACT}"]
    case_params: list[Any] = [needle]
    if uid_lower:
        case_parts.append(f"WHEN {uid_lower} = %s THEN {_SCORE_ID_EXACT}")
        case_params.append(needle)
    case_parts.append(f"WHEN e.id::text = %s THEN {_SCORE_ID_EXACT}")
    case_params.append(needle)
    if spec.artifact_id_col:
        case_parts.append(f"WHEN {spec.artifact_id_col}::text = %s THEN {_SCORE_ID_EXACT}")
        case_params.append(needle)
    case_parts.append(f"WHEN {title_lower} LIKE %s THEN {_SCORE_TITLE_PREFIX}")
    case_params.append(starts_with)
    case_parts.append(f"WHEN {title_lower} LIKE %s THEN {_SCORE_TITLE_SUBSTRING}")
    case_params.append(contains)
    score_sql = "CASE " + " ".join(case_parts) + f" ELSE {_SCORE_ID_SUBSTRING} END"

    # --- match predicate ---
    match_parts: list[str] = [f"{title_lower} LIKE %s"]
    match_params: list[Any] = [contains]
    if uid_lower:
        match_parts.append(f"{uid_lower} LIKE %s")
        match_params.append(contains)
    match_parts.append("e.id::text LIKE %s")
    match_params.append(contains)
    if spec.artifact_id_col:
        match_parts.append(f"{spec.artifact_id_col}::text LIKE %s")
        match_params.append(contains)

    where_parts = ["e.tenant_id = %s", "(" + " OR ".join(match_parts) + ")"]
    params: list[Any] = [str(tenant_id), *match_params]
    if workspace_id is not None:
        where_parts.append(f"{spec.workspace_col} = %s")
        params.append(str(workspace_id))

    sql = f"""
        SELECT
            e.id,
            {spec.workspace_col},
            COALESCE({spec.title_col}, '') AS title,
            {spec.description_col} AS description,
            {score_sql} AS relevance_score,
            {_custom_fields_select(spec)} AS custom_fields
        FROM {spec.table} e
        {spec.join_sql}
        WHERE {' AND '.join(where_parts)}
        ORDER BY relevance_score DESC, e.created_at DESC
        LIMIT {_MAX_LEXICAL_ROWS_PER_TYPE}
    """
    final_params = case_params + params

    try:
        with connection.cursor() as cursor:
            cursor.execute(sql, final_params)
            return _rows_to_hits(cursor.fetchall(), entity_type, _normalize_lexical_score)
    except Exception:
        logger.exception(
            "SearchService: lexical SQL error entity_type=%s", entity_type
        )
        # REQ-L3-SEARCH-009: degrade gracefully — a broken lexical pass must
        # never take the full-text results down with it.
        return []


# ---------- #1965 performance helpers ----------


def _embedding_timeout_seconds() -> float:
    """Return the hard deadline for query-embedding generation, in seconds.

    Any unparseable / non-positive value falls back to the safe default, so a
    mistyped env var can neither disable the timeout (hang) nor make every
    search degrade (0s deadline).
    """
    raw = os.environ.get(_SEARCH_EMBEDDING_TIMEOUT_ENV)
    if raw is None:
        return _SEARCH_EMBEDDING_TIMEOUT_DEFAULT
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return _SEARCH_EMBEDDING_TIMEOUT_DEFAULT
    return value if value > 0 else _SEARCH_EMBEDDING_TIMEOUT_DEFAULT


def _semantic_candidate_limit(page: int, limit: int) -> int:
    """Per-type semantic candidate pool for a ``page``/``limit`` window.

    Bounded by the requested window (with _SEMANTIC_OVERFETCH_FACTOR margin)
    and capped at the historical _SEMANTIC_TOP_K, so a small page no longer
    fetches 50 rows per embeddable type while a large page is unchanged.
    ``limit`` is already validated to [1, _MAX_LIMIT] by ``search()``.
    """
    return min(
        _SEMANTIC_TOP_K,
        max(page * limit * _SEMANTIC_OVERFETCH_FACTOR, _SEMANTIC_MIN_TOP_K),
    )


def _generate_query_embedding(
    query: str, tenant_id: Any | None = None
) -> tuple[list[float] | None, str | None]:
    """Generate the query vector without blocking the request thread past the
    #1965 deadline.

    Mirrors the established REQ-084 sync-timeout seam in
    ``llm_adapter.router``: the (synchronous, provider-owned) embed call runs
    in a one-shot worker thread, the request thread waits at most
    :func:`_embedding_timeout_seconds`, and the abandoned worker is never
    joined (``shutdown(wait=False, cancel_futures=True)``). On expiry the
    future is cancelled and ``None`` is returned, which makes the caller serve
    the keyword legs only -- no exception escapes into the search path.

    The active tenant is re-armed in the worker (both the thread-local
    ``TenantContext`` and the connection's ``app.current_tenant`` RLS GUC)
    because ``generate_embedding`` resolves its configuration through the
    best-effort SystemMemorySettings lookup.
    """
    timeout = _embedding_timeout_seconds()

    def _call() -> list[float] | None:
        if tenant_id is not None:
            from persistence.middleware import (
                clear_request_tenant,
                set_request_tenant,
            )

            set_request_tenant(tenant_id)
        try:
            return generate_embedding(query)
        finally:
            if tenant_id is not None:
                clear_request_tenant()

    started = time.perf_counter()
    pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="search-embed")
    try:
        future = pool.submit(_call)
        try:
            return future.result(timeout=timeout), None
        except FutureTimeoutError:
            future.cancel()
            logger.warning(
                "artifact.search: query embedding timed out after %.3fs "
                "(query_len=%d); degrading to keyword-only result legs.",
                timeout,
                len(query),
            )
            return None, DEGRADED_EMBEDDING_TIMEOUT
        except Exception:  # embedding must never fail a search
            logger.exception(
                "artifact.search: query embedding failed; degrading to keyword-only."
            )
            return None, DEGRADED_EMBEDDING_FAILED
        finally:
            logger.debug(
                "artifact.search timing: embedding_ms=%.1f timeout_s=%.3f",
                (time.perf_counter() - started) * 1000.0,
                timeout,
            )
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


# ---------- Service ----------


class SearchService(ServiceBase):
    """Full-text search across domain entity types.

    COMP-AS-010. REQ-L3-SEARCH-001..009.

    Usage::

        svc = SearchService()
        result = svc.search(
            query="authentication",
            ctx=auth_ctx,
            workspace_id=ws_uuid,
            type_filter=["Requirement"],
            page=1,
            limit=20,
        )
        for hit in result.results:
            print(hit.title, hit.relevance_score)
    """

    def search(
        self,
        query: str,
        ctx: AuthContext,
        workspace_id: UUID | str | None = None,
        type_filter: list[str] | None = None,
        page: int = _DEFAULT_PAGE,
        limit: int = _DEFAULT_LIMIT,
        scope: str = "workspace",
        min_score: float = 0.0,
        mode: str = "hybrid",
        include_outdated: bool = False,
    ) -> SearchResult:
        """Execute the search and return ranked, paginated results.

        Combines the full-text and the lexical pass per entity type (#345):
        an artifact whose title, uid or ID literally contains *query* is
        always returned. In ``hybrid`` mode an artifact whose title or uid/ID
        is an *exact* match is pinned above the fused ranking with
        ``relevance_score == 1.0`` (T-A3-2) — so the readable identifier a
        user typed comes first even when a semantically closer neighbour would
        otherwise win the RRF tiebreaker.

        Pinning is **conditional, not absolute** (review finding F4): it is part
        of the RRF path, so it applies only when the semantic pass contributes
        at least one hit for that entity type. Without a semantic hit — the type
        has no embedding column, no embedding provider is configured, or
        ``mode`` is ``"keyword"``/``"vector"`` — no pin is applied and no score
        of 1.0 is forced. That is not a gap: on that path the pre-Task-9
        max-score merge (:func:`_merge_hits`) already ranks a lexical hit
        (normalized >= 0.5) above any full-text hit.

        REQ-L3-SEARCH-002 (query parsing), REQ-L3-SEARCH-003 (ranking),
        REQ-L3-SEARCH-004 (type filter), REQ-L3-SEARCH-005 (tenant/workspace),
        REQ-L3-SEARCH-006 (pagination), REQ-L3-SEARCH-007 (annotation).

        Args:
            query: User-supplied search string.
            ctx: AuthContext (tenant + workspace isolation).
            workspace_id: Optional workspace UUID filter. Ignored when
                ``scope="tenant"``.
            type_filter: Optional list of entity types to search.
            page: Page number (1-based, default 1).
            limit: Page size (default 20, max 100).
            scope: ``"workspace"`` (default, unchanged behaviour: filters to
                ``workspace_id`` if given, else the whole tenant with no RBAC
                narrowing) or ``"tenant"`` (new: searches every workspace
                ``ctx.user_id`` has an active role in, via
                ``AuthorizationService.accessible_workspace_ids()`` --  an
                explicit ``workspace_id`` is ignored in this mode, since
                ``scope="tenant"`` means "all my workspaces", not one).
            mode: ``"hybrid"`` (default, unchanged behaviour), ``"keyword"``
                (full-text + lexical only, no embedding call) or ``"vector"``
                (semantic only; types without an embedding column return
                nothing). Any other value raises :class:`ValidationError`
                (A-L11: no silent ignore).
            min_score: Optional relevance floor (issue #1170). ``0.0``
                (default) applies no filtering -- every match is returned, as
                before. A value ``> 0`` drops every hit whose
                ``relevance_score`` is below it *after* the global ranking and
                *before* ``total_count`` and pagination, so ``total_count``
                reflects the filtered result set and the page window is taken
                from that set. Must be in ``[0, 1]``. **Backend-dependent under
                Qdrant**: there a hybrid query's semantic leg is an RRF *fused*
                score (a rank quantity, not a cosine similarity -- see
                ``vector_port.VectorHit``), so the same floor keeps a different
                number of semantically matched hits than on pgvector. It
                remains stable within one backend and deployment.
            include_outdated: P6 / D13: ``False`` (default) excludes every hit
                whose entity/backing artifact is soft-deleted
                (``Artifact.lifecycle_status == "outdated"``); ``True`` includes
                them. ``outdated`` (bool) is the filter axis and is set on every
                hit; ``status`` is display-only: the projected workflow status,
                resolved for the returned page, ``"outdated"`` for a kept
                outdated hit. Filtering happens after all ranking pieces are
                merged and *before* ``total_count``/pagination, so counts
                reflect the visible set; a failing outdated lookup drops that
                type's hits (fail-closed, WARNING) instead of leaking them.
                **Deliberate behaviour change** (Plan D13): before P6 outdated
                hits were returned by default for most types.
                **Known limitation (F4)**: on Qdrant and on the degraded
                pgvector fallback, the semantic leg discards outdated rows
                unconditionally
                (:func:`application.vector_port.hydrate_vector_hits`), so
                ``include_outdated=True`` restores an outdated hit there only
                when a keyword leg also matched it. On pgvector all legs feed
                this filter and every outdated hit is restored.

        Returns:
            SearchResult with ranked hits and pagination metadata, plus the
            T-A2-7 serving metadata (``vector_backend``/``degraded``/
            ``degraded_reason``) that reports a pgvector fallback
            (``qdrant_unavailable``) or a partial cross-type semantic leg
            (``cross_type_query_failed``).

        Raises:
            ValidationError: Empty query, invalid type, or invalid page params.
        """
        self._set_tenant_context(ctx)

        # Validate pagination (REQ-L3-SEARCH-006)
        if page < 1:
            raise ValidationError("page must be >= 1.")
        if limit < 1 or limit > _MAX_LIMIT:
            raise ValidationError(f"limit must be between 1 and {_MAX_LIMIT}.")

        # Validate the optional relevance floor (issue #1170). Coerce first so
        # a non-numeric value from a direct caller degrades to a validation
        # error instead of a TypeError surfacing as INTERNAL_ERROR.
        try:
            min_score = float(min_score)
        except (TypeError, ValueError):
            raise ValidationError("min_score must be a number in [0, 1].") from None
        if min_score < 0.0 or min_score > 1.0:
            raise ValidationError("min_score must be in [0, 1].")

        # T-A3-1 (A-L11): an unknown mode is a caller error, never a silent
        # fallback to hybrid.
        if mode not in {"hybrid", "keyword", "vector"}:
            raise ValidationError(
                "mode must be one of 'hybrid', 'keyword', 'vector'."
            )

        # Validate type filter (REQ-L3-SEARCH-004)
        effective_types: list[str]
        if type_filter:
            invalid = set(type_filter) - _VALID_TYPES
            if invalid:
                raise ValidationError(
                    f"Invalid type_filter values: {sorted(invalid)}. "
                    f"Allowed: {sorted(_VALID_TYPES)}"
                )
            effective_types = list(type_filter)
        else:
            effective_types = sorted(_VALID_TYPES)

        # Parse query (REQ-L3-SEARCH-002)
        try:
            tsquery_str = QueryParser.parse(query)
        except ValidationError:
            raise
        except Exception as exc:
            raise ValidationError(f"Failed to parse search query: {exc}") from exc

        tenant_id = ctx.tenant_id
        hits: list[SearchHit] = []

        # Task 9 (REQ-L2-VS-004): computed once here, not per entity type --
        # generate_embedding() never raises (its own contract: returns None on
        # any provider error, e.g. no SDK installed or a dimension mismatch it
        # can detect itself), so this is safe even when no embedding provider
        # is configured. Still, gate it on effective_types actually containing
        # an embeddable type: generate_embedding() is not free in general (a
        # real network round-trip for the openai provider, model inference for
        # sentence-transformers) -- a caller with e.g. type_filter=["TestCase"]
        # (no embedding column at all) must not pay that cost just because
        # Requirement/TraceLink/Icd exist elsewhere in the codebase.
        # T-A2-7: ONE port per request, so the degraded flag aggregates over
        # every entity type instead of being reset per type.
        port = get_fallback_vector_port()

        query_embedding: list[float] | None = None
        # ``keyword`` makes no embedding call at all (T-A3-1); ``hybrid`` and
        # ``vector`` share the single computed vector.
        #
        # T-A2-6: in Qdrant mode the vector is also needed for the types WITHOUT
        # an embedding column (``query_entities``), so the gate widens there --
        # and ONLY there: a pgvector deployment keeps its exact behaviour (no
        # embedding call when the filter holds no embeddable type).
        needs_entity_semantics = port.supports_entity_queries and bool(effective_types)
        search_started = time.perf_counter()
        semantic_limit = _semantic_candidate_limit(page, limit)
        if mode != "keyword" and (
            (_EMBEDDABLE_TYPES & set(effective_types)) or needs_entity_semantics
        ):
            query_embedding, embedding_degradation = _generate_query_embedding(
                query, tenant_id=tenant_id
            )
            if embedding_degradation is not None:
                # Timeout / provider error: the vector leg is gone. Hybrid
                # already falls back to the plain fulltext+lexical merge when
                # no semantic hit exists; make that degradation visible on
                # the wire (T-A2-7). A provider that is merely not configured
                # still returns None with NO token, preserving the old wire
                # contract for that steady state.
                mark_request_degraded(port, embedding_degradation)

        if scope == "tenant":
            # scope="tenant" means "every workspace I'm allowed to see", so an
            # explicit workspace_id (if one was also passed) is ignored.
            from auth_tenancy.services.authorization import AuthorizationService

            accessible_ids = AuthorizationService().accessible_workspace_ids(
                user_id=ctx.user_id, tenant_id=tenant_id
            )
            hits = self._search_multi_workspace(
                entity_types=effective_types,
                tsquery_str=tsquery_str,
                tenant_id=tenant_id,
                workspace_ids=accessible_ids,
                raw_query=query,
                query_embedding=query_embedding,
                mode=mode,
                ctx=ctx,
                port=port,
                semantic_limit=semantic_limit,
            )
        else:
            ws_uuid: UUID | None = (
                UUID(str(workspace_id)) if workspace_id is not None else None
            )
            port_hits = self._port_entity_hits(
                port,
                tenant_id=tenant_id,
                workspace_id=ws_uuid,
                query_embedding=query_embedding,
                query_text=query,
                entity_types=effective_types,
                ctx=ctx,
                mode=mode,
                semantic_limit=semantic_limit,
            )

            # Execute per-type queries and merge
            for entity_type in effective_types:
                try:
                    type_hits = self._search_entity_type(
                        entity_type=entity_type,
                        tsquery_str=tsquery_str,
                        tenant_id=tenant_id,
                        workspace_id=ws_uuid,
                        raw_query=query,
                        query_embedding=query_embedding,
                        mode=mode,
                        ctx=ctx,
                        port=port,
                        port_semantic_hits=port_hits.get(entity_type),
                        semantic_limit=semantic_limit,
                    )
                    hits.extend(type_hits)
                except Exception:
                    logger.exception(
                        "SearchService: error searching entity_type=%s query=%r",
                        entity_type,
                        tsquery_str,
                    )
                    # REQ-L3-SEARCH-009: degrade gracefully (empty results for failed type)

        # P6 / D13: ONE lifecycle filter for every type, applied after all legs
        # are merged and before ranking/total_count/pagination. Outdated hits are
        # excluded by default; ``include_outdated=True`` keeps them and marks
        # them ``outdated=True``. F1: fail-closed — see the helper.
        hits = _filter_outdated_hits(
            hits, include_outdated=include_outdated, tenant_id=tenant_id
        )

        # Sort by relevance DESC. Every score is normalized to [0, 1] at the
        # point of creation (issue #827): lexical hits occupy [0.5, 1.0] and
        # therefore land above full-text hits in practice.
        #
        # The key is deliberately a *total* order, in this precedence:
        #   1. relevance DESC
        #   2. pinned first (T-A3-2 / review finding F1) — a pin cannot rely on
        #      its score alone: _rrf_fuse normalizes by its theoretical maximum,
        #      so an unpinned hit ranked 0 in all three lists also scores 1.0
        #      and would otherwise be separated only by the title.
        #   3. title ASC — stable tiebreaker across entity types (the per-type
        #      SQL already orders by created_at).
        #   4. entity id ASC — final, unique tiebreaker (review finding F2,
        #      DoD "Tiebreaker eindeutig"): two hits with the same score *and*
        #      title would otherwise be ordered by dict/INSERT order, making the
        #      emitted ranking non-reproducible across identical calls.
        hits.sort(key=lambda h: (-h.relevance_score, not h.pinned, h.title, h.id))

        # Optional relevance floor (issue #1170): applied AFTER the global
        # ranking and BEFORE total_count/pagination, so total_count mirrors
        # the hits a caller actually gets and the page window is a slice of
        # the filtered set. ``min_score == 0`` is the "no filtering" default.
        if min_score > 0.0:
            hits = [hit for hit in hits if hit.relevance_score >= min_score]

        total_count = len(hits)

        # Apply pagination (REQ-L3-SEARCH-006)
        offset = (page - 1) * limit
        page_hits = hits[offset : offset + limit]

        # P6 / D13 / F2: the workflow ``status`` is display-only and resolved
        # for the final page window only (≤ limit ≤ 100 hits, one batched
        # projection per type actually present), never per corpus hit.
        page_hits = _annotate_hit_status(page_hits, tenant_id=tenant_id)

        # #1965 timing instrumentation: one structured line per request so a
        # regression to the 23-30s path is diagnosable without a profiler.
        logger.debug(
            "artifact.search timing: mode=%s types=%d total_ms=%.1f "
            "page=%d limit=%d semantic_limit=%d hits=%d",
            mode,
            len(effective_types),
            (time.perf_counter() - search_started) * 1000.0,
            page,
            limit,
            semantic_limit,
            total_count,
        )
        return SearchResult(
            results=page_hits,
            total_count=total_count,
            page=page,
            limit=limit,
            query=tsquery_str,
            degraded=port.degraded,
            vector_backend=port.vector_backend,
            degraded_reason=port.degraded_reason,
        )

    # ---------- Per-type search ----------

    @staticmethod
    def _search_entity_type(
        entity_type: str,
        tsquery_str: str,
        tenant_id: Any,
        workspace_id: UUID | None,
        raw_query: str = "",
        query_embedding: list[float] | None = None,
        mode: str = "hybrid",
        ctx: AuthContext | None = None,
        port: Any = None,
        port_semantic_hits: list[SearchHit] | None = None,
        semantic_limit: int | None = None,
    ) -> list[SearchHit]:
        """Return hits for one entity type from all applicable search passes.

        Runs the tsvector full-text pass (REQ-L3-SEARCH-001/003), the lexical
        title/uid/id pass (#345 Finding 2), and -- for entity types with an
        ``embedding`` column (Task 9, REQ-L2-VS-004) -- a cosine-similarity
        semantic pass, then combines them.

        Fusion (Task 9): when the semantic pass contributes at least one hit,
        all three passes are combined via Reciprocal Rank Fusion
        (:func:`_rrf_fuse`). Otherwise (no embedding column for this type, no
        embedding provider configured, or a dimension mismatch -- see
        :func:`_run_semantic_query`) this falls back to the pre-Task-9
        max-score merge (:func:`_merge_hits`), unchanged: normalized lexical
        scores lie in [0.5, 1.0] (see :func:`_normalize_lexical_score`) while
        full-text ts_rank scores are far below that in practice, so an exact
        or substring title match always wins over a weak full-text match. See
        :func:`_rrf_fuse`'s docstring for why the two are not unconditionally
        unified into one algorithm.

        Pinning (T-A3-2, A-L21): under RRF an *exact* identifier match (the
        exact-title / exact-uid / exact-ID lexical tiers, i.e. a normalized
        lexical score >= :data:`_PIN_MIN_NORMALIZED_LEXICAL_SCORE`) used to be
        flattened to the same 1/61 contribution as any single-list semantic
        hit, after which the alphabetical title tiebreaker could push it to
        rank 2. Those hits are lifted out of all three RRF lists and placed in
        front with ``relevance_score == 1.0``; they appear exactly once. They
        also carry :attr:`SearchHit.pinned`, because 1.0 is *not* unique to a
        pin — an unpinned hit at rank 0 in all three lists reaches it too (see
        :attr:`SearchHit.pinned` and ``search()``'s sort key).

        ``ctx`` only feeds the T-A3-3 per-hit visibility of the
        ``permission_scoped`` types (:func:`_apply_row_visibility`).

        IF-AS-EXT-OUT-007: raw SQL via django.db.connection backs the
        fulltext/lexical passes. Only the three tables that carry the
        ``to_tsvector('german', title || ' ' || description)`` expression index
        (Requirement, ArchitectureElement, TestCase) are actually
        index-accelerated by it. TraceLink and Icd deliberately scan
        unindexed — T-A3-4 measures that cost; their full-text pass is bounded
        by :data:`_MAX_LEXICAL_ROWS_PER_TYPE` for the same reason (findings F3
        and F5). The semantic pass uses the Django ORM (see
        :func:`_run_semantic_query`).

        SQL-injection safety: every user-supplied value (tsquery string,
        lexical pattern, tenant/workspace UUID) is parameterized via %s; only
        module-owned identifiers from ``_TABLE_SPECS`` are interpolated.
        """
        spec = _TABLE_SPECS.get(entity_type)
        if spec is None:
            return []

        if mode != "keyword":
            semantic_hits = _run_semantic_query(
                entity_type,
                query_embedding,
                tenant_id,
                workspace_id,
                port=port,
                query_text=raw_query,
                ctx=ctx,
                semantic_limit=semantic_limit,
            )
            # T-A2-6: types WITHOUT an embedding column get their semantic hits
            # from the port's cross-type query (Qdrant only; empty otherwise).
            if port_semantic_hits:
                semantic_hits = semantic_hits + list(port_semantic_hits)
        else:
            semantic_hits = []

        if mode == "vector":
            # Semantic only: a type without an embedding column (or a query
            # with no vector) simply contributes nothing.
            return _apply_row_visibility(entity_type, semantic_hits, ctx)

        fulltext_hits = _run_fulltext_query(entity_type, spec, tsquery_str, tenant_id, workspace_id)
        lexical_hits = _run_lexical_query(entity_type, spec, raw_query, tenant_id, workspace_id)
        if mode == "keyword":
            return _apply_row_visibility(
                entity_type, _merge_hits(fulltext_hits, lexical_hits), ctx
            )

        fused: list[SearchHit]
        if semantic_hits:
            pinned = [
                hit
                for hit in lexical_hits
                if hit.relevance_score >= _PIN_MIN_NORMALIZED_LEXICAL_SCORE
            ]
            if pinned:
                pinned_ids = {hit.id for hit in pinned}
                fused = [
                    dataclass_replace(hit, relevance_score=1.0, pinned=True)
                    for hit in pinned
                ] + _rrf_fuse(
                    [hit for hit in lexical_hits if hit.id not in pinned_ids],
                    [hit for hit in fulltext_hits if hit.id not in pinned_ids],
                    [hit for hit in semantic_hits if hit.id not in pinned_ids],
                )
            else:
                fused = _rrf_fuse(lexical_hits, fulltext_hits, semantic_hits)
        else:
            fused = _merge_hits(fulltext_hits, lexical_hits)
        return _apply_row_visibility(entity_type, fused, ctx)

    @staticmethod
    def _port_entity_hits(
        port: Any,
        *,
        tenant_id: Any,
        workspace_id: UUID | None,
        query_embedding: list[float] | None,
        query_text: str,
        entity_types: list[str],
        ctx: AuthContext | None,
        mode: str = "hybrid",
        semantic_limit: int | None = None,
    ) -> dict[str, list[SearchHit]]:
        """Cross-type semantic hits for the types WITHOUT an embedding column.

        T-A2-6 (counter-check to A-L19): StakeholderNeed, Adr, Risk, ... have no
        ``embedding`` column, so the pgvector pass can never reach them. In
        Qdrant mode the artifact index does, and ``query_entities`` returns them
        already hydrated (QR-S07: ORM row, workspace filter, READ check) with
        the title/description read from the row.

        ``{}`` on a pgvector deployment (``supports_entity_queries`` False) and
        when no workspace scope exists -- which keeps the default path
        byte-identical. A failure degrades to ``{}`` (REQ-L3-SEARCH-009) and is
        reported: the request served *partial* semantic results, which must not
        look complete, so the port is flagged with
        ``degraded_reason="cross_type_query_failed"`` (distinct from the
        ``qdrant_unavailable`` outage token -- no fallback happened here and
        ``vector_backend`` still names the backend that served the other legs).
        """
        if (
            mode == "keyword"
            or workspace_id is None
            or not getattr(port, "supports_entity_queries", False)
            or query_embedding is None
        ):
            return {}
        requested = [t for t in entity_types if t not in _EMBEDDABLE_TYPES]
        if not requested:
            return {}
        # Follow-ups (deliberately NOT part of this PR, tracked for PR-A21b):
        #   * One round-trip per type x workspace: this fan-out runs inside
        #     ``_search_multi_workspace``'s per-entity-type x per-workspace loop,
        #     so ``scope="tenant"`` costs ``len(types) * len(workspaces)``
        #     cross-type queries. A single workspace-scoped ``query_entities``
        #     call per workspace (requesting every type at once) would collapse
        #     it -- ``query_entities`` already accepts a list of ``entity_types``.
        #   * Hydration is already single-pass in this method: ``query_entities``
        #     resolves the ORM row under ``_hydrate_rows`` (ids + workspace fence
        #     + item-level READ + ``OUTDATED``) and returns ``TypedVectorHit``
        #     values that already carry title/description/workspace, so the loop
        #     below builds the ``SearchHit`` DTOs straight from them -- there is
        #     no second re-fetch here. (An earlier version of this note claimed
        #     cross-type results were re-fetched via ``_semantic_search_hits``;
        #     they are not.) The id-and-distance re-fetch in
        #     ``_semantic_search_hits`` belongs to the SINGLE-type embeddable
        #     path (Requirement/TraceLink/Icd): ``query_similar`` returns only
        #     ids + cosine distances, so those rows must be reloaded to build
        #     the DTO -- a necessary, separate step, not duplicate work here.
        #   * SECURITY ASYMMETRY in the lexical/full-text legs: they apply no
        #     item-level ``none`` filter for Requirement/ArchitectureElement/
        #     TestCase/StakeholderNeed (``_apply_row_visibility`` only covers
        #     Icd/TraceLink). That is a known gap of the DEFAULT pgvector path
        #     (A3-3), not a cost saving -- a user denied an item through an
        #     item-level rule can still see it in a lexical/full-text hit today.
        #     Named explicitly so this follow-up is not read as "no action".
        try:
            typed_hits: list[TypedVectorHit] = port.query_entities(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                query_vector=query_embedding,
                query_text=query_text,
                entity_types=requested,
                # #1965: same bounded pool as the single-type leg; ``None``
                # keeps direct callers on the historical fixed 50.
                limit=semantic_limit if semantic_limit is not None else _SEMANTIC_TOP_K,
                ctx=ctx,
            )
        except Exception:
            logger.exception("SearchService: cross-type semantic query error")
            # Partial semantic results must be reported as such (T-A2-7): the
            # hits of the other legs are still served, so this is a degradation,
            # not an error response -- and silence here made a Qdrant-side
            # failure indistinguishable from "this backend has no cross-type
            # index" on the wire.
            mark_request_degraded(port, DEGRADED_CROSS_TYPE_QUERY_FAILED)
            return {}

        grouped: dict[str, list[SearchHit]] = {}
        for hit in typed_hits:
            grouped.setdefault(hit.entity_type, []).append(
                SearchHit(
                    id=str(hit.id),
                    artifact_type=hit.entity_type,
                    title=hit.title,
                    description=hit.description,
                    relevance_score=_normalize_cosine_similarity(float(hit.distance)),
                    workspace_id=str(hit.workspace_id) if hit.workspace_id else "",
                )
            )
        return grouped

    @classmethod
    def _search_multi_workspace(
        cls,
        entity_types: list[str],
        tsquery_str: str,
        tenant_id: Any,
        workspace_ids: list[UUID],
        raw_query: str,
        query_embedding: list[float] | None = None,
        mode: str = "hybrid",
        ctx: AuthContext | None = None,
        port: Any = None,
        semantic_limit: int | None = None,
    ) -> list[SearchHit]:
        """Search every type in ``entity_types`` across all ``workspace_ids``.

        Used for ``scope="tenant"``: runs the same per-type fusion
        :meth:`_search_entity_type` already runs for a single workspace
        (fulltext + lexical, plus the Task 9 semantic pass where applicable --
        ``query_embedding`` is the same one computed once in
        :meth:`search` and threaded through unchanged per workspace, since it
        depends only on the query text, not the workspace), once per
        accessible workspace, then merges the per-workspace results with the
        same id-keyed/max-score dedup rule (:func:`_merge_hits`) -- a proper
        cross-workspace merge, not just the existing two-pass merge repeated
        in isolation per workspace.

        An empty ``workspace_ids`` (caller has no accessible workspace) yields
        no hits for any type, by construction.
        """
        hits: list[SearchHit] = []
        for entity_type in entity_types:
            per_workspace_hits: list[list[SearchHit]] = []
            for ws_id in workspace_ids:
                try:
                    port_hits = cls._port_entity_hits(
                        port,
                        tenant_id=tenant_id,
                        workspace_id=ws_id,
                        query_embedding=query_embedding,
                        query_text=raw_query,
                        entity_types=[entity_type],
                        ctx=ctx,
                        mode=mode,
                        semantic_limit=semantic_limit,
                    )
                    per_workspace_hits.append(
                        cls._search_entity_type(
                            entity_type=entity_type,
                            tsquery_str=tsquery_str,
                            tenant_id=tenant_id,
                            workspace_id=ws_id,
                            raw_query=raw_query,
                            query_embedding=query_embedding,
                            mode=mode,
                            ctx=ctx,
                            port=port,
                            port_semantic_hits=port_hits.get(entity_type),
                            semantic_limit=semantic_limit,
                        )
                    )
                except Exception:
                    # A failure querying ONE accessible workspace must not
                    # discard already-gathered hits from the OTHER accessible
                    # workspaces for this same entity type -- REQ-L3-SEARCH-009
                    # degrade-gracefully applies per workspace here, not per
                    # entity type (unlike the single-workspace path in
                    # search(), where "per type" and "per query" coincide).
                    logger.exception(
                        "SearchService: error searching entity_type=%s "
                        "workspace_id=%s query=%r (tenant scope)",
                        entity_type,
                        ws_id,
                        tsquery_str,
                    )
            hits.extend(_merge_hits(*per_workspace_hits))
        return hits


__all__ = [
    "SEARCHABLE_ARTIFACT_TYPES",
    "QueryParser",
    "SearchHit",
    "SearchResult",
    "SearchService",
]
