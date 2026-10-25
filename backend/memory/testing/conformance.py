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
"""
from __future__ import annotations

from collections.abc import Callable
from uuid import uuid4

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


def assert_capabilities_consistent(backend: MemoryBackend) -> None:
    """Assert the invariants every capability declaration must satisfy.

    * it is a :class:`MemoryCapabilities` instance (not a plain dict),
    * ``scopes`` is a subset of the canonical scopes,
    * both request bounds are positive,
    * ``ask_available`` agrees with ``dialectic``,
    * a backend that declares ``dialectic=False`` degrades instead of raising.
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
