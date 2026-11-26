"""Operator bootstrap password floor for ``SYSTEM_ADMIN_PASSWORD`` (P1.1).

FINDING (2026-11-25 REST/MCP security review, M-1): the shipped ``.env`` of a
local deployment carried ``SYSTEM_ADMIN_PASSWORD=admin``, and neither
``bootstrap_admin`` nor the ``post_migrate`` self-init path looked at the value
at all — it went straight into ``User.set_password``. The admin account is the
one credential that can reach every tenant, workspace and secret in the
deployment, so "the operator supplied it out of band" cannot also mean "any
string is acceptable".

WHAT THIS IS NOT. It is *not* the user-facing password policy and it does not
replace Django's ``AUTH_PASSWORD_VALIDATORS`` for people who change their own
password (that is ``auth_tenancy.services.password_policy``). The
operator/disaster-recovery exemption documented in ``.env.example`` stays
exactly as it was: a 12-character passphrase that no validator would rate
"strong" must still bootstrap a fresh instance, because the alternative is a
deployment nobody can log into.

It is a *floor*: length >= 8, not one of the handful of tokens every credential
scanner tries first, and no documentation placeholder marker.

Pure stdlib on purpose — no Django import, no ORM, no settings access — so the
management command, the ``post_migrate`` self-init path and the startup system
check (``reqogniloom.checks`` → ``reqogniloom.W012``) share exactly one
definition and a settings-time check never has to touch the database.
"""
from __future__ import annotations

#: Minimum length for the operator-supplied admin password.
MIN_LENGTH = 8

#: Case-insensitive, exact-match denylist: the values that appear in every
#: tutorial, CI fixture and credential-stuffing wordlist. Kept short on purpose —
#: this is a floor, not a dictionary attack on the operator.
DENYLIST: frozenset[str] = frozenset(
    {
        "admin",
        "password",
        "changeme",
        "change-me",
        "letmein",
        "12345678",
        "qwerty",
        "admin123",
    }
)

#: Case-insensitive substrings that only ever occur in documentation templates.
#: A value carrying one of these was copied from a template, not chosen.
PLACEHOLDER_MARKERS: tuple[str, ...] = ("change-me", "changeme", "placeholder")


def bootstrap_password_rejection_reason(value: str) -> str | None:
    """Return why ``value`` is unacceptable, or ``None`` when it is fine.

    The returned phrase is a predicate complement ("is shorter than 8
    characters"), so callers can interpolate it into their own sentence:
    ``f"SYSTEM_ADMIN_PASSWORD {reason}."``.

    The order is "most specific first": a documentation marker beats the
    denylist (``changeme`` is both), and the denylist beats the length, so
    ``admin`` is reported as a well-known value rather than merely as a short
    one.

    The value itself is never part of the return value or of any message built
    from it: these strings end up in ``CommandError`` output, ``post_migrate``
    logs and ``manage.py check`` diagnostics, and echoing a secret there would
    be a worse problem than the one being reported.

    Args:
        value: The candidate password.

    Returns:
        ``None`` if acceptable, otherwise a short reason phrase.
    """
    candidate = value.strip()
    folded = candidate.casefold()
    if any(marker in folded for marker in PLACEHOLDER_MARKERS):
        return "still carries a change-me/changeme/placeholder marker"
    if folded in DENYLIST:
        return "is one of the trivial passwords every credential scanner tries first"
    if len(candidate) < MIN_LENGTH:
        return f"is shorter than {MIN_LENGTH} characters"
    return None


def is_acceptable_bootstrap_password(value: str) -> bool:
    """True when ``value`` passes the operator bootstrap floor."""
    return bootstrap_password_rejection_reason(value) is None


__all__ = [
    "DENYLIST",
    "MIN_LENGTH",
    "PLACEHOLDER_MARKERS",
    "bootstrap_password_rejection_reason",
    "is_acceptable_bootstrap_password",
]
