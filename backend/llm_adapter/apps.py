"""App configuration for ARCH-L1-009 LlmAdapter."""
import logging
import os
import sys

from django.apps import AppConfig

logger = logging.getLogger(__name__)

# Gesamttest 2026-08-29 Bug 2: one-off management commands where the
# embedding model is never used and must not pay the preload latency — most
# importantly `migrate` (a short-lived provisioning container per
# docker-compose.yml) and `test`/pytest (CI/local test envs may have no
# network access to huggingface.co at all, which would otherwise turn every
# test run into a multi-second-per-process tax or a hard failure).
_PRELOAD_SKIP_COMMANDS = {
    "test",
    "migrate",
    "makemigrations",
    "shell",
    "shell_plus",
    "collectstatic",
    "dbshell",
    "check",
    "showmigrations",
    "seed_demo",
}


class LlmAdapterConfig(AppConfig):
    """ARCH-L1-009 LlmAdapter — Provider Abstraction for LLM Capabilities.

    Responsibilities:
    - Thin adapter between application logic and external LLM providers (ADR-02).
    - Three core operations: validate_artifact, decompose_requirement, check_consistency.
    - Provider implementations (Anthropic, OpenAI, Ollama, Azure) are swappable
      via LlmCapabilityInterface.
    - Graceful degradation when LLM is not configured: returns error
      'LLM not configured' without crashing core functionality.
    - All outbound HTTPS calls are routed through ResilienceOrchestrator (ARCH-L1-016,
      IF-L1-050).

    See: docs/se/L1/Gesamtsystem/L2/LlmAdapterSystem/L2_LlmAdapterSystem_Architecture.md
    REQ-L1: REQ-L1-013 (LLM capabilities)
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "llm_adapter"
    verbose_name = "ARCH-L1-009 LlmAdapter"

    def ready(self) -> None:
        """Warm the default embedding provider's model at process startup.

        Gesamttest 2026-08-29 Bug 2:
        ``SentenceTransformersEmbeddingProvider`` (the default
        ``EMBEDDING_PROVIDER``) lazily loads its model on the *first* call to
        ``.embed()`` — which happens synchronously inside
        ``RequirementService.create()``'s request/response cycle
        (``_generate_and_store_embedding``, best-effort but still
        in-line). On a cold local HF cache that first load also performs
        ~15 unguarded HTTP HEAD/GET round-trips to huggingface.co to
        validate cached files, which measured ~3.5s here and is not bounded
        beyond each individual request's own default timeout — enough to
        trip a 15s E2E timeout on the first requirement ever created against
        a fresh worker (api-completeness.spec.ts).

        Preloading here moves that one-time cost to worker boot
        (gunicorn/celery — both recycle workers periodically via
        ``--max-requests``, so this can recur), where it is invisible to
        users, instead of onto whichever user's request happens to hit a
        cold worker first. Chosen over an async/Celery redesign of
        ``_generate_and_store_embedding`` (REQ-L2-VS-004's embedding write
        is fire-and-forget already; moving it off the request path entirely
        would change the create-response contract and touch
        ``find_similar_requirements`` / search-service read paths for a
        best-effort side effect — larger blast radius than this session's
        scope) and over a bare timeout-only fix (which would still block
        every cold-worker's first request, just for a bounded time instead
        of an unbounded one).

        Best-effort by design, matching every other embedding code path in
        this module (see ``embedding_service``'s module docstring): a
        failure here (offline dev environment, optional
        ``sentence-transformers`` extra not installed, non-default
        provider) is logged and swallowed, never raised — it must not block
        app startup or fail the container healthcheck.

        Known limitation (env-only, no DB read): this preload only sees the
        embedding provider configured via environment variables
        (``EMBEDDING_PROVIDER`` et al.), never a workspace's DB-stored
        override (``SystemMemorySettings.embedding_model_name``, set via the
        Memory Admin UI). That is a consequence of Django's
        ``AppConfig.ready()`` App-Registry order: ``llm_adapter`` (app index
        13 in ``INSTALLED_APPS``) initialises before ``memory`` (index 23),
        so no ``SystemMemorySettings`` row can be queried here yet even if
        we wanted to -- and querying the DB from ``ready()`` at all is
        deliberately avoided (``ready()`` is not guaranteed to run with
        migrations applied or a DB connection available, e.g. during
        ``migrate`` itself or in management commands that never touch the
        DB). Reordering ``INSTALLED_APPS`` to put ``memory`` before
        ``llm_adapter`` would not by itself fix this either -- it would just
        make the DB-query-in-``ready()`` anti-pattern possible, trading a
        documented limitation for a fragile startup-time DB dependency.
        Net effect: a DB-configured override only takes effect once the
        provider is next constructed from scratch (e.g. the first real
        request on a fresh worker after the override was saved), which may
        eagerly warm the *previous* (env-default) model here first. This is
        accepted, known behaviour, not a bug.
        """
        if self._should_skip_preload():
            return

        # Defense in depth for the startup-blocking case this preload
        # otherwise trades the request-blocking case for: bound each
        # individual HEAD/GET call huggingface_hub issues while validating
        # its local cache, so an unreachable/slow huggingface.co degrades to
        # a fast, logged skip instead of stalling worker boot. Only takes
        # effect if the deployment hasn't already set its own value.
        os.environ.setdefault("HF_HUB_ETAG_TIMEOUT", "5")

        try:
            from llm_adapter.embedding_service import get_embedding_provider

            provider = get_embedding_provider()
            # Only sentence-transformers has an expensive, in-process lazy
            # load worth warming eagerly; ollama/openai hit an external
            # service per-call regardless, and mock is instant.
            get_model = getattr(provider, "_get_model", None)
            if callable(get_model):
                get_model()
                logger.info(
                    "LlmAdapterConfig.ready(): embedding model preloaded (%s)",
                    type(provider).__name__,
                )
        except Exception as exc:  # noqa: BLE001 - best-effort, see docstring
            logger.warning(
                "LlmAdapterConfig.ready(): embedding model preload skipped: %s",
                exc,
            )

    @staticmethod
    def _should_skip_preload() -> bool:
        """True for one-off management-command processes (see module docstring)."""
        if "pytest" in sys.modules:
            return True
        if len(sys.argv) > 1 and sys.argv[1] in _PRELOAD_SKIP_COMMANDS:
            return True
        return False
