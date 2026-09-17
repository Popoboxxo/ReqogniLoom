"""Governance configuration surfaces require the ADMIN tier on REST (#865 follow-up).

The security review of #865 found that the governance-relevant settings views
were still only AUTHOR-tier: their protection is the in-body
``ctx.has_role(ROLE_ADMIN)`` check, which does not narrow an AUTHOR-tier key
whose *owner* legitimately holds the Admin role. Prompt-template writes are the
canonical persistent prompt-injection vector (REQ-043), so the capability tier —
not the role — has to deny them.

This suite drives real API keys of every tier through the real URL routes:

* AUTHOR      -> 403 on every governance write, but still 201 on a normal
                 artifact write,
* ADMIN       -> allowed on both,
* READ_ONLY   -> 403 on the writes (unchanged legacy behaviour),
* reads       -> unchanged: no tier is denied a GET by the new declaration.

Covered surfaces: the settings views named by #865 (LLM settings, prompt
templates incl. the per-slot route and reset, review policy, context-graph
configuration) plus their REST siblings for the ``prompt_variable`` /
``link_type`` / ``attribute_*`` MCP namespaces — otherwise the ADMIN tier on MCP
would leave REST as the hole.

It also pins the declaration itself (``required_scope_operation`` per HTTP
method) so a future refactor cannot silently drop it from one of the views —
the MCP counterpart of these namespaces is covered by
``mcp_server.tests.test_api_key_granular_scope_865``.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_ADMIN, UserRole
from auth_tenancy.services import Operation
from auth_tenancy.services.authentication import AuthenticationService
from link_types.builtin import builtin_definition
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import PromptTemplate, PromptVariable, Tenant, User, Workspace
from rest_api.attribute_catalog_views import (
    AttributeCatalogAddToDefinitionView,
    AttributeCatalogDeprecateView,
    AttributeCatalogDetailView,
    AttributeCatalogImportView,
    AttributeCatalogListView,
)
from rest_api.attribute_definition_views import (
    AttributeDefaultsDetailView,
    AttributeDefaultsImportView,
    WorkspaceAttributeDefinitionImportView,
    WorkspaceAttributeDefinitionResetView,
    WorkspaceAttributeDefinitionView,
)
from rest_api.attribute_migration_views import (
    AttributeMigrationApplyView,
    AttributeMigrationRollbackView,
)
from rest_api.auth_enforcer import AdminScopeRequiredMixin
from rest_api.link_type_views import (
    LinkTypeDefaultsDetailView,
    LinkTypeDefaultsListView,
    WorkspaceLinkTypeDetailView,
    WorkspaceLinkTypeResetView,
)
from rest_api.prompt_variable_views import PromptVariableDetailView
from rest_api.settings_views import (
    ContextGraphRebuildView,
    ContextGraphSettingsView,
    LlmSettingsView,
    PromptTemplateResetView,
    PromptTemplateSlotDetailView,
    PromptTemplateView,
    ReviewPolicyView,
)

_PROMPT_TEMPLATES = "/api/v1/prompt-templates/"
_PROMPT_TEMPLATE_RESET = "/api/v1/prompt-templates/reset/"
_PROMPT_TEMPLATE_SLOT = "/api/v1/prompt-templates/slots/need_to_sysreq/"
_LLM_SETTINGS = "/api/v1/llm-settings/"

#: The settings views named by #865 plus the REST siblings of the
#: ``prompt_variable`` / ``link_type`` / ``attribute_*`` MCP namespaces.
_GOVERNANCE_VIEWS = (
    LlmSettingsView,
    PromptTemplateView,
    PromptTemplateResetView,
    PromptTemplateSlotDetailView,
    ReviewPolicyView,
    ContextGraphSettingsView,
    ContextGraphRebuildView,
    PromptVariableDetailView,
    LinkTypeDefaultsListView,
    LinkTypeDefaultsDetailView,
    WorkspaceLinkTypeDetailView,
    WorkspaceLinkTypeResetView,
    AttributeDefaultsDetailView,
    WorkspaceAttributeDefinitionView,
    WorkspaceAttributeDefinitionResetView,
    AttributeDefaultsImportView,
    WorkspaceAttributeDefinitionImportView,
    AttributeCatalogListView,
    AttributeCatalogDetailView,
    AttributeCatalogDeprecateView,
    AttributeCatalogAddToDefinitionView,
    AttributeCatalogImportView,
    AttributeMigrationApplyView,
    AttributeMigrationRollbackView,
)

#: One minimal-but-valid ``definition`` for the link-type catalog.
_LINK_TYPE_DEFINITION = {
    **builtin_definition("mitigates"),
    "built_in": False,
}


@pytest.fixture
def gov_context(db):
    """A tenant whose single user holds the Admin role (so RBAC never denies)."""
    tenant = Tenant.objects.create(
        name="GOV-T", slug=f"gov-t-{uuid.uuid4().hex[:8]}", is_active=True
    )
    set_request_tenant(tenant.id)
    try:
        user = User.objects.create(
            username=f"gov-{uuid.uuid4().hex[:8]}", email="gov@t.test", tenant=tenant
        )
        workspace = Workspace.objects.create(
            tenant=tenant, name="GOV-WS", preset={"name": "extended"}
        )
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=workspace, role=ROLE_ADMIN
        )
    finally:
        clear_request_tenant()
    return tenant, user, workspace


def _api_key_client(tenant: Tenant, user: User, scope: str) -> APIClient:
    """An APIClient authenticated with a real API key of the given scope."""
    result = AuthenticationService().create_api_key(
        user_id=user.id,
        tenant_id=tenant.id,
        name=f"gov-key-{scope}-{uuid.uuid4().hex[:6]}",
        scope=scope,
    )
    client = APIClient()
    client.credentials(HTTP_X_API_KEY=result.plaintext)
    return client


def _write_surfaces(workspace_id: object) -> dict[str, tuple[str, str, dict]]:
    """Return ``label -> (http method, url, body)`` for every governance write.

    The bodies are minimal-but-valid so a denial can only come from the
    capability gate, never from validation. ``ContextGraphRebuildView`` is not
    listed: it answers 404 until a settings row exists and is therefore pinned
    at declaration level below instead.
    """
    return {
        "prompt template": ("patch", _PROMPT_TEMPLATES, {"need_to_sysreq": "x {n}"}),
        "prompt template reset": ("post", _PROMPT_TEMPLATE_RESET, {}),
        "prompt template slot": ("put", _PROMPT_TEMPLATE_SLOT, {"content": "slot {n}"}),
        "llm settings": ("put", _LLM_SETTINGS, {"provider": "mock"}),
        "review policy": (
            "put",
            f"/api/v1/workspaces/{workspace_id}/review-policy/",
            # "review_all" — the extended preset tier requires a human gate.
            {"mode": "review_all", "min_confidence": 0.5},
        ),
        "context graph settings": (
            "put",
            f"/api/v1/workspaces/{workspace_id}/context-graph-settings/",
            {"enabled": False},
        ),
        "prompt variable": (
            "put",
            "/api/v1/prompt-variables/review_depth_hint/",
            {"value": "tenant", "var_type": "str"},
        ),
        "link type default": (
            "post",
            "/api/v1/link-type-defaults/",
            {"key": "conflicts-with", "definition": _LINK_TYPE_DEFINITION},
        ),
        "link type workspace": (
            "put",
            f"/api/v1/workspaces/{workspace_id}/link-type-definitions/mitigates/",
            {"definition": _LINK_TYPE_DEFINITION},
        ),
        "link type reset": (
            "post",
            f"/api/v1/workspaces/{workspace_id}"
            "/link-type-definitions/mitigates/reset/",
            {},
        ),
        "attribute definition": (
            "put",
            "/api/v1/attribute-defaults/Risk/standard/",
            {"attributes": []},
        ),
        "attribute defaults import": (
            "post",
            "/api/v1/attribute-defaults/Risk/standard/import/",
            {"attributes": []},
        ),
        "attribute catalog": (
            "post",
            "/api/v1/attribute-catalog/",
            {
                "name": "severity_rating",
                "definition": {
                    "name": "severity_rating",
                    "kind": "extended",
                    "type": "enum",
                    "options": [
                        {"value": "low", "label_de": "Niedrig", "label_en": "Low"}
                    ],
                },
                "category": "risk",
                "tags": ["risk"],
                "label": {"de": "Auswirkung", "en": "Impact"},
            },
        ),
        "attribute catalog import": (
            "post",
            "/api/v1/attribute-catalog/import/",
            {"schema_version": 1, "entries": []},
        ),
        "attribute migration apply": ("post", "/api/v1/attribute-migration/apply/", {}),
        "attribute migration rollback": (
            "post",
            f"/api/v1/attribute-migration/runs/{uuid.uuid4()}/rollback/",
            {},
        ),
    }


#: Surfaces whose happy path an ADMIN key actually completes, with the expected
#: status. The remaining ones are denial-only here because their success path
#: needs seeded rows or executes a migration — their own suites cover it, and
#: the capability declaration is pinned for all of them below.
_ADMIN_ALLOWED = {
    "prompt template": 200,
    "prompt template reset": 200,
    "prompt template slot": 200,
    "llm settings": 200,
    "review policy": 200,
    "context graph settings": 200,
    "prompt variable": 200,
    "link type default": 201,
    "attribute catalog": 201,
}

#: Every surface above, derived from the same helper the test uses so the two
#: cannot drift (the placeholder id only builds the parametrisation ids).
_SURFACES = sorted(_write_surfaces("placeholder"))


# ---------------------------------------------------------------------------
# Declaration (no DB) — the tier each view demands per HTTP method
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("view_cls", _GOVERNANCE_VIEWS)
@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_governance_views_require_admin_scope_for_mutations(view_cls, method) -> None:
    """Every governance view demands the ADMIN tier on every mutating method.

    ``Operation.WORKSPACE_CONFIG`` is the governance operation the shared gate
    classifies as ADMIN (``authorization.GOVERNANCE_OPERATIONS``); *which* of
    the three admin-reserved operations is named does not matter, only that the
    tier is ADMIN — the same one the MCP namespaces resolve to.
    """
    view = view_cls()
    view.request = SimpleNamespace(method=method)
    assert view.required_scope_operation is Operation.WORKSPACE_CONFIG


@pytest.mark.parametrize(
    "view_cls",
    [LlmSettingsView, PromptTemplateView, ContextGraphSettingsView],
)
def test_governance_views_add_no_scope_gate_to_reads(view_cls) -> None:
    """A GET keeps only the view's own Admin-role gate (no behaviour change)."""
    view = view_cls()
    view.request = SimpleNamespace(method="GET")
    assert view.required_scope_operation is None


def test_governance_view_without_request_adds_no_gate() -> None:
    """The ``getattr(self, 'request', None)`` guard: no request -> no narrowing."""
    assert LlmSettingsView().required_scope_operation is None


def test_mixin_is_the_only_declaration_mechanism() -> None:
    """Every governance view inherits the one shared mixin (no local copies)."""
    for view_cls in _GOVERNANCE_VIEWS:
        assert issubclass(view_cls, AdminScopeRequiredMixin), view_cls


# ---------------------------------------------------------------------------
# End-to-end: real API keys of every tier against the real routes
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("scope", ["admin", "write"])
@pytest.mark.parametrize("surface", sorted(_ADMIN_ALLOWED))
def test_admin_tier_key_is_allowed_on_governance_writes(
    gov_context, scope, surface
) -> None:
    """ADMIN — and the legacy ``write`` alias of the same tier — is allowed.

    The RBAC side is already proven by the owner holding the Admin role; this
    asserts the capability gate did not over-narrow.
    """
    tenant, user, workspace = gov_context
    client = _api_key_client(tenant, user, scope)
    method, url, body = _write_surfaces(workspace.id)[surface]

    resp = getattr(client, method)(url, body, format="json")

    assert resp.status_code == _ADMIN_ALLOWED[surface], resp.content


@pytest.mark.django_db
@pytest.mark.parametrize("scope", ["author", "read_only", "read"])
@pytest.mark.parametrize("surface", _SURFACES)
def test_non_admin_tier_keys_are_denied_on_governance_writes(
    gov_context, scope, surface
) -> None:
    """AUTHOR and READ_ONLY keys are denied every governance write.

    ``read`` is the legacy alias of ``read_only`` and must keep that meaning.
    """
    tenant, user, workspace = gov_context
    client = _api_key_client(tenant, user, scope)
    method, url, body = _write_surfaces(workspace.id)[surface]

    resp = getattr(client, method)(url, body, format="json")

    assert resp.status_code == 403, resp.content
    if scope == "author":
        # The governance-specific denial names the tier the key must have.
        assert "admin" in str(resp.content).lower()
    else:
        # read/read_only: already denied by the pre-existing WRITE gate.
        assert "read-only" in str(resp.content).lower()


@pytest.mark.django_db
def test_denied_author_prompt_template_write_changed_nothing(gov_context) -> None:
    """The canonical injection vector (REQ-043) is not merely 403-ed but untouched."""
    tenant, user, _workspace = gov_context
    client = _api_key_client(tenant, user, "author")

    resp = client.patch(
        _PROMPT_TEMPLATES, {"need_to_sysreq": "injected {n}"}, format="json"
    )
    assert resp.status_code == 403

    set_request_tenant(tenant.id)
    try:
        assert not PromptTemplate.objects.filter(
            workspace_id__isnull=True, content="injected {n}"
        ).exists()
    finally:
        clear_request_tenant()


@pytest.mark.django_db
def test_denied_author_prompt_variable_write_changed_nothing(gov_context) -> None:
    """The variable content lands in every later prompt — same vector, same check."""
    tenant, user, _workspace = gov_context
    client = _api_key_client(tenant, user, "author")

    resp = client.put(
        "/api/v1/prompt-variables/review_depth_hint/",
        {"value": "injected", "var_type": "str"},
        format="json",
    )
    assert resp.status_code == 403

    set_request_tenant(tenant.id)
    try:
        assert not PromptVariable.objects.filter(
            default_value__contains="injected"
        ).exists()
    finally:
        clear_request_tenant()


@pytest.mark.django_db
def test_author_key_still_writes_ordinary_artifacts(gov_context) -> None:
    """The ADMIN tier narrows governance only — content authoring is untouched."""
    tenant, user, workspace = gov_context
    client = _api_key_client(tenant, user, "author")

    resp = client.post(
        f"/api/v1/workspaces/{workspace.id}/needs/",
        {"title": "authored by an AUTHOR key"},
        format="json",
    )

    assert resp.status_code == 201, resp.content


@pytest.mark.django_db
@pytest.mark.parametrize("scope", ["read_only", "author", "admin", "read"])
def test_every_tier_still_reads_governance_settings(gov_context, scope) -> None:
    """Reads stay open: the new declaration narrows mutations only."""
    tenant, user, workspace = gov_context
    client = _api_key_client(tenant, user, scope)

    assert client.get(_PROMPT_TEMPLATES).status_code == 200
    assert client.get(_LLM_SETTINGS).status_code == 200
    assert client.get("/api/v1/prompt-variables/").status_code == 200
    review_policy = client.get(f"/api/v1/workspaces/{workspace.id}/review-policy/")
    assert review_policy.status_code == 200, review_policy.content
