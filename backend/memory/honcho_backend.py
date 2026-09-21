"""Optional, externally-connectable memory backend (``MEMORY_BACKEND=honcho``).

Delegates memory CONTENT to an external `Honcho <https://honcho.dev>`_
instance. Requires ``HONCHO_BASE_URL`` (and usually ``HONCHO_API_KEY``), or
the matching ``SystemMemorySettings`` override rows (Memory Admin Phase 3).

``mem_memory_entry`` is the LOCAL CANONICAL MIRROR (RFC #1002 PR A)
---------------------------------------------------------------
Since RFC #1002, Honcho is no longer the only store: every
:meth:`HonchoMemoryBackend.write` also creates a ``mem_memory_entry`` row
whose ``backend_ref`` carries the Honcho conclusion id. ReqogniLoom's own UUID
stays the primary key (``entry_id``); the nanoid never becomes our id. The
mirror is what makes ``list_entries``/``count``/``delete_entry``/
``delete_scope`` implementable over the shared ``MemoryBackend`` contract, and
it is what lets ``query`` map a Honcho result back to a local entry.

SECURITY CONSTRAINT (verified by test_honcho_backend.py -- do not weaken):
Honcho's `peer` primitive has no ReqogniLoom tenant boundary of its own.
Every peer/workspace ID this backend sends to Honcho MUST be prefixed with the
ReqogniLoom tenant_id, or a user_id that happens to collide across two
different ReqogniLoom tenants (e.g. two different companies both importing a
CSV of user IDs starting from 1) would silently share one memory profile on
the external service -- a real cross-tenant data leak. All data methods route
their ids through :meth:`_peer_id` / :meth:`_workspace_id` /
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
Honcho's hierarchy is workspace -> peers -> conclusions, so every ReqogniLoom
memory scope is modelled as a *peer* inside one Honcho workspace per tenant:

===================  ===========================================
ReqogniLoom          Honcho
===================  ===========================================
tenant               workspace ``reqogniloom_<tenant_id>``
scope="user"         peer ``<tenant_id>_<user_id>``
scope="workspace"    peer ``<tenant_id>_<workspace_id>``
scope="artifact"     peer ``<tenant_id>_a_<artifact_id>``
memory entry         conclusion (self-conclusion of that peer)
===================  ===========================================

Peer-prefix compatibility choice (RFC #1002): ``user``/``workspace`` keep the
LEGACY UNPREFIXED shape (``<tenant>_<id>``). Introducing ``_u_``/``_w_`` now
would orphan every already-written external peer's conclusions, and there is
no migration for a foreign service -- so the prefix is used only for the NEW
``artifact`` scope (``_a_``), which has no legacy peers to preserve. Reading
tolerates the unprefixed shape because that is exactly what is still written.

NOTE: the separator between the namespace prefix and the ReqogniLoom id is
``_``, not ``:``. Honcho v3 validates every workspace/peer id against
``^[a-zA-Z0-9_-]+$`` and rejects anything else with HTTP 422 -- a colon would
make every single call to this backend fail (see ``test_honcho_backend.py``'s
``TestHonchoIdCharset`` for the regression guard).

Mapping the tenant (not the ReqogniLoom workspace) onto the Honcho workspace
is what makes deletion implementable at all: Honcho's delete route is
``DELETE /v3/workspaces/{workspace_id}/conclusions/{id}`` -- workspace + id,
no scope. Had a Honcho workspace been minted per ReqogniLoom workspace,
``forget()`` could not know which one to address. It also means tenant
isolation on delete is structural: the tenant id is in the URL path.

Distance (F5 fix, RFC #1002)
---------------------------
Honcho's ``ConclusionResponse`` carries no similarity score. ``query()``
therefore computes one IN PROCESS: it embeds ``query_text`` and the matched
entry's content with the locally configured embedding provider and returns
``1 - cosine_similarity`` (the same convention as pgvector's cosine distance).
When no embedding can be produced, ``distance`` stays ``None`` rather than
being fabricated -- ``memory.tasks``'s consolidation treats ``distance is not
None`` as the trigger for its supersede branch, so a fabricated score would
act on a lie.

Deletion reaches the external service (F4 / DSGVO fix, RFC #1002)
-----------------------------------------------------------------
:meth:`delete_entry` / :meth:`delete_scope` delete BOTH the local mirror rows
AND the corresponding Honcho conclusions (via ``backend_ref``). Deleting only
locally would leave the user's content on the external service -- the exact
DSGVO gap this PR closes. :meth:`delete_entry` additionally accepts a raw
Honcho nanoid (resolved via ``backend_ref``) as well as our UUID.

EMBEDDING CONFIGURATION (GH #911)
---------------------------------
Honcho embeds memory entries through an OpenAI-compatible endpoint configured
**on the Honcho server**, not through this client. That endpoint is supplied
here as two env vars so :meth:`HonchoMemoryBackend.health_check` can probe it:

* ``HONCHO_EMBEDDING_BASE_URL`` -- OpenAI-compatible base URL *including* the
  ``/v1`` suffix (e.g. ``http://host.docker.internal:11434/v1``). This is the
  value ``deploy/docker-compose.yml`` wires into the Honcho service.
* ``HONCHO_EMBEDDING_MODEL`` -- embedding model id (e.g. ``nomic-embed-text``).

``health_check()`` reports the backend down when either is unset, rather than
the old behaviour of reporting ``ok`` from a HEAD reachability check alone --
which is what let a deploy with a placeholder embedding host pass ``/health``
while being unable to embed a single memory entry.

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
from typing import Any, List, Optional, Tuple
from uuid import UUID

from llm_adapter.embedding_service import generate_embedding
from memory.backends import (
    MemoryBackend,
    MemoryEntryId,
    MemoryEntryRef,
    MemoryHealth,
    _cosine_distance,
    _maybe_uuid,
    _ref_from_entry,
    _scope_filter,
    _tenant_context,
    register_memory_backend,
)
from memory.models import MemoryEntry

#: Upper bound for Honcho's paginated/top-k request parameters. The server
#: rejects oversized page sizes rather than clamping them, so an unbounded
#: caller-supplied ``limit``/``top_k`` would turn into an HTTP 422 instead of a
#: short result set. Requests above this are clamped and the response is
#: truncated to what the caller asked for.
_MAX_PAGE_SIZE = 100

#: Peer-id prefix for the ``artifact`` scope (RFC #1002). Deliberately NOT
#: applied to ``user``/``workspace``: those keep the legacy unprefixed
#: ``<tenant>_<id>`` shape so already-written external peers stay addressable
#: (there is no migration for a foreign service). The artifact scope is new,
#: so it gets the explicit prefix from day one.
_ARTIFACT_SCOPE_PREFIX = "a"

#: Scopes whose peer id keeps the legacy unprefixed ``<tenant>_<id>`` shape.
_LEGACY_UNPREFIXED_SCOPES = ("user", "workspace")

#: Fallback timeout, in seconds, for each network call
#: :meth:`HonchoMemoryBackend.health_check` makes (the reachability HEAD and the
#: embedding probe POST). Overridable through ``HEALTH_PROBE_TIMEOUT`` (issue
#: #990): a hard 1s is below any realistic embedding latency, so a healthy
#: Ollama/Honcho answered too late and the system-health dialog reported it as
#: "AUSGEFALLEN". Deliberately resolved from the environment here rather than
#: importing ``admin_ops.health_rest``: the backend must stay importable without
#: the admin_ops package, and this is a single bounded probe, never a retry loop.
_DEFAULT_HEALTH_PROBE_TIMEOUT_S = 10.0


def _health_probe_timeout_s() -> float:
    """Timeout for :meth:`HonchoMemoryBackend.health_check` network calls.

    Reads ``HEALTH_PROBE_TIMEOUT`` (seconds, same env var as
    ``settings.HEALTH_PROBE_TIMEOUT_SECONDS``) and falls back to
    :data:`_DEFAULT_HEALTH_PROBE_TIMEOUT_S`. A non-positive or unparsable value
    falls back too, so a typo can never produce an instant, always-red probe.
    """
    raw = os.environ.get("HEALTH_PROBE_TIMEOUT", "")
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return _DEFAULT_HEALTH_PROBE_TIMEOUT_S
    return value if value > 0 else _DEFAULT_HEALTH_PROBE_TIMEOUT_S


def _safe_generate_embedding(text: str) -> Optional[List[float]]:
    """Best-effort local embedding; ``None`` on any provider failure.

    Used for the local mirror row and for the in-process query distance. The
    external Honcho write must never fail because a LOCAL embedding provider is
    unavailable, so every error degrades to ``None`` (distance then stays
    ``None`` -- see the module docstring's F5 paragraph).
    """
    try:
        return generate_embedding(text)
    except Exception:  # noqa: BLE001 - best-effort, see docstring
        return None


#: Placeholder observer/observed pair used only to reach ``ConclusionScope.delete()``.
#:
#: Deleting a conclusion is a workspace-level operation in Honcho
#: (``DELETE /v3/workspaces/{workspace_id}/conclusions/{conclusion_id}`` --
#: the observer/observed pair is not part of the route and ``delete()`` never
#: reads it), but the SDK only exposes ``delete()`` through a peer-scoped
#: ``ConclusionScope``.
#:
#: :meth:`HonchoMemoryBackend._delete_conclusion` therefore constructs a
#: ``ConclusionScope`` directly instead of going through ``client.peer(...)``.
#: That is deliberate: ``client.peer()`` is a get-or-create that always POSTs
#: to ``/peers``, so routing a delete through it would create a junk peer in
#: every tenant's Honcho workspace -- one that Honcho would then start building
#: a representation for. The id is deliberately not a valid ``tenant_uuid`` pair
#: so it can never collide with a real memory peer if it ever does get sent.
_FORGET_SCOPE_PEER = "__reqogniloom_forget__"


@register_memory_backend("honcho")
class HonchoMemoryBackend(MemoryBackend):
    """Memory backend delegating storage to an external Honcho service.

    See the module docstring for the tenant-namespacing security constraint,
    the ReqogniLoom -> Honcho object mapping, the local-mirror contract, and
    the capability gaps versus the default ``PgvectorMemoryBackend``.
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

    def _artifact_peer_id(self, tenant_id: UUID, artifact_id: UUID) -> str:
        """Namespace an artifact_id by tenant_id, with the new ``_a_`` prefix.

        Unlike user/workspace (which keep the legacy unprefixed shape -- see
        the module docstring's compatibility note), the artifact scope is new
        and gets its own prefix so its peers can never collide with a
        user/workspace peer whose id happens to equal an artifact id.
        """
        return f"{tenant_id}_{_ARTIFACT_SCOPE_PREFIX}_{artifact_id}"

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
            ValueError: if *scope* is not ``"user"``, ``"workspace"`` or
                ``"artifact"`` -- mirrors ``memory.backends._scope_filter`` so
                an unknown scope fails identically on either backend instead
                of silently writing to the wrong peer.
        """
        if scope == "user":
            return self._peer_id(tenant_id, scope_id)
        if scope == "workspace":
            return self._workspace_id(tenant_id, scope_id)
        if scope == "artifact":
            return self._artifact_peer_id(tenant_id, scope_id)
        raise ValueError(f"unknown memory scope: {scope!r}")

    def _conclusions(self, tenant_id: UUID, scope: str, scope_id: UUID) -> Any:
        """Return the ``ConclusionScope`` holding this scope's memory entries."""
        client = self._ensure_client(tenant_id)
        return client.peer(self._scope_peer_id(tenant_id, scope, scope_id)).conclusions

    def _delete_conclusion(self, tenant_id: UUID, conclusion_id: str) -> None:
        """Delete one conclusion from *tenant_id*'s Honcho workspace.

        Cross-tenant deletion is structurally impossible: the client is bound
        to ``reqogniloom_<tenant_id>`` and that workspace is part of the delete
        route, so an id belonging to another tenant resolves to nothing.

        See :data:`_FORGET_SCOPE_PEER` for why the ``ConclusionScope`` is built
        directly rather than via ``client.peer(...)``.
        """
        from honcho.conclusions import ConclusionScope  # honcho-ai, lazy (see _ensure_client)

        client = self._ensure_client(tenant_id)
        scope = ConclusionScope(
            client,
            self._honcho_workspace_id(tenant_id),
            _FORGET_SCOPE_PEER,
            _FORGET_SCOPE_PEER,
        )
        scope.delete(str(conclusion_id))

    # -- canonical-store API (RFC #1002) --------------------------------

    def write(
        self,
        tenant_id: UUID,
        scope: str,
        scope_id: UUID,
        content: str,
        *,
        contributor_user_id: Optional[UUID] = None,
        source_event_id: Optional[UUID] = None,
        source_session_id: Optional[UUID] = None,
        language: str = "",
        confidence: float = 1.0,
        entity_type: str = "",
        backend_ref: Optional[str] = None,
    ) -> MemoryEntryRef:
        """Store *content* as a conclusion and mirror it into ``mem_memory_entry``.

        The Honcho conclusion is written first (it is the external source of
        truth for content); its id becomes the mirror row's ``backend_ref``.
        The returned ref carries OUR UUID as ``entry_id``. The local embedding
        is best-effort -- a missing embedding provider leaves the column NULL
        and the row is still written.

        ``source_event_id`` IS now preserved (on the local mirror), which the
        pre-#1002 implementation dropped: Honcho's create payload still only
        accepts ``content``/``session_id``, but provenance now has a home in
        ReqogniLoom's own table.
        """
        created = self._conclusions(tenant_id, scope, scope_id).create([{"content": content}])
        if not created:
            raise RuntimeError("Honcho accepted the conclusion but returned no object")
        conclusion = created[0]
        embedding = _safe_generate_embedding(content)
        with _tenant_context(tenant_id):
            entry = MemoryEntry.objects.create(
                tenant_id=tenant_id,
                content=content,
                embedding=embedding,
                contributor_user_id=contributor_user_id,
                source_event_id=source_event_id,
                source_session_id=source_session_id,
                language=language,
                confidence=confidence,
                entity_type=entity_type,
                backend_ref=backend_ref or str(conclusion.id),
                **_scope_filter(scope, scope_id),
            )
            return _ref_from_entry(entry)

    def list_entries(
        self,
        tenant_id: UUID,
        scope: str,
        scope_id: UUID,
        *,
        limit: int = 25,
        offset: int = 0,
        q: Optional[str] = None,
    ) -> Tuple[List[MemoryEntryRef], int]:
        """Page the LOCAL mirror rows (no network call) -- newest first."""
        with _tenant_context(tenant_id):
            qs = MemoryEntry.objects.filter(
                **_scope_filter(scope, scope_id), superseded_by__isnull=True
            )
            if q:
                qs = qs.filter(content__icontains=q)
            total = qs.count()
            rows = qs.order_by("-created_at")[max(0, offset) : max(0, offset) + max(0, limit)]
            return [_ref_from_entry(e) for e in rows], total

    def count(self, tenant_id: UUID, scope: str, scope_id: UUID) -> int:
        with _tenant_context(tenant_id):
            return MemoryEntry.objects.filter(
                **_scope_filter(scope, scope_id), superseded_by__isnull=True
            ).count()

    def delete_entry(self, tenant_id: UUID, entry_id: MemoryEntryId) -> bool:
        """Delete the local mirror row AND its Honcho conclusion.

        Accepts our UUID, a UUID-shaped string, or a raw Honcho nanoid (looked
        up via ``backend_ref``, which resolves F3). Returns whether a local
        row was removed; the external delete is attempted regardless, so a
        conclusion that predates the mirror (or whose mirror row is already
        gone) still gets deleted.
        """
        backend_ref: Optional[str] = None
        removed = False
        with _tenant_context(tenant_id):
            uid = _maybe_uuid(entry_id)
            row = MemoryEntry.objects.filter(id=uid).first() if uid is not None else None
            if row is None:
                row = MemoryEntry.objects.filter(backend_ref=str(entry_id)).first()
            if row is not None:
                backend_ref = row.backend_ref
                row.delete()
                removed = True

        self._delete_conclusion(tenant_id, backend_ref or str(entry_id))
        return removed

    def delete_scope(self, tenant_id: UUID, scope: str, scope_id: UUID) -> int:
        """Delete every local mirror row for the scope and its Honcho conclusions."""
        with _tenant_context(tenant_id):
            rows = list(MemoryEntry.objects.filter(**_scope_filter(scope, scope_id)))
            backend_refs = [r.backend_ref for r in rows]
            deleted, _ = MemoryEntry.objects.filter(**_scope_filter(scope, scope_id)).delete()

        for ref in backend_refs:
            if ref:
                self._delete_conclusion(tenant_id, ref)
        return deleted

    def health(self) -> MemoryHealth:
        ok, detail = self.health_check()
        return MemoryHealth(ok=ok, backend="honcho", detail=detail, degraded=not ok)

    # -- legacy facade ---------------------------------------------------

    def upsert(
        self,
        tenant_id: UUID,
        scope: str,
        scope_id: UUID,
        content: str,
        source_event_id: Optional[UUID] = None,
    ) -> MemoryEntryRef:
        return self.write(
            tenant_id, scope, scope_id, content, source_event_id=source_event_id
        )

    def query(
        self, tenant_id: UUID, scope: str, scope_id: UUID, query_text: str, top_k: int = 5
    ) -> List[MemoryEntryRef]:
        """Semantic search over this scope's conclusions, with a real distance.

        Unlike the pre-#1002 implementation, ``distance`` is computed in
        process (F5): the query text and the matched entry are embedded
        locally and the cosine distance is returned. When no local mirror row
        exists for a conclusion, or no embedding can be produced, the ref is
        still returned with ``distance=None`` (never a fabricated score --
        ``memory.tasks`` gates its supersede branch on that being non-None).
        """
        results = self._conclusions(tenant_id, scope, scope_id).query(
            query_text, top_k=max(1, min(top_k, _MAX_PAGE_SIZE))
        )
        query_embedding = _safe_generate_embedding(query_text)
        refs: List[MemoryEntryRef] = []
        with _tenant_context(tenant_id):
            for conclusion in results[:top_k]:
                local = MemoryEntry.objects.filter(
                    backend_ref=str(conclusion.id), **_scope_filter(scope, scope_id)
                ).first()
                if local is None:
                    refs.append(
                        MemoryEntryRef(entry_id=conclusion.id, content=conclusion.content, scope=scope)
                    )
                    continue
                distance = _cosine_distance(query_embedding, local.embedding)
                refs.append(_ref_from_entry(local, distance=distance))
        return refs

    def list_recent(
        self, tenant_id: UUID, scope: str, scope_id: UUID, limit: int = 20
    ) -> List[MemoryEntryRef]:
        """Return this scope's most recent conclusions, newest first.

        Still Honcho-backed (the read path for ``memory.list``): Honcho's list
        endpoint is documented as "ordered by recency unless ``reverse`` is
        true", so the default ordering already matches this method's contract
        and ``reverse`` must NOT be passed.

        Only the first page is read (``page.items``). Iterating a ``SyncPage``
        would transparently fetch *every* subsequent page -- the SDK warns
        about exactly this -- turning a bounded ``limit`` into a full dump of
        the peer's memory.

        NOTE: entry ids here are Honcho nanoids, not our UUIDs (the conclusion
        list carries no local-row join). ``list_entries`` is the mirror-backed
        variant that returns our UUIDs.
        """
        page = self._conclusions(tenant_id, scope, scope_id).list(
            size=max(1, min(limit, _MAX_PAGE_SIZE))
        )
        return [
            MemoryEntryRef(entry_id=c.id, content=c.content, scope=scope)
            for c in page.items[:limit]
        ]

    def forget(self, tenant_id: UUID, entry_id: MemoryEntryId) -> None:
        """Permanently delete an entry (local mirror + Honcho conclusion)."""
        self.delete_entry(tenant_id, entry_id)

    def health_check(self) -> tuple[bool, str]:
        """Probe Honcho reachability *and* the embedding endpoint's liveness.

        Returns ``(ok, detail)`` and never raises. The check is deterministic
        and runs in this order:

        1. ``HONCHO_BASE_URL`` must be configured.
        2. ``HONCHO_EMBEDDING_BASE_URL`` and ``HONCHO_EMBEDDING_MODEL`` must be
           configured -- otherwise a deploy that cannot embed must not report
           ``ok`` (GH #911).
        3. A bounded HEAD on ``HONCHO_BASE_URL`` (redirects disabled, so a
           redirect chain cannot re-arm the timeout budget); HTTP >= 500 is down.
        4. Exactly one ``POST {embedding_base_url}/embeddings`` with
           ``{"model": ..., "input": "ping"}``; a non-2xx status, an empty
           ``data[0]["embedding"]`` vector, or any transport/JSON error is down.

        Note that step 4 issues a real, bounded single embedding inference
        request on every admin health poll, so OpenAI-backed configs incur a
        small token cost and self-hosted ones consume CPU/GPU.

        Both network calls share :func:`_health_probe_timeout_s`. Like the
        sibling ``admin_ops.health_rest`` probes, this uses plain ``requests``
        -- never ``resilient_call`` -- so health traffic cannot trip a shared
        circuit breaker and cause the outage it is meant to report. The
        optional ``honcho-ai`` SDK is never imported
        (see ``test_health_check_does_not_import_honcho_sdk``).
        """
        if not self._base_url:
            return False, "HONCHO_BASE_URL is not configured"

        embedding_base_url = os.environ.get("HONCHO_EMBEDDING_BASE_URL", "").strip()
        embedding_model = os.environ.get("HONCHO_EMBEDDING_MODEL", "").strip()
        if not embedding_base_url:
            return False, (
                "HONCHO_EMBEDDING_BASE_URL is not configured: the Honcho memory "
                "backend cannot embed memory entries (see issue #911)"
            )
        if not embedding_model:
            return False, "HONCHO_EMBEDDING_MODEL is not configured"

        try:
            import requests  # noqa: PLC0415 - lazy import, matches this repo's health-check convention

            # HEAD (not GET) with redirects disabled: a plain reachability
            # check must not buffer an unbounded response body or follow a
            # redirect chain (each hop re-arming its own timeout budget)
            # past the intended bound.
            response = requests.head(
                self._base_url,
                timeout=_health_probe_timeout_s(),
                allow_redirects=False,
            )
            if response.status_code >= 500:
                return False, f"{self._base_url} returned HTTP {response.status_code}"

            # A real embedding probe: the shortest possible OpenAI-compatible
            # request. This is what turns "the host answers" into "memory can
            # actually be written" -- the whole point of GH #911.
            probe = requests.post(
                f"{embedding_base_url.rstrip('/')}/embeddings",
                json={"model": embedding_model, "input": "ping"},
                timeout=_health_probe_timeout_s(),
            )
            if probe.status_code < 200 or probe.status_code >= 300:
                return False, (
                    f"embedding probe for model {embedding_model!r} returned "
                    f"HTTP {probe.status_code}"
                )
            embedding = probe.json()["data"][0]["embedding"]
            if not embedding:
                return False, (
                    f"embedding probe for model {embedding_model!r} returned an "
                    "empty vector"
                )
            return True, (
                f"{self._base_url} reachable; embedding probe for model "
                f"{embedding_model!r} succeeded"
            )
        except Exception as exc:  # noqa: BLE001 - any probe failure is a "down" detail
            return False, str(exc)


__all__ = ["HonchoMemoryBackend"]
