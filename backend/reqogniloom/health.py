"""Health check endpoints for container readiness and liveness probes.

COMP-RA-006 HealthEndpoint — implements the split contract of ADR-010:

* ``GET /health/live``  — liveness: the process can serve HTTP. **Always 200**,
  never touches a dependency, so a dependency outage cannot restart-loop the
  container (restart-safety, REQ-L1-032).
* ``GET /health/ready`` — readiness: **fail-closed** (503) when any mandatory
  dependency is unhealthy. Mandatory: ``database``, ``memory_backend``,
  ``cache`` (Redis), ``celery_worker``, ``celery_beat``. The one exception is
  the OPTIONAL Qdrant memory backend (ADR-020 §4): when ``MEMORY_BACKEND=qdrant``
  is configured but unreachable, ``memory_backend`` is reported as ``degraded``
  and readiness stays 200 — pgvector remains the source of truth, so an
  opt-in backend outage must never turn the container unhealthy.
* ``GET /health/``      — deprecated alias for ``/health/ready`` (carries the
  ``Deprecation``/``Sunset`` headers) so the existing compose probe
  (``deploy/docker-compose.yml``) goes red on a mandatory dependency outage.

Advisory signals (``llm_provider_env``, ``embedding_dimensions``,
``embedding_model_consistency``, ``embedding_model_drift`` (``?verbose=1`` only;
per-table counts, or ``unknown`` when the connecting role cannot see past RLS),
``csrf_cookie_secure_matches_auth``,
``outbox_unbound_publishes``,
``outbox_pending`` / ``outbox_dlq`` queue gauges, workflow-definition warnings)
never affect the status code: they appear only
in ``warnings``/``advisory`` and escalate an otherwise-healthy response to
``status:"warning"`` (still HTTP 200). They are never a ``checks`` entry and
never produce ``degraded``/503.

The mandatory probes are reused from :mod:`admin_ops.health_rest`
(ADR-010 §7); the admin dashboard ``GET /api/v1/admin/health/`` stays the
detailed, admin-authenticated diagnostic view and is unchanged.
"""
from __future__ import annotations

import datetime as _dt
import email.utils as _email_utils
import logging
from collections.abc import Callable

from django.conf import settings as django_settings
from django.db import connection
from django.http import JsonResponse
from django.views import View

from reqogniloom.db_errors import is_db_saturation_error

logger = logging.getLogger(__name__)

#: Static failure marker exposed on the unauthenticated readiness endpoint.
#: Never a DSN/host/secret (CWE-209); the real cause only goes to the log.
_DEPENDENCY_DOWN_DETAIL = "dependency_down"

#: Static detail marker for an OPTIONAL dependency that is configured but
#: unreachable (ADR-020 §4, the Qdrant vector backend). Distinct from
#: ``dependency_down`` so an operator can tell a mandatory outage from a
#: degraded opt-in backend, and — like every other marker — never carries the
#: raw probe error (CWE-209).
_OPTIONAL_DEPENDENCY_DEGRADED_DETAIL = "optional_dependency_degraded"

#: Mandatory readiness dependencies, in their public contract order. ``cache``
#: is the ADR-010 contract name for the Redis probe, whose reused admin row is
#: called ``redis`` (``admin_ops.health_rest._check_redis``).
_REQUIRED_CHECK_NAMES = (
    "database",
    "memory_backend",
    "cache",
    "celery_worker",
    "celery_beat",
)

#: Stable lowercase table keys for the ``embedding_model_drift`` advisory
#: (T-A0-6). Explicit instead of derived from the class name so
#: ``TraceLink``/``MemoryEntry`` cannot leak their casing into the payload.
_EMBEDDING_DRIFT_LABELS = {
    "Requirement": "requirement",
    "TraceLink": "tracelink",
    "Icd": "icd",
    "MemoryEntry": "memory",
}


def _embedding_dimension_mismatches() -> list:
    """Return the labels of embedding columns that do not match the provider.

    Mirrors ``application.management.commands.verify_embedding_dimensions``: the
    comparison is between the *physical* ``pg_attribute`` type and the
    *configured embedding provider's* output width — the actual silent-skip
    cause (#1018/#1019). Comparing against the width the *models* declare would
    miss exactly the drift this check exists for, because the models follow
    ``EMBEDDING_VECTOR_DIMENSIONS`` immediately while the physical columns only
    change when DDL runs.

    Read-only and bounded: one ``pg_attribute`` lookup per known embedding
    column. Only column labels are returned — never a type from an arbitrary
    source, never a DSN — so the result is safe to expose on the
    unauthenticated readiness endpoint (CWE-209).

    Returns:
        One label per mismatching (or missing) embedding column; empty when
        every column matches the configured provider's width.
    """
    from llm_adapter.embedding_service import (
        EMBEDDING_PROVIDER_REGISTRY,
        _read_config,
        get_embedding_provider,
    )
    from persistence.embedding_schema import column_type, embedding_columns

    cfg = _read_config()
    if cfg.provider_name not in EMBEDDING_PROVIDER_REGISTRY:
        # An unknown provider is already reported by the llm_adapter.W002
        # system check; there is no width to compare against here, so do not
        # raise a second, misleading alarm.
        return []

    expected = f"vector({get_embedding_provider(cfg).dimensions})"
    mismatches = []
    with connection.cursor() as cursor:
        for column in embedding_columns():
            if column_type(cursor, column.table, column.column) != expected:
                mismatches.append(column.label)
    return mismatches


def _embedding_count_scope() -> str:
    """Return the visibility class of an aggregate on this connection.

    Thin seam over :func:`persistence.rls_visibility.count_scope` so a test can
    drive the RLS verdict without creating database roles. See
    :func:`_embedding_model_drift` for what the three values mean here.
    """
    from persistence.rls_visibility import count_scope

    return count_scope()


def _embedding_model_drift() -> dict[str, int | str]:
    """Return, per table, how many vectors were written by a *different* model.

    T-A0-6 (ADR-024 O3, #1317 point 3): ``embedding_model`` records the
    provenance of every vector. A model change that keeps the same width is
    invisible to a cosine query, so a mixed corpus is otherwise undetectable;
    ``EMBEDDING_MODEL_STRICT=strict`` filters those rows out, and this advisory
    is how an operator learns the corpus is mixed in the first place.

    Drift here means ``embedding_model`` is non-``NULL`` and differs from the id
    the configured provider would write NOW. Legacy ``NULL`` rows are *not*
    drift — they predate the column (T-A0-5) and stay visible in both modes;
    the ``--models`` report of ``verify_embedding_dimensions`` is where their
    count is published.

    WHAT THIS ENDPOINT CAN AND CANNOT SEE. ``/health*`` is unauthenticated and
    sets no tenant, while the embedding tables are ``ENABLE`` + ``FORCE ROW
    LEVEL SECURITY``. ``unscoped`` skips the ORM tenant filter but is *not* an
    RLS bypass, so the count's meaning depends on the connecting role — it is
    classified first (:func:`_embedding_count_scope`):

    * **privileged role** (superuser / ``BYPASSRLS``) -> the count is
      corpus-wide and numeric;
    * **RLS-bound role with a tenant context set** -> the count is that
      tenant's, numeric;
    * **RLS-bound role without a tenant context** -> every aggregate reads
      ``0`` no matter the data, so each table reports the literal ``"unknown"``
      instead of a false clean bill. ``manage.py verify_embedding_dimensions
      --models`` is the authoritative cross-corpus view (it runs under the
      migration/owner role).

    This is NOT a whole-corpus question on this endpoint, and the payload never
    pretends it is. One conditional-``COUNT`` aggregate per embedding table
    (never a row scan in Python, never a per-row query). Keys are lowercase
    table labels; a broken table contributes ``0`` instead of raising, so the
    advisory can never fail the readiness endpoint.

    Returns:
        ``{table_label: drifting_row_count}`` for Requirement, TraceLink, Icd
        and MemoryEntry — every value ``"unknown"`` when the aggregate is
        RLS-shadowed.
    """
    from django.db.models import Count, Q

    from llm_adapter.embedding_service import current_embedding_model_id
    from persistence.embedding_schema import embedding_columns
    from persistence.rls_visibility import COUNT_SCOPE_SHADOWED

    model_id = current_embedding_model_id()
    shadowed = _embedding_count_scope() == COUNT_SCOPE_SHADOWED
    drift: dict[str, int | str] = {}
    for column in embedding_columns():
        label = _EMBEDDING_DRIFT_LABELS.get(
            column.model.__name__, column.model.__name__.lower()
        )
        if shadowed:
            # Not "0": under this role every COUNT would lie. See the docstring.
            drift[label] = "unknown"
            continue
        try:
            counted = column.model.unscoped.filter(
                embedding__isnull=False
            ).aggregate(
                drifting=Count(
                    "id",
                    filter=~Q(embedding_model=model_id)
                    & Q(embedding_model__isnull=False),
                )
            )
        except Exception as exc:  # noqa: BLE001 - health check must never crash
            logger.warning(
                "Health check: embedding-model drift count failed for %s - %s",
                column.label,
                exc,
            )
            drift[label] = 0
            continue
        drift[label] = int(counted.get("drifting") or 0)
    return drift


def _missing_llm_required_env() -> list[str]:
    """Return the names of provider-required environment variables that are unset.

    GitHub #1050, the public health half of
    :func:`llm_adapter.checks.check_opencode_session_required`
    (``llm_adapter.W003``).

    Same failure mode the system check exists for, and the same reason it needs a
    second surface: ``LLM_OPENCODE_SESSION`` is REQUIRED by the ``opencode_go``
    endpoint, which answers every chat completion without the
    ``x-opencode-session`` header with ``400 MissingSessionID``. The provider
    deliberately omits the header when the variable is unset, the resilience
    wrapper treats 4xx as permanent so nothing retries, and the only trace is a
    provider-side log line — the deployment looks healthy while every LLM call
    (decomposition, validation, consistency check) fails.

    ``manage.py check`` is pull-based and manual; this is where a deployment is
    actually watched.

    The variable NAME is safe to expose on the unauthenticated readiness
    endpoint (CWE-209) — it is a configuration name, not a value. The session id
    itself is treated as a credential and never read, logged or returned.

    Reuses ``llm_adapter``'s own constants so the check, the provider docstring
    and this function cannot drift apart on the spelling.

    Returns:
        The unset variable names; empty when the active provider needs nothing
        extra, or when a required variable is present (even blank-but-present is
        the provider's call, not this function's — an empty header must not be
        sent, and that decision belongs to the provider).
    """
    from llm_adapter.checks import OPENCODE_PROVIDER_NAME
    from llm_adapter.providers import resolve_provider_config

    cfg = resolve_provider_config()
    if cfg.provider_name != OPENCODE_PROVIDER_NAME:
        return []
    if (cfg.opencode_session or "").strip():
        return []
    return ["LLM_OPENCODE_SESSION"]


def _probe_status(probe: Callable[[], dict]) -> str:
    """Return an admin probe's status, degrading any unexpected error to "down".

    The reused probes already guard themselves, but readiness must never crash
    on its own dependency check, so this is a defensive backstop.
    """
    try:
        row = probe()
    except Exception as exc:  # noqa: BLE001 - a required probe must never crash readiness
        logger.warning("Health check: required dependency probe failed - %s", exc)
        return "down"
    return str(row.get("status", "down"))


def _is_optional_memory_backend(backend: object) -> bool:
    """Return True when *backend* is the optional Qdrant backend (ADR-020 §4).

    Qdrant is an opt-in second vector backend; pgvector stays the source of
    truth, so a reachability failure must be surfaced as ``degraded`` and must
    never turn ``/health/ready`` red. The import is guarded and a failure is
    treated as "not optional" (fail-closed): an unresolvable backend keeps the
    historical ``down`` behaviour rather than silently exempting a mandatory
    dependency from readiness.
    """
    try:
        from memory.qdrant_backend import QdrantMemoryBackend
    except Exception as exc:  # noqa: BLE001 - detection must never crash readiness
        logger.warning("Health check: optional-backend detection failed - %s", exc)
        return False
    return isinstance(backend, QdrantMemoryBackend)


def _probe_memory_backend() -> str:
    """Probe the active memory backend and classify it for readiness.

    Returns ``"ok"`` when healthy, ``"degraded"`` when the configured backend is
    the OPTIONAL Qdrant backend (ADR-020 §4: visible, never fatal), and
    ``"down"`` for every required backend failure or an unresolvable backend
    (fail-closed). The raw probe detail is logged but never returned (CWE-209).
    """
    try:
        from memory.backends import get_memory_backend

        backend = get_memory_backend()
    except Exception as exc:  # noqa: BLE001 - unresolved backend is fail-closed
        logger.warning("Health check: memory backend probe failed - %s", exc)
        return "down"

    try:
        memory_ok, memory_detail = backend.health_check()
    except Exception as exc:  # noqa: BLE001 - health check must never crash readiness
        memory_ok, memory_detail = False, exc

    if memory_ok:
        return "ok"
    if _is_optional_memory_backend(backend):
        logger.warning("Health check: optional memory backend degraded - %s", memory_detail)
        return "degraded"
    logger.warning("Health check: memory backend degraded - %s", memory_detail)
    return "down"


def _required_check_state(value: str | None) -> str:
    """Map a required-check result to the public ``checks`` vocabulary.

    ``degraded`` is reserved for the optional Qdrant memory backend (ADR-020
    §4); every other non-``ok`` value is a mandatory failure (``error``).
    """
    if value == "ok":
        return "ok"
    if value == "degraded":
        return "degraded"
    return "error"


def _dependency_detail(value: str | None) -> str:
    """Return the static, CWE-209-safe ``dependencies`` detail marker for a value.

    #1166: connection-slot exhaustion gets its own marker so an operator can
    distinguish overload from a genuinely unreachable DB. ADR-020 §4: an
    optional degraded dependency gets its own marker so it is not mistaken for a
    mandatory outage. Everything else is the generic ``dependency_down``.
    """
    if value == "db_unavailable":
        return "db_unavailable"
    if value == "degraded":
        return _OPTIONAL_DEPENDENCY_DEGRADED_DETAIL
    return _DEPENDENCY_DOWN_DETAIL


def _run_required_checks() -> dict[str, str]:
    """Run the mandatory readiness probes and return ``{contract_name: status}``.

    Reuses the bounded probes from :mod:`admin_ops.health_rest` (ADR-010 §7)
    instead of duplicating them; the admin ``redis`` row is mapped to the
    contract name ``cache``. Every probe is independently guarded. Any value
    other than ``"ok"`` is a failed mandatory dependency (fail-closed) — with
    the single exception of ``"degraded"``, the optional Qdrant memory backend
    (ADR-020 §4), which is non-fatal by design.

    The database and memory-backend probes stay local (they read the ORM and
    the active memory backend), matching the previous ``HealthView`` behaviour.
    """
    from admin_ops.health_rest import (
        _check_celery_beat,
        _check_celery_worker,
        _check_redis,
    )

    results: dict[str, str] = {}

    db_ok = False
    try:
        connection.ensure_connection()
        results["database"] = "ok"
        db_ok = True
    except Exception as exc:  # noqa: BLE001 - readiness must never crash
        # #697 (CWE-209): readiness is reachable without authentication, and a
        # psycopg error's str() carries host, port, user and DSN fragments. Only
        # the status code reaches the client; the real cause goes to the log.
        # #1166: a connection-slot exhaustion is reported with its own static
        # status marker so the dependency detail can say ``db_unavailable``
        # instead of the generic ``dependency_down``.
        results["database"] = (
            "db_unavailable" if is_db_saturation_error(exc) else "down"
        )
        logger.warning("Health check: database degraded - %s", exc)

    if db_ok:
        results["memory_backend"] = _probe_memory_backend()
    else:
        # The pgvector backend lookup reads the catalog, so without the DB the
        # dependency cannot be verified — fail closed rather than silently
        # omitting it (ADR-010 §4: `dependencies` lists every non-ok required
        # dependency).
        results["memory_backend"] = "down"

    results["cache"] = _probe_status(_check_redis)
    results["celery_worker"] = _probe_status(_check_celery_worker)
    results["celery_beat"] = _probe_status(_check_celery_beat)
    return results


def _collect_advisory(
    advisory: dict[str, str],
    warnings: list[str],
    *,
    db_ok: bool,
    verbose: bool = False,
) -> None:
    """Run the advisory (non-status) probes into ``advisory``/``warnings``.

    Per ADR-010 §2/§4 these never become a ``checks`` entry and can never cause
    ``degraded``/503 — a non-empty warning list only escalates ``ok`` to
    ``warning`` (HTTP 200).

    ``verbose`` (``GET /health/?verbose=1``) enables the advisory probes that
    cost a real aggregate query over every embedding table
    (``embedding_model_drift``, T-A0-6). They are absent from the payload
    unless asked for, so the cheap default probe stays cheap.
    """
    # Embedding-column dimension check (#1018/#1019): the physical pgvector
    # column width is fixed by the last migration that ran, while the
    # configured embedding provider's width is fixed at container start.
    # When they disagree every embedding write and every semantic search
    # pass is skipped *silently* (the write guard is best-effort by
    # design), so the only symptom is an artifact.search that never returns
    # semantic hits. Deliberately advisory (HTTP 200): a width mismatch
    # disables semantic search but every read and write path still works.
    # Skipped when the DB is down (it needs the catalog) and never allowed
    # to raise. Only a static marker and column labels reach the client; the
    # detail goes to the log — same CWE-209 handling as the required checks.
    if db_ok:
        try:
            dimension_mismatches = _embedding_dimension_mismatches()
        except Exception as exc:  # noqa: BLE001 - health check must never crash
            logger.warning(
                "Health check: embedding-dimension check failed - %s", exc
            )
            warnings.append("embedding-dimension check failed")
        else:
            advisory["embedding_dimensions"] = (
                "mismatch" if dimension_mismatches else "ok"
            )
            if dimension_mismatches:
                logger.warning(
                    "Health check: embedding dimension mismatch - %s",
                    ", ".join(dimension_mismatches),
                )
                warnings.append(
                    "embedding columns do not match the configured embedding "
                    "provider's output width — embedding writes and semantic "
                    "search are silently skipped. Run `python manage.py "
                    "verify_embedding_dimensions` for the column list and the "
                    "provider's expected width. BEFORE resizing, set "
                    "EMBEDDING_VECTOR_DIMENSIONS to that provider width: "
                    "running `python manage.py align_embedding_dimensions` "
                    "(image deployment) or makemigrations/migrate (source "
                    "checkout) while EMBEDDING_VECTOR_DIMENSIONS still holds "
                    "a stale width would rewrite the columns at that wrong "
                    "width and discard the stored vectors — the mismatch "
                    "would remain."
                )

    # App <-> Honcho embedding coupling (T-A0-4, #1317 finding 2): the app and
    # the Honcho memory backend embed through two independently configurable
    # sets of variables (``EMBEDDING_*`` vs ``HONCHO_EMBEDDING_*``). Both write
    # paths are best-effort, so a divergence raises nothing and logs nothing —
    # it only makes the memory vectors and the artifact vectors incomparable,
    # which silently degrades memory retrieval and semantic search. The same
    # comparison is reported by ``manage.py check`` as ``memory.W001`` (model)
    # and ``memory.W002`` (width); this is the watched half. Gated on ``db_ok``
    # like the dimension check above and for the same reason: the effective
    # backend and model can come from a ``SystemMemorySettings`` override, so
    # without the DB the comparison would fall back to env-only and could
    # contradict the stored override. Advisory (HTTP 200): everything still
    # works, just not in one vector space.
    if db_ok:
        try:
            from memory.checks import honcho_embedding_mismatches

            embedding_inconsistencies = honcho_embedding_mismatches()
        except Exception as exc:  # noqa: BLE001 - health check must never crash
            logger.warning(
                "Health check: embedding-consistency check failed - %s", exc
            )
            warnings.append("embedding-consistency check failed")
        else:
            detail = "; ".join(m.message for m in embedding_inconsistencies)
            if embedding_inconsistencies:
                advisory["embedding_model_consistency"] = f"mismatch: {detail}"
                logger.warning(
                    "Health check: app and Honcho embedding configuration "
                    "differ - %s",
                    detail,
                )
                warnings.append(
                    "The app and the Honcho memory backend are configured with "
                    f"different embedding settings ({detail}). Honcho embeds "
                    "memory entries while the app embeds artifacts, so the two "
                    "vector spaces are not comparable and memory retrieval and "
                    "semantic search silently degrade. Fix the deployment so "
                    "both resolve ONE model and width: leave "
                    "HONCHO_EMBEDDING_MODEL / HONCHO_EMBEDDING_VECTOR_DIMENSIONS "
                    "unset so they inherit EMBEDDING_MODEL_NAME / "
                    "EMBEDDING_VECTOR_DIMENSIONS (deploy/docker-compose.yml), or "
                    "set both sides to the same values. Reported by "
                    "`manage.py check` as memory.W001 (model) / memory.W002 "
                    "(width)."
                )
            else:
                advisory["embedding_model_consistency"] = "ok"

    # Embedding-model drift (T-A0-6, ADR-024 O3, #1317 point 3): how many
    # stored vectors per table were written by a model other than the one the
    # active configuration produces today. A model change that keeps the same
    # vector width is invisible to a cosine query, so without this an operator
    # cannot tell a clean corpus from a mixed one; ``EMBEDDING_MODEL_STRICT=
    # strict`` filters the drifting rows, ``warn`` (default) keeps them and logs
    # one WARNING per process. Advisory (HTTP 200): the vectors are still
    # usable, they are merely not comparable — re-embed with
    # ``manage.py backfill_embeddings --force``. VERBOSE-ONLY because it runs a
    # conditional-COUNT aggregate over every embedding table; the default
    # readiness probe must stay cheap. Gated on ``db_ok`` (it reads the corpus)
    # and never allowed to raise.
    #
    # A per-table value of ``unknown`` (T-A0-6 review follow-up) means the
    # aggregate is RLS-shadowed: this endpoint sets no tenant and the app role
    # is not a superuser/BYPASSRLS role, so every COUNT would read 0. Reporting
    # that as "clean" was a structural false negative, so the numbers are
    # withheld and one warning points at the authoritative command instead. The
    # HTTP status is untouched: still an advisory, never degraded/503.
    if verbose and db_ok:
        try:
            drift = _embedding_model_drift()
        except Exception as exc:  # noqa: BLE001 - health check must never crash
            logger.warning("Health check: embedding-model drift check failed - %s", exc)
            warnings.append("embedding-model drift check failed")
        else:
            advisory["embedding_model_drift"] = ",".join(
                f"{label}={count}" for label, count in drift.items()
            )
            unknown_labels = [
                label for label, count in drift.items() if not isinstance(count, int)
            ]
            total_drift = sum(
                count for count in drift.values() if isinstance(count, int)
            )
            if unknown_labels:
                logger.warning(
                    "Health check: embedding-model drift count is RLS-shadowed "
                    "for %s — reporting 'unknown'",
                    ", ".join(unknown_labels),
                )
                warnings.append(
                    "the embedding-model drift count cannot be trusted from this "
                    "endpoint: /health* is unauthenticated and sets no tenant, "
                    "the embedding tables are FORCE ROW LEVEL SECURITY, and the "
                    "connecting role cannot bypass RLS — so the per-table "
                    "aggregates are RLS-shadowed and reported as 'unknown' "
                    f"({', '.join(unknown_labels)}) instead of a meaningless 0. "
                    "Run `python manage.py verify_embedding_dimensions --models` "
                    "with a role that can see the whole corpus for the "
                    "authoritative per-table counts."
                )
            if total_drift:
                logger.warning(
                    "Health check: %d embedding row(s) were written by a "
                    "different model (per table: %s)",
                    total_drift,
                    advisory["embedding_model_drift"],
                )
                warnings.append(
                    f"{total_drift} stored embedding(s) were produced by a "
                    "different model than the current configuration (per "
                    f"table: {advisory['embedding_model_drift']}). Semantic "
                    "search compares vectors across vector spaces, which makes "
                    "their rankings meaningless for those rows. Re-embed them "
                    "with `manage.py backfill_embeddings --force`, or set "
                    "EMBEDDING_MODEL_STRICT=strict to exclude them from "
                    "similarity search until then (legacy rows with a NULL "
                    "embedding_model stay visible either way)."
                )

    # Provider-required environment check (#1050): `opencode_go` is selected
    # but `LLM_OPENCODE_SESSION` is not set, so every LLM call fails with a
    # permanent 400 that nothing retries and nothing surfaces. Advisory
    # (HTTP 200) for the same reason as the dimension check above: one feature
    # is dead, the service is not. NOT gated on the database — the check reads
    # environment/tenant LLM settings, not the catalog. Never allowed to raise.
    try:
        missing_env = _missing_llm_required_env()
    except Exception as exc:  # noqa: BLE001 - health check must never crash
        logger.warning("Health check: provider-env check failed - %s", exc)
        warnings.append("provider-environment check failed")
    else:
        advisory["llm_provider_env"] = "missing" if missing_env else "ok"
        if missing_env:
            logger.warning(
                "Health check: provider-required environment missing - %s",
                ", ".join(missing_env),
            )
            warnings.append(
                "The active LLM provider requires "
                f"{', '.join(missing_env)}, which is not set. The provider "
                "answers every LLM call with a permanent 4xx, so "
                "decomposition, validation and the consistency check all "
                "fail while the UI shows nothing. Set it in the environment "
                "and restart the process. The value is treated as a "
                "credential and is never echoed here. Reported by "
                "`manage.py check` as llm_adapter.W003."
            )

    # Outbox transaction-binding counter (#1438): a domain event published
    # outside a transaction is autocommitted on its own, i.e. it is not bound
    # to the mutation that produced it (SA-02). The bus counts every such
    # publish as ``outbox_unbound_publish_count``; a non-zero value means
    # some producer is missing its transaction wrapper. Advisory (HTTP 200):
    # the events are still delivered — they are merely not atomic with their
    # mutation — so this escalates ``ok`` to ``warning`` and never causes
    # degraded/503. The count is always published, so an operator can read it
    # even while it is zero.
    #
    # The count is bounded by a DECAY WINDOW (the counter key expires after
    # ``OUTBOX_UNBOUND_COUNTER_TTL`` seconds), so a resolved defect clears
    # this signal by itself — a monotonic counter could never clear and would
    # turn one historic occurrence into a permanent "warning". The window is
    # published alongside the count so the number is never read out of
    # context; "0" means the decay is disabled and the count is monotonic.
    try:
        from application.event_bus_metrics import (
            counter_window_seconds,
            unbound_publish_count,
        )

        unbound_publishes = unbound_publish_count()
        unbound_window = counter_window_seconds()
    except Exception as exc:  # noqa: BLE001 - health check must never crash
        logger.warning(
            "Health check: outbox-unbound-publish counter failed - %s", exc
        )
        warnings.append("outbox-unbound-publish counter unavailable")
    else:
        advisory["outbox_unbound_publishes"] = str(unbound_publishes)
        advisory["outbox_unbound_publish_window_seconds"] = str(unbound_window)
        if unbound_publishes:
            logger.warning(
                "Health check: %d domain event(s) were published outside a "
                "transaction within the last %d s — their outbox rows are "
                "not atomically bound to a mutation",
                unbound_publishes,
                unbound_window,
            )
            warnings.append(
                f"{unbound_publishes} domain event(s) were published outside a "
                "transaction within the last "
                f"{unbound_window} s (metric outbox_unbound_publish_count, "
                "window outbox_unbound_publish_window_seconds) — the outbox "
                "row of such an event is not atomically bound to the mutation "
                "that produced it, so a rollback of the mutation cannot take "
                "the event with it. The count is bounded by the window and "
                "therefore clears by itself once the defect is resolved and "
                "the window expires; it is NOT a running total that can only "
                "grow. The count is reported as `application.event_bus` "
                "warnings: the first unbound publish of a process is logged in "
                "full, every OUTBOX_UNBOUND_WARN_SUMMARY_INTERVAL-th one adds "
                "a compact summary, and the per-event-type breakdown is "
                "available from the counter. The producers to look at are the "
                "service methods that emit a domain event without an "
                "`@atomic_transaction` wrapper."
            )

    # Outbox queue depths (#1389): the poller reports backlog/DLQ in the log
    # only when the observation CHANGES, so a constant or stuck backlog would
    # be invisible after the first cycle. The poller therefore writes both
    # numbers to cache-backed gauges every cycle and this reads them — no
    # extra DB query per readiness call. The gauges carry a short TTL
    # (QUEUE_GAUGE_TTL_SECONDS), so a poller that stopped reports "unknown"
    # instead of a stale number. Advisory (HTTP 200): a non-zero backlog or
    # DLQ is an operator signal, never a mandatory-dependency failure — this
    # publishes the values without adding a warning, because a transient
    # backlog is normal operation. Never allowed to raise: a cache outage is
    # swallowed inside queue_depths(), which returns (None, None) — the gauges
    # then show "unknown" with NO warning; only an unexpected exception
    # (import/patch failure) here appends "outbox queue gauges unavailable".
    try:
        from application.event_bus_metrics import queue_depths

        outbox_backlog, outbox_dlq = queue_depths()
    except Exception as exc:  # noqa: BLE001 - health check must never crash
        logger.warning("Health check: outbox queue gauges failed - %s", exc)
        warnings.append("outbox queue gauges unavailable")
    else:
        advisory["outbox_pending"] = (
            "unknown" if outbox_backlog is None else str(outbox_backlog)
        )
        advisory["outbox_dlq"] = (
            "unknown" if outbox_dlq is None else str(outbox_dlq)
        )

    # Artifact vector backend (#1437): ``ARTIFACT_VECTOR_BACKEND=qdrant`` is an
    # explicit opt-in, but Qdrant only serves when ALL gate conditions hold
    # (importable package, memory backend qdrant, configured base URL).
    # Otherwise the port silently degrades to pgvector and an operator who set
    # the opt-in still reads "ok". Publish the requested/active backend and the
    # first failing gate so the documented silent fallback is visible — without
    # changing any selection behaviour. Advisory (HTTP 200): pgvector is a fully
    # functional fallback, so a mismatch escalates ``ok`` to ``warning`` and
    # never causes degraded/503. Not gated on ``db_ok``: the gate is
    # best-effort and falls back to the environment when the DB is unreachable.
    try:
        from application.vector_port import vector_backend_diagnostic

        vector_backend = vector_backend_diagnostic()
    except Exception as exc:  # noqa: BLE001 - health check must never crash
        logger.warning(
            "Health check: vector-backend diagnostic failed - %s", exc
        )
        warnings.append("vector-backend diagnostic failed")
    else:
        advisory["effective_vector_backend"] = vector_backend["active"]
        advisory["vector_backend_requested"] = vector_backend["requested"]
        advisory["vector_backend_active"] = vector_backend["active"]
        if vector_backend["reason"]:
            advisory["vector_backend_fallback_reason"] = vector_backend["reason"]
            logger.warning(
                "Health check: artifact vector backend requested=%s active=%s "
                "reason=%s",
                vector_backend["requested"],
                vector_backend["active"],
                vector_backend["reason"],
            )
            warnings.append(
                f"ARTIFACT_VECTOR_BACKEND={vector_backend['requested']} is "
                f"requested but the artifact vector port runs on "
                f"{vector_backend['active']} (reason: "
                f"{vector_backend['reason']}). Artifact ANN search therefore "
                "queries pgvector, not Qdrant. The four gate conditions are: "
                "ARTIFACT_VECTOR_BACKEND=qdrant, an importable qdrant_client "
                "package, MEMORY_BACKEND=qdrant (or the SystemMemorySettings "
                "override), and a configured QDRANT_BASE_URL. See "
                "application/vector_port.py."
            )

    # CSRF-cookie security check: AUTH_COOKIE_SECURE must match
    # CSRF_COOKIE_SECURE to avoid CSRF failures in deployments without a
    # TLS-terminating reverse proxy.
    csrf_matches = (
        django_settings.CSRF_COOKIE_SECURE == django_settings.AUTH_COOKIE_SECURE
    )
    advisory["csrf_cookie_secure_matches_auth"] = (
        "ok" if csrf_matches else "mismatch"
    )
    if not csrf_matches:
        warnings.append(
            "CSRF_COOKIE_SECURE "
            f"({django_settings.CSRF_COOKIE_SECURE}) does not match "
            f"AUTH_COOKIE_SECURE ({django_settings.AUTH_COOKIE_SECURE}) — "
            "expect CSRF failures in deployments without a "
            "TLS-terminating reverse proxy"
        )

    # Workflow-definition sanity check (#40): a GlobalWorkflowDefinition or
    # WorkflowEngineDefinition row with no `states` (empty list or missing
    # key) means the workflow was never actually initialized — items of
    # that type/workspace cannot transition. Only run once DB connectivity
    # is confirmed above. Advisory: free-text warnings only.
    if db_ok:
        try:
            from django.db.models import Q

            from workflow.models import (
                GlobalWorkflowDefinition,
                WorkflowEngineDefinition,
            )

            empty_states = Q(workflow_json__states=[]) | ~Q(
                workflow_json__has_key="states"
            )
            empty_globals = GlobalWorkflowDefinition.unscoped.filter(
                empty_states
            ).count()
            empty_workspace = WorkflowEngineDefinition.unscoped.filter(
                empty_states
            ).count()
            if empty_globals:
                warnings.append(
                    f"{empty_globals} global workflow definition(s) have no states defined"
                )
            if empty_workspace:
                warnings.append(
                    f"{empty_workspace} workspace workflow definition(s) have no states defined"
                )
        except Exception as exc:  # noqa: BLE001 - health check must never crash
            logger.warning("Health check: workflow-definition check failed - %s", exc)
            warnings.append("workflow-definition check failed")


def _strict_readiness() -> bool:
    """Read the ADR-010 §6 feature flag (default: fail-closed strict).

    An unset/empty value is strict; only an explicit ``false`` yields the
    degraded-200 fallback mode.
    """
    return bool(getattr(django_settings, "HEALTH_STRICT_READINESS", True))


def _readiness_payload(*, verbose: bool = False) -> tuple[dict, int]:
    """Build the ``/health/ready`` body and HTTP status (ADR-010 §2/§4/§6).

    ``dependencies`` lists every non-``ok`` check — including an optional
    ``degraded`` backend, so the state stays observable — but only a genuine
    mandatory failure (any value other than ``ok``/``degraded``) may drive the
    503. ADR-020 §4: a configured-but-unreachable Qdrant backend is
    ``degraded`` at HTTP 200 and never turns readiness red.

    ``verbose`` (``GET /health/ready?verbose=1``) additionally runs the
    aggregate-only advisories (``embedding_model_drift``, T-A0-6). Without it
    those keys are absent and the probe costs exactly what it did before.
    """
    required = _run_required_checks()
    checks = {
        name: _required_check_state(required.get(name))
        for name in _REQUIRED_CHECK_NAMES
    }
    dependencies = [
        {
            "name": name,
            "status": required.get(name, "down"),
            "detail": _dependency_detail(required.get(name)),
        }
        for name in _REQUIRED_CHECK_NAMES
        if required.get(name) != "ok"
    ]
    # ADR-020 §4: only a genuine mandatory failure fails readiness. ``degraded``
    # is the optional Qdrant memory backend and stays a 200 signal.
    required_failed = any(
        required.get(name) not in ("ok", "degraded")
        for name in _REQUIRED_CHECK_NAMES
    )

    warnings: list[str] = []
    advisory: dict[str, str] = {}
    _collect_advisory(
        advisory, warnings, db_ok=required.get("database") == "ok", verbose=verbose
    )

    if dependencies:
        status_value = "degraded"
        http_status = 503 if (required_failed and _strict_readiness()) else 200
    elif warnings:
        status_value = "warning"
        http_status = 200
    else:
        status_value = "ok"
        http_status = 200

    return {
        "status": status_value,
        "checks": checks,
        "warnings": warnings,
        "dependencies": dependencies,
        "advisory": advisory,
    }, http_status


def _sunset_header_value(raw: str | None = None) -> str:
    """Return the ``Sunset`` HTTP-date for a deprecated endpoint (ADR-010 §3).

    ``raw`` is an ISO-8601 date, or an operator-supplied RFC 1123 date that is
    passed through unchanged. When omitted, the historical ``/health/`` alias
    sunset (``HEALTH_ALIAS_SUNSET``, ADR-010 §3) is used, preserving the
    original caller's behaviour. The ADR-014 §5 import contract passes its own
    ``IMPORT_CONTRACT_SUNSET`` (see :data:`sunset_header_value`).
    """
    if raw is None:
        raw = getattr(django_settings, "HEALTH_ALIAS_SUNSET", "2027-04-01")
    try:
        parsed = _dt.datetime.fromisoformat(str(raw))
    except ValueError:
        # An operator-supplied RFC 1123 date is passed through unchanged.
        return str(raw)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_dt.UTC)
    return _email_utils.format_datetime(parsed, usegmt=True)


#: Public alias for other deprecated endpoints that advertise a ``Sunset``
#: header (ADR-014 §5 import contract). Kept as an alias so the ADR-010
#: ``HealthAliasView`` call site and its tests are unchanged.
sunset_header_value = _sunset_header_value


class HealthLivenessView(View):
    """``GET /health/live`` — liveness: always 200, no dependency probe.

    Cheap and restart-safe: it never touches DB, cache, worker or beat, so a
    dependency outage cannot mark the container "dead" (ADR-010 §1).
    """

    def get(self, request):
        return JsonResponse({"status": "ok", "checks": {}}, status=200)


class HealthReadinessView(View):
    """``GET /health/ready`` — fail-closed readiness (ADR-010 §2/§4/§6)."""

    def get(self, request):
        # ``?verbose=1`` opts into the aggregate-only advisories (T-A0-6); the
        # probe stays cheap by default. Any other value (including a bare
        # ``?verbose``) means "not verbose".
        verbose = request.GET.get("verbose") == "1"
        payload, http_status = _readiness_payload(verbose=verbose)
        return JsonResponse(payload, status=http_status)


class HealthAliasView(HealthReadinessView):
    """``GET /health/`` — deprecated alias for ``/health/ready`` (ADR-010 §3).

    Inherits the readiness semantics so the existing compose probe goes red on a
    mandatory dependency outage, and advertises the deprecation via headers.
    """

    def get(self, request):
        response = super().get(request)
        response["Deprecation"] = "true"
        response["Sunset"] = _sunset_header_value()
        return response


#: Backward-compatible name for the public root view: the root URLconf imported
#: ``HealthView`` before the ADR-010 split into live/ready.
HealthView = HealthAliasView

__all__ = [
    "HealthAliasView",
    "HealthLivenessView",
    "HealthReadinessView",
    "HealthView",
    "sunset_header_value",
]
