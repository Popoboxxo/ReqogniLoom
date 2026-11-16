"""Per-API-key MCP policy: ``scope`` and ``tool_groups`` (spec section 6).

Two filters with deliberately different force, which the spec calls out as the
important distinction:

* ``scope`` is a REAL security boundary — a read-scoped key sees no write tool
  in ``tools/list`` *and* is rejected by ``tools/call``. The tier machinery
  behind that (:mod:`auth_tenancy.services.authorization`,
  ``scope_denial_reason``) is shared with REST and stays the single source of
  truth; :attr:`ApiKeyPolicy.is_read_only` only exposes the binary question
  ("may this key write at all?") for the manifest side.
* ``tool_groups`` is PURE CATALOG CURATION — it only narrows what
  ``tools/list`` advertises, so a client carries fewer tokens of manifest.
  Every tool the key's role and ``scope`` allow stays callable by name.

Read via one indexed primary-key query instead of being threaded through
``IdentityClaims`` / ``AuthContext``: those are project-wide identity
contracts shared with REST, Celery and the audit writer, and MCP-specific
curation fields do not belong on them. ``scope`` is already on the context
(#865) — the same row read serves both, so no extra query is added for it.

Requirements: REQ-L2-MC-006, REQ-L2-MC-007.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional
from uuid import UUID

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ApiKeyPolicy:
    """Effective MCP policy of one API key.

    Attributes:
        scope: ``ApiKey.scope`` — ``read_only``/``read``, ``author``,
            ``admin``/``write`` (see
            :data:`auth_tenancy.models.API_KEY_SCOPE_CHOICES`). Defaults to the
            legacy widest tier, which is the behaviour every pre-existing key
            has.
        tool_groups: Group prefixes to advertise. Empty means "every group",
            which is the pre-existing behaviour every key already has.
    """

    scope: str = "write"
    tool_groups: tuple[str, ...] = ()

    @property
    def is_read_only(self) -> bool:
        """Return whether this key may not execute any write tool.

        Delegates to the shared #865 gate (``scope_denial_reason``) rather than
        comparing against a literal here, so the two legacy aliases
        (``read``/``read_only``) and any future read tier keep working without
        a second, diverging table. An unknown scope name answers ``True``
        (fail-closed) exactly as that gate does.
        """
        from auth_tenancy.services.authorization import Operation, scope_denial_reason

        return scope_denial_reason(self.scope, Operation.WRITE) is not None

    def allows_group(self, prefix: str) -> bool:
        """Return whether *prefix* may appear in this key's ``tools/list``."""
        if not self.tool_groups:
            return True
        return prefix in self.tool_groups


#: Returned whenever no key-specific policy can be read.
DEFAULT_POLICY = ApiKeyPolicy()


def get_api_key_policy(api_key_id: Optional[UUID]) -> ApiKeyPolicy:
    """Return the policy of *api_key_id*, or :data:`DEFAULT_POLICY`.

    Uses the ``unscoped`` manager: the key has already been authenticated by
    ``AuthenticationService.validate_api_key`` at this point, and the lookup is
    by primary key, so no application-level tenant filter is required — the
    caller always runs with the key's tenant context armed, and the database
    RLS policy still applies as a backstop (ADR-PL-03).

    Degrades to the permissive default on any lookup or shape problem. A
    malformed ``tool_groups`` value must not silently blank a caller's whole
    catalog, and a DB hiccup must not escalate into an MCP outage; the RBAC and
    ``scope`` tier gates are untouched either way.
    """
    if api_key_id is None:
        return DEFAULT_POLICY

    try:
        from auth_tenancy.models import ApiKey

        row = ApiKey.unscoped.filter(id=api_key_id).values("scope", "tool_groups").first()
    except Exception:  # noqa: BLE001 — a policy read must never break a call
        logger.exception("Failed to load ApiKey policy for %s", api_key_id)
        return DEFAULT_POLICY

    if row is None:
        return DEFAULT_POLICY

    raw_groups = row.get("tool_groups")
    if isinstance(raw_groups, list):
        groups = tuple(str(g) for g in raw_groups if isinstance(g, str) and g)
    else:
        groups = ()

    return ApiKeyPolicy(scope=str(row.get("scope") or "write"), tool_groups=groups)


__all__ = ["DEFAULT_POLICY", "ApiKeyPolicy", "get_api_key_policy"]
