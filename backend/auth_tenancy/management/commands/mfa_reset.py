"""Break-glass TOTP reset for staff accounts (#1308, Plan E / WP E3.7).

Why this command exists
-----------------------
A lost or replaced authenticator device, or a ``FIELD_ENCRYPTION_KEY`` rotation
that made every stored TOTP secret undecryptable, leaves a staff account unable
to pass the second login step. There is deliberately **no** REST or MCP path for
this: ``MfaService.reset`` takes neither a TOTP code nor a password (the whole
point is the lost device), so exposing it over an API would let any caller strip
a victim's second factor. This management command — run with operator
privileges on the host — is the only entry point.

What it does, in one transaction:

1. :meth:`MfaService.reset` — deletes the TOTP device *and* every recovery code,
   and writes the ``user.mfa_reset`` audit entry.
2. :meth:`MfaService.grant_enrollment` — issues a **single-use** enrollment grant
   (valid at most 24 h, ``MFA_ENROLL_GRANT_TTL_SECONDS``) and writes the
   ``user.mfa_enroll_grant`` audit entry. The grant is what authorises the
   re-enrollment under ``MFA_STAFF_ENFORCEMENT=required`` (ENT-E7 = A), so it is
   always issued: a reset without one would leave the account unable to enroll.

Both steps share an outer transaction, so a failing grant does not leave the
account with its credential deleted and no way back in.

Idempotent-ish: running it for an account that never enrolled simply removes
nothing and issues the grant; older unused grants are marked used by the service
("at most one valid grant per user").

The command never prints, derives or stores a secret, a TOTP code or a recovery
code — only the username, non-secret counters and the grant's expiry.

Usage::

    python manage.py mfa_reset alice --reason "phone lost, ticket OPS-4711"
"""
from __future__ import annotations

import logging
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from auth_tenancy.models import UserRecoveryCode, UserTotpDevice
from auth_tenancy.services.mfa import MfaError, MfaService, enroll_grant_ttl_seconds
from persistence.models import User

logger = logging.getLogger("reqogniloom.security")

#: Free-form audit actor recorded on both audit entries and in the security log.
#: The CLI has no user context, so the label names the acting surface instead of
#: inventing an identity (``MfaService.reset``/``grant_enrollment`` take the
#: label as-is and never resolve it).
ACTOR = "mfa_reset (CLI)"


class Command(BaseCommand):
    help = (
        "Break-glass reset of a staff account's TOTP second factor: removes the "
        "device and all recovery codes, then issues a single-use enrollment "
        "grant (<= 24 h) so the account can enroll again. Writes the "
        "user.mfa_reset and user.mfa_enroll_grant audit entries. #1308 (E3.7)."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "username",
            help="Username of the staff account whose second factor is reset.",
        )
        parser.add_argument(
            "--reason",
            dest="reason",
            required=True,
            help="Mandatory justification, recorded on both audit entries.",
        )

    # -- helpers ----------------------------------------------------------

    @staticmethod
    def _resolve_user(raw: str) -> User:
        """Return the single user matching ``raw`` (case-insensitive, #125)."""
        username = (raw or "").strip()
        if not username:
            raise CommandError("username must not be empty.")
        user = User.objects.filter(username__iexact=username).first()
        if user is None:
            raise CommandError(f"No user with username {username!r}.")
        return user

    # -- entry point ------------------------------------------------------

    def handle(self, *args: Any, **options: Any) -> None:
        user = self._resolve_user(options["username"])
        reason = (options.get("reason") or "").strip()
        if not reason:
            raise CommandError("--reason must not be empty.")

        had_device = UserTotpDevice.objects.filter(user=user).exists()
        recovery_code_count = UserRecoveryCode.objects.filter(user=user).count()

        service = MfaService()
        try:
            with transaction.atomic():
                service.reset(user, actor=ACTOR)
                grant = service.grant_enrollment(user, actor=ACTOR, reason=reason)
        except MfaError as exc:
            # Fail closed: the outer transaction rolled the reset back, so the
            # account still has whatever credential it had before this run.
            raise CommandError(f"MFA reset failed for {user.username!r}: {exc}") from exc

        ttl_seconds = enroll_grant_ttl_seconds()
        logger.warning(
            "mfa_reset command username=%s actor=%s device_removed=%s "
            "recovery_codes_removed=%d grant_id=%s",
            user.username,
            ACTOR,
            had_device,
            recovery_code_count,
            grant.id,
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Reset second factor for '{user.username}': "
                f"device removed={had_device}, "
                f"recovery codes removed={recovery_code_count}."
            )
        )
        self.stdout.write(
            f"Issued single-use enrollment grant {grant.id} "
            f"(expires {grant.expires_at.isoformat()}, TTL {ttl_seconds}s). "
            "The user must enroll again within that window."
        )
        if not user.is_active:
            self.stderr.write(
                self.style.WARNING(
                    f"'{user.username}' is deactivated; enrollment is refused "
                    "for an inactive account until it is reactivated."
                )
            )


__all__ = ["ACTOR", "Command"]
