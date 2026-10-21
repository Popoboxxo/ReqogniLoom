"""HTTP preconditions: ``ETag`` response headers and ``If-Match`` (GH-868/GH-923).

Repo-wide there was no ``ETag``/``If-Match`` support at all. The only
optimistic-locking seam was the ``expected_version`` *body* field
(``OptimisticLockError`` → 409, see ``application.optimistic_lock``), which an
HTTP cache, a proxy or a generic REST client cannot use — and which a client
can silently forget to send. This module adds the standard HTTP half of the
same guarantee for the resources named in the bundle (Requirement, TestCase,
Baseline, Workspace)::

    GET   /resource/{pk}/   -> ``ETag: "<version>"``
    PATCH /resource/{pk}/     ``If-Match: "<version>"``
                              stale -> 412 PRECONDITION_FAILED

Design decisions, each with the reason it is not the obvious alternative:

* **One tag source, no drift.** :func:`compute_etag` derives the tag from the
  entity's ``version`` counter — the very counter ``expected_version`` and
  ``assert_expected_version`` compare against — so an ``ETag`` and a
  body-supplied version can never disagree about which revision is "current".
  A content hash would have needed a canonical serialisation of every field
  and would silently diverge from the counter the services actually enforce.
* **Strong tags only.** ``If-Match`` uses *strong* comparison (RFC 9110
  § 13.1.1), so a ``W/``-prefixed tag can never satisfy it; emitting one would
  be a guarantee that never holds.
* **The compare stays in the service.** A single strong integer tag is
  forwarded as ``expected_version`` (see
  :meth:`ETagMixin.resolve_expected_version`), so the authoritative compare
  still runs inside the service's row-locked transaction
  (``application.optimistic_lock.lock_for_version_check``). Checking the
  header in the view and *then* calling the service would leave a window in
  which a concurrent write could land — a false guarantee, which is worse than
  no guarantee.
* **Additive only.** ``ETag`` is a response header, ``If-Match`` an optional
  request header: a request without ``If-Match`` behaves exactly as before.

``If-Match`` decision matrix (GH-1396)
--------------------------------------

Before GH-1396 the parser collapsed five *different* inputs into one ``None``
("no assertion") and the view then fell back to the body's
``expected_version`` — so a weak validator, ``,``-list, ``*``, a malformed
value and an absent header were indistinguishable, and every one of them
answered 200. Parsing is now explicit (:class:`IfMatch`) and the HTTP answer is
derived from it:

===============================  ==============================================
``If-Match`` header value        Result
===============================  ==============================================
absent                           no assertion → body ``expected_version``
                                 fallback preserved (200 unless body conflicts)
present but empty / whitespace   400 ``INVALID_IF_MATCH`` (malformed)
``*``                            matches any existing representation → 200,
                                 no revision comparison
single strong tag matching      200
single strong tag not matching  412 ``PRECONDITION_FAILED``
weak validator (``W/"6"``,      syntactically valid, but ``If-Match`` requires
``w/"6"``)                       *strong* comparison (RFC 9110 § 13.1.1) → a weak
                                 tag can never match → 412
missing/unbalanced quotes       400 ``INVALID_IF_MATCH`` (malformed)
a tag containing a comma        one opaque tag, not a list separator: ``"a,b"``
(``"a,b"``)                      is a single strong tag (``etagc`` covers
                                 ``0x23``–``0x7E``) and therefore compares as a
                                 whole
non-ASCII ``obs-text`` tag       one opaque tag: ``etagc`` also covers
(``0x80``–``0xFF``)              ``0x80``–``0xFF``, so such a tag is *not*
                                 malformed
list of tags (``"1", "6"``)     valid grammar → 200 when ANY strong tag equals
                                 the current ``ETag``, else 412; weak entries
                                 in the list never match
list with a malformed entry     400 ``INVALID_IF_MATCH`` (malformed)
lone comma / only separators     400 ``INVALID_IF_MATCH`` — a documented
                                 deviation, see below
===============================  ==============================================

The split between 400 and 412 is deliberate: **400 means the header is not a
syntactically valid ``If-Match`` field-value, so the server cannot evaluate the
precondition at all; 412 means it was evaluated and does not hold.** A parser
that answered 412 for ``garbage`` would tell the client "your cached copy is
stale — re-read and retry", which is advice that can never succeed; a parser
that answered 200 would silently drop the client's write protection. Hence the
strict rejection.

**Documented deviation from RFC 9110 § 5.6.1:** empty list elements are skipped
as the ABNF requires (``"1",,"6"`` is two tags), but a field-value that reduces
to *zero* tags — a lone ``,``, ``, ,`` or a present-but-blank header — is
rejected as malformed. The RFC makes an empty list valid (it matches nothing, so
the precondition simply fails with 412); this server answers 400 instead,
because "I sent ``If-Match``" with no tag at all is a client bug, and 400 tells
the caller to fix the request rather than to re-read a representation that can
never satisfy it. Clients must not rely on the RFC's empty-list form here.

The field-value is scanned, not split: a comma inside a quoted entity-tag is
part of that tag's opaque value, so ``If-Match: "a,b"`` is one tag. A
``split(",")`` would cut it in half and report a legal header as malformed.

Workflow transitions are the one exception on the status side: there the same
header guards the ``WorkflowItemState`` revision, not the entity tag, and a
mismatch is **409 CONFLICT** by design (CR-08). Only the parser is shared; the
mapping stays with the route (see ``WorkflowTransitionsMixin``).

Layering note (ADR-01): the mixin only translates HTTP preconditions. The
version compare itself remains in the Layer-2 services, so REST and MCP cannot
drift apart.
"""
from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import Enum
from functools import cached_property
from typing import Any

from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response

__all__ = [
    "ETagMixin",
    "EntityTag",
    "IfMatch",
    "IfMatchKind",
    "IfMatchMismatch",
    "InvalidIfMatch",
    "compute_etag",
    "parse_if_match",
    "parse_if_match_version",
]

#: RFC 9110 entity-tag: optional (case-insensitive) weak prefix plus a quoted
#: opaque value. The opaque value is the RFC's ``etagc``: ``0x21``, the range
#: ``0x23``–``0x7E`` and ``obs-text`` ``0x80``–``0xFF`` — so ``"`` (0x22) and
#: whitespace terminate it, while a comma or a non-ASCII byte is legal *inside*
#: it. Deliberately unanchored: :func:`parse_if_match` scans the field-value and
#: matches at a position, which is what keeps a quoted comma from being read as
#: a list separator. ABNF literals are case-insensitive, hence ``[Ww]/``.
_ENTITY_TAG_RE = re.compile(r'([Ww]/)?"([\x21\x23-\x7e\x80-\xff]*)"')

#: Optional whitespace inside the field-value (RFC 9110 § 5.6.3).
_OWS = " \t"

#: Header field name, spelled once (RFC 9110 § 13.1.1).
_IF_MATCH = "If-Match"


def compute_etag(entity: Any) -> str | None:
    """Return the strong entity-tag for *entity*, or ``None`` when untaggable.

    The tag is the entity's ``version`` counter, formatted as a quoted
    integer (``"3"``). That counter increments on every write of every
    ``AuditableModel``-backed entity, which makes it exactly the "did this
    representation change?" token an ``ETag`` is meant to be.

    Entities without a ``version`` counter fall back to the timestamps
    ``AuditableModel`` already maintains. The one resource in scope that needs
    that path is ``BaselineDetail``: baselines are immutable (the PATCH route
    answers 405), so they never bump a counter, and ``created_at`` is stable
    for the lifetime of the row — all an ``ETag`` has to be.

    Args:
        entity: An ORM instance or read-model dataclass for the resource.

    Returns:
        A quoted strong entity-tag, or ``None`` when *entity* carries neither a
        version nor a timestamp (caller must then emit no ``ETag`` header).
    """
    version = getattr(entity, "version", None)
    if version is not None:
        return f'"{version}"'
    for attr in ("modified_at", "updated_at", "created_at"):
        stamp = getattr(entity, attr, None)
        if stamp is None:
            continue
        isoformat = getattr(stamp, "isoformat", None)
        return f'"{isoformat() if callable(isoformat) else stamp}"'
    return None


class IfMatchKind(str, Enum):
    """What an ``If-Match`` field-value *is*, independent of any resource.

    Replaces the old ``str | None`` return value, where the single value
    ``None`` carried four mutually exclusive meanings (absent, ``*``, weak tag,
    malformed multi-tag list) and every caller had to guess which one it got.
    """

    #: No ``If-Match`` header at all — no assertion, body fallback applies.
    ABSENT = "absent"
    #: ``*`` — "the resource exists", not a revision assertion (RFC 9110).
    ANY = "any"
    #: One or more syntactically valid entity-tags.
    TAGS = "tags"
    #: Present, but not a valid ``If-Match`` field-value. ``reason`` says why.
    MALFORMED = "malformed"


@dataclass(frozen=True)
class EntityTag:
    """One parsed entity-tag: its opaque value and whether it is weak."""

    value: str
    weak: bool = False

    @property
    def quoted(self) -> str:
        """The tag in wire form (``"3"`` / ``W/"3"``) — what ``ETag`` compares."""
        return f'W/"{self.value}"' if self.weak else f'"{self.value}"'


@dataclass(frozen=True)
class IfMatch:
    """The unambiguous parse result of an ``If-Match`` header (GH-1396)."""

    kind: IfMatchKind
    tags: tuple[EntityTag, ...] = ()
    reason: str = ""

    @cached_property
    def strong_tags(self) -> tuple[EntityTag, ...]:
        """The tags usable for ``If-Match``'s strong comparison."""
        return tuple(tag for tag in self.tags if not tag.weak)


def parse_if_match(header: str | None) -> IfMatch:
    """Parse an ``If-Match`` field-value into an explicit :class:`IfMatch`.

    The value is *scanned* left to right, not ``split(",")``: an entity-tag's
    opaque value may legally contain a comma, so only a comma **outside** the
    quotes separates list elements. Each element is matched with
    :data:`_ENTITY_TAG_RE`, which accepts RFC 9110's ``etagc`` (including
    ``obs-text``) and a case-insensitive ``W/`` prefix.

    Grammar (RFC 9110 § 13.1.1): ``"*" / #entity-tag``. Empty list elements are
    skipped as § 5.6.1 requires; a header that survives to zero tags — including
    a present-but-blank header and a lone comma — is
    :attr:`IfMatchKind.MALFORMED`. That last choice deliberately deviates from
    the RFC (an empty list would be valid and simply match nothing); see the
    module docstring for the reason.

    Args:
        header: Raw ``If-Match`` field-value, or ``None`` when absent.

    Returns:
        An :class:`IfMatch` whose ``kind`` is one of ``ABSENT``, ``ANY``,
        ``TAGS`` or ``MALFORMED``. Never a bare ``None``-means-everything.
    """
    if header is None:
        return IfMatch(IfMatchKind.ABSENT)
    if header.strip(_OWS) == "*":
        return IfMatch(IfMatchKind.ANY)

    tags: list[EntityTag] = []
    position = 0
    length = len(header)
    while position < length:
        # Optional whitespace between elements.
        while position < length and header[position] in _OWS:
            position += 1
        if position >= length:
            break
        if header[position] == ",":
            # RFC 9110 § 5.6.1: empty list elements are legal padding.
            position += 1
            continue
        match = _ENTITY_TAG_RE.match(header, position)
        if match is None:
            return IfMatch(
                IfMatchKind.MALFORMED,
                reason=f"{header[position:]!r} is not a quoted entity-tag",
            )
        tags.append(
            EntityTag(value=match.group(2), weak=match.group(1) is not None)
        )
        position = match.end()
        # Two entity-tags must be comma-separated; OWS alone is not a separator
        # (``"6" "9"`` is malformed, not two tags).
        while position < length and header[position] in _OWS:
            position += 1
        if position < length and header[position] != ",":
            return IfMatch(
                IfMatchKind.MALFORMED,
                reason=(
                    f"{header[position:]!r} follows an entity-tag without a comma"
                ),
            )
    if not tags:
        return IfMatch(IfMatchKind.MALFORMED, reason="the header carries no entity-tag")
    return IfMatch(IfMatchKind.TAGS, tags=tuple(tags))


def _version_of(tag: EntityTag) -> int | None:
    """Return the integer version encoded in *tag*, or ``None`` if not numeric."""
    try:
        return int(tag.value)
    except (TypeError, ValueError):
        return None


def parse_if_match_version(header: str | None) -> int | None:
    """Extract the revision asserted by an ``If-Match`` header, if unambiguous.

    Returns the integer encoded in a single strong entity-tag (``"7"`` → ``7``)
    or ``None`` when the header does not name exactly one strong numeric
    revision. This is the *narrow* version-extraction view of the header and it
    keeps its historical contract, so existing callers and tests are unaffected
    by GH-1396. It is deliberately not the enforcement path any more: the
    mixin uses :func:`parse_if_match`, which can tell a weak tag from a
    malformed one (both used to be ``None``).

    Args:
        header: Raw ``If-Match`` field-value, or ``None``.

    Returns:
        The asserted version, or ``None`` when the header is not a single
        strong tag holding an integer.
    """
    parsed = parse_if_match(header)
    if parsed.kind is not IfMatchKind.TAGS or len(parsed.tags) != 1:
        return None
    tag = parsed.tags[0]
    if tag.weak:
        return None
    return _version_of(tag)


class InvalidIfMatch(Exception):
    """The ``If-Match`` header is not a valid field-value → HTTP 400.

    Carries the parser's ``reason`` (client input only, never internals) so the
    view can explain what was rejected; ``str()`` stays empty so a route that
    only maps the exception through ``_service_error_response`` surfaces the
    localised registry message instead of an English parse fragment. Deliberately
    not a ``ValueError`` subclass: several transition views map ``ValueError``
    to a generic ``VALIDATION_ERROR``, which would swallow the dedicated code.
    """

    def __init__(self, reason: str = "") -> None:
        self.reason = reason
        super().__init__("")


class IfMatchMismatch(Exception):
    """No strong tag in ``If-Match`` can match the current representation.

    The route decides the status: ``412 PRECONDITION_FAILED`` on the ``ETag``
    endpoints, ``409 CONFLICT`` on ``transitions/`` (CR-08). ``str()`` stays
    empty so the reason never leaks into a client-visible message.
    """

    def __init__(self, reason: str = "") -> None:
        self.reason = reason
        super().__init__("")


class ETagMixin:
    """``ETag`` response header + ``If-Match`` precondition helpers (GH-868).

    Mixed into :class:`rest_api.views.BaseEntityViewSet`, so every entity
    ViewSet can opt in by calling :meth:`with_etag` /
    :meth:`resolve_expected_version` / :meth:`check_if_match`. Nothing is
    emitted automatically: a ViewSet that never calls these behaves byte-for-
    byte as before, which keeps the change additive for the ~24 entities the
    bundle does not cover.
    """

    @staticmethod
    def uses_if_match(request: Request) -> bool:
        """True when the request carries an ``If-Match`` header of any value.

        Membership, not truthiness (GH-1396): ``If-Match:`` with an empty value
        is present and therefore malformed. A truthiness check reported it as
        absent, so the malformed value was silently ignored instead of rejected.
        """
        return _IF_MATCH in request.headers

    def with_etag(self, response: Response, entity: Any) -> Response:
        """Attach *entity*'s current ``ETag`` to *response* and return it.

        Used on both GET and PATCH responses: a client that stores the tag from
        either response can safely use it as the next ``If-Match``.
        """
        etag = compute_etag(entity)
        if etag is not None:
            response["ETag"] = etag
        return response

    def if_match_parse_error(self, request: Request) -> Response | None:
        """Return 400 for a present-but-malformed ``If-Match``, else ``None``.

        A pure string check (no resource read), for the top of a write handler:
        a malformed precondition must be rejected *before* any side effect, so a
        route that can write on one branch and compare on another never ends up
        answering 400 after having already changed something.
        """
        parsed = parse_if_match(request.headers.get(_IF_MATCH))
        if parsed.kind is IfMatchKind.MALFORMED:
            return self.invalid_if_match(request, parsed.reason)
        return None

    def invalid_if_match(self, request: Request, reason: str = "") -> Response:
        """Build the ``400 INVALID_IF_MATCH`` response (standard envelope).

        The counterpart of :meth:`precondition_failed`: a malformed header is
        not an evaluated precondition, so it must not answer 412.
        """
        # Local import: ``rest_api.serializers`` imports this package (it pulls
        # ``_ALWAYS_ALLOWED_PATCH_FIELDS`` from ``mixins.workflow_transitions``),
        # so a module-level import here would close a cycle at import time.
        from rest_api.serializers import build_error_response, detect_lang

        return Response(
            build_error_response(
                "INVALID_IF_MATCH",
                detect_lang(request),
                details=[{"reason": reason}] if reason else None,
            ),
            status=status.HTTP_400_BAD_REQUEST,
        )

    def if_match_error(self, request: Request, exc: Exception) -> Response:
        """Map a resolver exception to this route's HTTP answer.

        ``InvalidIfMatch`` → 400, ``IfMatchMismatch`` → 412. Used by the
        ``ETag`` endpoints; ``transitions/`` maps the same mismatch to 409
        itself, because there the header guards the workflow revision.

        Any *other* exception is re-raised (GH-1396 review finding m4). The
        previous implementation answered 412 for everything that was not an
        ``InvalidIfMatch``, which turned a programming error — a ``TypeError``
        in the resolver, a broken ``current`` loader — into "your cached copy
        is stale, re-read and retry": advice that can never succeed and that
        hides the defect from monitoring. A 412 is only ever an *evaluated*
        precondition, so only ``IfMatchMismatch`` may produce one.
        """
        if isinstance(exc, InvalidIfMatch):
            return self.invalid_if_match(request, exc.reason)
        if isinstance(exc, IfMatchMismatch):
            return self.precondition_failed(request)
        raise exc

    def resolve_expected_version(
        self,
        request: Request,
        data: Mapping[str, Any],
        *,
        current: Callable[[], Any] | None = None,
    ) -> int | None:
        """Return the version to hand to a service ``update_*`` call.

        Precedence — the HTTP precondition wins, the body field is the
        fallback:

        1. ``If-Match: *`` → ``None``: the client asserted existence only, so no
           revision is compared (and a stale body ``expected_version`` is
           ignored — the header wins, as everywhere in this method).
        2. ``If-Match: "<n>"`` → ``n`` (also when the body carries a different
           ``expected_version``: the client asserted two different revisions;
           the standard HTTP one is authoritative, and it is the only one an
           intermediary can reason about).
        3. A tag list whose strong members are compared against the resource's
           current ``ETag``; the matching tag's version is forwarded, so the
           authoritative compare stays inside the service's row lock. The
           matching tag must encode a *numeric* revision: a non-numeric tag
           (the ISO timestamp a Baseline emits) has nothing to forward, so it
           raises ``IfMatchMismatch`` instead of degrading to an unguarded
           write.
        4. Otherwise the legacy ``expected_version`` body field, unchanged —
           including ``None``, which keeps the current last-writer-wins
           behaviour for callers that do not track versions.

        Forwarding the resolved value (instead of comparing here and forwarding
        nothing) is what makes the check atomic: the service compares it inside
        its row-locked transaction.

        Args:
            request: The incoming PATCH request.
            data: The serializer's ``validated_data`` for that request.
            current: Lazy loader for the current row, used only for the shapes
                that need a real ``ETag`` comparison (tag list, non-numeric
                tag). ``None`` means "this route cannot compare" — such a
                header is then a mismatch rather than silently ignored.

        Raises:
            InvalidIfMatch: The header is present but not a valid ``If-Match``.
            IfMatchMismatch: No strong tag can match the current representation.
        """
        parsed = parse_if_match(request.headers.get(_IF_MATCH))

        if parsed.kind is IfMatchKind.MALFORMED:
            raise InvalidIfMatch(parsed.reason)
        if parsed.kind is IfMatchKind.ABSENT:
            return data.get("expected_version")
        if parsed.kind is IfMatchKind.ANY:
            return None

        strong = parsed.strong_tags
        if not strong:
            # Only weak validators: strong comparison can never hold.
            raise IfMatchMismatch("If-Match carries no strong entity-tag")
        if len(parsed.tags) == 1:
            tag = strong[0]
            version = _version_of(tag)
            # ``str(version) == tag.value`` keeps the read-free path for the tag
            # this stack emits (``"6"``). A non-canonical number (``"06"``,
            # ``"+6"``) is NOT equal to ``"6"`` under RFC 9110's opaque
            # comparison, so it falls through to the real ETag compare instead of
            # being accepted because ``int("06") == 6``.
            if version is not None and str(version) == tag.value:
                # Common path: no extra read, the service compares under its lock.
                return version

        # A tag list or a non-numeric tag: compare against the current ETag.
        if current is None:
            raise IfMatchMismatch(
                "this route has no current representation to compare If-Match against"
            )
        etag = compute_etag(current())
        if etag is None:
            raise IfMatchMismatch("the resource carries no ETag")
        for tag in strong:
            if tag.quoted == etag:
                version = _version_of(tag)
                # Invariant (GH-1396 review finding m3): every caller of this
                # method forwards the return value as the service's
                # ``expected_version``, so a *non-numeric* matching tag cannot be
                # honoured — returning ``None`` would tell the service "the
                # caller tracks no version" and the row-locked compare would be
                # skipped, silently reopening the exact TOCTOU window this
                # method exists to close. The only non-numeric tag this stack
                # emits is a Baseline's ISO timestamp, and the Baseline PATCH is
                # immutable (405) and uses ``check_if_match`` instead. A route
                # that ever forwards a timestamp tag here must therefore be
                # rejected as a mismatch rather than silently unguarded.
                if version is None:
                    raise IfMatchMismatch(
                        "the matching If-Match tag is not a numeric revision and "
                        "cannot be forwarded as expected_version"
                    )
                return version
        raise IfMatchMismatch("no If-Match tag matches the current ETag")

    def check_if_match(self, request: Request, entity: Any) -> Response | None:
        """Return an error response when *entity* does not satisfy ``If-Match``.

        The out-of-band variant, for a route that has already loaded the row
        and cannot forward a version to a service — the immutable Baseline
        PATCH is the only current caller. Prefer
        :meth:`resolve_expected_version`, which is race-free.

        Args:
            request: The incoming request.
            entity: The freshly loaded current row.

        Returns:
            A 400 ``INVALID_IF_MATCH`` response when the header is malformed, a
            412 response when no strong tag matches, else ``None``.
        """
        parsed = parse_if_match(request.headers.get(_IF_MATCH))
        if parsed.kind in (IfMatchKind.ABSENT, IfMatchKind.ANY):
            # No header → no assertion; ``*`` → the row was loaded, so it holds.
            return None
        if parsed.kind is IfMatchKind.MALFORMED:
            return self.invalid_if_match(request, parsed.reason)

        etag = compute_etag(entity)
        if etag is None:
            return self.precondition_failed(request)
        if any(tag.quoted == etag for tag in parsed.strong_tags):
            return None
        return self.precondition_failed(request)

    def precondition_failed(self, request: Request) -> Response:
        """Build the ``412 Precondition Failed`` response (standard envelope)."""
        # Local import: see ``invalid_if_match`` for the cycle.
        from rest_api.serializers import build_error_response, detect_lang

        return Response(
            build_error_response("PRECONDITION_FAILED", detect_lang(request)),
            status=status.HTTP_412_PRECONDITION_FAILED,
        )
