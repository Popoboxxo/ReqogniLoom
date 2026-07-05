"""
COMP-LA-002 ProviderRegistry — Provider implementations and plugin registry.

Leaf node: ARCH-L1-009 / LlmAdapterSystem / COMP-LA-002
REQ-IDs: REQ-L2-LA-001, REQ-L2-LA-005, REQ-L2-LA-007,
         REQ-L3-LA002-001, REQ-L3-LA002-002, REQ-L3-LA002-003

Architecture:
    docs/se/L1/Gesamtsystem/L2/LlmAdapterSystem/Components/
    COMP-LA-002_ProviderRegistry/L3_COMP-LA-002_ProviderRegistry_Architecture.md

Interface contract (IF-LA-INT-002):
    CapabilityRouter calls get_provider() -> LlmCapabilityInterface.

Provider isolation:
    Each provider class makes HTTP calls only when its methods are invoked.
    Provider SDK libraries (anthropic, openai, etc.) are imported lazily so that
    the module is importable without them installed. MockLlmProvider is always
    available and requires no external SDK.

Note on ResilienceOrchestrator (IF-L1-050, ADR-LA-04):
    In this implementation the provider classes are responsible for their own
    HTTP transport. Integration with the ResilienceOrchestrator (circuit-breaker,
    retry, backoff) is deferred to the infrastructure layer and does not change
    the interface contracts defined here.
"""
from __future__ import annotations

import os
import time
import warnings
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Type

from llm_adapter.interface import (
    LlmCapabilityInterface,
    LlmConsistencyResult,
    LlmDecompositionResult,
    LlmResult,
)

# ---------------------------------------------------------------------------
# Error codes (shared across modules)
# ---------------------------------------------------------------------------

LLM_NOT_CONFIGURED = "LLM_NOT_CONFIGURED"
LLM_PROVIDER_UNKNOWN = "LLM_PROVIDER_UNKNOWN"
LLM_PROVIDER_ERROR = "LLM_PROVIDER_ERROR"


# ---------------------------------------------------------------------------
# Provider configuration dataclass
# ---------------------------------------------------------------------------


@dataclass
class ProviderConfig:
    """Runtime configuration resolved from environment variables.

    Attributes:
        provider_name: Selected provider key (e.g. "anthropic").
        timeout: HTTP request timeout in seconds (REQ-L3-LA002-002).
        api_key: Provider API key read from environment.
        api_base_url: Optional base URL override (Ollama, Azure).
        azure_deployment: Azure-specific deployment name.
        azure_api_version: Azure-specific API version string.
        mock_delay: Simulated latency for MockLlmProvider (seconds).
        mock_error_rate: Fraction [0.0–1.0] of calls that should raise an error.
    """

    provider_name: str
    timeout: int = 30
    api_key: str = ""
    api_base_url: Optional[str] = None
    azure_deployment: Optional[str] = None
    azure_api_version: Optional[str] = None
    mock_delay: float = 0.0
    mock_error_rate: float = 0.0


def _read_config() -> ProviderConfig:
    """Read ProviderConfig from environment variables.

    Returns:
        Populated ProviderConfig instance.
    """
    return ProviderConfig(
        provider_name=os.environ.get("LLM_PROVIDER", ""),
        timeout=int(os.environ.get("LLM_TIMEOUT", "30")),
        api_key=os.environ.get("LLM_API_KEY", ""),
        api_base_url=os.environ.get("LLM_API_BASE_URL") or None,
        azure_deployment=os.environ.get("AZURE_OPENAI_DEPLOYMENT") or None,
        azure_api_version=os.environ.get("AZURE_OPENAI_API_VERSION") or None,
        mock_delay=float(os.environ.get("MOCK_LLM_DELAY", "0.0")),
        mock_error_rate=float(os.environ.get("MOCK_LLM_ERROR_RATE", "0.0")),
    )


# ---------------------------------------------------------------------------
# MockLlmProvider — always-available test/CI/graceful-degradation provider
# ---------------------------------------------------------------------------


class MockLlmProvider(LlmCapabilityInterface):
    """Deterministic mock provider for tests and environments without a real LLM.

    Configured by environment variables (REQ-L3-LA002-001):
        LLM_PROVIDER=mock
        MOCK_LLM_DELAY=<seconds>   — simulated latency (default 0)
        MOCK_LLM_ERROR_RATE=<0-1>  — fraction of calls that raise an error

    The mock always returns stable, predictable LlmResult objects so test
    assertions can rely on specific values without network access.
    """

    PROVIDER_NAME = "mock"
    MODEL_NAME = "mock-model-v1"

    def __init__(self, config: Optional[ProviderConfig] = None) -> None:
        self._config = config or _read_config()

    def _simulate(self) -> None:
        """Apply configured delay and optional error simulation."""
        if self._config.mock_delay > 0:
            time.sleep(self._config.mock_delay)
        if self._config.mock_error_rate > 0:
            import random

            if random.random() < self._config.mock_error_rate:
                raise RuntimeError("MockLlmProvider: simulated error")

    def validate_artifact(self, artifact_id: str) -> LlmResult:
        """Return a fixed validation result for the given artifact."""
        self._simulate()
        return LlmResult(
            score=0.85,
            suggestions=[f"Mock suggestion for artifact {artifact_id}"],
            provider=self.PROVIDER_NAME,
            model=self.MODEL_NAME,
            token_usage=42,
        )

    def decompose_requirement(self, requirement_id: str) -> LlmDecompositionResult:
        """Return a fixed decomposition result for the given requirement."""
        self._simulate()
        return LlmDecompositionResult(
            score=0.90,
            suggestions=[],
            provider=self.PROVIDER_NAME,
            model=self.MODEL_NAME,
            token_usage=100,
            children=[
                {"id": f"{requirement_id}-child-1", "title": "Mock child 1", "type": "sub-requirement"},
                {"id": f"{requirement_id}-child-2", "title": "Mock child 2", "type": "sub-requirement"},
            ],
        )

        )

    def check_consistency(self, workspace_id: str) -> LlmConsistencyResult:
        """Return a fixed consistency result for the given workspace."""
        self._simulate()
        return LlmConsistencyResult(
            score=0.95,
            suggestions=[],
            provider=self.PROVIDER_NAME,
            model=self.MODEL_NAME,
            token_usage=200,
            issues=[],
        )

    def derive_requirements(self, need_id: str) -> LlmDecompositionResult:
        """Return a fixed set of derived requirements for the given need."""
        self._simulate()
        return LlmDecompositionResult(
            score=0.92,
            suggestions=[],
            provider=self.PROVIDER_NAME,
            model=self.MODEL_NAME,
            token_usage=120,
            children=[
                {"id": f"{need_id}-derived-1", "title": "Mock Derived Requirement 1", "description": "System shall do X.", "type": "SyReq"},
                {"id": f"{need_id}-derived-2", "title": "Mock Derived Requirement 2", "description": "System shall do Y.", "type": "SyReq"},
            ],
        )


# ---------------------------------------------------------------------------
# Stub provider base — common HTTP plumbing for real providers
# ---------------------------------------------------------------------------


class _BaseHttpProvider(LlmCapabilityInterface):
    """Shared HTTP request helpers for real providers.

    Subclasses must set PROVIDER_NAME and MODEL_NAME and override the three
    abstract capability methods.
    """

    PROVIDER_NAME: str = ""
    MODEL_NAME: str = ""

    def __init__(self, config: ProviderConfig) -> None:
        self._config = config

    def _request(self, payload: dict) -> dict:
        """Execute an HTTP request with timeout handling.

        This stub is intended to be overridden by concrete providers. Real
        providers call their SDK or use requests/httpx here.

        Raises:
            TimeoutError: When the request exceeds the configured timeout.
            RuntimeError: On non-success HTTP responses.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__}._request() not implemented. "
            "Install the provider SDK and override this method."
        )


# ---------------------------------------------------------------------------
# Anthropic provider
# ---------------------------------------------------------------------------


class AnthropicProvider(_BaseHttpProvider):
    """LLM provider backed by Anthropic Claude (REQ-L3-LA002-001).

    Requires: pip install anthropic
    Env vars: LLM_API_KEY=<your-anthropic-key>
    """

    PROVIDER_NAME = "anthropic"
    MODEL_NAME = "claude-3-opus-20240229"

    def validate_artifact(self, artifact_id: str) -> LlmResult:
        """Call Anthropic API to validate an artifact."""
        try:
            import anthropic  # noqa: PLC0415 (lazy import intentional)

            client = anthropic.Anthropic(api_key=self._config.api_key)
            message = client.messages.create(
                model=self.MODEL_NAME,
                max_tokens=1024,
                timeout=self._config.timeout,
                messages=[
                    {
                        "role": "user",
                        "content": (
                            f"Validate artifact {artifact_id}. "
                            "Return a JSON object with keys: score (0-1), suggestions (list of strings)."
                        ),
                    }
                ],
            )
            import json

            raw = message.content[0].text
            data = json.loads(raw)
            token_usage = (
                message.usage.input_tokens + message.usage.output_tokens
                if hasattr(message, "usage")
                else None
            )
            return LlmResult(
                score=float(data.get("score", 0.0)),
                suggestions=data.get("suggestions", []),
                provider=self.PROVIDER_NAME,
                model=self.MODEL_NAME,
                token_usage=token_usage,
            )
        except ImportError as exc:
            raise RuntimeError(
                "anthropic SDK not installed. Run: pip install anthropic"
            ) from exc

    def decompose_requirement(self, requirement_id: str) -> LlmDecompositionResult:
        """Call Anthropic API to decompose a requirement."""
        try:
            import anthropic  # noqa: PLC0415

            client = anthropic.Anthropic(api_key=self._config.api_key)
            message = client.messages.create(
                model=self.MODEL_NAME,
                max_tokens=4096,
                timeout=self._config.timeout,
                messages=[
                    {
                        "role": "user",
                        "content": (
                            f"Decompose requirement {requirement_id} into sub-requirements. "
                            "Return JSON: {score, suggestions, children: [{id, title, type}]}"
                        ),
                    }
                ],
            )
            import json

            raw = message.content[0].text
            data = json.loads(raw)
            token_usage = (
                message.usage.input_tokens + message.usage.output_tokens
                if hasattr(message, "usage")
                else None
            )
            return LlmDecompositionResult(
                score=float(data.get("score", 0.0)),
                suggestions=data.get("suggestions", []),
                provider=self.PROVIDER_NAME,
                model=self.MODEL_NAME,
                token_usage=token_usage,
                children=data.get("children", []),
            )
        except ImportError as exc:
            raise RuntimeError(
                "anthropic SDK not installed. Run: pip install anthropic"
            ) from exc

    def check_consistency(self, workspace_id: str) -> LlmConsistencyResult:
        """Call Anthropic API to check workspace consistency."""
        try:
            import anthropic  # noqa: PLC0415

            client = anthropic.Anthropic(api_key=self._config.api_key)
            message = client.messages.create(
                model=self.MODEL_NAME,
                max_tokens=4096,
                timeout=self._config.timeout,
                messages=[
                    {
                        "role": "user",
                        "content": (
                            f"Check consistency for workspace {workspace_id}. "
                            "Return JSON: {score, suggestions, issues: [{id, severity, description}]}"
                        ),
                    }
                ],
            )
            import json

            raw = message.content[0].text
            data = json.loads(raw)
            token_usage = (
                message.usage.input_tokens + message.usage.output_tokens
                if hasattr(message, "usage")
                else None
            )
            return LlmConsistencyResult(
                score=float(data.get("score", 0.0)),
                suggestions=data.get("suggestions", []),
                provider=self.PROVIDER_NAME,
                model=self.MODEL_NAME,
                token_usage=token_usage,
                issues=data.get("issues", []),
            )
        except ImportError as exc:
            raise RuntimeError(
                "anthropic SDK not installed. Run: pip install anthropic"
            ) from exc


# ---------------------------------------------------------------------------
# OpenAI provider
# ---------------------------------------------------------------------------


class OpenAiProvider(_BaseHttpProvider):
    """LLM provider backed by OpenAI (REQ-L3-LA002-001).

    Requires: pip install openai
    Env vars: LLM_API_KEY=<your-openai-key>
    """

    PROVIDER_NAME = "openai"
    MODEL_NAME = "gpt-4"

    def _chat(self, prompt: str) -> tuple[str, Optional[int]]:
        """Send a chat completion request and return (text, token_usage)."""
        try:
            from openai import OpenAI  # noqa: PLC0415
        except ImportError as exc:
            raise RuntimeError(
                "openai SDK not installed. Run: pip install openai"
            ) from exc

        client = OpenAI(api_key=self._config.api_key, timeout=self._config.timeout)
        response = client.chat.completions.create(
            model=self.MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.choices[0].message.content or ""
        token_usage = (
            response.usage.total_tokens if response.usage else None
        )
        return text, token_usage

    def validate_artifact(self, artifact_id: str) -> LlmResult:
        import json

        text, token_usage = self._chat(
            f"Validate artifact {artifact_id}. Return JSON: {{score, suggestions}}"
        )
        data = json.loads(text)
        return LlmResult(
            score=float(data.get("score", 0.0)),
            suggestions=data.get("suggestions", []),
            provider=self.PROVIDER_NAME,
            model=self.MODEL_NAME,
            token_usage=token_usage,
        )

    def decompose_requirement(self, requirement_id: str) -> LlmDecompositionResult:
        import json

        text, token_usage = self._chat(
            f"Decompose requirement {requirement_id}. "
            "Return JSON: {score, suggestions, children: [{id, title, type}]}"
        )
        data = json.loads(text)
        return LlmDecompositionResult(
            score=float(data.get("score", 0.0)),
            suggestions=data.get("suggestions", []),
            provider=self.PROVIDER_NAME,
            model=self.MODEL_NAME,
            token_usage=token_usage,
            children=data.get("children", []),
        )

    def derive_requirements(self, need_id: str) -> LlmDecompositionResult:
        import json
        from persistence.models import StakeholderNeed
        
        need = StakeholderNeed.objects.select_related("artifact__workspace").get(id=need_id)
        
        # Get configured prompt if available
        workspace = need.artifact.workspace
        configured_prompt = getattr(workspace, "ai_prompts", {}).get("L0_L1")
        
        # We don't have direct access to architecture elements from StakeholderNeed here easily, 
        # but the request asks to pass it if available. 
        # For L0->L1 there are typically no architecture elements yet.
        
        if configured_prompt:
            prompt_text = (
                f"{configured_prompt}\n\n"
                f"Source Requirement (Need):\n"
                f"Title: {need.title}\n"
                f"Description: {getattr(need, 'description', '')}\n\n"
                "Return exactly JSON format: {\"children\": [{\"title\": \"System Req 1\", \"description\": \"Desc...\"}]}"
            )
        else:
            prompt_text = (
                f"Decompose Stakeholder Need {need.title} into System Requirements.\n"
                f"Need Description: {getattr(need, 'description', '')}\n"
                "Return exactly JSON format: {\"score\": 1.0, \"suggestions\": [], \"children\": [{\"title\": \"...\", \"description\": \"...\"}]}"
            )

        text, token_usage = self._chat(prompt_text)
        
        try:
            # Qwen or other LLMs might wrap JSON in markdown blocks
            text = text.replace("```json", "").replace("```", "").strip()
            data = json.loads(text)
        except json.JSONDecodeError:
            print(f"LLM returned invalid JSON: {text}")
            data = {"children": [{"title": "Generated Req", "description": text}]}
            
        return LlmDecompositionResult(
            score=float(data.get("score", 1.0)),
            suggestions=data.get("suggestions", []),
            provider=self.PROVIDER_NAME,
            model=self._model,
            token_usage=token_usage,
            children=data.get("children", []),
        )

    def check_consistency(self, workspace_id: str) -> LlmConsistencyResult:
        import json

        text, token_usage = self._chat(
            f"Check consistency for workspace {workspace_id}. "
            "Return JSON: {score, suggestions, issues: [{id, severity, description}]}"
        )
        data = json.loads(text)
        return LlmConsistencyResult(
            score=float(data.get("score", 0.0)),
            suggestions=data.get("suggestions", []),
            provider=self.PROVIDER_NAME,
            model=self.MODEL_NAME,
            token_usage=token_usage,
            issues=data.get("issues", []),
        )


# ---------------------------------------------------------------------------
# Ollama provider (local)
# ---------------------------------------------------------------------------


class OllamaProvider(_BaseHttpProvider):
    """LLM provider backed by a local Ollama instance (REQ-L3-LA002-001).

    Env vars:
        LLM_API_BASE_URL=http://localhost:11434  (default)
        LLM_MODEL=llama3  (overrides MODEL_NAME, optional)
    """

    PROVIDER_NAME = "ollama"
    MODEL_NAME = "llama3"
    DEFAULT_BASE_URL = "http://localhost:11434"

    def __init__(self, config: ProviderConfig) -> None:
        super().__init__(config)
        self._base_url = config.api_base_url or self.DEFAULT_BASE_URL
        self._model = os.environ.get("LLM_MODEL", self.MODEL_NAME)

    def _chat(self, prompt: str) -> tuple[str, Optional[int]]:
        """POST to Ollama /api/generate endpoint."""
        import json as _json

        try:
            import requests  # noqa: PLC0415
        except ImportError as exc:
            raise RuntimeError(
                "requests library not installed. Run: pip install requests"
            ) from exc

        url = f"{self._base_url}/api/generate"
        resp = requests.post(
            url,
            json={"model": self._model, "prompt": prompt, "stream": False},
            timeout=self._config.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        text = data.get("response", "")
        # Ollama does not expose token counts in the same format; use eval_count
        token_usage = data.get("eval_count") or None
        return text, token_usage

    def validate_artifact(self, artifact_id: str) -> LlmResult:
        import json

        text, token_usage = self._chat(
            f"Validate artifact {artifact_id}. Return JSON: {{score, suggestions}}"
        )
        data = json.loads(text)
        return LlmResult(
            score=float(data.get("score", 0.0)),
            suggestions=data.get("suggestions", []),
            provider=self.PROVIDER_NAME,
            model=self._model,
            token_usage=token_usage,
        )

    def decompose_requirement(self, requirement_id: str) -> LlmDecompositionResult:
        import json

        text, token_usage = self._chat(
            f"Decompose requirement {requirement_id}. "
            "Return JSON: {score, suggestions, children: [{id, title, type}]}"
        )
        data = json.loads(text)
        return LlmDecompositionResult(
            score=float(data.get("score", 0.0)),
            suggestions=data.get("suggestions", []),
            provider=self.PROVIDER_NAME,
            model=self._model,
            token_usage=token_usage,
            children=data.get("children", []),
        )

    def check_consistency(self, workspace_id: str) -> LlmConsistencyResult:
        import json

        text, token_usage = self._chat(
            f"Check consistency for workspace {workspace_id}. "
            "Return JSON: {score, suggestions, issues: [{id, severity, description}]}"
        )
        data = json.loads(text)
        return LlmConsistencyResult(
            score=float(data.get("score", 0.0)),
            suggestions=data.get("suggestions", []),
            provider=self.PROVIDER_NAME,
            model=self._model,
            token_usage=token_usage,
            issues=data.get("issues", []),
        )


# ---------------------------------------------------------------------------
# Azure OpenAI provider (REQ-L2-LA-007)
# ---------------------------------------------------------------------------


class AzureOpenAiProvider(_BaseHttpProvider):
    """LLM provider backed by Azure OpenAI (REQ-L2-LA-007, REQ-L3-LA002-001).

    Requires: pip install openai
    Env vars:
        LLM_API_KEY=<azure-api-key>
        LLM_API_BASE_URL=https://<resource>.openai.azure.com
        AZURE_OPENAI_DEPLOYMENT=<deployment-name>
        AZURE_OPENAI_API_VERSION=2024-02-01
    """

    PROVIDER_NAME = "azure"
    MODEL_NAME = "gpt-4"

    def _chat(self, prompt: str) -> tuple[str, Optional[int]]:
        """Send a chat completion request via Azure OpenAI endpoint."""
        try:
            from openai import AzureOpenAI  # noqa: PLC0415
        except ImportError as exc:
            raise RuntimeError(
                "openai SDK not installed. Run: pip install openai"
            ) from exc

        client = AzureOpenAI(
            api_key=self._config.api_key,
            azure_endpoint=self._config.api_base_url or "",
            azure_deployment=self._config.azure_deployment or "",
            api_version=self._config.azure_api_version or "2024-02-01",
            timeout=self._config.timeout,
        )
        response = client.chat.completions.create(
            model=self._config.azure_deployment or self.MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.choices[0].message.content or ""
        token_usage = response.usage.total_tokens if response.usage else None
        return text, token_usage

    def validate_artifact(self, artifact_id: str) -> LlmResult:
        import json

        text, token_usage = self._chat(
            f"Validate artifact {artifact_id}. Return JSON: {{score, suggestions}}"
        )
        data = json.loads(text)
        return LlmResult(
            score=float(data.get("score", 0.0)),
            suggestions=data.get("suggestions", []),
            provider=self.PROVIDER_NAME,
            model=self._config.azure_deployment or self.MODEL_NAME,
            token_usage=token_usage,
        )

    def decompose_requirement(self, requirement_id: str) -> LlmDecompositionResult:
        import json

        text, token_usage = self._chat(
            f"Decompose requirement {requirement_id}. "
            "Return JSON: {score, suggestions, children: [{id, title, type}]}"
        )
        data = json.loads(text)
        return LlmDecompositionResult(
            score=float(data.get("score", 0.0)),
            suggestions=data.get("suggestions", []),
            provider=self.PROVIDER_NAME,
            model=self._config.azure_deployment or self.MODEL_NAME,
            token_usage=token_usage,
            children=data.get("children", []),
        )

    def check_consistency(self, workspace_id: str) -> LlmConsistencyResult:
        import json

        text, token_usage = self._chat(
            f"Check consistency for workspace {workspace_id}. "
            "Return JSON: {score, suggestions, issues: [{id, severity, description}]}"
        )
        data = json.loads(text)
        return LlmConsistencyResult(
            score=float(data.get("score", 0.0)),
            suggestions=data.get("suggestions", []),
            provider=self.PROVIDER_NAME,
            model=self._config.azure_deployment or self.MODEL_NAME,
            token_usage=token_usage,
            issues=data.get("issues", []),
        )


# ---------------------------------------------------------------------------
# Plugin registry — REQ-L3-LA002-003
# ---------------------------------------------------------------------------

# Dict-based registry: maps provider_name -> provider class.
# New providers can be registered without touching the CapabilityRouter.
_PROVIDER_REGISTRY: Dict[str, Type[LlmCapabilityInterface]] = {
    "anthropic": AnthropicProvider,
    "openai": OpenAiProvider,
    "ollama": OllamaProvider,
    "azure": AzureOpenAiProvider,
    "mock": MockLlmProvider,
}


def register_provider(
    name: str,
) -> Callable[[Type[LlmCapabilityInterface]], Type[LlmCapabilityInterface]]:
    """Class decorator to register a new provider (REQ-L3-LA002-003).

    Usage::

        @register_provider("custom")
        class CustomProvider(LlmCapabilityInterface):
            ...

    Args:
        name: Provider name that users set via LLM_PROVIDER env var.

    Returns:
        Decorator that registers the class and returns it unchanged.
    """

    def _decorator(cls: Type[LlmCapabilityInterface]) -> Type[LlmCapabilityInterface]:
        _PROVIDER_REGISTRY[name] = cls
        return cls

    return _decorator


def get_provider(config: Optional[ProviderConfig] = None) -> LlmCapabilityInterface:
    """Instantiate and return the configured LLM provider (IF-LA-INT-002).

    Reads LLM_PROVIDER from the environment (or uses provided config).

    Args:
        config: Optional pre-built config; if None, reads env vars.

    Returns:
        An instance of the requested LlmCapabilityInterface implementation.

    Raises:
        LlmNotConfiguredError: If LLM_PROVIDER is not set.
        LlmProviderUnknownError: If LLM_PROVIDER names an unregistered provider.
    """
    cfg = config or _read_config()

    if not cfg.provider_name:
        raise LlmNotConfiguredError(
            "LLM_PROVIDER environment variable is not set. "
            "Set LLM_PROVIDER to one of: "
            + ", ".join(sorted(_PROVIDER_REGISTRY.keys()))
        )

    provider_cls = _PROVIDER_REGISTRY.get(cfg.provider_name)
    if provider_cls is None:
        raise LlmProviderUnknownError(
            f"Unknown LLM provider: {cfg.provider_name!r}. "
            "Registered providers: " + ", ".join(sorted(_PROVIDER_REGISTRY.keys()))
        )

    return provider_cls(cfg)  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# Domain exceptions
# ---------------------------------------------------------------------------


class LlmNotConfiguredError(Exception):
    """Raised when no LLM provider is configured (code: LLM_NOT_CONFIGURED)."""

    code: str = LLM_NOT_CONFIGURED


class LlmProviderUnknownError(Exception):
    """Raised when LLM_PROVIDER names an unknown provider (code: LLM_PROVIDER_UNKNOWN)."""

    code: str = LLM_PROVIDER_UNKNOWN


__all__ = [
    # Public API
    "get_provider",
    "register_provider",
    "ProviderConfig",
    # Provider implementations
    "MockLlmProvider",
    "AnthropicProvider",
    "OpenAiProvider",
    "OllamaProvider",
    "AzureOpenAiProvider",
    # Error codes
    "LLM_NOT_CONFIGURED",
    "LLM_PROVIDER_UNKNOWN",
    "LLM_PROVIDER_ERROR",
    # Exceptions
    "LlmNotConfiguredError",
    "LlmProviderUnknownError",
]
