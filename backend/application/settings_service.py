"""COMP-AS-SET SettingsService — LLM + PromptTemplate configuration (REQ-066).

Single entry point for the tenant-scoped configuration rows behind the
``/api/v1/llm-settings/`` and ``/api/v1/prompt-templates/`` endpoints. Moves the
``get_or_create`` / ``save`` ORM access out of ``rest_api/settings_views.py`` so
the REST layer stays free of direct ORM calls (Option B, REQ-066).

Behaviour is a faithful port of the previous view logic:

  - ``api_key`` on LlmSettings is write-only and only the whitelisted fields are
    ever mutated.
  - The LlmSettings row is created on first *write*, defaulting ``provider``
    to the ``LLM_PROVIDER`` environment variable if set to a valid choice,
    otherwise ``mock`` (GitHub #32). Reads never create it: the row's mere
    existence overrides the environment in the LLM adapter, so materialising
    one on a GET pinned the provider forever (issue #276).

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

import os
from types import SimpleNamespace
from typing import Any
from uuid import UUID

from django.db import IntegrityError

from auth_tenancy.context import AuthContext
from persistence.models import (
    PROMPT_TEMPLATE_DEFAULTS,
    REVIEW_POLICY_MODES,
    LlmProvider,
    LlmSettings,
    PromptTemplate,
    ReviewPolicy,
)
from presets.registry import TIER_EXTENDED

from application.base import ServiceBase, ValidationError
from application.prompt_template_versioning import (
    deactivate_scope,
    get_active_template,
    list_active_templates,
    publish_new_version,
)

# Fields a client may write onto the LlmSettings row.
_LLM_WRITABLE_FIELDS = ("provider", "base_url", "model_name", "api_key")

# Writable prompt slots (also the valid ``slot`` names for a targeted reset).
_PROMPT_SLOT_FIELDS = (
    "need_to_sysreq",
    "sysreq_to_arch_assign",
    "sysreq_decompose_next_level",
    "goal_aggregate",
)


def _env_default_provider() -> str:
    """Return the LLM provider a freshly created tenant should default to.

    GitHub #32: the tenant's :class:`LlmSettings` row is created lazily
    on first access to ``/api/v1/llm-settings/``. Hard-coding
    ``provider=mock`` here meant a deployment that configures a real
    provider via the ``LLM_PROVIDER`` environment variable (see
    ``docker-compose.yml``) still reported/used ``mock`` until an admin
    manually edited the settings once through the UI/API — the endpoint
    never reflected the actually configured provider.

    Falls back to ``mock`` when ``LLM_PROVIDER`` is unset or not a valid
    choice, preserving the previous safe default.
    """
    candidate = os.environ.get("LLM_PROVIDER", "").strip().lower()
    if candidate in LlmProvider.values:
        return candidate
    return LlmProvider.MOCK


def _env_base_url() -> str:
    """Return the base URL the adapter resolves from the environment.

    Both spellings are accepted, matching
    ``llm_adapter.providers._read_env_config`` (issue #276): the compose files
    pass ``LLM_BASE_URL``, while ``LLM_API_BASE_URL`` is the historical name
    and keeps precedence.
    """
    return (
        os.environ.get("LLM_API_BASE_URL")
        or os.environ.get("LLM_BASE_URL")
        or ""
    )


def _env_model_name() -> str:
    """Return the model id the adapter resolves from the environment (#276)."""
    return (
        os.environ.get("LLM_MODEL_NAME") or os.environ.get("LLM_MODEL") or ""
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

    @staticmethod
    def review_policy_modes() -> list[str]:
        """Return valid ReviewPolicy mode choice values (for serializer ChoiceField)."""
        return list(REVIEW_POLICY_MODES)

    # ---- LlmSettings ------------------------------------------------------

    def get_llm_settings(self, ctx: AuthContext) -> LlmSettings:
        """Return the tenant's LLM settings for reading — WITHOUT persisting.

        When the tenant has no stored row this returns an **unsaved**
        instance mirroring the effective environment configuration, so the
        caller sees what the adapter actually uses.

        Issue #276: this used to be a ``get_or_create``, which meant merely
        opening the settings page wrote a row — and
        ``llm_adapter.providers._apply_db_settings`` gives an existing row
        unconditional precedence over the environment. The deployment's
        ``LLM_PROVIDER`` was thereby frozen into the database on first read
        and every later ``.env`` change became a silent no-op. Keeping reads
        side-effect free is what makes "a row exists" mean "an admin
        explicitly configured this tenant".
        """
        self._set_tenant_context(ctx)
        obj = LlmSettings.objects.filter(tenant_id=ctx.tenant_id).first()
        if obj is not None:
            return obj
        return LlmSettings(
            tenant_id=ctx.tenant_id,
            provider=_env_default_provider(),
            base_url=_env_base_url(),
            model_name=_env_model_name(),
            api_key=os.environ.get("LLM_API_KEY", ""),
        )

    def get_or_create_llm_settings(self, ctx: AuthContext) -> LlmSettings:
        """Return the tenant's singleton LlmSettings row, creating it if absent.

        Write path only — creating the row is an explicit act of configuration
        (see :meth:`get_llm_settings` for why reads must not create one).
        """
        self._set_tenant_context(ctx)
        obj, _ = LlmSettings.objects.get_or_create(
            tenant_id=ctx.tenant_id,
            defaults={
                # Seed from the environment so the first write does not
                # silently drop the configuration already in effect — a PATCH
                # touching a single field must not leave the row internally
                # inconsistent (e.g. provider=ollama with a blank base_url).
                # The api_key is deliberately NOT copied: a secret is never
                # duplicated into a second store implicitly; an unset
                # ``api_key`` on the row keeps LLM_API_KEY as the fallback.
                "provider": _env_default_provider(),
                "base_url": _env_base_url(),
                "model_name": _env_model_name(),
            },
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

    # ---- PromptTemplate slots (issue #119) --------------------------------
    #
    # The flat facade above is deliberately frozen at its historical shape:
    # 4 slots, tenant-global scope only. That is exactly the gap issue #119
    # reports -- the 4 further slots the AI-derivation flows use
    # (``testcase_derive``, ``architecture_to_risk``, ``workspace_to_glossary``,
    # ``decision_to_adr``) were unreachable from REST, and workspace-level
    # overrides -- which ``AiDerivationService._get_template_content`` has
    # honoured since Phase 4 -- were reachable only via MCP.
    #
    # Rather than widening the flat object (which cannot express "is this
    # value a workspace override, a tenant-global default, or the factory
    # text?"), the slot API below is a second, per-slot representation over
    # the same rows. Both write through ``publish_new_version``, so the
    # model's own one-active-row-per-scope mutex still serialises them.

    @staticmethod
    def _all_prompt_defaults() -> dict[str, str]:
        """Return the canonical factory-default registry for every slot.

        Imported lazily from ``ai_derivation_service`` because that module is
        the single canonical registry for every derive-flow prompt name (see
        its ``PROMPT_TEMPLATE_DEFAULTS`` comment) while it also imports this
        module — a module-level import here would close that cycle.
        """
        from application.ai_derivation_service import (
            PROMPT_TEMPLATE_DEFAULTS as _ALL_DEFAULTS,
        )

        return dict(_ALL_DEFAULTS)

    @staticmethod
    def prompt_slot_names() -> list[str]:
        """Return the names of every factory-known prompt slot."""
        return list(SettingsService._all_prompt_defaults())

    @staticmethod
    def _build_slot_state(
        name: str,
        *,
        global_row: PromptTemplate | None,
        workspace_row: PromptTemplate | None,
        factory_default: str | None,
    ) -> dict[str, Any]:
        """Resolve one slot's per-scope rows into the wire representation.

        Args:
            name:            Template name / slot.
            global_row:      Active tenant-global row, or ``None``.
            workspace_row:   Active workspace-override row, or ``None``.
            factory_default: Factory text for ``name``, or ``None`` for a
                             custom name introduced via MCP that has no
                             factory default.

        Returns:
            A dict with the per-scope contents plus the resolved
            ``effective_content``/``effective_scope`` (``"workspace"`` >
            ``"global"`` > ``"factory"``), mirroring
            ``AiDerivationService._get_template_content``'s fallback chain.
        """
        if workspace_row is not None:
            effective, scope = workspace_row.content, "workspace"
        elif global_row is not None:
            effective, scope = global_row.content, "global"
        else:
            effective, scope = (factory_default or ""), "factory"

        return {
            "name": name,
            "factory_default": factory_default,
            "global_content": global_row.content if global_row else None,
            "global_version": global_row.version if global_row else None,
            "workspace_content": (
                workspace_row.content if workspace_row else None
            ),
            "workspace_version": (
                workspace_row.version if workspace_row else None
            ),
            "has_workspace_override": workspace_row is not None,
            "effective_content": effective,
            "effective_scope": scope,
        }

    def _slot_state(
        self,
        ctx: AuthContext,
        name: str,
        *,
        workspace_id: UUID | None,
        factory_default: str | None,
    ) -> dict[str, Any]:
        """Fetch one slot's rows and resolve them (single-slot read path)."""
        return self._build_slot_state(
            name,
            global_row=get_active_template(
                tenant_id=ctx.tenant_id, name=name, workspace_id=None
            ),
            workspace_row=(
                get_active_template(
                    tenant_id=ctx.tenant_id, name=name, workspace_id=workspace_id
                )
                if workspace_id is not None
                else None
            ),
            factory_default=factory_default,
        )

    def list_prompt_slots(
        self, ctx: AuthContext, *, workspace_id: UUID | None = None
    ) -> list[dict[str, Any]]:
        """Return every prompt slot with its per-scope state, sorted by name.

        The result is the union of the factory slots and any additional
        names that already have an active row for this tenant — templates
        created under a custom name via MCP (``prompt_template.create``) would
        otherwise be invisible to (and silently un-editable from) the UI.

        Args:
            ctx:          Caller's auth context.
            workspace_id: Workspace whose overrides to report, or ``None`` for
                          the tenant-global view only.
        """
        self._set_tenant_context(ctx)
        defaults = self._all_prompt_defaults()
        # One query for every active row of the tenant, then resolved in
        # memory: per-slot lookups would be 2 queries x slot count for a page
        # that renders all of them at once. workspace_id=None here means "no
        # workspace filter" (see list_active_templates' docstring), which is
        # what we want -- a custom name may exist only as a workspace row.
        rows = list_active_templates(tenant_id=ctx.tenant_id)
        global_rows = {r.name: r for r in rows if r.workspace_id is None}
        workspace_rows = (
            {r.name: r for r in rows if r.workspace_id == workspace_id}
            if workspace_id is not None
            else {}
        )
        names = set(defaults) | {r.name for r in rows}
        return [
            self._build_slot_state(
                name,
                global_row=global_rows.get(name),
                workspace_row=workspace_rows.get(name),
                factory_default=defaults.get(name),
            )
            for name in sorted(names)
        ]

    def set_prompt_slot(
        self,
        ctx: AuthContext,
        *,
        name: str,
        content: str,
        workspace_id: UUID | None = None,
    ) -> dict[str, Any]:
        """Publish a new active version of ``name`` for the given scope.

        Args:
            ctx:          Caller's auth context.
            content:      New prompt body.
            name:         Template name / slot.
            workspace_id: Workspace to override for, or ``None`` to write the
                          tenant-global default.

        Raises:
            ValidationError: A concurrent writer published for the same scope
                first (the model's own mutex rejected this write).
        """
        self._set_tenant_context(ctx)
        try:
            publish_new_version(
                tenant_id=ctx.tenant_id,
                name=name,
                content=content,
                workspace_id=workspace_id,
            )
        except IntegrityError as exc:
            raise ValidationError(
                f"Could not publish a new version for '{name}': {exc}"
            ) from exc
        return self._slot_state(
            ctx,
            name,
            workspace_id=workspace_id,
            factory_default=self._all_prompt_defaults().get(name),
        )

    def clear_prompt_slot(
        self, ctx: AuthContext, *, name: str, workspace_id: UUID | None = None
    ) -> dict[str, Any]:
        """Drop the active override for ``name`` at the given scope.

        Deactivates (never deletes) the scope's active row so the resolution
        chain falls through to the next level: clearing a workspace scope
        restores the tenant-global default, clearing the tenant-global scope
        restores the factory text. Clearing a scope that has no active row is
        a no-op, not an error — it is already at its inherited value.

        Args:
            ctx:          Caller's auth context.
            name:         Template name / slot.
            workspace_id: Workspace whose override to drop, or ``None`` for
                          the tenant-global row.
        """
        self._set_tenant_context(ctx)
        deactivate_scope(
            tenant_id=ctx.tenant_id, name=name, workspace_id=workspace_id
        )
        return self._slot_state(
            ctx,
            name,
            workspace_id=workspace_id,
            factory_default=self._all_prompt_defaults().get(name),
        )

    # ---- ReviewPolicy (Phase 5, REQ-L2-RV-001) -----------------------------
    #
    # Unlike PromptTemplate this is a plain upsert target, not append-only
    # version history -- there is no audit value in keeping old policy values
    # around, only the effective one matters. See persistence.models.
    # ReviewPolicy's class docstring for the full scoping rationale.

    # Modes that let AiDerivationService._auto_approve cross an approval gate
    # without a human decision, other than via an explicit confidence check
    # (GitHub #452): "auto" always did (given an explicit auto_approve_target
    # exists for the item type), "review_changes" is documented as currently
    # identical to "auto". Both are unsafe as the *effective* mode for a
    # preset tier that mandates human approval gates.
    _UNGATED_MODES = ("auto", "review_changes")

    @staticmethod
    def _workspace_tier(workspace_id: "str | None") -> "str | None":
        """Best-effort resolution of *workspace_id*'s active preset tier.

        Returns ``None`` when no workspace is in scope (tenant-global row)
        or the workspace/its preset config cannot be resolved -- callers
        must treat that as "tier unknown" and skip tier-specific behaviour
        rather than raise, since this is a read-side safety net, not the
        primary validation path.
        """
        if not workspace_id:
            return None
        try:
            from presets.services import get_preset

            return get_preset(workspace_id).preset
        except Exception:
            return None

    def get_effective_review_policy(
        self, ctx: AuthContext, *, workspace_id: "str | None" = None
    ) -> ReviewPolicy:
        """Return the effective ReviewPolicy for ``workspace_id``.

        Resolution order: active workspace-scoped row -> tenant-global row
        (``workspace_id=None``) -> an unsaved default instance
        (``mode="auto"``, ``min_confidence=0.7``). A read never creates a row.

        GitHub #452: for a workspace on the ``extended`` preset tier, the
        resolved mode is additionally floored to ``"review_all"`` when it
        would otherwise be ``"auto"`` or ``"review_changes"`` -- the
        ``extended`` tier's approval-workflow rigor (REQ-L2-PC-001) requires
        a human decision at every approval gate, so it must never depend on
        a stored/defaulted policy value that lets
        ``AiDerivationService._auto_approve`` cross one unsupervised. This
        override is applied here (not only in ``update_review_policy``) so
        that both this read path and the write path share one enforcement
        point, and so pre-existing rows created before this fix are covered
        too. The underlying stored value is left untouched -- only the
        in-memory, unsaved instance returned to the caller reflects the
        floor.
        """
        self._set_tenant_context(ctx)
        if workspace_id is not None:
            row = ReviewPolicy.objects.filter(
                tenant_id=ctx.tenant_id, workspace_id=workspace_id
            ).first()
            if row is not None:
                return self._apply_tier_floor(row, workspace_id)
        row = ReviewPolicy.objects.filter(
            tenant_id=ctx.tenant_id, workspace_id=None
        ).first()
        if row is not None:
            return self._apply_tier_floor(row, workspace_id)
        return self._apply_tier_floor(
            ReviewPolicy(
                tenant_id=ctx.tenant_id,
                workspace_id=workspace_id,
                mode="auto",
                min_confidence=0.7,
            ),
            workspace_id,
        )

    def _apply_tier_floor(
        self, policy: ReviewPolicy, workspace_id: "str | None"
    ) -> ReviewPolicy:
        """Floor *policy* to ``"review_all"`` if its tier requires it.

        See :meth:`get_effective_review_policy` for the rationale. Mutates
        and returns *policy* in place; never persists the change.
        """
        if policy.mode in self._UNGATED_MODES:
            tier = self._workspace_tier(workspace_id)
            if tier == TIER_EXTENDED:
                policy.mode = "review_all"
        return policy

    def update_review_policy(
        self,
        ctx: AuthContext,
        *,
        workspace_id: "str | None",
        mode: str,
        min_confidence: float,
    ) -> ReviewPolicy:
        """Upsert the single ``(tenant, workspace_id)`` ReviewPolicy row.

        Validates ``mode`` against ``REVIEW_POLICY_MODES`` and that
        ``min_confidence`` is within ``[0.0, 1.0]``; raises ``ValidationError``
        otherwise.

        GitHub #452: also rejects ``mode in ("auto", "review_changes")`` for
        a workspace on the ``extended`` preset tier -- that tier requires a
        human approval gate, so it must not be possible to explicitly store
        a policy that bypasses it (defense in depth alongside the read-side
        floor in :meth:`get_effective_review_policy`).
        """
        self._set_tenant_context(ctx)
        if mode not in REVIEW_POLICY_MODES:
            raise ValidationError(
                f"Unknown review policy mode '{mode}'. Valid: {', '.join(REVIEW_POLICY_MODES)}."
            )
        if not (0.0 <= min_confidence <= 1.0):
            raise ValidationError("min_confidence must be between 0.0 and 1.0.")
        if mode in self._UNGATED_MODES and self._workspace_tier(workspace_id) == TIER_EXTENDED:
            raise ValidationError(
                f"mode='{mode}' is not allowed for the 'extended' preset tier: "
                "extended workspaces require a human approval gate "
                "(use 'review_all' or 'review_high_risk')."
            )
        row, _ = ReviewPolicy.objects.update_or_create(
            tenant_id=ctx.tenant_id,
            workspace_id=workspace_id,
            defaults={"mode": mode, "min_confidence": min_confidence},
        )
        return row


__all__ = ["SettingsService"]
