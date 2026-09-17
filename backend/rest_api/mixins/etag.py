"""HTTP preconditions: ``ETag`` response headers and ``If-Match`` (GH-868/GH-923).

Repo-wide there was no ``ETag``/``If-Match`` support at all. The only
optimistic-locking seam was the ``expected_version`` *body* field
(``OptimisticLockError`` → 409, see ``application.optimistic_lock``), which an
HTTP cache, a proxy or a generic REST client cannot use — and which a client
can silently forget to send. This module adds the standard HTTP half of the
same guarantee for the three resources named in the bundle (Requirement,
TestCase, Baseline)::

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
* **The compare stays in the service.** The version encoded in ``If-Match`` is
  forwarded as ``expected_version`` (see
  :meth:`ETagMixin.resolve_expected_version`), so the authoritative compare
  still runs inside the service's row-locked transaction
  (``application.optimistic_lock.lock_for_version_check``). Checking the
  header in the view and *then* calling the service would leave a window in
  which a concurrent write could land — a false guarantee, which is worse than
  no guarantee.
* **Additive only.** ``ETag`` is a response header, ``If-Match`` an optional
  request header: neither the response body nor any status code of an existing
  flow changes, and a request without ``If-Match`` behaves exactly as before.

Layering note (ADR-01): the mixin only translates HTTP preconditions. The
version compare itself remains in the Layer-2 services, so REST and MCP cannot
drift apart.
"""
from __future__ import annotations

import re
from typing import Any, Mapping

from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response

__all__ = ["ETagMixin", "compute_etag", "parse_if_match_version"]

#: RFC 9110 entity-tag: optional weak prefix plus a quoted opaque value.
#: Anchored so a malformed field-value (unquoted, embedded quote, trailing
#: garbage) is rejected instead of being read as a tag that would then compare
#: unequal and produce a misleading 412.
_ENTITY_TAG_RE = re.compile(r'^\s*(W/)?"([^"\s]*)"\s*$')

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


def _single_strong_tag(header: str | None) -> str | None:
    """Return the opaque value of a single strong entity-tag, else ``None``.

    ``None`` for an absent/blank header, ``*`` (an existence check, not a
    revision check — RFC 9110 § 13.1.1), a weak tag (never satisfies
    ``If-Match``'s strong comparison), a multi-tag list, or a malformed
    field-value.
    """
    if not header or header.strip() == "*":
        return None
    parts = [part for part in (chunk.strip() for chunk in header.split(",")) if part]
    if len(parts) != 1:
        return None
    match = _ENTITY_TAG_RE.match(parts[0])
    if match is None or match.group(1) is not None:
        return None
    return match.group(2)


def parse_if_match_version(header: str | None) -> int | None:
    """Extract the revision asserted by an ``If-Match`` header, if unambiguous.

    Returns the integer encoded in a single strong entity-tag (``"7"`` → ``7``)
    or ``None`` when the header carries no single revision this stack can hand
    to a service (see :func:`_single_strong_tag` for the rejected shapes).

    In those cases the caller falls back to the legacy ``expected_version``
    body field, i.e. the documented backward-compatible mechanism, rather than
    inventing a comparison the service cannot express. Multi-tag lists are a
    deliberate scope limit: matching "any of N revisions" would need a
    ``version IN (...)`` compare in the service, which no ``update_*`` offers.

    A non-numeric tag also yields ``None``. That is harmless for
    :meth:`ETagMixin.resolve_expected_version` (a version is by definition
    numeric); :meth:`ETagMixin.check_if_match` compares the *tag* directly and
    accepts a non-numeric one, which is what the timestamp tag of an immutable
    baseline needs.

    Args:
        header: Raw ``If-Match`` field-value, or ``None``.

    Returns:
        The asserted version, or ``None`` when the header is not a single
        strong tag holding an integer.
    """
    value = _single_strong_tag(header)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


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
        """True when the request carries an ``If-Match`` precondition."""
        return bool(request.headers.get(_IF_MATCH))

    def with_etag(self, response: Response, entity: Any) -> Response:
        """Attach *entity*'s current ``ETag`` to *response* and return it.

        Used on both GET and PATCH responses: a client that stores the tag from
        either response can safely use it as the next ``If-Match``.
        """
        etag = compute_etag(entity)
        if etag is not None:
            response["ETag"] = etag
        return response

    def resolve_expected_version(
        self, request: Request, data: Mapping[str, Any]
    ) -> int | None:
        """Return the version to hand to a service ``update_*`` call.

        Precedence — the HTTP precondition wins, the body field is the
        fallback:

        1. ``If-Match: "<n>"`` → ``n`` (also when the body carries a different
           ``expected_version``: the client asserted two different revisions;
           the standard HTTP one is authoritative, and it is the only one an
           intermediary can reason about).
        2. Otherwise the legacy ``expected_version`` body field, unchanged —
           including ``None``, which keeps the current last-writer-wins
           behaviour for callers that do not track versions.

        Forwarding the resolved value (instead of comparing here and forwarding
        nothing) is what makes the check atomic: the service compares it inside
        its row-locked transaction.

        Args:
            request: The incoming PATCH request.
            data: The serializer's ``validated_data`` for that request.

        Returns:
            The version the service must require, or ``None`` for no check.
        """
        asserted = parse_if_match_version(request.headers.get(_IF_MATCH))
        if asserted is not None:
            return asserted
        return data.get("expected_version")

    def check_if_match(self, request: Request, entity: Any) -> Response | None:
        """Return a 412 response when *entity* does not satisfy ``If-Match``.

        The out-of-band variant, for a route that has already loaded the row
        and cannot forward a version to a service — the immutable Baseline
        PATCH is the only current caller. Prefer
        :meth:`resolve_expected_version`, which is race-free.

        Args:
            request: The incoming request.
            entity: The freshly loaded current row.

        Returns:
            A 412 ``Response`` when the precondition fails, else ``None``.
        """
        header = request.headers.get(_IF_MATCH)
        if not header:
            return None
        if header.strip() == "*":
            # Existence check: *entity* was loaded, so the condition holds.
            return None
        current = compute_etag(entity)
        asserted = _single_strong_tag(header)
        if current is None or asserted is None:
            return self.precondition_failed(request)
        return None if current == f'"{asserted}"' else self.precondition_failed(request)

    def precondition_failed(self, request: Request) -> Response:
        """Build the ``412 Precondition Failed`` response (standard envelope)."""
        # Local import: ``rest_api.serializers`` imports this package (it pulls
        # ``_ALWAYS_ALLOWED_PATCH_FIELDS`` from ``mixins.workflow_transitions``),
        # so a module-level import here would close a cycle at import time.
        from rest_api.serializers import build_error_response, detect_lang

        return Response(
            build_error_response("PRECONDITION_FAILED", detect_lang(request)),
            status=status.HTTP_412_PRECONDITION_FAILED,
        )
