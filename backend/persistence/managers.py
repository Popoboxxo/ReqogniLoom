"""
Custom QuerySet managers for persistence models (COMP-PL-001).

Handles specialized database queries, including:
- Recursive CTE for ArchitectureElement hierarchy levels (REQ-L1-058 AC2)
- Tenant-scoped queries via TenantManager
- Query optimization hints (select_related, prefetch_related)

leaf_id: ADR-01 (Single responsibility)
req_id: REQ-L1-058 AC2 (CTE-based level computation)
"""

from typing import Optional
from django.db import models
from django.db.models import F, Value, Case, When, CharField, IntegerField, Subquery, OuterRef, QuerySet
from django.db.models.functions import Coalesce

from persistence.base import TenantManager


class ArchitectureElementQuerySet(QuerySet):
    """Custom QuerySet for ArchitectureElement with CTE support.

    REQ-L1-058 AC2: get_with_level() annotates each element with its tree depth
    using PostgreSQL WITH RECURSIVE CTE. Avoids N+1 queries when bulk-fetching
    hierarchies.

    Example usage:
        ArchitectureElement.objects.get_with_level().filter(tenant=ws.tenant)
        # Returns queryset with level annotation available for serialization.
    """

    def get_with_level(self) -> QuerySet:
        """Annotate queryset with level (tree depth) via PostgreSQL CTE.

        REQ-L1-058 AC2: Uses WITH RECURSIVE to compute level in single SQL query.
        Level: 0 for root (parent IS NULL), 1 for children, etc.

        Performance: O(1) query for N elements, vs O(n) with Python recursion.
        Database: PostgreSQL only (CTE syntax is DB-specific).

        Returns:
            QuerySet annotated with 'level' field (IntegerField, read-only).
        """
        from django.db import connection

        # PostgreSQL CTE query inline via RawSQL
        # This approach works with Django ORM and supports filtering/ordering after CTE
        cte_sql = """
            (WITH RECURSIVE hierarchy AS (
                -- Base case: root elements (parent IS NULL)
                SELECT id, parent_id, 0 AS level
                FROM pl_architecture_element
                WHERE parent_id IS NULL AND tenant_id = %s

                UNION ALL

                -- Recursive case: children inherit parent's level + 1
                SELECT ae.id, ae.parent_id, h.level + 1
                FROM pl_architecture_element ae
                JOIN hierarchy h ON ae.parent_id = h.id
                WHERE ae.tenant_id = %s
            )
            SELECT level FROM hierarchy WHERE id = %s
            )
        """

        # Use Subquery + OuterRef to annotate from CTE
        # Note: This is a simplified approach; full CTE join would be more efficient
        # For production, consider using raw_sql or a database view

        # Alternative: Use annotate() with Case/When for simpler cases
        # This is a workaround for Django ORM limitations with CTEs

        # For now, use a simpler annotation approach that works with Django ORM:
        # We'll compute level via recursive F expressions (limited depth support)
        # OR use extra() with raw SQL

        # Best practice for PostgreSQL CTE with Django (REQ-L1-058 AC2):
        # Use Subquery with RawSQL for each row's level

        from django.db.models import RawSQL

        return self.annotate(
            level=RawSQL(
                """
                WITH RECURSIVE hierarchy AS (
                    SELECT id, parent_id, 0 AS depth
                    FROM pl_architecture_element
                    WHERE parent_id IS NULL AND tenant_id = %s

                    UNION ALL

                    SELECT ae.id, ae.parent_id, h.depth + 1
                    FROM pl_architecture_element ae
                    JOIN hierarchy h ON ae.parent_id = h.id
                    WHERE ae.tenant_id = %s
                )
                SELECT COALESCE(h.depth, 0)
                FROM hierarchy h
                WHERE h.id = pl_architecture_element.id
                """,
                [OuterRef('tenant_id'), OuterRef('tenant_id')],
            )
        )


class ArchitectureElementManager(TenantManager):
    """Custom manager for ArchitectureElement (COMP-PL-001, ADR-01).

    Provides specialized methods for hierarchy operations:
    - get_queryset_with_level(): Fetch elements with tree depth annotation via CTE

    REQ-L1-058 AC2: Replaces Python-recursive get_level() with DB CTE.
    """

    def get_queryset(self) -> ArchitectureElementQuerySet:
        """Return custom queryset with CTE support.

        Returns:
            ArchitectureElementQuerySet: Custom QuerySet class.
        """
        return ArchitectureElementQuerySet(self.model, using=self._db)

    def get_with_level(self) -> QuerySet:
        """Annotate all elements with tree depth (CTE-based, no N+1).

        Shortcut to queryset.get_with_level() for convenience.

        REQ-L1-058 AC2 Compliance:
        - Single SQL CTE query (no recursion)
        - Returns level as annotated field
        - Supports filtering, ordering, pagination after annotation

        Example:
            elements = ArchitectureElement.objects.filter(tenant=ws.tenant).get_with_level()
            for elem in elements:
                print(f"{elem.title}: level={elem.level}")

        Returns:
            QuerySet: Annotated with 'level' field.
        """
        return self.get_queryset().get_with_level()
