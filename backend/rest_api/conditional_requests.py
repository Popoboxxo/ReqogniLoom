"""Which API operations honour HTTP conditional requests — issue #1397.

The published OpenAPI document advertised a ``412`` response on four ``PATCH``
operations but declared **no** ``If-Match`` request header anywhere: the
contract said "this call can fail with a precondition failure" without saying
which input triggers it, so a generated client could neither build the request
that is guarded nor the retry that recovers from it. This module is the single
source of truth for that pairing, and
``rest_api.tests.test_conditional_request_contract_1397`` fails the build when
the generated document and this module disagree in either direction.

The decision (recorded for #1397, deliberately not extended in that issue)
--------------------------------------------------------------------------
Only four *PATCH* operations implement optimistic locking through an ``ETag``
they also emit on ``GET``: ``Requirement``, ``TestCase``, ``Baseline`` and
``Workspace``. They are the only entities whose ``ETag`` is derived from a
monotonic ``version`` counter (or, for the immutable ``Baseline``, a stable
``created_at`` timestamp) — the very value ``expected_version`` compares
against, so an ``ETag`` and the body field can never disagree about which
revision is current.

Retrofitting ``ETag``/``If-Match`` onto the six core artifact families — ``Adr``,
``ArchitectureElement``, ``ChangeRequest``, ``Issue``, ``Risk`` and
``StakeholderNeed`` — would add a write precondition to six ViewSets that have
no client asking for one, i.e. it would turn a contract-honesty fix into a
behaviour change: a stale header would start refusing writes that answered
``200`` before. Those families keep their ``expected_version`` **body** field
(stale → ``409``) and are documented as *not* supporting conditional requests.

Scope of the machine-checkable negative half
--------------------------------------------
:data:`UNSUPPORTED_CONDITIONAL_FAMILIES` enumerates the detail paths of those
six core artifact families, plus the legacy ``changerequests`` alias of the
change-request detail route and ``GlossaryTerm`` (artifact-shaped, but not one
of the six). It is deliberately **not** an inventory of the whole API: 36 other
``PATCH`` operations declare neither ``412`` nor ``If-Match`` and are covered by
the other gate direction ("no operation outside
:data:`CONDITIONAL_REQUEST_OPERATIONS` declares the header") instead of being
enumerated here. The prose this module publishes says exactly that, rather than
claiming every remaining resource.

``POST`` actions are a third, separate contract
-----------------------------------------------
Five ``POST`` actions do evaluate ``If-Match``: ``adrs/{id}/supersede/``,
``goals/{id}/outdate/``, ``goals/{id}/reactivate/``,
``main-goals/{id}/approve/`` and ``change-requests/{id}/transition/`` (plus the
legacy ``changerequests/{id}/transition/`` alias of the same view). They guard
the ``WorkflowItemState`` revision, not the entity ``ETag``, so a lost
precondition is **409 CONFLICT** (CR-08) and never ``412``; a malformed
field-value is still ``400 INVALID_IF_MATCH``. They are listed in
:data:`CONDITIONAL_ACTION_OPERATIONS` so that neither half of the 412 contract
can drift: a ``412`` on one of these routes would be a lie, and so would silence
about the header they evaluate.

Rules for changing this file
----------------------------
* Adding an entry to :data:`CONDITIONAL_REQUEST_OPERATIONS` requires the route
  to actually evaluate the header (``ETagMixin.check_if_match`` or
  ``ETagMixin.resolve_expected_version``) **and** to emit the matching ``ETag``
  on the read that a client would condition against. An allowlist entry without
  a real evaluation is exactly the defect #1397 fixes, mirrored.
* The same change must add the ``If-Match`` parameter
  (``rest_api.views._IF_MATCH_PARAMETER``) to the operation's
  ``@extend_schema`` and the ``412`` response — the gate test asserts both.
* Removing an entry means removing the ``412`` response too; a ``412`` that no
  longer appears in the document is just as much a drift as an undeclared one.
* Adding an entry to :data:`CONDITIONAL_ACTION_OPERATIONS` means the action
  really calls the shared ``If-Match`` resolver, maps a malformed value to
  ``400`` and a mismatch to ``409``, and declares **no** ``412``.
"""

from __future__ import annotations

from typing import Final

__all__ = [
    "CONDITIONAL_ACTION_OPERATIONS",
    "CONDITIONAL_REQUESTS_DESCRIPTION",
    "CONDITIONAL_REQUEST_OPERATIONS",
    "UNSUPPORTED_CONDITIONAL_FAMILIES",
]


#: ``(path, method)`` pairs that legitimately declare ``412`` and an
#: ``If-Match`` request header. ``method`` is the lowercase HTTP method as it
#: appears in the generated document.
#:
#: Five entries for four ViewSets: ``TestCaseViewSet`` is routed twice —
#: ``rest_api/urls.py`` registers ``testcases`` (legacy, un-hyphenated) and
#: ``test-cases`` (canonical kebab-case, #1177) — and drf-spectacular documents
#: both as separate paths. They are the *same* view, so both are honest.
CONDITIONAL_REQUEST_OPERATIONS: Final[frozenset[tuple[str, str]]] = frozenset(
    {
        ("/api/v1/baselines/{id}/", "patch"),
        ("/api/v1/requirements/{id}/", "patch"),
        ("/api/v1/test-cases/{id}/", "patch"),
        ("/api/v1/testcases/{id}/", "patch"),
        ("/api/v1/workspaces/{id}/", "patch"),
    }
)

#: ``POST`` actions that evaluate an optional ``If-Match`` header against the
#: **workflow** revision rather than the entity ``ETag``.
#:
#: Each entry records the contract that operation implements:
#:
#: * it accepts the same header syntax (``rest_api.mixins.etag.parse_if_match``;
#:   section 1's grammar applies unchanged, including ``400
#:   INVALID_IF_MATCH`` for a malformed field-value);
#: * a lost precondition answers ``409 CONFLICT`` (CR-08) — **never** ``412``;
#: * it emits no ``ETag``: the guarded revision is ``WorkflowItemState.version``,
#:   which is only discoverable from the ``version`` key of the corresponding
#:   ``.../transitions/`` GET/POST response, so this contract is documented here
#:   and in ``docs/api/REST-CONVENTIONS.md`` §1 rather than as an ``If-Match``
#:   parameter with a ``412`` response.
#:
#: Six entries for five view implementations: ``ChangeRequestViewSet`` is routed
#: twice (``change-requests`` and the legacy ``changerequests`` alias, §7), and
#: both spellings reach the same ``transition`` action.
CONDITIONAL_ACTION_OPERATIONS: Final[dict[tuple[str, str], str]] = {
    ("/api/v1/adrs/{id}/supersede/", "post"): (
        "Evaluates If-Match against the workflow revision: malformed -> 400 "
        "INVALID_IF_MATCH, lost precondition -> 409 CONFLICT, never 412; no "
        "ETag is emitted."
    ),
    ("/api/v1/change-requests/{id}/transition/", "post"): (
        "Evaluates If-Match against the workflow revision: malformed -> 400 "
        "INVALID_IF_MATCH, lost precondition -> 409 CONFLICT, never 412; no "
        "ETag is emitted."
    ),
    ("/api/v1/changerequests/{id}/transition/", "post"): (
        "Legacy alias of /change-requests/{id}/transition/ — same view, same "
        "If-Match contract: 400 INVALID_IF_MATCH, 409 CONFLICT, never 412."
    ),
    ("/api/v1/goals/{id}/outdate/", "post"): (
        "Evaluates If-Match against the workflow revision: malformed -> 400 "
        "INVALID_IF_MATCH, lost precondition -> 409 CONFLICT, never 412; no "
        "ETag is emitted."
    ),
    ("/api/v1/goals/{id}/reactivate/", "post"): (
        "Evaluates If-Match against the workflow revision: malformed -> 400 "
        "INVALID_IF_MATCH, lost precondition -> 409 CONFLICT, never 412; no "
        "ETag is emitted."
    ),
    ("/api/v1/main-goals/{id}/approve/", "post"): (
        "Evaluates If-Match against the workflow revision: malformed -> 400 "
        "INVALID_IF_MATCH, lost precondition -> 409 CONFLICT, never 412; no "
        "ETag is emitted."
    ),
}

#: Detail paths of the families that do **not** support conditional requests,
#: each with the one-line reason. Their ``PATCH`` accepts the
#: ``expected_version`` body field (stale → ``409 CONFLICT``) but emits no
#: ``ETag`` and ignores ``If-Match``, so they must never declare ``412``.
#:
#: It contains the six core artifact families (``adrs``, ``architecture``,
#: ``change-requests``, ``issues``, ``needs``, ``risks``) plus ``glossary`` —
#: artifact-shaped and PATCHable without being one of the six — and
#: ``changerequests``, the legacy alias of the ``change-requests`` detail route
#: (§7). Leaving either of the last two out would have let a documented
#: non-conditional family escape the gate.
UNSUPPORTED_CONDITIONAL_FAMILIES: Final[dict[str, str]] = {
    "/api/v1/adrs/{id}/": (
        "Adr has no version-derived ETag; PATCH honours the expected_version "
        "body field only."
    ),
    "/api/v1/architecture/{id}/": (
        "ArchitectureElement has no version-derived ETag; PATCH honours the "
        "expected_version body field only."
    ),
    "/api/v1/change-requests/{id}/": (
        "ChangeRequest has no version-derived ETag; PATCH honours the "
        "expected_version body field only."
    ),
    "/api/v1/changerequests/{id}/": (
        "Legacy alias of /change-requests/{id}/ — same ChangeRequest view, same "
        "expected_version-only PATCH contract."
    ),
    "/api/v1/glossary/{id}/": (
        "GlossaryTerm has no version-derived ETag; PATCH honours the "
        "expected_version body field only."
    ),
    "/api/v1/issues/{id}/": (
        "Issue has no version-derived ETag; PATCH honours the expected_version "
        "body field only."
    ),
    "/api/v1/needs/{id}/": (
        "StakeholderNeed has no version-derived ETag; PATCH honours the "
        "expected_version body field only."
    ),
    "/api/v1/risks/{id}/": (
        "Risk has no version-derived ETag; PATCH honours the expected_version "
        "body field only."
    ),
}

#: Paragraph appended to ``SPECTACULAR_SETTINGS["DESCRIPTION"]``.
#:
#: Kept next to the allowlist instead of in ``settings.py`` so the published
#: summary and the machine-readable sets cannot drift: both are computed from
#: the same module, and the gate test checks the schema against it.
CONDITIONAL_REQUESTS_DESCRIPTION: Final[str] = (
    "Conditional requests (ETag / If-Match): the requirement, test-case "
    "(both the /test-cases/ and legacy /testcases/ spellings), workspace and "
    "baseline PATCH operations implement HTTP optimistic locking. Their GET "
    "responses carry an ETag (a successful PATCH returns the new one), and "
    "their PATCH accepts an optional If-Match request header; a "
    "strong-comparison mismatch answers 412 "
    "PRECONDITION_FAILED and a malformed field-value answers 400 "
    "INVALID_IF_MATCH. No other PATCH operation supports conditional requests: "
    "the six core artifact families (ADR, architecture element, change "
    "request, issue, risk and stakeholder need) and glossary terms emit no "
    "ETag and ignore If-Match on PATCH, so they accept the "
    "expected_version body field instead (stale -> 409 CONFLICT). A 412 is "
    "therefore only ever declared where If-Match is honoured on PATCH. Five "
    "POST actions are separately conditional: adrs/{id}/supersede/, "
    "goals/{id}/outdate/, goals/{id}/reactivate/, main-goals/{id}/approve/ and "
    "change-requests/{id}/transition/ (plus its legacy changerequests/ alias) "
    "evaluate an optional If-Match header against the workflow revision, "
    "answering 400 INVALID_IF_MATCH for a malformed value and 409 CONFLICT for "
    "a lost precondition — never 412. They emit no ETag; the guarded workflow "
    "revision is the version key of the corresponding transitions/ response."
)
