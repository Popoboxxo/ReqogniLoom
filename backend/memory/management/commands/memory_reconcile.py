"""``manage.py memory_reconcile`` — READ-ONLY reconciliation report.

RFC #1002 PR A. Compares the local canonical store (``mem_memory_entry``)
against the active memory backend and prints a report. It NEVER deletes or
repairs anything -- exit code 0 is "report produced", not "everything is
consistent"; the operator decides what (if anything) to do next.
:cclass:`~django.core.management.base.CommandError` is raised only for
unrecoverable problems (unknown backend name, malformed UUID).

Two findings are reported:

``local_rows_without_backend_ref``
    Local rows that were never mirrored to the external backend
    (``backend_ref IS NULL``). For the default ``pgvector`` backend this is
    EXPECTED -- pgvector IS the external backend, so it never sets
    ``backend_ref`` at all -- and is therefore marked ``severity: info``.
    Under ``honcho`` a NULL ``backend_ref`` means a write that reached the
    local table but not the external service, which is marked
    ``severity: warning``.

``backend_objects_without_local_row``
    Conclusions that exist on the external Honcho service with no matching
    local ``backend_ref`` (severity ``warning``). Only implementable for
    ``honcho``: candidate peers are derived from the local rows' scope/owner
    pairs (the backend never enumerates peers itself), then each peer's
    conclusions are listed and compared. For ``qdrant`` this is the analogous
    scan: candidate scopes are derived from the Qdrant collections themselves
    (matching the configured prefix) -- NOT from surviving local rows -- so a
    scope whose local rows were all deleted is still covered, and ``scroll`` is
    paginated so a collection larger than one page is fully scanned. Qdrant
    points store no content (Postgres is canonical), so these findings carry no
    ``content_preview``.

``scan_findings``
    Qdrant collections (or the collection listing itself) that could not be
    read. A blind spot is reported as ``severity: warning`` and turns ``ok``
    false, instead of silently under-reporting orphans.

Scoping: ``--tenant`` limits the report to one tenant; without it every
tenant is walked one at a time, each with a properly armed RLS context (never
a cross-tenant query). ``--workspace`` further limits the local-row report to
one workspace.
"""
from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from django.core.management.base import BaseCommand, CommandError

from memory.backends import MEMORY_BACKEND_REGISTRY, _resolve_memory_backend_name, _tenant_context
from memory.models import MemoryEntry
from persistence.models import Tenant


def _parse_uuid(raw: str | None, flag: str) -> UUID | None:
    """Parse an optional UUID CLI value; ``None`` when the flag is absent."""
    if raw is None:
        return None
    try:
        return UUID(str(raw))
    except (TypeError, ValueError) as exc:
        raise CommandError(f"{flag} must be a valid UUID, got {raw!r}") from exc


class Command(BaseCommand):
    help = (
        "Read-only reconciliation report between mem_memory_entry and the "
        "active memory backend. Never deletes anything."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--tenant",
            default=None,
            help="Limit the report to one tenant UUID (default: every tenant).",
        )
        parser.add_argument(
            "--workspace",
            default=None,
            help="Limit the local-row report to one workspace UUID.",
        )
        parser.add_argument(
            "--backend",
            default=None,
            help="Backend to inspect (default: the active SystemMemorySettings/env backend).",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            dest="as_json",
            help="Emit the report as JSON instead of a human-readable summary.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        backend_name = options["backend"] or _resolve_memory_backend_name()
        if backend_name not in MEMORY_BACKEND_REGISTRY:
            raise CommandError(f"unknown memory backend: {backend_name!r}")

        tenant_id = _parse_uuid(options["tenant"], "--tenant")
        workspace_id = _parse_uuid(options["workspace"], "--workspace")

        tenant_ids = (
            [tenant_id] if tenant_id is not None else list(Tenant.objects.values_list("id", flat=True))
        )

        backend_cls = MEMORY_BACKEND_REGISTRY[backend_name]
        external_store = backend_cls.capabilities.external_store

        unmirrored: list[dict[str, Any]] = []
        orphans: list[dict[str, Any]] = []
        for current_tenant in tenant_ids:
            rows = self._local_rows(current_tenant, workspace_id)
            unmirrored.extend(self._unmirrored_rows(rows, external_store))

        # Provider-owned external scan: no backend-name branching here. A
        # backend without an external store returns ([], []) by default.
        scan_findings: list[dict[str, Any]] = []
        if external_store:
            orphans, scan_findings = backend_cls().reconcile_external(
                tenant_ids, workspace_id
            )

        report = {
            "backend": backend_name,
            "external_store": external_store,
            "tenants_scanned": [str(t) for t in tenant_ids],
            "workspace_filter": str(workspace_id) if workspace_id else None,
            "local_rows_without_backend_ref": unmirrored,
            "backend_objects_without_local_row": orphans,
            "scan_findings": scan_findings,
            "counts": {
                "local_rows_without_backend_ref": len(unmirrored),
                "backend_objects_without_local_row": len(orphans),
                "scan_findings": len(scan_findings),
            },
        }
        report["ok"] = (
            not orphans
            and not scan_findings
            and not any(row["severity"] != "info" for row in unmirrored)
        )

        if options["as_json"]:
            self.stdout.write(json.dumps(report, indent=2, default=str))
        else:
            self._print_human(report)
        # Report-only: exit 0 even when findings exist (never auto-delete).

    # -- local side ------------------------------------------------------

    @staticmethod
    def _local_rows(tenant_id: UUID, workspace_id: UUID | None) -> list[dict[str, Any]]:
        with _tenant_context(tenant_id):
            qs = MemoryEntry.objects.all()
            if workspace_id is not None:
                qs = qs.filter(workspace_id=workspace_id)
            return list(
                qs.values(
                    "id",
                    "scope",
                    "workspace_id",
                    "user_id",
                    "artifact_id",
                    "backend_ref",
                    "content",
                    "created_at",
                )
            )

    @staticmethod
    def _unmirrored_rows(
        rows: list[dict[str, Any]], external_store: bool
    ) -> list[dict[str, Any]]:
        severity = "warning" if external_store else "info"
        out: list[dict[str, Any]] = []
        for row in rows:
            if row["backend_ref"] is not None:
                continue
            scope = row["scope"]
            scope_id = row.get(f"{scope}_id")
            out.append(
                {
                    "id": str(row["id"]),
                    "scope": scope,
                    "scope_id": str(scope_id) if scope_id else None,
                    "created_at": row["created_at"],
                    "severity": severity,
                    "note": (
                        "no external store; backend_ref is never set"
                        if not external_store
                        else "local row has no external backend_ref (never mirrored)"
                    ),
                }
            )
        return out

    # -- output ----------------------------------------------------------

    def _print_human(self, report: dict[str, Any]) -> None:
        self.stdout.write(f"memory_reconcile — backend={report['backend']}")
        self.stdout.write(
            f"  tenants scanned: {len(report['tenants_scanned'])}"
            + (f" (workspace filter: {report['workspace_filter']})" if report["workspace_filter"] else "")
        )
        unmirrored = report["local_rows_without_backend_ref"]
        orphans = report["backend_objects_without_local_row"]
        self.stdout.write(
            f"  local rows without backend_ref: {len(unmirrored)}"
            + ("  [expected: no external store]" if not report.get("external_store") else "")
        )
        for row in unmirrored[:20]:
            self.stdout.write(
                f"    - {row['id']} scope={row['scope']} scope_id={row['scope_id']} severity={row['severity']}"
            )
        if len(unmirrored) > 20:
            self.stdout.write(f"    ... and {len(unmirrored) - 20} more")
        self.stdout.write(f"  backend objects without local row: {len(orphans)}")
        for row in orphans[:20]:
            if "error" in row:
                self.stdout.write(f"    - scope={row['scope']} scope_id={row['scope_id']} ERROR={row['error']}")
            else:
                self.stdout.write(
                    f"    - {row['backend_ref']} scope={row['scope']} scope_id={row['scope_id']}"
                )
        if len(orphans) > 20:
            self.stdout.write(f"    ... and {len(orphans) - 20} more")
        scan_findings = report.get("scan_findings") or []
        if scan_findings:
            self.stdout.write(f"  scan findings (blind spots): {len(scan_findings)}")
            for row in scan_findings[:20]:
                label = row.get("collection") or "<collection list>"
                self.stdout.write(f"    - {label} ERROR={row['error']}")
            if len(scan_findings) > 20:
                self.stdout.write(f"    ... and {len(scan_findings) - 20} more")
        self.stdout.write(
            "  result: consistent" if report["ok"] else "  result: findings above (report only, nothing deleted)"
        )
