"""``manage.py honcho_migrate_scopes`` -- attach existing sessions to native scopes.

T-A4-6 (Plan A, PR-A27). Honcho's *scopes* are a visibility boundary over
sessions (T-A4-1 spike, ``deploy/README.md``): a session belongs to a peer and
may additionally be grouped into a scope. This backend only writes scopes when
``HONCHO_USE_NATIVE_SCOPES`` is on, and it does so for sessions created from
then on -- everything written before the flag was switched on would stay
outside any scope. This command closes that gap: it derives, from the local
canonical mirror (``mem_memory_entry``), the ``(scope, scope_id)`` pairs that
already reached Honcho, and attaches each one's session to its native scope.

``--dry-run`` is the DEFAULT
----------------------------
Without ``--no-dry-run`` (alias ``--apply``) the command writes NOTHING: it
never even constructs an SDK client for a write, it only reports what it would
change. The counter-flag is deliberately explicit and long -- attaching scopes
is a change on a foreign service, so it must be asked for by name.

Rollout order (do not invert)
-----------------------------
1. ``python manage.py honcho_migrate_scopes --dry-run``  -- inspect the plan;
2. ``python manage.py honcho_migrate_scopes --no-dry-run`` -- provision scopes;
3. only then, after user approval, set ``HONCHO_USE_NATIVE_SCOPES=true``.

The command therefore works with the flag OFF (that is the point: it is the
precondition for turning the flag on). It reports the flag's current state as
``flag_enabled`` in every line.

Two operational requirements
----------------------------
* **A workspace-level or admin API key is required.** Every scopes route -- and
  every read that passes ``scope=`` -- rejects peer- and session-scoped keys
  with ``401``. The single per-tenant ``HONCHO_API_KEY`` (or the
  ``SystemMemorySettings`` override) must therefore be a workspace-scoped
  token, or every call here fails.
* **A scope is a visibility boundary, NOT an observer.** It is rejected in any
  ``target``/observed position, including as a dream target. This command only
  ever creates a scope and adds its session; it never passes a scope id where
  Honcho expects an observer.

Both requirements are also emitted in each report line under ``notes`` so an
operator sees them without reading this docstring.

Output is JSON Lines, one object per tenant::

    {"tenant": "...", "dry_run": true, "flag_enabled": false,
     "planned_scopes": 2, "planned_entries": 5, "written_scopes": 0,
     "failed": 0, "failures": {}, "skipped_entries": 0,
     "scopes": [{"scope": "user", "scope_id": "...",
                 "native_scope_id": "...", "session_id": "..."}],
     "notes": ["...", "..."]}

Candidate scopes are derived with the SAME id resolvers the backend writes
with (``memory.honcho_backend.scope_session_id_for`` /
``native_scope_id_for``). A set ``backend_ref`` only makes a row a *candidate*
scope -- it does not prove the Honcho session exists: the message publish that
creates the session is fail-open, so a scope whose publish never succeeded has
no ``s_<peer id>`` session and ``POST …/scopes/{id}/sessions`` answers it with
``NotFoundError``. Such scopes are counted as failures (``failed`` /
``failures``) like any other write error; they are not silently skipped. Rows
with a NULL ``backend_ref`` belong to another backend (pgvector leaves it NULL)
and are skipped, never guessed at. A run with ``failed > 0`` still emits its
line and then exits non-zero, so the report survives and an operator sees the
failure without parsing JSON.
"""
from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from django.core.management.base import BaseCommand, CommandError

from memory.backends import (
    MEMORY_BACKEND_REGISTRY,
    _resolve_memory_backend_name,
    _tenant_context,
)
from memory.honcho_backend import (
    HonchoMemoryBackend,
    native_scope_id_for,
    scope_session_id_for,
    use_native_scopes,
)
from memory.models import MemoryEntry
from persistence.models import Tenant

#: Emitted in every report line. Kept terse and stable -- this is the operator
#: facing reminder of the two properties that make scopes different from peers.
_NOTES = (
    "native scopes need a workspace-scoped or admin Honcho API key; "
    "peer- and session-scoped keys are rejected with 401",
    "a scope is a visibility boundary, not an observer: it is invalid in any "
    "target/observed position, including as a dream target",
)


def _parse_uuid(raw: str | None, flag: str) -> UUID | None:
    """Parse an optional UUID CLI value; ``None`` when the flag is absent."""
    if raw is None:
        return None
    try:
        return UUID(str(raw))
    except (TypeError, ValueError) as exc:
        raise CommandError(f"{flag} must be a valid UUID, got {raw!r}") from exc


def _plan_for_tenant(tenant_id: UUID) -> tuple[list[dict[str, Any]], int, int]:
    """Return ``(plan, candidate_entries, skipped_entries)`` for one tenant.

    ``plan`` is one entry per distinct ``(scope, scope_id)`` that already reached
    Honcho, carrying the derived native scope id and session id. The read is
    wrapped in :func:`_tenant_context`, so it is armed per tenant (RLS) and can
    never scan across tenants. The explicit ``tenant_id`` filter is
    belt-and-braces on top of RLS (F8): this command WRITES (``--apply``), and
    row-level security does not constrain a superuser connection, so the filter
    must not depend on the session context alone.
    """
    plan: dict[tuple[str, UUID], dict[str, Any]] = {}
    entries = 0
    skipped = 0
    with _tenant_context(tenant_id):
        rows = MemoryEntry.objects.filter(tenant_id=tenant_id).values(
            "scope", "user_id", "workspace_id", "artifact_id", "backend_ref"
        )
        for row in rows:
            if not row.get("backend_ref"):
                # Not mirrored to Honcho (pgvector leaves backend_ref NULL), so
                # there is no session to attach -- never guessed at.
                skipped += 1
                continue
            scope = row["scope"]
            scope_id = row.get(f"{scope}_id")
            if scope_id is None:
                skipped += 1
                continue
            try:
                native_id = native_scope_id_for(tenant_id, scope, scope_id)
                session_id = scope_session_id_for(tenant_id, scope, scope_id)
            except ValueError:
                # A scope this backend does not know (data drift) is skipped and
                # counted, never silently coerced into another scope.
                skipped += 1
                continue
            entries += 1
            plan[(scope, scope_id)] = {
                "scope": scope,
                "scope_id": scope_id,
                "native_scope_id": native_id,
                "session_id": session_id,
            }
    ordered = sorted(plan.values(), key=lambda item: (item["scope"], item["scope_id"]))
    return ordered, entries, skipped


def _resolve_backend() -> HonchoMemoryBackend:
    """Return the active memory backend, requiring the honcho implementation.

    Module-level so a test can substitute a backend whose ``_client`` is a fake
    SDK -- no live Honcho is ever needed to exercise this command.
    """
    backend_name = _resolve_memory_backend_name()
    if backend_name not in MEMORY_BACKEND_REGISTRY:
        raise CommandError(f"unknown memory backend: {backend_name!r}")
    if backend_name != "honcho":
        raise CommandError(
            "honcho_migrate_scopes requires MEMORY_BACKEND=honcho "
            f"(active backend: {backend_name!r}); native scopes exist only on Honcho"
        )
    from memory.backends import get_memory_backend

    backend = get_memory_backend()
    if not isinstance(backend, HonchoMemoryBackend):
        raise CommandError(
            f"the active backend is not the Honcho backend ({type(backend).__name__})"
        )
    return backend


class Command(BaseCommand):
    """Plan (default) or apply the native-scope migration for one/all tenants."""

    help = (
        "Attach already-written Honcho sessions to native scopes (T-A4-6). "
        "DRY RUN BY DEFAULT: --no-dry-run (alias --apply) is required to write."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--tenant",
            default=None,
            help="Limit the run to one tenant UUID (default: every tenant).",
        )
        dry_run = parser.add_mutually_exclusive_group()
        dry_run.add_argument(
            "--dry-run",
            action="store_true",
            default=True,
            dest="dry_run",
            help="Plan only, write nothing (DEFAULT).",
        )
        dry_run.add_argument(
            "--no-dry-run",
            "--apply",
            action="store_false",
            dest="dry_run",
            help=(
                "Actually create the scopes and attach their sessions on the "
                "Honcho service. Requires a workspace-scoped/admin API key."
            ),
        )

    def handle(self, *args: Any, **options: Any) -> None:
        tenant_id = _parse_uuid(options["tenant"], "--tenant")
        if tenant_id is not None and not Tenant.objects.filter(id=tenant_id).exists():
            # F6: a syntactically valid but nonexistent UUID used to produce a
            # green report with ``planned_scopes: 0`` and exit 0 -- an operator
            # who typo'd the tenant would read that as "nothing to migrate".
            raise CommandError(f"unknown tenant {tenant_id}")
        dry_run = bool(options["dry_run"])

        # A pure plan needs no client, so an unreachable/misconfigured Honcho
        # must not stop the report; the backend is resolved only to WRITE.
        writer = None if dry_run else _resolve_backend()

        tenant_ids = (
            [tenant_id]
            if tenant_id is not None
            else list(Tenant.objects.values_list("id", flat=True))
        )

        total_failed = 0
        for current_tenant in tenant_ids:
            plan, entries, skipped = _plan_for_tenant(current_tenant)
            written = 0
            failures: dict[str, int] = {}
            if writer is not None:
                for item in plan:
                    try:
                        writer.attach_native_scope(
                            current_tenant, item["scope"], item["scope_id"]
                        )
                    except Exception as exc:  # noqa: BLE001 - counted, see docstring
                        reason = type(exc).__name__
                        failures[reason] = failures.get(reason, 0) + 1
                    else:
                        written += 1
            total_failed += sum(failures.values())
            self.stdout.write(
                json.dumps(
                    {
                        "tenant": str(current_tenant),
                        "dry_run": dry_run,
                        "flag_enabled": use_native_scopes(),
                        "planned_scopes": len(plan),
                        "planned_entries": entries,
                        "skipped_entries": skipped,
                        "written_scopes": written,
                        "failed": sum(failures.values()),
                        "failures": failures,
                        "scopes": plan,
                        "notes": list(_NOTES),
                    },
                    default=str,
                )
            )

        if total_failed:
            raise CommandError(
                f"{total_failed} scope(s) could not be migrated; see the 'failures' "
                "field above (a 401 usually means HONCHO_API_KEY is not "
                "workspace-scoped)"
            )
