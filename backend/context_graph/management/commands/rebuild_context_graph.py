"""Management command: full Workspace Context Graph rebuild for one workspace.

Issue #377, Task 8. An admin/operator action (not a new MCP write tool —
Task 8's own scoping note: a management command is sufficient for v1).

Usage:
    python manage.py rebuild_context_graph --workspace <uuid>
"""
from __future__ import annotations

import uuid

from django.core.management.base import BaseCommand, CommandError

from context_graph.admin_ops import rebuild_workspace_graph


class Command(BaseCommand):
    help = "Full rebuild of the Workspace Context Graph for one workspace (Issue #377)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--workspace", required=True, help="Workspace UUID to rebuild."
        )

    def handle(self, *args, **options):
        try:
            workspace_id = uuid.UUID(str(options["workspace"]))
        except ValueError as exc:
            raise CommandError(f"--workspace is not a valid UUID: {options['workspace']}") from exc

        result = rebuild_workspace_graph(workspace_id)

        if result.error:
            raise CommandError(result.error)

        self.stdout.write(
            self.style.SUCCESS(
                f"Rebuilt context graph for workspace {workspace_id}: "
                f"{result.artifacts_processed}/{result.node_count} artifacts processed, "
                f"{result.edge_count} edge(s), {result.artifact_errors} error(s)."
            )
        )
