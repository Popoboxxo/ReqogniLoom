"""COMP-AS-SET SettingsService — LLM + PromptTemplate configuration (REQ-066).

Single entry point for the tenant-scoped singleton configuration rows behind the
``/api/v1/llm-settings/`` and ``/api/v1/prompt-templates/`` endpoints. Moves the
``get_or_create`` / ``save`` ORM access out of ``rest_api/settings_views.py`` so
the REST layer stays free of direct ORM calls (Option B, REQ-066).

Behaviour is a faithful port of the previous view logic:

  - ``api_key`` on LlmSettings is write-only and only the whitelisted fields are
    ever mutated.
  - Both rows are created on first access with ``provider=mock`` / factory
    prompt defaults.

Permission enforcement (admin-only) stays in the view layer so the exact 403
messages are preserved; this service only owns persistence.

req_id: REQ-066, REQ-L2-LLM-001, REQ-L2-PT-001
leaf_id: COMP-AS-SET
"""
from __future__ import annotations

from typing import Any

from auth_tenancy.context import AuthContext
from persistence.models import (
    PROMPT_TEMPLATE_DEFAULTS,
    LlmProvider,
    LlmSettings,
    PromptTemplate,
)

from application.base import ServiceBase

# Fields a client may write onto the LlmSettings row.
_LLM_WRITABLE_FIELDS = ("provider", "base_url", "model_name", "api_key")

# Writable prompt slots (also the valid ``slot`` names for a targeted reset).
_PROMPT_SLOT_FIELDS = (
    "need_to_sysreq",
    "sysreq_to_arch_assign",
    "sysreq_decompose_next_level",
)


class SettingsService(ServiceBase):
    """Tenant-scoped LLM + PromptTemplate configuration facade (REQ-066)."""

    # ---- Static choice/default surfaces (for serializer definitions) ------

    @staticmethod
    def provider_choices() -> list[str]:
        """Return valid LLM provider choice values (for serializer ChoiceField)."""
        return list(LlmProvider.values)

    @staticmethod
    def prompt_defaults() -> dict[str, str]:
        """Return the factory prompt-template defaults (read-only copy)."""
        return dict(PROMPT_TEMPLATE_DEFAULTS)

    @staticmethod
    def is_valid_prompt_slot(slot: str) -> bool:
        """Return whether ``slot`` is a known resettable prompt slot."""
        return slot in PROMPT_TEMPLATE_DEFAULTS

    # ---- LlmSettings ------------------------------------------------------

    def get_or_create_llm_settings(self, ctx: AuthContext) -> LlmSettings:
        """Return the tenant's singleton LlmSettings row, creating it if absent."""
        self._set_tenant_context(ctx)
        obj, _ = LlmSettings.objects.get_or_create(
            tenant_id=ctx.tenant_id,
            defaults={"provider": LlmProvider.MOCK},
        )
        return obj

    def update_llm_settings(
        self, ctx: AuthContext, validated_data: dict[str, Any]
    ) -> LlmSettings:
        """Apply whitelisted ``validated_data`` to the LlmSettings row and save."""
        obj = self.get_or_create_llm_settings(ctx)
        for field in _LLM_WRITABLE_FIELDS:
            if field in validated_data:
                setattr(obj, field, validated_data[field])
        obj.save()
        return obj

    # ---- PromptTemplate ---------------------------------------------------

    def get_or_create_prompt_template(self, ctx: AuthContext) -> PromptTemplate:
        """Return the tenant's singleton PromptTemplate row, creating if absent."""
        self._set_tenant_context(ctx)
        obj, _ = PromptTemplate.objects.get_or_create(tenant_id=ctx.tenant_id)
        return obj

    def update_prompt_template(
        self, ctx: AuthContext, validated_data: dict[str, Any]
    ) -> PromptTemplate:
        """Apply writable slot fields from ``validated_data`` and save."""
        obj = self.get_or_create_prompt_template(ctx)
        for field in _PROMPT_SLOT_FIELDS:
            if field in validated_data:
                setattr(obj, field, validated_data[field])
        obj.save()
        return obj

    def reset_prompt_template(
        self, ctx: AuthContext, slot: str | None = None
    ) -> PromptTemplate:
        """Reset one slot (``slot``) or all slots to factory defaults and save."""
        obj = self.get_or_create_prompt_template(ctx)
        if slot is not None:
            obj.reset_slot(slot)
        else:
            obj.reset_all()
        obj.save()
        return obj


__all__ = ["SettingsService"]
