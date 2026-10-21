"""Which API operations honour HTTP conditional requests — issue #1397.

The published OpenAPI document advertised a ``412`` response on four ``PATCH``
operations but declared **no** ``If-Match`` request header anywhere: the
contract said "this call can fail with a precondition failure" without saying
which input triggers it, so a generated client could neither build the request
that is guarded nor the retry that recovers from it. This module is the single
source of truth for that pairing, and
``rest_api.tests.test_conditional_request_contract_1397`` fails the build when
the generated document and this list disagree in either direction.

The decision (recorded for #1397, deliberately *not* extended in that issue)
--------------------------------------------------------------------------
Only four ``PATCH`` operations implement optimistic locking through an ``ETag``
they also emit on ``GET``: ``Requirement``, ``TestCase``, ``Baseline`` and
``Workspace``. They are the only entities whose ``ETag`` is derived from a
monotonic ``version`` counter (or, for the immutable ``Baseline``, a stable
``created_at`` timestamp) — the very value ``expected_version`` compares
against, so an ``ETag`` and the body field can never disagree about which
revision is current.

Retrofitting ``ETag``/``If-Match`` onto the six remaining artifact families
would add a write precondition to six ViewSets that have no client asking for
one, i.e. it would turn a contract-honesty fix into a behaviour change — a
stale header would start refusing writes that answered ``200`` before. Those
families keep their ``expected_version`` **body** field (stale → ``409``) and
are documented as *not* supporting conditional requests. They are listed in
:data:`UNSUPPORTED_CONDITIONAL_FAMILIES` so the negative half of the contract
is machine-checkable too, instead of living only in prose.

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
"""

from __future__ import annotations

from typing import Final

__all__ = [
    "CONDITIONAL_REQUEST_OPERATIONS",
    "CONDITIONAL_REQUESTS_DESCRIPTION",
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

#: Detail paths of the families that do **not** support conditional requests,
#: each with the one-line reason. Their ``PATCH`` accepts the
#: ``expected_version`` body field (stale → ``409 CONFLICT``) but emits no
#: ``ETag`` and ignores ``If-Match``, so they must never declare ``412``.
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
    "/api/v1/glossary/{id}/": (
        "GlossaryTerm has no version-derived ETag; PATCH honours the "
        "expected_version body field only."
    ),
    "/api/v1/issues/{id}/": (
        "Issue has no version-derived ETag; PATCH honours the expected_version "
        "body field only."
    ),
    "/api/v1/risks/{id}/": (
        "Risk has no version-derived ETag; PATCH honours the expected_version "
        "body field only."
    ),
}

#: Paragraph appended to ``SPECTACULAR_SETTINGS["DESCRIPTION"]``.
#:
#: Kept next to the allowlist instead of in ``settings.py`` so the published
#: summary and the machine-readable set cannot drift: both are computed from
#: the same module, and the gate test checks the schema against it.
CONDITIONAL_REQUESTS_DESCRIPTION: Final[str] = (
    "Conditional requests (ETag / If-Match): the requirement, test-case "
    "(both the /test-cases/ and legacy /testcases/ spellings), workspace and "
    "baseline PATCH operations implement HTTP optimistic locking. Their GET "
    "responses carry an ETag (a successful PATCH returns the new one), and "
    "their PATCH accepts an optional If-Match request header; a "
    "strong-comparison mismatch answers 412 "
    "PRECONDITION_FAILED and a malformed field-value answers 400 "
    "INVALID_IF_MATCH. All other resources do not support conditional "
    "requests: they emit no ETag and ignore If-Match, so they accept the "
    "expected_version body field instead (stale -> 409 CONFLICT). A 412 is "
    "therefore only ever declared where If-Match is honoured."
)
