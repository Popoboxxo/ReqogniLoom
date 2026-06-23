"""
ARCH-L1-009 LlmAdapter — Models.

TODO(COMP-LA-001): Implement LlmCapabilityInterface (abstract base class/protocol):
  - validate_artifact(artifact: dict) -> ValidationResult
  - decompose_requirement(requirement: dict) -> list[dict]
  - check_consistency(artifacts: list[dict]) -> ConsistencyReport
TODO(COMP-LA-002): Implement provider adapters: AnthropicAdapter, OpenAIAdapter,
  OllamaAdapter, AzureOpenAIAdapter, MockAdapter (for testing / graceful degradation).
TODO(COMP-LA-003): Implement LlmProviderFactory — selects provider based on
  settings.LLM_PROVIDER env variable at startup.

Reference: docs/se/L1/Gesamtsystem/L2/LlmAdapterSystem/L2_LlmAdapterSystem_Architecture.md
"""
from django.db import models  # noqa: F401
