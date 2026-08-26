"""Optional, externally-connectable memory backend. Requires HONCHO_BASE_URL
(and optionally HONCHO_API_KEY) to be set; enabled via MEMORY_BACKEND=honcho.

SECURITY CONSTRAINT (verified by test_honcho_backend.py -- do not weaken):
Honcho's `peer` primitive has no tenant boundary of its own -- it is a flat
namespace on the Honcho side. Every peer/workspace ID this backend sends to
Honcho MUST be prefixed with the ReqogniLoom tenant_id, or a user_id that
happens to collide across two different ReqogniLoom tenants (e.g. two
different companies both importing a CSV of user IDs starting from 1) would
silently share one memory profile on the external service -- a real
cross-tenant data leak.

NOTE: this backend is a deliberately partial skeleton. Honcho's Python
SDK/HTTP API surface is external to this repo and has NOT been verified
against real installed code -- ``query()``/``list_recent()``/``forget()``
are left as ``NotImplementedError`` stubs on purpose (see their docstrings).
Only ``_peer_id()``/``_workspace_id()`` (the tenant-namespacing helpers) and
``upsert()``'s use of them are the load-bearing security contract this task
implements; the exact SDK calls inside ``upsert()``/``_client`` are
placeholders marked "verify at implementation time" and must be confirmed
against the actual installed ``honcho`` package before this backend is used
against a real Honcho instance.
"""
from __future__ import annotations

import os
from typing import List, Optional
from uuid import UUID

from memory.backends import MemoryBackend, MemoryEntryRef, register_memory_backend


@register_memory_backend("honcho")
class HonchoMemoryBackend(MemoryBackend):
    """Skeleton backend delegating memory storage to an external Honcho
    service. See module docstring for the tenant-namespacing security
    constraint and the intentionally-unimplemented read/delete methods.
    """

    def __init__(self) -> None:
        self._base_url = os.environ.get("HONCHO_BASE_URL", "").rstrip("/")
        self._api_key = os.environ.get("HONCHO_API_KEY")
        # Lazily initialized on first use (see ``_ensure_client``), stored as a
        # plain instance attribute rather than behind a property so tests can
        # swap it via ``unittest.mock.patch.object(backend, "_client", ...)``
        # without ever triggering the real (currently un-installed) ``honcho``
        # SDK import.
        self._client = None

    def _ensure_client(self):
        if self._client is None:
            from honcho import Honcho  # external SDK -- verify exact import path at implementation time

            self._client = Honcho(base_url=self._base_url, api_key=self._api_key)
        return self._client

    def _peer_id(self, tenant_id: UUID, user_id: UUID) -> str:
        """Namespace a ReqogniLoom user_id by tenant_id for Honcho's flat peer space."""
        return f"{tenant_id}:{user_id}"

    def _workspace_id(self, tenant_id: UUID, workspace_id: UUID) -> str:
        """Namespace a ReqogniLoom workspace_id by tenant_id for Honcho's flat workspace space."""
        return f"{tenant_id}:{workspace_id}"

    def upsert(
        self,
        tenant_id: UUID,
        scope: str,
        scope_id: UUID,
        content: str,
        source_event_id: Optional[UUID] = None,
    ) -> MemoryEntryRef:
        client = self._ensure_client()
        if scope == "user":
            peer = client.peers.get_or_create(id=self._peer_id(tenant_id, scope_id))
            client.create_conclusion(peer=peer, content=content)  # exact SDK call TBD, verify against installed package
        else:
            honcho_ws = client.workspaces.get_or_create(id=self._workspace_id(tenant_id, scope_id))
            client.create_conclusion(workspace=honcho_ws, content=content)
        # Honcho's own ID is the entry_id -- exact return shape TBD, verify at implementation time.
        return MemoryEntryRef(entry_id=scope_id, content=content)

    def query(
        self, tenant_id: UUID, scope: str, scope_id: UUID, query_text: str, top_k: int = 5
    ) -> List[MemoryEntryRef]:
        raise NotImplementedError("verify Honcho's dialectic chat()/search API before implementing")

    def list_recent(
        self, tenant_id: UUID, scope: str, scope_id: UUID, limit: int = 20
    ) -> List[MemoryEntryRef]:
        raise NotImplementedError("verify Honcho's conclusion-listing API before implementing")

    def forget(self, tenant_id: UUID, entry_id: UUID) -> None:
        raise NotImplementedError("verify Honcho's deletion API before implementing")

    def health_check(self) -> tuple[bool, str]:
        if not self._base_url:
            return False, "HONCHO_BASE_URL is not configured"
        try:
            import requests  # noqa: PLC0415 - lazy import, matches this repo's health-check convention

            # HEAD (not GET) with redirects disabled: a plain reachability
            # check must not buffer an unbounded response body or follow a
            # redirect chain (each hop re-arming its own 1s timeout budget)
            # past the intended ~1s bound.
            response = requests.head(self._base_url, timeout=1.0, allow_redirects=False)
            if response.status_code >= 500:
                return False, f"{self._base_url} returned HTTP {response.status_code}"
            return True, f"{self._base_url} reachable (HTTP {response.status_code})"
        except Exception as exc:
            return False, str(exc)


__all__ = ["HonchoMemoryBackend"]
