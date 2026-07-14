"""
REQ-106: ``token_usage`` management command — per-tenant token consumption report.

Prints aggregated LLM token usage per tenant over a rolling window, plus each
tenant's configured daily limit and whether it is currently exceeded.

Usage::

    python manage.py token_usage            # last 30 days, all tenants
    python manage.py token_usage --days 7   # last 7 days
    python manage.py token_usage --tenant <uuid>

The report reads through the unscoped manager so it can span all tenants; this
is an operator/reporting tool, not a tenant-facing query.
"""
from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Sum
from django.utils import timezone

from llm_adapter.token_tracking import get_daily_token_limit
from persistence.models import Tenant, TokenUsageRecord


class Command(BaseCommand):
    help = "Report aggregated LLM token usage per tenant (REQ-106)."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--days",
            type=int,
            default=30,
            help="Rolling window size in days (default: 30).",
        )
        parser.add_argument(
            "--tenant",
            type=str,
            default=None,
            help="Limit the report to a single tenant UUID.",
        )

    def handle(self, *args, **options) -> None:
        days: int = options["days"]
        tenant_filter: str | None = options["tenant"]
        window_days: int = days if days and days > 0 else 30

        since = timezone.now() - timedelta(days=window_days)
        daily_since = timezone.now() - timedelta(days=1)
        limit = get_daily_token_limit()

        tenants = Tenant.objects.all()
        if tenant_filter:
            tenants = tenants.filter(id=tenant_filter)

        self.stdout.write(
            f"Token usage report — last {window_days} day(s) "
            f"(daily limit: {limit if limit is not None else 'unlimited'})"
        )
        self.stdout.write("-" * 72)

        # Unscoped: this reporting tool intentionally spans all tenants.
        base = TokenUsageRecord.unscoped.filter(created_at__gte=since)

        for tenant in tenants:
            rows = (
                base.filter(tenant_id=tenant.id)
                .values("provider")
                .annotate(total=Sum("input_tokens") + Sum("output_tokens"))
                .order_by("provider")
            )
            window_total = 0
            provider_lines = []
            for row in rows:
                provider_total = int(row["total"] or 0)
                window_total += provider_total
                provider_lines.append(f"    {row['provider']}: {provider_total}")

            daily_agg = TokenUsageRecord.unscoped.filter(
                tenant_id=tenant.id, created_at__gte=daily_since
            ).aggregate(total=Sum("input_tokens") + Sum("output_tokens"))
            daily_total = int(daily_agg["total"] or 0)
            over = limit is not None and daily_total >= limit

            self.stdout.write(
                f"{tenant.slug} ({tenant.id}): {window_total} tokens / {window_days}d, "
                f"{daily_total} tokens / 1d"
                + ("  [OVER DAILY LIMIT]" if over else "")
            )
            for line in provider_lines:
                self.stdout.write(line)
