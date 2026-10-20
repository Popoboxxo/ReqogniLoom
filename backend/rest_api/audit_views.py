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
       query params: ``scope`` (document|project|global, default: project),
       ``scope_artifact_id`` (required when scope=document), ``page_size`` /
       ``limit`` (aliases, >= 1, capped at 500) + ``offset`` for a sequential
       walk,
       ``include_suppressed`` (default true), and the #1262 finding filters
       ``rule_id`` / ``severity`` / ``artifact_type``. The 200 body carries
       ``counts`` (ground truth over the full run), ``page_counts`` (the
       returned window) and ``next_offset`` (the cursor, #1382).

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
from collections.abc import Callable
from typing import Any

from django.utils import timezone
from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
)
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
from rest_api.auth_enforcer import get_auth_context
from rest_api.openapi import ErrorResponseSerializer
from rest_api.serializers import (
    SanitizedCharField,
    UnknownFieldRejectionMixin,
    build_error_response,
    detect_lang,
)
from traceability.audit import AuditScope, get_rule_catalogue
from traceability.audit.finding_filters import (
    finding_matches,
    normalize_rule_ids,
    normalize_severities,
    resolve_artifact_ids_for_type,
)

logger = logging.getLogger(__name__)

_VALID_SCOPES = frozenset({"document", "project", "global"})

#: Suppression lifecycle states accepted by ``?state=`` on the waiver list
#: (#569/m2). ``active`` is the default; anything else is a 400.
_VALID_WAIVER_STATES = frozenset({"active", "expired", "all"})


# ---------------------------------------------------------------------------
# OpenAPI-only response schemas (#1383).
#
# The audit view returns ``AuditReport.to_dict()`` verbatim — these serializers
# are never used to serialize a response. They exist so the generated document
# states the report contract (and, before #1383, advertised no query parameters
# and no response body at all). Keep them in sync with ``to_dict()``.
# ---------------------------------------------------------------------------


class AuditCountsSerializer(serializers.Serializer):
    """Ground-truth count block (``counts``, #1382) over the full run.

    Computed before the response window, so it is identical on every page of a
    sequential walk (and on the default capped run). ``blockers`` is
    **waiver-aware**: a blocker matched by an active suppression is excluded.
    ``warnings`` and ``total`` are raw, so the composition that holds is
    ``blockers + warnings + suppressed_blockers == total`` — not
    ``blockers + warnings == total``. ``suppressed`` counts suppressed findings
    of either severity.
    """

    total = serializers.IntegerField(
        help_text=(
            "Raw finding count over the full (pre-window) run; identical on "
            "every page."
        )
    )
    blockers = serializers.IntegerField(
        help_text=(
            "Effective (waiver-aware) BLOCKER count over the full run — a "
            "blocker covered by an active suppression is excluded. Equals "
            "total_blockers_available / total_effective_blockers."
        )
    )
    warnings = serializers.IntegerField(
        help_text=(
            "Raw WARNING count over the full run. Includes suppressed "
            "warnings (nothing is hidden)."
        )
    )
    suppressed = serializers.IntegerField(
        help_text=(
            "Suppressed findings of either severity in the full run; equals "
            "total_suppressed_available."
        )
    )
    suppressed_blockers = serializers.IntegerField(
        help_text=(
            "Suppressed BLOCKERs in the full run — the subset excluded from "
            "`blockers`. Equals total_suppressed_blockers_available."
        )
    )


class AuditPageCountsSerializer(serializers.Serializer):
    """Window count block (``page_counts``, #1382) over the returned ``findings``.

    These are the raw, page-local counters (the pre-#1382 ``counts``
    semantics): ``blockers`` includes suppressed blockers, so
    ``blockers + warnings == total`` holds unconditionally (``Severity`` has
    exactly two members). They shrink and grow with ``page_size`` /
    ``offset`` — use ``counts`` for a stable total.
    """

    total = serializers.IntegerField(
        help_text="Number of findings in this response (`len(findings)`)."
    )
    blockers = serializers.IntegerField(
        help_text=(
            "Raw BLOCKER count in this window — includes suppressed blockers "
            "(unlike counts.blockers, which is waiver-aware)."
        )
    )
    warnings = serializers.IntegerField(
        help_text="Raw WARNING count in this window."
    )
    suppressed = serializers.IntegerField(
        help_text="Suppressed findings in this window."
    )
    suppressed_blockers = serializers.IntegerField(
        help_text="Suppressed BLOCKERs in this window."
    )


class AuditFindingSerializer(serializers.Serializer):
    """Schema view of one returned finding (``AuditFindingView.to_dict()``)."""

    index = serializers.IntegerField()
    finding_key = serializers.CharField()
    rule_id = serializers.CharField()
    severity = serializers.CharField()
    message = serializers.CharField()
    artifact_ids = serializers.ListField(child=serializers.CharField())
    scope = serializers.CharField(required=False, allow_null=True)
    scope_artifact_id = serializers.CharField(required=False, allow_null=True)
    suppressed = serializers.BooleanField(required=False)
    suppressed_until = serializers.CharField(required=False, allow_null=True)
    suppression_reason = serializers.CharField(required=False, allow_null=True)
    suppression_id = serializers.CharField(required=False, allow_null=True)
    remediation = serializers.DictField()


class AuditReportSerializer(serializers.Serializer):
    """200 body of ``GET .../audit/`` (#1382 semantics documented inline)."""

    tier = serializers.CharField()
    scope = serializers.CharField(allow_null=True)
    scope_artifact_id = serializers.CharField(allow_null=True)
    counts = AuditCountsSerializer(
        help_text=(
            "Ground truth over the full (pre-window, post-filter) result set; "
            "independent of page_size/limit/offset. `counts.blockers` is "
            "waiver-aware, so `blockers + warnings + suppressed_blockers == "
            "total` (not `blockers + warnings == total`)."
        )
    )
    page_counts = AuditPageCountsSerializer(
        help_text=(
            "Raw counters restricted to the returned `findings` window "
            "(`blockers + warnings == total`, suppressed blockers included). "
            "Use `counts` for the stable total."
        )
    )
    truncated = serializers.BooleanField(
        help_text=(
            "With an explicit page size: more findings exist past this window. "
            "Without one: the default BLOCKER-preferred cap was applied."
        )
    )
    total_findings_available = serializers.IntegerField()
    total_blockers_available = serializers.IntegerField(
        help_text="Effective (waiver-aware) blockers in the full run."
    )
    total_effective_blockers = serializers.IntegerField(
        help_text="Alias of total_blockers_available (issue #1150)."
    )
    total_warnings_available = serializers.IntegerField()
    total_suppressed_available = serializers.IntegerField()
    total_suppressed_blockers_available = serializers.IntegerField()
    suppressed_filtered = serializers.IntegerField(
        help_text=(
            "Findings removed by include_suppressed=false. On the unpaged run "
            "this explains the `page_counts.total` vs `counts.total` gap "
            "(counts still describes the full run); with an explicit page size "
            "that gap is the window truncation plus this value."
        )
    )
    offset = serializers.IntegerField()
    next_offset = serializers.IntegerField(
        allow_null=True,
        help_text=(
            "Offset of the next window when paging with page_size/limit; null "
            "otherwise (the default capped run is not a sequential walk)."
        ),
    )
    findings = AuditFindingSerializer(many=True)


_AUDIT_QUERY_PARAMETERS = [
    OpenApiParameter(
        name="page_size",
        # drf-spectacular only accepts a basic type, a Serializer or a raw
        # schema dict here — a serializers.IntegerField instance is skipped.
        # Deliberately no `maximum`: the parser accepts larger values and
        # `run_audit` caps the window at 500 (FR-08, #1382).
        type={"type": "integer", "minimum": 1},
        location=OpenApiParameter.QUERY,
        required=False,
        description=(
            "Sequential page size (>= 1; values above 500 are capped at 500). "
            "Walks the full result set in engine order; combine with `offset` / "
            "`next_offset`. May be given at most once (a repeated parameter is "
            "a 400)."
        ),
    ),
    OpenApiParameter(
        name="limit",
        type={"type": "integer", "minimum": 1},
        location=OpenApiParameter.QUERY,
        required=False,
        description=(
            "Backward-compatible alias of `page_size` (#622; values above 500 "
            "are capped at 500). When both are given they must be equal, "
            "otherwise 400 VALIDATION_ERROR. May be given at most once."
        ),
    ),
    OpenApiParameter(
        name="offset",
        type={"type": "integer", "minimum": 0},
        location=OpenApiParameter.QUERY,
        required=False,
        description=(
            "Start offset (>= 0) within the result set; requires page_size or "
            "limit unless 0. May be given at most once."
        ),
    ),
    OpenApiParameter(
        name="include_suppressed",
        type=bool,
        location=OpenApiParameter.QUERY,
        required=False,
        default=True,
        description=(
            "Keep suppressed findings in the report, marked with "
            "suppressed/reason/expiry (default true). Only the literals `true` "
            "and `false` are accepted; matching is case-insensitive with "
            "surrounding whitespace trimmed (`TRUE`, ` False ` are valid). Any "
            "other value is a 400. May be given at most once (a repeated "
            "parameter is a 400)."
        ),
    ),
    OpenApiParameter(
        name="scope",
        type=str,
        location=OpenApiParameter.QUERY,
        required=False,
        enum=["document", "project", "global"],
        description="Baseline scope to audit (default: project).",
    ),
    OpenApiParameter(
        name="scope_artifact_id",
        type=str,
        location=OpenApiParameter.QUERY,
        required=False,
        description="Document subtree root; required when scope=document.",
    ),
    OpenApiParameter(
        name="rule_id",
        type=str,
        location=OpenApiParameter.QUERY,
        required=False,
        many=True,
        description=(
            "Filter by rule id; repeat the parameter or pass a "
            "comma-separated list (e.g. 'TRACE-P1,TRACE-P2')."
        ),
    ),
    OpenApiParameter(
        name="severity",
        type=str,
        location=OpenApiParameter.QUERY,
        required=False,
        many=True,
        description=(
            "Filter by severity (blocker|warning); repeat the parameter or "
            "pass a comma-separated list."
        ),
    ),
    OpenApiParameter(
        name="artifact_type",
        type=str,
        location=OpenApiParameter.QUERY,
        required=False,
        description=(
            "Only findings that concern an artifact of this type (e.g. "
            "'Requirement', 'ArchitectureElement')."
        ),
    ),
]


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


def _parse_page_size(raw: str, parameter: str) -> int:
    """Parse one explicit page-size value (``page_size`` or its ``limit`` alias).

    Non-integer values (including an empty string and floats such as ``1.5``)
    raise ValueError naming *parameter*, mapped to a 400 by the caller. A value
    below 1 is rejected rather than clamped: silently turning ``page_size=0``
    into "the default cap" would hide the caller's mistake. Deliberately no
    upper bound here — :meth:`AuditService.run_audit` already caps the window at
    :data:`AuditService.MAX_REPORT_FINDINGS`; the OpenAPI parameter description
    states "values above 500 are capped at 500" (FR-08, #1382).
    """
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise ValueError(f"{parameter} must be an integer.") from None
    if value < 1:
        raise ValueError(f"{parameter} must be >= 1.")
    return value


def _parse_pagination(request: Request) -> tuple[int | None, int]:
    """#622/#1383: optional ``?page_size=&offset=`` (``limit`` is an alias).

    ``page_size`` and ``limit`` are aliases for the page size. When both are
    present their parsed values must agree; conflicting values raise
    ValueError (400 ``VALIDATION_ERROR``) instead of silently preferring one.
    Only one present -> that one is used. Neither present -> ``(None, 0)``,
    preserving the default BLOCKER-preferred truncation exactly as before #622.

    An explicit page size must be ``>= 1`` and ``offset`` must be ``>= 0``;
    invalid values (non-integers, out-of-range) raise ValueError rather than
    being silently clamped — same pattern as ``_parse_scopes``. A positive
    ``offset`` without a page size is also rejected ("offset requires
    page_size or limit"): without a window the offset has no meaning and
    silently ignoring it would return the wrong page. ``offset=0`` without a
    page size is accepted and ignored.

    #1382/FR-10: each of ``page_size``, ``limit`` and ``offset`` may be given
    **at most once**; a repeated parameter is rejected with 400 instead of
    silently using one of the values. ``rule_id`` / ``severity`` stay
    repeatable by design (they are set-valued finding filters, see
    ``_parse_finding_filters``).

    Values above :data:`AuditService.MAX_REPORT_FINDINGS` are *capped*, not
    rejected — ``run_audit`` clamps the window. The OpenAPI description states
    that cap; there is deliberately no ``maximum`` in the schema (FR-08).
    """
    page_size_values = request.query_params.getlist("page_size")
    limit_values = request.query_params.getlist("limit")
    offset_values = request.query_params.getlist("offset")
    if len(page_size_values) > 1:
        raise ValueError("page_size may be given at most once.")
    if len(limit_values) > 1:
        raise ValueError("limit may be given at most once.")
    if len(offset_values) > 1:
        raise ValueError("offset may be given at most once.")

    raw_page_size = page_size_values[0] if page_size_values else None
    raw_limit = limit_values[0] if limit_values else None

    page_size: int | None = None
    if raw_page_size is not None and raw_limit is not None:
        page_size_value = _parse_page_size(raw_page_size, "page_size")
        limit_value = _parse_page_size(raw_limit, "limit")
        if page_size_value != limit_value:
            raise ValueError(
                "page_size and limit are aliases; when both are given they "
                f"must have the same value (got {page_size_value} and "
                f"{limit_value})."
            )
        page_size = page_size_value
    elif raw_page_size is not None:
        page_size = _parse_page_size(raw_page_size, "page_size")
    elif raw_limit is not None:
        page_size = _parse_page_size(raw_limit, "limit")

    offset = 0
    raw_offset = offset_values[0] if offset_values else None
    if raw_offset is not None:
        try:
            offset = int(raw_offset)
        except (TypeError, ValueError):
            raise ValueError("offset must be an integer.") from None
        if offset < 0:
            raise ValueError("offset must be >= 0.")
    if offset > 0 and page_size is None:
        raise ValueError("offset requires page_size or limit.")
    return page_size, offset


def _parse_include_suppressed(request: Request) -> bool:
    """#569/m2: parse ``?include_suppressed=true|false`` strictly.

    Absent -> ``True`` (O3: nothing is hidden by default). Only the literals
    ``true``/``false`` are accepted, matched case-insensitively with
    surrounding whitespace trimmed (``TRUE`` and `` False `` are valid); every
    other value raises ValueError so the caller answers 400
    ``VALIDATION_ERROR`` instead of silently coercing a typo into a filter
    (spec E15/AC-569-22).

    #1382/FR-10: the parameter may be given **at most once**, matching the
    pagination parameters — a repeated value is ambiguous, so it is a 400
    rather than a silent pick of one of the values.
    """
    values = request.query_params.getlist("include_suppressed")
    if len(values) > 1:
        raise ValueError("include_suppressed may be given at most once.")
    if not values:
        return True
    lowered = str(values[0]).strip().lower()
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


def _parse_finding_filters(request: Request) -> dict[str, Any]:
    """#1262: parse the optional ``rule_id`` / ``severity`` / ``artifact_type``
    server-side finding filters off the audit-run query params.

    ``rule_id`` and ``severity`` accept a repeated query parameter or a
    comma-separated list. ``artifact_type`` is a single ``Artifact`` type
    discriminator. Returns a dict with the normalised sets plus ``active``
    (whether any filter was named) and the raw ``artifact_type``; an unknown
    severity raises ValueError (400), mapped by the caller.
    """
    rule_ids = normalize_rule_ids(
        request.query_params.getlist("rule_id") or request.query_params.get("rule_id")
    )
    severities = normalize_severities(
        request.query_params.getlist("severity") or request.query_params.get("severity")
    )
    raw_type = request.query_params.get("artifact_type") or ""
    artifact_type = raw_type.strip()
    return {
        "rule_ids": rule_ids,
        "severities": severities,
        "artifact_type": artifact_type,
        "active": bool(rule_ids or severities or artifact_type),
    }


def _build_finding_filter(
    *,
    rule_ids: frozenset[str],
    severities: frozenset[str],
    artifact_type_ids: frozenset[str] | None,
) -> Callable[[Any], bool]:
    """#1382: bind the parsed filters into one ``Finding`` predicate.

    Passed to ``AuditService.run_audit(finding_filter=...)`` so filtering
    happens *before* the service's totals/cap/window. Reuses
    :func:`finding_matches` (the same predicate ``apply_report_filters``
    uses) — no rule logic is duplicated or changed.
    """

    def _matches(finding: Any) -> bool:
        return finding_matches(
            finding,
            rule_ids=rule_ids,
            severities=severities,
            artifact_type_ids=artifact_type_ids,
        )

    return _matches


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

    @extend_schema(
        parameters=_AUDIT_QUERY_PARAMETERS,
        responses={
            200: OpenApiResponse(
                response=AuditReportSerializer,
                description=(
                    "Audit report: `counts` is the ground truth over the full "
                    "(pre-window) run, `page_counts` only the returned window."
                ),
            ),
            400: OpenApiResponse(
                response=ErrorResponseSerializer,
                description=(
                    "VALIDATION_ERROR — conflicting/invalid page_size/limit, "
                    "negative offset, offset without a page size, or an "
                    "invalid scope/filter value."
                ),
            ),
        },
    )
    def get(
        self, request: Request, workspace_id: str, *args: Any, **kwargs: Any
    ) -> Response:
        lang = detect_lang(request)
        try:
            scopes = _parse_scopes(request)
            limit, offset = _parse_pagination(request)
            include_suppressed = _parse_include_suppressed(request)
            filters = _parse_finding_filters(request)
        except ValueError as exc:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message=str(exc)),
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            ctx = get_auth_context(request)
            _assert_workspace_in_tenant(workspace_id, ctx)
            # #1382: build the filter as a predicate and let the service apply
            # it before its cap/totals, so `counts` is the filtered ground
            # truth and a match beyond MAX_REPORT_FINDINGS is reachable. The
            # old run-audit-then-filter path could not reach such a match and
            # reported counts.total == 0 while matches existed.
            finding_filter = None
            if filters["active"]:
                artifact_type_ids = None
                if filters["artifact_type"]:
                    artifact_type_ids = resolve_artifact_ids_for_type(
                        artifact_type=filters["artifact_type"],
                        tenant_id=ctx.tenant_id,
                        workspace_id=workspace_id,
                    )
                finding_filter = _build_finding_filter(
                    rule_ids=filters["rule_ids"],
                    severities=filters["severities"],
                    artifact_type_ids=artifact_type_ids,
                )
            report = AuditService().run_audit(
                workspace_id,
                ctx,
                scopes=scopes,
                limit=limit,
                offset=offset,
                include_suppressed=include_suppressed,
                finding_filter=finding_filter,
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
            # Static 500 (CWE-209): the cause is masked in the response, so it
            # must be logged here or it is lost to operators.
            logger.exception(
                "Audit remediation failed for workspace %s", workspace_id
            )
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
            # Static 500 (CWE-209): the cause is masked in the response, so it
            # must be logged here or it is lost to operators.
            logger.exception("AI review failed for workspace %s", workspace_id)
            return Response(
                build_error_response("INTERNAL_SERVER_ERROR", lang),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class AuditRuleCatalogView(APIView):
    """GET /api/v1/audit/rules/ — the SE-Auditor rule catalogue (#1262).

    Read-only metadata for every registered audit rule (title, description,
    severity, standard reference, remediation hint, active tiers). Bearer-
    authenticated and not workspace-scoped: the rule vocabulary is global, so a
    client can render rule help before selecting a workspace. The catalogue is
    metadata only — no rule is executed here.
    """

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            # Authentication only — an unauthenticated caller is rejected by
            # BearerTokenAuthentication before this runs; this is the defensive
            # parity call every audit view makes.
            get_auth_context(request)
        except Exception:
            logger.exception("SE-Auditor rule catalogue failed")
            return Response(
                build_error_response("INTERNAL_SERVER_ERROR", lang),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        return Response({"rules": get_rule_catalogue()})


__all__ = [
    "AuditRuleCatalogView",
    "WorkspaceAuditAiReviewView",
    "WorkspaceAuditRemediateView",
    "WorkspaceAuditView",
    "WorkspaceAuditWaiverView",
]
