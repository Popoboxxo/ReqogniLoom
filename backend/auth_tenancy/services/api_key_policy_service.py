"""Layer-2 read seam for the MCP API-key policy (ADR-01).

``mcp_server`` must not touch the ORM itself, so the one policy read lives here
and the MCP module only shapes the result. The caller has already authenticated
the key, the lookup is by primary key and the database RLS policy still applies
as a backstop (ADR-PL-03), which is why the ``unscoped`` manager is correct.
"""

from __future__ import annotations

from typing import Any, Optional
from uuid import UUID


def read_api_key_policy_row(api_key_id: UUID) -> Optional[dict[str, Any]]:
    """Return ``{"scope", "tool_groups"}`` for *api_key_id*, or ``None``."""
    from auth_tenancy.models import ApiKey

    return (
        ApiKey.unscoped.filter(id=api_key_id)
        .values("scope", "tool_groups")
        .first()
    )


__all__ = ["read_api_key_policy_row"]
