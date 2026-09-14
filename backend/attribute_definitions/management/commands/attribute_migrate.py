"""``manage.py attribute_migrate`` — operator entry point for AWMS (spec §7).

Examples::

    python manage.py attribute_migrate --plan migration.yaml --tenant <uuid>
    python manage.py attribute_migrate --plan migration.yaml --apply --tenant <uuid>
    python manage.py attribute_migrate --rollback <run_id> --tenant <uuid>

``--dry-run`` is the default; ``--apply`` is required for a real run. A
management command has no request/middleware around it, so the tenant context
(both the app-layer filter and the DB-level ``app.current_tenant`` RLS variable)
is armed explicitly per tenant and cleared in a ``finally`` — the same pattern as
``bootstrap_attribute_definitions`` / ``backfill_embeddings``.
"""
from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from django.core.management.base import BaseCommand, CommandError

from application.attribute_migration_service import AttributeMigrationService
from attribute_definitions.migration_plan import MigrationPlanError, load_plan_file
from auth_tenancy.context import AuthContext, AuthMethod
from auth_tenancy.models import ROLE_ADMIN
from persistence.models import Tenant


class Command(BaseCommand):
    help = (
        "Validate, preview (default) or apply a declarative AWMS migration plan, "
        "or roll back a previous apply run. Dry run is the default."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--plan",
            dest="plan",
            default=None,
            help="Path to the plan document (.yaml/.yml/.json).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            dest="dry_run",
            help="Validate + report only (the default; accepted explicitly).",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            dest="apply",
            help="Execute the plan for real (snapshots + writes + audit).",
        )
        parser.add_argument(
            "--rollback",
            dest="rollback",
            default=None,
            help="Run id to roll back (restores that run's snapshots).",
        )
        parser.add_argument(
            "--tenant",
            dest="tenant",
            default=None,
            help="Tenant UUID. Optional when exactly one tenant exists.",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            dest="as_json",
            help="Print the full report as JSON instead of a summary.",
        )

    def handle(self, *args, **options) -> None:
        if not options["plan"] and not options["rollback"]:
            raise CommandError("either --plan or --rollback is required")
        if options["plan"] and options["rollback"]:
            raise CommandError("--plan and --rollback are mutually exclusive")

        tenant_id = self._resolve_tenant(options["tenant"])
        ctx = AuthContext(
            user_id=UUID(int=0),
            tenant_id=tenant_id,
            active_roles=(ROLE_ADMIN,),
            auth_method=AuthMethod.SYSTEM,
            actor_type="user",
        )

        from persistence.middleware import clear_request_tenant, set_request_tenant

        service = AttributeMigrationService()
        set_request_tenant(tenant_id)
        try:
            if options["rollback"]:
                report = self._rollback(service, ctx, options["rollback"])
            else:
                report = self._run_plan(service, ctx, options)
        finally:
            clear_request_tenant()

        if options["as_json"]:
            self.stdout.write(json.dumps(report, indent=2, default=str))
        else:
            self._print_summary(report)

        if report.get("status") == "failed":
            raise CommandError(
                f"AWMS run {report.get('run_id')} failed; nothing was rolled back"
            )

    # -- modes --------------------------------------------------------------

    def _run_plan(
        self, service: AttributeMigrationService, ctx: AuthContext, options: dict[str, Any]
    ) -> dict[str, Any]:
        try:
            payload = load_plan_file(options["plan"])
        except MigrationPlanError as exc:
            raise CommandError("; ".join(exc.errors)) from exc

        if options["apply"]:
            try:
                return service.apply(ctx, payload)
            except MigrationPlanError as exc:
                raise CommandError("; ".join(exc.errors)) from exc
        try:
            return service.dry_run(ctx, payload)
        except MigrationPlanError as exc:
            raise CommandError("; ".join(exc.errors)) from exc

    def _rollback(
        self, service: AttributeMigrationService, ctx: AuthContext, run_id: str
    ) -> dict[str, Any]:
        try:
            return service.rollback(ctx, run_id)
        except MigrationPlanError as exc:
            raise CommandError("; ".join(exc.errors)) from exc

    # -- helpers ------------------------------------------------------------

    @staticmethod
    def _resolve_tenant(raw: str | None) -> UUID:
        tenants = Tenant.objects.all().order_by("slug")
        if raw:
            try:
                identifier = UUID(str(raw))
            except (TypeError, ValueError) as exc:
                raise CommandError(f"invalid tenant id {raw!r}") from exc
            if not tenants.filter(id=identifier).exists():
                raise CommandError(f"no tenant with id {raw}")
            return identifier
        candidates = list(tenants.values_list("id", flat=True)[:2])
        if not candidates:
            raise CommandError("no tenant exists; pass --tenant <uuid>")
        if len(candidates) > 1:
            raise CommandError(
                "multiple tenants exist; pass --tenant <uuid> to select one"
            )
        return candidates[0]

    def _print_summary(self, report: dict[str, Any]) -> None:
        summary = report.get("summary", {})
        self.stdout.write(
            self.style.SUCCESS(
                f"attribute_migrate: run={report.get('run_id')} "
                f"mode={report.get('mode')} status={report.get('status')} "
                f"changed={summary.get('changed', 0)} "
                f"skipped={summary.get('skipped', 0)} "
                f"failed={summary.get('failed', 0)}"
            )
        )
        for step in report.get("steps", []):
            counts = step.get("counts", {})
            self.stdout.write(
                f"  [{step.get('index')}] {step.get('op')}: "
                f"changed={counts.get('changed', 0)} skipped={counts.get('skipped', 0)} "
                f"failed={counts.get('failed', 0)}"
            )
            for error in step.get("errors", [])[:5]:
                self.stdout.write(self.style.WARNING(f"      {error}"))
