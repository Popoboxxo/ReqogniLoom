"""
COMP-AS-021 AiDerivationService — LLM-backed draft generation (REQ-L2-AI-001/002).

This service implements three *explicit, user-triggered* AI derivation flows.
Every flow follows the **Draft/Accept** pattern (REQ-L2-AI-001):

  * The service only ever returns proposed data ("drafts"). Nothing is
    persisted here.
  * "Accepting" a draft is the client's responsibility — it re-uses the
    existing create/update REST endpoints to persist whichever drafts the
    user selected.

Flows (REQ-L2-AI-002):
  1. :meth:`derive_requirements_from_need` — StakeholderNeed -> SystemRequirements
  2. :meth:`suggest_architecture_for_requirement` — Requirement -> ArchitectureElement ids
  3. :meth:`decompose_requirement_next_level` — Requirement -> next-level requirement drafts

LLM access goes through the ``llm_adapter`` provider registry. The default
provider is ``mock`` (credential-free, deterministic) so the flows and their
tests run without network access. Prompt text is sourced from the tenant's
:class:`~persistence.models.PromptTemplate` row, falling back to the module-level
``PROMPT_TEMPLATE_DEFAULTS`` when no row exists yet.

Architecture:
  docs/se/L1/Gesamtsystem/L2/ApplicationServiceSystem/
    L2_ApplicationServiceSystem_Architecture.md (ADR-AS-01, single entry point)
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from auth_tenancy.context import AuthContext
from persistence.models import (
    PROMPT_TEMPLATE_DEFAULTS,
    ArchitectureElement,
    PromptTemplate,
    Requirement,
    StakeholderNeed,
    TraceLink,
)
from traceability.types import LinkType

from application.base import NotFoundError, ServiceBase, ValidationError

logger = logging.getLogger(__name__)

# Prefix stamped onto completions that were served by the mock provider after a
# real provider failed (REQ-078). Callers can test for it to warn the user that
# the content is a deterministic placeholder, not a genuine LLM answer.
MOCK_FALLBACK_MARKER = "[MOCK FALLBACK] "


class LlmResponseError(RuntimeError):
    """Raised when the LLM returns a response that cannot be parsed as JSON.

    Maps to HTTP 500 in the REST layer and to an INTERNAL_ERROR ToolResult in
    the MCP layer — the request itself was valid, but the provider misbehaved.
    """


class AiDerivationService(ServiceBase):
    """LLM-backed, draft-only derivation flows (REQ-L2-AI-001, REQ-L2-AI-002)."""

    # ------------------------------------------------------------------
    # Public flows
    # ------------------------------------------------------------------

    def derive_requirements_from_need(
        self,
        ctx: AuthContext,
        stakeholder_need_id: UUID | str,
        n: int = 3,
    ) -> Dict[str, Any]:
        """Flow 1: propose ``n`` system requirements for a stakeholder need.

        Args:
            ctx: Authenticated, tenant-scoped context.
            stakeholder_need_id: Source stakeholder need.
            n: Number of requirement drafts to request (clamped to >= 1).

        Returns:
            ``{"drafts": [{title, description, rationale, suggested_parent_id}]}``.

        Raises:
            NotFoundError: The stakeholder need does not exist for this tenant.
            LlmResponseError: The provider returned non-JSON content.
        """
        self._set_tenant_context(ctx)
        count = max(1, int(n))

        need = (
            StakeholderNeed.objects.select_related("artifact")
            .filter(id=stakeholder_need_id)
            .first()
        )
        if need is None:
            raise NotFoundError(f"StakeholderNeed {stakeholder_need_id} not found")

        template = self._get_slot(ctx, "need_to_sysreq")
        prompt = self._render(
            template,
            n=count,
            need_title=need.title,
            need_description=need.description or "",
        )

        raw = self._complete(
            prompt, purpose="need_to_sysreq", context={"n": count}
        )
        items = self._parse_json_list(raw)

        drafts = [
            {
                "title": str(item.get("title", "")),
                "description": str(item.get("description", "")),
                "rationale": str(item.get("rationale", "")),
                "suggested_parent_id": str(need.id),
            }
            for item in items
            if isinstance(item, dict)
        ]
        return {"drafts": drafts}

    def suggest_architecture_for_requirement(
        self,
        ctx: AuthContext,
        requirement_id: UUID | str,
    ) -> Dict[str, Any]:
        """Flow 2: suggest architecture elements to satisfy a requirement.

        Only meaningful while the requirement is unassigned: if an
        ``allocated-to`` link already exists a :class:`ValidationError` is
        raised (mapped to HTTP 400).

        Args:
            ctx: Authenticated, tenant-scoped context.
            requirement_id: Requirement to find responsible elements for.

        Returns:
            ``{"suggested_arch_element_ids": [<uuid-str>, ...]}``.

        Raises:
            NotFoundError: The requirement does not exist for this tenant.
            ValidationError: The requirement is already allocated.
            LlmResponseError: The provider returned non-JSON content.
        """
        self._set_tenant_context(ctx)

        req = self._get_requirement(requirement_id)

        if self._allocated_target_ids(req):
            raise ValidationError(
                "Requirement is already assigned to an architecture element."
            )

        workspace_id = req.artifact.workspace_id
        arch_elements = list(
            ArchitectureElement.objects.select_related("artifact").filter(
                artifact__workspace_id=workspace_id
            )
        )
        arch_payload = [
            {
                "id": str(ae.id),
                "name": ae.title,
                "description": ae.description or "",
            }
            for ae in arch_elements
        ]
        available_ids = {entry["id"] for entry in arch_payload}

        template = self._get_slot(ctx, "sysreq_to_arch_assign")
        prompt = self._render(
            template,
            req_title=req.title,
            req_description=req.description or "",
            arch_elements_json=json.dumps(arch_payload),
        )

        raw = self._complete(
            prompt,
            purpose="sysreq_to_arch_assign",
            context={"arch_element_ids": [entry["id"] for entry in arch_payload]},
        )
        suggested = self._parse_json_list(raw)

        # Keep only ids the LLM was actually offered (defensive against
        # hallucinated identifiers).
        result_ids = [
            str(item)
            for item in suggested
            if isinstance(item, (str, int)) and str(item) in available_ids
        ]
        return {"suggested_arch_element_ids": result_ids}

    def decompose_requirement_next_level(
        self,
        ctx: AuthContext,
        requirement_id: UUID | str,
    ) -> Dict[str, Any]:
        """Flow 3: propose next-level requirement drafts for a requirement.

        Requires at least one ``allocated-to`` architecture element; otherwise a
        :class:`ValidationError` is raised (mapped to HTTP 400).

        Args:
            ctx: Authenticated, tenant-scoped context.
            requirement_id: Parent requirement to decompose.

        Returns:
            ``{"drafts": [{title, description, rationale,
            suggested_arch_element_id}], "parent_requirement_id": <uuid-str>}``.

        Raises:
            NotFoundError: The requirement does not exist for this tenant.
            ValidationError: The requirement has no allocated architecture element.
            LlmResponseError: The provider returned non-JSON content.
        """
        self._set_tenant_context(ctx)

        req = self._get_requirement(requirement_id)

        target_ids = self._allocated_target_ids(req)
        if not target_ids:
            raise ValidationError(
                "Requirement must be assigned to at least one architecture "
                "element before it can be decomposed."
            )

        arch_elements = list(
            ArchitectureElement.objects.filter(artifact_id__in=target_ids)
        )
        arch_payload = [
            {
                "id": str(ae.id),
                "name": ae.title,
                "description": ae.description or "",
            }
            for ae in arch_elements
        ]

        template = self._get_slot(ctx, "sysreq_decompose_next_level")
        prompt = self._render(
            template,
            req_title=req.title,
            req_description=req.description or "",
            arch_elements_json=json.dumps(arch_payload),
        )

        raw = self._complete(
            prompt,
            purpose="sysreq_decompose_next_level",
            context={"arch_element_ids": [entry["id"] for entry in arch_payload]},
        )
        items = self._parse_json_list(raw)

        drafts = [
            {
                "title": str(item.get("title", "")),
                "description": str(item.get("description", "")),
                "rationale": str(item.get("rationale", "")),
                "suggested_arch_element_id": (
                    str(item["suggested_arch_element_id"])
                    if item.get("suggested_arch_element_id") is not None
                    else None
                ),
            }
            for item in items
            if isinstance(item, dict)
        ]
        return {
            "drafts": drafts,
            "parent_requirement_id": str(req.id),
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_requirement(self, requirement_id: UUID | str) -> Requirement:
        """Return a tenant-scoped Requirement or raise NotFoundError."""
        req = (
            Requirement.objects.select_related("artifact")
            .filter(id=requirement_id)
            .first()
        )
        if req is None:
            raise NotFoundError(f"Requirement {requirement_id} not found")
        return req

    @staticmethod
    def _allocated_target_ids(req: Requirement) -> List[UUID]:
        """Return the artifact ids this requirement is ``allocated-to``."""
        links = TraceLink.objects.filter(
            source_id=req.artifact_id,
            link_type=LinkType.ALLOCATED_TO.value,
        ).values_list("target_id", flat=True)
        return list(links)

    @staticmethod
    def _get_slot(ctx: AuthContext, slot: str) -> str:
        """Return the tenant's prompt content for *slot* (or the factory default).

        The default manager is already tenant-scoped by the active
        TenantContext, so a plain ``.filter().first()`` is sufficient.
        """
        row = PromptTemplate.objects.filter(tenant_id=ctx.tenant_id).first()
        if row is not None:
            return row.get_slot(slot)
        return PROMPT_TEMPLATE_DEFAULTS[slot]

    @staticmethod
    def _render(template: str, **values: Any) -> str:
        """Substitute ``{name}`` placeholders without touching other braces.

        A literal ``str.format`` call would choke on JSON braces embedded in a
        user-customised prompt, so placeholders are replaced individually.
        """
        rendered = template
        for key, value in values.items():
            rendered = rendered.replace("{" + key + "}", str(value))
        return rendered

    def _complete(
        self,
        prompt: str,
        *,
        purpose: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Run the configured provider's free-form completion.

        Falls back to the credential-free mock provider when no provider is
        configured, so the flows degrade to deterministic output instead of
        failing hard (REQ-L2-AI-002; default provider is ``mock``).
        """
        from django.conf import settings

        from llm_adapter.providers import (
            LlmNotConfiguredError,
            LlmProviderUnknownError,
            MockLlmProvider,
            get_provider,
        )

        try:
            provider = get_provider()
        except (LlmNotConfiguredError, LlmProviderUnknownError) as error:
            # Silent degradation hides that the caller is looking at mock output
            # instead of a real LLM answer (REQ-078). Emit a WARNING and tag the
            # response so downstream code / the UI can flag it to the user.
            provider_name = getattr(settings, "LLM_PROVIDER", "unknown")
            logger.warning(
                "LLM provider %s failed, falling back to mock. Error: %s",
                provider_name,
                error,
            )
            result = MockLlmProvider().complete(
                prompt, purpose=purpose, context=context
            )
            return f"{MOCK_FALLBACK_MARKER}{result}"

        return provider.complete(prompt, purpose=purpose, context=context)

    @staticmethod
    def _parse_json_list(raw: str) -> List[Any]:
        """Parse *raw* into a JSON list, tolerating Markdown code fences.

        Raises:
            LlmResponseError: When *raw* is not valid JSON or not a list.
        """
        text = raw.strip()
        # Strip the mock-fallback marker (REQ-078) so a degraded response still
        # parses; the marker is only a user-facing signal, not part of the JSON.
        if text.startswith(MOCK_FALLBACK_MARKER):
            text = text[len(MOCK_FALLBACK_MARKER):].strip()
        if text.startswith("```"):
            # Strip a leading ```json / ``` fence and the trailing ```.
            text = text.replace("```json", "").replace("```", "").strip()
        try:
            parsed = json.loads(text)
        except (json.JSONDecodeError, TypeError) as exc:
            raise LlmResponseError(
                "The LLM response was not valid JSON."
            ) from exc
        if not isinstance(parsed, list):
            raise LlmResponseError(
                "The LLM response was not a JSON array as expected."
            )
        return parsed


__all__ = ["AiDerivationService", "LlmResponseError", "MOCK_FALLBACK_MARKER"]
