"""Snapshot and diff the SE-Auditor finding counts around the link migration.

Written for OFFENE FRAGE 2: folding ``refines`` into ``derives-from`` turns
formerly symmetric same-level edges into directed hierarchy edges, which the
root/leaf classifier reads. TRACE-P1 ("a decomposition root must derive from a
StakeholderNeed") and VERIF-P8 ("a leaf must have a verifying TestCase") will
therefore fire on a different set of requirements than before.

Usage::

    # before running the TraceLink data migration
    python manage.py diff_auditor_findings --snapshot /tmp/before.json --workspace <id>
    # after
    python manage.py diff_auditor_findings --snapshot /tmp/after.json --workspace <id>
    python manage.py diff_auditor_findings --before /tmp/before.json --after /tmp/after.json

A non-empty delta is the expected signal, not a defect: it is the evidence the
decision in OFFENE FRAGE 2 needs.
"""
from __future__ import annotations

import json
from collections import Counter
from typing import Dict
from uuid import UUID

from django.core.management.base import BaseCommand, CommandError


def summarize_findings(workspace_id: UUID | str) -> Dict[str, int]:
    """Return ``{rule_id: finding_count}`` for a workspace's SE-Auditor run.

    Paginates through ``AuditService.run_audit`` via ``limit``/``offset``
    instead of taking the single-call default: that default returns a
    BLOCKER-preferred view capped at ``AuditService.MAX_REPORT_FINDINGS``
    (500) findings, which would silently undercount rule_ids past the cap on
    any workspace with more findings than that. This command's entire
    purpose is an exact before/after count for OFFENE FRAGE 2, so a silent
    undercount would defeat it — every page is walked until
    ``total_findings_available`` is exhausted.
    """
    from application.audit_service import AuditService
    from auth_tenancy.context import AuthContext
    from persistence.models import Workspace

    workspace_id = str(workspace_id)
    try:
        tenant_id = Workspace.unscoped.values_list("tenant_id", flat=True).get(
            id=workspace_id
        )
    except Workspace.DoesNotExist as exc:
        raise ValueError(f"No workspace with id {workspace_id!r}") from exc

    ctx = AuthContext.system(tenant_id=tenant_id)
    service = AuditService()
    counter: Counter = Counter()
    offset = 0
    page_size = AuditService.MAX_REPORT_FINDINGS
    total_available = 0
    while True:
        report = service.run_audit(workspace_id, ctx, limit=page_size, offset=offset)
        for finding_view in report.findings:
            counter[str(finding_view.finding.rule_id)] += 1
        total_available = report.total_findings_available
        offset += len(report.findings)
        if not report.findings or offset >= total_available:
            break
    return dict(counter)


class Command(BaseCommand):
    help = "Snapshot or diff SE-Auditor finding counts around the link-type migration."

    def add_arguments(self, parser):
        parser.add_argument("--workspace", dest="workspace_id", default=None)
        parser.add_argument("--snapshot", dest="snapshot_path", default=None)
        parser.add_argument("--before", dest="before_path", default=None)
        parser.add_argument("--after", dest="after_path", default=None)

    def handle(self, *args, **options):
        if options["snapshot_path"]:
            if not options["workspace_id"]:
                raise CommandError("--snapshot requires --workspace")
            summary = summarize_findings(options["workspace_id"])
            with open(options["snapshot_path"], "w", encoding="utf-8") as handle:
                json.dump(summary, handle, indent=2, sort_keys=True)
            self.stdout.write(
                f"{sum(summary.values())} finding(s) written to "
                f"{options['snapshot_path']}"
            )
            return

        if not (options["before_path"] and options["after_path"]):
            raise CommandError("Provide either --snapshot, or both --before and --after.")

        with open(options["before_path"], encoding="utf-8") as handle:
            before = json.load(handle)
        with open(options["after_path"], encoding="utf-8") as handle:
            after = json.load(handle)

        changed = {
            rule_id: after.get(rule_id, 0) - before.get(rule_id, 0)
            for rule_id in sorted(set(before) | set(after))
            if after.get(rule_id, 0) != before.get(rule_id, 0)
        }

        if not changed:
            self.stdout.write(
                self.style.SUCCESS("No SE-Auditor findings changed across the migration.")
            )
        else:
            self.stdout.write(
                self.style.WARNING("SE-Auditor findings changed across the migration:")
            )
            for rule_id, delta in changed.items():
                self.stdout.write(
                    f"  {rule_id}: {before.get(rule_id, 0)} -> "
                    f"{after.get(rule_id, 0)}  ({delta:+d})"
                )
            # Only name the rule ids that actually moved: TRACE-P1 ("a
            # decomposition root must derive from a StakeholderNeed") and
            # VERIF-P8 ("a leaf must have a verifying TestCase") are the
            # expected, decision-relevant signal for OFFENE FRAGE 2 (the
            # retired same-level link type merged into derives-from
            # reclassifies roots/leaves) — but only when they are among the
            # rules that actually changed.
            expected_signal_ids = {"TRACE-P1", "VERIF-P8"} & set(changed)
            if expected_signal_ids:
                self.stdout.write(
                    "\nExpected for OFFENE FRAGE 2: "
                    f"{', '.join(sorted(expected_signal_ids))} changing here "
                    "reflects former same-level edges between two Requirements "
                    "now counting as hierarchy edges — not a bug to silently "
                    "fix. See OFFENE FRAGE 2 of the traceability-semantik plan."
                )

        unchanged = sorted(set(before) & set(after) - set(changed))
        self.stdout.write(f"\nUnchanged rules: {', '.join(unchanged) or '(none)'}")
