"""App configuration for ARCH-L1-009 LlmAdapter."""
from django.apps import AppConfig


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
