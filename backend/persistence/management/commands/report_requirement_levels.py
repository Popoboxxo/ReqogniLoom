"""Report (and optionally apply) the V-model cascade level backfill (#1289).

The field ``Requirement.level`` is derived (ADR-005), but a corpus can still
hold rows the derivation never reached (pre-ADR-005 rows, direct ORM writes) and
rows whose level disagrees with the architecture allocation. This command
recomputes the level from the two sources the ticket names —

* the ``derives-from`` / ``decomposes`` requirement hierarchy, and
* the ``allocated-to`` architecture allocation (``ArchitectureElement`` depth ->
  cascade level, :data:`traceability.audit.hierarchy.ARCHITECTURE_DEPTH_TO_LEVEL`)

— and **reports** the outcome. Where *neither* source determines a level it
reports ``NULL`` instead of guessing.

By default it is read-only. ``--apply`` fills only the rows that are currently
``NULL`` (never overwrites an existing or a ``manual`` value), which is the same
calibration contract ``recompute_requirement_levels(fill_only=True)`` uses.
"""
from __future__ import annotations

from uuid import UUID

from django.core.management.base import BaseCommand

from persistence.models import Requirement, RequirementLevelSource, Tenant
from persistence.tenancy import TenantContext, TenantContextNotSetError
from traceability.audit.hierarchy import (
    _tenant_hierarchy_subgraph,
    architecture_allocated_levels,
    derive_requirement_levels,
)


class Command(BaseCommand):
    help = (
        "Report the V-model level backfill from the requirement hierarchy and "
        "the architecture allocation; NULL is reported where no source "
        "determines a level. Read-only unless --apply is given."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--apply",
            action="store_true",
            help=(
                "Fill rows whose level is currently NULL from the architecture "
                "allocation / hierarchy. Never overwrites an existing or manual "
                "level."
            ),
        )
        parser.add_argument(
            "--tenant",
            default=None,
            help="Restrict to a single tenant UUID.",
        )

    def handle(self, *args, **options):
        apply_changes: bool = options["apply"]
        tenant_filter: str | None = options.get("tenant")

        tenants = Tenant.objects.all()
        if tenant_filter:
            tenants = tenants.filter(id=tenant_filter)

        totals = {
            "requirements": 0,
            "manual": 0,
            "null_level": 0,
            "architecture_missing": 0,
            "architecture_mismatch": 0,
            "applied": 0,
        }

        for tenant in tenants:
            TenantContext.set_tenant(tenant.id)
            totals = self._process_tenant(tenant.id, apply_changes, totals)

        self.stdout.write("Requirement level backfill report (#1289)")
        self.stdout.write(f"  requirements scanned : {totals['requirements']}")
        self.stdout.write(f"  manual overrides     : {totals['manual']}")
        self.stdout.write(
            f"  level NULL (no source): {totals['null_level']}"
        )
        self.stdout.write(
            f"  no architecture alloc.: {totals['architecture_missing']}"
        )
        self.stdout.write(
            f"  level != architecture : {totals['architecture_mismatch']}"
        )
        if apply_changes:
            self.stdout.write(f"  applied (NULL filled) : {totals['applied']}")

    def _process_tenant(
        self, tenant_id: UUID, apply_changes: bool, totals: dict
    ) -> dict:
        """Compute/emit the per-tenant report and return the updated *totals*."""
        current, edges = _tenant_hierarchy_subgraph(tenant_id)
        if not current:
            return totals

        hierarchy_levels = derive_requirement_levels(edges, sorted(current, key=repr))
        architecture_levels = architecture_allocated_levels(tenant_id)

        rows = list(
            Requirement.unscoped.filter(tenant_id=tenant_id).values(
                "artifact_id", "level", "level_source", "uid"
            )
        )

        to_fill: dict[int, list] = {1: [], 2: [], 3: [], 4: []}
        for row in rows:
            artifact_id = row["artifact_id"]
            level = row["level"]
            source = row["level_source"]
            label = row["uid"] or str(artifact_id)
            totals["requirements"] += 1

            if source == RequirementLevelSource.MANUAL:
                totals["manual"] += 1

            hierarchy_level = hierarchy_levels.get(artifact_id)
            architecture_level = architecture_levels.get(artifact_id)

            if architecture_level is None and artifact_id not in architecture_levels:
                totals["architecture_missing"] += 1
            elif (
                level is not None
                and architecture_level is not None
                and level != architecture_level
            ):
                totals["architecture_mismatch"] += 1

            resolved = architecture_level if architecture_level is not None else hierarchy_level
            if level is None and resolved is None:
                totals["null_level"] += 1
                self.stdout.write(
                    f"  [NULL] {label} ({artifact_id}): no hierarchy parent and no "
                    "architecture allocation — level not derivable."
                )
            elif (
                apply_changes
                and level is None
                and resolved is not None
                and source != RequirementLevelSource.MANUAL
            ):
                to_fill[resolved].append(artifact_id)
                totals["applied"] += 1

        for resolved, artifact_ids in to_fill.items():
            if not artifact_ids:
                continue
            Requirement.unscoped.filter(artifact_id__in=artifact_ids).update(
                level=resolved, level_source=RequirementLevelSource.DERIVED
            )
        return totals


__all__ = ["Command"]
