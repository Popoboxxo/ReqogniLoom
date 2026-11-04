"""C10 / #1410 — report (and optionally soft-delete) orphan artifacts.

An "orphan" here is an active, linkable artifact with **zero** trace links in
either direction. The type-specific SE-Auditor rules (TRACE-P1/P4/P6) already
flag missing derivation/verification edges; this command is the data-hygiene
counterpart for the whole corpus and the only place that can clean up the
non-rule-covered remainder.

Default is a read-only report. ``--apply`` sets the backing Artifact's D-3
lifecycle flag to ``outdated`` (soft-delete), never a hard delete, so the rows
remain recoverable and the audit trail is preserved.
"""
from __future__ import annotations

from uuid import UUID

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count

from persistence.models import Artifact, TraceLink

#: Types for which a trace link is a meaningful expectation. Non-linkable
#: artifacts (MainGoal, ChangeRequest, Diagram, GlossaryTerm) are excluded so
#: the report does not flag them as defects by design.
LINKABLE_TYPES: tuple[str, ...] = (
    "Requirement",
    "TestCase",
    "StakeholderNeed",
    "ArchitectureElement",
    "Adr",
    "Risk",
    "Issue",
    "Icd",
    "Goal",
    "Document",
    "WorkItem",
)


class Command(BaseCommand):
    help = (
        "Report active, linkable artifacts with no trace links. "
        "Dry-run by default; pass --apply to soft-delete them."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Soft-delete the detected orphans (default: report only).",
        )
        parser.add_argument(
            "--workspace",
            type=UUID,
            default=None,
            help="Restrict the scan to one workspace UUID.",
        )
        parser.add_argument(
            "--type",
            dest="artifact_types",
            action="append",
            choices=LINKABLE_TYPES,
            default=None,
            help="Restrict the scan to one artifact type (repeatable).",
        )

    def handle(self, *args, **options) -> None:
        apply = bool(options["apply"])
        workspace_id = options["workspace"]
        artifact_types = options["artifact_types"] or list(LINKABLE_TYPES)

        source_ids = TraceLink.unscoped.values_list("source_id", flat=True)
        target_ids = TraceLink.unscoped.values_list("target_id", flat=True)

        qs = Artifact.unscoped.filter(
            artifact_type__in=artifact_types,
            lifecycle_status="active",
        )
        if workspace_id is not None:
            qs = qs.filter(workspace_id=workspace_id)
        orphans = qs.exclude(id__in=source_ids).exclude(id__in=target_ids)

        counts = list(
            orphans.values("artifact_type")
            .annotate(count=Count("id"))
            .order_by("-count", "artifact_type")
        )
        if not counts:
            self.stdout.write(self.style.SUCCESS("No orphan artifacts found."))
            return

        total = sum(row["count"] for row in counts)
        self.stdout.write(f"Orphan artifacts: {total}")
        for row in counts:
            self.stdout.write(f"  {row['artifact_type']}: {row['count']}")

        sample = list(
            orphans.values("id", "artifact_type", "workspace_id").order_by(
                "artifact_type", "created_at"
            )[:20]
        )
        if sample:
            self.stdout.write("Sample (first 20):")
            for row in sample:
                self.stdout.write(
                    f"  {row['artifact_type']} {row['id']} "
                    f"(workspace {row['workspace_id']})"
                )

        if not apply:
            self.stdout.write(
                self.style.WARNING(
                    "Dry-run only; re-run with --apply to soft-delete these rows."
                )
            )
            return

        with transaction.atomic():
            updated = orphans.update(lifecycle_status="outdated")
        self.stdout.write(
            self.style.SUCCESS(f"Soft-deleted {updated} orphan artifact(s).")
        )
