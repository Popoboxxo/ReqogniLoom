"""Coverage gate for the ADR-011 resource-scope classifier (SEC-02/SEC-03).

ADR-011 decision point 4 requires a coverage gate *before* the DEFAULT-DENY
seam is switched on: a test that enumerates every REST resource/view class over
the central classifier and turns red as long as **one** unclassified resource
exists. Without it a newly added view would silently be denied (or, worse, a
misclassification would fail a whole scope open).

The test also pins the two fail-closed rules of the ADR so the seam cannot be
"fixed" into a tenant-wide fallback:

* a ``workspace``-scoped resource whose target workspace is not resolvable is
  denied (403 semantics);
* a ``tenant``-scoped resource needs no target workspace and is *not* denied by
  that rule.

req_id: ADR-011, findings AUD-2026-09-222 / N2 / 240 / 035.
"""
from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from django.test import override_settings
from django.urls import get_resolver

from auth_tenancy.context import AuthContext, AuthMethod
from auth_tenancy.resource_scope import (
    _REGISTRY,
    UNCLASSIFIED_DENIAL,
    WORKSPACE_MEMBERSHIP_DENIAL,
    WORKSPACE_UNRESOLVABLE_DENIAL,
    ResourceScope,
    classify_class_name,
    enforce_request_scope,
)
from auth_tenancy.services import AuthorizationService

# View classes that are not application resources and therefore must never be
# classified as ``workspace``. They are still *declared* as ``exception`` so the
# gate stays data-driven rather than exempting them by name.
_FRAMEWORK_CLASSES = {
    "APIRootView",
    "RedirectView",
    "SpectacularAPIView",
    "SpectacularJSONAPIView",
    "SpectacularSwaggerView",
    "SpectacularRedocView",
    "VersionView",
    "HealthView",
    "PublicLoginBannerView",
    "LoginView",
    "RefreshView",
    "LogoutView",
    "McpHttpTransportView",
    "McpMessagesView",
    "McpSseTransportView",
}


def _view_classes_from_urlconf() -> dict[str, str]:
    """Return ``{class name: module}`` for every class-based URL callback."""
    classes: dict[str, str] = {}

    def walk(patterns, prefix=""):
        for pattern in patterns:
            if hasattr(pattern, "url_patterns"):
                walk(pattern.url_patterns, prefix + str(pattern.pattern))
                continue
            callback = getattr(pattern, "callback", None)
            cls = getattr(callback, "cls", None)
            if cls is not None:
                classes.setdefault(cls.__name__, cls.__module__)

    walk(get_resolver().url_patterns)
    return classes


def test_every_url_view_class_is_classified() -> None:
    """The gate: an unclassified view class turns this test red (ADR-011 §4)."""
    declared = _view_classes_from_urlconf()
    unclassified = sorted(
        name for name in declared if classify_class_name(name) is None
    )
    assert not unclassified, (
        "Unclassified REST resource/view class(es) found. Add each to "
        "_REGISTRY in auth_tenancy/resource_scope.py with an explicit scope "
        "(tenant | workspace | exception) and a reason for exceptions.\n"
        f"Unclassified: {unclassified}"
    )


def test_workspace_classes_have_resolution_metadata() -> None:
    """Every ``workspace`` class can name its target (object key or reason)."""
    from application.workspace_lookup import ENTITY_SPECS

    for name, classification in _REGISTRY.items():
        if classification.scope is not ResourceScope.WORKSPACE:
            continue
        has_entity = classification.entity_key is not None
        has_reason = bool(classification.reason)
        assert has_entity or has_reason, (
            f"{name}: workspace-scoped class must declare either an entity_key "
            "or a reason explaining how its target workspace is supplied."
        )
        if classification.entity_key is not None:
            assert classification.entity_key in ENTITY_SPECS, (
                f"{name}: unknown entity_key {classification.entity_key!r}"
            )


def test_exception_and_tenant_entries_are_named() -> None:
    """``exception`` entries must carry a reason (no silent fallback)."""
    for name, classification in _REGISTRY.items():
        if classification.scope is ResourceScope.EXCEPTION:
            assert classification.reason, f"{name}: exception needs a reason"
        if classification.scope is ResourceScope.TENANT:
            assert classification.reason, f"{name}: tenant scope needs a reason"


def test_registry_summary_counts() -> None:
    """The classification is non-trivial and structurally sane."""
    counts = {"tenant": 0, "workspace": 0, "exception": 0}
    for classification in _REGISTRY.values():
        counts[classification.scope.value] += 1
    # At least the core domain must be workspace-scoped and the admin surface
    # tenant-scoped; a regression that empties either group is a red flag.
    assert counts["workspace"] >= 20, counts
    assert counts["tenant"] >= 40, counts
    assert counts["exception"] >= 10, counts


# ---------------------------------------------------------------------------
# Fail-closed semantics of the seam (unit level, no DB)
# ---------------------------------------------------------------------------


class _UnclassifiedView:
    """A view class that is deliberately not in the registry."""


def _request(**kwargs) -> SimpleNamespace:
    base = dict(
        resolver_match=None,
        query_params={},
        method="GET",
        content_type="",
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def _context(**kwargs) -> AuthContext:
    values = dict(
        user_id=uuid4(),
        tenant_id=uuid4(),
        active_roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN,
    )
    values.update(kwargs)
    return AuthContext(**values)


@override_settings(AUTHZ_WORKSPACE_SCOPE_ENFORCED=True)
def test_unclassified_resource_is_denied_by_default() -> None:
    denial = enforce_request_scope(
        _request(), _UnclassifiedView(), _context(auth_method=AuthMethod.BEARER_TOKEN)
    )
    assert denial == UNCLASSIFIED_DENIAL


@override_settings(AUTHZ_WORKSPACE_SCOPE_ENFORCED=True)
def test_workspace_resource_without_target_is_denied() -> None:
    class _DeclaredWorkspaceView:
        pass

    from auth_tenancy import resource_scope

    resource_scope._declare(
        "_DeclaredWorkspaceView",
        resource_scope.ResourceClassification(resource_scope.ResourceScope.WORKSPACE),
    )
    try:
        denial = enforce_request_scope(
            _request(),
            _DeclaredWorkspaceView(),
            _context(auth_method=AuthMethod.BEARER_TOKEN),
        )
        assert denial == WORKSPACE_UNRESOLVABLE_DENIAL
    finally:
        resource_scope._REGISTRY.pop("_DeclaredWorkspaceView", None)


@override_settings(AUTHZ_WORKSPACE_SCOPE_ENFORCED=True)
def test_tenant_resource_without_target_is_not_denied_by_target_rule() -> None:
    class _DeclaredTenantView:
        pass

    from auth_tenancy import resource_scope

    resource_scope._declare(
        "_DeclaredTenantView",
        resource_scope.ResourceClassification(
            resource_scope.ResourceScope.TENANT, reason="tenant singleton"
        ),
    )
    try:
        denial = enforce_request_scope(
            _request(),
            _DeclaredTenantView(),
            _context(auth_method=AuthMethod.BEARER_TOKEN),
        )
        assert denial is None
    finally:
        resource_scope._REGISTRY.pop("_DeclaredTenantView", None)


@override_settings(AUTHZ_WORKSPACE_SCOPE_ENFORCED=False)
def test_seam_disabled_leaves_tenant_and_unclassified_alone() -> None:
    """With the flag off, only the (independent) API-key fence can deny."""
    ctx = _context(auth_method=AuthMethod.BEARER_TOKEN)
    assert enforce_request_scope(_request(), _UnclassifiedView(), ctx) is None


# ---------------------------------------------------------------------------
# ADR-013 review fixes — collection gate (M2), collection detection (CODE-4),
# restored membership (CODE-1) and fail-closed existence check (CODE-2)
# ---------------------------------------------------------------------------


def test_collection_action_requires_detail_false() -> None:
    """CODE-4: an action named ``create`` on a detail route is not a collection."""
    from auth_tenancy.resource_scope import _is_collection_action

    class _View:
        pass

    view = _View()
    view.action = "create"
    view.detail = True
    assert _is_collection_action(view) is False
    view.detail = False
    assert _is_collection_action(view) is True
    view.action = "retrieve"
    assert _is_collection_action(view) is False

    # A plain APIView (no action/detail) is never a collection.
    class _ApiView:
        pass

    assert _is_collection_action(_ApiView()) is False


@pytest.mark.parametrize("action", ["list", "create"])
def test_every_workspace_collection_action_is_fenced(action, monkeypatch) -> None:
    """M2 gate: every declared workspace-scoped view fences a *named* target.

    Iterating ``_REGISTRY`` means a newly added workspace-scoped view inherits
    this check automatically: its list/create must deny a caller with no
    authority in the named target workspace. The object/role lookups are
    short-circuited so this is a pure seam-structure test (no DB).
    """
    from auth_tenancy import resource_scope

    monkeypatch.setattr(resource_scope, "_workspace_in_active_tenant", lambda _ws: True)
    monkeypatch.setattr(
        resource_scope, "_has_active_role_in_workspace", lambda _ctx, _ws: False
    )
    monkeypatch.setattr(resource_scope, "_is_tenant_admin", lambda _ctx: False)

    target = uuid4()

    checked: list[str] = []
    for name, classification in _REGISTRY.items():
        if classification.scope is not ResourceScope.WORKSPACE:
            continue
        view_cls = type(name, (), {})
        view = view_cls()
        view.action = action
        view.detail = False
        request = _request(query_params={"workspace_id": str(target)})
        denial = enforce_request_scope(
            request, view, _context(workspace_id=target)
        )
        assert denial, f"{name}.{action}: named target workspace was not fenced"
        checked.append(f"{name}.{action}")
    assert len(checked) >= 20, checked


@override_settings(AUTHZ_WORKSPACE_SCOPE_ENFORCED=True)
def test_workspace_named_route_without_authority_is_denied(monkeypatch) -> None:
    """CODE-1: an ``entity_key=None`` route naming a workspace enforces authority."""
    from auth_tenancy import resource_scope

    class _DeclaredWorkspaceView:
        pass

    resource_scope._declare(
        "_DeclaredWorkspaceView",
        resource_scope.ResourceClassification(
            resource_scope.ResourceScope.WORKSPACE, reason="unit test"
        ),
    )
    monkeypatch.setattr(resource_scope, "_workspace_in_active_tenant", lambda _ws: True)
    monkeypatch.setattr(
        resource_scope, "_has_active_role_in_workspace", lambda _ctx, _ws: False
    )
    monkeypatch.setattr(resource_scope, "_is_tenant_admin", lambda _ctx: False)
    try:
        ws = uuid4()
        denial = enforce_request_scope(
            _request(query_params={"workspace_id": str(ws)}),
            _DeclaredWorkspaceView(),
            _context(),
        )
        assert denial == WORKSPACE_MEMBERSHIP_DENIAL
    finally:
        resource_scope._REGISTRY.pop("_DeclaredWorkspaceView", None)


@override_settings(AUTHZ_WORKSPACE_SCOPE_ENFORCED=True)
def test_workspace_named_route_denies_a_tenant_admin_lookup_that_errors(
    monkeypatch,
) -> None:
    """CODE-1: a failing elevation lookup stays fail-closed (deny, not allow)."""
    from auth_tenancy import resource_scope

    class _DeclaredWorkspaceView:
        pass

    resource_scope._declare(
        "_DeclaredWorkspaceView",
        resource_scope.ResourceClassification(
            resource_scope.ResourceScope.WORKSPACE, reason="unit test"
        ),
    )
    monkeypatch.setattr(resource_scope, "_workspace_in_active_tenant", lambda _ws: True)
    monkeypatch.setattr(
        resource_scope, "_has_active_role_in_workspace", lambda _ctx, _ws: False
    )

    def _boom(self, **_kwargs):
        raise RuntimeError("lookup down")

    monkeypatch.setattr(AuthorizationService, "is_tenant_admin", _boom)
    try:
        ws = uuid4()
        denial = enforce_request_scope(
            _request(query_params={"workspace_id": str(ws)}),
            _DeclaredWorkspaceView(),
            _context(),
        )
        assert denial == WORKSPACE_MEMBERSHIP_DENIAL
    finally:
        resource_scope._REGISTRY.pop("_DeclaredWorkspaceView", None)


def test_workspace_in_active_tenant_fails_closed_on_error(monkeypatch) -> None:
    """CODE-2: a resolution error must deny downstream, not read as "absent"."""
    from auth_tenancy import resource_scope

    def _boom(_ws):
        raise RuntimeError("db down")

    monkeypatch.setattr(resource_scope, "workspace_exists", _boom)
    assert resource_scope._workspace_in_active_tenant(uuid4()) is True


#: The only workspace-scoped routes allowed to delegate the membership decision
#: to their handler/service (ADR-013 CODE-1). Growing this set is a deliberate,
#: reviewable act: each entry must carry a non-empty ``handler_guard`` naming the
#: enforcement point.
_EXPECTED_HANDLER_GUARDS = {"WorkspaceMembersView"}


def test_only_expected_routes_defer_membership_to_the_handler() -> None:
    guarded = {
        name for name, classification in _REGISTRY.items() if classification.handler_guard
    }
    assert guarded == _EXPECTED_HANDLER_GUARDS
    for name in guarded:
        assert len(_REGISTRY[name].handler_guard) > 20, name
