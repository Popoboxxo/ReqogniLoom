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

``SettingsService`` itself is a thin facade: it applies the tenant context
(REQ-L2-AS-022) and delegates to one private ``_*Ops`` helper per cohesive
concern (LlmSettings, the flat PromptTemplate contract, the per-slot prompt
API, ReviewPolicy), so each surface keeps its persistence logic in exactly
one place.
"""
from __future__ import annotations

import os
from types import SimpleNamespace
from typing import Any
from uuid import UUID

from django.db import IntegrityError

from application.base import ServiceBase, ValidationError
from application.prompt_template_versioning import (
    deactivate_scope,
    get_active_template,
    list_active_templates,
    publish_new_version,
)
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


class _LlmSettingsOps:
    """LlmSettings persistence behind the ``/api/v1/llm-settings/`` surface.

    Owns the lazy-create-on-write / never-create-on-read split (issue #276)
    and the whitelisted write path; the facade only supplies the tenant
    context in front of these calls.
    """

    @staticmethod
    def read(ctx: AuthContext) -> LlmSettings:
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

    @staticmethod
    def get_or_create(ctx: AuthContext) -> LlmSettings:
        """Return the tenant's singleton LlmSettings row, creating it if absent.

        Write path only — creating the row is an explicit act of configuration
        (see :meth:`_LlmSettingsOps.read` for why reads must not create one).
        """
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

    @staticmethod
    def apply_writable_fields(obj: LlmSettings, validated_data: dict[str, Any]) -> None:
        """Mutate only the whitelisted fields of *obj* (``api_key`` write-only)."""
        for field in _LLM_WRITABLE_FIELDS:
            if field in validated_data:
                setattr(obj, field, validated_data[field])

    def update(self, ctx: AuthContext, validated_data: dict[str, Any]) -> LlmSettings:
        """Apply whitelisted ``validated_data`` to the row and save it."""
        obj = self.get_or_create(ctx)
        self.apply_writable_fields(obj, validated_data)
        obj.save()
        return obj


class _PromptTemplateOps:
    """REST backward-compat facade over prompt templates (Phase 4, REQ-L2-PT-001).

    Reads/writes only the tenant-global (workspace_id=None) rows for the 3
    original slot names, and presents them as one flat object -- the shape the
    REST contract has always exposed. See module docstring for the full
    rationale.
    """

    @staticmethod
    def effective(ctx: AuthContext) -> SimpleNamespace:
        """Return the effective content of the 3 original slots as one object.

        For each slot: the tenant-global active row's content if one exists,
        else the factory default. Read-only -- never creates a row, since a
        slot with no active row already has a well-defined effective value
        (the factory default).
        """
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

    def update(self, ctx: AuthContext, validated_data: dict[str, Any]) -> SimpleNamespace:
        """Publish a new tenant-global version for each slot in ``validated_data``.

        Only the slots present in ``validated_data`` are touched (partial
        update semantics identical to the pre-Phase-4 behaviour); untouched
        slots keep whatever their current effective value is.
        """
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
        return self.effective(ctx)

    def reset(self, ctx: AuthContext, slot: str | None = None) -> SimpleNamespace:
        """Reset one slot (``slot``) or all slots to their factory defaults.

        A slot with no active tenant-global row is already at its factory
        default (see :meth:`effective`), so resetting it is a
        no-op -- only slots that were actually customised get a new version
        published. This keeps "reset" from manufacturing rows (and version
        history) for slots nobody ever touched.
        """
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
                    # See the same handling in _PromptTemplateOps.update above.
                    raise ValidationError(
                        f"Could not reset '{name}' to its factory default: {exc}"
                    ) from exc
        return self.effective(ctx)


class _PromptSlotOps:
    """Per-slot prompt API over the versioned template rows (issue #119).

    The flat facade above is deliberately frozen at its historical shape:
    4 slots, tenant-global scope only. That is exactly the gap issue #119
    reports -- the 4 further slots the AI-derivation flows use
    (``testcase_derive``, ``architecture_to_risk``, ``workspace_to_glossary``,
    ``decision_to_adr``) were unreachable from REST, and workspace-level
    overrides -- which ``AiDerivationService._get_template_content`` has
    honoured since Phase 4 -- were reachable only via MCP.

    Rather than widening the flat object (which cannot express "is this
    value a workspace override, a tenant-global default, or the factory
    text?"), the slot API below is a second, per-slot representation over
    the same rows. Both write through ``publish_new_version``, so the
    model's own one-active-row-per-scope mutex still serialises them.
    """

    @staticmethod
    def all_defaults() -> dict[str, str]:
        """Return the canonical factory-default registry for every slot.

        Reads ``application.prompt_slots`` — the one consolidated registry
        (spec §3.2) — instead of ``ai_derivation_service``'s
        derive-flow-only dict, so slots owned by other services (e.g.
        ``architecture_decompose_tree``) are editable in the slot UI too.

        Imported lazily because ``prompt_slots`` lazily imports
        ``ai_derivation_service``, which imports this module — a module-level
        import here would close that cycle.
        """
        from application.prompt_slots import get_prompt_slots

        return {name: spec.default_content for name, spec in get_prompt_slots().items()}

    @staticmethod
    def resolve_effective(
        workspace_row: PromptTemplate | None,
        global_row: PromptTemplate | None,
        factory_default: str | None,
    ) -> tuple[str, str]:
        """Return ``(effective_content, effective_scope)`` for one slot.

        The ``"workspace"`` > ``"global"`` > ``"factory"`` fallback chain,
        mirroring ``AiDerivationService._get_template_content``.
        """
        if workspace_row is not None:
            return workspace_row.content, "workspace"
        if global_row is not None:
            return global_row.content, "global"
        return (factory_default or ""), "factory"

    @staticmethod
    def _row_view(row: PromptTemplate | None) -> dict[str, Any]:
        """Project one scope's active row to its wire fields (empty when absent)."""
        if row is None:
            return {}
        return {"content": row.content, "version": row.version}

    @classmethod
    def build_state(
        cls,
        name: str,
        *,
        global_row: PromptTemplate | None,
        workspace_row: PromptTemplate | None,
        factory_default: str | None,
        data_variables: list[str] | None = None,
        config_variables: list[str] | None = None,
        unknown_placeholders: list[str] | None = None,
    ) -> dict[str, Any]:
        """Resolve one slot's per-scope rows into the wire representation.

        Args:
            name:            Template name / slot.
            global_row:      Active tenant-global row, or ``None``.
            workspace_row:   Active workspace-override row, or ``None``.
            factory_default: Factory text for ``name``, or ``None`` for a
                             custom name introduced via MCP that has no
                             factory default.
            data_variables:   Declared code-bound variables for ``name``, or
                              ``None`` when the caller annotates separately.
            config_variables: Config variables the effective body actually
                              references, or ``None``.
            unknown_placeholders: ``{placeholders}`` neither list can fill,
                              or ``None``.

        Returns:
            A dict with the per-scope contents plus the resolved
            ``effective_content``/``effective_scope``, plus the three
            variable-catalog annotations (spec §5).
        """
        effective, scope = cls.resolve_effective(
            workspace_row, global_row, factory_default
        )
        global_view = cls._row_view(global_row)
        workspace_view = cls._row_view(workspace_row)
        return {
            "name": name,
            "factory_default": factory_default,
            "global_content": global_view.get("content"),
            "global_version": global_view.get("version"),
            "workspace_content": workspace_view.get("content"),
            "workspace_version": workspace_view.get("version"),
            "has_workspace_override": workspace_row is not None,
            "effective_content": effective,
            "effective_scope": scope,
            "data_variables": data_variables or [],
            "config_variables": config_variables or [],
            "unknown_placeholders": unknown_placeholders or [],
        }

    @staticmethod
    def annotations(
        ctx: AuthContext,
        name: str,
        content: str,
        workspace_id: UUID | None,
        *,
        config_values: dict[str, Any] | None = None,
    ) -> tuple[list[str], list[str], list[str]]:
        """Return ``(data_variables, config_variables, unknown_placeholders)``.

        ``config_variables`` lists only the config names the *effective body*
        actually references — spec §5 asks the UI to show what this prompt
        uses, not the whole catalog. ``unknown_placeholders`` is the typo
        warning: a ``{name}`` that is neither a declared data variable of this
        slot nor a resolvable config variable can never be filled.

        Args:
            config_values: Pre-resolved ``{config_name: value}`` (Task 5's
                ``resolve_config_values``), or ``None`` to resolve it here.
                It does not depend on ``name`` -- callers annotating many
                slots for one request (``list_slots``) must resolve it
                ONCE and pass it through, or every slot re-triggers the same
                DB roundtrip (``list_active_variables``) for an identical
                result. The typo check is reimplemented locally against this
                dict instead of delegating to ``prompt_resolver
                .unknown_placeholders``, which would otherwise re-resolve
                config values internally and reintroduce the same N+1.

        Imported lazily for the same import-cycle reason as
        :meth:`all_defaults`.
        """
        from application.prompt_resolver import (
            extract_placeholders,
            resolve_config_values,
        )
        from application.prompt_slots import get_slot_data_variables

        if config_values is None:
            config_values = resolve_config_values(ctx, workspace_id)

        data_variables = list(get_slot_data_variables(name))
        placeholders = extract_placeholders(content or "")
        config_variables = [p for p in placeholders if p in config_values]
        known = set(data_variables) | set(config_values)
        unknown = [p for p in placeholders if p not in known]
        return data_variables, config_variables, unknown

    @staticmethod
    def partition_rows(
        rows: list[PromptTemplate], workspace_id: UUID | None
    ) -> tuple[dict[str, PromptTemplate], dict[str, PromptTemplate]]:
        """Split active *rows* into the tenant-global and workspace name maps.

        ``workspace_id=None`` means "no workspace filter" (the caller wants
        the tenant-global view only) -- a custom name may exist only as a
        workspace row, so both maps stay keyed by name.
        """
        global_rows = {r.name: r for r in rows if r.workspace_id is None}
        workspace_rows = (
            {r.name: r for r in rows if r.workspace_id == workspace_id}
            if workspace_id is not None
            else {}
        )
        return global_rows, workspace_rows

    def slot_state(
        self,
        ctx: AuthContext,
        name: str,
        *,
        workspace_id: UUID | None,
        factory_default: str | None,
    ) -> dict[str, Any]:
        """Fetch one slot's rows, resolve them, and annotate its variables."""
        state = self.build_state(
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
        data_vars, config_vars, unknown = self.annotations(
            ctx, name, state["effective_content"], workspace_id
        )
        state["data_variables"] = data_vars
        state["config_variables"] = config_vars
        state["unknown_placeholders"] = unknown
        return state

    def list_slots(
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
        from application.prompt_resolver import resolve_config_values

        defaults = self.all_defaults()
        # One query for every active row of the tenant, then resolved in
        # memory: per-slot lookups would be 2 queries x slot count for a page
        # that renders all of them at once. workspace_id=None here means "no
        # workspace filter" (see list_active_templates' docstring), which is
        # what we want -- a custom name may exist only as a workspace row.
        rows = list_active_templates(tenant_id=ctx.tenant_id)
        global_rows, workspace_rows = self.partition_rows(rows, workspace_id)
        # Resolved once for the whole page, not per slot: it does not depend
        # on the slot name, so re-resolving it ~20+ times (once per slot,
        # each internally re-querying list_active_variables) would multiply
        # this single request's DB roundtrips by the slot count for an
        # identical result every time.
        config_values = resolve_config_values(ctx, workspace_id)
        names = set(defaults) | {r.name for r in rows}
        slots: list[dict[str, Any]] = []
        for name in sorted(names):
            state = self.build_state(
                name,
                global_row=global_rows.get(name),
                workspace_row=workspace_rows.get(name),
                factory_default=defaults.get(name),
            )
            data_vars, config_vars, unknown = self.annotations(
                ctx,
                name,
                state["effective_content"],
                workspace_id,
                config_values=config_values,
            )
            state["data_variables"] = data_vars
            state["config_variables"] = config_vars
            state["unknown_placeholders"] = unknown
            slots.append(state)
        return slots

    def publish(
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
        return self.slot_state(
            ctx,
            name,
            workspace_id=workspace_id,
            factory_default=self.all_defaults().get(name),
        )

    def clear(
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
        deactivate_scope(
            tenant_id=ctx.tenant_id, name=name, workspace_id=workspace_id
        )
        return self.slot_state(
            ctx,
            name,
            workspace_id=workspace_id,
            factory_default=self.all_defaults().get(name),
        )


class _ReviewPolicyOps:
    """ReviewPolicy upsert + effective resolution (Phase 5, REQ-L2-RV-001).

    Unlike PromptTemplate this is a plain upsert target, not append-only
    version history -- there is no audit value in keeping old policy values
    around, only the effective one matters. See persistence.models.
    ReviewPolicy's class docstring for the full scoping rationale.
    """

    # Modes that let AiDerivationService._auto_approve cross an approval gate
    # without a human decision, other than via an explicit confidence check
    # (GitHub #452): "auto" always did (given an explicit auto_approve_target
    # exists for the item type), "review_changes" is documented as currently
    # identical to "auto". Both are unsafe as the *effective* mode for a
    # preset tier that mandates human approval gates.
    _UNGATED_MODES = ("auto", "review_changes")

    @staticmethod
    def workspace_tier(workspace_id: str | None) -> str | None:
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

    @classmethod
    def apply_tier_floor(
        cls, policy: ReviewPolicy, workspace_id: str | None
    ) -> ReviewPolicy:
        """Floor *policy* to ``"review_all"`` if its tier requires it.

        See :meth:`_ReviewPolicyOps.get_effective` for the rationale. Mutates
        and returns *policy* in place; never persists the change.
        """
        if policy.mode in cls._UNGATED_MODES:
            tier = cls.workspace_tier(workspace_id)
            if tier == TIER_EXTENDED:
                policy.mode = "review_all"
        return policy

    def get_effective(
        self, ctx: AuthContext, *, workspace_id: str | None = None
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
        if workspace_id is not None:
            row = ReviewPolicy.objects.filter(
                tenant_id=ctx.tenant_id, workspace_id=workspace_id
            ).first()
            if row is not None:
                return self.apply_tier_floor(row, workspace_id)
        row = ReviewPolicy.objects.filter(
            tenant_id=ctx.tenant_id, workspace_id=None
        ).first()
        if row is not None:
            return self.apply_tier_floor(row, workspace_id)
        return self.apply_tier_floor(
            ReviewPolicy(
                tenant_id=ctx.tenant_id,
                workspace_id=workspace_id,
                mode="auto",
                min_confidence=0.7,
            ),
            workspace_id,
        )

    def update(
        self,
        ctx: AuthContext,
        *,
        workspace_id: str | None,
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
        floor in :meth:`_ReviewPolicyOps.get_effective`).
        """
        if mode not in REVIEW_POLICY_MODES:
            raise ValidationError(
                f"Unknown review policy mode '{mode}'. Valid: {', '.join(REVIEW_POLICY_MODES)}."
            )
        if not (0.0 <= min_confidence <= 1.0):
            raise ValidationError("min_confidence must be between 0.0 and 1.0.")
        if mode in self._UNGATED_MODES and self.workspace_tier(workspace_id) == TIER_EXTENDED:
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


class SettingsService(ServiceBase):
    """Tenant-scoped LLM + PromptTemplate configuration facade (REQ-066).

    Delegates each configuration surface to its private ``_*Ops`` helper
    (LlmSettings, the flat PromptTemplate contract, the per-slot prompt
    API, ReviewPolicy); this class only owns the tenant context
    (REQ-L2-AS-022) and the static choice/default surfaces.
    """

    def __init__(self) -> None:
        super().__init__()
        self._llm_ops = _LlmSettingsOps()
        self._flat_ops = _PromptTemplateOps()
        self._slot_ops = _PromptSlotOps()
        self._policy_ops = _ReviewPolicyOps()

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
        """Return the tenant's LLM settings for reading — WITHOUT persisting."""
        self._set_tenant_context(ctx)
        return self._llm_ops.read(ctx)

    def get_or_create_llm_settings(self, ctx: AuthContext) -> LlmSettings:
        """Return the tenant's singleton LlmSettings row, creating it if absent.

        Write path only — creating the row is an explicit act of configuration
        (see :meth:`get_llm_settings` for why reads must not create one).
        """
        self._set_tenant_context(ctx)
        return self._llm_ops.get_or_create(ctx)

    def update_llm_settings(
        self, ctx: AuthContext, validated_data: dict[str, Any]
    ) -> LlmSettings:
        """Apply whitelisted ``validated_data`` to the LlmSettings row and save.

        Raises:
            llm_adapter.url_guard.UnsafeOutboundUrlError: If ``base_url`` points
                at a non-public address (SA-33). The REST serializer already
                rejects these with a 400; this is the backstop that keeps the
                invariant attached to the single write path rather than to one
                caller, so a future MCP tool or management command cannot
                configure an SSRF target by skipping the serializer.
        """
        from llm_adapter.url_guard import validate_outbound_url

        if "base_url" in validated_data:
            validate_outbound_url(validated_data["base_url"])

        self._set_tenant_context(ctx)
        return self._llm_ops.update(ctx, validated_data)

    # ---- PromptTemplate ---------------------------------------------------
    #
    # REST backward-compat facade (Phase 4, REQ-L2-PT-001): reads/writes only
    # the tenant-global (workspace_id=None) rows for the 3 original slot
    # names, and presents them as one flat object -- the shape the REST
    # contract has always exposed. See module docstring for the full
    # rationale. Persistence lives in ``_PromptTemplateOps``.

    def get_or_create_prompt_template(self, ctx: AuthContext) -> SimpleNamespace:
        """Return the effective (tenant-global) prompt-template content.

        Named ``get_or_create`` for continuity with the pre-Phase-4 API
        surface; despite the name it never creates a row -- a GET is a read,
        and "the row doesn't exist yet" already has a well-defined answer
        (the default).
        """
        self._set_tenant_context(ctx)
        return self._flat_ops.effective(ctx)

    def update_prompt_template(
        self, ctx: AuthContext, validated_data: dict[str, Any]
    ) -> SimpleNamespace:
        """Publish a new tenant-global version for each slot in ``validated_data``.

        Only the slots present in ``validated_data`` are touched (partial
        update semantics identical to the pre-Phase-4 behaviour); untouched
        slots keep whatever their current effective value is.
        """
        self._set_tenant_context(ctx)
        return self._flat_ops.update(ctx, validated_data)

    def reset_prompt_template(
        self, ctx: AuthContext, slot: str | None = None
    ) -> SimpleNamespace:
        """Reset one slot (``slot``) or all slots to their factory defaults."""
        self._set_tenant_context(ctx)
        return self._flat_ops.reset(ctx, slot)

    # ---- PromptTemplate slots (issue #119) --------------------------------
    #
    # Per-slot representation over the same rows, reachable per workspace;
    # persistence and state building live in ``_PromptSlotOps``.

    @staticmethod
    def prompt_slot_names() -> list[str]:
        """Return the names of every factory-known prompt slot."""
        return list(_PromptSlotOps.all_defaults())

    def list_prompt_slots(
        self, ctx: AuthContext, *, workspace_id: UUID | None = None
    ) -> list[dict[str, Any]]:
        """Return every prompt slot with its per-scope state, sorted by name."""
        self._set_tenant_context(ctx)
        return self._slot_ops.list_slots(ctx, workspace_id=workspace_id)

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
        return self._slot_ops.publish(
            ctx, name=name, content=content, workspace_id=workspace_id
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
        return self._slot_ops.clear(ctx, name=name, workspace_id=workspace_id)

    # ---- ReviewPolicy (Phase 5, REQ-L2-RV-001) -----------------------------
    #
    # Plain upsert target, not append-only version history -- resolution and
    # validation live in ``_ReviewPolicyOps``.

    def get_effective_review_policy(
        self, ctx: AuthContext, *, workspace_id: str | None = None
    ) -> ReviewPolicy:
        """Return the effective ReviewPolicy for ``workspace_id``.

        Resolution order: active workspace-scoped row -> tenant-global row
        (``workspace_id=None``) -> an unsaved default instance
        (``mode="auto"``, ``min_confidence=0.7``). A read never creates a row.
        A workspace on the ``extended`` preset tier is floored to
        ``"review_all"`` (GitHub #452, REQ-L2-PC-001); the stored value is
        left untouched.
        """
        self._set_tenant_context(ctx)
        return self._policy_ops.get_effective(ctx, workspace_id=workspace_id)

    def update_review_policy(
        self,
        ctx: AuthContext,
        *,
        workspace_id: str | None,
        mode: str,
        min_confidence: float,
    ) -> ReviewPolicy:
        """Upsert the single ``(tenant, workspace_id)`` ReviewPolicy row.

        Validates ``mode`` against ``REVIEW_POLICY_MODES`` and that
        ``min_confidence`` is within ``[0.0, 1.0]``; raises ``ValidationError``
        otherwise. ``mode in ("auto", "review_changes")`` is rejected for a
        workspace on the ``extended`` preset tier (GitHub #452).
        """
        self._set_tenant_context(ctx)
        return self._policy_ops.update(
            ctx,
            workspace_id=workspace_id,
            mode=mode,
            min_confidence=min_confidence,
        )


__all__ = ["SettingsService"]
