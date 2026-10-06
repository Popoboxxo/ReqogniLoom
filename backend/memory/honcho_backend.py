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

Verified SDK surface (``honcho-ai==2.5.1``, the PyPI distribution of
``plastic-labs/honcho``; NOT the unrelated legacy ``honcho`` Procfile
process-manager package, which is a completely different project):

* ``Honcho(api_key=..., base_url=..., workspace_id=...)`` -- the workspace is
  bound at *client* construction, so this backend keeps one client per tenant.
* ``client.peer(id)`` -- get-or-create. Note this ALWAYS issues
  ``POST /v3/workspaces/{ws}/peers`` (verified by running the real client;
  the published docs claim peer handles are lazy, which is not true of this
  release), so it must never be called with a throwaway id.
* ``peer.conclusions`` -> ``ConclusionsView`` (observer == observed == peer),
  i.e. the peer's self-conclusions, with ``.create()`` / ``.query()`` /
  ``.list()`` / ``.delete()``. "Conclusions" are Honcho's name for the derived
  facts this app calls memory entries.
* ``Conclusion.level`` -> ``Literal["explicit", "deductive", "inductive",
  "contradiction"]`` (re-verified by introspecting ``honcho-ai==2.5.1`` in the
  deployed container for AP-B5.1 / #1155): ``explicit`` conclusions are
  extracted verbatim from messages (every :meth:`write` creates one directly),
  the other three are Deriver/Dream output -- so the level field, not a
  content heuristic, is what distinguishes "stored" from "derived".
  ``ConclusionsView.list`` accepts ``filters={"level": ...}`` server-side.
* ``Honcho.queue_status(observer=..., sender=..., session=...)`` ->
  ``QueueStatusResponse`` with ``total``/``completed``/``in_progress``/
  ``pending`` ``_work_units`` counters (same verification run) -- the SDK's
  ONLY work-unit surface. It carries no per-unit error flag and no
  last-error/last-run detail, which bounds what :meth:`_queue_gap`
  can honestly claim (see it).

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

Sessions + messages: giving the Deriver something to derive from (F6)
---------------------------------------------------------------------
Before F6 this backend wrote exactly one thing per entry: a *conclusion*.
Honcho's Deriver, peer card, summary and dream are all fed by **messages**
inside a **session** -- a conclusion written directly is a terminal artefact,
not an observation the engine can learn from. The engine therefore stayed
idle: no representation, no card, nothing a ``digest()`` could return.

Since F6 every :meth:`HonchoMemoryBackend.write` ALSO appends the same content
as a real message to the scope's session, authored by the scope's own peer
(observer == observed == the memory peer, matching the conclusion's scope).
The conclusion write stays the mandatory step and its id stays
``backend_ref``; the message is *additional* input for the Deriver.

*Stable session id per scope.* One session per ``(tenant, scope, scope_id)``,
never one per write: the Deriver's whole job is to aggregate many messages into
one representation over time, so a fresh session per write would restart that
aggregation on every entry. The id is derived from the peer id
(``s_<peer id>``, see :meth:`HonchoMemoryBackend._scope_session_id`) so it is
tenant-namespaced by construction and matches Honcho's
``^[a-zA-Z0-9_-]+$`` id charset (colons would be rejected with HTTP 422 -- the
same constraint that applies to peers, guarded by ``TestHonchoIdCharset``).

FAIL-OPEN is the rule for the whole session path
------------------------------------------------
Sending the message, creating the session and enabling the engine
configuration are all *derived* concerns: they make the external engine
smarter, they are not what the caller asked to persist. Every one of them runs
best-effort inside its own ``try``/``except``, logs a warning on failure and
then continues. A Honcho release that renames a session method, a workspace
whose configuration cannot be written, a transient 5xx -- none of that may turn
a successful memory write into an error, because the conclusion (the mandatory
part) is already stored and mirrored locally. The only hard failure left in
:meth:`write` is the pre-existing "Honcho accepted the conclusion but returned
no object" guard.

``digest()`` (F6)
-----------------
:meth:`HonchoMemoryBackend.digest` reads the engine's derived artefact first
(peer representation scoped to the scope's session, falling back to the peer
card), then degrades in steps:

1. representation / card -- the engine's own summary. ``degraded=False`` when
   either answered, even if it was empty;
2. the scope's conclusion list -- the SAME bounded page the derivation probe
   already read when the engine answered cleanly with nothing to summarise,
   or ``list_recent`` when the engine read raised and no page exists;
3. the LOCAL MIRROR rows (``list_entries``, no network) -- last resort when a
   network call raised, i.e. the engine is unreachable. This path sets
   ``degraded=True``, so a caller can still show *something* while the
   envelope says the answer is unreliable.

Only a failure of step 3 as well yields an empty text. Like pgvector, an empty
but healthy scope is ``degraded=False`` (F9), and the method never raises.

Since AP-B5.1 (#1155) the digest additionally fills ``derivation_status`` /
``derived_count``, consulting the probe on EVERY clean path: a non-empty
representation or card is deriver output (``ok``); a clean-but-empty engine
answer runs :meth:`_derivation_probe` (``ok`` / ``none`` from the conclusion
levels); a demonstrable work-unit gap in ``queue_status`` yields ``failed``
and OUTRANKS any earlier output; an unreachable engine yields ``unknown``
rather than silently collapsing into ``none``.

**What ``ok`` does NOT mean, and the residual blind spot.** ``ok`` asserts
only that this scope HAS produced derived output -- never that the Deriver is
currently healthy. The dominant #1155 root cause is the Zen-Go endpoint's rate
limit (HTTP 429): the Deriver dies *server-side* and Honcho counts the
affected work units as processed. ``honcho-ai==2.5.1`` exposes no per-unit
error flag and no last-error/last-run surface (verified empirically, see the
SDK-surface list above), so such a loss leaves no accounting gap and is
**client-undetectable**: a scope with earlier output keeps reading ``ok`` and
a scope without any reads ``none`` -- neither is ``failed``. ``failed`` fires
only on the provable gap (``total > completed + in_progress + pending``).
That limit is documented for operators in ``deploy/README.md`` (§Derivation
visibility) rather than papered over with a guess.

``ask()`` (natural-language access)
-----------------------------------
:meth:`HonchoMemoryBackend.ask` is the engine's *dialectic* surface: instead of
rendering facts (``digest``) or returning matches (``query``), it answers the
caller's actual question through ``peer.chat(query, session=<scope session>)``
on the scope's tenant-namespaced peer. Scoping to the session keeps the answer
inside this scope's observations; failure degrades to
``MemoryAnswer(degraded=True)`` exactly like ``digest``, so a missing session,
an unreachable engine or an unknown scope can never raise -- and a clean
``None`` answer is a non-degraded "nothing known", not an outage (F9).

The degraded ``detail`` is classified by :func:`_degraded_detail`: an
engine/transport failure yields ``"engine_error:<ExceptionClassName>"``, a
rejected unknown scope ``"unknown_scope:<ExceptionClassName>"``. The two
prefixes keep an outage distinguishable from a caller error, carry no user
data, and leave the exception class name retrievable as a substring.

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
*server-side*. ``honcho-ai==2.5.1`` exposes no provider, model, API-key or
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

import logging
import os
from typing import Any, List, Optional, Tuple
from uuid import UUID

from django.utils import timezone

from llm_adapter.embedding_service import generate_embedding
from memory.backends import (
    MemoryBackend,
    MemoryAnswer,
    MemoryDigest,
    MemoryEntryId,
    MemoryEntryRef,
    MemoryHealth,
    _DIGEST_MAX_FACTS,
    _cosine_distance,
    _digest_text,
    _maybe_uuid,
    _ref_from_entry,
    _render_digest_facts,
    _scope_filter,
    _tenant_context,
    register_memory_backend,
)
from memory.models import MemoryEntry

#: Module logger. Every message it emits is IDs/lengths only -- memory content
#: is user data and must never reach a log sink (see :meth:`HonchoMemoryBackend.
#: _publish_engine_message`).
logger = logging.getLogger(__name__)

#: Upper bound for Honcho's paginated/top-k request parameters. The server
#: rejects oversized page sizes rather than clamping them, so an unbounded
#: caller-supplied ``limit``/``top_k`` would turn into an HTTP 422 instead of a
#: short result set. Requests above this are clamped and the response is
#: truncated to what the caller asked for.
_MAX_PAGE_SIZE = 100

#: Page budget for the derivation probe (:meth:`HonchoMemoryBackend.
#: _derivation_probe`, AP-B5.1 #1155): one bounded newest-first page of the
#: scope's conclusions is read. ``_MAX_PAGE_SIZE`` is reused because Honcho
#: 422s oversized pages exactly like for every other list call.
_DERIVATION_PROBE_PAGE_SIZE = _MAX_PAGE_SIZE

#: Conclusion levels only the Deriver/Dream can produce (verified against
#: ``honcho-ai==2.5.1``'s ``ConclusionLevel`` literal, see the module
#: docstring). A conclusion at any of these levels is proof that derivation
#: happened for the scope; ``explicit`` never is, because every ``write``
#: creates one directly.
_DERIVED_CONCLUSION_LEVELS = ("deductive", "inductive", "contradiction")

#: Peer-id prefix for the ``artifact`` scope (RFC #1002). Deliberately NOT
#: applied to ``user``/``workspace``: those keep the legacy unprefixed
#: ``<tenant>_<id>`` shape so already-written external peers stay addressable
#: (there is no migration for a foreign service). The artifact scope is new,
#: so it gets the explicit prefix from day one.
_ARTIFACT_SCOPE_PREFIX = "a"

#: Scopes whose peer id keeps the legacy unprefixed ``<tenant>_<id>`` shape.
_LEGACY_UNPREFIXED_SCOPES = ("user", "workspace")

#: Prefix for a scope's session id (F6). Sessions and peers are separate Honcho
#: namespaces, so this prefix is not a collision guard -- it makes the two
#: families distinguishable when reading Honcho's own logs/UI, and keeps the id
#: obviously derived from the peer it belongs to. See
#: :meth:`HonchoMemoryBackend._scope_session_id`.
_SESSION_ID_PREFIX = "s"

#: Stable prefix marking a degraded ``ask`` as an ENGINE/TRANSPORT failure --
#: the peer/chat call could not reach or be answered by the engine (an SDK
#: ``ServerError``, a timeout, a missing session, ...). See
#: :func:`_degraded_detail` for the full contract.
_DEGRADED_ENGINE_PREFIX = "engine_error:"

#: Stable prefix marking a degraded ``ask`` as a rejected UNKNOWN SCOPE -- the
#: caller passed a ``scope`` this backend does not know, so no engine call was
#: ever attempted. Deliberately distinct from :data:`_DEGRADED_ENGINE_PREFIX`
#: so a caller can tell "the engine is down" (retryable, an outage) from "you
#: asked for a scope that does not exist" (a caller bug) without parsing logs.
_DEGRADED_UNKNOWN_SCOPE_PREFIX = "unknown_scope:"

#: Marker the scope resolvers use in their rejection message (kept in sync with
#: ``memory.backends._scope_filter`` and :meth:`HonchoMemoryBackend._scope_peer_id`).
#: :func:`_degraded_detail` classifies on this marker rather than on the
#: exception type: an SDK ``ValueError`` is an engine error, not a scope
#: rejection, and must not be mislabelled.
_UNKNOWN_SCOPE_MARKER = "unknown memory scope"


def _degraded_detail(exc: BaseException) -> str:
    """Return the non-user-data ``detail`` for a degraded ``ask`` answer.

    Consumed by :class:`memory.backends.MemoryAnswer.detail`. Contract:

    * NON-EMPTY for every degraded outcome -- a degraded answer always says
      *why* it degraded (the old bare ``type(exc).__name__`` did too, but could
      not distinguish causes);
    * DETERMINISTIC for a given cause: an engine/transport failure yields
      ``"engine_error:<ExceptionClassName>"`` (stable per exception class), a
      rejected unknown scope yields ``"unknown_scope:<ExceptionClassName>"``;
    * DISCRIMINABLE: the :data:`_DEGRADED_ENGINE_PREFIX` prefix marks an
      engine/transport failure, :data:`_DEGRADED_UNKNOWN_SCOPE_PREFIX` a
      rejected scope -- so "the engine is down" and "you asked for a scope
      that does not exist" never collapse into the same token;
    * CONTAINS NO USER DATA: only the exception *class name* enters the string,
      never the exception message (which can embed the query text or memory
      content) and never any memory text;
    * the exception CLASS NAME stays RETRIEVABLE as a substring, so a consumer
      that matched the old bare ``"RuntimeError"`` keeps matching.

    Classification is by the :data:`_UNKNOWN_SCOPE_MARKER` the scope resolvers
    put in their ``ValueError``, not by exception type alone: a Honcho SDK
    ``ValueError`` flowing out of ``peer.chat`` is an engine error.
    """
    name = type(exc).__name__
    if isinstance(exc, ValueError) and _UNKNOWN_SCOPE_MARKER in str(exc):
        return f"{_DEGRADED_UNKNOWN_SCOPE_PREFIX}{name}"
    return f"{_DEGRADED_ENGINE_PREFIX}{name}"


def _with_engine_enabled(current: Any) -> Any:
    """Return *current* configuration with the Deriver features switched on.

    Conservative get-modify-set: it starts from what the server already has and
    only forces the four feature flags, so any ``custom_instructions``,
    summary counters or (future) server-side setting this client does not model
    survives the round trip. A flag that is already on stays exactly as it is,
    which lets the caller skip the write entirely when nothing would change
    (see :meth:`HonchoMemoryBackend._ensure_engine_configuration`).

    Works for both ``SessionConfiguration`` and ``WorkspaceConfiguration`` --
    the former subclasses the latter unchanged in ``honcho-ai==2.5.1``, so both
    expose the same four fields and ``model_copy`` keeps the concrete class.

    The SDK is imported lazily (see the module docstring's Global Constraint):
    this function is only ever reached from the session path, which must stay
    importable without ``honcho-ai`` installed.
    """
    from honcho.api_types import (  # honcho-ai; lazy, see docstring
        DreamConfiguration,
        PeerCardConfiguration,
        ReasoningConfiguration,
        SummaryConfiguration,
    )

    return current.model_copy(
        update={
            # Reasoning unlocks the Deriver's actual analysis; without it a
            # message is stored but never turned into conclusions we could
            # digest later.
            "reasoning": (current.reasoning or ReasoningConfiguration()).model_copy(
                update={"enabled": True}
            ),
            "peer_card": (current.peer_card or PeerCardConfiguration()).model_copy(
                update={"use": True, "create": True}
            ),
            "summary": (current.summary or SummaryConfiguration()).model_copy(
                update={"enabled": True}
            ),
            "dream": (current.dream or DreamConfiguration()).model_copy(
                update={"enabled": True}
            ),
        }
    )

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


#: Default timeout, in seconds, for the Honcho SDK client this backend builds.
#: Follow-up of REQ-192 (code-review F2): before this the client was constructed
#: with no timeout, so a dialectic ``peer.chat`` (and every other SDK call)
#: could block unbounded. A generative answer legitimately takes longer than the
#: health probe, so it gets a generous budget of its own rather than reusing
#: ``HEALTH_PROBE_TIMEOUT``. Overridable through ``MEMORY_ASK_TIMEOUT``.
_DEFAULT_ASK_TIMEOUT_S = 120.0


def _ask_timeout_s() -> float:
    """Timeout for the SDK client that serves :meth:`HonchoMemoryBackend.ask`.

    Reads ``MEMORY_ASK_TIMEOUT`` (seconds) and falls back to
    :data:`_DEFAULT_ASK_TIMEOUT_S`; a non-positive or unparsable value falls back
    too, so a typo can never produce an instant, always-failing call.

    Applied as the ``Honcho(...)`` client's default request timeout. That bounds
    the whole ask path -- ``client.peer()`` (a get-or-create POST) *and* the
    generative ``peer.chat`` call -- not just the chat request, because the
    pre-chat peer resolution is a network call too and would otherwise still
    block unbounded. ``peer.chat`` omits its per-call ``timeout`` so it inherits
    this client default (documented by the SDK).
    """
    raw = os.environ.get("MEMORY_ASK_TIMEOUT", "")
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return _DEFAULT_ASK_TIMEOUT_S
    return value if value > 0 else _DEFAULT_ASK_TIMEOUT_S


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


def _unit_count(value: Any) -> Optional[int]:
    """Parse one ``queue_status`` work-unit counter; ``None`` when unusable.

    Guards the #1052 failure detection (see :meth:`HonchoMemoryBackend.
    _queue_gap`) against test doubles and older server/SDK shapes: only
    a real non-negative ``int`` counts. ``bool`` is explicitly rejected -- it
    is an ``int`` subclass, and a stray ``True`` would silently pass as ``1``
    and corrupt the queue accounting.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if value >= 0 else None


#: Placeholder observer/observed pair used only to construct a
#: ``ConclusionsView`` whose ``delete()`` is called.
#:
#: Deleting a conclusion is a workspace-level operation in Honcho
#: (``DELETE /v3/workspaces/{workspace_id}/conclusions/{conclusion_id}`` --
#: the observer/observed pair is not part of the route and ``delete()`` never
#: reads it), but ``honcho-ai==2.5.1`` only exposes ``delete()`` through a
#: ``ConclusionsView``.
#:
#: :meth:`HonchoMemoryBackend._delete_conclusion` therefore constructs a
#: ``ConclusionsView`` directly instead of going through ``client.peer(...)``.
#: That is deliberate: ``client.peer()`` is a get-or-create that always POSTs
#: to ``/peers``, so routing a delete through it would create a junk peer in
#: every tenant's Honcho workspace -- one that Honcho would then start building
#: a representation for. ``ConclusionsView.__init__`` only stores these four
#: fields (it makes no network call), and ``delete()`` sends only the workspace
#: id and the conclusion id (plus the workspace-level ``_ensure_workspace``), so
#: neither placeholder ever reaches Honcho as a peer. The id is deliberately not
#: a valid ``tenant_uuid`` pair so it can never collide with a real memory peer
#: if it ever does get sent.
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
        # Memo of session ids whose Deriver configuration this process already
        # ensured (``_ensure_engine_configuration``), and of tenant workspace
        # configurations already ensured. Both exist purely to avoid repeating a
        # get+PUT round trip for every write THIS instance handles; a set is
        # enough because the work is idempotent -- a race would at worst
        # re-issue the same write. Deliberately per-instance and not
        # process-global: ``get_memory_backend()`` constructs a backend per
        # call, so nothing here can go stale against the server long enough to
        # matter, and a long-lived instance (a consolidation task writing
        # several facts) still skips the repeats.
        self._configured_sessions: set = set()
        self._configured_workspaces: set = set()

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
                # Bounded request budget: without it a hung dialectic engine made
                # ``ask`` (``client.peer()`` + ``peer.chat``) block unbounded.
                # See :func:`_ask_timeout_s`.
                timeout=_ask_timeout_s(),
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

    def _scope_session_id(self, tenant_id: UUID, scope: str, scope_id: UUID) -> str:
        """Resolve ``(scope, scope_id)`` to the stable Honcho session id (F6).

        Derived from :meth:`_scope_peer_id` rather than rebuilt from the scope
        map, so the session is namespaced by tenant (and shares the ``_a_``
        artifact prefix) exactly like the peer it belongs to -- one source of
        truth for the scope -> id mapping, and the id can never drift from the
        peer it describes.

        Stable per scope, never per write: the Deriver aggregates many messages
        into one peer representation over time, so a new session per entry would
        restart that aggregation every single time (see the module docstring).

        Raises:
            ValueError: for an unknown scope, via :meth:`_scope_peer_id`.
        """
        return f"{_SESSION_ID_PREFIX}_{self._scope_peer_id(tenant_id, scope, scope_id)}"

    def _peer(self, tenant_id: UUID, scope: str, scope_id: UUID) -> Any:
        """Return this scope's peer object (get-or-create, one POST).

        Extracted so a single write can create the conclusion *and* publish the
        message on the SAME peer: every ``client.peer()`` call is an HTTP POST
        (the docs call it lazy; it is not -- see the module docstring), so a
        second resolution would double the request count of every write.
        """
        client = self._ensure_client(tenant_id)
        return client.peer(self._scope_peer_id(tenant_id, scope, scope_id))

    def _conclusions(self, tenant_id: UUID, scope: str, scope_id: UUID) -> Any:
        """Return the ``ConclusionsView`` holding this scope's memory entries."""
        return self._peer(tenant_id, scope, scope_id).conclusions

    def _delete_conclusion(self, tenant_id: UUID, conclusion_id: str) -> None:
        """Delete one conclusion from *tenant_id*'s Honcho workspace.

        Cross-tenant deletion is structurally impossible: the client is bound
        to ``reqogniloom_<tenant_id>`` and that workspace is part of the delete
        route, so an id belonging to another tenant resolves to nothing.

        See :data:`_FORGET_SCOPE_PEER` for why the ``ConclusionsView`` is built
        directly rather than via ``client.peer(...)``.
        """
        from honcho.conclusions import ConclusionsView  # honcho-ai, lazy (see _ensure_client)

        client = self._ensure_client(tenant_id)
        scope = ConclusionsView(
            client,
            self._honcho_workspace_id(tenant_id),
            _FORGET_SCOPE_PEER,
            _FORGET_SCOPE_PEER,
        )
        scope.delete(str(conclusion_id))

    # -- session / message plumbing (F6) --------------------------------

    def _ensure_session(self, tenant_id: UUID, scope: str, scope_id: UUID) -> Any:
        """Return this scope's Honcho session, get-or-creating it if needed.

        The session metadata is constant per scope (tenant, scope and scope_id),
        so passing it on every call is an idempotent overwrite rather than a
        mutation -- and it makes a session created by an older ReqogniLoom
        build, or by hand, attributable. The Deriver configuration is ensured
        separately, best-effort, in :meth:`_ensure_engine_configuration`.
        """
        client = self._ensure_client(tenant_id)
        return client.session(
            self._scope_session_id(tenant_id, scope, scope_id),
            metadata={
                "reqogniloom_tenant_id": str(tenant_id),
                "reqogniloom_scope": scope,
                "reqogniloom_scope_id": str(scope_id),
            },
        )

    def _ensure_engine_configuration(
        self, tenant_id: UUID, client: Any, session: Any, session_id: str
    ) -> None:
        """Best-effort: turn on reasoning, peer card, summary and dream (F6).

        Toggles the SessionConfiguration (per scope session) and the
        WorkspaceConfiguration (per tenant, so a session this client never
        touches still inherits the flags). Both are a conservative
        get-modify-set through :func:`_with_engine_enabled`, memoized per
        backend instance -- which is exactly the batch case (a consolidation
        task or a request writing several facts) where the extra round trips
        would otherwise repeat on every write.

        Every failure is swallowed with a warning: these flags only make the
        engine produce richer derived artefacts, so an SDK that renamed a method
        or a server that rejects the configuration must not break memory writes
        (see the module docstring's fail-open rule).
        """
        try:
            from honcho.api_types import (  # honcho-ai; lazy, see module docstring
                SessionConfiguration,
                WorkspaceConfiguration,
            )

            if session_id not in self._configured_sessions:
                current = session.get_configuration() or SessionConfiguration()
                desired = _with_engine_enabled(current)
                if desired != current:
                    session.set_configuration(desired)
                self._configured_sessions.add(session_id)

            workspace_key = str(tenant_id)
            if workspace_key not in self._configured_workspaces:
                current_ws = client.get_configuration() or WorkspaceConfiguration()
                desired_ws = _with_engine_enabled(current_ws)
                if desired_ws != current_ws:
                    client.set_configuration(desired_ws)
                self._configured_workspaces.add(workspace_key)
        except Exception as exc:  # noqa: BLE001 - fail-open, see docstring
            logger.warning(
                "honcho memory: could not enable the Deriver configuration for "
                "tenant=%s (error type %s); writes continue unaffected",
                tenant_id,
                type(exc).__name__,
            )

    def _publish_engine_message(
        self,
        peer: Any,
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
    ) -> None:
        """Append *content* as a message to the scope's session (F6).

        This is what actually feeds Honcho's Deriver: the conclusion written by
        :meth:`write` is a stored fact, but only *messages* inside a *session*
        are observations the engine derives representations, cards and summaries
        from (see the module docstring).

        FAIL-OPEN by construction: the whole body sits in one ``try``/``except``
        and the caller treats it as fire-and-forget, so a session endpoint that
        is down, an SDK rename or a metadata rejection can never fail a write
        whose mandatory part (the conclusion + local mirror row) already
        succeeded. Success logs at debug, failure at warning -- and both log
        IDs/lengths only, never the content, because memory content is user data
        (identical discipline to the audit log's size-only metadata).

        Provenance travels as JSON-serialisable metadata (UUIDs stringified), so
        the engine can attribute the observation without a second lookup. Keys
        whose value is unknown are omitted rather than sent as ``null``: an
        absent ``source_event_id`` means "not derived from an event", and
        claiming otherwise in the engine's own data would be a bug.
        """
        try:
            session_id = self._scope_session_id(tenant_id, scope, scope_id)
            metadata: dict = {
                "reqogniloom_kind": "memory_entry",
                "tenant_id": str(tenant_id),
                "scope": scope,
                "scope_id": str(scope_id),
                "language": language,
                "confidence": float(confidence),
            }
            for key, value in (
                ("contributor_user_id", contributor_user_id),
                ("source_event_id", source_event_id),
                ("source_session_id", source_session_id),
            ):
                if value is not None:
                    metadata[key] = str(value)

            session = self._ensure_session(tenant_id, scope, scope_id)
            self._ensure_engine_configuration(
                tenant_id, self._ensure_client(tenant_id), session, session_id
            )
            session.add_messages([peer.message(content, metadata=metadata)])
        except Exception as exc:  # noqa: BLE001 - fail-open, see docstring
            logger.warning(
                "honcho memory: message publish failed for tenant=%s scope=%s "
                "scope_id=%s (content length %d, error type %s); the conclusion "
                "was stored anyway",
                tenant_id,
                scope,
                scope_id,
                len(content),
                type(exc).__name__,
            )
        else:
            logger.debug(
                "honcho memory: published a %d char message to session %s",
                len(content),
                session_id,
            )

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

        F6 adds one step: the same content is also published as a *message* in
        the scope's session (see :meth:`_publish_engine_message`), which is what
        gives Honcho's Deriver, peer card, summary and dream something to work
        with. That step is fail-open and runs only AFTER the conclusion -- and,
        deliberately, only after the no-object guard, so a rejected conclusion
        never leaves an orphan observation in the engine. Both the guard and the
        nanoid-in-``backend_ref`` contract are unchanged by F6.
        """
        peer = self._peer(tenant_id, scope, scope_id)
        created = peer.conclusions.create([{"content": content}])
        if not created:
            raise RuntimeError("Honcho accepted the conclusion but returned no object")
        conclusion = created[0]
        self._publish_engine_message(
            peer,
            tenant_id,
            scope,
            scope_id,
            content,
            contributor_user_id=contributor_user_id,
            source_event_id=source_event_id,
            source_session_id=source_session_id,
            language=language,
            confidence=confidence,
        )
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
            if limit <= 0:
                # See PgvectorMemoryBackend.list_entries: bounds an admin caller
                # that only wants the total without projecting ``content``.
                return [], total
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

    def digest(self, tenant_id: UUID, scope: str, scope_id: UUID) -> MemoryDigest:
        """Digest this scope's memory, preferring the engine's own artefact.

        Read ladder (see the module docstring):

        1. the peer representation scoped to this scope's session, falling back
           to the peer card when the representation is empty -- Honcho's Deriver
           output, which is the richest and cheapest thing to hand a caller;
        2. the scope's conclusion list -- the SAME bounded page the derivation
           probe already read (step 1's clean-but-empty case), or ``list_recent``
           when the engine read raised and no page exists yet;
        3. the LOCAL MIRROR rows (``list_entries``, no network) when a network
           call raised -- the engine is unreachable, so a best-effort local
           rendering is better than nothing, but ``degraded=True`` says so.

        ``degraded`` is ``True`` iff a backend/network call raised. A peer that
        answers cleanly and simply remembers nothing yields the sentinel body
        with ``degraded=False`` -- F9: "empty" is not "down". Never raises, and
        only a failure of the last step as well produces an empty text.

        ``derivation_status`` (AP-B5.1, #1155) tracks the *Deriver*, not this
        read, and is consulted on EVERY clean path:

        * a non-empty representation/card is deriver output -> ``ok``;
        * a clean-but-empty engine answer runs :meth:`_derivation_probe`
          -> ``ok`` (derived conclusions found) / ``none`` / ``failed``;
        * a demonstrable queue gap (units vanishing without completing)
          OUTRANKS the historical output -> ``failed``, even while ``text``
          still carries the derived artefact. Without this override a Deriver
          that died after producing once would read ``ok`` forever, which is
          the exact #1052 blind spot this AP exists to close;
        * an unreachable engine -> ``unknown`` (an outage must not masquerade
          as "nothing derived", and a scope that once derived must not
          masquerade as healthy).

        ``ok`` therefore means "this scope HAS produced derived output", never
        "the deriver is currently healthy" -- see the module docstring's
        quota paragraph for what the client surface cannot see at all.
        ``derived_count`` is the exact derived-conclusion count only when the
        probe bounded it exactly, else ``None`` -- never a fabricated total.
        """
        generated_at = timezone.now()
        try:
            body, engine_failed = self._engine_digest_body(tenant_id, scope, scope_id)
        except Exception as exc:  # noqa: BLE001 - degrade, never raise (contract)
            logger.warning(
                "honcho memory: digest could not reach the engine for tenant=%s "
                "scope=%s (error type %s); falling back to the local mirror",
                tenant_id,
                scope,
                type(exc).__name__,
            )
            body, engine_failed = "", True

        if body:
            # A non-empty representation/peer card is deriver OUTPUT, so the
            # baseline answer is ``ok`` -- but ``ok`` only ever means "this
            # scope has produced derived output", NEVER "the deriver is
            # currently healthy". A demonstrable queue gap is a loss of work
            # happening NOW and outranks the historical output (the text still
            # carries that output), so the quota-death case on an already-
            # derived scope cannot hide behind a permanent ``ok``.
            if engine_failed:
                status = "unknown"
            else:
                status = "ok"
                try:
                    peer_id = self._scope_peer_id(tenant_id, scope, scope_id)
                except ValueError:  # pragma: no cover - a body proves resolution
                    # Unreachable in practice: the body came from this scope's
                    # peer, so the id construction worked. Guarded anyway
                    # because ``digest`` must never raise; the answer then
                    # stays the proven ``ok`` without the queue signal.
                    peer_id = ""
                if peer_id and self._queue_gap(tenant_id, peer_id):
                    status = "failed"
            return MemoryDigest(
                text=_digest_text("honcho", scope, facts=None, body=body),
                generated_at=generated_at,
                backend="honcho",
                degraded=engine_failed,
                derivation_status=status,
                derived_count=None,
            )

        degraded = engine_failed
        page_items: Optional[List[Any]] = None
        if engine_failed:
            # The engine could not be read at all -- whether it had derived
            # anything is NOT determinable from here, and must not collapse
            # into "none" (F9 applied to the Deriver).
            derivation_status: str = "unknown"
            derived_count: Optional[int] = None
        else:
            derivation_status, derived_count, page_items = self._derivation_probe(
                tenant_id, scope, scope_id
            )

        if page_items is not None:
            # The probe already read this scope's conclusions: render from THAT
            # page rather than issuing a second, differently-timed read of the
            # same endpoint. Re-reading would re-resolve the peer (every
            # ``client.peer()`` is an HTTP POST, see the module docstring) and
            # could render a fact list that does not match the page the status
            # was derived from.
            contents = [conclusion.content for conclusion in page_items[:_DIGEST_MAX_FACTS]]
            return MemoryDigest(
                text=_digest_text(
                    "honcho", scope, facts=len(contents), body=_render_digest_facts(contents)
                ),
                generated_at=generated_at,
                backend="honcho",
                degraded=degraded,
                derivation_status=derivation_status,
                derived_count=derived_count,
            )

        try:
            conclusions = self.list_recent(
                tenant_id, scope, scope_id, limit=_DIGEST_MAX_FACTS
            )
        except Exception as exc:  # noqa: BLE001 - degrade to the mirror below
            logger.warning(
                "honcho memory: digest could not list conclusions for tenant=%s "
                "scope=%s (error type %s); falling back to the local mirror",
                tenant_id,
                scope,
                type(exc).__name__,
            )
            degraded = True
        else:
            contents = [ref.content for ref in conclusions]
            return MemoryDigest(
                text=_digest_text(
                    "honcho", scope, facts=len(contents), body=_render_digest_facts(contents)
                ),
                generated_at=generated_at,
                backend="honcho",
                degraded=degraded,
                derivation_status=derivation_status,
                derived_count=derived_count,
            )

        try:
            refs, _total = self.list_entries(
                tenant_id, scope, scope_id, limit=_DIGEST_MAX_FACTS
            )
            contents = [ref.content for ref in refs]
        except Exception:  # noqa: BLE001 - nothing left to fall back to
            return MemoryDigest(
                text="",
                generated_at=generated_at,
                backend="honcho",
                degraded=True,
                derivation_status=derivation_status,
                derived_count=derived_count,
            )
        return MemoryDigest(
            text=_digest_text(
                "honcho", scope, facts=len(contents), body=_render_digest_facts(contents)
            ),
            generated_at=generated_at,
            backend="honcho",
            degraded=True,
            derivation_status=derivation_status,
            derived_count=derived_count,
        )

    def _engine_digest_body(self, tenant_id: UUID, scope: str, scope_id: UUID) -> Tuple[str, bool]:
        """Return ``(body, failed)`` from the engine's representation/peer card.

        ``failed`` is ``True`` whenever a transport/backend call raised, which is
        what makes the enclosing digest report ``degraded=True``. An empty body
        with ``failed=False`` means the peer answered cleanly and simply has
        nothing yet -- NOT degraded (F9).

        A failing representation short-circuits before the card: both are calls
        on the same unreachable peer, so the second one would only add latency to
        an answer already known to be degraded.

        ``get_card()`` rather than the ``card`` attribute: the installed
        ``honcho-ai==2.5.1`` exposes *both* as methods, and ``card()`` is a
        deprecation shim that warns on every call (verified by introspecting the
        SDK in the deployed container).
        """
        client = self._ensure_client(tenant_id)
        peer = client.peer(self._scope_peer_id(tenant_id, scope, scope_id))
        session_id = self._scope_session_id(tenant_id, scope, scope_id)
        try:
            representation = peer.representation(session=session_id)
        except Exception as exc:  # noqa: BLE001 - degrade, never raise (see digest)
            logger.warning(
                "honcho memory: digest representation read failed for tenant=%s "
                "scope=%s (error type %s)",
                tenant_id,
                scope,
                type(exc).__name__,
            )
            return "", True
        body = (representation or "").strip()
        if body:
            return body, False

        try:
            card = peer.get_card()
        except Exception as exc:  # noqa: BLE001 - degrade, never raise (see digest)
            logger.warning(
                "honcho memory: digest peer-card read failed for tenant=%s "
                "scope=%s (error type %s)",
                tenant_id,
                scope,
                type(exc).__name__,
            )
            return "", True
        if card:
            return "\n".join(str(line) for line in card).strip(), False
        return "", False

    def _queue_gap(self, tenant_id: UUID, peer_id: str) -> bool:
        """Whether *peer_id*'s work-unit accounting shows a demonstrable gap.

        ``True`` ONLY when all four ``queue_status`` counters were readable as
        non-negative ints and ``total > completed + in_progress + pending`` --
        work units that vanished without completing and without being counted,
        the #1052 class. Everything else is ``False``: a balanced queue, an
        unreadable queue, and counters this SDK build does not expose. Absence
        of proof is never reported as proof of failure (F9); the one honest
        failure signal on this surface is the accounting gap.

        Two deliberate error directions:

        * a transient race between the caller's conclusion read and this queue
          read can briefly show a gap the server is about to close, so a
          spurious ``failed`` is possible -- fail-LOUD, never fail-silent, and
          the next digest corrects it (F9's asymmetry: a false alarm is
          recoverable, a silent healthy lie is not);
        * an unusable counter logs a WARNING, because a detector that can
          never fire is itself invisible (#1052's failure mode): silently
          returning ``False`` forever would disable failure detection without
          leaving a trace. Logs IDs/type names only -- never queue content.

        Never raises: the queue is a best-effort EXTRA signal on paths whose
        primary answer already stands.
        """
        try:
            queue = self._ensure_client(tenant_id).queue_status(observer=peer_id)
            total = _unit_count(getattr(queue, "total_work_units", None))
            completed = _unit_count(getattr(queue, "completed_work_units", None))
            in_progress = _unit_count(getattr(queue, "in_progress_work_units", None))
            pending = _unit_count(getattr(queue, "pending_work_units", None))
        except Exception as exc:  # noqa: BLE001 - best-effort signal, see docstring
            logger.warning(
                "honcho memory: queue_status probe failed for tenant=%s peer=%s "
                "(error type %s); failure detection skipped",
                tenant_id,
                peer_id,
                type(exc).__name__,
            )
            return False

        if None in (total, completed, in_progress, pending):
            logger.warning(
                "honcho memory: queue_status returned unusable counters for "
                "tenant=%s peer=%s (total=%s completed=%s in_progress=%s "
                "pending=%s); failure detection is inert on this surface",
                tenant_id,
                peer_id,
                *(type(v).__name__ if v is None else "int" for v in
                  (total, completed, in_progress, pending)),
            )
            return False

        return total > completed + in_progress + pending

    def _derivation_probe(
        self, tenant_id: UUID, scope: str, scope_id: UUID
    ) -> Tuple[str, Optional[int], Optional[List[Any]]]:
        """Probe whether Honcho's Deriver has produced anything for this scope.

        Returns ``(status, derived_count, items)`` with ``status`` from
        ``VALID_DERIVATION_STATUSES`` minus ``unsupported`` (this backend
        derives by design) and ``items`` the scope's bounded conclusion page
        the classification was made from -- ``None`` when no page could be
        read, which is the caller's signal to fall back to its own read.
        Handing the page back is deliberate: re-reading the same endpoint
        would re-resolve the peer (every ``client.peer()`` is an HTTP POST)
        and could render facts that do not match the page the status came
        from. Built ONLY on the surface verified against ``honcho-ai==2.5.1``
        (see the module docstring) -- F9 discipline applied to the Deriver, so
        every branch reports what the SDK actually showed:

        * ``ok`` + exact count -- the scope's conclusion page contains
          conclusions at a derived level (``deductive``/``inductive``/
          ``contradiction``); the count is ``None`` when the page saturated,
          because more derived conclusions may sit beyond the probe budget --
          a floor is not a total and is never reported as one;
        * ``ok`` + ``None`` -- a saturated page held no derived conclusion, but
          a server-side ``filters={"level": ...}`` re-check found one;
        * ``none`` -- probed cleanly, zero derived conclusions;
        * ``failed`` -- :meth:`_queue_gap` proved a work-unit accounting gap.
          Checked on EVERY clean path, so it outranks a ``ok`` earned from
          earlier output: a Deriver that dies after having derived once must
          not read healthy forever. The SDK exposes no per-unit error flag,
          so a failure the server counts as ``completed`` stays invisible
          from here -- that residual blind spot is the Zen-Go quota outage
          (#1155, HTTP 429) and is documented in the module docstring and
          ``deploy/README.md``, NOT papered over with a guess;
        * ``unknown`` -- the page read raised (engine unreachable, scope
          rejected), or the saturated-page level re-check raised. Never
          guessed, never downgraded to ``none``.

        Cost: one ``client.peer()`` get-or-create plus one bounded list GET,
        plus one ``queue_status`` GET for the failure signal. Never raises.
        """
        try:
            peer_id = self._scope_peer_id(tenant_id, scope, scope_id)
            view = self._conclusions(tenant_id, scope, scope_id)
            page = view.list(size=_DERIVATION_PROBE_PAGE_SIZE)
            items = list(page.items[:_DERIVATION_PROBE_PAGE_SIZE])
        except Exception as exc:  # noqa: BLE001 - the digest contract: never raise
            logger.warning(
                "honcho memory: derivation probe failed for tenant=%s scope=%s "
                "(error type %s); reporting unknown",
                tenant_id,
                scope,
                type(exc).__name__,
            )
            return "unknown", None, None

        # ``level`` defaults to the SDK's own field default ("explicit") so a
        # double that does not model the attribute is treated like a verbatim
        # stored conclusion, never as phantom deriver output.
        derived = [c for c in items if getattr(c, "level", "explicit") != "explicit"]
        if derived:
            bounded = len(items) < _DERIVATION_PROBE_PAGE_SIZE
            status: str = "ok"
            count: Optional[int] = len(derived) if bounded else None
        elif len(items) >= _DERIVATION_PROBE_PAGE_SIZE:
            # Saturated page: the newest N conclusions hold no derived item,
            # but older ones might. Confirm server-side per derived level
            # (one size-1 GET each) instead of guessing from a truncated view.
            try:
                confirmed = any(
                    view.list(size=1, filters={"level": level}).items
                    for level in _DERIVED_CONCLUSION_LEVELS
                )
            except Exception as exc:  # noqa: BLE001 - see the except above
                logger.warning(
                    "honcho memory: derivation level re-check failed for tenant=%s "
                    "scope=%s (error type %s); reporting unknown",
                    tenant_id,
                    scope,
                    type(exc).__name__,
                )
                # The page itself was read fine, so the caller can still render
                # it -- only the derivation ANSWER is undeterminable.
                return "unknown", None, items
            status = "ok" if confirmed else "none"
            count = None if confirmed else 0
        else:
            status, count = "none", 0

        # The failure signal is scope-local and independent of whether output
        # exists, so it is consulted on every clean path (see the docstring).
        if self._queue_gap(tenant_id, peer_id):
            status = "failed"
        return status, count, items

    def ask(
        self,
        tenant_id: UUID,
        scope: str,
        scope_id: UUID,
        query: str,
        *,
        reasoning_level: Optional[str] = None,
    ) -> MemoryAnswer:
        """Answer ``query`` via the engine's dialectic surface (F6 follow-up).

        Calls ``peer.chat`` on the scope's own tenant-namespaced peer, scoped to
        the scope's stable session so the answer is drawn from this scope's
        observations rather than the peer's whole history. ``reasoning_level``
        is forwarded only when set, so the SDK's own default (``"low"``)
        applies otherwise.

        Never raises (see :meth:`MemoryBackend.ask`): any SDK/transport error --
        an unreachable engine, a missing session (Honcho answers a sessionless
        dialectic call with ``MissingSessionID``/HTTP 400), an unknown scope
        rejected by :meth:`_scope_peer_id` -- degrades to
        ``MemoryAnswer(degraded=True)`` with an empty text and a non-empty
        ``detail`` carrying NO user data. ``degraded`` is ``True`` for every
        such failure; the ``detail`` string is built by
        :func:`_degraded_detail` and follows that helper's contract:

        * ``"engine_error:<ExceptionClassName>"`` for an engine/transport
          failure (e.g. an SDK ``ServerError`` -> ``"engine_error:ServerError"``);
        * ``"unknown_scope:<ExceptionClassName>"`` for a scope rejected by
          :meth:`_scope_peer_id` (no engine call was attempted).

        The prefixes let a caller distinguish an outage from a caller error
        without parsing logs, and the exception class name stays retrievable as
        a substring for backward compatibility. A ``None`` answer (Honcho's way
        of saying "nothing relevant known") is a clean, non-degraded empty
        answer, distinct from an outage (F9).

        The SDK client is built with a bounded request timeout (see
        :func:`_ask_timeout_s`), so neither the peer resolution nor the chat
        call can block unbounded. Logs IDs/lengths only, never the query,
        matching :meth:`_publish_engine_message`'s discipline.
        """
        generated_at = timezone.now()
        try:
            client = self._ensure_client(tenant_id)
            peer = client.peer(self._scope_peer_id(tenant_id, scope, scope_id))
            session_id = self._scope_session_id(tenant_id, scope, scope_id)
            kwargs: dict = {}
            if reasoning_level:
                kwargs["reasoning_level"] = reasoning_level
            answer = peer.chat(query, session=session_id, **kwargs)
        except Exception as exc:  # noqa: BLE001 - degrade, never raise (contract)
            logger.warning(
                "honcho memory: ask could not reach the engine for tenant=%s "
                "scope=%s (query length %d, error type %s); answering degraded",
                tenant_id,
                scope,
                len(query or ""),
                type(exc).__name__,
            )
            return MemoryAnswer(
                text="",
                generated_at=generated_at,
                backend="honcho",
                degraded=True,
                detail=_degraded_detail(exc),
            )

        # Without ``include_evidence`` the SDK returns the bare answer string, or
        # ``None`` when the engine found nothing to say -- never a wrapper.
        text = answer if isinstance(answer, str) else ("" if answer is None else str(answer))
        return MemoryAnswer(
            text=text, generated_at=generated_at, backend="honcho", degraded=False
        )

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
