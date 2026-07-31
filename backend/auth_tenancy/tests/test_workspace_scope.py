"""Unit tests for request -> workspace resolution (GitHub #103).

:func:`~auth_tenancy.workspace_scope.resolve_request_workspace_id` runs inside
DRF authentication, so it must be total: any input it cannot interpret has to
yield ``None`` (fall back to the previous tenant-wide behaviour and let the view
produce the proper 400/404) rather than raise, which would surface as a
misleading auth error.
"""
from __future__ import annotations

import uuid

from auth_tenancy.workspace_scope import resolve_request_workspace_id


class _Match:
    """Stand-in for ``django.urls.ResolverMatch``."""

    def __init__(self, kwargs: dict | None = None, route: str = "") -> None:
        self.kwargs = kwargs or {}
        self.route = route


class _Request:
    """Minimal DRF-request stand-in covering the fields the resolver reads."""

    def __init__(
        self,
        *,
        resolver_match: _Match | None = None,
        query_params: dict | None = None,
        method: str = "GET",
        content_type: str = "application/json",
        data: object = None,
        data_raises: bool = False,
    ) -> None:
        self.resolver_match = resolver_match
        self.query_params = query_params if query_params is not None else {}
        self.method = method
        self.content_type = content_type
        self._data = data
        self._data_raises = data_raises

    @property
    def data(self) -> object:
        if self._data_raises:
            raise ValueError("unparsable body")
        return self._data


def test_resolves_workspace_pk_url_kwarg() -> None:
    ws = uuid.uuid4()
    request = _Request(resolver_match=_Match({"workspace_pk": str(ws)}))
    assert resolve_request_workspace_id(request) == ws


def test_resolves_workspace_id_url_kwarg() -> None:
    ws = uuid.uuid4()
    request = _Request(resolver_match=_Match({"workspace_id": str(ws)}))
    assert resolve_request_workspace_id(request) == ws


def test_resolves_bare_pk_only_on_workspace_route() -> None:
    """``pk`` names a workspace only under ``workspaces/<uuid:pk>`` routes."""
    ws = uuid.uuid4()
    on_workspace_route = _Request(
        resolver_match=_Match({"pk": str(ws)}, route="api/v1/workspaces/<uuid:pk>/")
    )
    assert resolve_request_workspace_id(on_workspace_route) == ws

    # A requirement id must never be mistaken for a workspace id.
    on_other_route = _Request(
        resolver_match=_Match({"pk": str(ws)}, route="api/v1/requirements/<uuid:pk>/")
    )
    assert resolve_request_workspace_id(on_other_route) is None


def test_resolves_query_param() -> None:
    ws = uuid.uuid4()
    request = _Request(query_params={"workspace_id": str(ws)})
    assert resolve_request_workspace_id(request) == ws


def test_url_kwarg_wins_over_query_param() -> None:
    """A caller-supplied query param must not override the routed workspace."""
    routed = uuid.uuid4()
    request = _Request(
        resolver_match=_Match({"workspace_pk": str(routed)}),
        query_params={"workspace_id": str(uuid.uuid4())},
    )
    assert resolve_request_workspace_id(request) == routed


def test_resolves_json_body_on_write_methods() -> None:
    ws = uuid.uuid4()
    request = _Request(method="POST", data={"workspace_id": str(ws)})
    assert resolve_request_workspace_id(request) == ws


def test_body_ignored_for_safe_methods() -> None:
    request = _Request(method="GET", data={"workspace_id": str(uuid.uuid4())})
    assert resolve_request_workspace_id(request) is None


def test_body_ignored_for_non_json_content_type() -> None:
    request = _Request(
        method="POST",
        content_type="multipart/form-data; boundary=x",
        data={"workspace_id": str(uuid.uuid4())},
    )
    assert resolve_request_workspace_id(request) is None


def test_malformed_values_yield_none() -> None:
    """Garbage must degrade to ``None``, never raise (would become a 401/500)."""
    for value in ("not-a-uuid", "", "   ", None, ["a"], {"a": 1}, True, 12345):
        request = _Request(query_params={"workspace_id": value})
        assert resolve_request_workspace_id(request) is None, value


def test_unparsable_body_yields_none() -> None:
    request = _Request(method="POST", data_raises=True)
    assert resolve_request_workspace_id(request) is None


def test_non_dict_body_yields_none() -> None:
    request = _Request(method="POST", data=["not", "a", "dict"])
    assert resolve_request_workspace_id(request) is None


def test_request_without_resolver_match_yields_none() -> None:
    assert resolve_request_workspace_id(_Request()) is None
