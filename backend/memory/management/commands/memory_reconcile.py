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
    conclusions are listed and compared.

Scoping: ``--tenant`` limits the report to one tenant; without it every
tenant is walked one at a time, each with a properly armed RLS context (never
a cross-tenant query). ``--workspace`` further limits the local-row report to
one workspace.
"""
from __future__ import annotations

import json
from typing import Any, Optional
from uuid import UUID

from django.core.management.base import BaseCommand, CommandError

from memory.backends import MEMORY_BACKEND_REGISTRY, _resolve_memory_backend_name, _tenant_context
from memory.models import MemoryEntry
from persistence.models import Tenant


def _parse_uuid(raw: Optional[str], flag: str) -> Optional[UUID]:
    """Parse an optional UUID CLI value; ``None`` when the flag is absent."""
    if raw is None:
        return None
    try:
        return UUID(str(raw))
    except (TypeError, ValueError) as exc:
        raise CommandError(f"{flag} must be a valid UUID, got {raw!r}") from exc


def _owner_ids(row: dict[str, Any]) -> tuple[str, Optional[UUID]]:
    """Return ``(scope, scope_id)`` for a ``values()`` row."""
    scope = row["scope"]
    scope_id = row.get(f"{scope}_id")
    return scope, scope_id


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

        unmirrored: list[dict[str, Any]] = []
        orphans: list[dict[str, Any]] = []
        for current_tenant in tenant_ids:
            rows = self._local_rows(current_tenant, workspace_id)
            unmirrored.extend(self._unmirrored_rows(rows, backend_name))
            if backend_name == "honcho":
                orphans.extend(self._honcho_orphans(current_tenant, rows))

        report = {
            "backend": backend_name,
            "tenants_scanned": [str(t) for t in tenant_ids],
            "workspace_filter": str(workspace_id) if workspace_id else None,
            "local_rows_without_backend_ref": unmirrored,
            "backend_objects_without_local_row": orphans,
            "counts": {
                "local_rows_without_backend_ref": len(unmirrored),
                "backend_objects_without_local_row": len(orphans),
            },
        }
        report["ok"] = not orphans and not any(
            row["severity"] != "info" for row in unmirrored
        )

        if options["as_json"]:
            self.stdout.write(json.dumps(report, indent=2, default=str))
        else:
            self._print_human(report)
        # Report-only: exit 0 even when findings exist (never auto-delete).

    # -- local side ------------------------------------------------------

    @staticmethod
    def _local_rows(tenant_id: UUID, workspace_id: Optional[UUID]) -> list[dict[str, Any]]:
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
    def _unmirrored_rows(rows: list[dict[str, Any]], backend_name: str) -> list[dict[str, Any]]:
        severity = "info" if backend_name == "pgvector" else "warning"
        out: list[dict[str, Any]] = []
        for row in rows:
            if row["backend_ref"] is not None:
                continue
            scope, scope_id = _owner_ids(row)
            out.append(
                {
                    "id": str(row["id"]),
                    "scope": scope,
                    "scope_id": str(scope_id) if scope_id else None,
                    "created_at": row["created_at"],
                    "severity": severity,
                    "note": (
                        "pgvector is the backend itself; backend_ref is never set"
                        if backend_name == "pgvector"
                        else "local row has no external backend_ref (never mirrored to honcho)"
                    ),
                }
            )
        return out

    # -- external side (honcho only) -------------------------------------

    @staticmethod
    def _honcho_orphans(tenant_id: UUID, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Conclusions present on Honcho with no matching local row.

        Candidate peers come from the local rows' own ``(scope, scope_id)``
        pairs -- the backend has no peer-enumeration API, and inventing one
        would mean listing every peer a Honcho instance has ever seen.
        """
        from memory.honcho_backend import _MAX_PAGE_SIZE, HonchoMemoryBackend

        backend = HonchoMemoryBackend()
        peers: dict[tuple[str, UUID], set[str]] = {}
        for row in rows:
            scope, scope_id = _owner_ids(row)
            if scope_id is None:
                continue
            refs = peers.setdefault((scope, scope_id), set())
            if row["backend_ref"]:
                refs.add(row["backend_ref"])

        orphans: list[dict[str, Any]] = []
        for (scope, scope_id), local_refs in peers.items():
            try:
                page = backend._conclusions(tenant_id, scope, scope_id).list(size=_MAX_PAGE_SIZE)
            except Exception as exc:  # noqa: BLE001 - report the failure, do not abort the run
                orphans.append(
                    {
                        "scope": scope,
                        "scope_id": str(scope_id),
                        "error": str(exc),
                        "severity": "warning",
                    }
                )
                continue
            for conclusion in page.items:
                if str(conclusion.id) in local_refs:
                    continue
                orphans.append(
                    {
                        "scope": scope,
                        "scope_id": str(scope_id),
                        "backend_ref": str(conclusion.id),
                        "content_preview": (conclusion.content or "")[:120],
                        "severity": "warning",
                        "note": "honcho conclusion has no matching local mem_memory_entry row",
                    }
                )
        return orphans

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
            + ("  [expected for pgvector]" if report["backend"] == "pgvector" else "")
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
        self.stdout.write(
            "  result: consistent" if report["ok"] else "  result: findings above (report only, nothing deleted)"
        )
