"""Detect and repair cyclic ArchitectureElement hierarchies (#1660).

A self-parent (``parent_id == id``) or a longer cycle (A -> B -> C -> A)
makes the recursive CTEs in ``ArchitectureElement.annotate_levels`` and
``ArtifactService.get_tree`` non-terminating, which turns every detail and
list read of the workspace into a 500. The write path now rejects such
assignments, but rows written before that guard still exist.

This command is the repair path. It is dry-run by default; ``--apply``
performs the repair. For every cycle it detaches exactly one element — the
one with the smallest UUID, so the choice is deterministic and repeatable —
to the root and mirrors that change onto the backing Artifact.
"""
from __future__ import annotations

from uuid import UUID

from django.core.management.base import BaseCommand
from django.db import transaction

from persistence.models import ArchitectureElement, Artifact


class Command(BaseCommand):
    help = (
        "Detect and repair self-parent / cyclic ArchitectureElement rows. "
        "Dry-run by default; pass --apply to write."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Repair the detected cycles (default: report only).",
        )
        parser.add_argument(
            "--workspace",
            type=UUID,
            default=None,
            help="Restrict the scan to one workspace UUID.",
        )

    def handle(self, *args, **options) -> None:
        apply = bool(options["apply"])
        workspace_id = options["workspace"]

        qs = ArchitectureElement.unscoped.all()
        if workspace_id is not None:
            qs = qs.filter(artifact__workspace_id=workspace_id)

        rows = list(
            qs.values("id", "parent_id", "artifact_id", "artifact__workspace_id")
        )
        parent_by_id = {row["id"]: row["parent_id"] for row in rows}
        by_id = {row["id"]: row for row in rows}

        cycles = self._find_cycles(parent_by_id)
        if not cycles:
            self.stdout.write(self.style.SUCCESS("No architecture cycles found."))
            return

        for cycle in cycles:
            victim_id = min(cycle)
            victim = by_id[victim_id]
            self.stdout.write(
                f"Cycle: {' -> '.join(str(node) for node in cycle)} "
                f"(workspace {victim['artifact__workspace_id']}); "
                f"detach {victim_id} from its parent."
            )
            if not apply:
                continue
            with transaction.atomic():
                ArchitectureElement.unscoped.filter(id=victim_id).update(
                    parent_id=None
                )
                Artifact.unscoped.filter(id=victim["artifact_id"]).update(
                    parent_id=None
                )

        if apply:
            self.stdout.write(
                self.style.SUCCESS(f"Repaired {len(cycles)} cycle(s).")
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    f"Found {len(cycles)} cycle(s); re-run with --apply to repair."
                )
            )

    @staticmethod
    def _find_cycles(parent_by_id: dict[UUID, UUID | None]) -> list[list[UUID]]:
        """Return one node list per cycle in the functional parent graph.

        Uses an iterative three-state walk (0 = unvisited, 1 = on the current
        path, 2 = done) so a pre-existing cycle terminates instead of hanging
        the repair command itself.
        """
        state: dict[UUID, int] = {}
        cycles: list[list[UUID]] = []

        for start in parent_by_id:
            if state.get(start) == 2:
                continue
            path: list[UUID] = []
            index: dict[UUID, int] = {}
            node: UUID | None = start
            while node is not None and state.get(node, 0) == 0:
                state[node] = 1
                index[node] = len(path)
                path.append(node)
                node = parent_by_id.get(node)
            if node is not None and state.get(node) == 1:
                cycle_start = index[node]
                cycles.append(path[cycle_start:])
            for visited in path:
                state[visited] = 2

        return cycles
