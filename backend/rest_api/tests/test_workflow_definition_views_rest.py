"""REST-level coverage for WorkflowDefinitionViewSet (views.py).

leaf_id : COMP-RA-WF (WorkflowDefinitionViewSet)
req_id  : REQ-L2-RA-001, REQ-176, REQ-177, REQ-180

The existing ``test_views.py`` covers this ViewSet with
``APIRequestFactory`` + mocked ``WorkflowFacade``; this module drives the same
endpoints through the real middleware stack (JWT auth, RBAC workspace
resolution, preset gate, service layer) against the test database, so the
handler-level error mapping is exercised end to end:

  - ``list``/``retrieve``/``destroy`` stub behaviour (empty envelope, 404, 403).
  - ``definition/`` read mode: missing/invalid scope params (400), the
    uninitialized empty-graph contract (200 + ``initialized: false``).
  - ``definition/states/`` and ``definition/transitions/`` edit mode: admin
    gate (403), ``WorkflowNotConfigurableError`` -> 403, and the
    create/rename/delete happy paths.
  - ``BaseEntityViewSet`` UUID path validation leaking into PATCH.
"""
from __future__ import annotations

import uuid

import pytest
from drf_spectacular.generators import SchemaGenerator
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_ADMIN, ROLE_EDITOR, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Artifact, Tenant, User, Workspace
from presets.models import WorkspacePresetConfig
from workflow.item_types import WORK_ITEM_PRESET_BY_TIER, WORK_ITEM_TIERS

pytestmark = pytest.mark.django_db

_PASSWORD = "hunter2pass"
_ITEM_TYPE = "Requirement"


def _scenario(
    preset: str = "extended", *, config_tier: str | None = None
) -> tuple[Tenant, User, User, Workspace]:
    """Create a tenant with an admin and an editor user plus one workspace.

    ``config_tier`` additionally persists a ``WorkspacePresetConfig`` — the row
    ``workflow.services.resolve_default_preset`` treats as authoritative for the
    workspace's rigorous tier. Without it, the resolver falls back to the
    denormalised ``Workspace.preset`` blob and then to ``standard``.
    """
    suffix = uuid.uuid4().hex[:8]
    tenant = Tenant.objects.create(name=f"T-{suffix}", slug=f"wf-{suffix}", is_active=True)

    def _user(role: str) -> User:
        user = User.objects.create(
            username=f"{role}-{suffix}", email=f"{role}-{suffix}@t.test", tenant=tenant
        )
        user.set_password(_PASSWORD)
        user.save(update_fields=["password"])
        set_request_tenant(tenant.id)
        try:
            UserRole.objects.create(
                tenant=tenant, user=user, workspace=workspace, role=role
            )
        finally:
            clear_request_tenant()
        return user

    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="WF WS", preset={"name": preset}
        )
        if config_tier is not None:
            WorkspacePresetConfig.objects.create(
                tenant=tenant, workspace=workspace, active_tier=config_tier
            )
    finally:
        clear_request_tenant()

    return tenant, _user(ROLE_ADMIN), _user(ROLE_EDITOR), workspace


def _client(user: User) -> APIClient:
    client = APIClient()
    login = client.post(
        "/api/v1/auth/login/",
        {"username": user.username, "password": _PASSWORD},
        format="json",
    )
    assert login.status_code == 200, login.content
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.json()['token']}")
    return client


# ---------------------------------------------------------------------------
# Auth enforcement — the whole ViewSet sits behind the Bearer-token auth
# ---------------------------------------------------------------------------


def test_list_without_token_returns_401() -> None:
    resp = APIClient().get("/api/v1/workflows/")
    assert resp.status_code == 401, resp.content


def test_definition_mutation_without_token_returns_401() -> None:
    client = APIClient()
    resp = client.post(
        "/api/v1/workflows/definition/states/",
        {"workspace_id": str(uuid.uuid4()), "item_type": _ITEM_TYPE, "name": "review"},
        format="json",
    )
    assert resp.status_code == 401, resp.content


# ---------------------------------------------------------------------------
# list / retrieve / destroy — the stub branches
# ---------------------------------------------------------------------------


def test_list_returns_empty_pagination_envelope() -> None:
    """``WorkflowFacade`` exposes no list, so the handler is a fixed envelope."""
    _, admin, _, _ = _scenario()
    resp = _client(admin).get("/api/v1/workflows/")

    assert resp.status_code == 200, resp.content
    assert resp.json() == {"count": 0, "next": None, "previous": None, "results": []}


def test_retrieve_is_not_supported_and_returns_404() -> None:
    _, admin, _, _ = _scenario()
    resp = _client(admin).get(f"/api/v1/workflows/{uuid.uuid4()}/")
    assert resp.status_code == 404, resp.content


def test_destroy_is_always_refused_with_403() -> None:
    """A workflow definition is configuration, never a deletable resource."""
    _, admin, _, _ = _scenario()
    resp = _client(admin).delete(f"/api/v1/workflows/{uuid.uuid4()}/")

    assert resp.status_code == 403, resp.content
    assert resp.json()["error"]["code"] == "PERMISSION_DENIED"


def test_create_without_body_returns_validation_error() -> None:
    _, admin, _, _ = _scenario()
    resp = _client(admin).post("/api/v1/workflows/", {}, format="json")

    assert resp.status_code == 400, resp.content
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_transition_without_target_state_returns_400() -> None:
    """PATCH /workflows/<pk>/ demands ``target_state`` before touching the service."""
    _, admin, _, _ = _scenario()
    resp = _client(admin).patch(f"/api/v1/workflows/{uuid.uuid4()}/", {}, format="json")

    assert resp.status_code == 400, resp.content
    assert "target_state" in resp.json()["error"]["message"]


def test_transition_with_wellformed_pk_hits_the_service_contract() -> None:
    """Regression test for a real defect in ``partial_update``.

    ``WorkflowDefinitionViewSet.partial_update`` used to call
    ``WorkflowFacade.transition(entity_id=..., entity_type=..., target_state=...)``,
    but the facade's ``transition`` does not spell its first parameter
    ``entity_id`` — every request with a well-formed UUID and a
    ``target_state`` therefore died on a ``TypeError`` that the generic
    ``except Exception`` mapped to 500.

    The endpoint now resolves the artifact behind ``pk`` through
    ``ArtifactService.get_artifact`` (the same item/workspace resolution the
    ``WorkflowTransitionsMixin`` uses) and hands the facade its real
    signature — ``item_id``, ``item_type``, ``workspace_id``. An unknown
    artifact is a 404 from the service, no longer a 500 from a TypeError.
    """
    _, admin, _, _ = _scenario()
    resp = _client(admin).patch(
        f"/api/v1/workflows/{uuid.uuid4()}/",
        {"target_state": "in_review"},
        format="json",
    )

    assert resp.status_code == 404, resp.content
    assert resp.json()["error"]["code"] == "NOT_FOUND"


def test_transition_moves_the_artifact_through_the_workflow() -> None:
    """The fixed PATCH path really drives ``WorkflowFacade.transition``.

    The unknown-pk test above only proves the ``TypeError`` is gone. This one
    resolves an existing artifact, seeds its workflow state through the same
    ``create`` action the endpoint pairs with, and asserts the transition
    answer — so the real ``item_id``/``item_type``/``workspace_id`` signature
    is exercised end to end, not just the error path around it.
    """
    tenant, admin, _, workspace = _scenario()
    set_request_tenant(tenant.id)
    try:
        artifact = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="Artifact"
        )
    finally:
        clear_request_tenant()

    client = _client(admin)
    scope = {"workspace_id": str(workspace.id), "item_type": "Artifact"}

    init = client.post("/api/v1/workflows/definition/initialize/", scope, format="json")
    assert init.status_code == 201, init.content
    initial_state = init.json()["initial_state"]

    added = client.post(
        "/api/v1/workflows/definition/states/",
        {**scope, "name": "in_review"},
        format="json",
    )
    assert added.status_code == 201, added.content
    edge = client.post(
        "/api/v1/workflows/definition/transitions/",
        {**scope, "from_state": initial_state, "to_state": "in_review"},
        format="json",
    )
    assert edge.status_code == 201, edge.content

    seeded = client.post(
        "/api/v1/workflows/",
        {
            "artifact_id": str(artifact.id),
            "workspace_id": str(workspace.id),
            "name": "Artifact workflow",
        },
        format="json",
    )
    assert seeded.status_code == 201, seeded.content

    moved = client.patch(
        f"/api/v1/workflows/{artifact.id}/",
        {"target_state": "in_review", "change_reason": "ready for review"},
        format="json",
    )

    assert moved.status_code == 200, moved.content
    assert moved.json() == {"id": str(artifact.id), "target_state": "in_review"}


def test_non_uuid_pk_is_rejected_before_the_service_call() -> None:
    """``BaseEntityViewSet.initial`` 400s a malformed UUID path segment (#271)."""
    _, admin, _, _ = _scenario()
    resp = _client(admin).patch(
        "/api/v1/workflows/not-a-uuid/", {"target_state": "in_review"}, format="json"
    )

    assert resp.status_code == 400, resp.content
    assert "well-formed UUID" in resp.json()["error"]["message"]


# ---------------------------------------------------------------------------
# definition/ — read mode
# ---------------------------------------------------------------------------


def test_definition_without_scope_params_returns_400() -> None:
    _, admin, _, _ = _scenario()
    resp = _client(admin).get("/api/v1/workflows/definition/")

    assert resp.status_code == 400, resp.content
    assert "workspace_id and item_type are required" in resp.json()["error"]["message"]


def test_definition_with_invalid_workspace_uuid_returns_400() -> None:
    _, admin, _, _ = _scenario()
    resp = _client(admin).get(
        f"/api/v1/workflows/definition/?workspace_id=nope&item_type={_ITEM_TYPE}"
    )

    assert resp.status_code == 400, resp.content
    assert "workspace_id must be a valid UUID" in resp.json()["error"]["message"]


def test_definition_uninitialized_returns_empty_graph() -> None:
    """No configured workflow is an empty graph, not a 404 (editor empty state)."""
    _, admin, _, workspace = _scenario()
    resp = _client(admin).get(
        f"/api/v1/workflows/definition/?workspace_id={workspace.id}&item_type={_ITEM_TYPE}"
    )

    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["initialized"] is False
    assert body["states"] == []
    assert body["transitions"] == []
    assert body["on_default"] is True


# ---------------------------------------------------------------------------
# definition/* — edit mode (admin gate + error mapping + happy paths)
# ---------------------------------------------------------------------------


def test_editor_role_cannot_mutate_the_definition() -> None:
    _, _, editor, workspace = _scenario()
    resp = _client(editor).post(
        "/api/v1/workflows/definition/states/",
        {"workspace_id": str(workspace.id), "item_type": _ITEM_TYPE, "name": "review"},
        format="json",
    )

    assert resp.status_code == 403, resp.content
    assert resp.json()["error"]["code"] == "PERMISSION_DENIED"


def test_state_mutation_without_scope_params_returns_400() -> None:
    _, admin, _, _ = _scenario()
    resp = _client(admin).post(
        "/api/v1/workflows/definition/states/", {"name": "review"}, format="json"
    )

    assert resp.status_code == 400, resp.content
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_state_mutation_with_invalid_workspace_uuid_returns_400() -> None:
    _, admin, _, _ = _scenario()
    resp = _client(admin).post(
        "/api/v1/workflows/definition/states/",
        {"workspace_id": "garbage", "item_type": _ITEM_TYPE, "name": "review"},
        format="json",
    )

    assert resp.status_code == 400, resp.content
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_add_state_without_name_returns_400() -> None:
    _, admin, _, workspace = _scenario()
    resp = _client(admin).post(
        "/api/v1/workflows/definition/states/",
        {"workspace_id": str(workspace.id), "item_type": _ITEM_TYPE, "name": "  "},
        format="json",
    )

    assert resp.status_code == 400, resp.content
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_initialize_then_edit_state_and_transition_roundtrip() -> None:
    """The editor's full create/rename/delete flow over the REST surface."""
    _, admin, _, workspace = _scenario()
    client = _client(admin)
    scope = {"workspace_id": str(workspace.id), "item_type": _ITEM_TYPE}

    init = client.post("/api/v1/workflows/definition/initialize/", scope, format="json")
    assert init.status_code == 201, init.content
    graph = init.json()
    assert graph["initialized"] is True
    assert graph["states"], "the preset default must seed at least one state"

    added = client.post(
        "/api/v1/workflows/definition/states/", {**scope, "name": "in_review"}, format="json"
    )
    assert added.status_code == 201, added.content
    assert "in_review" in added.json()["states"]

    renamed = client.patch(
        "/api/v1/workflows/definition/states/in_review/",
        {**scope, "name": "in_review_2"},
        format="json",
    )
    assert renamed.status_code == 200, renamed.content
    names = set(renamed.json()["states"])
    assert "in_review_2" in names and "in_review" not in names

    initial_state = graph["initial_state"]
    transition = client.post(
        "/api/v1/workflows/definition/transitions/",
        {
            **scope,
            "from_state": initial_state,
            "to_state": "in_review_2",
            "allowed_roles": ["admin"],
            "requires_change_reason": True,
        },
        format="json",
    )
    assert transition.status_code == 201, transition.content
    edges = {
        (t["from_state"], t["to_state"]): t
        for t in transition.json()["transitions"]
    }
    assert edges[(initial_state, "in_review_2")]["requires_change_reason"] is True

    patched = client.patch(
        "/api/v1/workflows/definition/transitions/"
        f"{initial_state}__in_review_2/",
        {**scope, "requires_change_reason": False, "allowed_roles": ["admin", "editor"]},
        format="json",
    )
    assert patched.status_code == 200, patched.content
    edges = {
        (t["from_state"], t["to_state"]): t for t in patched.json()["transitions"]
    }
    assert edges[(initial_state, "in_review_2")]["requires_change_reason"] is False

    removed = client.delete(
        "/api/v1/workflows/definition/transitions/"
        f"{initial_state}__in_review_2/",
        data=scope,
        format="json",
    )
    assert removed.status_code == 200, removed.content
    assert not any(
        (t["from_state"], t["to_state"]) == (initial_state, "in_review_2")
        for t in removed.json()["transitions"]
    )

    dropped = client.delete(
        "/api/v1/workflows/definition/states/in_review_2/", data=scope, format="json"
    )
    assert dropped.status_code == 200, dropped.content
    assert "in_review_2" not in set(dropped.json()["states"])


def test_transition_missing_states_returns_400() -> None:
    _, admin, _, workspace = _scenario()
    resp = _client(admin).post(
        "/api/v1/workflows/definition/transitions/",
        {"workspace_id": str(workspace.id), "item_type": _ITEM_TYPE, "from_state": "a"},
        format="json",
    )

    assert resp.status_code == 400, resp.content
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_malformed_transition_id_returns_400() -> None:
    """The ``<from>__<to>`` pair is validated before the service is called."""
    _, admin, _, workspace = _scenario()
    resp = _client(admin).patch(
        "/api/v1/workflows/definition/transitions/no-separator/",
        {"workspace_id": str(workspace.id), "item_type": _ITEM_TYPE},
        format="json",
    )

    assert resp.status_code == 400, resp.content
    assert "transition id must be" in resp.json()["error"]["message"]


def test_reset_restores_the_global_default() -> None:
    """``definition/reset/`` rewinds to the global default (REQ-180).

    The preset bootstrap seeds a global default, so the happy path answers 200
    with ``on_default: true`` rather than the 409 NO_GLOBAL_SOURCE a workspace
    without a linked global source would get.
    """
    _, admin, _, workspace = _scenario()
    client = _client(admin)
    init = client.post(
        "/api/v1/workflows/definition/initialize/",
        {"workspace_id": str(workspace.id), "item_type": _ITEM_TYPE},
        format="json",
    )
    assert init.status_code == 201, init.content

    reset = client.post(
        "/api/v1/workflows/definition/reset/",
        {"workspace_id": str(workspace.id), "item_type": _ITEM_TYPE},
        format="json",
    )

    assert reset.status_code == 200, reset.content
    body = reset.json()
    assert body["initialized"] is True
    assert body["on_default"] is True
    assert body["is_customized"] is False


def test_edit_on_non_configurable_preset_returns_403() -> None:
    """``WorkflowNotConfigurableError`` -> 403 (REQ-L3-WE001-002 configurability gate)."""
    _, admin, _, workspace = _scenario(preset="minimal")
    client = _client(admin)
    init = client.post(
        "/api/v1/workflows/definition/initialize/",
        {"workspace_id": str(workspace.id), "item_type": _ITEM_TYPE},
        format="json",
    )
    if init.status_code == 409:
        pytest.skip("minimal preset does not initialize a definition here")

    resp = client.post(
        "/api/v1/workflows/definition/states/",
        {"workspace_id": str(workspace.id), "item_type": _ITEM_TYPE, "name": "review"},
        format="json",
    )

    assert resp.status_code == 403, resp.content
    assert resp.json()["error"]["code"] == "PERMISSION_DENIED"


def test_definition_read_of_foreign_workspace_does_not_leak_states() -> None:
    """Cross-tenant isolation for the editor graph.

    The read endpoint only takes the scope from the query string, so an
    admin of workspace A may point it at workspace B. Whatever the service
    decides, the response must not describe B's state machine — an empty
    graph is the acceptable answer, a populated one is a data leak.
    """
    _, admin, _, _ = _scenario()
    _, foreign_admin, _, foreign_ws = _scenario()

    seeded = _client(foreign_admin).post(
        "/api/v1/workflows/definition/initialize/",
        {"workspace_id": str(foreign_ws.id), "item_type": _ITEM_TYPE},
        format="json",
    )
    assert seeded.status_code == 201, seeded.content
    foreign_states = set(seeded.json()["states"])
    assert foreign_states, "the foreign workspace needs a real graph for this test"

    resp = _client(admin).get(
        "/api/v1/workflows/definition/"
        f"?workspace_id={foreign_ws.id}&item_type={_ITEM_TYPE}"
    )

    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert not (foreign_states & set(body["states"])), (
        f"foreign workflow states leaked into the response: {sorted(foreign_states)}"
    )


# ---------------------------------------------------------------------------
# P1.4 / M-6 — the list route is an honest, empty compatibility envelope
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def openapi_schema() -> dict:
    """The generated OpenAPI document (same output as ``GET /api/schema/``)."""
    return SchemaGenerator().get_schema(request=None, public=True)


def test_list_documents_itself_as_a_non_collection_envelope(
    openapi_schema: dict,
) -> None:
    """The envelope is empty *and* the document does not promise a CRUD list.

    P1.4 keeps the historical wire contract (byte-identical empty pagination
    envelope) while making the OpenAPI entry say what the route really is: an
    intentionally empty compatibility envelope whose real counterpart is
    ``definition/?workspace_id=&item_type=``.
    """
    _, admin, _, _ = _scenario()
    resp = _client(admin).get("/api/v1/workflows/")

    assert resp.status_code == 200, resp.content
    assert resp.json() == {"count": 0, "next": None, "previous": None, "results": []}

    operation = openapi_schema["paths"]["/api/v1/workflows/"]["get"]
    text = f"{operation.get('summary', '')} {operation.get('description', '')}".lower()

    assert "compatibility envelope" in text
    assert "always empty" in text
    assert "not a collection" in text
    assert "definition/" in text, "the entry must point at the real graph route"
    # A collection would be paged and would list definitions; this route does
    # neither, so neither may appear in the document.
    assert {
        p["name"] for p in operation.get("parameters", []) if p["in"] == "query"
    } == set()
    response_schema = operation["responses"]["200"]["content"]["application/json"][
        "schema"
    ]
    assert response_schema.get("type") != "array"
    assert response_schema["$ref"].endswith("/WorkflowDefinitionListEnvelope")


# ---------------------------------------------------------------------------
# P1.5 / M-7 — an uninitialized definition names the preset it would get
# ---------------------------------------------------------------------------


def _definition_body(client: APIClient, workspace: Workspace, item_type: str) -> dict:
    resp = client.get(
        f"/api/v1/workflows/definition/?workspace_id={workspace.id}&item_type={item_type}"
    )
    assert resp.status_code == 200, resp.content
    return resp.json()


@pytest.mark.parametrize("tier", WORK_ITEM_TIERS)
def test_uninitialized_work_item_definition_names_the_tier_preset(tier: str) -> None:
    """``preset`` used to be ``null`` for WorkItem, hiding the whole lifecycle."""
    _, admin, _, workspace = _scenario(config_tier=tier)

    body = _definition_body(_client(admin), workspace, "WorkItem")

    assert body["initialized"] is False
    assert body["states"] == []
    assert body["preset"] == WORK_ITEM_PRESET_BY_TIER[tier] == f"work_item_{tier}"


@pytest.mark.parametrize("tier", WORK_ITEM_TIERS)
def test_uninitialized_requirement_definition_names_the_tier(tier: str) -> None:
    """Requirement keeps the 1:1 tier mapping — no regression from P1.5."""
    _, admin, _, workspace = _scenario(config_tier=tier)

    body = _definition_body(_client(admin), workspace, "Requirement")

    assert body["initialized"] is False
    assert body["preset"] == tier


def test_uninitialized_fixed_type_names_its_registry_preset() -> None:
    """A fixed type answers its registry key, independent of the tier."""
    _, admin, _, workspace = _scenario(config_tier="extended")

    body = _definition_body(_client(admin), workspace, "Adr")

    assert body["initialized"] is False
    assert body["preset"] == "adr_default"


def test_missing_preset_config_falls_back_to_standard() -> None:
    """No usable tier configuration anywhere must still answer a real preset."""
    _, admin, _, workspace = _scenario()  # preset={"name": ...}, no config row

    work_item = _definition_body(_client(admin), workspace, "WorkItem")
    requirement = _definition_body(_client(admin), workspace, "Requirement")

    assert work_item["preset"] == "work_item_standard"
    assert requirement["preset"] == "standard"


@pytest.mark.parametrize("tier", WORK_ITEM_TIERS)
def test_initialize_stores_the_preset_the_read_promised(tier: str) -> None:
    """Read and write share one resolver, so they cannot disagree."""
    _, admin, _, workspace = _scenario(config_tier=tier)
    client = _client(admin)
    scope = {"workspace_id": str(workspace.id), "item_type": "WorkItem"}

    promised = _definition_body(client, workspace, "WorkItem")["preset"]
    initialized = client.post(
        "/api/v1/workflows/definition/initialize/", scope, format="json"
    )

    assert initialized.status_code == 201, initialized.content
    body = initialized.json()
    assert body["initialized"] is True
    assert body["preset"] == promised == f"work_item_{tier}"


def test_uninitialized_definition_of_an_unreadable_workspace_invents_no_preset() -> None:
    """A foreign workspace must not answer a preset the caller has no standing in."""
    _, admin, _, _ = _scenario()
    _, _, _, foreign_ws = _scenario(config_tier="extended")

    body = _definition_body(_client(admin), foreign_ws, "WorkItem")

    assert body["initialized"] is False
    assert body["preset"] is None
    assert body["states"] == []
