"""Report and apply the leaf-relative requirement tier backfill (P2, Task 2.8).

Default is a **dry run**: it computes the tier for every requirement from the
workspace's tier ladder + allocation and prints the counts per
``level_source`` without writing anything. ``--apply`` writes the result.

The write path never overwrites a ``manual`` override (see
:func:`application.tier_compute.recompute_workspace_tiers`).
"""
from __future__ import annotations

from collections import Counter

from django.core.management.base import BaseCommand

from application.tier_compute import recompute_workspace_tiers
from persistence.models import Requirement, Tenant, Workspace
from persistence.tenancy import TenantContext


class Command(BaseCommand):
    help = (
        "Report (default, dry run) the leaf-relative tier backfill per "
        "level_source; --apply writes it. Manual overrides are preserved."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Write the computed tier_key/level/level_source.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Explicit dry run (the default). Mutually exclusive with --apply.",
        )
        parser.add_argument("--tenant", default=None, help="Restrict to a tenant UUID.")
        parser.add_argument("--workspace", default=None, help="Restrict to a workspace UUID.")

    def handle(self, *args, **options):
        if options["apply"] and options["dry_run"]:
            raise SystemExit("--apply and --dry-run are mutually exclusive.")
        apply_changes: bool = options["apply"]
        tenant_filter = options.get("tenant")
        workspace_filter = options.get("workspace")

        tenants = Tenant.objects.all()
        if tenant_filter:
            tenants = tenants.filter(id=tenant_filter)

        totals = Counter()
        source_counts: Counter = Counter()

        for tenant in tenants:
            TenantContext.set_tenant(tenant.id)
            try:
                workspaces = Workspace.objects.filter(tenant=tenant)
                if workspace_filter:
                    workspaces = workspaces.filter(id=workspace_filter)
                for workspace in workspaces:
                    changes = recompute_workspace_tiers(
                        workspace.id, dry_run=not apply_changes
                    )
                    totals["requirements"] += Requirement.objects.filter(
                        workspace_id=workspace.id
                    ).count()
                    totals["changed"] += len(changes)
                    for change in changes:
                        source_counts[change.new_source] += 1
            finally:
                TenantContext.clear_tenant()

        mode = "APPLY" if apply_changes else "DRY RUN"
        self.stdout.write(f"Requirement tier backfill report ({mode})")
        self.stdout.write(f"  requirements scanned : {totals['requirements']}")
        self.stdout.write(f"  rows {'written' if apply_changes else 'to change'}: {totals['changed']}")
        for source, count in sorted(source_counts.items()):
            self.stdout.write(f"  {source:<22}: {count}")
        if totals["changed"] == 0:
            self.stdout.write("  nothing to do")
