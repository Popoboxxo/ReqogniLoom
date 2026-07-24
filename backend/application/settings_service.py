"""COMP-AS-SET SettingsService — LLM + PromptTemplate configuration (REQ-066).

Single entry point for the tenant-scoped configuration rows behind the
``/api/v1/llm-settings/`` and ``/api/v1/prompt-templates/`` endpoints. Moves the
``get_or_create`` / ``save`` ORM access out of ``rest_api/settings_views.py`` so
the REST layer stays free of direct ORM calls (Option B, REQ-066).

Behaviour is a faithful port of the previous view logic:

  - ``api_key`` on LlmSettings is write-only and only the whitelisted fields are
    ever mutated.
  - LlmSettings row is created on first access with ``provider=mock``.

PromptTemplate note (Phase 4 backward-compat, REQ-L2-PT-001): the persistence
model backing prompt templates was replaced (see ``persistence.models.
PromptTemplate``) with an open-ended, named/versioned, workspace-overridable
model -- it no longer has a single tenant-singleton row with three fixed
fields. The REST contract at ``/api/v1/prompt-templates/`` is intentionally
kept unchanged for the 3 original slot names
(``need_to_sysreq``/``sysreq_to_arch_assign``/``sysreq_decompose_next_level``):
this service reads/writes only the **tenant-global** rows (``workspace_id=
None``) for those 3 names and presents them as a single flat object, mirroring
the old response shape. New template names and workspace-level overrides are
intentionally NOT exposed here -- those are MCP-only (see
``mcp_server/tools/prompt_template.py``).

Permission enforcement (admin-only) stays in the view layer so the exact 403
messages are preserved; this service only owns persistence.

req_id: REQ-066, REQ-L2-LLM-001, REQ-L2-PT-001
leaf_id: COMP-AS-SET
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from django.db import IntegrityError

from auth_tenancy.context import AuthContext
from persistence.models import (
    PROMPT_TEMPLATE_DEFAULTS,
    LlmProvider,
    LlmSettings,
    PromptTemplate,
)

from application.base import ServiceBase, ValidationError
from application.prompt_template_versioning import publish_new_version

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

    # ---- PromptTemplate -----------------------------------------------
    #
    # REST backward-compat facade (Phase 4, REQ-L2-PT-001): reads/writes only
    # the tenant-global (workspace_id=None) rows for the 3 original slot
    # names, and presents them as one flat object -- the shape the REST
    # contract has always exposed. See module docstring for the full
    # rationale.

    def _effective_prompt_template(self, ctx: AuthContext) -> SimpleNamespace:
        """Return the effective content of the 3 original slots as one object.

        For each slot: the tenant-global active row's content if one exists,
        else the factory default. Read-only -- never creates a row, since a
        slot with no active row already has a well-defined effective value
        (the factory default).
        """
        self._set_tenant_context(ctx)
        values: dict[str, str] = {}
        for slot in _PROMPT_SLOT_FIELDS:
            row = PromptTemplate.objects.filter(
                tenant_id=ctx.tenant_id,
                workspace_id=None,
                name=slot,
                is_active=True,
            ).first()
            values[slot] = row.content if row is not None else PROMPT_TEMPLATE_DEFAULTS[slot]
        return SimpleNamespace(**values)

    def get_or_create_prompt_template(self, ctx: AuthContext) -> SimpleNamespace:
        """Return the effective (tenant-global) prompt-template content.

        Named ``get_or_create`` for continuity with the pre-Phase-4 API
        surface; despite the name it never creates a row (see
        ``_effective_prompt_template``) -- a GET is a read, and "the row
        doesn't exist yet" already has a well-defined answer (the default).
        """
        return self._effective_prompt_template(ctx)

    def update_prompt_template(
        self, ctx: AuthContext, validated_data: dict[str, Any]
    ) -> SimpleNamespace:
        """Publish a new tenant-global version for each slot in ``validated_data``.

        Only the slots present in ``validated_data`` are touched (partial
        update semantics identical to the pre-Phase-4 behaviour); untouched
        slots keep whatever their current effective value is.
        """
        self._set_tenant_context(ctx)
        for slot in _PROMPT_SLOT_FIELDS:
            if slot in validated_data:
                try:
                    publish_new_version(
                        tenant_id=ctx.tenant_id,
                        name=slot,
                        content=validated_data[slot],
                        workspace_id=None,
                    )
                except IntegrityError as exc:
                    # A concurrent writer for the same scope committed first;
                    # PromptTemplate.save()'s own mutex rejected our attempt
                    # to activate a second row for this scope (mirrors the
                    # same IntegrityError -> ValidationError translation used
                    # by mcp_server/tools/prompt_template.py and
                    # custom_field_service.py).
                    raise ValidationError(
                        f"Could not publish a new version for '{slot}': {exc}"
                    ) from exc
        return self._effective_prompt_template(ctx)

    def reset_prompt_template(
        self, ctx: AuthContext, slot: str | None = None
    ) -> SimpleNamespace:
        """Reset one slot (``slot``) or all slots to their factory defaults.

        A slot with no active tenant-global row is already at its factory
        default (see ``_effective_prompt_template``), so resetting it is a
        no-op -- only slots that were actually customised get a new version
        published. This keeps "reset" from manufacturing rows (and version
        history) for slots nobody ever touched.
        """
        self._set_tenant_context(ctx)
        slots = (slot,) if slot is not None else _PROMPT_SLOT_FIELDS
        for name in slots:
            has_active_override = PromptTemplate.objects.filter(
                tenant_id=ctx.tenant_id,
                workspace_id=None,
                name=name,
                is_active=True,
            ).exists()
            if has_active_override:
                try:
                    publish_new_version(
                        tenant_id=ctx.tenant_id,
                        name=name,
                        content=PROMPT_TEMPLATE_DEFAULTS[name],
                        workspace_id=None,
                    )
                except IntegrityError as exc:
                    # See the same handling in update_prompt_template above.
                    raise ValidationError(
                        f"Could not reset '{name}' to its factory default: {exc}"
                    ) from exc
        return self._effective_prompt_template(ctx)


__all__ = ["SettingsService"]
