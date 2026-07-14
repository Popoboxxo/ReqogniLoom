"""COMP-LA-005 Celery tasks for the LLM adapter async path.

Leaf node: ARCH-L1-009 / LlmAdapterSystem / COMP-LA-005
REQ-IDs: REQ-042, REQ-L2-LA-008, REQ-L3-LA005-001, REQ-L3-LA005-002

This module registers ``run_capability`` as a ``@shared_task`` so it is picked
up by ``reqflow.celery:app.autodiscover_tasks()`` and therefore known to the
worker started via ``celery -A reqflow worker``.

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
    from persistence.tenancy import TenantContext
    from llm_adapter.providers import get_provider, resolve_provider_config

    try:
        if tenant_id:
            TenantContext.set_tenant(tenant_id)
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

        record_token_usage(
            provider=getattr(provider, "PROVIDER_NAME", config.provider_name or "unknown"),
            capability=capability,
            input_tokens=getattr(result, "token_usage", None) or 0,
            output_tokens=0,
            workspace_id=kwargs.get("workspace_id"),
        )
        return _serialise(result)
    except Exception as exc:  # noqa: BLE001 — re-raised so Celery records FAILURE
        logger.error("LLM task failed for capability %s: %s", capability, exc, exc_info=True)
        raise
    finally:
        if tenant_id:
            TenantContext.clear_tenant()


__all__ = ["run_capability", "ALLOWED_CAPABILITIES"]
