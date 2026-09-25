"""``X-Workspace-ID`` is decorative: it never reaches the resolved identity.

Audit track CR-22 (``docs/se/reports/deep_audit/system-audit-2026-09/
09-evidence-register.md``). Negative coverage for the claim that the header is
inert on the REST surface.

What is actually asserted
-------------------------
Not "the header does not cause a 403" — that is all the pre-existing
``test_workspace_scoped_roles.py::test_workspaceless_bearer_uses_live_user_and_roles_only``
proves, and it proves it on a *separate headerless* request, so the two
observations are never compared. Here the **same** authenticated principal is
authenticated twice, once with the header and once without, and the two
resulting :class:`~auth_tenancy.context.AuthContext` objects are compared field
by field. Equality is the claim: the header is decorative.

Why the header cannot be live
-----------------------------
The REST adapter resolves the request's target workspace in exactly one place,
``auth_tenancy.workspace_scope.resolve_request_workspace_id``, whose three
sources are the URL kwargs, the ``workspace_id`` query parameter and the JSON
body field (module docstring, lines 8-17). It reads no HTTP header, so there is
no code path by which ``X-Workspace-ID`` could reach
``AuthTenancyAuthentication.authenticate``'s role resolution
(``auth_tenancy/rest.py:180``). These tests pin that from the outside, so a
future change that starts honouring the header fails here rather than silently
widening authority.

Header variants are parametrised because CR-22 claims "beliebige
X-Workspace-ID-Werte": a cross-tenant workspace UUID, a same-tenant UUID the
caller holds no role in, a non-UUID string, and an empty value.
"""
from __future__ import annotations

import time
import uuid
from datetime import timedelta

import pytest
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient, APIRequestFactory

from auth_tenancy.context import AuthContext
from auth_tenancy.jwt_tokens import encode_hs256
from auth_tenancy.models import ROLE_ADMIN, ROLE_EDITOR, UserRole
from auth_tenancy.rest import AuthTenancyAuthentication
from auth_tenancy.services.authentication import AuthenticationService
from auth_tenancy.workspace_scope import resolve_request_workspace_id
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace

_SECRET = "w1-header-test-jwt-signing-placeholder"
_JWT_OVERRIDES = dict(
    AUTH_JWT_SECRET=_SECRET,
    AUTH_JWT_ISSUER="reqflow",
    AUTH_JWT_AUDIENCE="reqflow-api",
    AUTH_JWT_TTL_SECONDS=3600,
)

#: A workspaceless endpoint: no workspace in the URL, no query, no body. Any
#: identity change observed here can therefore only have come from the header.
_ENDPOINT = "/api/v1/prompt-templates/"

#: Every field of :class:`AuthContext` that carries authority or provenance.
_IDENTITY_FIELDS = (
    "user_id",
    "tenant_id",
    "active_roles",
    "auth_method",
    "api_key_id",
    "tenant_name",
    "workspace_id",
    "actor_type",
    "agent_label",
    "scope",
    "api_key_workspace_ids",
)


def _tenant_with_two_workspaces() -> tuple[Tenant, User, Workspace, Workspace]:
    """Create one tenant, one user and two workspaces (A and B), no roles yet."""
    slug = f"w1hdr-{uuid.uuid4().hex[:8]}"
    tenant = Tenant.objects.create(name=f"T-{slug}", slug=slug, is_active=True)
    user = User.objects.create(
        username=f"user-{slug}", email=f"{slug}@t.test", tenant=tenant
    )
    set_request_tenant(tenant.id)
    try:
        workspace_a = Workspace.objects.create(
            tenant=tenant, name=f"WS-A-{slug}", preset={"name": "extended"}
        )
        workspace_b = Workspace.objects.create(
            tenant=tenant, name=f"WS-B-{slug}", preset={"name": "extended"}
        )
    finally:
        clear_request_tenant()
    return tenant, user, workspace_a, workspace_b


def _other_tenant_workspace() -> Workspace:
    """Create a workspace in a *different* tenant than the caller's."""
    slug = f"w1hdr-other-{uuid.uuid4().hex[:8]}"
    tenant = Tenant.objects.create(name=f"T-{slug}", slug=slug, is_active=True)
    set_request_tenant(tenant.id)
    try:
        return Workspace.objects.create(
            tenant=tenant, name=f"WS-X-{slug}", preset={"name": "extended"}
        )
    finally:
        clear_request_tenant()


def _grant(tenant: Tenant, user: User, workspace: Workspace, role: str) -> None:
    """Create a non-suspended role assignment for ``user`` in ``workspace``."""
    set_request_tenant(tenant.id)
    try:
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=workspace, role=role
        )
    finally:
        clear_request_tenant()


def _mint_bearer(user: User, tenant: Tenant, roles: list[str]) -> str:
    """Mint a valid JWT carrying ``roles`` as its (tenant-wide) roles claim."""
    now = int(time.time())
    return encode_hs256(
        {
            "user_id": str(user.id),
            "tenant_id": str(tenant.id),
            "roles": roles,
            "iss": "reqflow",
            "aud": "reqflow-api",
            "iat": now,
            "exp": now + 3600,
        },
        secret=_SECRET,
    )


def _authenticate(request) -> AuthContext:
    """Return the AuthContext the REST authenticator builds for ``request``."""
    try:
        _principal, context = AuthTenancyAuthentication().authenticate(request)
    finally:
        clear_request_tenant()
    return context


def _identity(context: AuthContext) -> dict:
    """Return every identity field of ``context`` as a comparable mapping."""
    return {name: getattr(context, name) for name in _IDENTITY_FIELDS}


# ---------------------------------------------------------------------------
# The header is never consulted during request->workspace resolution
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize(
    "header_value",
    [
        pytest.param("str(uuid4())", id="non-uuid-string"),
        pytest.param("", id="empty"),
        pytest.param("   ", id="whitespace"),
        pytest.param("0" * 8, id="wrong-length-hex"),
        pytest.param("../../etc/passwd", id="path-like"),
        pytest.param("null", id="literal-null"),
    ],
)
@override_settings(**_JWT_OVERRIDES)
def test_x_workspace_id_header_is_not_a_resolution_source(
    header_value: str,
) -> None:
    """``resolve_request_workspace_id`` must ignore the header outright.

    The mechanism assertion: the header is not a fourth resolution source, so no
    downstream role resolution can ever be steered by it. Every value yields
    ``None`` — the same answer as a request that carries no header at all.
    """
    request = APIRequestFactory().get(
        _ENDPOINT, HTTP_X_WORKSPACE_ID=header_value
    )

    assert resolve_request_workspace_id(request) is None


@pytest.mark.django_db
@override_settings(**_JWT_OVERRIDES)
def test_x_workspace_id_header_is_ignored_even_with_a_resolvable_workspace() -> None:
    """A real workspace UUID in the header is still not a resolution source.

    Guards against a future implementation that merely *validates* the header
    before honouring it: the value here names an existing workspace of the
    caller's own tenant, so any "is this a real workspace?" short-circuit
    would resolve it.
    """
    _tenant, _user, _workspace_a, workspace_b = _tenant_with_two_workspaces()
    request = APIRequestFactory().get(
        _ENDPOINT, HTTP_X_WORKSPACE_ID=str(workspace_b.id)
    )

    assert resolve_request_workspace_id(request) is None


# ---------------------------------------------------------------------------
# The resolved AuthContext is identical with and without the header
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize(
    "header_kind", ["cross_tenant", "same_tenant_no_role", "non_uuid", "empty"]
)
@override_settings(**_JWT_OVERRIDES)
def test_bearer_auth_context_is_identical_with_and_without_the_header(
    header_kind: str,
) -> None:
    """Same principal, two requests, identical identity — CR-22 core claim.

    ``header_kind`` covers CR-22's "beliebige X-Workspace-ID-Werte": a workspace
    in a foreign tenant, a workspace in the caller's own tenant where the caller
    holds no role, a non-UUID string, and an empty value.
    """
    tenant, user, workspace_a, workspace_b = _tenant_with_two_workspaces()
    _grant(tenant, user, workspace_a, ROLE_ADMIN)
    token = _mint_bearer(user, tenant, [ROLE_ADMIN, ROLE_EDITOR])

    if header_kind == "cross_tenant":
        header_value = str(_other_tenant_workspace().id)
    elif header_kind == "same_tenant_no_role":
        header_value = str(workspace_b.id)
    elif header_kind == "non_uuid":
        header_value = "not-a-uuid-at-all"
    else:
        header_value = ""

    without = _authenticate(
        APIRequestFactory().get(_ENDPOINT, HTTP_AUTHORIZATION=f"Bearer {token}")
    )
    with_header = _authenticate(
        APIRequestFactory().get(
            _ENDPOINT,
            HTTP_AUTHORIZATION=f"Bearer {token}",
            HTTP_X_WORKSPACE_ID=header_value,
        )
    )

    # The header must not have silently become the target workspace, and must
    # not have shifted the resolved roles off the live user/role state.
    assert with_header.workspace_id is None
    assert with_header.workspace_id == without.workspace_id
    assert with_header.tenant_id == without.tenant_id == tenant.id
    assert with_header.user_id == without.user_id == user.id
    assert with_header.active_roles == without.active_roles == (ROLE_ADMIN,)
    assert with_header.actor_type == without.actor_type == "user"
    assert _identity(with_header) == _identity(without)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "header_value_kind", ["cross_tenant", "same_tenant_no_role", "non_uuid", "empty"]
)
@override_settings(**_JWT_OVERRIDES)
def test_api_key_auth_context_is_identical_with_and_without_the_header(
    header_value_kind: str,
) -> None:
    """Same claim on the API-key surface, which also carries the fence fields.

    The API-key path adds ``actor_type``/``agent_label``/``scope``/
    ``api_key_workspace_ids`` to the identity, so comparing the whole field set
    also proves the header cannot disturb a workspace-fenced agent key.
    """
    tenant, user, workspace_a, workspace_b = _tenant_with_two_workspaces()
    _grant(tenant, user, workspace_a, ROLE_ADMIN)
    key = AuthenticationService().create_api_key(
        user_id=user.id,
        tenant_id=tenant.id,
        name="w1neg-user-key",
        principal_type="agent",
        agent_label="header-probe-agent",
        scope="write",
        workspace_ids=[str(workspace_a.id)],
        expires_at=timezone.now() + timedelta(days=1),
    )

    if header_value_kind == "cross_tenant":
        header_value = str(_other_tenant_workspace().id)
    elif header_value_kind == "same_tenant_no_role":
        header_value = str(workspace_b.id)
    elif header_value_kind == "non_uuid":
        header_value = "not-a-uuid-at-all"
    else:
        header_value = ""

    without = _authenticate(
        APIRequestFactory().get(_ENDPOINT, HTTP_X_API_KEY=key.plaintext)
    )
    with_header = _authenticate(
        APIRequestFactory().get(
            _ENDPOINT,
            HTTP_X_API_KEY=key.plaintext,
            HTTP_X_WORKSPACE_ID=header_value,
        )
    )

    assert with_header.actor_type == without.actor_type == "agent"
    assert with_header.api_key_workspace_ids == without.api_key_workspace_ids
    assert with_header.workspace_id is None
    assert with_header.workspace_id == without.workspace_id
    assert with_header.tenant_id == without.tenant_id == tenant.id
    assert with_header.user_id == without.user_id == user.id
    assert with_header.active_roles == without.active_roles
    assert _identity(with_header) == _identity(without)


# ---------------------------------------------------------------------------
# End-to-end: the endpoint's own authorization verdict is unchanged
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize(
    "header_value_kind", ["cross_tenant", "same_tenant_no_role", "non_uuid", "empty"]
)
@override_settings(**_JWT_OVERRIDES)
def test_endpoint_authorization_is_identical_with_and_without_the_header(
    header_value_kind: str,
) -> None:
    """A real request pair: same status, same payload, header or not.

    The unit-level comparison above pins the identity; this pins the observable
    consequence, so the claim holds for the caller and not only for the
    ``AuthContext`` dataclass.
    """
    tenant, user, workspace_a, workspace_b = _tenant_with_two_workspaces()
    _grant(tenant, user, workspace_a, ROLE_ADMIN)
    token = _mint_bearer(user, tenant, [ROLE_ADMIN])

    if header_value_kind == "cross_tenant":
        header_value = str(_other_tenant_workspace().id)
    elif header_value_kind == "same_tenant_no_role":
        header_value = str(workspace_b.id)
    elif header_value_kind == "non_uuid":
        header_value = "not-a-uuid-at-all"
    else:
        header_value = ""

    without = APIClient()
    without.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    plain = without.get(_ENDPOINT)

    with_header = APIClient()
    with_header.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    decorated = with_header.get(_ENDPOINT, HTTP_X_WORKSPACE_ID=header_value)

    assert plain.status_code == 200, plain.content
    assert decorated.status_code == plain.status_code, decorated.content
    assert decorated.json() == plain.json()


@pytest.mark.django_db
@override_settings(**_JWT_OVERRIDES)
def test_header_naming_a_workspace_the_caller_holds_no_role_in_grants_nothing() -> None:
    """The negative of the CR-22 escalation: the header cannot *grant* a role.

    The caller is admin in workspace A only. A POST that names workspace B in
    the URL *and* repeats it in the header must still be denied, so the header
    neither supplies the missing role nor substitutes for the URL kwarg.
    """
    tenant, user, workspace_a, workspace_b = _tenant_with_two_workspaces()
    _grant(tenant, user, workspace_a, ROLE_ADMIN)
    token = _mint_bearer(user, tenant, [ROLE_ADMIN])

    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    response = client.post(
        f"/api/v1/workspaces/{workspace_b.id}/needs/",
        {"title": "must-not-be-created"},
        format="json",
        HTTP_X_WORKSPACE_ID=str(workspace_b.id),
    )
    assert response.status_code == 403, response.content
