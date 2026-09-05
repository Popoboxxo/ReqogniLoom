from django.core.management.base import BaseCommand

from persistence.models import Tenant
from persistence.tenancy import TenantContext, TenantContextNotSetError
from workflow.models import WorkflowItemState
from workflow.services import outdate


class _SystemAuthContext:
    """Minimal ctx stand-in for a system-run backfill (not a real user)."""
    user_id = "system:backfill_outdated_from_legacy_status"


# Datenmodell-Konsolidierung Task 12: the ``("application.models", "Adr",
# "status", Adr.Status.DELETED, "Adr")`` lookup that used to live here is
# removed -- it filtered on the (now-dropped) ``status`` column to find
# legacy pre-WorkflowEngine "deleted" Adrs. That column was the only record
# of which Adrs were in that legacy state; with it gone, this lookup can
# never match anything again and would only raise FieldError if it ran
# (Adr.objects.filter(status=...) -- no such field). Documented, reviewed
# data-loss tradeoff: any Adr never backfilled by this one-shot command
# before Task 12 stays un-flagged as "outdated" going forward (see the Task
# 12 report, Finding 2). Requirement/ArchitectureElement/GlossaryTerm below
# are unaffected -- they key off ``lifecycle_status``, a separate column this
# task does not touch.
LEGACY_DELETED_LOOKUPS = [
    ("persistence.models", "Requirement", "lifecycle_status", "deleted", "Requirement"),
    ("persistence.models", "ArchitectureElement", "lifecycle_status", "deleted", "ArchitectureElement"),
    ("persistence.models", "GlossaryTerm", "lifecycle_status", "deleted", "GlossaryTerm"),
]


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

                    for obj in queryset:
                        item_state = WorkflowItemState.objects.filter(
                            item_id=obj.id, item_type=item_type
                        ).first()
                        if item_state is None or item_state.current_state == "outdated":
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
