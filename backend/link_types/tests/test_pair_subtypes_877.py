"""#877 / Plan B B3-T2 — subtype-capable link pairs (``Typ:Subtag``).

The mechanism is **generic**: ``link_types.catalog.SUBTYPE_FIELDS`` names the
artifact types that may carry a tag and the entity field holding the value
(``ArchitectureElement`` is the only registration today). ``Typ:Subtag`` is the
*only* representation, on the pair side and on the endpoint side.

Expand guarantee: a pair **without** a tag still matches the normalised base
type, so existing catalogs and links are untouched.
"""
from __future__ import annotations

import uuid

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_ADMIN, UserRole
from link_types.catalog import SUBTYPE_FIELDS, invalidate_workspace, validate_link_pair
from link_types.schema import validate_definition_json
from link_types.workspace_store import (
    WorkspaceLinkTypeDefinitionStore,
    provision_workspace_link_types,
)
from persistence.errors import ValidationError
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Artifact, Tenant, User, Workspace
from persistence.tenancy import TenantContext

_KEY = "satisfies"
_SUBTYPE_PAIR = {"source_type": "Requirement", "target_type": "ArchitectureElement:function"}
_BASE_PAIR = {"source_type": "Requirement", "target_type": "ArchitectureElement"}
_PASSWORD = "hunter2pass"


def _definition(pairs: list[dict[str, str]]) -> dict:
    return {
        "label": {
            "de": {"downstream": "a", "upstream": "b", "neutral": "c"},
            "en": {"downstream": "a", "upstream": "b", "neutral": "c"},
        },
        "allowed_pairs": pairs,
        "coverage_relevant": False,
        "suspect_rule": "none",
        "impact_weight": 0.5,
        "manual_creatable": True,
        "system_owned": False,
        "active": True,
        "built_in": False,
    }


@pytest.fixture
def workspace(db) -> Workspace:
    """A real workspace with the provisioned built-in catalog."""
    tenant = Tenant.objects.create(
        name="pair-subtypes-877", slug=f"pair-sub-{uuid.uuid4().hex[:8]}"
    )
    TenantContext.set_tenant(tenant.id)
    row = Workspace.objects.create(tenant=tenant, name="pair-subtype-ws")
    provision_workspace_link_types(workspace_id=row.id, tenant_id=tenant.id)
    yield row
    invalidate_workspace(str(row.id))
    TenantContext.clear_tenant()


def _set_pairs(workspace: Workspace, pairs: list[dict[str, str]]) -> None:
    WorkspaceLinkTypeDefinitionStore().update(
        workspace.tenant_id, workspace.id, _KEY, _definition(pairs)
    )
    invalidate_workspace(str(workspace.id))


@pytest.fixture
def trace_env(workspace: Workspace):
    """Editor context plus one Requirement and two architecture artifacts."""
    from auth_tenancy.context import AuthContext, AuthMethod
    from persistence.models import ArchitectureElement

    ctx = AuthContext(
        user_id=None,
        tenant_id=workspace.tenant_id,
        active_roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN,
        workspace_id=workspace.id,
    )
    requirement = Artifact.objects.create(
        tenant_id=workspace.tenant_id, workspace=workspace, artifact_type="Requirement"
    )

    def element(element_type: str) -> Artifact:
        artifact = Artifact.objects.create(
            tenant_id=workspace.tenant_id,
            workspace=workspace,
            artifact_type="ArchitectureElement",
        )
        ArchitectureElement.objects.create(
            tenant_id=workspace.tenant_id,
            workspace=workspace,
            artifact=artifact,
            title=f"{element_type} element",
            element_type=element_type,
        )
        return artifact

    return {
        "workspace": workspace,
        "ctx": ctx,
        "requirement": requirement,
        "function": element("function"),
        "component": element("component"),
    }


def test_schema_keeps_a_subtype_tag_on_save() -> None:
    result = validate_definition_json(_definition([_SUBTYPE_PAIR]), key="conflicts-with")
    assert result["allowed_pairs"] == [_SUBTYPE_PAIR]


def test_schema_normalizes_the_tag_to_lowercase() -> None:
    payload = _definition(
        [{"source_type": "Requirement", "target_type": "ArchitectureElement:Function"}]
    )
    result = validate_definition_json(payload, key="conflicts-with")
    assert result["allowed_pairs"] == [_SUBTYPE_PAIR]


def test_subtype_pair_rejected_for_type_without_registered_subtype_field() -> None:
    """``Requirement:foo`` — Requirement has no registered subtype field.

    Only the stable message prefix is asserted: the register list appended to it
    grows with :data:`SUBTYPE_FIELDS` (Plan F adds ``Document``), so pinning the
    rendering would turn every registration into a test failure.
    """
    payload = _definition([{"source_type": "Requirement:foo", "target_type": "Risk"}])
    with pytest.raises(ValidationError, match="subtype tag is only supported for"):
        validate_definition_json(payload, key="conflicts-with")


def test_an_overlong_pair_side_is_rejected() -> None:
    """The catalog side is bounded: an 80-character limit matches the model.

    ``Artifact.artifact_type`` is capped at 64 characters, so a longer pair side
    can never name an artifact type — it is rejected at the write path instead
    of being stored as a pair that silently never matches.
    """
    payload = _definition([{"source_type": "Requirement", "target_type": "A" * 81}])
    with pytest.raises(ValidationError, match="longer than 80 characters"):
        validate_definition_json(payload, key="conflicts-with")


@pytest.mark.parametrize(
    "bad",
    [
        "ArchitectureElement:",
        "ArchitectureElement:fun:extra",
        "ArchitectureElement: function",
        "ArchitectureElement :function",
    ],
)
def test_malformed_subtype_tags_are_rejected(bad: str) -> None:
    payload = _definition([{"source_type": "Requirement", "target_type": bad}])
    with pytest.raises(ValidationError):
        validate_definition_json(payload, key="conflicts-with")


def test_subtype_register_lists_architecture_element() -> None:
    assert SUBTYPE_FIELDS["ArchitectureElement"] == "element_type"


@pytest.mark.django_db
def test_validate_link_pair_matches_on_the_exact_subtype(workspace: Workspace) -> None:
    _set_pairs(workspace, [_SUBTYPE_PAIR])
    validate_link_pair(
        workspace.id, _KEY, "Requirement", "ArchitectureElement:function", manual=True
    )
    with pytest.raises(ValidationError) as exc:
        validate_link_pair(
            workspace.id,
            _KEY,
            "Requirement",
            "ArchitectureElement:component",
            manual=True,
        )
    # The error lists the allowed pairs in the same ``Typ:Subtag`` notation.
    assert "Requirement->ArchitectureElement:function" in str(exc.value)


@pytest.mark.django_db
def test_a_pair_without_a_subtype_still_matches_any_subtype(
    workspace: Workspace,
) -> None:
    """Expand guarantee: the untagged pair behaves exactly as before."""
    _set_pairs(workspace, [_BASE_PAIR])
    validate_link_pair(
        workspace.id, _KEY, "Requirement", "ArchitectureElement:function", manual=True
    )
    validate_link_pair(
        workspace.id, _KEY, "Requirement", "ArchitectureElement", manual=True
    )


#: The subtype lookup is a single-column ``values_list`` query, never a join.
_LOOKUP_PREFIX = 'SELECT "pl_architecture_element"."element_type"'


def _create_link(env, target):
    from application.trace_link_service import TraceLinkService

    return TraceLinkService().create_trace_link(
        env["requirement"].id, target.id, _KEY, env["ctx"]
    )


@pytest.mark.django_db
def test_service_derives_the_tag_from_the_entity_field(trace_env) -> None:
    _set_pairs(trace_env["workspace"], [_SUBTYPE_PAIR])
    with CaptureQueriesContext(connection) as captured:
        link = _create_link(trace_env, trace_env["function"])
    assert link.link_type == _KEY
    lookups = [
        q["sql"]
        for q in captured.captured_queries
        if q["sql"].startswith(_LOOKUP_PREFIX)
    ]
    # One single-column query for the registered endpoint only (the Requirement
    # source has no registered sub-type field) — never a full entity row.
    assert len(lookups) == 1

    with pytest.raises(ValidationError, match="ArchitectureElement:function"):
        _create_link(trace_env, trace_env["component"])


@pytest.mark.django_db
def test_no_subtype_lookup_without_a_subtagged_pair(trace_env) -> None:
    """Short circuit: without a tagged pair the entity field is never read."""
    _set_pairs(trace_env["workspace"], [_BASE_PAIR])
    with CaptureQueriesContext(connection) as captured:
        _create_link(trace_env, trace_env["function"])
    assert not any(
        query["sql"].startswith(_LOOKUP_PREFIX) for query in captured.captured_queries
    )


def _admin_client(workspace: Workspace) -> APIClient:
    """A logged-in workspace admin — the role the link-type editor requires."""
    suffix = uuid.uuid4().hex[:8]
    user = User.objects.create(
        username=f"pair-{suffix}", email=f"pair-{suffix}@t.test", tenant_id=workspace.tenant_id
    )
    user.set_password(_PASSWORD)
    user.save(update_fields=["password"])
    set_request_tenant(workspace.tenant_id)
    try:
        UserRole.objects.create(
            tenant_id=workspace.tenant_id,
            user=user,
            workspace=workspace,
            role=ROLE_ADMIN,
        )
    finally:
        clear_request_tenant()

    client = APIClient()
    login = client.post(
        "/api/v1/auth/login/",
        {"username": user.username, "password": _PASSWORD},
        format="json",
    )
    assert login.status_code == 200, login.content
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.json()['token']}")
    return client


@pytest.mark.django_db
def test_rest_rejects_a_subtype_tag_for_an_unregistered_type(workspace) -> None:
    """The refusal reaches the admin editor as a 400, not only the schema."""
    client = _admin_client(workspace)

    response = client.put(
        f"/api/v1/workspaces/{workspace.id}/link-type-definitions/{_KEY}/",
        data={
            "definition": _definition(
                [{"source_type": "Requirement:foo", "target_type": "Risk"}]
            )
        },
        content_type="application/json",
    )
    assert response.status_code == 400, response.content
    assert "subtype tag is only supported for" in response.json()["detail"]


@pytest.mark.django_db
def test_rest_accepts_a_tagged_pair_round_trip(workspace) -> None:
    """The tagged notation survives the REST write path unchanged."""
    client = _admin_client(workspace)

    response = client.put(
        f"/api/v1/workspaces/{workspace.id}/link-type-definitions/{_KEY}/",
        data={"definition": _definition([_SUBTYPE_PAIR])},
        content_type="application/json",
    )
    assert response.status_code == 200, response.content
    assert response.json()["definition"]["allowed_pairs"] == [_SUBTYPE_PAIR]
