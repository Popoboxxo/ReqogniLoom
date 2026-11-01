"""Backend conformance registry (Plan A T-A0b-4, #1316).

A backend's declared :class:`~memory.backends.MemoryCapabilities` are only
worth anything if every implementation is held to the same contract. The
suite iterates this registry instead of a hand-maintained list of class names:
a backend added to ``MEMORY_BACKEND_REGISTRY`` without a fixture here makes
``test_every_registered_backend_has_conformance_fixture`` fail, so a future
backend cannot ship unexamined.

The fixtures are deliberately cheap. ``pgvector`` and ``qdrant`` construct
without I/O (their clients are lazy), and ``honcho`` is built with config
resolution skipped — the assertions below only read class-level declarations
and, for non-dialectic backends, the guaranteed ``degraded`` answer.

The QR-S04 derived-search isolation case (T-A4-3) is registered separately in
:data:`DERIVED_SEARCH_FIXTURES`: it has to drive a real ``query(source=
"derived")`` call, so only the backends that DECLARE ``search_derived=True``
need an (offline) engine fake, and every one of them must supply a probe.

The QR-S04 session-summaries isolation case (T-A4-5) is registered in
:data:`SESSION_SUMMARIES_FIXTURES` on the same principle: only the backends that
DECLARE ``summaries=True`` need a probe, every one of them must supply one
(:func:`missing_session_summaries_fixtures` is the gate), and the probe carries
both a foreign *workspace* session and a foreign *user* session -- a backend
that collapsed all users onto one peer would pass a workspace-only check while
still leaking another user's session summaries.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

from memory.backends import (
    MEMORY_BACKEND_REGISTRY,
    VALID_MEMORY_SCOPES,
    MemoryBackend,
    MemoryCapabilities,
)

#: Factories keyed by the same name ``MEMORY_BACKEND_REGISTRY`` uses.
CONFORMANCE_FIXTURES: dict[str, Callable[[], MemoryBackend]] = {}


def register_conformance_fixture(
    name: str,
) -> Callable[[Callable[[], MemoryBackend]], Callable[[], MemoryBackend]]:
    """Class-register a fixture factory for the backend registered as *name*."""

    def _decorator(factory: Callable[[], MemoryBackend]) -> Callable[[], MemoryBackend]:
        CONFORMANCE_FIXTURES[name] = factory
        return factory

    return _decorator


def missing_conformance_fixtures() -> list[str]:
    """Registered backends that no fixture covers (sorted, for a stable diff)."""
    return sorted(set(MEMORY_BACKEND_REGISTRY) - set(CONFORMANCE_FIXTURES))


@dataclass(frozen=True)
class DerivedSearchProbe:
    """A backend plus the one knob the QR-S04 isolation case needs.

    The case cannot build the engine's answer itself: derived search calls into
    the backend's engine, and this suite stays offline. So the backend's own
    fixture hands over the switch it controls -- which messages the engine fake
    returns -- instead of conformance importing that fake. A spec WITHOUT a
    ``peer_id`` key pins the fail-closed branch (an unattributable message must
    be dropped, never trusted).

    ``tenant_id``/``scope_id`` may be any UUIDs; the case only requires that
    ``own_peer_id`` is the peer this backend derives for that pair.
    """

    backend: MemoryBackend
    tenant_id: UUID
    scope: str
    scope_id: UUID
    own_peer_id: str
    install_messages: Callable[[list[Mapping[str, Any]]], None]


#: QR-S04 probes keyed like :data:`CONFORMANCE_FIXTURES`. Exactly the backends
#: declaring ``search_derived=True`` must be registered here -- enforced by
#: :func:`missing_derived_search_fixtures`, so a future backend with a second
#: recall surface cannot ship without its isolation case.
DERIVED_SEARCH_FIXTURES: dict[str, Callable[[], DerivedSearchProbe]] = {}


def register_derived_search_fixture(
    name: str,
) -> Callable[[Callable[[], DerivedSearchProbe]], Callable[[], DerivedSearchProbe]]:
    """Register a QR-S04 probe factory for the backend registered as *name*."""

    def _decorator(factory: Callable[[], DerivedSearchProbe]) -> Callable[[], DerivedSearchProbe]:
        DERIVED_SEARCH_FIXTURES[name] = factory
        return factory

    return _decorator


def missing_derived_search_fixtures() -> list[str]:
    """Backends declaring ``search_derived`` without a QR-S04 probe."""
    declared = {
        name
        for name, backend_cls in MEMORY_BACKEND_REGISTRY.items()
        if backend_cls.capabilities.search_derived
    }
    return sorted(declared - set(DERIVED_SEARCH_FIXTURES))


@dataclass(frozen=True)
class SessionSummariesProbe:
    """A backend plus the ids the ``summaries`` isolation case needs (T-A4-5).

    The QR-S04 decision lives in ``MemoryEntryService.session_summaries``: it
    allows exactly the session of THIS workspace's peer and the session of the
    caller's own user peer. That set is derived through
    :meth:`MemoryBackend.session_ref_for_scope`, so the isolation case can be
    checked per backend without importing the service: a foreign session must
    never be part of it.

    ``own_session_ref`` is the backend's own ref for the same workspace;
    ``foreign_session_ref`` is another workspace's and
    ``foreign_user_session_ref`` another user's. Both foreign refs must stay
    outside the allow-list, so a backend that collapses two workspaces (or two
    users) onto one session -- one peer shared by everyone -- fails here instead
    of silently widening the service's 404 to a real leak.
    """

    backend: MemoryBackend
    tenant_id: UUID
    workspace_id: UUID
    user_id: UUID
    own_session_ref: str
    foreign_session_ref: str
    foreign_user_session_ref: str


#: QR-S04 probes keyed like :data:`CONFORMANCE_FIXTURES`. Exactly the backends
#: declaring ``summaries=True`` must be registered -- enforced by
#: :func:`missing_session_summaries_fixtures`, so a future backend with a
#: session surface cannot ship without its isolation case.
SESSION_SUMMARIES_FIXTURES: dict[str, Callable[[], SessionSummariesProbe]] = {}


def register_session_summaries_fixture(
    name: str,
) -> Callable[[Callable[[], SessionSummariesProbe]], Callable[[], SessionSummariesProbe]]:
    """Register a QR-S04 probe factory for the backend registered as *name*."""

    def _decorator(
        factory: Callable[[], SessionSummariesProbe],
    ) -> Callable[[], SessionSummariesProbe]:
        SESSION_SUMMARIES_FIXTURES[name] = factory
        return factory

    return _decorator


def missing_session_summaries_fixtures() -> list[str]:
    """Backends declaring ``summaries`` without a QR-S04 probe."""
    declared = {
        name
        for name, backend_cls in MEMORY_BACKEND_REGISTRY.items()
        if backend_cls.capabilities.summaries
    }
    return sorted(declared - set(SESSION_SUMMARIES_FIXTURES))


def assert_capabilities_consistent(backend: MemoryBackend) -> None:
    """Assert the invariants every capability declaration must satisfy.

    * it is a :class:`MemoryCapabilities` instance (not a plain dict),
    * ``scopes`` is a subset of the canonical scopes,
    * both request bounds are positive,
    * ``ask_available`` agrees with ``dialectic``,
    * a backend that declares ``dialectic=False`` degrades instead of raising,
    * a backend that declares ``consolidation=False`` answers ``unsupported``
      from :meth:`MemoryBackend.consolidate` -- without raising and without
      attempting anything (Plan A T-A4-2). Backends that DO declare the
      capability are not probed here: the pass is a network call on Honcho, so
      the ``True`` side is pinned by that backend's own fake-SDK test.
    * a backend that declares ``search_derived=False`` answers ``[]`` for
      ``derived``/``all`` (Plan A T-A4-3). The ``True`` side -- the QR-S04
      isolation case -- is :func:`assert_derived_search_isolated`, driven from
      :data:`DERIVED_SEARCH_FIXTURES` because it needs an engine fake.
    """
    name = type(backend).__name__
    capabilities = backend.capabilities
    assert isinstance(capabilities, MemoryCapabilities), name
    assert set(capabilities.scopes) <= set(VALID_MEMORY_SCOPES), name
    assert capabilities.max_query_chars > 0, name
    assert capabilities.max_ask_query_chars > 0, name
    assert backend.ask_available is capabilities.dialectic, name

    if not capabilities.dialectic:
        answer = backend.ask(uuid4(), "workspace", uuid4(), "capability probe")
        assert answer.degraded is True, f"{name}: dialectic=False must degrade"

    if not capabilities.consolidation:
        outcome = backend.consolidate(uuid4(), "workspace", uuid4())
        assert outcome.status == "unsupported", (
            f"{name}: consolidation=False must answer 'unsupported', "
            f"got {outcome.status!r}"
        )

    if not capabilities.search_derived:
        for source in ("derived", "all"):
            refs = backend.query(
                uuid4(), "workspace", uuid4(), "capability probe", source=source
            )
            assert refs == [], (
                f"{name}: search_derived=False must answer [] for "
                f"source={source!r}, got {refs!r}"
            )

    if not capabilities.summaries:
        summaries = backend.session_summaries(uuid4(), "s_capability_probe")
        assert summaries == [], (
            f"{name}: summaries=False must answer [], got {summaries!r}"
        )


def assert_derived_search_isolated(name: str, probe: DerivedSearchProbe) -> None:
    """QR-S04: a derived search never returns a message from a foreign peer.

    Two drops are asserted, both fail-closed:

    * a message whose ``peer_id`` is a DIFFERENT peer -- the leak QR-S04
      forbids (one Honcho workspace spans a whole tenant);
    * a message with no readable ``peer_id`` at all -- unattributable, so it is
      dropped rather than trusted.

    Only the own peer's message survives. The probe's fake answers the one peer
    it was asked about, so a workspace-wide search has no peer to attribute the
    message to and cannot pass this case either.
    """
    own, foreign = probe.own_peer_id, f"{probe.own_peer_id}_foreign"
    probe.install_messages(
        [
            {"id": "probe-own", "content": "own peer fact", "peer_id": own},
            {"id": "probe-foreign", "content": "foreign peer secret", "peer_id": foreign},
            {"id": "probe-unattributed", "content": "unattributable secret"},
        ]
    )
    refs = probe.backend.query(
        probe.tenant_id, probe.scope, probe.scope_id, "probe", source="derived"
    )
    assert [ref.content for ref in refs] == ["own peer fact"], (
        f"{name}: derived search returned a non-own-peer message: {refs!r}"
    )
    assert [ref.entry_id for ref in refs] == ["probe-own"], name


def assert_session_summaries_isolated(name: str, probe: SessionSummariesProbe) -> None:
    """QR-S04: a workspace route may only ever reach its own two sessions.

    The service builds its allow-list from exactly these two
    ``session_ref_for_scope`` answers (this workspace's peer, the caller's own
    user peer). The case pins the property the 404 depends on: the caller's
    own sessions ARE in that set, and a foreign workspace's session and a
    foreign USER's session are NOT -- so neither can be read through the route,
    whatever the engine would answer for them.

    The user case is not redundant with the workspace one: a backend that
    derived one session per USER for every workspace (or ignored the scope id
    for the ``user`` scope) would keep the workspace assertion green and still
    expose another user's session summaries. Both refs are therefore required,
    and distinct from each other and from the own session.
    """
    allowed = {
        probe.backend.session_ref_for_scope(
            probe.tenant_id, "workspace", probe.workspace_id
        ),
        probe.backend.session_ref_for_scope(probe.tenant_id, "user", probe.user_id),
    }
    assert probe.own_session_ref in allowed, (
        f"{name}: the workspace's own session is not in the allowed set: {allowed!r}"
    )
    assert probe.foreign_session_ref not in allowed, (
        f"{name}: a foreign workspace session is in the allowed set: {allowed!r}"
    )
    assert probe.foreign_user_session_ref not in allowed, (
        f"{name}: a foreign user's session is in the allowed set: {allowed!r}"
    )
    assert probe.foreign_session_ref != probe.own_session_ref, name
    assert probe.foreign_user_session_ref != probe.own_session_ref, name
    assert probe.foreign_user_session_ref != probe.foreign_session_ref, name


def _pgvector() -> MemoryBackend:
    from memory.backends import PgvectorMemoryBackend

    return PgvectorMemoryBackend()


def _qdrant() -> MemoryBackend:
    from memory.qdrant_backend import QdrantMemoryBackend

    return QdrantMemoryBackend()


def _honcho() -> MemoryBackend:
    from memory.honcho_backend import HonchoMemoryBackend

    class _NoConfigHoncho(HonchoMemoryBackend):
        """Capability probe only: skip config resolution in ``__init__``."""

        def __init__(self) -> None:
            pass

    return _NoConfigHoncho()


register_conformance_fixture("pgvector")(_pgvector)
register_conformance_fixture("qdrant")(_qdrant)
register_conformance_fixture("honcho")(_honcho)
