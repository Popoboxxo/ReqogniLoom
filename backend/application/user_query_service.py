"""Read-only user queries for the MCP ``user.*`` tool group (ADR-01 façade).

R2S-003 boundary fix: ``mcp_server/tools/users.py`` used to reach into
``persistence.models.User``/``auth_tenancy.models.UserRole`` directly for six
read queries.  This module owns those queries in Layer 2 (application); the
MCP tool layer only consumes the DTOs below and never imports a persistence
model.

Behaviour contract
------------------
Every query here is a verbatim relocation of the former inline tool query —
same filters, same ``order_by("username")``, same slice, same best-effort
``except Exception`` semantics.  The MCP tool keeps its existing error
mapping (``INTERNAL_ERROR`` / ``NOT_FOUND``); this module deliberately does
not know about ``ToolResult``.

Rollout flag
------------
:func:`service_backed_queries_enabled` gates the call sites (default on).
With the flag off the tools call the module-level ``legacy_*`` functions
directly; with it on they call the :class:`UserQueryService` façade.  Both
paths run the exact same queries, so ``ToolResult`` payloads are
byte-identical (asserted by the MCP tool-group tests).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from django.conf import settings

from auth_tenancy.models import UserRole
from persistence.models import User

#: Re-exported so the tool layer can keep mapping ``User.DoesNotExist`` to
#: ``NOT_FOUND`` without importing a persistence model itself (OC 2: the old
#: exception identity is preserved for one release).
UserDoesNotExist = User.DoesNotExist


def service_backed_queries_enabled() -> bool:
    """Return whether MCP read queries route through the application façade.

    Mirrors the ``IMPORT_CONTRACT_V2`` rollout pattern in ``rest_api``: the
    ``getattr`` fallback keeps the flag readable without a settings entry,
    while the tested default is **on**.  Operators may pin it to ``False``
    to exercise the legacy (relocated, still in Layer 2) query path.
    """
    return bool(getattr(settings, "MCP_SERVICE_BACKED_QUERIES", True))


@dataclass(frozen=True)
class UserData:
    """DTO carrying exactly the ``User`` fields the MCP serialiser reads.

    Attribute names intentionally match the ORM model so the tool's
    ``_user_to_dict`` helper works unchanged — the emitted JSON is therefore
    byte-for-byte identical to the pre-migration response.
    """

    id: UUID
    username: str
    email: str
    is_active: bool
    is_staff: bool
    is_superuser: bool
    tenant_id: UUID | None
    created_at: datetime | None


def _to_user_data(user: User | Any) -> UserData:
    """Build a :class:`UserData` DTO from an ORM ``User`` row."""
    return UserData(
        id=user.id,
        username=user.username,
        email=user.email,
        is_active=user.is_active,
        is_staff=user.is_staff,
        is_superuser=user.is_superuser,
        tenant_id=user.tenant_id,
        created_at=getattr(user, "created_at", None),
    )


# ---------------------------------------------------------------------------
# Canonical queries — verbatim relocations of the former tool-layer queries
# ---------------------------------------------------------------------------


def legacy_caller_is_superuser(user_id: UUID) -> bool:
    """Return whether *user_id* is a Django superuser (probe fails closed).

    Relocated from ``UsersToolGroup._caller_is_superuser``.  Any database
    failure is swallowed and answered ``False`` so a caller cannot gain
    elevated rights through an outage.
    """
    try:
        user = User.objects.filter(id=user_id).first()
    except Exception:  # noqa: BLE001 — probe fails closed (False)
        return False
    return bool(user and user.is_superuser)


def legacy_member_has_active_role(user_id: UUID, workspace_id: UUID) -> bool:
    """Return whether *user_id* holds an active role in *workspace_id*.

    Relocated from ``_handle_user_assign_role``'s ``target_is_member`` check.
    An active (non-suspended) role assignment is the codebase's definition
    of workspace membership.
    """
    return UserRole.objects.filter(
        user_id=user_id,
        workspace_id=workspace_id,
        suspended_at__isnull=True,
    ).exists()


def legacy_get_user(user_id: UUID) -> UserData | None:
    """Load one user by id as a DTO; ``None`` when the row is absent.

    Relocated from the audit/read-back probes in ``user.deactivate`` and
    ``user.activate``.  Best-effort: the caller decides whether a missing
    row is an error (the former ``except Exception`` audit probe semantics
    are preserved by the tool).
    """
    user = User.objects.filter(id=user_id).first()
    return _to_user_data(user) if user is not None else None


def legacy_list_user_rows(
    *, tenant_id: UUID, is_active: bool | None, limit: int
) -> list[UserData]:
    """Load one ordered, tenant-scoped page of users as DTOs.

    Relocated from ``UsersToolGroup._fetch_user_rows``.  Ordering is by
    ``username`` and the page is cut with ``[:limit]``; both are part of the
    wire contract and must not drift.  Database errors propagate to the
    tool, which keeps the ``INTERNAL_ERROR`` mapping and log message.
    """
    queryset = User.objects.filter(tenant_id=tenant_id)
    if is_active is not None:
        queryset = queryset.filter(is_active=is_active)
    return [_to_user_data(row) for row in queryset.order_by("username")[:limit]]


class UserQueryService:
    """ADR-01 façade over the relocated read queries.

    The methods delegate to the ``legacy_*`` functions so the service-backed
    path is byte-identical to the legacy path by construction.  Keeping both
    entry points in Layer 2 is what lets the MCP tool drop its persistence
    imports while retaining a reversible rollout flag.
    """

    def caller_is_superuser(self, user_id: UUID) -> bool:
        """Return whether *user_id* is a Django superuser."""
        return legacy_caller_is_superuser(user_id)

    def member_has_active_role(self, user_id: UUID, workspace_id: UUID) -> bool:
        """Return whether *user_id* holds an active role in *workspace_id*."""
        return legacy_member_has_active_role(user_id, workspace_id)

    def get_user(self, user_id: UUID) -> UserData | None:
        """Return one user DTO by id, or ``None`` when absent."""
        return legacy_get_user(user_id)

    def list_user_rows(
        self, *, tenant_id: UUID, is_active: bool | None, limit: int
    ) -> list[UserData]:
        """Return one ordered, tenant-scoped page of user DTOs."""
        return legacy_list_user_rows(
            tenant_id=tenant_id, is_active=is_active, limit=limit
        )
