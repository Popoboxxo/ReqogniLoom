"""Error taxonomy for ``suggestion.capture`` (ADR-032, plan P2/P3).

One type per machine-readable code of the listen-mode contract (spec §4.3), so
both transports answer the same code and neither has to parse a message:

======================  ============  =========================================
Type                    Code          Meaning
======================  ============  =========================================
CaptureDisabledError    CAPTURE_DISABLED   The workspace switch is off.
CaptureTextTooLongError TEXT_TOO_LONG      ``text`` exceeds the server maximum.
CaptureRateLimitedError RATE_LIMITED       Hourly call quota or the daily token
                                           budget is exhausted (fail-closed).
WorkspaceForbiddenError WORKSPACE_FORBIDDEN The key may not act in that
                                           workspace (fence, role, tenant).
======================  ============  =========================================

``PRODUCER_CONTEXT_REQUIRED`` and ``LLM_UNAVAILABLE`` already have canonical
types (``application.base.ProducerContextRequiredError`` and
``application.base.LlmProviderUnavailableError``); capture raises those rather
than duplicate them, so there is exactly one home per code.

All four types are ``ValidationError``/``PermissionDeniedError`` subclasses, the
established precedent for "a well-formed request the policy refuses": existing
``except`` clauses keep working while the REST/MCP maps — which look exceptions
up by *exact* type — answer the dedicated code. Every type in this module must
therefore be registered in ``rest_api.views_common._EXC_TO_HTTP`` /
``_EXC_TO_CODE`` and in the MCP tool group's mapping.
"""
from __future__ import annotations

from application.base import PermissionDeniedError, ValidationError

__all__ = [
    "CaptureDisabledError",
    "CaptureRateLimitedError",
    "CaptureTextTooLongError",
    "WorkspaceForbiddenError",
]


class CaptureDisabledError(ValidationError):
    """The workspace has not switched listening on (decision D4, default off).

    Answered with **409 CAPTURE_DISABLED**: a rejected precondition on a
    well-formed request — the same convention ``PRODUCER_CONTEXT_REQUIRED``
    uses. Deliberately not a 404: the client relay needs to distinguish "the
    feature is off here" from "this route does not exist", because the former is
    a status line in the user's client and the latter is a version mismatch.
    """

    error_code = "CAPTURE_DISABLED"
    http_status = 409


class CaptureTextTooLongError(ValidationError):
    """``text`` exceeds the server-side maximum length (spec §4.1).

    **400**: a request defect the client can fix — it should truncate or split
    the message, not retry. ``details`` carries the limit so a client does not
    have to hard-code it.
    """

    error_code = "TEXT_TOO_LONG"
    http_status = 400

    def __init__(self, message: str, *, limit: int, actual: int) -> None:
        super().__init__(message)
        self.message = message
        self.details = {"limit": limit, "actual": actual}


class CaptureRateLimitedError(ValidationError):
    """A capture quota is exhausted.

    **429** — covers both quotas of spec §4.4: calls per key/workspace/hour and
    the daily token budget, which is deliberately **fail-closed** on this path
    (the interview chat path is fail-open; a per-message listener must not be).
    ``details`` names which quota fired (``"calls_per_hour"`` /
    ``"daily_tokens"``) plus the configured limit.
    """

    error_code = "RATE_LIMITED"
    http_status = 429

    def __init__(self, message: str, *, limit: str, value: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = {"quota": limit, "limit": value}


class WorkspaceForbiddenError(PermissionDeniedError):
    """The caller may not act in the requested workspace.

    **403 WORKSPACE_FORBIDDEN** — the workspace is unknown to this tenant, the
    caller holds no role in it, or the API key's workspace fence excludes it.
    All three answer the same code on purpose: distinguishing them would leak
    the existence of another tenant's workspace (spec §4.1 "kein stilles
    ‚erster Workspace'" — the caller must name the right one).
    """

    error_code = "WORKSPACE_FORBIDDEN"
    http_status = 403
