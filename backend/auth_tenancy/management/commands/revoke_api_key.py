"""Privileged, ownership-independent API-key revocation (SEC-04).

Why this command exists
-----------------------
The REST endpoint ``DELETE /api/v1/api-keys/<pk>/`` is deliberately
*self-scoped*: ``AuthenticationService.revoke_api_key(..., user_id=...)`` refuses
a key that does not belong to the caller (``api_key_views.py:424``). That is the
correct behaviour for a user-facing endpoint, but it leaves no legitimate path
to revoke a *foreign-owned* or *tenant-legacy* key — e.g. an ``admin``-scope key
whose owner is a decommissioned ``e2e-user`` and which never expires. The audit
track recorded exactly that residue (``docs/audit/2026-09/review/plan/
SECURITY_TRACK_EXECUTION.md`` §"BLOCKER"); the only alternatives were a direct
SQL write or a manual admin column edit, neither of which is auditable or
reviewable.

This command is the missing governed path. It is explicit about being
privileged: it resolves the key across *all* tenants, calls the existing
``AuthenticationService.revoke_api_key`` **without** an owner filter (the
service's documented ``user_id=None`` mode), and records an append-only
``AuditEntry`` in the key's own tenant. It never prints, derives or stores key
material — only the stable UUID and non-secret metadata.

It does **not** weaken the REST endpoint: that endpoint continues to pass the
caller's ``user_id`` and keeps returning 404 for foreign keys. This command is a
separate, operator-only surface (CLI access + ``--apply`` opt-in).

Usage::

    # dry run (default): resolve and report, change nothing
    python manage.py revoke_api_key --key-id 34e0aeae --reason "cleanup legacy admin key"

    # actually revoke (writes exactly one audit entry)
    python manage.py revoke_api_key --key-id 34e0aeae --reason "cleanup legacy admin key" --apply

Safety properties:

* ``--key-id`` accepts a full UUID or an **8+ character** UUID prefix; an
  ambiguous prefix is refused, never guessed.
* Idempotent: an already-revoked key is reported and left untouched; no second
  audit entry is written.
* The revocation and its audit entry share one transaction — a failed audit
  write rolls the revocation back.
"""
from __future__ import annotations

from typing import Any, List
from uuid import UUID

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from audit.events import AuditableOperationOccurred
from audit.models import AuditEntry
from audit.writer import get_writer
from auth_tenancy.models import ApiKey
from auth_tenancy.services.authentication import AuthenticationService
from persistence.tenancy import TenantContext

#: Minimum accepted prefix length. 8 hex chars already narrow the UUID space to
#: a practically unique range; shorter prefixes are refused as ambiguous.
_MIN_PREFIX_LEN = 8

#: Default actor string recorded on the audit entry. The management command is
#: the actor, not a mapped user (no user context exists on the CLI path).
_DEFAULT_ACTOR = "system:revoke_api_key"


class Command(BaseCommand):
    help = (
        "Privileged, ownership-independent revocation of one API key, "
        "identified by full UUID or 8+ character prefix. Uses the existing "
        "AuthenticationService (user_id=None), is idempotent, writes an "
        "append-only audit entry, and never prints key material. Dry-run "
        "unless --apply is given. SEC-04."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--key-id",
            dest="key_id",
            required=True,
            help="Full API-key UUID or an unambiguous 8+ character prefix.",
        )
        parser.add_argument(
            "--reason",
            dest="reason",
            required=True,
            help="Human-readable justification, recorded on the audit entry.",
        )
        parser.add_argument(
            "--actor",
            dest="actor",
            default=_DEFAULT_ACTOR,
            help=f"Actor string for the audit entry (default: {_DEFAULT_ACTOR}).",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Actually revoke the key. Without it the command is a dry run.",
        )

    # -- helpers ----------------------------------------------------------

    @staticmethod
    def _resolve_key(raw: str) -> List[ApiKey]:
        """Return the key(s) matching *raw* (full UUID or prefix)."""
        value = raw.strip().lower()
        if not value:
            raise CommandError("--key-id must not be empty.")
        try:
            full_id = UUID(value)
        except (AttributeError, TypeError, ValueError):
            full_id = None
        if full_id is not None:
            return list(ApiKey.unscoped.filter(id=full_id))
        if len(value) < _MIN_PREFIX_LEN:
            raise CommandError(
                f"--key-id must be a full UUID or at least {_MIN_PREFIX_LEN} "
                "characters; shorter prefixes are ambiguous."
            )
        return list(ApiKey.unscoped.filter(id__startswith=value))

    def _write_audit_entry(self, *, key: ApiKey, actor: str, reason: str) -> None:
        """Write the append-only audit entry for the revocation.

        The entry lands in the key's own tenant (never the caller's): the key is
        the subject and the operator may be cross-tenant by design. Only
        non-secret metadata is recorded.
        """
        event = AuditableOperationOccurred(
            actor=actor,
            actor_type=AuditEntry.ACTOR_TYPE_USER,
            op=AuditEntry.OP_DELETE,
            entity_type="ApiKey",
            entity_id=key.id,
            version=None,
            change_reason=reason,
            details={
                "origin": "management-command",
                "action": "revoke_api_key",
                "owner_user_id": str(key.user_id),
                "tenant_id": str(key.tenant_id),
                "scope": key.scope,
                "principal_type": key.principal_type,
            },
            ctx={"source": "rest"},
        )
        TenantContext.set_tenant(key.tenant_id)
        try:
            get_writer().write(event)
        finally:
            TenantContext.clear_tenant()

    # -- entry point ------------------------------------------------------

    def handle(self, *args: Any, **options: Any) -> None:
        raw = options["key_id"]
        reason = options["reason"].strip()
        actor = (options.get("actor") or _DEFAULT_ACTOR).strip()
        apply_change = bool(options.get("apply"))

        if not reason:
            raise CommandError("--reason must not be empty.")

        matches = self._resolve_key(raw)
        if not matches:
            raise CommandError(f"No API key matches --key-id {raw!r}.")
        if len(matches) > 1:
            prefixes = ", ".join(str(k.id)[:8] for k in matches)
            raise CommandError(
                f"--key-id {raw!r} is ambiguous: {len(matches)} keys match "
                f"({prefixes}). Supply more characters or the full UUID."
            )

        key = matches[0]

        if key.revoked_at is not None:
            self.stdout.write(
                f"API key {key.id} is already revoked at "
                f"{key.revoked_at.isoformat()}; no action taken (idempotent)."
            )
            return

        if not apply_change:
            self.stdout.write(
                f"Dry run: would revoke API key {key.id} "
                f"(name={key.name!r}, tenant={key.tenant_id}, "
                f"owner={key.user_id}, scope={key.scope}). "
                f"Re-run with --apply to revoke and write the audit entry."
            )
            return

        with transaction.atomic():
            AuthenticationService().revoke_api_key(api_key_id=key.id)
            self._write_audit_entry(key=key, actor=actor, reason=reason)

        self.stdout.write(
            self.style.SUCCESS(
                f"Revoked API key {key.id} (name={key.name!r}) and wrote an "
                f"audit entry in tenant {key.tenant_id}."
            )
        )
