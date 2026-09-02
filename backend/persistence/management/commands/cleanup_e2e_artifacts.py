"""
Issue #711: cleanup command for stale E2E/CI test workspaces.

Every Playwright spec that needs an isolated workspace creates one via
``createIsolatedWorkspace``/the visual-regression fixture with a
recognisable ``e2e-`` name prefix (see ``e2e/helpers/auth.ts`` and
``e2e/tests/visual-regression.spec.ts``). Those workspaces are never
cleaned up, so a long-lived instance that runs E2E/QA suites against it
accumulates them indefinitely (63 observed in the reported case, ~60 of
them ``e2e-visual-regression-*``) until the workspace list becomes
unusable.

This mirrors ``cleanup_revoked_api_keys``: dry-run by default, age
threshold, full cascade delete of the workspace and everything under it
(same order as ``WorkspaceService.delete_workspace``, minus the
human-in-the-loop captcha confirmation which makes no sense for an
automated maintenance job).

Note: the *active* API-key limit already excludes revoked keys (see
``AuthenticationService.create_api_key``); accumulated revoked keys are a
separate DB-hygiene concern already covered by ``cleanup_revoked_api_keys``.
This command only targets workspaces, which had no retention mechanism at
all before #711.

Usage:
    python manage.py cleanup_e2e_artifacts                 # dry run, 1-day threshold
    python manage.py cleanup_e2e_artifacts --apply
    python manage.py cleanup_e2e_artifacts --apply --older-than-days=0 --name-prefix=e2e-
"""
from __future__ import annotations

from argparse import ArgumentParser
from datetime import timedelta
from typing import Any

from django.core.management.base import BaseCommand
from django.utils import timezone

from baseline.models import BaselineSnapshot
from persistence.models import (
    ArchitectureElement,
    Artifact,
    AuditLogEntry,
    Requirement,
    TestCase,
    TraceLink,
    Workspace,
)
from presets.models import WorkspacePresetConfig

_DEFAULT_OLDER_THAN_DAYS = 1
_DEFAULT_NAME_PREFIX = "e2e-"


class Command(BaseCommand):
    """Hard-delete stale E2E/CI test workspaces (dry-run by default)."""

    help = (
        "Delete Workspace rows created by E2E/CI runs (#711), identified by "
        "name prefix and age. Dry-run unless --apply is given; always "
        "reports the count either way."
    )

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            "--older-than-days",
            type=int,
            default=_DEFAULT_OLDER_THAN_DAYS,
            help=(
                "Age threshold in days since creation "
                f"(default: {_DEFAULT_OLDER_THAN_DAYS})."
            ),
        )
        parser.add_argument(
            "--name-prefix",
            type=str,
            default=_DEFAULT_NAME_PREFIX,
            help=(
                "Only workspaces whose name starts with this prefix are "
                f"candidates (default: {_DEFAULT_NAME_PREFIX!r})."
            ),
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Actually delete the matched rows (default: dry-run, report only).",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        older_than_days = options["older_than_days"]
        name_prefix = options["name_prefix"]
        cutoff = timezone.now() - timedelta(days=older_than_days)

        # unscoped: cross-tenant maintenance, not a request-scoped operation.
        stale = Workspace.unscoped.filter(
            name__startswith=name_prefix, created_at__lt=cutoff
        )
        count = stale.count()

        if not options["apply"]:
            self.stdout.write(
                f"[dry-run] {count} workspace(s) with name prefix "
                f"{name_prefix!r} older than {older_than_days} day(s) would "
                "be deleted. Re-run with --apply to delete them."
            )
            return

        deleted_count = 0
        for workspace in list(stale):
            self._cascade_delete(workspace)
            deleted_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Deleted {deleted_count} workspace(s) with name prefix "
                f"{name_prefix!r} older than {older_than_days} day(s)."
            )
        )

    @staticmethod
    def _cascade_delete(workspace: Workspace) -> None:
        """Full cascade delete for one workspace.

        Same deletion order as ``WorkspaceService.delete_workspace`` (audit
        log, baselines, trace links, test cases, architecture elements,
        requirements, artifacts, preset config, workspace) — intentionally
        duplicated rather than reused, since that service method requires an
        admin ``AuthContext`` and a captcha confirmation that make no sense
        for an unattended maintenance job with no human operator to confirm.
        """
        workspace_pk = workspace.pk

        AuditLogEntry.unscoped.filter(
            object_type="Workspace", object_id=workspace_pk
        ).delete()

        artifact_ids = list(
            Artifact.unscoped.filter(workspace_id=workspace_pk).values_list(
                "id", flat=True
            )
        )

        if artifact_ids:
            BaselineSnapshot.unscoped.filter(workspace_id=workspace_pk).delete()
            TraceLink.unscoped.filter(source_id__in=artifact_ids).delete()
            TraceLink.unscoped.filter(target_id__in=artifact_ids).delete()
            TestCase.unscoped.filter(artifact_id__in=artifact_ids).delete()
            ArchitectureElement.unscoped.filter(artifact_id__in=artifact_ids).delete()
            Requirement.unscoped.filter(artifact_id__in=artifact_ids).delete()
            Artifact.unscoped.filter(workspace_id=workspace_pk).delete()

        WorkspacePresetConfig.unscoped.filter(workspace_id=workspace_pk).delete()
        Workspace.unscoped.filter(pk=workspace_pk).delete()
