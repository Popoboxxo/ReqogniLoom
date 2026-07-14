"""
COMP-LA-001 CapabilityInterface — Stable abstract LLM interface and result dataclasses.

Leaf node: ARCH-L1-009 / LlmAdapterSystem / COMP-LA-001
REQ-IDs: REQ-L2-LA-001, REQ-L2-LA-004, REQ-L3-LA001-001, REQ-L3-LA001-002, REQ-L3-LA001-003

Architecture:
    docs/se/L1/Gesamtsystem/L2/LlmAdapterSystem/Components/
    COMP-LA-001_CapabilityInterface/L3_COMP-LA-001_CapabilityInterface_Architecture.md

Interface contract (IF-LA-INT-003):
    Provider classes in COMP-LA-002 inherit from LlmCapabilityInterface and must
    implement all three abstract methods.

Provider isolation:
    No provider SDK is imported here. This module is importable without any
    provider library installed (REQ-L3-LA001-003).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional


# ---------------------------------------------------------------------------
# Result dataclasses — REQ-L3-LA001-002 / REQ-L2-LA-004
# ---------------------------------------------------------------------------


@dataclass
class LlmResult:
    """Standard result object returned by validate_artifact.

    Attributes:
        score: Confidence score in range [0.0, 1.0]. ValueError raised if outside.
        suggestions: List of textual suggestions from the LLM.
        provider: Provider name (e.g. "anthropic", "openai", "ollama", "azure").
        model: Model identifier (e.g. "claude-3-opus", "gpt-4").
        token_usage: Total token count consumed or None if unavailable.
    """

    score: float
    suggestions: List[str]
    provider: str
    model: str
    token_usage: Optional[int]

    def __post_init__(self) -> None:
        """Validate score range after initialisation (REQ-L3-LA001-002)."""
        if not (0.0 <= self.score <= 1.0):
            raise ValueError(
                f"LlmResult.score must be in [0.0, 1.0], got {self.score!r}"
            )


@dataclass
class LlmDecompositionResult(LlmResult):
    """Result object returned by decompose_requirement.

    Extends LlmResult with a list of decomposed child items.

    Attributes:
        children: List of decomposed sub-items, each a dict with keys such as
                  id, title, type, and description.
    """

    children: List[dict] = field(default_factory=list)


@dataclass
class LlmConsistencyResult(LlmResult):
    """Result object returned by check_consistency.

    Extends LlmResult with a list of identified consistency issues.

    Attributes:
        issues: List of consistency issues, each a dict with keys such as
                id, severity, and description.
    """

    issues: List[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Abstract base class — REQ-L3-LA001-001 / REQ-L2-LA-001
# ---------------------------------------------------------------------------


class LlmCapabilityInterface(ABC):
    """Abstract base class for all LLM provider implementations.

    Defines the stable contract that every provider must fulfil. No business
    module may depend on a concrete provider type — all callers reference only
    this interface (REQ-L2-LA-001, ADR-02).

    Interface relationships:
        IF-LA-INT-003 (outgoing from COMP-LA-002): provider classes inherit this.
        IF-LA-INT-001 (incoming from COMP-LA-003): CapabilityRouter calls methods.
    """

    @abstractmethod
    def validate_artifact(
        self,
        artifact_id: str,
        *,
        title: Optional[str] = None,
        content: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> LlmResult:
        """Validate a single artifact using the LLM.

        The caller (application layer) is responsible for fetching the artifact
        and passing its ``title`` / ``content`` so the provider can embed the
        real text into the prompt instead of only the opaque identifier
        (REQ-046). ``title`` / ``content`` are optional to preserve backward
        compatibility; when omitted the provider falls back to an id-only
        prompt.

        Args:
            artifact_id: Identifier of the artifact to validate.
            title: Optional artifact title to embed into the prompt.
            content: Optional artifact body/description to embed into the prompt.
            timeout: Optional per-call timeout in seconds (REQ-084). ``None``
                falls back to the provider's configured timeout.

        Returns:
            LlmResult containing score, suggestions, and usage metadata.
        """

    @abstractmethod
    def decompose_requirement(
        self,
        requirement_id: str,
        *,
        title: Optional[str] = None,
        content: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> LlmDecompositionResult:
        """Decompose a requirement into child items using the LLM.

        The caller (application layer) passes the requirement ``title`` /
        ``content`` so the provider embeds the real text into the prompt
        instead of only the opaque identifier (REQ-046). Both are optional to
        preserve backward compatibility.

        Args:
            requirement_id: Identifier of the requirement to decompose.
            title: Optional requirement title to embed into the prompt.
            content: Optional requirement body/description to embed into the
                prompt.
            timeout: Optional per-call timeout in seconds (REQ-084). ``None``
                falls back to the provider's configured timeout.

        Returns:
            LlmDecompositionResult with children list and usage metadata.
        """

    @abstractmethod
    def check_consistency(
        self,
        workspace_id: str,
        *,
        artifacts: Optional[List[dict]] = None,
        timeout: Optional[float] = None,
    ) -> LlmConsistencyResult:
        """Check consistency across all artifacts in a workspace.

        The caller (application layer) passes an ``artifacts`` summary (each a
        ``{"id", "title", "content"}`` dict) so the provider embeds the real
        artifact text into the prompt instead of only the workspace identifier
        (REQ-046). ``artifacts`` is optional to preserve backward
        compatibility.

        Args:
            workspace_id: Identifier of the workspace to check.
            artifacts: Optional list of artifact summary dicts to embed.
            timeout: Optional per-call timeout in seconds (REQ-084). ``None``
                falls back to the provider's configured timeout.

        Returns:
            LlmConsistencyResult with issues list and usage metadata.
        """

    @abstractmethod
    def derive_requirements(
        self,
        need_id: str,
        *,
        timeout: Optional[float] = None,
    ) -> LlmDecompositionResult:
        """Derive System Requirements from a Stakeholder Need.

        Args:
            need_id: Identifier of the stakeholder need to derive from.
            timeout: Optional per-call timeout in seconds (REQ-084). ``None``
                falls back to the provider's configured timeout.

        Returns:
            LlmDecompositionResult with derived requirements.
        """

    @abstractmethod
    def complete(
        self,
        prompt: str,
        *,
        purpose: str = "",
        context: Optional[dict] = None,
        timeout: Optional[float] = None,
    ) -> str:
        """Return the raw completion text for a free-form prompt (REQ-L2-AI-002).

        Provides a stable static contract for the free-form completion
        capability already offered by the concrete providers (REQ-048).

        Args:
            prompt: Free-form prompt sent to the underlying model.
            purpose: Optional hint used by deterministic mocks; real
                providers may ignore it.
            context: Optional structured context; real providers may ignore it.
            timeout: Optional per-call timeout in seconds (REQ-084). ``None``
                falls back to the provider's configured timeout.

        Returns:
            The raw completion text produced by the model.
        """


__all__ = [
    "LlmCapabilityInterface",
    "LlmResult",
    "LlmDecompositionResult",
    "LlmConsistencyResult",
]
