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

Same RLS bug as #815 (fixed here too): ``pl_workspace`` and every table this
command's cascade touches (``pl_artifact``, ``pl_requirement``,
``pl_architecture_element``, ``pl_tracelink``, ``pl_testcase``, ``pl_baseline``,
``pl_audit_log_entry``, ``pc_workspace_preset_config``) carry a
``FORCE ROW LEVEL SECURITY`` policy keyed on the session variable
``app.current_tenant`` (``persistence/migrations/0003_rls_policies.py``,
``presets/migrations/0003_workspace_preset_config_rls.py``). ``.unscoped`` only
bypasses the ORM-level ``TenantManager`` filter — it does NOT touch
``app.current_tenant``, so under the least-privilege ``reqogniloom_app`` DB
role (``docker-compose.yml``'s documented production/dev setup, which does
NOT bypass RLS like the migration-owner/superuser role does) every query here
silently returned zero rows. ``cleanup_revoked_api_keys`` looks like the
same pattern but is *not* actually a counter-example: ``at_api_key`` is one
of the two tables ``auth_tenancy/migrations/0011_rls_policies.py`` explicitly
excludes from RLS (chicken-and-egg with pre-auth key lookup), so that command
never needed a tenant context to begin with — coincidence, not a working
template. This command's tables ARE covered, so it must arm
``app.current_tenant`` itself: since this is a cross-tenant job by design (not
one request for one tenant), it iterates every ``Tenant`` row (untenanted
table, no RLS, safe to list without a context) and pairs
``set_request_tenant``/``clear_request_tenant`` (``persistence.middleware``)
around each tenant's slice of work, same pairing discipline #522 requires of
every caller.

Baselines are NOT part of the cascade (Issue #711 follow-up): ``BaselineSnapshot``
(``bl_baseline_snapshot``) is append-only by design (ADR-L3-BL003-01,
REQ-L2-BL-002) — ``baseline/migrations/0001_initial.py`` installs a
``BEFORE UPDATE OR DELETE`` trigger (``bl_raise_immutable``) that raises
``InternalError: Baselines are immutable`` for every row it would touch,
unconditionally, with no bypass at the DB level. This is not limited to a
direct ``BaselineSnapshot.delete()`` call either: ``BaselineSnapshot.artifact``
is ``ForeignKey(Artifact, on_delete=models.CASCADE)``, so the ORM's own
collector attempts to cascade-delete any document-scope baseline the moment
its owning ``Artifact`` row is deleted — the same trigger fires and aborts
just the same. The *reference* path this command mirrors,
``WorkspaceService.delete_workspace``, does not solve this either: it has no
baseline pre-check, so it hits the same trigger and relies on
``@atomic_transaction`` to roll the whole delete back, leaving the workspace
AND its baseline(s) intact (pinned by
``application/tests/test_workspace_lifecycle.py::test_delete_workspace_with_baselines_fails``).
An unattended batch job cannot rely on that per-call rollback the same way —
a raised exception here would abort the entire remaining ``stale`` loop, not
just one workspace — so ``_cascade_delete`` pre-checks for baselines and
*skips* (not deletes, not crashes) any workspace that still has one, exactly
mirroring what the reference path's rollback achieves (workspace + baseline
both survive), just without needing to hit the trigger to get there. Each
workspace's cascade also now runs inside its own ``transaction.atomic()``
block so an unrelated failure can't leave one workspace half-deleted while
still allowing the rest of the batch to proceed.

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
from django.db import transaction
from django.utils import timezone

from baseline.models import BaselineSnapshot
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import (
    ArchitectureElement,
    Artifact,
    AuditLogEntry,
    Requirement,
    Tenant,
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
        # Still RLS-protected (see module docstring, #815-style bug): must be
        # gathered per-tenant with app.current_tenant armed, or every query
        # below returns zero rows under the least-privilege DB role.
        stale: list[Workspace] = []
        for tenant in Tenant.objects.all():
            set_request_tenant(tenant.id)
            try:
                stale.extend(
                    Workspace.unscoped.filter(
                        tenant_id=tenant.id,
                        name__startswith=name_prefix,
                        created_at__lt=cutoff,
                    )
                )
            finally:
                clear_request_tenant()

        count = len(stale)

        if not options["apply"]:
            self.stdout.write(
                f"[dry-run] {count} workspace(s) with name prefix "
                f"{name_prefix!r} older than {older_than_days} day(s) would "
                "be deleted. Re-run with --apply to delete them."
            )
            return

        deleted_count = 0
        skipped_count = 0
        for workspace in stale:
            if self._cascade_delete(workspace):
                deleted_count += 1
            else:
                skipped_count += 1
                self.stdout.write(
                    self.style.WARNING(
                        f"Skipped workspace {workspace.name!r} ({workspace.pk}): "
                        "has immutable baseline(s), cannot be deleted (see "
                        "module docstring)."
                    )
                )

        summary = (
            f"Deleted {deleted_count} workspace(s) with name prefix "
            f"{name_prefix!r} older than {older_than_days} day(s)."
        )
        if skipped_count:
            summary += (
                f" Skipped {skipped_count} workspace(s) with existing "
                "baseline(s)."
            )
        self.stdout.write(self.style.SUCCESS(summary))

    @staticmethod
    def _cascade_delete(workspace: Workspace) -> bool:
        """Full cascade delete for one workspace.

        Same deletion order as ``WorkspaceService.delete_workspace`` (audit
        log, baselines, trace links, test cases, architecture elements,
        requirements, artifacts, preset config, workspace) — intentionally
        duplicated rather than reused, since that service method requires an
        admin ``AuthContext`` and a captcha confirmation that make no sense
        for an unattended maintenance job with no human operator to confirm.

        Arms ``app.current_tenant`` for ``workspace.tenant_id`` itself (does
        not rely on a caller having already done so) — every table touched
        below is RLS-protected (see module docstring), so this method is not
        self-contained without it.

        Returns ``False`` (and does NOT touch anything) if the workspace has
        any ``BaselineSnapshot`` rows — baselines are append-only by design
        and deleting through them (directly, or indirectly via the ORM's
        ``on_delete=CASCADE`` from ``Artifact``) trips the DB-level
        ``bl_raise_immutable`` trigger (see module docstring). Otherwise
        performs the cascade inside its own transaction and returns ``True``.
        """
        workspace_pk = workspace.pk

        set_request_tenant(workspace.tenant_id)
        try:
            if BaselineSnapshot.unscoped.filter(workspace_id=workspace_pk).exists():
                return False

            with transaction.atomic():
                AuditLogEntry.unscoped.filter(
                    object_type="Workspace", object_id=workspace_pk
                ).delete()

                artifact_ids = list(
                    Artifact.unscoped.filter(workspace_id=workspace_pk).values_list(
                        "id", flat=True
                    )
                )

                if artifact_ids:
                    TraceLink.unscoped.filter(source_id__in=artifact_ids).delete()
                    TraceLink.unscoped.filter(target_id__in=artifact_ids).delete()
                    TestCase.unscoped.filter(artifact_id__in=artifact_ids).delete()
                    ArchitectureElement.unscoped.filter(
                        artifact_id__in=artifact_ids
                    ).delete()
                    Requirement.unscoped.filter(artifact_id__in=artifact_ids).delete()
                    Artifact.unscoped.filter(workspace_id=workspace_pk).delete()

                WorkspacePresetConfig.unscoped.filter(
                    workspace_id=workspace_pk
                ).delete()
                Workspace.unscoped.filter(pk=workspace_pk).delete()
            return True
        finally:
            clear_request_tenant()
