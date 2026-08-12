"""WorkflowTransitionsMixin — shared workflow REST actions (REQ-165 / REQ-167).

Adds the two workflow endpoints that every workflow-backed entity ViewSet needs:

    GET  /api/v1/<entity>/{pk}/transitions/       → current state + allowed moves
    POST /api/v1/<entity>/{pk}/transitions/       → perform a gated transition
    POST /api/v1/<entity>/{pk}/reactivate/        → undo a soft-delete (GH-443)
    GET  /api/v1/<entity>/{pk}/workflow-history/   → append-only audit trail

The WorkflowEngine (via ``WorkflowFacade``) is the single authority for the
transition: role gates, change_reason and signature gates are enforced there and
their errors propagate unchanged to the HTTP layer. This mixin only translates
between HTTP and the facade — no business logic (REQ-L3-RA001-004).

Extracted from the original inline ``RequirementViewSet`` actions so all entity
types (Requirement, StakeholderNeed, Adr, Risk, Issue, ChangeRequest, TestCase)
share one implementation and one response contract.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from rest_framework import status
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from application.preset_policy_service import get_preset_policy_service
from application.services import (
    NotFoundError,
    PermissionDeniedError,
    WorkflowFacade,
)
from rest_api.auth_enforcer import get_auth_context
from rest_api.serializers import build_error_response, detect_lang

#: Keys that are never writable through PATCH on any entity, whether or not the
#: serializer happens to declare them (#269, finding 5). ``workspace_id`` is a
#: create-time field — a PATCH carrying it is an attempted cross-workspace move,
#: which has to go through the dedicated move flow. ``is_admin`` is not a field
#: of any entity at all; it is listed explicitly so a mass-assignment probe gets
#: a precise error instead of the generic "unknown field".
_PROTECTED_PATCH_FIELDS = frozenset(
    {
        "artifact_id",
        "created_at",
        "created_by_id",
        "id",
        "is_admin",
        "modified_by_id",
        "tenant_id",
        "updated_at",
        "uid",
        "version",
        "workspace_id",
    }
)

#: Keys accepted on every entity even when the serializer does not declare them.
#: ``change_reason`` and ``custom_fields`` are sent by the UI detail panels on
#: every save, and ``expected_version`` carries optimistic-locking state, so
#: rejecting them as "unknown" would break working save paths.
_ALWAYS_ALLOWED_PATCH_FIELDS = frozenset(
    {"change_reason", "custom_fields", "expected_version"}
)


def _same_status(candidate: Any, current: str) -> bool:
    """Compare a client-supplied status against the stored one, leniently.

    Status labels are mirrored across the WorkflowEngine and the entity's own
    column and still differ in casing between entity types (``'draft'`` for the
    persistence-app entities vs ``'Draft'`` for ``Adr``; TestCase joined the
    lowercase group in GH-453). Comparing case-insensitively keeps a harmless
    echo of the value the client just read via GET from being treated as a
    status *change*, which under #263 cost the user the rest of their edit.

    It also absorbs the GH-453 rename for clients that cached the old
    Title-Case TestCase status and echo it back on the next PATCH.
    """
    return str(candidate).strip().casefold() == str(current).strip().casefold()


class WorkflowTransitionsMixin:
    """Adds GET/POST ``transitions/`` and GET ``workflow-history/`` actions.

    Subclasses must declare::

        workflow_item_type: str   # e.g. "Adr", "Risk", "Requirement", ...

    and implement::

        _resolve_workflow_target(self, pk, ctx) -> tuple[UUID, UUID]
            # returns (item_id, workspace_id); raises NotFoundError /
            # PermissionDeniedError on not-found or permission denied, and
            # ValueError on a malformed pk.

    Subclasses may override ``_serialize_after_transition`` to embed the refreshed
    entity in the transition POST response.
    """

    workflow_item_type: str = ""

    def _resolve_workflow_target(self, pk: str, ctx: Any) -> tuple[UUID, UUID]:
        """Return ``(item_id, workspace_id)`` for the entity identified by *pk*.

        Must raise ``NotFoundError`` / ``PermissionDeniedError`` when the entity
        is missing or inaccessible, and ``ValueError`` on a malformed pk.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement _resolve_workflow_target"
        )

    def _serialize_after_transition(self, item_id: UUID, ctx: Any) -> dict | None:
        """Override to embed refreshed entity data in the transition POST response.

        Returning ``None`` (the default) yields the bare state envelope
        ``{id, previous_state, new_state}``.
        """
        return None

    @action(detail=True, methods=["get", "post"], url_path="transitions")
    def transitions(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """Workflow transitions for a workflow-backed entity (REQ-143).

        GET  → ``{current_state, states, allowed_transitions[]}`` — the moves
               allowed from the current state. Drives a transition-aware UI.

        POST → body ``{target_state, change_reason?, credential?}``; performs the
               transition through the WorkflowEngine (role / change_reason /
               signature gates enforced) and returns the new state envelope,
               optionally with the refreshed entity embedded.
        """
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            item_id, workspace_id = self._resolve_workflow_target(pk, ctx)
        except NotFoundError as exc:
            return self._error(exc, lang)
        except PermissionDeniedError as exc:
            return self._error(exc, lang)
        except ValueError:
            return Response(
                build_error_response("NOT_FOUND", lang),
                status=status.HTTP_404_NOT_FOUND,
            )

        facade = WorkflowFacade()

        if request.method.upper() == "GET":
            avail = facade.get_available_transitions(
                item_id=item_id,
                ctx=ctx,
                item_type=self.workflow_item_type,
                workspace_id=workspace_id,
            )
            # REQ-169: surface the EFFECTIVE change_reason requirement. When the
            # workspace preset mandates a change_reason (Extended rigor), the
            # facade's global gate (WorkflowFacade._check_change_reason) rejects
            # every empty-reason transition regardless of the per-transition flag.
            # If the GET response only reported the per-transition flag, the UI
            # would hide the textarea for those transitions and POST an empty
            # reason that the facade then blocks. Report the OR of both so the UI
            # always collects a reason when it will actually be required.
            preset_requires = get_preset_policy_service().is_change_reason_required(
                str(workspace_id)
            )
            return Response(
                {
                    "current_state": avail.current_state,
                    "states": list(avail.states),
                    "allowed_transitions": [
                        {
                            "target_state": t.to_state,
                            "requires_change_reason": (
                                t.requires_change_reason or preset_requires
                            ),
                            "signature_gate": t.signature_gate,
                        }
                        for t in avail.transitions
                    ],
                }
            )

        # POST → perform the transition.
        target_state = request.data.get("target_state")
        if not target_state:
            return Response(
                build_error_response(
                    "VALIDATION_ERROR", lang, message="target_state is required"
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        change_reason = request.data.get("change_reason", "") or ""
        credential = request.data.get("credential", "") or ""
        try:
            result = facade.transition(
                item_id=item_id,
                target_state=target_state,
                change_reason=change_reason,
                ctx=ctx,
                credential=credential,
                item_type=self.workflow_item_type,
                workspace_id=workspace_id,
            )
        except Exception as exc:
            return self._error(exc, lang)

        body: dict[str, Any] = {
            "id": pk,
            "previous_state": result.previous_state,
            "new_state": result.new_state,
        }
        embedded = self._serialize_after_transition(item_id, ctx)
        if embedded is not None:
            body.update(embedded)
        return Response(body)

    @action(detail=True, methods=["post"], url_path="reactivate")
    def reactivate(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """POST ``reactivate/`` — undo a soft-delete (GH-443).

        DELETE on these entities is a soft-delete: the row survives with
        ``status="outdated"``. This restores it to the state it held
        immediately before the delete, and is the only way back — "outdated"
        is a system state outside every preset's state list, so
        ``POST .../transitions/`` cannot leave it.

        Responses:
            200 ``{id, previous_state, new_state}`` (plus the refreshed entity
                when the ViewSet embeds one, exactly as ``transitions/`` does),
            400 when the item is not currently outdated,
            403 without the write role,
            404 when the item does not exist.
        """
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            item_id, workspace_id = self._resolve_workflow_target(pk, ctx)
        except NotFoundError as exc:
            return self._error(exc, lang)
        except PermissionDeniedError as exc:
            return self._error(exc, lang)
        except ValueError:
            return Response(
                build_error_response("NOT_FOUND", lang),
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            result = WorkflowFacade().reactivate(
                item_id=item_id,
                ctx=ctx,
                item_type=self.workflow_item_type,
                workspace_id=workspace_id,
            )
        except Exception as exc:
            return self._error(exc, lang)

        body: dict[str, Any] = {
            "id": pk,
            "previous_state": result.previous_state,
            "new_state": result.new_state,
        }
        embedded = self._serialize_after_transition(item_id, ctx)
        if embedded is not None:
            body.update(embedded)
        return Response(body)

    @action(detail=True, methods=["get"], url_path="workflow-history")
    def workflow_history(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """GET ``workflow-history/`` — transition audit trail (REQ-144).

        Returns the append-only WorkflowHistoryEntry list for this entity,
        oldest first: actor, from/to state, change_reason, timestamp, and whether
        the transition was signature-sealed. The seal value itself is never
        exposed — only a ``sealed`` boolean.
        """
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            item_id, workspace_id = self._resolve_workflow_target(pk, ctx)
        except NotFoundError as exc:
            return self._error(exc, lang)
        except PermissionDeniedError as exc:
            return self._error(exc, lang)
        except ValueError:
            return Response(
                build_error_response("NOT_FOUND", lang),
                status=status.HTTP_404_NOT_FOUND,
            )

        facade = WorkflowFacade()
        entries = facade.get_history(
            item_id=item_id,
            ctx=ctx,
            item_type=self.workflow_item_type,
            workspace_id=workspace_id,
        )
        return Response(
            [
                {
                    "id": str(entry.id),
                    "from_state": entry.from_state,
                    "to_state": entry.to_state,
                    "actor": entry.transitioned_by,
                    "change_reason": entry.change_reason,
                    "transitioned_at": entry.transitioned_at.isoformat(),
                    "sealed": bool(entry.signature_seal),
                }
                for entry in entries
            ]
        )

    def _current_status(self, pk: str, ctx: Any) -> str | None:
        """Return the entity's current status, as the GET representation reports it.

        Override in ViewSets whose serializer exposes ``status`` so
        :meth:`_validate_patch_payload` can tell an unchanged status echo apart
        from an actual status change (#263). Returning ``None`` means "cannot
        determine" and makes the guard fall back to accepting-and-ignoring the
        field, because losing the rest of the payload is the worse failure.
        """
        return None

    def _validate_patch_payload(
        self,
        request: Request,
        lang: str,
        *,
        serializer_cls: type | None = None,
        pk: str | None = None,
        ctx: Any = None,
    ) -> Response | None:
        """Validate PATCH field names; return a 400 Response or ``None`` if OK.

        Three rules, all reported as field-level errors in the standard error
        envelope so a client can point at the offending key:

        ``status`` (#263 / QA-123)
            Status only moves through the WorkflowEngine
            (``POST .../transitions/``). A payload whose ``status`` *equals* the
            current one changes nothing, so it is accepted and the field
            ignored — the UI detail panels resend the whole form and the
            previous blanket rejection threw away the description the user had
            just typed. A *differing* status is still refused, so a real status
            change can never be silently swallowed.

        Protected fields (#269, finding 5)
            Server-owned or privilege-shaped keys (``workspace_id``,
            ``is_admin``, ``version``, ...) used to be dropped by DRF without a
            word while the request still reported 200 — a cross-workspace move
            or a mass-assignment attempt looked like it had succeeded.

        Unknown fields (#269, finding 5)
            A key the serializer does not declare (a typo, or ``title`` on
            glossary, which uses ``term``) used to return 200 and bump
            ``version`` although nothing was written. Rejecting it keeps
            ``version`` an honest change counter.
        """
        data = request.data
        if not isinstance(data, dict):
            return None

        known: set[str] = set(_ALWAYS_ALLOWED_PATCH_FIELDS)
        if serializer_cls is not None:
            # Instantiated without context on purpose: that yields the
            # unfiltered field superset, so a field merely hidden by the
            # workspace's rigor preset is not mistaken for an unknown one.
            known |= set(serializer_cls().fields)

        errors: list[dict[str, Any]] = []
        for field in data:
            if field == "status":
                exposed = "status" in known
                current = None
                if exposed and pk is not None:
                    try:
                        current = self._current_status(pk, ctx)
                    except Exception:  # noqa: BLE001 — never mask the PATCH itself
                        current = None
                if exposed and (current is None or _same_status(data[field], current)):
                    # Either a verbatim echo of the current status, or a status
                    # we could not read back. Both are accepted and ignored:
                    # discarding the rest of the payload (#263) is the worse
                    # outcome, and the response body still reports the real,
                    # unchanged status.
                    continue
                errors.append(
                    {
                        "field": "status",
                        "errors": [
                            "status cannot be changed via PATCH; use "
                            "POST .../transitions/ with a target_state "
                            "instead."
                        ],
                    }
                )
                continue
            if field in _PROTECTED_PATCH_FIELDS:
                errors.append(
                    {
                        "field": field,
                        "errors": [f"'{field}' is read-only and cannot be set via PATCH."],
                    }
                )
                continue
            if field not in known:
                errors.append(
                    {"field": field, "errors": [f"Unknown field '{field}'."]}
                )

        if errors:
            # Keep a human-readable summary in ``message`` as well: the detail
            # panels surface ``error.message`` directly in their save alert, so
            # field-only errors would degrade into a generic "validation error".
            summary = (
                errors[0]["errors"][0]
                if len(errors) == 1
                else "Invalid fields: "
                + ", ".join(str(e["field"]) for e in errors)
            )
            return Response(
                build_error_response(
                    "VALIDATION_ERROR", lang, details=errors, message=summary
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        return None

    @staticmethod
    def _error(exc: Exception, lang: str) -> Response:
        """Translate a service exception into the standard error Response.

        Delegates to ``rest_api.views._service_error_response`` (single source of
        truth for the exception→HTTP mapping). Imported lazily to avoid a circular
        import: ``rest_api.views`` imports this mixin at module load time.
        """
        from rest_api.views import _service_error_response

        return _service_error_response(exc, lang)
