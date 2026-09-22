"""
SE-Auditor REST endpoints (SysEng 2.0 Phase 3, "Auditor UI").

UMSETZUNGSPLAN_SYSENG_2.0.md §4, Phase 3. Two endpoints, both workspace-scoped
and Bearer-authenticated, both going exclusively through the Layer-2
``AuditService`` facade (ADR-01 — no direct model/RuleEngine access in the view;
the view only translates HTTP <-> service call):

  GET  /api/v1/workspaces/<workspace_id>/audit/
       Run the SE-Auditor for the workspace and return the findings (grouped by
       the frontend), each with a remediation proposal. The rigor tier is
       resolved from the workspace's active preset by the service. Optional
       query params: ``scope`` (document|project|global, default: project) and
       ``scope_artifact_id`` (required when scope=document).

  POST /api/v1/workspaces/<workspace_id>/audit/remediate/
       Apply the automatic remediation for a single finding (Adopt-Workflow).
       Body: {rule_id, artifact_ids: [...], scope?, scope_artifact_id?}. On
       success returns {applied: true, finding_resolved, created_link_id,
       proposal}. A finding without an unambiguous auto-fix returns HTTP 422
       with the reason (the UI turns this into a "Modify" / manual prompt).

  POST /api/v1/workspaces/<workspace_id>/audit/ai-review/
       SysEng 2.0 N8 (`audit.ai_review`, Phase 4b): run the SE-Auditor and
       bundle its findings into strategic refactoring packages via the LLM
       adapter (mock by default). Read-only / advisory — nothing is
       persisted, and every returned finding reference is resolved against
       the real audit run (see AiReviewService's referential-integrity
       guarantee). Optional query params: same ``scope`` /
       ``scope_artifact_id`` pair as the GET endpoint above.

  POST /api/v1/workspaces/<workspace_id>/audit/waivers/
       Grant a per-finding suppression (#569) through the standalone Auditor
       surface: the caller names a reported BLOCKER finding and justifies
       accepting that deviation. 201 on create, 200 on an idempotent replay of
       an identical active waiver. ``granted_by`` is derived from the
       AuthContext, never accepted from the body.

  GET  /api/v1/workspaces/<workspace_id>/audit/waivers/
       List the workspace's suppressions, filtered by lifecycle state
       (``?state=active|expired|all``, default ``active``); nothing is ever
       hidden from the count.

#569 status-code contract (spec §3.4.1), deliberately disjoint: no endpoint in
this module ever emits HTTP 422 — that status stays reserved for
``POST .../audit/remediate/`` ("Adopt not automatically applicable -> offer
Modify"). A rejected justification is a 400 ``WAIVER_REASON_REJECTED``, a named
finding that is not blocking a 400 ``WAIVER_FINDING_NOT_BLOCKING``, and an
expired-only row a 409 ``SUPPRESSION_EXPIRED``.

Module rationale: the codebase splits large view groups into dedicated modules
(settings_views.py, global_default_views.py, diagram_views.py, ...) rather than
growing the 5k-line views.py. This follows that established convention; the
Phase-3 plan's "views.py" is a rough placement hint, not a hard constraint.
"""
from __future__ import annotations

import logging
from typing import Any

from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from application.ai_review_service import AiReviewResponseError, AiReviewService
from application.audit_service import AuditService
from application.base import (
    NotFoundError,
    PermissionDeniedError,
    SuppressionExpiredError,
    ValidationError,
    WaiverFindingNotBlockingError,
    WaiverReasonPolicyViolation,
)
from baseline.exceptions import GovernanceAuthorityError
from baseline.waivers import assert_gate_waiver_authority
from traceability.audit import AuditScope
from rest_api.auth_enforcer import get_auth_context
from rest_api.serializers import (
    SanitizedCharField,
    UnknownFieldRejectionMixin,
    build_error_response,
    detect_lang,
)

logger = logging.getLogger(__name__)

_VALID_SCOPES = frozenset({"document", "project", "global"})

#: Suppression lifecycle states accepted by ``?state=`` on the waiver list
#: (#569/m2). ``active`` is the default; anything else is a 400.
_VALID_WAIVER_STATES = frozenset({"active", "expired", "all"})


# ---------------------------------------------------------------------------
# Request serializers (validation only — responses are service DTOs).
# ---------------------------------------------------------------------------


class RemediateRequestSerializer(
    UnknownFieldRejectionMixin, serializers.Serializer
):
    """Body of POST .../audit/remediate/ — identifies one finding to adopt.

    ``UnknownFieldRejectionMixin`` (#851) rejects request keys no declared
    field accepts instead of the DRF default of silently dropping them.
    """

    rule_id = serializers.CharField(max_length=64)
    artifact_ids = serializers.ListField(
        child=serializers.CharField(max_length=64),
        allow_empty=False,
    )
    scope = serializers.ChoiceField(
        choices=sorted(_VALID_SCOPES), required=False, allow_null=True
    )
    scope_artifact_id = serializers.CharField(
        max_length=64, required=False, allow_null=True, allow_blank=True
    )


def _parse_scopes(request: Request) -> list[AuditScope] | None:
    """Build the AuditScope list from query params, or None for the default.

    ``?scope=`` absent -> None (RuleEngine defaults to the project scope).
    ``scope=document`` requires ``scope_artifact_id``; a missing one raises
    ValueError which the caller maps to a 400.
    """
    scope = request.query_params.get("scope")
    if not scope:
        return None
    if scope not in _VALID_SCOPES:
        raise ValueError(f"Invalid scope '{scope}'.")
    artifact_id = request.query_params.get("scope_artifact_id") or None
    if scope == "document" and not artifact_id:
        raise ValueError("scope_artifact_id is required when scope=document.")
    return [AuditScope(scope, artifact_id=artifact_id)]


def _parse_pagination(request: Request) -> tuple[int | None, int]:
    """#622: optional ``?limit=&offset=`` to page past the findings cap.

    Absent ``limit`` -> ``(None, 0)``, preserving the default BLOCKER-
    preferred truncation exactly as before this was added. A present but
    invalid (non-integer) value raises ValueError, mapped to a 400 by the
    caller — same pattern as ``_parse_scopes``.
    """
    raw_limit = request.query_params.get("limit")
    if raw_limit is None:
        return None, 0
    try:
        limit = int(raw_limit)
    except ValueError as exc:
        raise ValueError("limit must be an integer.") from exc
    raw_offset = request.query_params.get("offset", "0")
    try:
        offset = int(raw_offset)
    except ValueError as exc:
        raise ValueError("offset must be an integer.") from exc
    return limit, offset


def _parse_include_suppressed(request: Request) -> bool:
    """#569/m2: parse ``?include_suppressed=true|false`` strictly.

    Absent -> ``True`` (O3: nothing is hidden by default). Only the literals
    ``true``/``false`` (case-insensitive) are accepted; every other value
    raises ValueError so the caller answers 400 ``VALIDATION_ERROR`` instead
    of silently coercing a typo into a filter (spec E15/AC-569-22).
    """
    raw = request.query_params.get("include_suppressed")
    if raw is None:
        return True
    lowered = str(raw).strip().lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    raise ValueError("include_suppressed must be 'true' or 'false'.")


def _parse_waiver_state(request: Request) -> str:
    """#569/m2: parse ``?state=active|expired|all`` (default ``active``).

    Anything else raises ValueError, mapped to 400 ``VALIDATION_ERROR`` by the
    caller (spec E11/AC-569-22).
    """
    state = request.query_params.get("state") or "active"
    if state not in _VALID_WAIVER_STATES:
        raise ValueError(
            f"Unknown suppression state {state!r}; expected one of "
            f"{sorted(_VALID_WAIVER_STATES)}."
        )
    return state


def _assert_workspace_in_tenant(workspace_id: Any, ctx: Any) -> None:
    """Raise NotFoundError when *workspace_id* is not in the caller's tenant.

    The workspace-scoped routes carry the id in the URL, and the RuleEngine
    itself is tenant-filtered rather than workspace-validating, so a foreign
    workspace would otherwise fall through to a finding-level error. #569
    answers 404 ``NOT_FOUND`` for it (E7/E13/E16), matching the existing
    ``WorkspaceAuditView`` convention.

    The existence check is delegated to
    :meth:`auth_tenancy.services.authorization.AuthorizationService.workspace_exists_in_tenant`
    (a read-only service) rather than querying the model here — the REST layer
    performs no direct ORM access (REQ-066 ratchet).
    """
    from auth_tenancy.services.authorization import AuthorizationService

    if not AuthorizationService().workspace_exists_in_tenant(
        workspace_id=workspace_id, tenant_id=ctx.tenant_id
    ):
        raise NotFoundError(
            f"Workspace '{workspace_id}' was not found in the caller's tenant."
        )


def _assert_waiver_surface_access(ctx: Any) -> None:
    """Require approval authority for the suppression list (#569/E12).

    The waiver list is the governance *management* surface for suppression
    records, so it evaluates the same single authority choke point as the
    grant path (:func:`baseline.waivers.assert_gate_waiver_authority`:
    Admin/Approver and, for API keys, the ADMIN tier) and remaps the domain
    error to ``PermissionDeniedError`` (403 ``PERMISSION_DENIED``). The report
    endpoint stays readable by any workspace member — only this dedicated
    management list is authority-gated.
    """
    try:
        assert_gate_waiver_authority(ctx)
    except GovernanceAuthorityError as exc:
        raise PermissionDeniedError(str(exc)) from exc


class AwareDateTimeField(serializers.DateTimeField):
    """ISO-8601 datetime field that refuses a naive (offset-less) value.

    DRF's ``DateTimeField`` silently attaches the project timezone to a naive
    timestamp. #569/E3/D2 requires such a value to be *rejected* (400): an
    expiry the caller did not fully specify must not be reinterpreted behind
    its back — the service repeats the check defensively.
    """

    def enforce_timezone(self, value: Any) -> Any:
        if value is not None and timezone.is_naive(value):
            raise serializers.ValidationError(
                "Datetime must be timezone-aware (ISO-8601 with 'Z' or an "
                "explicit UTC offset)."
            )
        return super().enforce_timezone(value)


class WaiverCreateSerializer(
    UnknownFieldRejectionMixin, serializers.Serializer
):
    """Body of ``POST .../audit/waivers/`` (#569) — names and justifies one finding.

    ``UnknownFieldRejectionMixin`` (#851) rejects any undeclared key with 400,
    which is what keeps ``granted_by`` out of the request contract: the author
    is derived from the AuthContext only (§3.2/AC-569-30).

    ``reason`` is intentionally ``allow_blank=True`` here: a blank or
    placeholder justification is *not* a shape error but a policy violation,
    and must surface as 400 ``WAIVER_REASON_REJECTED`` from the single Layer-1
    policy (:func:`baseline.waivers.validate_waiver_reason`), not as a generic
    serializer ``VALIDATION_ERROR`` (spec E4/AC-569-02). ``expires_at`` is
    optional; ``None`` means unbounded.

    ``scope``/``scope_artifact_id`` select the scope for the *existence check*
    only (C1) — the persisted scope always comes from the matched finding.
    """

    rule_id = serializers.CharField(
        max_length=64, help_text="SE-Auditor rule being suppressed, e.g. 'TRACE-P1'."
    )
    artifact_ids = serializers.ListField(
        child=serializers.CharField(max_length=64),
        allow_empty=True,
        required=False,
        default=list,
        help_text=(
            "Artifacts the finding concerns, as returned by the audit report "
            "(empty for graph-level findings)."
        ),
    )
    scope = serializers.ChoiceField(
        choices=sorted(_VALID_SCOPES),
        required=False,
        allow_null=True,
        help_text=(
            "Optional baseline scope used only to locate the finding for the "
            "existence check (document|project|global)."
        ),
    )
    scope_artifact_id = serializers.CharField(
        max_length=64,
        required=False,
        allow_null=True,
        allow_blank=True,
        help_text="Document root; required when scope='document'.",
    )
    reason = SanitizedCharField(
        max_length=2000,
        allow_blank=True,
        help_text=(
            "Mandatory justification for accepting this single deviation; "
            "recorded on the waiver and in the audit log."
        ),
    )
    expires_at = AwareDateTimeField(
        required=False,
        allow_null=True,
        default=None,
        help_text=(
            "Optional expiry (ISO-8601, timezone-aware). Omitted/null means "
            "unbounded; an already-past or naive value is rejected with 400."
        ),
    )


class WorkspaceAuditView(APIView):
    """GET /api/v1/workspaces/<workspace_id>/audit/ — run the SE-Auditor."""

    def get(
        self, request: Request, workspace_id: str, *args: Any, **kwargs: Any
    ) -> Response:
        lang = detect_lang(request)
        try:
            scopes = _parse_scopes(request)
            limit, offset = _parse_pagination(request)
            include_suppressed = _parse_include_suppressed(request)
        except ValueError as exc:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message=str(exc)),
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            ctx = get_auth_context(request)
            _assert_workspace_in_tenant(workspace_id, ctx)
            report = AuditService().run_audit(
                workspace_id,
                ctx,
                scopes=scopes,
                limit=limit,
                offset=offset,
                include_suppressed=include_suppressed,
            )
            return Response(report.to_dict())
        except NotFoundError as exc:
            return Response(
                build_error_response("NOT_FOUND", lang, message=str(exc)),
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception:
            # #569 review BR-569-01: an unexpected fault on a governance
            # surface must be loud. Returning a Response means Django's
            # ``django.request`` logger never fires, so without this line the
            # failure (leaked L1 domain error, TenantContextNotSetError, DB
            # error) would be undiagnosable — the exact safety net the spec
            # built deliberately (spec §3.4.2 / N6).
            logger.exception(
                "SE-Auditor report failed for workspace %s", workspace_id
            )
            return Response(
                build_error_response("INTERNAL_SERVER_ERROR", lang),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class WorkspaceAuditWaiverView(APIView):
    """Per-finding SE-Auditor suppressions, standalone (#569).

    ``POST .../audit/waivers/`` grants a suppression for one reported BLOCKER
    finding:

      * 201 — a new waiver row was persisted;
      * 200 — an identical active waiver was already on file (idempotent);
      * 400 ``WAIVER_REASON_REJECTED`` — the justification fails the policy;
      * 400 ``WAIVER_FINDING_NOT_BLOCKING`` — the named finding is not a
        reported BLOCKER (unknown, or only a WARNING);
      * 400 ``VALIDATION_ERROR`` — malformed body, unknown field (incl.
        ``granted_by``), invalid scope, missing document root, or a naive /
        already-past ``expires_at``;
      * 403 ``PERMISSION_DENIED`` — no Admin/Approver authority or an API key
        below the ADMIN tier;
      * 404 ``NOT_FOUND`` — workspace not in the caller's tenant;
      * 409 ``SUPPRESSION_EXPIRED`` — only an expired row exists for the key;
      * 500 ``INTERNAL_SERVER_ERROR`` — unexpected server error.

    ``GET .../audit/waivers/`` lists suppressions, ``?state=active|expired|all``
    (default ``active``), returning ``{waivers, counts}``.

    This view answers the standard ``{"error": {code, message, details}}``
    envelope for every failure and never emits 422 (spec E18) — 422 stays
    reserved for :class:`WorkspaceAuditRemediateView`.
    """

    def post(
        self, request: Request, workspace_id: str, *args: Any, **kwargs: Any
    ) -> Response:
        lang = detect_lang(request)
        ser = WaiverCreateSerializer(data=request.data)
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
        data = ser.validated_data
        try:
            ctx = get_auth_context(request)
            _assert_workspace_in_tenant(workspace_id, ctx)
            view, created = AuditService().suppress_finding(
                workspace_id,
                ctx,
                rule_id=data["rule_id"],
                artifact_ids=data.get("artifact_ids") or [],
                scope=data.get("scope"),
                scope_artifact_id=data.get("scope_artifact_id") or None,
                reason=data["reason"],
                expires_at=data.get("expires_at"),
            )
        except WaiverReasonPolicyViolation as exc:
            return Response(
                build_error_response(exc.error_code, lang, message=str(exc)),
                status=status.HTTP_400_BAD_REQUEST,
            )
        except WaiverFindingNotBlockingError as exc:
            return Response(
                build_error_response(exc.error_code, lang, message=str(exc)),
                status=status.HTTP_400_BAD_REQUEST,
            )
        except SuppressionExpiredError as exc:
            return Response(
                build_error_response(exc.error_code, lang, message=str(exc)),
                status=status.HTTP_409_CONFLICT,
            )
        except PermissionDeniedError as exc:
            return Response(
                build_error_response("PERMISSION_DENIED", lang, message=str(exc)),
                status=status.HTTP_403_FORBIDDEN,
            )
        except NotFoundError as exc:
            return Response(
                build_error_response("NOT_FOUND", lang, message=str(exc)),
                status=status.HTTP_404_NOT_FOUND,
            )
        except ValidationError as exc:
            # Remaining shape/invariant failures (invalid scope, missing
            # document root, naive/past expiry from the service's defensive
            # guard). Deliberately 400 — never 422 (spec E18).
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message=str(exc)),
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception:
            # #569 review BR-569-01: log before masking — see the sibling
            # comment on WorkspaceAuditView.get. Rule/artifact identity is the
            # useful context for a governance write that blew up.
            logger.exception(
                "Waiver grant failed for workspace %s (rule=%s, artifacts=%s)",
                workspace_id,
                data.get("rule_id"),
                data.get("artifact_ids"),
            )
            return Response(
                build_error_response("INTERNAL_SERVER_ERROR", lang),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(
            view.to_dict(),
            status=(
                status.HTTP_201_CREATED if created else status.HTTP_200_OK
            ),
        )

    def get(
        self, request: Request, workspace_id: str, *args: Any, **kwargs: Any
    ) -> Response:
        lang = detect_lang(request)
        try:
            state = _parse_waiver_state(request)
        except ValueError as exc:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message=str(exc)),
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            ctx = get_auth_context(request)
            _assert_workspace_in_tenant(workspace_id, ctx)
            _assert_waiver_surface_access(ctx)
            all_views = AuditService().list_suppressions(
                workspace_id, ctx, state="all"
            )
        except PermissionDeniedError as exc:
            return Response(
                build_error_response("PERMISSION_DENIED", lang, message=str(exc)),
                status=status.HTTP_403_FORBIDDEN,
            )
        except NotFoundError as exc:
            return Response(
                build_error_response("NOT_FOUND", lang, message=str(exc)),
                status=status.HTTP_404_NOT_FOUND,
            )
        except ValidationError as exc:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message=str(exc)),
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception:
            # #569 review BR-569-01: log before masking — see the sibling
            # comment on WorkspaceAuditView.get.
            logger.exception(
                "Waiver list failed for workspace %s", workspace_id
            )
            return Response(
                build_error_response("INTERNAL_SERVER_ERROR", lang),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # counts describe the *whole* set (both states), so a caller can see
        # whether a filter hides anything; ``waivers`` is the filtered view.
        counts = {
            "active": sum(1 for v in all_views if v.state == "active"),
            "expired": sum(1 for v in all_views if v.state == "expired"),
        }
        waivers = [
            v.to_dict() for v in all_views if state == "all" or v.state == state
        ]
        return Response({"waivers": waivers, "counts": counts})


class WorkspaceAuditRemediateView(APIView):
    """POST /api/v1/workspaces/<workspace_id>/audit/remediate/ — Adopt-Workflow."""

    def post(
        self, request: Request, workspace_id: str, *args: Any, **kwargs: Any
    ) -> Response:
        lang = detect_lang(request)
        ser = RemediateRequestSerializer(data=request.data)
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
        data = ser.validated_data
        try:
            result = AuditService().remediate(
                workspace_id,
                get_auth_context(request),
                rule_id=data["rule_id"],
                artifact_ids=data["artifact_ids"],
                scope=data.get("scope"),
                scope_artifact_id=data.get("scope_artifact_id") or None,
            )
            return Response(result.to_dict(), status=status.HTTP_200_OK)
        except PermissionDeniedError as exc:
            return Response(
                build_error_response("PERMISSION_DENIED", lang, message=str(exc)),
                status=status.HTTP_403_FORBIDDEN,
            )
        except NotFoundError as exc:
            return Response(
                build_error_response("NOT_FOUND", lang, message=str(exc)),
                status=status.HTTP_404_NOT_FOUND,
            )
        except ValidationError as exc:
            # A finding without an unambiguous auto-fix, or a rejected
            # correction. 422 = "understood, but cannot apply automatically";
            # the UI renders this as a manual "Modify" action.
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message=str(exc)),
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        except Exception:
            return Response(
                build_error_response("INTERNAL_SERVER_ERROR", lang),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class WorkspaceAuditAiReviewView(APIView):
    """POST /api/v1/workspaces/<workspace_id>/audit/ai-review/ — SysEng 2.0 N8.

    Runs the SE-Auditor (Phase 3) and bundles its findings into strategic
    refactoring packages via the LLM adapter. Advisory only — no data is
    mutated; individual findings are still fixed through the existing
    ``audit/remediate/`` Adopt-Workflow.
    """

    def post(
        self, request: Request, workspace_id: str, *args: Any, **kwargs: Any
    ) -> Response:
        lang = detect_lang(request)
        try:
            scopes = _parse_scopes(request)
        except ValueError as exc:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message=str(exc)),
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            result = AiReviewService().review(
                workspace_id, get_auth_context(request), scopes=scopes
            )
            return Response(result.to_dict())
        except NotFoundError as exc:
            return Response(
                build_error_response("NOT_FOUND", lang, message=str(exc)),
                status=status.HTTP_404_NOT_FOUND,
            )
        except AiReviewResponseError:
            # Deviation from Task 5 brief (finding claims logging is present
            # everywhere): no logger.exception ran here before this fix, so
            # the real exception was never visible to operators once its
            # message was dropped from the response. Adding it here restores
            # observability while still masking the client-facing message.
            logger.exception("AI review failed for workspace %s", workspace_id)
            return Response(
                build_error_response("INTERNAL_SERVER_ERROR", lang),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        except Exception:
            return Response(
                build_error_response("INTERNAL_SERVER_ERROR", lang),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


__all__ = [
    "WorkspaceAuditView",
    "WorkspaceAuditWaiverView",
    "WorkspaceAuditRemediateView",
    "WorkspaceAuditAiReviewView",
]
