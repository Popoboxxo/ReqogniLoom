"""
COMP-RA-001 — LLM configuration REST endpoints (REQ-L2-LLM-001).

Endpoints:
  GET   /api/v1/llm-settings/
      Return the active tenant's LLM configuration. The row is created on
      first access (get-or-create with provider=mock). ``api_key`` is never
      returned; a boolean ``api_key_is_set`` reports whether one is stored.

  PUT   /api/v1/llm-settings/
  PATCH /api/v1/llm-settings/
      Update the configuration. ``api_key`` is write-only.

Authentication: Bearer token (global default).
Permissions:    Admin role only (both read and write) — LLM credentials are
                sensitive tenant-wide configuration.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from rest_framework import serializers, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from application.base import ValidationError
from application.settings_service import SettingsService
from auth_tenancy.models import ROLE_ADMIN
from rest_api.auth_enforcer import get_auth_context
from rest_api.serializers import build_error_response, detect_lang


# ---------------------------------------------------------------------------
# Serializer
# ---------------------------------------------------------------------------


class LlmSettingsSerializer(serializers.Serializer):
    """Read/write serializer for :class:`LlmSettings` (REQ-L2-LLM-001).

    ``api_key`` is write-only: it is accepted on write but never serialized on
    read. Readers receive ``api_key_is_set`` instead, so the UI can render a
    "configured" indicator without ever exposing the secret.
    """

    provider = serializers.ChoiceField(choices=SettingsService.provider_choices())
    base_url = serializers.URLField(required=False, allow_blank=True)
    model_name = serializers.CharField(
        required=False, allow_blank=True, max_length=255
    )
    api_key = serializers.CharField(
        write_only=True, required=False, allow_blank=True, max_length=512
    )
    api_key_is_set = serializers.SerializerMethodField()

    def get_api_key_is_set(self, obj: Any) -> bool:
        """Return whether a non-empty API key is stored."""
        return bool(getattr(obj, "api_key", ""))

    def validate(self, attrs: dict) -> dict:
        """Reject Ollama configurations that leave ``base_url`` blank.

        Ollama has no default endpoint that ReqFlow can assume; without a
        base_url every derivation call would fail at request time. On partial
        updates the effective provider/base_url falls back to the persisted
        instance so a PATCH that only touches one field is validated correctly.
        """
        provider = attrs.get("provider") or getattr(
            self.instance, "provider", None
        )
        if provider == "ollama":
            base_url = attrs.get("base_url")
            if base_url is None:
                base_url = getattr(self.instance, "base_url", "")
            if not (base_url or "").strip():
                raise serializers.ValidationError(
                    {
                        "base_url": (
                            "Ollama requires a base_url. Set the "
                            "OLLAMA_BASE_URL environment variable or provide a "
                            "URL (e.g. http://localhost:11434)"
                        )
                    }
                )
        return attrs


# ---------------------------------------------------------------------------
# View
# ---------------------------------------------------------------------------


class LlmSettingsView(APIView):
    """GET/PUT/PATCH /api/v1/llm-settings/ (REQ-L2-LLM-001). Admin-only."""

    def _forbidden(self, lang: str) -> Response:
        return Response(
            build_error_response(
                "PERMISSION_DENIED",
                lang,
                message="Admin role required to access LLM settings.",
            ),
            status=status.HTTP_403_FORBIDDEN,
        )

    # ---- GET ----------------------------------------------------------

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        ctx = get_auth_context(request)
        if not ctx.has_role(ROLE_ADMIN):
            return self._forbidden(lang)
        # Read-only: never materialises a row (issue #276). Without a stored
        # row the response mirrors the effective environment configuration.
        obj = SettingsService().get_llm_settings(ctx)
        return Response(LlmSettingsSerializer(obj).data)

    # ---- PUT / PATCH --------------------------------------------------

    def put(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return self._update(request, partial=False)

    def patch(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return self._update(request, partial=True)

    def _update(self, request: Request, *, partial: bool) -> Response:
        lang = detect_lang(request)
        ctx = get_auth_context(request)
        if not ctx.has_role(ROLE_ADMIN):
            return self._forbidden(lang)

        svc = SettingsService()
        # Validate against the *effective* settings without creating a row —
        # a rejected request must leave no trace, because row existence now
        # means "explicitly configured" (issue #276). The row is created by
        # update_llm_settings once the payload is known to be valid.
        obj = svc.get_llm_settings(ctx)
        ser = LlmSettingsSerializer(obj, data=request.data, partial=partial)
        if not ser.is_valid():
            return Response(
                build_error_response(
                    "VALIDATION_ERROR",
                    lang,
                    details=[
                        {"field": k, "errors": v} for k, v in ser.errors.items()
                    ],
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        obj = svc.update_llm_settings(ctx, dict(ser.validated_data))
        return Response(LlmSettingsSerializer(obj).data)


# ---------------------------------------------------------------------------
# PromptTemplate — tenant-global LLM prompt templates, REST compat facade
# (REQ-L2-PT-001)
# ---------------------------------------------------------------------------


class PromptTemplateSerializer(serializers.Serializer):
    """Read/write serializer for :class:`PromptTemplate` (REQ-L2-PT-001).

    All three slot fields are readable and writable. ``defaults_dict`` is a
    read-only map of slot name -> factory default, so the UI can offer a
    "reset to default" affordance without hard-coding the prompt text.
    """

    need_to_sysreq = serializers.CharField(
        required=False, allow_blank=True, trim_whitespace=False
    )
    sysreq_to_arch_assign = serializers.CharField(
        required=False, allow_blank=True, trim_whitespace=False
    )
    sysreq_decompose_next_level = serializers.CharField(
        required=False, allow_blank=True, trim_whitespace=False
    )
    goal_aggregate = serializers.CharField(
        required=False, allow_blank=True, trim_whitespace=False
    )
    defaults_dict = serializers.SerializerMethodField()

    def get_defaults_dict(self, obj: Any) -> dict:
        """Return the read-only factory defaults for every slot."""
        return SettingsService.prompt_defaults()


class PromptTemplateView(APIView):
    """GET/PUT/PATCH /api/v1/prompt-templates/ (REQ-L2-PT-001).

    Backward-compat facade over the versioned, named ``PromptTemplate`` model
    (see ``persistence.models.PromptTemplate``): the underlying persistence is
    no longer a single tenant-singleton row but an append-only history of
    versioned rows per ``(tenant, workspace_id, name)`` scope. This view keeps
    the original REST contract's flat-object shape for exactly the 3
    original slot names (``need_to_sysreq``/``sysreq_to_arch_assign``/
    ``sysreq_decompose_next_level``), always reading/writing the
    tenant-global (``workspace_id=None``) row for each — see
    ``SettingsService``'s module docstring for the full rationale. Admin
    role required to read or write, mirroring :class:`LlmSettingsView` —
    prompt templates steer AI derivation and are tenant-wide configuration.
    """

    def _forbidden(self, lang: str) -> Response:
        return Response(
            build_error_response(
                "PERMISSION_DENIED",
                lang,
                message="Admin role required to access prompt templates.",
            ),
            status=status.HTTP_403_FORBIDDEN,
        )

    # ---- GET ----------------------------------------------------------

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        ctx = get_auth_context(request)
        if not ctx.has_role(ROLE_ADMIN):
            return self._forbidden(lang)
        obj = SettingsService().get_or_create_prompt_template(ctx)
        return Response(PromptTemplateSerializer(obj).data)

    # ---- PUT / PATCH --------------------------------------------------

    def put(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return self._update(request, partial=False)

    def patch(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return self._update(request, partial=True)

    def _update(self, request: Request, *, partial: bool) -> Response:
        lang = detect_lang(request)
        ctx = get_auth_context(request)
        if not ctx.has_role(ROLE_ADMIN):
            return self._forbidden(lang)

        svc = SettingsService()
        obj = svc.get_or_create_prompt_template(ctx)
        ser = PromptTemplateSerializer(obj, data=request.data, partial=partial)
        if not ser.is_valid():
            return Response(
                build_error_response(
                    "VALIDATION_ERROR",
                    lang,
                    details=[
                        {"field": k, "errors": v} for k, v in ser.errors.items()
                    ],
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            obj = svc.update_prompt_template(ctx, dict(ser.validated_data))
        except ValidationError as exc:
            # A concurrent writer published a version for the same scope in
            # between our read and our write (PromptTemplate.save()'s own
            # mutex rejected the second attempt) -- report it as a clean 4xx
            # instead of surfacing an unhandled 500 to the caller.
            return Response(
                build_error_response(
                    "VALIDATION_ERROR", lang, message=str(exc)
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(PromptTemplateSerializer(obj).data)


class PromptTemplateResetView(APIView):
    """POST /api/v1/prompt-templates/reset/ (REQ-L2-PT-001).

    Restore prompt content to the factory ``DEFAULT_*`` constants. Body may
    contain ``{"slot": "<name>"}`` to reset a single slot; without it, all
    slots are reset. Admin role required.
    """

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        ctx = get_auth_context(request)
        if not ctx.has_role(ROLE_ADMIN):
            return Response(
                build_error_response(
                    "PERMISSION_DENIED",
                    lang,
                    message="Admin role required to reset prompt templates.",
                ),
                status=status.HTTP_403_FORBIDDEN,
            )

        svc = SettingsService()
        slot = request.data.get("slot")
        if slot is not None and not svc.is_valid_prompt_slot(slot):
            return Response(
                build_error_response(
                    "VALIDATION_ERROR",
                    lang,
                    message=f"Unknown prompt slot: '{slot}'.",
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            obj = svc.reset_prompt_template(ctx, slot=slot)
        except ValidationError as exc:
            # Same concurrent-write race as PromptTemplateView._update above.
            return Response(
                build_error_response(
                    "VALIDATION_ERROR", lang, message=str(exc)
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(PromptTemplateSerializer(obj).data)


# ---------------------------------------------------------------------------
# PromptTemplate slots — every slot, per-workspace overrides (issue #119)
# ---------------------------------------------------------------------------


class PromptTemplateSlotWriteSerializer(serializers.Serializer):
    """Write serializer for a single prompt slot (issue #119).

    ``content`` is intentionally allowed to be blank and is not whitespace-
    trimmed: prompt bodies are significant whitespace and an admin may
    legitimately want to blank a slot out before rewriting it.
    """

    content = serializers.CharField(allow_blank=True, trim_whitespace=False)


class _PromptSlotAdminMixin:
    """Shared admin gate + ``workspace_id`` query-param parsing (issue #119)."""

    def _forbidden(self, lang: str) -> Response:
        """Return the 403 body used by every prompt-template endpoint."""
        return Response(
            build_error_response(
                "PERMISSION_DENIED",
                lang,
                message="Admin role required to access prompt templates.",
            ),
            status=status.HTTP_403_FORBIDDEN,
        )

    def _parse_workspace_id(self, request: Request) -> "UUID | None":
        """Return the ``?workspace_id=`` scope, or ``None`` for tenant-global.

        Raises:
            ValueError: The parameter was present but not a valid UUID.
        """
        raw = request.query_params.get("workspace_id")
        if raw in (None, ""):
            return None
        return UUID(raw)

    def _bad_workspace_id(self, lang: str) -> Response:
        """Return the 400 body for a malformed ``workspace_id``."""
        return Response(
            build_error_response(
                "VALIDATION_ERROR",
                lang,
                message="'workspace_id' must be a valid UUID.",
            ),
            status=status.HTTP_400_BAD_REQUEST,
        )


class PromptTemplateSlotListView(_PromptSlotAdminMixin, APIView):
    """GET /api/v1/prompt-templates/slots/[?workspace_id=<uuid>] (issue #119).

    Returns every prompt slot — every factory slot plus any custom name
    created via MCP — with its content at each scope and the resolved
    effective value. This is the read side the flat
    :class:`PromptTemplateView` facade cannot express: that endpoint reports a
    single merged string per slot for only 4 slots at only the tenant-global
    scope, so a UI had no way to tell an override apart from an inherited
    value, nor to reach the remaining slots at all.

    Admin role required, mirroring :class:`PromptTemplateView`.
    """

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Return the per-scope state of every prompt slot."""
        lang = detect_lang(request)
        ctx = get_auth_context(request)
        if not ctx.has_role(ROLE_ADMIN):
            return self._forbidden(lang)
        try:
            workspace_id = self._parse_workspace_id(request)
        except ValueError:
            return self._bad_workspace_id(lang)

        slots = SettingsService().list_prompt_slots(
            ctx, workspace_id=workspace_id
        )
        return Response(
            {
                "slots": slots,
                "count": len(slots),
                "workspace_id": str(workspace_id) if workspace_id else None,
            }
        )


class PromptTemplateSlotDetailView(_PromptSlotAdminMixin, APIView):
    """PUT/DELETE /api/v1/prompt-templates/slots/<name>/ (issue #119).

    PUT publishes a new active version of ``name`` for the requested scope
    (``?workspace_id=<uuid>`` for a workspace override, omitted for the
    tenant-global default). DELETE drops that scope's override so the value
    falls back to the next level (workspace -> tenant-global -> factory).

    ``name`` is deliberately not validated against the factory registry: MCP's
    ``prompt_template.create`` can introduce names at runtime (see that tool
    group's naming-openness decision), so rejecting unknown names here would
    make MCP-created templates un-editable from REST — the exact class of
    split-surface gap issue #119 is about.

    Admin role required.
    """

    def put(self, request: Request, name: str, *args: Any, **kwargs: Any) -> Response:
        """Publish a new active version of ``name`` for the requested scope."""
        lang = detect_lang(request)
        ctx = get_auth_context(request)
        if not ctx.has_role(ROLE_ADMIN):
            return self._forbidden(lang)
        try:
            workspace_id = self._parse_workspace_id(request)
        except ValueError:
            return self._bad_workspace_id(lang)

        ser = PromptTemplateSlotWriteSerializer(data=request.data)
        if not ser.is_valid():
            return Response(
                build_error_response(
                    "VALIDATION_ERROR",
                    lang,
                    details=[
                        {"field": k, "errors": v} for k, v in ser.errors.items()
                    ],
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            slot = SettingsService().set_prompt_slot(
                ctx,
                name=name,
                content=ser.validated_data["content"],
                workspace_id=workspace_id,
            )
        except ValidationError as exc:
            # A concurrent writer published for the same scope first — same
            # race (and same 4xx translation) as PromptTemplateView._update.
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message=str(exc)),
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(slot)

    def delete(
        self, request: Request, name: str, *args: Any, **kwargs: Any
    ) -> Response:
        """Drop ``name``'s override at the requested scope (idempotent)."""
        lang = detect_lang(request)
        ctx = get_auth_context(request)
        if not ctx.has_role(ROLE_ADMIN):
            return self._forbidden(lang)
        try:
            workspace_id = self._parse_workspace_id(request)
        except ValueError:
            return self._bad_workspace_id(lang)

        slot = SettingsService().clear_prompt_slot(
            ctx, name=name, workspace_id=workspace_id
        )
        # 200 with the now-effective state rather than 204: the caller's next
        # question is always "so what applies now?", and the fallback value is
        # not derivable client-side without a second round trip.
        return Response(slot)


# ---------------------------------------------------------------------------
# ReviewPolicy — per-workspace AI-derivation review policy (Phase 5,
# REQ-L2-RV-001)
# ---------------------------------------------------------------------------


class ReviewPolicySerializer(serializers.Serializer):
    """Read/write serializer for :class:`ReviewPolicy` (REQ-L2-RV-001).

    ``mode`` is restricted to :data:`REVIEW_POLICY_MODES` and
    ``min_confidence`` to ``[0.0, 1.0]`` at the field level, mirroring the
    same validation ``SettingsService.update_review_policy`` also performs
    (defense-in-depth: the service must not depend on the REST layer having
    validated first, since it is also reachable from the MCP server).
    """

    mode = serializers.ChoiceField(choices=SettingsService.review_policy_modes())
    min_confidence = serializers.FloatField(min_value=0.0, max_value=1.0)


class ReviewPolicyView(APIView):
    """GET/PUT /api/v1/workspaces/{workspace_id}/review-policy/ (REQ-L2-RV-001).

    Admin-only, mirroring :class:`LlmSettingsView`'s permission gate,
    response shape, and error-mapping idiom (``ValidationError`` -> 400,
    ``PermissionDeniedError`` -> 403 is not reachable here since the admin
    check happens before the service call, same as ``LlmSettingsView``).
    """

    def _forbidden(self, lang: str) -> Response:
        return Response(
            build_error_response(
                "PERMISSION_DENIED",
                lang,
                message="Admin role required to access the review policy.",
            ),
            status=status.HTTP_403_FORBIDDEN,
        )

    # ---- GET ------------------------------------------------------------

    def get(self, request: Request, workspace_id: str, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        ctx = get_auth_context(request)
        if not ctx.has_role(ROLE_ADMIN):
            return self._forbidden(lang)
        obj = SettingsService().get_effective_review_policy(ctx, workspace_id=workspace_id)
        return Response(ReviewPolicySerializer(obj).data)

    # ---- PUT --------------------------------------------------------------

    def put(self, request: Request, workspace_id: str, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        ctx = get_auth_context(request)
        if not ctx.has_role(ROLE_ADMIN):
            return self._forbidden(lang)

        ser = ReviewPolicySerializer(data=request.data)
        if not ser.is_valid():
            return Response(
                build_error_response(
                    "VALIDATION_ERROR",
                    lang,
                    details=[
                        {"field": k, "errors": v} for k, v in ser.errors.items()
                    ],
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        svc = SettingsService()
        try:
            obj = svc.update_review_policy(
                ctx,
                workspace_id=workspace_id,
                mode=ser.validated_data["mode"],
                min_confidence=ser.validated_data["min_confidence"],
            )
        except ValidationError as exc:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message=str(exc)),
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(ReviewPolicySerializer(obj).data)


# ---------------------------------------------------------------------------
# Workspace Context Graph — per-workspace settings toggle (Issue #377, Task 9)
# ---------------------------------------------------------------------------


class ContextGraphSettingsSerializer(serializers.Serializer):
    """Read/write serializer for context_service.ContextGraphSettingsDTO."""

    enabled = serializers.BooleanField()
    enabled_generators = serializers.ListField(
        child=serializers.CharField(), required=False
    )
    provider = serializers.CharField(read_only=True)
    last_projected_at = serializers.CharField(read_only=True, allow_null=True)
    last_refresh_at = serializers.CharField(read_only=True, allow_null=True)
    last_error = serializers.CharField(read_only=True)
    node_count = serializers.IntegerField(read_only=True)
    edge_count = serializers.IntegerField(read_only=True)


class ContextGraphSettingsView(APIView):
    """GET/PUT /api/v1/workspaces/{workspace_id}/context-graph-settings/
    (Issue #377, Task 9). Admin-only, mirrors :class:`ReviewPolicyView`.

    GET never creates a row (missing row = feature off, defaults apply —
    Global Constraints). PUT creates/updates it; enabling for the first time
    (or False -> True) triggers an async rebuild.
    """

    def _forbidden(self, lang: str) -> Response:
        return Response(
            build_error_response(
                "PERMISSION_DENIED",
                lang,
                message="Admin role required to access context graph settings.",
            ),
            status=status.HTTP_403_FORBIDDEN,
        )

    def get(self, request: Request, workspace_id: str, *args: Any, **kwargs: Any) -> Response:
        from application import context_service

        lang = detect_lang(request)
        ctx = get_auth_context(request)
        if not ctx.has_role(ROLE_ADMIN):
            return self._forbidden(lang)
        dto = context_service.get_settings(workspace_id, ctx)
        return Response(ContextGraphSettingsSerializer(dto).data)

    def put(self, request: Request, workspace_id: str, *args: Any, **kwargs: Any) -> Response:
        from application import context_service

        lang = detect_lang(request)
        ctx = get_auth_context(request)
        if not ctx.has_role(ROLE_ADMIN):
            return self._forbidden(lang)

        ser = ContextGraphSettingsSerializer(data=request.data)
        if not ser.is_valid():
            return Response(
                build_error_response(
                    "VALIDATION_ERROR",
                    lang,
                    details=[{"field": k, "errors": v} for k, v in ser.errors.items()],
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            dto = context_service.update_settings(
                workspace_id,
                ctx,
                enabled=ser.validated_data["enabled"],
                enabled_generators=ser.validated_data.get("enabled_generators"),
            )
        except context_service.NotFoundError as exc:
            return Response(
                build_error_response("NOT_FOUND", lang, message=str(exc)),
                status=status.HTTP_404_NOT_FOUND,
            )
        except ValidationError as exc:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message=str(exc)),
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(ContextGraphSettingsSerializer(dto).data)


class ContextGraphRebuildView(APIView):
    """POST /api/v1/workspaces/{workspace_id}/context-graph-settings/rebuild/
    (Issue #377, Task 9's "Rebuild now" button). Admin-only. Async — 202,
    not a synchronous rebuild in the request/response cycle."""

    def post(self, request: Request, workspace_id: str, *args: Any, **kwargs: Any) -> Response:
        from application import context_service

        lang = detect_lang(request)
        ctx = get_auth_context(request)
        if not ctx.has_role(ROLE_ADMIN):
            return Response(
                build_error_response(
                    "PERMISSION_DENIED",
                    lang,
                    message="Admin role required to rebuild the context graph.",
                ),
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            context_service.trigger_manual_rebuild(workspace_id, ctx)
        except context_service.NotFoundError as exc:
            return Response(
                build_error_response("NOT_FOUND", lang, message=str(exc)),
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response({"status": "queued"}, status=status.HTTP_202_ACCEPTED)


__all__ = [
    "LlmSettingsView",
    "LlmSettingsSerializer",
    "PromptTemplateView",
    "PromptTemplateSlotListView",
    "PromptTemplateSlotDetailView",
    "PromptTemplateSlotWriteSerializer",
    "PromptTemplateResetView",
    "PromptTemplateSerializer",
    "ReviewPolicyView",
    "ReviewPolicySerializer",
    "ContextGraphSettingsView",
    "ContextGraphSettingsSerializer",
    "ContextGraphRebuildView",
]
