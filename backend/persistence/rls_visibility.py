"""How far can the CURRENT database role see through Row-Level Security?

Every cross-corpus aggregate in this project (the ``/health/?verbose=1``
embedding drift advisory, the warn-mode drift sample, the ``--models`` report of
``verify_embedding_dimensions``) runs on a connection whose visibility is NOT
what the SQL suggests. The embedding tables have ``ENABLE`` + ``FORCE ROW LEVEL
SECURITY`` keyed on ``current_setting('app.current_tenant')``, and
:class:`persistence.tenancy.UnscopedManager` deliberately does **not** bypass
RLS — it only skips the ORM-side tenant filter
(:class:`persistence.tenancy.UnscopedManager` docstring; COMP-PL-006 stays the
backstop). So:

* a role with ``BYPASSRLS`` or superuser rights sees the whole corpus;
* any other role with a tenant context sees exactly that tenant's rows;
* any other role WITHOUT a tenant context sees *nothing* — and an aggregate
  then returns ``0``, which is indistinguishable from "the corpus is clean".

That last case is the trap this module exists for: an unauthenticated endpoint
(``/health*`` is a plain Django ``View`` and sets no tenant) under the shipped
least-privilege app role can never answer a corpus-wide question. Callers must
be able to tell "0 rows drifted" apart from "0 rows visible", so the verdict is
reported instead of being guessed.

One cheap catalog query answers both halves at once (``pg_roles`` for the
capability, ``current_setting(..., true)`` for the ambient tenant). Nothing is
cached: the connection's role is fixed for the process, but the tenant setting
is per request/transaction, and a cached verdict would be exactly the kind of
stale answer this module is meant to prevent.
"""
from __future__ import annotations

from django.db import connections

#: The aggregate covers the whole corpus: the role bypasses RLS
#: (superuser / ``BYPASSRLS``).
COUNT_SCOPE_CORPUS = "corpus"

#: The aggregate covers exactly the ambient tenant's rows: the role is
#: RLS-bound but a tenant context is set, so the count is numeric and correct
#: *for that tenant* -- never corpus-wide.
COUNT_SCOPE_TENANT = "tenant"

#: The aggregate is RLS-shadowed: RLS-bound role, no tenant context. Every
#: count will read ``0`` regardless of the real data, so callers must report
#: "unknown" rather than a confident zero. Also the fail-closed verdict when
#: the probe itself cannot run (non-PostgreSQL backend, dead connection): a
#: visibility we could not prove is not a visibility we may claim.
COUNT_SCOPE_SHADOWED = "shadowed"

#: Constant (never interpolated) probe: capability plus ambient tenant.
_SCOPE_PROBE_SQL = """
SELECT (r.rolbypassrls OR r.rolsuper),
       NULLIF(current_setting('app.current_tenant', true), '')
FROM pg_roles r
WHERE r.rolname = current_user
"""


def count_scope(using: str = "default") -> str:
    """Classify what an aggregate on *using* actually counts (see module docstring).

    Args:
        using: Django database alias. Defaults to the app connection.

    Returns:
        One of :data:`COUNT_SCOPE_CORPUS`, :data:`COUNT_SCOPE_TENANT`,
        :data:`COUNT_SCOPE_SHADOWED`. Never raises: a probe failure yields
        ``COUNT_SCOPE_SHADOWED`` (fail-closed — an unproven visibility is
        reported as unknown, not as a trustworthy number).
    """
    try:
        with connections[using].cursor() as cursor:
            cursor.execute(_SCOPE_PROBE_SQL)
            row = cursor.fetchone()
    except Exception:  # noqa: BLE001 - a visibility probe must never break the caller
        return COUNT_SCOPE_SHADOWED
    if not row:
        return COUNT_SCOPE_SHADOWED
    privileged, tenant = row[0], row[1]
    if privileged:
        return COUNT_SCOPE_CORPUS
    if tenant:
        return COUNT_SCOPE_TENANT
    return COUNT_SCOPE_SHADOWED


def can_see_beyond_tenant(using: str = "default") -> bool:
    """True only when the role sees the whole corpus (RLS is bypassed).

    The narrow question callers of :class:`persistence.tenancy.UnscopedManager`
    actually ask before trusting a cross-tenant aggregate. ``False`` for both an
    RLS-bound role and an unprovable probe, so it can never widen a count that
    is really tenant-scoped.
    """
    return count_scope(using) == COUNT_SCOPE_CORPUS


__all__ = [
    "COUNT_SCOPE_CORPUS",
    "COUNT_SCOPE_SHADOWED",
    "COUNT_SCOPE_TENANT",
    "can_see_beyond_tenant",
    "count_scope",
]
