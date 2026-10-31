"""Enforcement cutover for the staff second factor (#1308, Plan E / WP E3.9).

Sessions issued before the cutoff carry ``amr=["pwd"]`` only, and that claim
lives *inside* the JWT, not in the refresh-token table — so a password-only
session cannot be upgraded after the fact. Flipping ``MFA_STAFF_ENFORCEMENT`` to
``required`` therefore needs a cutover that invalidates every staff session so
each account re-authenticates once with its second factor.

1. Revoke every live refresh-token family of a staff user, per tenant, via
   ``revoke_refresh_family`` (the sanctioned ``SECURITY DEFINER`` store).
2. Delete ``django.contrib.sessions`` rows whose decoded ``_auth_user_id`` is a
   staff user (the admin cookie login is a second credential).
3. Inventory non-revoked API keys owned by staff via ``collect_inventory`` —
   list only, never revoke (ENT-E8 = A), never print key material.
4. Write one ``user.mfa_cutover`` audit row per affected user with a tenant,
   plus one ``reqogniloom.security`` summary line.
5. Report per-staff enrollment (``mfa_enrolled``/``confirmed_at``) and the active
   enforcement mode, so an operator sees an unenrolled-staff lockout *before*
   flipping the flag.

``--dry-run`` reports the same counters and writes nothing. Revocation and audit
of one user share a ``transaction.atomic()``: a failed audit row rolls that
user's revocation back. The command is deliberately not transactional *across*
tenants — a failure in tenant B must not roll back tenant A's revocations — and
it always prints the accumulated report before a failed tenant turns into a
non-zero exit. A re-run is idempotent (``revoked_at IS NULL`` is the predicate).

Invariant for future refactors: ``public.auth_revoke_refresh_family`` has **no
tenant guard** of its own. It revokes every row of the ``session_id`` it is
given, so the caller must only pass ids it enumerated under an active tenant
context *and* a staff-user filter. Do not call it with a session id from an
untrusted input or before the tenant/staff scoping above.

.. warning::
   ``MFA_STAFF_ENFORCEMENT=required`` must **not** be enabled before this command
   has been run in this deployment (hardening F2 from the P3-3 review).

Usage::

    python manage.py mfa_enforce_cutover --dry-run
    python manage.py mfa_enforce_cutover [--format text|json]
"""

from __future__ import annotations

import json
import logging
from argparse import ArgumentParser
from collections import defaultdict
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from typing import Any
from uuid import UUID

from django.contrib.sessions.models import Session
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from audit.models import AuditEntry
from audit.services import log_write
from auth_tenancy.management.commands.inventory_api_keys import collect_inventory
from auth_tenancy.models import RefreshToken, UserTotpDevice
from auth_tenancy.services.mfa import enforcement_mode
from auth_tenancy.services.refresh_token_store import revoke_refresh_family
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User
from persistence.tenancy import TenantContext

logger = logging.getLogger("reqogniloom.security")

#: Reason stamped on every revoked family; mirrors the audit operation name.
CUTOVER_REASON = "mfa_cutover"
ACTOR = "mfa_enforce_cutover (CLI)"
#: Repeated in text and JSON output: the cutover and the env flag are two
#: separate steps and their order matters.
WARNING = (
    "MFA_STAFF_ENFORCEMENT=required must not be enabled until this cutover has "
    "been run in this deployment."
)
_VALID_FORMATS = ("text", "json")


@contextmanager
def _tenant_context(tenant_id: UUID) -> Iterator[None]:
    """Activate ``tenant_id`` for both isolation layers, restoring the previous one.

    :func:`persistence.middleware.set_request_tenant` sets the app-layer
    :class:`~persistence.tenancy.TenantContext` (what the tenant-scoped managers
    filter on) *and* the PostgreSQL ``app.current_tenant`` GUC that the staged
    RLS policy on ``at_refresh_token`` reads. The thread-local alone would be
    enough for the ORM filter but silently empty under ``RLS_PREAUTH_ENFORCED``.

    Index §f.8: remember what was armed, restore it in ``finally``; when nothing
    was armed, clear instead.
    """
    previous = TenantContext.get_tenant() if TenantContext.is_set() else None
    try:
        set_request_tenant(tenant_id)
        yield
    finally:
        if previous is not None:
            set_request_tenant(previous)
        else:
            clear_request_tenant()


class Command(BaseCommand):
    """Revoke all staff sessions and inventory staff API keys before ``required``."""

    help = (
        "Enforcement cutover before MFA_STAFF_ENFORCEMENT=required (#1308, "
        "E3.9): revoke every live refresh-token family and Django-admin session "
        "of staff users, inventory their API keys, audit user.mfa_cutover. "
        "Reports counters as text or JSON."
    )

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            "--dry-run",
            dest="dry_run",
            action="store_true",
            help="Count only; revoke, delete and audit nothing.",
        )
        parser.add_argument(
            "--format",
            dest="format",
            choices=_VALID_FORMATS,
            default="text",
            help="Output format: text (default) or json.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        output_format = options.get("format") or "text"
        if output_format not in _VALID_FORMATS:
            raise CommandError(
                f"Unsupported --format {output_format!r}; "
                f"expected one of {', '.join(_VALID_FORMATS)}."
            )
        dry_run = bool(options.get("dry_run"))
        now = timezone.now()
        mode = enforcement_mode()
        staff_users = list(
            User.objects.filter(Q(is_staff=True) | Q(is_superuser=True)).order_by("username")
        )
        staff_ids = {str(user.id) for user in staff_users}
        staff_enrollment, unenrolled = self._staff_enrollment(staff_users)
        refresh = self._cutover_refresh_tokens(staff_users=staff_users, dry_run=dry_run)
        warnings = [WARNING]
        if mode == "required" and unenrolled:
            names = ", ".join(
                member["username"] for member in staff_enrollment if not member["mfa_enrolled"]
            )
            warnings.append(
                f"MFA_STAFF_ENFORCEMENT=required but {unenrolled} staff account(s) "
                f"are not enrolled: {names}. These accounts cannot complete the "
                "second login step."
            )
        payload = {
            "dry_run": dry_run,
            "generated_at": now.isoformat(),
            "enforcement": mode,
            "staff_users": len(staff_users),
            "unenrolled_staff": unenrolled,
            "staff": staff_enrollment,
            "refresh_families": refresh["families"],
            "refresh_tokens": refresh["tokens"],
            "admin_sessions": self._cutover_admin_sessions(
                staff_user_ids=staff_ids, dry_run=dry_run
            ),
            "audited_users": refresh["audited_users"],
            "staff_api_keys": self._staff_api_keys(staff_user_ids=staff_ids, now=now),
            "warnings": warnings,
            "failures": refresh["failures"],
        }
        logger.warning(
            "mfa_enforce_cutover dry_run=%s enforcement=%s staff_users=%d "
            "unenrolled_staff=%d refresh_families=%d refresh_tokens=%d "
            "admin_sessions=%d staff_api_keys=%d audited_users=%d failures=%d",
            dry_run,
            mode,
            payload["staff_users"],
            unenrolled,
            payload["refresh_families"],
            payload["refresh_tokens"],
            payload["admin_sessions"],
            len(payload["staff_api_keys"]),
            payload["audited_users"],
            len(payload["failures"]),
        )
        # Always print the accumulated report, even when tenants failed below:
        # the operator has to see how far the run got before the exit code turns.
        if output_format == "json":
            self.stdout.write(json.dumps(payload, indent=2, sort_keys=True))
        else:
            self._write_text(payload, dry_run=dry_run)
        if payload["failures"]:
            summary = "; ".join(
                f"{failure['tenant_slug']}: {failure['error']}" for failure in payload["failures"]
            )
            raise CommandError(
                f"MFA cutover failed for {len(payload['failures'])} tenant(s): {summary}"
            )

    @staticmethod
    def _staff_enrollment(staff_users: list[User]) -> tuple[list[dict], int]:
        """Return per-staff enrollment state and the unenrolled count.

        Exactly one query over the global (non-tenant-scoped)
        ``UserTotpDevice`` table: only ``confirmed_at`` is read, never
        ``secret_ciphertext``, and the report carries usernames + timestamps only.
        """
        confirmed = dict(
            UserTotpDevice.objects.filter(
                user_id__in=[user.id for user in staff_users],
                confirmed_at__isnull=False,
            ).values_list("user_id", "confirmed_at")
        )
        records = [
            {
                "user_id": str(user.id),
                "username": user.username,
                "mfa_enrolled": user.id in confirmed,
                "confirmed_at": (confirmed[user.id].isoformat() if user.id in confirmed else None),
            }
            for user in staff_users
        ]
        return records, sum(1 for record in records if not record["mfa_enrolled"])

    def _cutover_refresh_tokens(self, *, staff_users: list[User], dry_run: bool) -> dict:
        """Revoke (or count) every live staff refresh family, per tenant.

        ``tokens`` counts the rows ``revoke_refresh_family`` would/does hit; a
        family can hold several spent-but-unrevoked rows. Users without a tenant
        own no refresh rows (``issue_refresh_token`` refuses them).

        A failing tenant is recorded in ``failures`` and the loop continues, so
        one broken tenant cannot hide the progress made in the others. Each
        user's revocation and audit row share one ``transaction.atomic()``: if the
        audit insert fails, that user's revocation is rolled back (the target is
        an audited security act, not a best-effort write).
        """
        staff_by_tenant: dict[UUID, list[User]] = defaultdict(list)
        for user in staff_users:
            if user.tenant_id is not None:
                staff_by_tenant[user.tenant_id].append(user)

        families = tokens = audited_users = 0
        failures: list[dict[str, str]] = []
        tenants = Tenant.objects.filter(id__in=staff_by_tenant).order_by("slug")
        for tenant in tenants:
            tenant_staff = staff_by_tenant[tenant.id]
            try:
                with _tenant_context(tenant.id):
                    rows = list(
                        RefreshToken.objects.filter(
                            user_id__in=[u.id for u in tenant_staff],
                            revoked_at__isnull=True,
                        ).values("user_id", "session_id")
                    )
                    families_by_user: dict[UUID, set[UUID]] = defaultdict(set)
                    for row in rows:
                        families_by_user[row["user_id"]].add(row["session_id"])
                    if dry_run:
                        families += sum(len(s) for s in families_by_user.values())
                        tokens += len(rows)
                        continue
                    for user in tenant_staff:
                        session_ids = families_by_user.get(user.id, set())
                        if not session_ids:
                            continue
                        with transaction.atomic():
                            revoked_rows = sum(
                                revoke_refresh_family(sid, CUTOVER_REASON) for sid in session_ids
                            )
                            self._audit_cutover(
                                user,
                                families_revoked=len(session_ids),
                                rows_revoked=revoked_rows,
                            )
                        families += len(session_ids)
                        tokens += revoked_rows
                        audited_users += 1
            except Exception as exc:  # noqa: BLE001 - per-tenant isolation
                failures.append(
                    {
                        "tenant_slug": tenant.slug,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
        return {
            "families": families,
            "tokens": tokens,
            "audited_users": audited_users,
            "failures": failures,
        }

    @staticmethod
    def _audit_cutover(user: User, *, families_revoked: int, rows_revoked: int) -> None:
        """Write one ``user.mfa_cutover`` entry inside the active tenant context."""
        log_write(
            actor=str(user.id),
            actor_type=AuditEntry.ACTOR_TYPE_USER,
            operation=AuditEntry.OP_USER_MFA_CUTOVER,
            entity_type="User",
            entity_id=user.id,
            change_reason="MFA enforcement cutover: staff session revoked",
            details={
                "reason": CUTOVER_REASON,
                "refresh_families_revoked": families_revoked,
                "refresh_rows_revoked": rows_revoked,
                "actor": ACTOR,
            },
            ctx={"source": "rest"},
        )

    @staticmethod
    def _cutover_admin_sessions(*, staff_user_ids: set[str], dry_run: bool) -> int:
        """Delete admin sessions owned by staff; return the matched row count.

        Session data is signed; a row that cannot be decoded (corrupt data,
        rotated ``SECRET_KEY``) is left alone because the command cannot prove it
        belongs to a staff account. Sessions are not tenant-scoped, so this runs
        once across all tenants.
        """
        matched = [
            session.session_key
            for session in Session.objects.all().iterator()
            if session.get_decoded().get("_auth_user_id") in staff_user_ids
        ]
        if not dry_run and matched:
            Session.objects.filter(pk__in=matched).delete()
        return len(matched)

    @staticmethod
    def _staff_api_keys(*, staff_user_ids: set[str], now: datetime) -> list[dict]:
        """Non-revoked staff API keys, metadata only — no key material, no revoke.

        ENT-E8 = A makes the cutover an inventory plus an expiry obligation for
        *new* staff keys, not a mass revocation.
        """
        return [
            {
                "key_id": row["key_id"],
                "name": row["name"],
                "tenant_slug": row["tenant_slug"],
                "owner_user_id": row["owner_user_id"],
                "owner_username": row["owner_username"],
                "expires_at": row["expires_at"],
                "expiry_state": row["expiry_state"],
                "last_used_at": row["last_used_at"],
                "usage_state": row["usage_state"],
            }
            for row in collect_inventory(now=now)
            if row["not_revoked"] and row["owner_user_id"] in staff_user_ids
        ]

    def _write_text(self, payload: dict[str, Any], *, dry_run: bool) -> None:
        """Render the human-readable report (no secrets, deterministic labels)."""
        families_verb = "would be revoked" if dry_run else "revoked"
        sessions_verb = "would be deleted" if dry_run else "deleted"
        header = "MFA enforcement cutover" + (" — DRY RUN" if dry_run else "")
        self.stdout.write(self.style.MIGRATE_HEADING(header))
        for warning in payload["warnings"]:
            self.stdout.write(self.style.WARNING(f"WARNING: {warning}"))
        self.stdout.write(f"Enforcement: {payload['enforcement']}")
        self.stdout.write(
            f"Staff users: {payload['staff_users']} (unenrolled: {payload['unenrolled_staff']})"
        )
        for member in payload["staff"]:
            state = (
                f"enrolled since {member['confirmed_at']}"
                if member["mfa_enrolled"]
                else "NOT ENROLLED"
            )
            self.stdout.write(f"  - {member['username']}: {state}")
        self.stdout.write(
            f"Refresh families {families_verb}: {payload['refresh_families']} "
            f"(rows: {payload['refresh_tokens']})"
        )
        self.stdout.write(f"Django admin sessions {sessions_verb}: {payload['admin_sessions']}")
        self.stdout.write(f"Staff API keys (not revoked): {len(payload['staff_api_keys'])}")
        for key in payload["staff_api_keys"]:
            self.stdout.write(
                f"  - {key['name']} (owner={key['owner_username']}, "
                f"tenant={key['tenant_slug']}, expiry={key['expiry_state']})"
            )
        if dry_run:
            self.stdout.write("Audited users: 0 (dry run writes nothing)")
        else:
            self.stdout.write(f"Audited users: {payload['audited_users']}")
        if payload["failures"]:
            self.stdout.write(self.style.ERROR(f"Failures: {len(payload['failures'])} tenant(s)"))
            for failure in payload["failures"]:
                self.stdout.write(
                    self.style.ERROR(f"  - {failure['tenant_slug']}: {failure['error']}")
                )


__all__ = ["ACTOR", "CUTOVER_REASON", "WARNING", "Command"]
