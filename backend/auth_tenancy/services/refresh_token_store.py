"""Sanctioned ``SECURITY DEFINER`` access layer for refresh-token state (#1182).

This module is the *single sanctioned production implementation* that reads and
writes ``public.at_refresh_token`` before a tenant context exists. It wraps the
owner-privileged functions created by
``auth_tenancy/migrations/0021_refresh_token_functions_and_rls.py`` (see IC-1c of
``docs/audit/2026-10/1136-rls-coverage-spec.md``). Those functions exist because
``at_refresh_token`` is now RLS-enabled with the staged pre-auth policy: a plain
(scoped or unscoped) ORM access at login/refresh time would be silently emptied
(or its INSERT rejected) once ``RLS_PREAUTH_ENFORCED`` is on.

Replaced path
-------------
The five functions below replace the previous ``RefreshToken.unscoped`` accesses
one-for-one:

* :func:`claim_refresh_token` ← ``unscoped.select_for_update().filter(jti=...).first()``
* :func:`spend_refresh_token` ← ``record.used_at = ...; record.save(...)``
* :func:`revoke_refresh_family` ← ``unscoped.filter(session_id=..., revoked_at__isnull=True).update(...)``
* :func:`insert_refresh_token` ← ``unscoped.create(...)``
* :func:`purge_expired_refresh_tokens` ← the maintenance command's count/delete

Semantics are deliberately unchanged: the row lock of
``auth_refresh_token_claim`` is held by the caller's Django
``transaction.atomic()`` (``SECURITY DEFINER`` changes only the privilege
context, never the transaction identity), and the INSERT relies on the same
column defaults as ``RefreshToken.unscoped.create()`` did.

Do **not** reintroduce a ``RefreshToken.unscoped`` access on the login, refresh,
logout or cleanup path: under enforcement it silently matches nothing. Extend
this module instead.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.db import connection

__all__ = [
    "CLAIM_SQL",
    "INSERT_SQL",
    "PURGE_SQL",
    "REVOKE_FAMILY_SQL",
    "SPEND_SQL",
    "RefreshTokenState",
    "claim_refresh_token",
    "insert_refresh_token",
    "purge_expired_refresh_tokens",
    "revoke_refresh_family",
    "spend_refresh_token",
]

#: The one sanctioned SQL statements for each operation, kept as module
#: constants so the static guard and the regression suite can assert that no
#: other production module inlines the ``SECURITY DEFINER`` calls.
CLAIM_SQL = (
    "SELECT id, user_id, tenant_id, jti, session_id, used_at, revoked_at "
    "FROM public.auth_refresh_token_claim(%s)"
)
SPEND_SQL = "SELECT public.auth_refresh_token_spend(%s)"
REVOKE_FAMILY_SQL = "SELECT public.auth_revoke_refresh_family(%s, %s)"
INSERT_SQL = "SELECT public.auth_refresh_token_insert(%s, %s, %s, %s, %s)"
PURGE_SQL = "SELECT public.auth_purge_expired_refresh_tokens(%s, %s)"


@dataclass(frozen=True)
class RefreshTokenState:
    """Immutable snapshot of one ``at_refresh_token`` row from the claim read.

    Mirrors the exact columns and types the previous ORM read exposed to
    :meth:`~auth_tenancy.services.authentication.AuthenticationService.rotate_refresh_token`,
    so the rotation/reuse-decision logic is byte-identical over the raw-SQL path.
    """

    id: UUID
    user_id: UUID
    tenant_id: UUID
    jti: UUID
    session_id: UUID
    used_at: datetime | None
    revoked_at: datetime | None


def claim_refresh_token(jti: UUID) -> RefreshTokenState | None:
    """Read the row for *jti* under a row lock, or ``None`` if it is gone.

    ``SELECT ... FOR UPDATE`` runs inside the ``SECURITY DEFINER`` function; the
    lock is held by the caller's transaction and ends with its COMMIT/ROLLBACK,
    exactly like the previous ``select_for_update()``.

    Args:
        jti: The ``jti`` claim of the presented refresh token.

    Returns:
        The row state, or ``None`` when no row carries that ``jti``.
    """
    with connection.cursor() as cursor:
        cursor.execute(CLAIM_SQL, [jti])
        row = cursor.fetchone()
    if row is None:
        return None
    return RefreshTokenState(*row)


def spend_refresh_token(jti: UUID) -> None:
    """Mark the token *jti* as spent (``used_at = now()``).

    Args:
        jti: The ``jti`` claim of the token being exchanged.
    """
    with connection.cursor() as cursor:
        cursor.execute(SPEND_SQL, [jti])


def revoke_refresh_family(session_id: UUID, reason: str) -> int:
    """Revoke every still-live token in the family *session_id*.

    Args:
        session_id: The rotation family (``sid`` claim) to burn.
        reason: ``"reuse_detected"`` or ``"logout"``.

    Returns:
        The number of rows that were still live and are now revoked.
    """
    with connection.cursor() as cursor:
        cursor.execute(REVOKE_FAMILY_SQL, [session_id, reason])
        row = cursor.fetchone()
    return int(row[0])


def insert_refresh_token(
    *,
    user_id: UUID,
    tenant_id: UUID,
    jti: UUID,
    session_id: UUID,
    expires_at: datetime,
) -> UUID:
    """Persist one server-side refresh-token row and return its id.

    The owner-privileged function supplies ``id``/``created_at``/``modified_at``
    and relies on the column defaults (``version``, ``revoked_reason``, …) — the
    same values ``RefreshToken.unscoped.create()`` produced before #1182.

    Args:
        user_id: The token's owner.
        tenant_id: The owner's tenant (stamped before any tenant context exists).
        jti: The token's ``jti`` claim (unique).
        session_id: The token's rotation family (``sid`` claim).
        expires_at: The ``exp`` claim as a timezone-aware datetime.

    Returns:
        The primary key of the inserted row.
    """
    with connection.cursor() as cursor:
        cursor.execute(
            INSERT_SQL, [user_id, tenant_id, jti, session_id, expires_at]
        )
        row = cursor.fetchone()
    return UUID(str(row[0]))


def purge_expired_refresh_tokens(cutoff: datetime, *, apply: bool) -> int:
    """Count (``apply=False``) or delete (``apply=True``) rows past *cutoff*.

    Used by ``cleanup_expired_refresh_tokens`` so the cross-tenant maintenance
    read is owner-privileged and keeps working under enforcement instead of
    silently matching zero rows.

    Args:
        cutoff: Rows with ``expires_at < cutoff`` are affected.
        apply: When false, only counts; when true, deletes and returns the count.

    Returns:
        The number of matching rows (deleted, when ``apply`` is true).
    """
    with connection.cursor() as cursor:
        cursor.execute(PURGE_SQL, [cutoff, apply])
        row = cursor.fetchone()
    return int(row[0])
