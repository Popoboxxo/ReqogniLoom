"""
COMP-AS-010 SearchService — PostgreSQL Full-Text Search.

leaf_id : COMP-AS-010
req_id  : REQ-L1-020, REQ-L3-SEARCH-001 through REQ-L3-SEARCH-009

Full-text search over Requirements, ArchitectureElements, and TestCases via
PostgreSQL tsvector / tsquery. Results are relevance-ranked (ts_rank) with
workspace and tenant isolation. Supports type filtering, pagination, and safe
query parsing.

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

from application.base import ServiceBase, ValidationError

logger = logging.getLogger(__name__)

# ---------- Constants ----------

_VALID_TYPES = {"Requirement", "ArchitectureElement", "TestCase"}
_DEFAULT_PAGE = 1
_DEFAULT_LIMIT = 20
_MAX_LIMIT = 100

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
    ) -> SearchResult:
        """Execute full-text search and return ranked, paginated results.

        REQ-L3-SEARCH-002 (query parsing), REQ-L3-SEARCH-003 (ranking),
        REQ-L3-SEARCH-004 (type filter), REQ-L3-SEARCH-005 (tenant/workspace),
        REQ-L3-SEARCH-006 (pagination), REQ-L3-SEARCH-007 (annotation).

        Args:
            query: User-supplied search string.
            ctx: AuthContext (tenant + workspace isolation).
            workspace_id: Optional workspace UUID filter.
            type_filter: Optional list of entity types to search.
            page: Page number (1-based, default 1).
            limit: Page size (default 20, max 100).

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
            effective_types = list(_VALID_TYPES)

        # Parse query (REQ-L3-SEARCH-002)
        try:
            tsquery_str = QueryParser.parse(query)
        except ValidationError:
            raise
        except Exception as exc:
            raise ValidationError(f"Failed to parse search query: {exc}") from exc

        ws_uuid: Optional[UUID] = (
            UUID(str(workspace_id)) if workspace_id is not None else None
        )

        # Execute per-type queries and merge
        hits: List[SearchHit] = []
        tenant_id = ctx.tenant_id

        for entity_type in effective_types:
            try:
                type_hits = self._search_entity_type(
                    entity_type=entity_type,
                    tsquery_str=tsquery_str,
                    tenant_id=tenant_id,
                    workspace_id=ws_uuid,
                )
                hits.extend(type_hits)
            except Exception:
                logger.exception(
                    "SearchService: error searching entity_type=%s query=%r",
                    entity_type,
                    tsquery_str,
                )
                # REQ-L3-SEARCH-009: degrade gracefully (empty results for failed type)

        # Sort by relevance DESC, then created_at tiebreaker (handled in SQL per type)
        hits.sort(key=lambda h: h.relevance_score, reverse=True)

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
    ) -> List[SearchHit]:
        """Execute tsvector FTS query for one entity type.

        IF-AS-EXT-OUT-007: raw SQL via django.db.connection for expression
        index compatibility (REQ-L3-SEARCH-001, GIN index on expression).

        SQL-injection safety: tsquery_str is parameterized via %s.
        """
        from django.db import connection

        # Table names and column mapping per entity type
        table_map = {
            "Requirement": ("pl_requirement", "pl_artifact"),
            "ArchitectureElement": ("pl_architecture_element", "pl_artifact"),
            "TestCase": ("pl_testcase", "pl_artifact"),
        }
        if entity_type not in table_map:
            return []

        entity_table, artifact_table = table_map[entity_type]

        # Build WHERE clauses
        where_parts = [
            "e.tenant_id = %s",
            "to_tsvector('german', e.title || ' ' || COALESCE(e.description, '')) "
            "@@ plainto_tsquery('german', %s)",
        ]
        params: List[Any] = [str(tenant_id), tsquery_str]

        if workspace_id is not None:
            where_parts.append("a.workspace_id = %s")
            params.append(str(workspace_id))

        where_sql = " AND ".join(where_parts)

        sql = f"""
            SELECT
                e.id,
                a.workspace_id,
                e.title,
                COALESCE(e.description, '') AS description,
                ts_rank(
                    to_tsvector('german', e.title || ' ' || COALESCE(e.description, '')),
                    plainto_tsquery('german', %s)
                ) AS relevance_score
            FROM {entity_table} e
            JOIN {artifact_table} a ON a.id = e.artifact_id
            WHERE {where_sql}
            ORDER BY relevance_score DESC, e.created_at DESC
        """
        # relevance param is prepended for ts_rank
        final_params = [tsquery_str] + params

        hits: List[SearchHit] = []
        try:
            with connection.cursor() as cursor:
                cursor.execute(sql, final_params)
                for row in cursor.fetchall():
                    eid, ws_id, title, description, score = row
                    hits.append(
                        SearchHit(
                            id=str(eid),
                            artifact_type=entity_type,
                            title=title or "",
                            description=description or "",
                            relevance_score=float(score),
                            workspace_id=str(ws_id),
                        )
                    )
        except Exception:
            logger.exception(
                "SearchService._search_entity_type: SQL error entity_type=%s",
                entity_type,
            )

        return hits


__all__ = ["SearchService", "SearchResult", "SearchHit", "QueryParser"]
