"""Optional, externally-connectable memory backend (``MEMORY_BACKEND=honcho``).

Delegates memory storage to an external `Honcho <https://honcho.dev>`_
instance. Requires ``HONCHO_BASE_URL`` (and usually ``HONCHO_API_KEY``), or
the matching ``SystemMemorySettings`` override rows (Memory Admin Phase 3).

SECURITY CONSTRAINT (verified by test_honcho_backend.py -- do not weaken):
Honcho's `peer` primitive has no ReqogniLoom tenant boundary of its own.
Every peer/workspace ID this backend sends to Honcho MUST be prefixed with the
ReqogniLoom tenant_id, or a user_id that happens to collide across two
different ReqogniLoom tenants (e.g. two different companies both importing a
CSV of user IDs starting from 1) would silently share one memory profile on
the external service -- a real cross-tenant data leak. All four data methods
route their ids through :meth:`_peer_id` / :meth:`_workspace_id` /
:meth:`_honcho_workspace_id`; none of them ever passes a raw ReqogniLoom id.

Verified SDK surface (``honcho-ai==2.3.0``, the PyPI distribution of
``plastic-labs/honcho``; NOT the unrelated legacy ``honcho`` Procfile
process-manager package, which is a completely different project):

* ``Honcho(api_key=..., base_url=..., workspace_id=...)`` -- the workspace is
  bound at *client* construction, so this backend keeps one client per tenant.
* ``client.peer(id)`` -- get-or-create. Note this ALWAYS issues
  ``POST /v3/workspaces/{ws}/peers`` (verified by running the real client;
  the published docs claim peer handles are lazy, which is not true of this
  release), so it must never be called with a throwaway id.
* ``peer.conclusions`` -> ``ConclusionScope`` (observer == observed == peer),
  i.e. the peer's self-conclusions, with ``.create()`` / ``.query()`` /
  ``.list()`` / ``.delete()``. "Conclusions" are Honcho's name for the derived
  facts this app calls memory entries.

Object mapping
--------------
Honcho's hierarchy is workspace -> peers -> conclusions, so both ReqogniLoom
memory scopes are modelled as *peers* inside one Honcho workspace per tenant:

===================  ===========================================
ReqogniLoom          Honcho
===================  ===========================================
tenant               workspace ``reqogniloom_<tenant_id>``
scope="user"         peer ``<tenant_id>_<user_id>``
scope="workspace"    peer ``<tenant_id>_<workspace_id>``
memory entry         conclusion (self-conclusion of that peer)
===================  ===========================================

NOTE: the separator between the namespace prefix and the ReqogniLoom id is
``_``, not ``:``. Honcho v3 validates every workspace/peer id against
``^[a-zA-Z0-9_-]+$`` and rejects anything else with HTTP 422 -- a colon would
make every single call to this backend fail (see ``test_honcho_backend.py``'s
``TestHonchoIdCharset`` for the regression guard).

Mapping the tenant (not the ReqogniLoom workspace) onto the Honcho workspace
is what makes :meth:`forget` implementable at all: the ``MemoryBackend``
contract passes only ``(tenant_id, entry_id)`` to ``forget()``, and Honcho's
delete route is ``DELETE /v3/workspaces/{workspace_id}/conclusions/{id}`` --
workspace + id, no scope. Had a Honcho workspace been minted per ReqogniLoom
workspace, ``forget()`` could not know which one to address. It also means
tenant isolation on delete is structural: the tenant id is in the URL path.

Known capability gaps vs. PgvectorMemoryBackend (see the individual methods)
---------------------------------------------------------------------------
* ``source_event_id`` is dropped -- Honcho's conclusion-create payload accepts
  only ``content`` and ``session_id``.
* ``query()`` returns no per-result distance -- Honcho's ``ConclusionResponse``
  carries ``id``/``content``/``observer_id``/``observed_id``/``session_id``/
  ``level``/``created_at`` and no similarity score. ``distance`` therefore
  stays ``None``; see :meth:`query` for why that is load-bearing, not cosmetic.
* Entry ids are Honcho nanoids (21 chars, ``[A-Za-z0-9_-]``), not UUIDs --
  hence ``MemoryEntryId`` rather than ``UUID`` in ``memory.backends``.

LLM PINNING IS NOT POSSIBLE FROM THIS CLIENT (researched, not assumed)
----------------------------------------------------------------------
Honcho runs its own LLM calls (deriver / dialectic / summary / dream)
*server-side*. ``honcho-ai==2.3.0`` exposes no provider, model, API-key or
base-URL parameter anywhere: neither on the ``Honcho(...)`` constructor
(``api_key``/``environment``/``base_url``/``workspace_id``/``timeout``/
``max_retries``/``default_headers``/``default_query``/``http_client``) nor on
``WorkspaceConfiguration`` (``reasoning``/``peer_card``/``summary``/``dream``,
all of which are ``ConfigDict(extra="forbid")`` pydantic models exposing only
``enabled``/``custom_instructions``/counters). ``peer.chat()`` accepts a
``reasoning_level`` ("minimal".."max") -- which *selects among* the server's
configured models, but cannot supply one.

Pinning Honcho to this project's ``opencode_go`` provider + ``mimo-v2.5``
therefore has to be configured on the Honcho *server* deployment, which lives
outside this repository. See ``.env.example`` for the concrete server-side
variables.
"""
from __future__ import annotations

import os
from typing import Any, List, Optional
from uuid import UUID

from memory.backends import MemoryBackend, MemoryEntryId, MemoryEntryRef, register_memory_backend

#: Upper bound for Honcho's paginated/top-k request parameters. The server
#: rejects oversized page sizes rather than clamping them, so an unbounded
#: caller-supplied ``limit``/``top_k`` would turn into an HTTP 422 instead of a
#: short result set. Requests above this are clamped and the response is
#: truncated to what the caller asked for.
_MAX_PAGE_SIZE = 100

#: Placeholder observer/observed pair used only to reach ``ConclusionScope.delete()``.
#:
#: Deleting a conclusion is a workspace-level operation in Honcho
#: (``DELETE /v3/workspaces/{workspace_id}/conclusions/{conclusion_id}`` --
#: the observer/observed pair is not part of the route and ``delete()`` never
#: reads it), but the SDK only exposes ``delete()`` through a peer-scoped
#: ``ConclusionScope``.
#:
#: :meth:`HonchoMemoryBackend.forget` therefore constructs a ``ConclusionScope``
#: directly instead of going through ``client.peer(...)``. That is deliberate:
#: ``client.peer()`` is a get-or-create that always POSTs to ``/peers``, so
#: routing a delete through it would create a junk peer in every tenant's
#: Honcho workspace -- one that Honcho would then start building a
#: representation for. The id is deliberately not a valid ``tenant_uuid`` pair
#: so it can never collide with a real memory peer if it ever does get sent.
_FORGET_SCOPE_PEER = "__reqogniloom_forget__"


@register_memory_backend("honcho")
class HonchoMemoryBackend(MemoryBackend):
    """Memory backend delegating storage to an external Honcho service.

    See the module docstring for the tenant-namespacing security constraint,
    the ReqogniLoom -> Honcho object mapping, and the capability gaps versus
    the default ``PgvectorMemoryBackend``.
    """

    def __init__(self) -> None:
        base_url, api_key = self._resolve_config()
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        # Test seam: when set, ``_ensure_client`` returns this instead of
        # constructing a real SDK client, so tests can swap it via
        # ``unittest.mock.patch.object(backend, "_client", ...)`` without the
        # ``honcho`` import ever running.
        self._client: Any = None
        # One SDK client per tenant -- the Honcho workspace is bound at client
        # construction time (see module docstring), so a single client cannot
        # serve two tenants. Keyed by tenant id.
        self._clients: dict[str, Any] = {}

    @staticmethod
    def _resolve_config() -> tuple[str, Optional[str]]:
        """SystemMemorySettings override (Phase 3) wins over env vars if set."""
        try:
            from memory.models import SystemMemorySettings

            row = SystemMemorySettings.objects.first()
            if row is not None:
                base_url = row.honcho_base_url or os.environ.get("HONCHO_BASE_URL", "")
                api_key = row.honcho_api_key or os.environ.get("HONCHO_API_KEY")
                return base_url, api_key
        except Exception:  # noqa: BLE001 - settings are best-effort; env is the fallback.
            pass
        return os.environ.get("HONCHO_BASE_URL", ""), os.environ.get("HONCHO_API_KEY")

    def _ensure_client(self, tenant_id: UUID) -> Any:
        """Return an SDK client bound to *tenant_id*'s Honcho workspace."""
        if self._client is not None:
            return self._client
        key = str(tenant_id)
        client = self._clients.get(key)
        if client is None:
            from honcho import Honcho  # honcho-ai; imported lazily, see module docstring

            client = Honcho(
                api_key=self._api_key,
                base_url=self._base_url,
                workspace_id=self._honcho_workspace_id(tenant_id),
            )
            self._clients[key] = client
        return client

    def _peer_id(self, tenant_id: UUID, user_id: UUID) -> str:
        """Namespace a ReqogniLoom user_id by tenant_id for Honcho's flat peer space.

        Uses ``_`` (not ``:``) as the separator: Honcho v3 validates every id
        against ``^[a-zA-Z0-9_-]+$`` and returns HTTP 422 for anything else,
        which previously turned every memory call into an unhandled 500
        (see module docstring note and ``TestHonchoIdCharset``).
        """
        return f"{tenant_id}_{user_id}"

    def _workspace_id(self, tenant_id: UUID, workspace_id: UUID) -> str:
        """Namespace a ReqogniLoom workspace_id by tenant_id for Honcho's flat peer space.

        A ReqogniLoom workspace is represented as a Honcho *peer* (see the
        module docstring's mapping table): conclusions in Honcho always belong
        to a peer, so workspace-scoped memory needs a peer to hang off. Uses
        ``_`` (not ``:``) as the separator -- see :meth:`_peer_id`.
        """
        return f"{tenant_id}_{workspace_id}"

    @staticmethod
    def _honcho_workspace_id(tenant_id: UUID) -> str:
        """Honcho workspace name for a ReqogniLoom tenant.

        The ``reqogniloom_`` prefix keeps this app's workspaces recognisable
        (and collision-free) on a Honcho instance shared with other products.
        Uses ``_`` (not ``:``) as the separator -- see :meth:`_peer_id`.
        """
        return f"reqogniloom_{tenant_id}"

    def _scope_peer_id(self, tenant_id: UUID, scope: str, scope_id: UUID) -> str:
        """Resolve ``(scope, scope_id)`` to the tenant-namespaced Honcho peer id.

        Raises:
            ValueError: if *scope* is not ``"user"`` or ``"workspace"`` --
                mirrors ``memory.backends._model_for_scope`` so an unknown
                scope fails identically on either backend instead of silently
                writing to the wrong peer.
        """
        if scope == "user":
            return self._peer_id(tenant_id, scope_id)
        if scope == "workspace":
            return self._workspace_id(tenant_id, scope_id)
        raise ValueError(f"unknown memory scope: {scope!r}")

    def _conclusions(self, tenant_id: UUID, scope: str, scope_id: UUID) -> Any:
        """Return the ``ConclusionScope`` holding this scope's memory entries."""
        client = self._ensure_client(tenant_id)
        return client.peer(self._scope_peer_id(tenant_id, scope, scope_id)).conclusions

    def upsert(
        self,
        tenant_id: UUID,
        scope: str,
        scope_id: UUID,
        content: str,
        source_event_id: Optional[UUID] = None,
    ) -> MemoryEntryRef:
        """Store *content* as a conclusion on this scope's peer.

        ``source_event_id`` is accepted for interface compatibility but
        dropped: Honcho's conclusion-create payload only carries ``content``
        and ``session_id``, and there is no user-writable metadata field on a
        conclusion to smuggle it through. Provenance for entries written via
        this backend therefore lives only in ReqogniLoom's audit log.
        """
        created = self._conclusions(tenant_id, scope, scope_id).create([{"content": content}])
        if not created:
            raise RuntimeError("Honcho accepted the conclusion but returned no object")
        conclusion = created[0]
        return MemoryEntryRef(entry_id=conclusion.id, content=conclusion.content)

    def query(
        self, tenant_id: UUID, scope: str, scope_id: UUID, query_text: str, top_k: int = 5
    ) -> List[MemoryEntryRef]:
        """Semantic search over this scope's conclusions.

        ``distance`` is intentionally left ``None``: Honcho's query response
        carries no similarity score, so there is nothing truthful to put
        there. That is not merely cosmetic -- ``memory.tasks``'s consolidation
        treats ``distance is not None`` as the trigger for its
        "supersede the contradicted entry" branch, which writes straight to
        the pgvector tables via the Django ORM. Reporting a fabricated
        distance here would send Honcho nanoids into a ``UUIDField`` lookup.
        """
        results = self._conclusions(tenant_id, scope, scope_id).query(
            query_text, top_k=max(1, min(top_k, _MAX_PAGE_SIZE))
        )
        return [MemoryEntryRef(entry_id=c.id, content=c.content) for c in results[:top_k]]

    def list_recent(
        self, tenant_id: UUID, scope: str, scope_id: UUID, limit: int = 20
    ) -> List[MemoryEntryRef]:
        """Return this scope's most recent conclusions, newest first.

        Honcho's list endpoint is documented as "ordered by recency unless
        ``reverse`` is true", so the default ordering already matches this
        method's contract and ``reverse`` must NOT be passed.

        Only the first page is read (``page.items``). Iterating a ``SyncPage``
        would transparently fetch *every* subsequent page -- the SDK warns
        about exactly this -- turning a bounded ``limit`` into a full dump of
        the peer's memory.
        """
        page = self._conclusions(tenant_id, scope, scope_id).list(
            size=max(1, min(limit, _MAX_PAGE_SIZE))
        )
        return [MemoryEntryRef(entry_id=c.id, content=c.content) for c in page.items[:limit]]

    def forget(self, tenant_id: UUID, entry_id: MemoryEntryId) -> None:
        """Permanently delete a conclusion from *tenant_id*'s Honcho workspace.

        Cross-tenant deletion is structurally impossible: the client is bound
        to ``reqogniloom_<tenant_id>`` and that workspace is part of the
        delete route, so an ``entry_id`` belonging to another tenant resolves
        to nothing.

        See :data:`_FORGET_SCOPE_PEER` for why the ``ConclusionScope`` is
        built directly rather than via ``client.peer(...)``.
        """
        from honcho.conclusions import ConclusionScope  # honcho-ai, lazy (see _ensure_client)

        client = self._ensure_client(tenant_id)
        scope = ConclusionScope(
            client,
            self._honcho_workspace_id(tenant_id),
            _FORGET_SCOPE_PEER,
            _FORGET_SCOPE_PEER,
        )
        scope.delete(str(entry_id))

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
