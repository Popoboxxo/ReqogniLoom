"""
COMP-AS-010 SearchService — PostgreSQL Full-Text Search.

leaf_id : COMP-AS-010
req_id  : REQ-L1-020, REQ-L3-SEARCH-001 through REQ-L3-SEARCH-009

Search over every artifact type listed in ``SEARCHABLE_ARTIFACT_TYPES``
(Requirement, ArchitectureElement, TestCase, StakeholderNeed, Adr, Risk,
Issue, ChangeRequest, Goal, GlossaryTerm). Two passes run per type and are
merged (issue #345):

  1. semantic: PostgreSQL tsvector / tsquery, relevance-ranked via ts_rank
  2. lexical:  case-insensitive substring match on title, uid and IDs

Pass 2 exists because ``plainto_tsquery`` lexemizes its input, so literal
identifiers ("QA-AI", "00436a35") were previously unfindable. Lexical hits
always rank above full-text hits. Both passes enforce workspace and tenant
isolation. Supports type filtering, pagination, and safe query parsing.

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
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from uuid import UUID

from auth_tenancy.context import AuthContext

# Backward-compat alias used by tests that patch 'application.search_service.TenantContext'
TenantContext = AuthContext

from application.base import ServiceBase, ValidationError

logger = logging.getLogger(__name__)

# ---------- Constants ----------

_DEFAULT_PAGE = 1
_DEFAULT_LIMIT = 20
_MAX_LIMIT = 100

# #345 Finding 2: a lexical hit always outranks a full-text hit. ts_rank()
# with default weights stays well below 1.0 in practice (the QA report saw
# 0.06 for a semantic match), so putting every lexical tier above 1.0 makes
# "the title literally contains what you typed" a strictly stronger signal
# than any tsvector score — without needing to normalize ts_rank.
_SCORE_TITLE_EXACT = 3.0
_SCORE_ID_EXACT = 2.9
_SCORE_TITLE_PREFIX = 2.5
_SCORE_TITLE_SUBSTRING = 2.0
_SCORE_ID_SUBSTRING = 1.5

# A single character would substring-match nearly every row; below this the
# lexical pass is skipped and only the full-text pass runs.
_MIN_LEXICAL_QUERY_LEN = 2

# The lexical pass has no supporting index (ILIKE '%x%' cannot use the FTS
# GIN index), so a very generic needle could otherwise stream a whole table
# into memory. Capping per type bounds the cost; the full-text pass — the
# relevance-ranked one — stays uncapped, as before.
_MAX_LEXICAL_ROWS_PER_TYPE = 200


@dataclass(frozen=True)
class _TableSpec:
    """Physical mapping of a searchable artifact type.

    ``title_col``/``description_col``/``workspace_col`` are trusted SQL
    fragments defined in this module only — never built from user input.
    """

    table: str
    title_col: str = "e.title"
    description_col: str = "COALESCE(e.description, '')"
    join_sql: str = ""
    workspace_col: str = "e.workspace_id"
    uid_col: Optional[str] = "e.uid"
    artifact_id_col: Optional[str] = None


_ARTIFACT_JOIN = "JOIN pl_artifact a ON a.id = e.artifact_id"

# Every artifact type ``artifact.search`` can return (#345 Finding 2b: the
# type_filter enum used to allow only the first three, so Needs/Goals/ADRs
# were unfilterable even though they are searchable).
#
# Deliberately excluded:
#   MainGoal — has no title, only a single aggregated ``content`` blob per
#   workspace; it is a derived summary, not an addressable artifact.
_TABLE_SPECS: Dict[str, _TableSpec] = {
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
    # Artifact FK is nullable (added later, additive migration), so joining
    # pl_artifact would silently drop pre-existing rows.
    "Adr": _TableSpec(table="as_adr", artifact_id_col="e.artifact_id"),
    "Risk": _TableSpec(table="as_risk", artifact_id_col="e.artifact_id"),
    "Issue": _TableSpec(table="as_issue", artifact_id_col="e.artifact_id"),
    "ChangeRequest": _TableSpec(table="as_change_request", uid_col=None),
    "Goal": _TableSpec(
        table="as_goal", uid_col=None, artifact_id_col="e.artifact_id"
    ),
    "GlossaryTerm": _TableSpec(
        table="pl_glossary_term",
        title_col="e.term",
        description_col="COALESCE(e.definition, '')",
        uid_col=None,
    ),
}

_VALID_TYPES = set(_TABLE_SPECS)

#: Public, stable view of the searchable artifact types — the single source
#: of truth for the ``type_filter`` enum published by MCP ``artifact.search``.
SEARCHABLE_ARTIFACT_TYPES: frozenset[str] = frozenset(_TABLE_SPECS)

# ---------- DTOs ----------


@dataclass
class SearchHit:
    """Single search result item."""

    id: str
    artifact_type: str  # "Requirement" | "ArchitectureElement" | "TestCase"
    title: str
    description: str
    relevance_score: float
    workspace_id: str


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

    results: List[SearchHit]
    total_count: int
    page: int
    limit: int
    query: str = ""


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


def _merge_hits(*hit_lists: List[SearchHit]) -> List[SearchHit]:
    """Dedup ``hit_lists`` by ``hit.id``, keeping the highest relevance score.

    Shared by :meth:`SearchService._search_entity_type`'s two-pass
    (full-text + lexical) merge and :meth:`SearchService._search_multi_workspace`'s
    per-workspace merge -- same "keyed by id, keep max score" pattern either way.
    """
    merged: Dict[str, SearchHit] = {}
    for hits in hit_lists:
        for hit in hits:
            existing = merged.get(hit.id)
            if existing is None or hit.relevance_score > existing.relevance_score:
                merged[hit.id] = hit
    return list(merged.values())


def _rows_to_hits(rows: Any, entity_type: str) -> List[SearchHit]:
    """Map ``(id, workspace_id, title, description, score)`` rows to hits."""
    return [
        SearchHit(
            id=str(eid),
            artifact_type=entity_type,
            title=title or "",
            description=description or "",
            relevance_score=float(score),
            workspace_id=str(ws_id) if ws_id is not None else "",
        )
        for eid, ws_id, title, description, score in rows
    ]


def _run_fulltext_query(
    entity_type: str,
    spec: _TableSpec,
    tsquery_str: str,
    tenant_id: Any,
    workspace_id: Optional[UUID],
) -> List[SearchHit]:
    """tsvector/ts_rank pass for one entity type (REQ-L3-SEARCH-001/003)."""
    from django.db import connection

    tsv = (
        f"to_tsvector('german', COALESCE({spec.title_col}, '') || ' ' "
        f"|| {spec.description_col})"
    )

    where_parts = ["e.tenant_id = %s", f"{tsv} @@ plainto_tsquery('german', %s)"]
    params: List[Any] = [str(tenant_id), tsquery_str]
    if workspace_id is not None:
        where_parts.append(f"{spec.workspace_col} = %s")
        params.append(str(workspace_id))

    sql = f"""
        SELECT
            e.id,
            {spec.workspace_col},
            COALESCE({spec.title_col}, '') AS title,
            {spec.description_col} AS description,
            ts_rank({tsv}, plainto_tsquery('german', %s)) AS relevance_score
        FROM {spec.table} e
        {spec.join_sql}
        WHERE {' AND '.join(where_parts)}
        ORDER BY relevance_score DESC, e.created_at DESC
    """
    # The ts_rank parameter in the SELECT list is bound before the WHERE ones.
    final_params = [tsquery_str] + params

    try:
        with connection.cursor() as cursor:
            cursor.execute(sql, final_params)
            return _rows_to_hits(cursor.fetchall(), entity_type)
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
    workspace_id: Optional[UUID],
) -> List[SearchHit]:
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
    case_parts: List[str] = [f"WHEN {title_lower} = %s THEN {_SCORE_TITLE_EXACT}"]
    case_params: List[Any] = [needle]
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
    match_parts: List[str] = [f"{title_lower} LIKE %s"]
    match_params: List[Any] = [contains]
    if uid_lower:
        match_parts.append(f"{uid_lower} LIKE %s")
        match_params.append(contains)
    match_parts.append("e.id::text LIKE %s")
    match_params.append(contains)
    if spec.artifact_id_col:
        match_parts.append(f"{spec.artifact_id_col}::text LIKE %s")
        match_params.append(contains)

    where_parts = ["e.tenant_id = %s", "(" + " OR ".join(match_parts) + ")"]
    params: List[Any] = [str(tenant_id), *match_params]
    if workspace_id is not None:
        where_parts.append(f"{spec.workspace_col} = %s")
        params.append(str(workspace_id))

    sql = f"""
        SELECT
            e.id,
            {spec.workspace_col},
            COALESCE({spec.title_col}, '') AS title,
            {spec.description_col} AS description,
            {score_sql} AS relevance_score
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
            return _rows_to_hits(cursor.fetchall(), entity_type)
    except Exception:
        logger.exception(
            "SearchService: lexical SQL error entity_type=%s", entity_type
        )
        # REQ-L3-SEARCH-009: degrade gracefully — a broken lexical pass must
        # never take the full-text results down with it.
        return []


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
        workspace_id: Optional[UUID | str] = None,
        type_filter: Optional[List[str]] = None,
        page: int = _DEFAULT_PAGE,
        limit: int = _DEFAULT_LIMIT,
        scope: str = "workspace",
    ) -> SearchResult:
        """Execute the search and return ranked, paginated results.

        Combines the full-text and the lexical pass per entity type (#345):
        an artifact whose title, uid or ID literally contains *query* is
        always returned, and ranks above purely semantic matches.

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

        Returns:
            SearchResult with ranked hits and pagination metadata.

        Raises:
            ValidationError: Empty query, invalid type, or invalid page params.
        """
        self._set_tenant_context(ctx)

        # Validate pagination (REQ-L3-SEARCH-006)
        if page < 1:
            raise ValidationError("page must be >= 1.")
        if limit < 1 or limit > _MAX_LIMIT:
            raise ValidationError(f"limit must be between 1 and {_MAX_LIMIT}.")

        # Validate type filter (REQ-L3-SEARCH-004)
        effective_types: List[str]
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
        hits: List[SearchHit] = []

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
            )
        else:
            ws_uuid: Optional[UUID] = (
                UUID(str(workspace_id)) if workspace_id is not None else None
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
                    )
                    hits.extend(type_hits)
                except Exception:
                    logger.exception(
                        "SearchService: error searching entity_type=%s query=%r",
                        entity_type,
                        tsquery_str,
                    )
                    # REQ-L3-SEARCH-009: degrade gracefully (empty results for failed type)

        # Sort by relevance DESC (lexical hits score >= 1.5 and therefore
        # always land above full-text hits), title ASC as a stable tiebreaker
        # across entity types — the per-type SQL already orders by created_at.
        hits.sort(key=lambda h: (-h.relevance_score, h.title))

        total_count = len(hits)

        # Apply pagination (REQ-L3-SEARCH-006)
        offset = (page - 1) * limit
        page_hits = hits[offset : offset + limit]

        return SearchResult(
            results=page_hits,
            total_count=total_count,
            page=page,
            limit=limit,
            query=tsquery_str,
        )

    # ---------- Per-type search ----------

    @staticmethod
    def _search_entity_type(
        entity_type: str,
        tsquery_str: str,
        tenant_id: Any,
        workspace_id: Optional[UUID],
        raw_query: str = "",
    ) -> List[SearchHit]:
        """Return hits for one entity type from both search passes.

        Runs the tsvector full-text pass (REQ-L3-SEARCH-001/003) and the
        lexical title/uid/id pass (#345 Finding 2), then merges them keeping
        the higher score per entity ID. Lexical scores are all >= 1.5 and
        full-text ts_rank scores are far below that, so an exact or substring
        title match always wins over a weak semantic match.

        IF-AS-EXT-OUT-007: raw SQL via django.db.connection for expression
        index compatibility (GIN index on the tsvector expression).

        SQL-injection safety: every user-supplied value (tsquery string,
        lexical pattern, tenant/workspace UUID) is parameterized via %s; only
        module-owned identifiers from ``_TABLE_SPECS`` are interpolated.
        """
        spec = _TABLE_SPECS.get(entity_type)
        if spec is None:
            return []

        return _merge_hits(
            _run_fulltext_query(entity_type, spec, tsquery_str, tenant_id, workspace_id),
            _run_lexical_query(entity_type, spec, raw_query, tenant_id, workspace_id),
        )

    @classmethod
    def _search_multi_workspace(
        cls,
        entity_types: List[str],
        tsquery_str: str,
        tenant_id: Any,
        workspace_ids: List[UUID],
        raw_query: str,
    ) -> List[SearchHit]:
        """Search every type in ``entity_types`` across all ``workspace_ids``.

        Used for ``scope="tenant"``: runs the same two-pass (full-text +
        lexical) query :meth:`_search_entity_type` already runs for a single
        workspace, once per accessible workspace, then merges the per-workspace
        results with the same id-keyed/max-score dedup rule (:func:`_merge_hits`)
        -- a proper cross-workspace merge, not just the existing two-pass merge
        repeated in isolation per workspace.

        An empty ``workspace_ids`` (caller has no accessible workspace) yields
        no hits for any type, by construction.
        """
        hits: List[SearchHit] = []
        for entity_type in entity_types:
            try:
                per_workspace_hits = [
                    cls._search_entity_type(
                        entity_type=entity_type,
                        tsquery_str=tsquery_str,
                        tenant_id=tenant_id,
                        workspace_id=ws_id,
                        raw_query=raw_query,
                    )
                    for ws_id in workspace_ids
                ]
                hits.extend(_merge_hits(*per_workspace_hits))
            except Exception:
                logger.exception(
                    "SearchService: error searching entity_type=%s query=%r "
                    "(tenant scope)",
                    entity_type,
                    tsquery_str,
                )
                # REQ-L3-SEARCH-009: degrade gracefully (empty results for failed type)
        return hits


__all__ = [
    "SearchService",
    "SearchResult",
    "SearchHit",
    "QueryParser",
    "SEARCHABLE_ARTIFACT_TYPES",
]
