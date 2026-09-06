from django.core.management.base import BaseCommand

from persistence.models import Tenant
from persistence.tenancy import TenantContext, TenantContextNotSetError
from workflow.models import WorkflowItemState
from workflow.services import outdate
from workflow.state_reader import outdated_ids


class _SystemAuthContext:
    """Minimal ctx stand-in for a system-run backfill (not a real user)."""
    user_id = "system:backfill_outdated_from_legacy_status"


# Datenmodell-Konsolidierung Task 12 removed the Adr lookup that used to key
# off the (already-dropped) ``status`` column, for the same reason Task 24
# now empties this list entirely: Requirement/ArchitectureElement/
# GlossaryTerm's ``lifecycle_status`` columns are dropped too, so
# ``model.objects.filter(lifecycle_status=...)`` would raise FieldError if it
# ran (no such field). Documented, reviewed data-loss tradeoff: any row never
# backfilled by this one-shot command before Task 24 stays un-flagged as
# "outdated" going forward (same tradeoff as the Task 12 report, Finding 2).
LEGACY_DELETED_LOOKUPS: list[tuple[str, str, str, str, str]] = []


class Command(BaseCommand):
    help = "One-shot backfill: transition already-legacy-deleted records to the workflow 'outdated' state."

    def handle(self, *args, **options):
        from importlib import import_module

        ctx = _SystemAuthContext()
        total = 0

        # Preserve the caller's ambient tenant context (if any) so this command
        # can be safely invoked from within an already tenant-scoped caller
        # (e.g. call_command(...) from a test that set its own tenant context).
        try:
            original_tenant_id = TenantContext.get_tenant()
        except TenantContextNotSetError:
            original_tenant_id = None

        # Iterate over all tenants to handle multi-tenant row-level security
        for tenant in Tenant.objects.all():
            TenantContext.set_tenant(tenant.id)
            try:
                for module_path, class_name, field_name, deleted_value, item_type in LEGACY_DELETED_LOOKUPS:
                    model = getattr(import_module(module_path), class_name)
                    queryset = model.objects.filter(**{field_name: deleted_value})

                    already_outdated = set(
                        outdated_ids(item_type, tenant_id=tenant.id)
                    )
                    for obj in queryset:
                        item_state = WorkflowItemState.objects.filter(
                            item_id=obj.id, item_type=item_type
                        ).first()
                        # Datenmodell-Konsolidierung Phase 4 (D-3): the
                        # "already backfilled" check reads the soft-delete flag.
                        # It used to compare ``current_state == "outdated"``,
                        # which ``outdate()`` no longer writes — that guard
                        # would now never fire, so every run would redo every
                        # row (harmless but pointless work, and it would report
                        # an inflated count).
                        if item_state is None or obj.id in already_outdated:
                            continue  # no workflow item, or already backfilled - idempotent skip
                        outdate(
                            item_id=obj.id,
                            item_type=item_type,
                            workspace_id=item_state.workspace_id,
                            ctx=ctx,
                            reason="backfilled from legacy deleted status",
                        )
                        total += 1
            finally:
                TenantContext.clear_tenant()

        # Restore the caller's ambient tenant context instead of leaving it cleared.
        if original_tenant_id is not None:
            TenantContext.set_tenant(original_tenant_id)

        self.stdout.write(self.style.SUCCESS(f"Backfilled {total} records to outdated."))
