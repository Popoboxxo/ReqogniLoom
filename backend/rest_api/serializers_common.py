"""
COMP-RA-002 DataSerializer — serializers_common — extracted from rest_api/serializers.py (content-sensible split; public import surface preserved by the facade)..

leaf_id : COMP-RA-002
req_id  : REQ-L2-RA-001 (CRUD serialization), REQ-L2-RA-003 (performance),
          REQ-L2-RA-004 (i18n errors), REQ-L2-RA-008 (preset field filter),
          REQ-L2-RA-009 (error format), REQ-L2-RA-010 (pagination/filter/sort),
          REQ-L2-RA-012 (no business logic), REQ-L2-RA-013 (N+1 avoidance)
          REQ-L3-RA002-001 through REQ-L3-RA002-004

Architecture:
  docs/se/L1/Gesamtsystem/L2/RestApiAdapterSystem/Components/
    COMP-RA-002_DataSerializer/L3_COMP-RA-002_DataSerializer_Architecture.md

Interfaces:
  IF-RA-INT-003  COMP-RA-001 <-> COMP-RA-002  (SerializeRequest / ValidatedDTO)
  IF-RA-INT-004  COMP-RA-004 -> COMP-RA-002   (FieldFilter)
  IF-RA-INT-006  COMP-RA-005 -> COMP-RA-002   (SerializerSchemas)

Design:
  - DRF ModelSerializers for all 7 domain entities.
  - Preset-aware field filtering via FieldFilter (set by PresetGuard).
  - i18n error messages via Accept-Language header (DE/EN).
  - Pagination: offset-based, default 25, max 100.
  - Queryset optimization: select_related / prefetch_related defined here,
    applied in ViewSets via get_queryset() (REQ-L2-RA-013).
  - No business logic in serializers — pure translation layer.
"""
from __future__ import annotations

from collections.abc import Container, Mapping, Sequence
from typing import Any

from django.utils import translation
from rest_framework import pagination, serializers, status
from rest_framework.exceptions import APIException
from rest_framework.request import Request
from rest_framework.response import Response

from application.bulk_update_service import MAX_ENTRIES, MAX_TRANSITION_IDS
from application.test_steps import normalize_steps, validate_steps
from persistence.models import (
    Document,
    ElementType,
    Milestone,
    ScenarioKind,
    TestCaseOrigin,
    TestCaseType,
    WorkItem,
)
from rest_api.mixins.workflow_state import WorkflowStateSerializerMixin
from rest_api.mixins.workflow_transitions import _ALWAYS_ALLOWED_PATCH_FIELDS
from rest_api.preset_guard import FieldFilter
from rest_api.sanitization import FreeTextFieldMarker, validate_free_text



# ---------------------------------------------------------------------------
# Lock-counter semantics (issue #213)
# ---------------------------------------------------------------------------

# ``AuditableModel.version`` is an optimistic-concurrency counter, not a
# content revision number. It is exposed so clients can send it back as
# ``expected_version``; it must not be rendered as "this artifact has N
# revisions". Historical values have no retrievable snapshot — real history
# comes from the ``/versions/`` and ``/history/`` endpoints and from Baselines.
LOCK_VERSION_HELP_TEXT = (
    "Optimistic-lock counter for concurrency control (send back as "
    "expected_version). NOT a content revision number: it also increments on "
    "writes that change nothing user-visible, and historical values have no "
    "retrievable snapshot. Use /versions/, /history/ or Baselines for real "
    "history."
)


# ---------------------------------------------------------------------------
# Identity semantics: ``id`` vs ``uid`` (Attribut v3 WS2, #936, spec section 3)
# ---------------------------------------------------------------------------

# Spec section 3: the Artifact UUID ``id`` is the technical identity; ``uid`` is
# the *readable local identifier* (issue #932). Each artifact-create service
# allocates ``{PREFIX}-{NNN}`` per ``(workspace, item_type)`` via
# ``application.local_uid.generate_local_uid``, so a freshly created artifact
# carries one without any user action; an explicit ``uid`` (ReqIF import) still
# wins. The field stays read-only to clients on every serializer —
# ``ClientUidRejectionMixin`` answers 400 for a supplied value instead of
# discarding it silently. ReqIF's external identity lives on the Artifact
# ``reqif_*`` fields (#1003), not here.
UID_HELP_TEXT = (
    "Local readable identifier, auto-generated per (workspace, item_type) as "
    "'<PREFIX>-NNN' (issue #932). Read-only: managed by the server. External "
    "ReqIF identity lives on Artifact.reqif_uid/reqif_identifier, not here."
)


# ---------------------------------------------------------------------------
# i18n error translation (REQ-L2-RA-004, REQ-L3-RA002-002)
# ---------------------------------------------------------------------------

# Bilingual error message registry. Every key MUST have both DE and EN entries.
# Missing a DE entry for a new key is treated as a build error (per CI rule).
_ERROR_MESSAGES: dict[str, dict[str, str]] = {
    "VALIDATION_ERROR": {
        "en": "Validation failed.",
        "de": "Validierung fehlgeschlagen.",
    },
    "REQUIRED_FIELD": {
        "en": "This field is required.",
        "de": "Dieses Feld ist erforderlich.",
    },
    "NOT_FOUND": {
        "en": "Resource not found.",
        "de": "Ressource nicht gefunden.",
    },
    # #1081: the two statuses DRF raises on its own that the rest of the
    # registry had no entry for. They complete the status->code map in
    # ``rest_api.error_envelope`` so every code a client can observe is a key
    # of this registry (and therefore has a localised message).
    "METHOD_NOT_ALLOWED": {
        "en": "This method is not allowed on this resource.",
        "de": "Diese Methode ist auf dieser Ressource nicht erlaubt.",
    },
    "UNSUPPORTED_MEDIA_TYPE": {
        "en": "The request media type is not supported.",
        "de": "Der Medientyp der Anfrage wird nicht unterstützt.",
    },
    "PERMISSION_DENIED": {
        "en": "You do not have permission to perform this action.",
        "de": "Sie haben keine Berechtigung, diese Aktion durchzuführen.",
    },
    # ADR-028 A1: the release conflicts with the item's workflow state.
    "RELEASE_NOT_ALLOWED": {
        "en": "The item cannot be released from its current workflow state.",
        "de": "Das Element kann aus seinem aktuellen Workflow-Zustand nicht freigegeben werden.",
    },
    "AUTHENTICATION_REQUIRED": {
        "en": "Authentication credentials were not provided.",
        "de": "Es wurden keine Authentifizierungsdaten angegeben.",
    },
    "CONFLICT": {
        "en": "A conflict occurred with existing data.",
        "de": "Es ist ein Konflikt mit vorhandenen Daten aufgetreten.",
    },
    # GH-1199: the baseline DELETE is refused because the resource is
    # content-immutable — a domain prohibition, not a role denial. Kept distinct
    # from PERMISSION_DENIED so a client does not mistake "cannot be deleted by
    # anyone" for "you lack the role".
    "BASELINE_IMMUTABLE": {
        "en": (
            "Baselines are content-immutable and cannot be deleted through this "
            "route. An administrator can remove one via the audited route "
            "DELETE /api/v1/baselines/{id}/purge/."
        ),
        "de": (
            "Baselines sind inhaltlich unveränderlich und können über diese "
            "Route nicht gelöscht werden. Ein Administrator kann sie über die "
            "auditierte Route DELETE /api/v1/baselines/{id}/purge/ entfernen."
        ),
    },
    # GH-868/GH-923: a failed ``If-Match`` precondition (stale ETag). Kept
    # distinct from CONFLICT so a client can tell the two optimistic-locking
    # mechanisms apart: 412 PRECONDITION_FAILED = the ``If-Match`` header lost,
    # 409 CONFLICT = the legacy ``expected_version`` body field lost.
    "PRECONDITION_FAILED": {
        "en": "The resource changed since it was last read; re-read it and retry.",
        "de": (
            "Die Ressource wurde seit dem letzten Lesen geändert; lesen Sie sie "
            "erneut und wiederholen Sie den Vorgang."
        ),
    },
    # GH-1396: the ``If-Match`` header was present but is not a valid
    # field-value (blank, unquoted, unbalanced quote, garbage inside a list).
    # Kept distinct from PRECONDITION_FAILED on purpose: 412 tells the client
    # "your copy is stale, re-read and retry", which can never help when the
    # header never parsed. A malformed header is a request defect → 400.
    "INVALID_IF_MATCH": {
        "en": (
            "The If-Match header is not a valid entity-tag (expected a quoted "
            'value such as "3", a weak validator, or *).'
        ),
        "de": (
            "Der If-Match-Header ist kein gültiger Entity-Tag (erwartet wird ein "
            'quotierter Wert wie "3", ein Weak-Validator oder *).'
        ),
    },
    # Plan F F4.4 (SEC-RB-05): one entry per baseline-rollback refusal so a
    # client can enumerate the code space and get a localised default even when
    # no service message is forwarded. The service's own sentence is what the
    # rollback routes return; these are the fallbacks.
    "ROLLBACK_ERROR": {
        "en": "The baseline rollback was refused.",
        "de": "Der Baseline-Rollback wurde abgelehnt.",
    },
    "ROLLBACK_NOT_APPROVED": {
        "en": "Baseline rollback requires an approved change request.",
        "de": "Ein Baseline-Rollback erfordert einen freigegebenen Change Request.",
    },
    "ROLLBACK_ALREADY_APPLIED": {
        "en": "This change request has already been implemented.",
        "de": "Dieser Change Request wurde bereits umgesetzt.",
    },
    "ROLLBACK_PLAN_STALE": {
        "en": (
            "Items changed since the change request was opened; create a new "
            "request."
        ),
        "de": (
            "Artikel haben sich seit dem Öffnen des Change Requests geändert; "
            "legen Sie einen neuen an."
        ),
    },
    "ROLLBACK_CONFLICT": {
        "en": (
            "The change request is being modified by a concurrent CCB decision; "
            "retry the rollback."
        ),
        "de": (
            "Der Change Request wird durch eine parallele CCB-Entscheidung "
            "verändert; wiederholen Sie den Rollback."
        ),
    },
    "ROLLBACK_EMPTY": {
        "en": "Nothing to roll back: the plan restores nothing at all.",
        "de": "Nichts rückzusetzen: der Plan stellt nichts wieder her.",
    },
    "ROLLBACK_TOO_LARGE": {
        "en": "The rollback covers too many items for one change request.",
        "de": "Der Rollback umfasst zu viele Artikel für einen Change Request.",
    },
    "PRESET_FIELD_REQUIRED": {
        "en": "This field is required by the active workspace preset.",
        "de": "Dieses Feld ist durch das aktive Workspace-Preset erforderlich.",
    },
    "PRESET_FIELD_FORBIDDEN": {
        "en": "This field is not permitted by the active workspace preset.",
        "de": "Dieses Feld ist durch das aktive Workspace-Preset nicht erlaubt.",
    },
    "SE_AUDITOR_BLOCKED": {
        "en": (
            "The SE-Auditor reported blocking findings; resolve them or supply "
            "a written override justification."
        ),
        "de": (
            "Der SE-Auditor meldet blockierende Findings; beheben Sie diese "
            "oder geben Sie eine schriftliche Ausnahmebegründung an."
        ),
    },
    # #569: the three dedicated suppression error codes (§3.4.2). Bilingual
    # entries are mandatory for every key (CI rule at the top of this registry).
    "WAIVER_REASON_REJECTED": {
        "en": (
            "The suppression justification does not meet the governance "
            "policy; state which deviation is accepted and why."
        ),
        "de": (
            "Die Begründung der Unterdrückung erfüllt die Governance-Richtlinie "
            "nicht; nennen Sie die akzeptierte Abweichung und den Grund."
        ),
    },
    "WAIVER_FINDING_NOT_BLOCKING": {
        "en": (
            "No blocking SE-Auditor finding matches this suppression request; "
            "re-run the auditor and suppress a finding it reports."
        ),
        "de": (
            "Zu dieser Unterdrückungsanfrage passt kein blockierendes "
            "SE-Auditor-Finding; starten Sie den Auditor neu und unterdrücken "
            "Sie ein gemeldetes Finding."
        ),
    },
    "SUPPRESSION_EXPIRED": {
        "en": (
            "A suppression for this finding exists but has expired; re-granting "
            "is a separate governance decision that is not supported yet."
        ),
        "de": (
            "Für dieses Finding existiert eine Unterdrückung, die jedoch "
            "abgelaufen ist; eine erneute Gewährung ist eine separate "
            "Governance-Entscheidung, die noch nicht unterstützt wird."
        ),
    },
    "INTERNAL_SERVER_ERROR": {
        "en": "An internal server error occurred.",
        "de": "Ein interner Serverfehler ist aufgetreten.",
    },
    "SERVICE_UNAVAILABLE": {
        "en": "A required service is temporarily unavailable.",
        "de": "Ein erforderlicher Dienst ist vorübergehend nicht verfügbar.",
    },
    # ADR-019 WP5 / review finding 003-01: a suggestion may only be produced
    # under an agent/API-key context. A human bearer trigger is refused
    # fail-closed (409) rather than writing an unstamped, unreviewed proposal.
    "PRODUCER_CONTEXT_REQUIRED": {
        "en": (
            "This action produces a reviewable proposal and may only run under "
            "an agent/API-key context; a human trigger is refused. Use an "
            "API key with an agent principal."
        ),
        "de": (
            "Diese Aktion erzeugt einen prüfbaren Vorschlag und darf nur in "
            "einem Agent-/API-Key-Kontext ausgeführt werden; ein menschlicher "
            "Aufruf wird abgewiesen. Verwenden Sie einen API-Key mit "
            "Agent-Principal."
        ),
    },
    # Issue #1165: an LLM provider timeout or transport failure is an expected,
    # retry-able upstream condition, not an internal server error.
    "LLM_TIMEOUT": {
        "en": (
            "The AI service did not answer within the allotted time. "
            "Please retry later."
        ),
        "de": (
            "Der KI-Dienst hat nicht innerhalb der vorgesehenen Zeit "
            "geantwortet. Bitte versuchen Sie es später erneut."
        ),
    },
    "LLM_UNAVAILABLE": {
        "en": (
            "The AI service is temporarily unavailable. Please retry later."
        ),
        "de": (
            "Der KI-Dienst ist vorübergehend nicht verfügbar. "
            "Bitte versuchen Sie es später erneut."
        ),
    },
    # #1240: the provider answered, but its content could not be parsed into the
    # structured shape the flow expects. An upstream/response fault — a valid
    # request met an invalid LLM output — so 502, alongside the LLM_TIMEOUT (504)
    # and LLM_UNAVAILABLE (503) upstream conditions, never a 500.
    "LLM_OUTPUT_INVALID": {
        "en": (
            "The AI service returned a response that could not be processed. "
            "Please retry later."
        ),
        "de": (
            "Der KI-Dienst hat eine nicht verarbeitbare Antwort geliefert. "
            "Bitte versuchen Sie es später erneut."
        ),
    },
    # Issue #1416: the REQ-106 daily token budget is exhausted — a quota
    # refusal, not an invalid answer. 429, matching the error code
    # CapabilityRouter already returns for the same condition.
    "LLM_TOKEN_LIMIT_EXCEEDED": {
        "en": (
            "The tenant's daily AI token budget is exhausted. "
            "Please retry later or raise TENANT_TOKEN_LIMIT_PER_DAY."
        ),
        "de": (
            "Das tägliche KI-Token-Budget des Mandanten ist aufgebraucht. "
            "Bitte versuchen Sie es später erneut oder erhöhen Sie "
            "TENANT_TOKEN_LIMIT_PER_DAY."
        ),
    },
    # RFC #1002 PR B: the configurable write ratelimit for memory.write. Kept
    # distinct from the DRF transport throttles (which answer a plain 429 body):
    # REST maps this to HTTP 429 with a Retry-After header and MCP to the
    # RATE_LIMITED JSON-RPC code, so a client can tell "back off" apart from
    # any other 4xx.
    "RATE_LIMITED": {
        "en": "Too many memory writes; slow down and retry later.",
        "de": "Zu viele Memory-Schreibvorgänge; bitte später erneut versuchen.",
    },
    # #1308 (Plan E / WP E3.3 + E3.4): the second-factor codes. Mirrored in
    # ``auth_tenancy.errors._ERROR_CATALOG`` — that catalog owns the
    # HTTP status and is what ``build_error_body`` reads, this registry is the
    # enumerable, localised code space every REST error envelope draws from.
    "MFA_STEP_UP_REQUIRED": {
        "en": (
            "This session was authenticated with a password only, but a second "
            "factor is required. Log in again and confirm the code."
        ),
        "de": (
            "Diese Sitzung wurde nur mit einem Passwort authentifiziert, es ist "
            "jedoch ein zweiter Faktor erforderlich. Melden Sie sich erneut an "
            "und bestätigen Sie den Code."
        ),
    },
    "MFA_ENROLLMENT_REQUIRES_GRANT": {
        "en": (
            "A second factor is required. Ask an administrator for an "
            "enrollment grant."
        ),
        "de": (
            "Ein zweiter Faktor ist erforderlich. Bitten Sie eine "
            "Administratorin oder einen Administrator um eine "
            "Enrollment-Freigabe."
        ),
    },
    # ------------------------------------------------------------------
    # Second factor enrollment (WP E3.6) — the management surface.
    # ------------------------------------------------------------------
    "MFA_NOT_ALLOWED": {
        "en": "A second factor can only be enrolled for a staff account.",
        "de": (
            "Ein zweiter Faktor kann nur für ein Staff-Konto eingerichtet "
            "werden."
        ),
    },
    "MFA_ALREADY_ENROLLED": {
        "en": (
            "This account already has a confirmed second factor. Disable it "
            "before enrolling a new device."
        ),
        "de": (
            "Für dieses Konto ist bereits ein zweiter Faktor bestätigt. "
            "Deaktivieren Sie ihn, bevor Sie ein neues Gerät einrichten."
        ),
    },
    "MFA_REQUIRED": {
        "en": (
            "A second factor is required for this account and cannot be removed."
        ),
        "de": (
            "Für dieses Konto ist ein zweiter Faktor erforderlich; er kann nicht "
            "entfernt werden."
        ),
    },
    # 403: the session is authenticated but has not completed a second-factor
    # step-up (API-key creation for a staff account). Deliberately separate
    # from the 409 "cannot remove the factor" meaning of ``MFA_REQUIRED``.
    "MFA_STEP_UP_REQUIRED_FOR_KEY": {
        "en": (
            "This session has not completed a second-factor step-up. Creating "
            "or managing an API key for a staff account requires it while a "
            "second factor is mandatory."
        ),
        "de": (
            "Diese Sitzung hat keinen zweiten Faktor bestätigt. Das Anlegen oder "
            "Verwalten eines API-Schlüssels für ein Staff-Konto setzt ihn "
            "voraus, solange ein zweiter Faktor verpflichtend ist."
        ),
    },
    "MFA_REQUIRES_INTERACTIVE_SESSION": {
        "en": (
            "The second factor can only be changed from an interactive session, "
            "not with an API key."
        ),
        "de": (
            "Der zweite Faktor kann nur aus einer interaktiven Sitzung geändert "
            "werden, nicht mit einem API-Schlüssel."
        ),
    },
    "MFA_CHALLENGE_INVALID": {
        "en": "The second-factor challenge is invalid, expired or already used.",
        "de": (
            "Die Challenge für den zweiten Faktor ist ungültig, abgelaufen oder "
            "wurde bereits verwendet."
        ),
    },
    "MFA_INVALID_CODE": {
        "en": "The second-factor code is invalid.",
        "de": "Der Code für den zweiten Faktor ist ungültig.",
    },
    "MFA_LOCKED": {
        "en": (
            "Too many failed second-factor attempts. The second factor is "
            "temporarily locked."
        ),
        "de": (
            "Zu viele fehlgeschlagene Versuche mit dem zweiten Faktor. Der "
            "zweite Faktor ist vorübergehend gesperrt."
        ),
    },
    "MFA_UNAVAILABLE": {
        "en": (
            "The second factor cannot be evaluated right now; the login was "
            "refused."
        ),
        "de": (
            "Der zweite Faktor kann derzeit nicht geprüft werden; die Anmeldung "
            "wurde abgelehnt."
        ),
    },
    # GitHub #1739 (beta.29 C2-T1): self-service password change. Mirrored in
    # ``auth_tenancy.errors._ERROR_CATALOG``, which owns the 400 status.
    "INVALID_CURRENT_PASSWORD": {
        "en": "The current password is incorrect.",
        "de": "Das aktuelle Passwort ist falsch.",
    },
    "PASSWORD_POLICY_VIOLATION": {
        "en": "The new password does not meet the password policy.",
        "de": "Das neue Passwort erfüllt die Passwort-Richtlinie nicht.",
    },
    "PASSWORD_CHANGE_REQUIRES_INTERACTIVE_SESSION": {
        "en": (
            "The password can only be changed from an interactive "
            "password-authenticated session, not with an API key or a session "
            "without a password factor."
        ),
        "de": (
            "Das Passwort kann nur aus einer interaktiven, "
            "passwortauthentifizierten Sitzung geändert werden — nicht mit "
            "einem API-Schlüssel und nicht aus einer Sitzung ohne "
            "Passwort-Faktor."
        ),
    },
}



def get_error_message(code: str, lang: str = "en") -> str:
    """Return a localized error message for the given error code.

    Falls back to English if the language or code is not found.
    Unit-testable without HTTP context (REQ-L3-RA002-002 AC).

    Args:
        code: Error code key (must exist in _ERROR_MESSAGES).
        lang: Two-letter language code ("de" or "en").

    Returns:
        Localized error message string.
    """
    lang_lower = (lang or "en").lower()[:2]
    messages = _ERROR_MESSAGES.get(code, {})
    return messages.get(lang_lower) or messages.get("en", code)



def detect_lang(request: Any) -> str:
    """Extract the preferred language from Accept-Language header.

    Returns "de" or "en". Falls back to "en" (REQ-L3-RA002-002).
    """
    if request is None:
        return "en"
    accept = (
        getattr(request, "META", {}).get("HTTP_ACCEPT_LANGUAGE", "")
        or getattr(request, "LANGUAGE_CODE", "")
    )
    if accept and accept.lower().startswith("de"):
        return "de"
    return "en"



class InvalidEnumValue(ValueError):
    """A query-parameter value outside its documented enum (issue #1613).

    Raised at the transport boundary so a typo in a filter cannot be silently
    dropped or echoed back as if it were honoured. ``details`` carries the
    ``[{"field": ..., "allowed_values": [...]}]`` block
    :func:`build_error_response` serialises — the same shape the interview
    surface uses for an unknown ``artifact_type`` — so a client can correct the
    call without guessing.
    """

    def __init__(
        self, parameter: str, value: Any, allowed: Sequence[str]
    ) -> None:
        values = list(allowed)
        shown = repr(value)
        # An error message is not a place to reflect an arbitrarily large
        # payload back to the caller.
        if len(shown) > 64:
            shown = shown[:61] + "..."
        super().__init__(
            f"Invalid {parameter} {shown}; allowed values: {', '.join(values)}."
        )
        self.details: list[dict[str, Any]] = [
            {"field": parameter, "allowed_values": values}
        ]



def build_error_response(
    code: str,
    lang: str = "en",
    details: list[dict[str, Any]] | dict[str, Any] | None = None,
    message: str | None = None,
) -> dict[str, Any]:
    """Construct the standardized error response body (REQ-L2-RA-009).

    Format: {"error": {"code": "...", "message": "...", "details": [...],
    "request_id": "..."}}

    R2A-001: ``request_id`` mirrors the ``X-Request-ID`` header (ADR-014 §1)
    for every error, not only for the views that call ``_with_request_id``.
    Outside a request context it is ``None`` — the published schema already
    allows null — so callers never see a fabricated correlation id.
    """
    from reqogniloom.middleware import get_request_id

    return {
        "error": {
            "code": code,
            "message": message or get_error_message(code, lang),
            "details": details or [],
            "request_id": get_request_id(),
        }
    }



def normalize_preset_blob(blob: Any) -> dict[str, Any]:
    """Return ``blob`` with a consistent ``tier``/``name`` pair (issue #271).

    ``Workspace.preset`` is written in three different shapes depending on the
    row's age and provenance::

        {"tier": "standard", ...}              WorkspaceService.create
        {"tier": "x", "name": "x", ...}        WorkspaceService.switch_preset_tier
        {"name": "extended"}                   legacy/seeded rows (e.g. Demo)

    Both keys are emitted, resolved by preferring ``tier`` and falling back to
    ``name``. ``tier`` is authoritative because ``switch_preset_tier`` — the
    only writer that maintains both — always sets them to the same value, so a
    disagreement can only mean ``name`` is a stale leftover.

    Normalisation happens on READ only. Rewriting the stored blobs would need a
    destructive, hard-to-reverse data migration over live tenant rows for what
    is a low-priority hygiene issue; the read path is cheap and reversible.

    Other keys (``language``, ``terminology_profile``) are preserved untouched,
    and the input is never mutated. A missing/``None``/non-dict blob yields
    ``{}`` rather than a fabricated tier — inventing one would mislabel the
    workspace, and callers already default (the frontend falls back to
    ``"standard"``).
    """
    if not isinstance(blob, dict):
        return {}
    resolved = blob.get("tier") or blob.get("name")
    if not resolved:
        return dict(blob)
    return {**blob, "tier": resolved, "name": resolved}



def extract_preset_tier(value: Any) -> str | None:
    """Extract a bare tier string from a workspace-preset write payload (GH-411).

    ``Workspace.preset`` round-trips through the wire as the resolved object
    ``normalize_preset_blob`` above builds on read (``{"tier": "standard",
    "name": "standard", ...}``), but the write side
    (``WorkspaceViewSet.create``/``set_preset`` in rest_api/views.py) used to
    accept only a bare tier string and reject that very same object shape
    with a confusing "Invalid preset '{'tier': 'standard'}'" error — the
    ``str()`` of a dict, not a real validation message.

    Accepts either shape:
      - a plain tier string: ``"standard"``
      - an object carrying it under ``tier`` or ``name``: ``{"tier": "standard"}``

    Returns the extracted string (still unvalidated against the canonical
    tier list — callers pass it on to ``WorkspaceService.create_workspace``/
    ``switch_preset_tier``, which reject an unknown tier explicitly), or
    ``None`` when no tier string could be extracted at all (wrong type, or
    an object without a usable ``tier``/``name`` key) so the caller can
    return a clear 400 instead of a silently-wrong value.
    """
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        tier = value.get("tier") or value.get("name")
        return tier if isinstance(tier, str) else None
    return None



# ---------------------------------------------------------------------------
# Pagination (REQ-L2-RA-010, REQ-L3-RA002-003)
# ---------------------------------------------------------------------------


class InvalidPageSize(APIException):
    """400 for a ``page_size`` that cannot be used as a page size (issue #1761).

    Before #1761 an unusable value (``0``, negative, non-numeric, empty string)
    was silently replaced by the default, so a client asking for "no limit"
    with ``page_size=0`` got a normal first page and no indication that its
    request had been rewritten.

    ``detail`` carries an already-built ``build_error_response`` body, which
    ``rest_api.error_envelope.reqogniloom_exception_handler`` passes through
    unchanged (it short-circuits on a dict that already has an ``error`` key).
    Same mechanism as ``rest_api.views.MalformedUuidInPath``: the response
    stays byte-identical in shape to every explicit error of the API
    (REQ-071, REQ-L2-RA-009).
    """

    status_code = status.HTTP_400_BAD_REQUEST



class StandardPagination(pagination.PageNumberPagination):
    """Offset-based pagination: default 25, max 100 (REQ-L3-RA002-003, REQ-076).

    Response envelope::

        {
            "count":         <int>,  # total number of matching items
            "next":          <url|null>,  # absolute URL of the next page (null on last)
            "previous":      <url|null>,  # absolute URL of the previous page (null on first)
            "page_size":     <int>,  # page size actually applied to this response
            "max_page_size": <int>,  # hard upper bound this endpoint accepts
            "results":       [ ... ]  # page slice of serialized items
        }

    Query parameters (documented in OpenAPI via
    ``get_schema_operation_parameters`` / ``get_paginated_response_schema``):

    - ``page``      — 1-based page number (default 1).
    - ``page_size`` — items per page (default 25, capped at ``max_page_size``).

    Fix #571 (reopen, QA 2026-09-01): DRF clamps an out-of-range ``page_size``
    to ``max_page_size`` *silently* — ``?page_size=5000`` answered 200 with 100
    results and nothing in the payload said the request had been rewritten.
    Clients sizing their fetch loop from the value they asked for therefore
    could not tell a capped page from a short last page. ``page_size`` and
    ``max_page_size`` are now echoed on every paginated response, so the
    effective slice size and the endpoint's ceiling are both machine-readable.
    The clamp itself is kept (returning 400 would break every existing caller
    that over-asks and today gets a valid, merely smaller, page).

    Issue #1761: a value that is *unusable* as a page size (``0``, negative,
    non-numeric, empty string) is no longer silently swapped for the default.
    Those requests answer ``400 VALIDATION_ERROR`` with a ``page_size`` entry
    in ``error.details`` — see :class:`InvalidPageSize`. Only an *absent*
    parameter keeps the default, and an over-large one keeps the #571 clamp;
    both paths behave exactly as before.
    """

    #: Default number of items returned per page when ``page_size`` is omitted.
    page_size = 25
    #: Query parameter clients use to override the page size (bounded by max_page_size).
    page_size_query_param = "page_size"
    #: Hard upper bound for client-requested page sizes — protects against abuse.
    max_page_size = 100
    #: Query parameter selecting the 1-based page number.
    page_query_param = "page"

    def get_page_size(self, request: Request) -> int | None:
        """Resolve the effective page size and remember it for the envelope.

        DRF resolves this once per request inside ``paginate_queryset`` but
        keeps no record of the result, so ``get_paginated_response`` cannot
        report what was actually applied. Caching it here is the whole
        mechanism behind the ``page_size`` field (see the class docstring).

        Issue #1761: the DRF default silently falls back to :attr:`page_size`
        for any value :func:`rest_framework.pagination._positive_int` rejects —
        including ``0``, negatives and non-numeric strings. An explicit but
        unusable value now raises :class:`InvalidPageSize` instead, so the
        caller learns the request was rewritten. An *absent* parameter still
        yields the default.
        """
        raw_page_size = (
            request.query_params.get(self.page_size_query_param)
            if self.page_size_query_param
            else None
        )
        page_size = (
            self.page_size
            if raw_page_size is None
            else self._parse_page_size(request, raw_page_size)
        )
        self._effective_page_size = page_size
        return page_size

    def _parse_page_size(self, request: Request, raw_page_size: Any) -> int:
        """Validate one explicit ``page_size`` value (issue #1761).

        Returns the applied page size — the requested value, clamped to
        :attr:`max_page_size` when it is larger (the #571 behaviour, kept).
        Raises :class:`InvalidPageSize` for a value below ``1`` or one that is
        not an integer at all; those have no meaningful clamp target, so a
        silent default would only hide the caller's mistake.
        """
        try:
            value = int(raw_page_size)
        except (TypeError, ValueError):
            message = (
                "Must be an integer of at least 1 "
                f"(got {str(raw_page_size)!r})."
            )
        else:
            if value >= 1:
                return (
                    value
                    if self.max_page_size is None
                    else min(value, self.max_page_size)
                )
            message = f"Must be an integer of at least 1 (got {value})."

        raise InvalidPageSize(
            build_error_response(
                "VALIDATION_ERROR",
                detect_lang(request),
                details=[
                    {
                        "field": self.page_size_query_param,
                        "errors": [message],
                    }
                ],
            )
        )

    def get_paginated_response(self, data: Any) -> Response:
        """Return the ``count/next/previous/page_size/max_page_size/results`` envelope.

        The two extra keys are additive — existing clients reading only
        ``count``/``next``/``previous``/``results`` are unaffected.
        """
        return Response(
            {
                "count": self.page.paginator.count,
                "next": self.get_next_link(),
                "previous": self.get_previous_link(),
                "page_size": getattr(
                    self, "_effective_page_size", self.page_size
                ),
                "max_page_size": self.max_page_size,
                "results": data,
            }
        )

    def get_schema_operation_parameters(self, view: Any) -> list[dict[str, Any]]:
        """Document the ``page_size`` ceiling in OpenAPI (fix #571 reopen).

        DRF's default parameter description does not mention ``max_page_size``,
        which is exactly what made the cap invisible to API consumers.
        """
        parameters = super().get_schema_operation_parameters(view)
        for parameter in parameters:
            if parameter.get("name") != self.page_size_query_param:
                continue
            parameter["schema"] = {
                **parameter.get("schema", {"type": "integer"}),
                "minimum": 1,
                "maximum": self.max_page_size,
                "default": self.page_size,
            }
            parameter["description"] = (
                f"Number of results per page (default {self.page_size}, maximum "
                f"{self.max_page_size}). Larger values are clamped to "
                f"{self.max_page_size} (the applied value is echoed as "
                "'page_size' in the response). Values below 1 or non-numeric "
                "values are rejected with 400 VALIDATION_ERROR."
            )
        return parameters

    def get_paginated_response_schema(self, schema: dict[str, Any]) -> dict[str, Any]:
        """Declare the exact pagination envelope for drf-spectacular (REQ-076).

        Overrides DRF's default so the generated OpenAPI schema pins the
        ``count``/``next``/``previous``/``page_size``/``max_page_size``/
        ``results`` contract instead of leaving it implicit. *schema* is the
        item schema of a single ``results`` entry.
        """
        return {
            "type": "object",
            "required": ["count", "results"],
            "properties": {
                "count": {
                    "type": "integer",
                    "example": 123,
                    "description": "Total number of items across all pages.",
                },
                "next": {
                    "type": "string",
                    "nullable": True,
                    "format": "uri",
                    "example": (
                        "https://api.example.org/api/v1/requirements/?page=3&page_size=25"
                    ),
                    "description": "Absolute URL of the next page, or null on the last page.",
                },
                "previous": {
                    "type": "string",
                    "nullable": True,
                    "format": "uri",
                    "example": (
                        "https://api.example.org/api/v1/requirements/?page=1&page_size=25"
                    ),
                    "description": "Absolute URL of the previous page, or null on the first page.",
                },
                "page_size": {
                    "type": "integer",
                    "example": 25,
                    "description": (
                        "Page size actually applied. Differs from the requested "
                        "'page_size' when that value exceeded 'max_page_size'."
                    ),
                },
                "max_page_size": {
                    "type": "integer",
                    "example": 100,
                    "description": (
                        "Hard upper bound this endpoint accepts for 'page_size'."
                    ),
                },
                "results": schema,
            },
        }



class TraceLinkPagination(StandardPagination):
    """Pagination for ``GET /api/v1/tracelinks/`` — same envelope, higher ceiling.

    Fix #571 (reopen, QA 2026-09-01): the traceability view needs the *whole*
    link graph of a workspace, so the client walks every page. At the shared
    ceiling of 100 that is 20 serial round-trips for the ~1980 links of a real
    workspace, and it was the pile-up of those concurrent requests — not one
    single response — that pushed the 512 MB backend container into the OOM
    kill of the original report.

    A TraceLink row is small and fixed-size (two FK ids, a link type, a version
    and a timestamp; the wide pgvector ``embedding`` column is deferred and the
    endpoint never joins the endpoint Artifacts — see
    ``TraceLinkManager.get_trace_links_queryset``), so a page of 500 costs a
    few hundred KB. That is the reason this ceiling can be raised here and not
    globally: entities with free-text bodies (Requirement descriptions, ADR
    rationales) have no comparable bound per row.
    """

    max_page_size = 500



# ---------------------------------------------------------------------------
# Preset-aware Serializer mixin (IF-RA-INT-004)
# REQ-L3-RA002-004
# ---------------------------------------------------------------------------


class PresetAwareSerializerMixin:
    """Mixin that applies FieldFilter from PresetGuard to serializer fields.

    Set ``field_filter`` on the serializer instance before calling
    to_representation() to activate filtering.

    REQ-L3-RA002-004: FieldFilter is applied before generating response (not after).
    """

    field_filter: FieldFilter | None = None

    def to_representation(self, instance: Any) -> dict[str, Any]:
        data = super().to_representation(instance)  # type: ignore[misc]
        ff = self.field_filter
        if ff is not None and ff.permitted_fields:
            # Drop fields not in permitted set
            return {k: v for k, v in data.items() if k in ff.permitted_fields}
        return data

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        attrs = super().validate(attrs)  # type: ignore[misc]
        # QIRK-003 (#76): Postgres text columns reject NUL (0x00) bytes with a
        # raw DB exception (HTTP 500). Reject such input at the serializer
        # boundary with a proper 400 instead of letting it reach the DB.
        null_byte_fields = [
            field
            for field, value in attrs.items()
            if isinstance(value, str) and "\x00" in value
        ]
        if null_byte_fields:
            raise serializers.ValidationError(
                {
                    field: "This field may not contain NUL (0x00) characters."
                    for field in null_byte_fields
                }
            )
        ff = self.field_filter
        if ff is not None and ff.required_fields:
            missing = [f for f in ff.required_fields if f not in attrs]
            if missing:
                raise serializers.ValidationError(
                    {
                        f: get_error_message("PRESET_FIELD_REQUIRED")
                        for f in missing
                    }
                )
        return attrs



# ---------------------------------------------------------------------------
# Free-text sanitization (SEC-03)
# ---------------------------------------------------------------------------


class SanitizedCharField(FreeTextFieldMarker, serializers.CharField):
    """CharField that *rejects* HTML markup and script-capable URI schemes.

    B006: XSS/SQLi payloads (e.g. ``<script>alert(1)</script>``) were stored
    verbatim in free-text fields like ``title``/``description`` and echoed
    back unescaped, enabling stored XSS in any consumer that renders the
    value as HTML. SQL injection is not applicable here (the ORM always
    parametrizes queries); this field only addresses the HTML/script-injection
    half of B006.

    #269 changed the remedy from *strip silently* to *reject*: stripping
    turned ``{"title": "<img src=x onerror=alert(1)>"}`` into a ``201`` with an
    empty title, i.e. silent data loss (same failure class as #263), and it
    did not cover ``javascript:`` URIs at all. See
    :mod:`rest_api.sanitization` for the rules and the trade-off.

    Applied to user-authored narrative fields (title, description, and
    similar prose fields) across the entity serializers, not to identifiers,
    UUIDs, enums or read-only fields. Declaring a new field with this class is
    also what enrols it in the ViewSet-level guard
    (``FreeTextSanitizationMixin``), which covers write paths that read
    ``request.data`` without running the serializer.
    """

    def to_internal_value(self, data: Any) -> str:
        value = super().to_internal_value(data)
        # No field_name here: DRF already nests a field-level error under the
        # field's key, so passing one would produce {"title": {"title": [...]}}.
        return validate_free_text(value)



class AcceptanceCriteriaListField(serializers.JSONField):
    """Structured acceptance-criteria list, validated on write (#1609).

    ``RequirementSerializer.acceptance_criteria_items`` used to be declared
    ``read_only``: a ``PATCH``/``POST`` carrying the list answered **200** and
    wrote nothing — the value was dropped by DRF without a word. It is a
    writable field now, validated through the same ``criteria-list`` contract
    the dedicated ``/requirements/{id}/acceptance-criteria/`` endpoint uses
    (:func:`attribute_definitions.field_validation.normalize_criteria_list`),
    so a malformed list is a field-level 400 instead of a silent no-op.

    The value is deliberately *not* handed to ``super().to_internal_value``:
    a JSON-encoded string would otherwise be parsed into a list, which hides a
    client bug behind an accidental success. Only a real list is accepted.
    """

    def to_internal_value(self, data: Any) -> list[dict[str, Any]]:
        from attribute_definitions.field_validation import (
            FieldValidationError,
            normalize_criteria_list,
        )

        try:
            return normalize_criteria_list(data)
        except FieldValidationError as exc:
            # As in SanitizedCharField above: DRF already nests field errors
            # under the field's own key, so the bare message list is enough.
            raise serializers.ValidationError(
                exc.errors.get("criteria-list") or [str(exc)]
            ) from exc



class SanitizedJSONField(FreeTextFieldMarker, serializers.JSONField):
    """JSONField whose *nested* strings obey the free-text rules.

    ``GlossaryTerm.synonyms`` is a list of user-authored labels. It is as
    renderable as ``definition`` (the SPA and the PDF/ReqIF exporters print
    synonyms verbatim), but the scalar guard skipped it: the value is a
    ``list``, not a ``str``, so every element went to the database raw — #269
    finding 4, one nesting level down.

    ``find_free_text_violation`` walks the structure, so this covers list
    items, dict values and dict keys alike.
    """

    def to_internal_value(self, data: Any) -> Any:
        value = super().to_internal_value(data)
        # As above: DRF nests field errors under the field's own key already.
        return validate_free_text(value)



# ---------------------------------------------------------------------------
# Artifact system fields mixin (Attribut v3 WS2, #936)
# ---------------------------------------------------------------------------


class ArtifactSystemFieldsSerializerMixin(
    metaclass=serializers.SerializerMetaclass
):
    """Adds the Artifact-level ``owner``/``reporter``/``priority`` fields.

    Spec section 3: these live on ``Artifact``, not on the per-type model, so an
    entity serializer has no attribute to bind them to. The read values are
    supplied by the entity's DTO (``rest_api.views._artifact_system_fields``)
    or, for a serializer handed a raw ORM object, injected in
    ``to_representation``. Declaring the fields is what also lets a write
    payload carrying them pass ``UnknownFieldRejectionMixin`` (#851) instead of
    being rejected as unknown; the viewset applies them through the gateway.

    ``metaclass=`` is load-bearing for the same reason as on
    :class:`CustomFieldsSerializerMixin` (#290).
    """

    owner = serializers.JSONField(
        required=False,
        allow_null=True,
        help_text=(
            "Artifact owner in actor wire form (spec section 4): "
            '{"kind": "user", "id": "<uuid>"} or '
            '{"kind": "external", "name": "<label>"}.'
        ),
    )
    reporter = serializers.JSONField(
        required=False,
        allow_null=True,
        help_text="Artifact reporter in actor wire form (spec section 4).",
    )
    priority = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        help_text=(
            "Artifact priority. The scale is defined per attribute definition "
            "(type=enum; default low|medium|high|critical)."
        ),
    )
    # ADR-006: the ISO 42010 stakeholder selection of a StakeholderNeed. A list
    # of option values whose vocabulary lives in the attribute catalogue
    # (type=multi-enum) — a classification, NOT a person reference, which is why
    # it is not an actor field. Declared here for the same reason as the three
    # above: the value is persisted through ``_apply_artifact_system_fields`` →
    # ``ArtifactAttributeGateway`` (the column is on ``Artifact``), so the viewset
    # never passes it to the service; declaring it is what lets a payload carry it
    # past ``UnknownFieldRejectionMixin`` (#851) and what makes the read-back
    # include the key.
    stakeholder = serializers.JSONField(
        required=False,
        allow_null=True,
        help_text=(
            "ISO 42010 stakeholder role(s)/group(s) of the need, as a list of "
            "option values. The options are defined per (item_type, preset) in "
            "the attribute definition (type=multi-enum) and validated there."
        ),
    )

    def to_representation(self, instance: Any) -> dict[str, Any]:
        data = super().to_representation(instance)  # type: ignore[misc]
        # DTO dicts already carry the values (their builders add them); a raw
        # ORM object has no such attributes, so inject the actor-form values.
        if not isinstance(instance, dict):
            from application.artifact_attribute_gateway import artifact_system_fields

            data.update(artifact_system_fields(instance))
        return data



# ---------------------------------------------------------------------------
# Unknown-field rejection (issue #851)
# ---------------------------------------------------------------------------


class ClientUidRejectionMixin:
    """Reject a client-supplied ``uid`` instead of silently dropping it (#932).

    ``uid`` is declared ``read_only`` on all eight artifact serializers, so DRF
    discarded any value a client sent — the same silent-field-drop class as
    :class:`UnknownFieldRejectionMixin` (#851). Because the field was *also*
    never generated, no code path could fill it: every artifact's identifier
    stayed empty.

    ``uid`` is now system-owned — the create path allocates one
    (:func:`application.local_uid.generate_local_uid`), so a client must not set
    it. To stay safe for the UI's full-object save paths, echoing the *existing*
    value back (``uid == self.instance.uid``) is accepted as a no-op; any other
    supplied value — including on create — answers 400 with a field-scoped
    error, never a silent discard.
    """

    #: Field-scoped 400 message for a client-supplied ``uid`` (issue #932).
    UID_READONLY_MESSAGE = "uid is system-generated and read-only; omit it."

    def to_internal_value(self, data: Any) -> Any:
        supplied = data.get("uid") if isinstance(data, dict) else None
        if isinstance(supplied, str):
            supplied = supplied.strip()
        if supplied:
            current = (
                getattr(self.instance, "uid", None)
                if self.instance is not None
                else None
            )
            if supplied != current:
                raise serializers.ValidationError(
                    {"uid": [self.UID_READONLY_MESSAGE]}
                )
        return super().to_internal_value(data)  # type: ignore[misc]



class UnknownFieldRejectionMixin:
    """Reject request keys that no declared field on the serializer accepts (#851).

    DRF silently ignores a key it has no field for. On a create/update that
    means a typo or an unsupported field answers 201/200 while the value is
    absent from both the response and the persisted row — indistinguishable
    from success. That is the same #73/#580/QIRK-002 failure class
    ``UserProfileSerializer`` and ``TestCaseSerializer`` fixed one serializer
    at a time; this mixin is the shared implementation.

    Placement: the check runs in ``to_internal_value``, not ``validate``, so a
    subclass that overrides ``validate`` without calling ``super()`` cannot
    accidentally bypass it — exactly the hole ``TestCaseSerializer`` had to
    patch by hand before #851. It is also the one seam both create and update
    (partial or full) pass through.

    ``self.fields`` is authoritative: every declared field is accepted —
    required, optional, write-only (``change_reason``) and read-only alike.
    The always-allowed write keys (``change_reason``/``custom_fields``/
    ``expected_version``, see
    :data:`rest_api.mixins.workflow_transitions._ALWAYS_ALLOWED_PATCH_FIELDS`)
    pass even on a serializer that does not declare them, keeping this guard
    consistent with ``_validate_patch_payload`` and preserving the UI's
    full-form save paths. A key that passes only via that allowlist is still
    not written (DRF drops it), exactly as before.
    """

    def to_internal_value(self, data: Any) -> Any:
        validated = super().to_internal_value(data)  # type: ignore[misc]
        errors = unknown_field_errors(data, set(self.fields))
        if errors:
            raise serializers.ValidationError(errors)
        return validated



#: Per-field error text for a request key no declared field accepts (#851).
#: Shared by :class:`UnknownFieldRejectionMixin` (serializer routes) and
#: :func:`reject_unknown_fields` (raw ``request.data`` handlers) so both
#: surfaces report exactly the same message instead of a second format.
UNKNOWN_FIELD_MESSAGE = "Unknown field."



def unknown_field_errors(
    data: Any, allowed_keys: Container[str]
) -> dict[str, list[str]]:
    """Return ``{key: [UNKNOWN_FIELD_MESSAGE]}`` for undeclared keys (#851).

    ``data`` is only inspected when it is a mapping — a non-dict body is DRF's
    own concern, not an unknown-key one. The always-allowed write keys
    (:data:`rest_api.mixins.workflow_transitions._ALWAYS_ALLOWED_PATCH_FIELDS`)
    pass even when the caller's *allowed_keys* omits them, exactly as in the
    serializer mixin.
    """
    if not isinstance(data, dict):
        return {}
    allowed = set(allowed_keys) | set(_ALWAYS_ALLOWED_PATCH_FIELDS)
    return {key: [UNKNOWN_FIELD_MESSAGE] for key in data if key not in allowed}



def reject_unknown_fields(
    data: Any,
    allowed_keys: Container[str],
    lang: str = "en",
) -> Response | None:
    """Reject keys outside *allowed_keys* with a 400, or return ``None`` (#851).

    The raw-handler counterpart to :class:`UnknownFieldRejectionMixin`: a view
    that reads ``request.data`` directly cannot inherit the serializer mixin, so
    it calls this first and returns the response when it is not ``None``. The
    envelope — 400 ``VALIDATION_ERROR`` with one ``error.details`` entry per
    offending key, carrying :data:`UNKNOWN_FIELD_MESSAGE` — is identical to what
    the guarded-serializer routes produce, because both build on
    :func:`unknown_field_errors`.
    """
    errors = unknown_field_errors(data, allowed_keys)
    if not errors:
        return None
    return Response(
        build_error_response(
            "VALIDATION_ERROR",
            lang,
            details=[{"field": k, "errors": v} for k, v in errors.items()],
        ),
        status=status.HTTP_400_BAD_REQUEST,
    )



# ---------------------------------------------------------------------------
# Custom fields mixin (REQ-L2-AS-037)
# ---------------------------------------------------------------------------


class CustomFieldsSerializerMixin(
    UnknownFieldRejectionMixin, metaclass=serializers.SerializerMetaclass
):
    """Adds a writable ``custom_fields`` field with flat-map validation.

    REQ-L2-AS-037: custom_fields lives on the shared Artifact node but is
    exposed on every artifact-backed entity serializer so it can be read and
    written through the entity's own endpoint. Validation is delegated to
    :func:`persistence.custom_fields.validate_custom_fields` (single source of
    truth — no duplicate rules per serializer).

    #290: the ``metaclass=`` is load-bearing, not decoration. DRF collects
    declared fields in ``SerializerMetaclass._get_declared_fields``, which walks
    ``bases`` and only reads a base's ``_declared_fields`` attribute. A *plain*
    mixin never gets that attribute, so ``custom_fields`` stayed an inert class
    attribute: ``'custom_fields' in RequirementSerializer().fields`` was
    ``False``, the key never reached ``validated_data``, and the
    ``if "custom_fields" in data:`` branches in ``rest_api.views`` were dead
    code — every custom-field edit from the UI was silently dropped while the
    request still reported 200. Applying the metaclass here registers the field
    for every serializer mixing this in, which is what revives those branches.

    #269 follow-up: making the field live also made it a *stored-XSS* surface —
    keys and values round-trip byte-identically into the SPA, the PDF/ReqIF
    exporters and MCP responses. It is therefore declared as a
    :class:`SanitizedJSONField`, which (a) rejects markup / script URIs in the
    map's keys and values and (b) enrols ``custom_fields`` in the ViewSet-level
    guard, so the ~9 handlers that read ``request.data`` without running this
    serializer still return a field-scoped 400. The same rule is enforced a
    second time in ``persistence.custom_fields.validate_custom_fields`` for the
    write paths that never see a serializer at all (MCP, ReqIF import).
    """

    custom_fields = SanitizedJSONField(
        required=False,
        help_text=(
            "User-defined custom attributes as a flat key-value map "
            "(REQ-L2-AS-037). Values: string, number, boolean or null. "
            "HTML markup and script-capable URI schemes are rejected in both "
            "keys and values."
        ),
    )

    def validate_custom_fields(self, value: Any) -> dict:
        from django.core.exceptions import ValidationError as DjangoValidationError

        from persistence.custom_fields import validate_custom_fields

        try:
            return validate_custom_fields(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages[0] if exc.messages else str(exc))



# ---------------------------------------------------------------------------
# Optimistic locking mixin (SYSTEMAUDIT_2026-08-29, REST finding 1)
# ---------------------------------------------------------------------------


class ExpectedVersionSerializerMixin(metaclass=serializers.SerializerMetaclass):
    """Adds the write-only ``expected_version`` field used for optimistic locking.

    Pair with a service ``update_*(..., expected_version=...)``: the PATCH
    handler forwards ``validated_data.get("expected_version")`` and the service
    answers ``OptimisticLockError`` → **409 CONFLICT** when the caller's
    last-seen version is stale.

    Until the audit, only ``ArchitectureElementSerializer`` declared this field
    and only ``ArchitectureService`` honoured it, while
    ``_ALWAYS_ALLOWED_PATCH_FIELDS`` let the key through on *every* entity — so
    a client sending ``expected_version`` to Requirement/TestCase/Adr/... got a
    200 and a silent overwrite of whatever another session had written. Sharing
    one declaration keeps the schema and the enforcement from drifting apart
    again.

    ``metaclass=`` is load-bearing for exactly the reason spelled out on
    :class:`CustomFieldsSerializerMixin` (#290): DRF's ``SerializerMetaclass``
    only collects ``_declared_fields`` from bases that have it, so a plain mixin
    would leave the field inert and the value would never reach
    ``validated_data``.
    """

    expected_version = serializers.IntegerField(
        required=False,
        write_only=True,
        min_value=1,
        help_text=(
            "Optimistic locking: the ``version`` the client last read. When "
            "supplied and no longer current, the update is rejected with 409 "
            "CONFLICT instead of overwriting a concurrent edit. Omit it to "
            "accept last-writer-wins."
        ),
    )



class NormalizedChoiceField(serializers.ChoiceField):
    """ChoiceField that normalizes input string to Title-Case before validation.

    Allows API clients to send "open", "OPEN", or "Open" — all normalize to "Open"
    (or the appropriate Title-Case variant) before choice validation.
    """

    def to_internal_value(self, data):
        """Normalize string input to Title-Case before validating against choices."""
        if isinstance(data, str):
            data = data.title()
        return super().to_internal_value(data)



# ---------------------------------------------------------------------------
# Queryset optimization helpers (REQ-L2-RA-013, COMP-RA-006 integration point)
# ---------------------------------------------------------------------------

QUERYSET_OPTIMIZATIONS: dict[str, dict[str, list[str]]] = {
    "requirement": {
        "select_related": [
            "artifact",
            "artifact__workspace",
            "artifact__owner",
            "artifact__reporter",
        ],
        "prefetch_related": [],
    },
    "artifact": {
        "select_related": ["parent", "workspace"],
        "prefetch_related": [],
    },
    "architecture_element": {
        "select_related": [
            "artifact",
            "artifact__workspace",
            "artifact__owner",
            "artifact__reporter",
        ],
        "prefetch_related": [],
    },
    "test_case": {
        "select_related": [
            "artifact",
            "artifact__workspace",
            "artifact__owner",
            "artifact__reporter",
        ],
        "prefetch_related": [],
    },
    "trace_link": {
        "select_related": ["source", "target"],
        "prefetch_related": [],
    },
    "baseline": {
        "select_related": ["artifact"],
        "prefetch_related": [],
    },
    "workflow_definition": {
        "select_related": ["artifact"],
        "prefetch_related": [],
    },
}



def apply_queryset_optimizations(queryset: Any, entity_type: str) -> Any:
    """Apply select_related / prefetch_related to avoid N+1 queries.

    REQ-L2-RA-013: Must be called in ViewSet.get_queryset().

    Args:
        queryset: Django QuerySet.
        entity_type: Key in QUERYSET_OPTIMIZATIONS.

    Returns:
        Optimized queryset.
    """
    opts = QUERYSET_OPTIMIZATIONS.get(entity_type, {})
    for rel in opts.get("select_related", []):
        queryset = queryset.select_related(rel)
    for rel in opts.get("prefetch_related", []):
        queryset = queryset.prefetch_related(rel)
    return queryset
