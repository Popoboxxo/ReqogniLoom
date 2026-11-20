"""Artifact vector-backend registry (ADR-020 extension).

Before this module the artifact store was a hardcoded two-way switch inside
:mod:`application.vector_port`: a literal ``ARTIFACT_VECTOR_BACKEND == "qdrant"``
check, a Qdrant-only indexer and env-only configuration. Adding a store meant
editing the port, the indexer and the command. This module makes the store a
plugin, mirroring the memory backend registry
(:mod:`memory.backends`):

* :class:`VectorBackendPlugin` -- one registered store, declaring its
  capabilities, its admin settings schema and lazy factories for the read port
  and the write store.
* :data:`VECTOR_BACKEND_REGISTRY` / :func:`register_vector_backend` -- the
  extension point. A third store is a new subclass plus one decorator; the
  port, the indexer and the admin API pick it up without core changes.
* :func:`resolve_artifact_vector_backend_name` -- ``DB override > env >
  pgvector``. The DB override lives in
  :class:`persistence.models.SystemArtifactVectorSettings` (separate from the
  memory settings, because the artifact store is decoupled from
  ``MEMORY_BACKEND`` by ADR-020 §4).
* :func:`effective_qdrant_config` -- the one place that resolves "which Qdrant
  does the artifact store talk to".

Import direction: ``vector_port`` and ``vector_write_store`` import this
module -- never the reverse. Adapter construction is late-bound through
:data:`SEARCH_PORT_FACTORIES` / :data:`WRITE_STORE_FACTORIES`, which those
modules populate at import time, so the registry is free of import cycles and
importing it is always safe. ``qdrant_client`` is only touched through
:func:`importlib.util.find_spec` (availability) and inside the adapters.
"""
from __future__ import annotations

import importlib.util
import os
from abc import ABC
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, ClassVar

from persistence.qdrant_config import (
    DEFAULT_QDRANT_COLLECTION_PREFIX,
    DEFAULT_QDRANT_DISTANCE,
    DEFAULT_QDRANT_HNSW_EF_CONSTRUCT,
    DEFAULT_QDRANT_HNSW_M,
    DEFAULT_QDRANT_QUANTIZATION,
    DEFAULT_QDRANT_TIMEOUT,
    QDRANT_DISTANCE_ATTRS,
    QDRANT_QUANTIZATION_MODES,
    QdrantConfig,
    resolve_qdrant_config,
)

__all__ = [
    "ARTIFACT_VECTOR_BACKEND_ENV",
    "DEFAULT_ARTIFACT_VECTOR_BACKEND",
    "NoopWriteStore",
    "PgVectorVectorPlugin",
    "QdrantVectorPlugin",
    "VECTOR_BACKEND_REGISTRY",
    "VectorBackendCapabilities",
    "VectorBackendPlugin",
    "VectorBackendSettingField",
    "active_vector_backend_capabilities",
    "active_vector_backend_name",
    "build_write_store",
    "effective_qdrant_config",
    "get_vector_backend_plugin",
    "qdrant_client_available",
    "register_search_port_factory",
    "register_write_store_factory",
    "register_vector_backend",
    "resolve_artifact_vector_backend_name",
]

#: Explicit selector for the ARTIFACT vector backend. Deliberately separate from
#: ``MEMORY_BACKEND`` (ADR-020 §4).
ARTIFACT_VECTOR_BACKEND_ENV = "ARTIFACT_VECTOR_BACKEND"
DEFAULT_ARTIFACT_VECTOR_BACKEND = "pgvector"
QDRANT_ARTIFACT_BACKEND = "qdrant"


@dataclass(frozen=True)
class VectorBackendCapabilities:
    """What an artifact vector backend can really do.

    Declared per plugin so callers (admin UI, health, search) can answer
    capability questions without constructing the backend.
    """

    #: Can serve nearest-neighbour queries through :class:`VectorPort`.
    search: bool = True
    #: Can fuse a text (BM25) leg with the dense leg.
    hybrid_query: bool = False
    #: Can answer cross-entity :meth:`VectorPort.query_entities`.
    entity_queries: bool = False
    #: Vectors live outside this database, so an external index must be built.
    external_store: bool = False
    #: ``manage.py index_artifact_vectors`` writes a real index for this store.
    indexing_required: bool = False
    #: The store keeps its own sparse/BM25 representation.
    sparse_vectors: bool = False


@dataclass(frozen=True)
class VectorBackendSettingField:
    """One backend setting the admin surface may persist.

    ``type`` mirrors the memory settings contract (``str``, ``int``, ``float``,
    ``bool``, ``choice``, ``secret``) so the same frontend renderer can be
    reused. ``secret`` values are never returned by a read surface; only
    ``secrets_set`` is reported.
    """

    name: str
    type: str
    env_var: str | None = None
    default: Any = None
    choices: tuple[str, ...] = ()
    min_value: float | None = None
    max_length: int | None = None
    label_key: str = ""


def _coerce_setting(field: VectorBackendSettingField, raw: str) -> Any:
    if field.type == "int":
        return int(raw)
    if field.type == "float":
        return float(raw)
    if field.type == "bool":
        return str(raw).strip().lower() in {"1", "true", "yes", "on"}
    return raw


def _artifact_settings_row() -> Any:
    """Best-effort read of the singleton; ``None`` when unset/unavailable."""
    try:
        from persistence.models import SystemArtifactVectorSettings

        return SystemArtifactVectorSettings.objects.first()
    except Exception:  # noqa: BLE001 - settings must never break a read
        return None


#: Late-bound adapter factories. The registry itself must not import
#: ``application.vector_port`` or ``application.vector_write_store`` (that
#: would close an import cycle; ``tests/test_architecture_contracts.py`` walks
#: function-level imports too). Those modules register their factories here at
#: import time, and :meth:`VectorBackendPlugin.create_search_port` resolves them
#: lazily. In practice the factory is always present: the only caller of
#: ``create_search_port`` is the selector in ``vector_port`` itself.
SEARCH_PORT_FACTORIES: dict[str, Callable[[], Any]] = {}
WRITE_STORE_FACTORIES: dict[str, Callable[[], Any]] = {}


def register_search_port_factory(name: str) -> Callable[[Callable[[], Any]], Callable[[], Any]]:
    """Register the read-port factory for ``name`` (called by ``vector_port``)."""

    def _decorator(factory: Callable[[], Any]) -> Callable[[], Any]:
        SEARCH_PORT_FACTORIES[name] = factory
        return factory

    return _decorator


def register_write_store_factory(name: str) -> Callable[[Callable[[], Any]], Callable[[], Any]]:
    """Register the write-store factory for ``name`` (called by ``vector_write_store``)."""

    def _decorator(factory: Callable[[], Any]) -> Callable[[], Any]:
        WRITE_STORE_FACTORIES[name] = factory
        return factory

    return _decorator


def qdrant_client_available() -> bool:
    """Whether the optional ``qdrant_client`` package is importable."""
    return importlib.util.find_spec("qdrant_client") is not None


class NoopWriteStore:
    """pgvector: the ORM column is the index, so no external write exists.

    Lives here (not in ``vector_write_store``) so the default
    :meth:`VectorBackendPlugin.create_write_store` needs no import of that
    module -- keeping the registry free of a back-edge.
    """

    name = "pgvector"
    available = False

    def ensure_workspace(
        self, tenant_id: Any, workspace_id: Any, *, dry_run: bool = False
    ) -> str:
        return ""

    def read_signature(self, handle: str, entity_id: Any) -> dict[str, Any] | None:
        return None

    def upsert(self, handle: str, record: Any) -> None:
        return None

    def delete(self, handle: str, entity_id: Any) -> None:
        return None

    def recreate_workspace(self, tenant_id: Any, workspace_id: Any) -> str:
        return ""


class VectorBackendPlugin(ABC):
    """One registered artifact vector backend."""

    #: Registry key (``"pgvector"``, ``"qdrant"``, ...).
    name: ClassVar[str] = ""
    #: Declared capability contract.
    capabilities: ClassVar[VectorBackendCapabilities] = VectorBackendCapabilities()
    #: Key this backend's settings live under in
    #: ``SystemArtifactVectorSettings.backend_options`` (``""`` = none).
    settings_key: ClassVar[str] = ""
    #: Declared settings schema rendered by the admin surface.
    settings_schema: ClassVar[tuple[VectorBackendSettingField, ...]] = ()

    @classmethod
    def availability_reason(cls) -> str:
        """Return ``""`` when the backend can serve, else a stable gate token."""
        return ""

    @classmethod
    def effective_settings(cls) -> dict[str, Any]:
        """Resolve ``DB override > env > default`` for non-secret fields."""
        override: dict[str, Any] = {}
        try:
            row = _artifact_settings_row()
            if row is not None and cls.settings_key:
                override = (row.backend_options or {}).get(cls.settings_key, {}) or {}
        except Exception:  # noqa: BLE001 - best effort
            override = {}

        values: dict[str, Any] = {}
        for setting in cls.settings_schema:
            if setting.type == "secret":
                continue
            if setting.name in override and override[setting.name] is not None:
                values[setting.name] = override[setting.name]
                continue
            raw = os.environ.get(setting.env_var) if setting.env_var else None
            values[setting.name] = (
                _coerce_setting(setting, raw) if raw not in (None, "") else setting.default
            )
        return values

    @classmethod
    def secret_names(cls) -> tuple[str, ...]:
        """Names of the declared ``secret`` fields (never their values)."""
        return tuple(
            setting.name for setting in cls.settings_schema if setting.type == "secret"
        )

    @classmethod
    def create_search_port(cls) -> Any:
        """Build the read-side port via the late-bound factory registry."""
        factory = SEARCH_PORT_FACTORIES.get(cls.name)
        if factory is None:
            raise RuntimeError(
                f"no search-port factory registered for {cls.name!r}; "
                "import application.vector_port first"
            )
        return factory()

    @classmethod
    def create_write_store(cls) -> Any:
        """Build the write-side store via the factory registry (noop default)."""
        factory = WRITE_STORE_FACTORIES.get(cls.name)
        if factory is not None:
            return factory()
        return NoopWriteStore()


VECTOR_BACKEND_REGISTRY: dict[str, type[VectorBackendPlugin]] = {}


def register_vector_backend(
    name: str,
) -> Callable[[type[VectorBackendPlugin]], type[VectorBackendPlugin]]:
    """Class decorator registering a :class:`VectorBackendPlugin` under ``name``."""

    def _decorator(cls: type[VectorBackendPlugin]) -> type[VectorBackendPlugin]:
        VECTOR_BACKEND_REGISTRY[name] = cls
        return cls

    return _decorator


def get_vector_backend_plugin(name: str) -> type[VectorBackendPlugin] | None:
    """Return the plugin registered under ``name``, or ``None`` (never raises)."""
    return VECTOR_BACKEND_REGISTRY.get(name)


def resolve_artifact_vector_backend_name() -> str:
    """Resolve the requested artifact backend: DB override > env > pgvector."""
    row = _artifact_settings_row()
    if row is not None and getattr(row, "vector_backend", None):
        return str(row.vector_backend).strip().lower()
    return os.environ.get(
        ARTIFACT_VECTOR_BACKEND_ENV, DEFAULT_ARTIFACT_VECTOR_BACKEND
    ).strip().lower()


def active_vector_backend_name() -> str:
    """Alias kept for symmetry with :func:`memory.backends.active_memory_backend_name`."""
    return resolve_artifact_vector_backend_name()


def active_vector_backend_capabilities() -> VectorBackendCapabilities:
    """Declared capabilities of the requested backend (no construction)."""
    plugin = get_vector_backend_plugin(resolve_artifact_vector_backend_name())
    if plugin is None:
        plugin = get_vector_backend_plugin(DEFAULT_ARTIFACT_VECTOR_BACKEND)
    if plugin is None:  # pragma: no cover - pgvector is always registered
        return VectorBackendCapabilities()
    return plugin.capabilities


def effective_qdrant_config() -> QdrantConfig:
    """The Qdrant connection the artifact store actually uses.

    Resolution order:

    1. ``SystemArtifactVectorSettings.backend_options["qdrant"]`` (+ the
       ``backend_secrets["qdrant"]["api_key"]`` secret) over the ``QDRANT_*``
       environment.
    2. Legacy fallback: when the artifact settings row holds no Qdrant options,
       the memory-owned resolver is used, so a deployment that configured
       Qdrant through the memory admin UI before this table existed keeps
       working.

    Best-effort and non-raising for a missing/unavailable DB: env is the
    fallback.
    """
    row = _artifact_settings_row()
    if row is not None:
        options = (row.backend_options or {}).get("qdrant", {}) or {}
        try:
            secrets = (row.backend_secrets or {}).get("qdrant", {}) or {}
        except Exception:  # noqa: BLE001 - rotated key must not break a read
            secrets = {}
        if options or secrets:
            overrides = {
                field: options[field]
                for field in (
                    "base_url",
                    "collection_prefix",
                    "distance",
                    "timeout",
                    "hnsw_m",
                    "hnsw_ef_construct",
                    "prefer_grpc",
                    "quantization",
                )
                if options.get(field) is not None
            }
            api_key = secrets.get("api_key") or None
            if api_key is not None:
                overrides["api_key"] = api_key
            return resolve_qdrant_config(**overrides)

    try:
        from memory.qdrant_backend import (  # lazy: legacy DB override
            resolve_effective_qdrant_config,
        )
    except ImportError:  # pragma: no cover - memory is always installed here
        return resolve_qdrant_config()
    return resolve_effective_qdrant_config()


@register_vector_backend("pgvector")
class PgVectorVectorPlugin(VectorBackendPlugin):
    """The default: vectors live in the Postgres ``embedding`` columns."""

    name = "pgvector"
    capabilities = VectorBackendCapabilities(
        search=True, hybrid_query=False, entity_queries=False, external_store=False
    )

@register_vector_backend("qdrant")
class QdrantVectorPlugin(VectorBackendPlugin):
    """The opt-in external store (ADR-020)."""

    name = "qdrant"
    capabilities = VectorBackendCapabilities(
        search=True,
        hybrid_query=True,
        entity_queries=True,
        external_store=True,
        indexing_required=True,
        sparse_vectors=True,
    )
    settings_key = "qdrant"
    settings_schema = (
        VectorBackendSettingField("base_url", "str", "QDRANT_BASE_URL"),
        VectorBackendSettingField(
            "collection_prefix",
            "str",
            "QDRANT_COLLECTION_PREFIX",
            default=DEFAULT_QDRANT_COLLECTION_PREFIX,
            max_length=64,
        ),
        VectorBackendSettingField(
            "distance",
            "choice",
            "QDRANT_DISTANCE",
            default=DEFAULT_QDRANT_DISTANCE,
            choices=tuple(QDRANT_DISTANCE_ATTRS),
        ),
        VectorBackendSettingField(
            "timeout",
            "float",
            "QDRANT_TIMEOUT",
            default=DEFAULT_QDRANT_TIMEOUT,
            min_value=0.1,
        ),
        VectorBackendSettingField(
            "hnsw_m", "int", "QDRANT_HNSW_M", default=DEFAULT_QDRANT_HNSW_M, min_value=1
        ),
        VectorBackendSettingField(
            "hnsw_ef_construct",
            "int",
            "QDRANT_HNSW_EF_CONSTRUCT",
            default=DEFAULT_QDRANT_HNSW_EF_CONSTRUCT,
            min_value=1,
        ),
        VectorBackendSettingField(
            "prefer_grpc", "bool", "QDRANT_PREFER_GRPC", default=False
        ),
        VectorBackendSettingField(
            "quantization",
            "choice",
            "QDRANT_QUANTIZATION",
            default=DEFAULT_QDRANT_QUANTIZATION,
            choices=QDRANT_QUANTIZATION_MODES,
        ),
        VectorBackendSettingField("api_key", "secret", "QDRANT_API_KEY"),
    )

    @classmethod
    def availability_reason(cls) -> str:
        """Return the first gate that keeps Qdrant from serving, or ``""``.

        The same three conditions the port documents (ADR-020 §4): the package
        is importable, the effective config resolves, and a base URL is set.
        Deliberately self-contained: the registry must not import
        ``application.vector_port`` back.
        """
        if not qdrant_client_available():
            return "qdrant_client_missing"
        try:
            config = effective_qdrant_config()
        except Exception:  # noqa: BLE001 - config problems degrade to pgvector
            return "qdrant_config_error"
        if not getattr(config, "base_url", "").strip():
            return "qdrant_base_url_missing"
        return ""


def build_write_store(name: str | None = None) -> Any:
    """Build the write store for ``name`` (default: the requested backend)."""
    backend = (name or resolve_artifact_vector_backend_name()).strip().lower()
    plugin = get_vector_backend_plugin(backend)
    if plugin is None:
        raise ValueError(f"unknown artifact vector backend: {backend!r}")
    return plugin.create_write_store()
