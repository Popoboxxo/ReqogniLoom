"""Tenant-agnostic role read primitive for pre-auth token issuance (issue #1181).

This module is the *single sanctioned production implementation* that reads a
user's roles before a tenant context exists. It wraps the ``SECURITY DEFINER``
function ``public.auth_resolve_roles(p_user_id uuid)`` (see
``auth_tenancy/migrations/0016_auth_api_key_lookup_functions.py`` and IC-1b of
``docs/audit/2026-10/1136-rls-coverage-spec.md``). That function exists because
``at_user_role`` is RLS-enabled with the staged pre-auth policy: a plain (scoped
or unscoped) ORM read at login time would be silently emptied once
``RLS_PREAUTH_ENFORCED`` is on.

Deliberately tenant-agnostic (residual R-9, security F10)
---------------------------------------------------------
The primitive filters ONLY by ``user_id`` and ``suspended_at IS NULL`` — it
returns the user's roles across **every** workspace. This is faithful to the read
it replaces (``UserRole.unscoped.filter(...).values_list("role")``) and is the
documented pre-auth boundary: at token-issuance time no workspace is known, so
the ``roles`` claim can only ever be a tenant-wide snapshot.

**Adding a ``tenant_id`` predicate would change observable auth behaviour and is
therefore a behaviour change that requires its own reviewed change — do NOT add
one here.**

Normalisation is unchanged (F4/AC-22): deduplicate, sort and lower-case the raw
role names, so the JWT ``roles`` claim stays byte-identical to the pre-#1181
output. The pure helper :func:`normalize_roles` is importable and testable
without a database; the DB-bound read :func:`fetch_roles_for_user` is separable.
"""
from __future__ import annotations

from collections.abc import Iterable
from uuid import UUID

from django.db import connection

__all__ = [
    "ROLES_SQL",
    "fetch_roles_for_user",
    "normalize_roles",
    "resolve_roles_for_user",
]

#: The one sanctioned SQL statement that resolves roles before a tenant context
#: exists. Kept as a module constant so the static guard
#: ``tests/test_role_read_1181.py`` can prove no other production module inlines
#: the call to ``public.auth_resolve_roles``.
ROLES_SQL = "SELECT role FROM public.auth_resolve_roles(%s)"


def normalize_roles(roles: Iterable[object]) -> tuple[str, ...]:
    """Return the role names deduplicated, sorted and lower-cased.

    Pure and database-free, so the exact normalisation contract is testable
    without a live ``auth_resolve_roles`` function. The expression is the one
    that was previously inlined in
    :meth:`~auth_tenancy.services.password_authentication.PasswordAuthenticationService.resolve_roles`
    and is kept byte-identical to preserve the JWT ``roles`` claim.

    Args:
        roles: Raw role values as returned by the read (any ``str``-able type).

    Returns:
        The deduplicated, ascending-sorted, lower-cased role names.
    """
    return tuple(sorted({str(role).lower() for role in roles}))


def fetch_roles_for_user(user_id: UUID) -> list[str]:
    """Read the user's non-suspended role names via ``auth_resolve_roles``.

    Separated from :func:`normalize_roles` so the (DB-bound) read can be stubbed
    in unit tests that only exercise normalisation. The function filters
    ``user_id`` + ``suspended_at IS NULL`` and is tenant-agnostic (see the module
    docstring, residual R-9).

    Args:
        user_id: The user whose roles are resolved.

    Returns:
        The raw role names for the user, one entry per non-suspended assignment.
    """
    with connection.cursor() as cursor:
        cursor.execute(ROLES_SQL, [user_id])
        return [row[0] for row in cursor.fetchall()]


def resolve_roles_for_user(user_id: UUID) -> tuple[str, ...]:
    """Return the user's normalised role names for the JWT ``roles`` claim.

    The single sanctioned entry point for the pre-auth role read: combines
    :func:`fetch_roles_for_user` with :func:`normalize_roles`. Tenant-agnostic by
    design (residual R-9) — read the module docstring before changing it.

    Args:
        user_id: The user whose roles are resolved.

    Returns:
        Deduplicated, sorted, lower-cased role names across all workspaces.
    """
    return normalize_roles(fetch_roles_for_user(user_id))
