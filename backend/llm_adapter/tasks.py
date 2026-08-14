"""COMP-LA-005 Celery tasks for the LLM adapter async path.

Leaf node: ARCH-L1-009 / LlmAdapterSystem / COMP-LA-005
REQ-IDs: REQ-042, REQ-L2-LA-008, REQ-L3-LA005-001, REQ-L3-LA005-002

This module registers ``run_capability`` as a ``@shared_task`` so it is picked
up by ``reqogniloom.celery:app.autodiscover_tasks()`` and therefore known to the
worker started via ``celery -A reqogniloom worker``.

The previous implementation created a throw-away Celery app inside the
dispatcher on every call. That app was never wired to the project's worker, so
the worker discarded ``llm_adapter.run_capability`` messages and every dispatch
stayed PENDING forever. Registering the task here fixes the async path.
"""
from __future__ import annotations

import dataclasses
import logging

from celery import shared_task

logger = logging.getLogger(__name__)

# Security: only these capabilities may be dispatched to a worker. We never call
# an arbitrary ``getattr(provider, capability)`` on an unvalidated name.
ALLOWED_CAPABILITIES = frozenset(
    {
        "validate_artifact",
        "decompose_requirement",
        "check_consistency",
        "derive_requirements",
        "complete",  # generic free-form completion (Requirement Bundle Export Plan 2)
    }
)


def _serialise(result: object) -> dict:
    """Coerce a provider result into a Celery-serialisable dict.

    Provider capability methods return dataclasses (LlmResult,
    LlmDecompositionResult, LlmConsistencyResult). Those are converted via
    ``dataclasses.asdict``. A plain dict is passed through; anything else is
    wrapped under a ``result`` key.
    """
    if dataclasses.is_dataclass(result) and not isinstance(result, type):
        return dataclasses.asdict(result)
    if isinstance(result, dict):
        return result
    return {"result": result}


# Rough characters-per-token ratio for English text, used only as a fallback
# when no real token count is available (see _approximate_completion_tokens).
_APPROX_CHARS_PER_TOKEN = 4


def _approximate_completion_tokens(prompt: str, result_text: str) -> int:
    """Approximate a token count for a "complete" capability call.

    ``complete()`` (``llm_adapter.providers``) returns a plain ``str`` with
    no token-usage figure attached, unlike the 4 original capabilities whose
    results are dataclasses carrying a real ``.token_usage``. Real HTTP
    providers *do* compute a token count internally (see ``_invoke_chat``)
    but discard it before returning -- surfacing it would mean changing
    ``complete()``'s return type, which ripples through every one of its
    ~10 existing call sites (AiDerivationService, ArchitectureDecomposeService,
    AiReviewService, BundleCompressionService, TraceabilitySuggestService,
    MCP cross_cutting tools) and is out of scope for wiring up the
    "complete" capability here.

    This uses the common ~4-characters-per-token heuristic for English text
    instead, so REQ-106 daily-budget accounting for "complete" calls is a
    reasonable order-of-magnitude estimate rather than silently always 0.
    NOT a substitute for a real count -- revisit if precise accounting for
    "complete" calls becomes a real requirement.
    """
    combined_length = len(prompt or "") + len(result_text or "")
    return max(1, combined_length // _APPROX_CHARS_PER_TOKEN) if combined_length else 0


@shared_task(bind=True, name="llm_adapter.run_capability")
def run_capability(
    self,
    capability: str,
    kwargs: dict,
    tenant_id: str | None = None,
) -> dict:
    """Execute an LLM capability inside a Celery worker (REQ-L3-LA005-001).

    Args:
        capability: Whitelisted capability name to invoke on the provider.
        kwargs: Keyword arguments forwarded to the provider method.
        tenant_id: Optional tenant primary key (UUID string) to restore the
            tenant context for the duration of the task, since Celery workers
            run outside any request thread.

    Returns:
        Serialisable dict of the capability result.

    Raises:
        ValueError: If ``capability`` is not in the whitelist. Celery marks the
            task FAILURE and stores the exception in the result backend.

    Tenant configuration (REQ-083):
        Only the ``tenant_id`` crosses the queue boundary — never the raw API
        key. After restoring the tenant context the worker resolves the
        tenant's persisted LlmSettings (provider, api_key, base_url,
        model_name) from the database and instantiates the matching provider.
        Without a ``tenant_id`` the global environment configuration
        (``LLM_PROVIDER`` etc.) is used, preserving backward compatibility.
    """
    if capability not in ALLOWED_CAPABILITIES:
        raise ValueError(f"Unknown capability: {capability}")

    # Imported here to avoid import-time coupling and keep the module importable
    # in contexts where these deps are not needed.
    from persistence.middleware import clear_request_tenant, set_request_tenant
    from persistence.tenancy import TenantContext
    from llm_adapter.providers import get_provider, resolve_provider_config

    # #522 review follow-up: snapshot the context *before* arming it. Under
    # CELERY_TASK_ALWAYS_EAGER (settings_test.py) apply_async runs this body
    # inline on the caller's own thread and DB connection, and
    # AsyncTaskDispatcher._resolve_tenant_id (dispatcher.py) reads tenant_id
    # off that same caller's thread-local — so tenant_id is non-None precisely
    # when the caller already owns a context. Tearing it down unconditionally
    # in the finally therefore disarmed the *caller's* isolation for the rest
    # of its request, at both layers: CapabilityRouter.log_llm_call's audit
    # INSERT runs after this returns and was dropped by its own swallowing
    # except. Same unset->set nesting guard AuthTenancyMiddleware already uses.
    tenant_was_set = TenantContext.is_set()

    try:
        if tenant_id:
            # #444: TenantContext.set_tenant() alone only satisfies the Django
            # ORM side (TenantManager filters/auto-injects tenant_id in
            # Python). It never issues `SET app.current_tenant` on this
            # worker's DB connection, so Postgres RLS's WITH CHECK policy
            # rejects every INSERT here (record_token_usage below) with "new
            # row violates row-level security policy" — and its USING policy
            # silently hides every SELECT (resolve_provider_config's
            # LlmSettings lookup), masking the failure as "no per-tenant
            # settings configured" instead of surfacing it. Celery workers run
            # outside any request thread, so nothing else sets the RLS session
            # variable for this connection; set_request_tenant does both.
            set_request_tenant(tenant_id)
        # REQ-083: resolve per-tenant LLM settings from the DB (tenant context
        # is active now); falls back to the environment when no tenant_id was
        # dispatched or no settings row exists.
        config = resolve_provider_config()
        logger.info(
            "LLM worker resolved provider %s for tenant %s (capability=%s)",
            config.provider_name or "<unset>",
            tenant_id or "<none>",
            capability,
        )
        provider = get_provider(config)
        method = getattr(provider, capability)
        result = method(**kwargs)
        # REQ-106: record token consumption for the active tenant (best-effort;
        # never fails the task). Runs while the tenant context is still active.
        from llm_adapter.token_tracking import record_token_usage  # noqa: PLC0415

        token_usage = getattr(result, "token_usage", None)
        if token_usage is None and capability == "complete" and isinstance(result, str):
            # No real count on a plain-str "complete" result -- approximate
            # rather than silently recording 0 (see _approximate_completion_tokens).
            token_usage = _approximate_completion_tokens(kwargs.get("prompt", ""), result)

        record_token_usage(
            provider=getattr(provider, "PROVIDER_NAME", config.provider_name or "unknown"),
            capability=capability,
            input_tokens=token_usage or 0,
            output_tokens=0,
            workspace_id=kwargs.get("workspace_id"),
        )
        return _serialise(result)
    except Exception as exc:  # noqa: BLE001 — re-raised so Celery records FAILURE
        logger.error("LLM task failed for capability %s: %s", capability, exc, exc_info=True)
        raise
    finally:
        if tenant_id and not tenant_was_set and TenantContext.is_set():
            try:
                clear_request_tenant()
            except Exception:  # noqa: BLE001 — teardown must not mask the cause
                # #522 review follow-up: clear_request_tenant executes
                # `RESET app.current_tenant` on the connection, so unlike the
                # old bare TenantContext.clear_tenant() it can raise — and a
                # raise from a finally *replaces* the exception in flight.
                # Celery would then store this teardown error as the task
                # result while the real failure survived only in the log line
                # above. RESET only fails when the connection is already
                # broken; CONN_MAX_AGE is unset (Django default 0), so that
                # connection is closed rather than handed on with a stale
                # app.current_tenant. clear_request_tenant also clears the
                # Python thread-local before it touches the DB, so that half
                # of the teardown has happened regardless.
                logger.exception(
                    "LLM task could not reset the tenant context (capability=%s)",
                    capability,
                )


__all__ = ["run_capability", "ALLOWED_CAPABILITIES"]
