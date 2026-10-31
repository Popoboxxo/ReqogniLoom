"""ARCH-L1-013 DiagramService — report_unbacked_diagrams management command.

F1.2-T2 (#1374, PR-F3b): ``create_diagram`` now requires a ``workspace_id``, so
no *new* Diagram can be created without one. Rows written before that change
(or outside the service layer) may still carry ``workspace_id IS NULL``; because
``Artifact.workspace`` is not nullable they can never get a backing Artifact and
are therefore unlinkable and cannot enter a baseline. This command reports
them, read-only.

Usage::

    python manage.py report_unbacked_diagrams

Output (one line per tenant, nothing is written)::

    tenant=<uuid> without_workspace=<n> without_artifact=<n>

``without_workspace`` counts ``workspace_id IS NULL`` rows, ``without_artifact``
counts ``artifact_id IS NULL`` rows — the two sets overlap for a legacy row that
has neither. Assigning a foreign Diagram to a workspace is an operator decision
(the report only names the rows' tenant); the command never mutates anything.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand

from diagram.models import Diagram
from persistence.models import Tenant
from persistence.tenancy import TenantContext, TenantContextNotSetError


class Command(BaseCommand):
    help = (
        "Read-only report: per tenant, count diagrams without workspace_id "
        "and/or without a backing artifact."
    )

    def handle(self, *args, **options) -> None:
        # Preserve the caller's ambient tenant context (a test may invoke this
        # via call_command while it has its own context active).
        try:
            original_tenant_id = TenantContext.get_tenant()
        except TenantContextNotSetError:
            original_tenant_id = None

        try:
            for tenant in Tenant.objects.all().order_by("created_at", "id"):
                TenantContext.set_tenant(tenant.id)
                try:
                    diagrams = Diagram.objects.filter(tenant_id=tenant.id)
                    without_workspace = diagrams.filter(
                        workspace_id__isnull=True
                    ).count()
                    without_artifact = diagrams.filter(
                        artifact_id__isnull=True
                    ).count()
                finally:
                    TenantContext.clear_tenant()

                self.stdout.write(
                    f"tenant={tenant.id} "
                    f"without_workspace={without_workspace} "
                    f"without_artifact={without_artifact}"
                )
        finally:
            if original_tenant_id is not None:
                TenantContext.set_tenant(original_tenant_id)
