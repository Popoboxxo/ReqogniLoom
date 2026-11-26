"""P0.1 / B-1 — the workflow editor's REST surface is fully documented.

Before this module's change ``WorkflowDefinitionViewSet`` had **no**
``@extend_schema`` at all. The generated document therefore described the
editor's actions with whatever drf-spectacular could guess: the state/transition
``DELETE`` routes advertised ``204`` although the handler answers ``200`` with
the full graph, ``definition/`` advertised no query parameters although both are
mandatory, ``retrieve``/``destroy`` advertised a ``200``/``204`` success the
handlers can never produce, and not a single edit-mode failure (403 admin gate,
409 orphaned state, 409 NO_GLOBAL_SOURCE) was discoverable.

The assertions below pin the *document* against the handlers:

* every operation of the ViewSet carries a summary and a real response schema
  (a named component, never a free-form object);
* the success codes and the error codes are the ones the handlers really emit;
* the graph component's field set is exactly ``_serialize_definition``'s;
* ``GET /workflows/`` is documented as the empty compatibility envelope it is
  (P1.4 / M-6), not as a CRUD collection.
"""
from __future__ import annotations

import pytest
from drf_spectacular.generators import SchemaGenerator

pytestmark = pytest.mark.django_db

_BASE = "/api/v1/workflows/"
_DEFINITION = f"{_BASE}definition/"

#: (path, method) -> the operation the ViewSet publishes.
_OPERATIONS = {
    (_BASE, "get"): "workflows_list",
    (_BASE, "post"): "workflows_create",
    (f"{_BASE}{{id}}/", "get"): "workflows_retrieve",
    (f"{_BASE}{{id}}/", "patch"): "workflows_partial_update",
    (f"{_BASE}{{id}}/", "delete"): "workflows_destroy",
    (_DEFINITION, "get"): "workflows_definition_retrieve",
    (f"{_DEFINITION}states/", "post"): "workflows_definition_states_create",
    (
        f"{_DEFINITION}states/{{state_id}}/",
        "patch",
    ): "workflows_definition_states_partial_update",
    (
        f"{_DEFINITION}states/{{state_id}}/",
        "delete",
    ): "workflows_definition_states_destroy",
    (f"{_DEFINITION}transitions/", "post"): "workflows_definition_transitions_create",
    (
        f"{_DEFINITION}transitions/{{transition_id}}/",
        "patch",
    ): "workflows_definition_transitions_partial_update",
    (
        f"{_DEFINITION}transitions/{{transition_id}}/",
        "delete",
    ): "workflows_definition_transitions_destroy",
    (
        f"{_DEFINITION}initialize/",
        "post",
    ): "workflows_definition_initialize_create",
    (f"{_DEFINITION}reset/", "post"): "workflows_definition_reset_create",
}

#: The field set of ``WorkflowDefinitionViewSet._serialize_definition``.
_GRAPH_FIELDS = {
    "item_type",
    "preset",
    "is_custom",
    "is_customized",
    "on_default",
    "source_global_id",
    "initial_state",
    "initialized",
    "states",
    "transitions",
}

_TRANSITION_FIELDS = {
    "from_state",
    "to_state",
    "allowed_roles",
    "requires_change_reason",
    "signature_gate",
}

#: The edit-mode actions that can reach a ``409`` as well as the shared
#: 400/403/404 set (F-6): ``modify_state`` (a rename may orphan a state, a delete
#: may hit a state still referenced by a transition) and ``reset/`` (no linked
#: global default → NO_GLOBAL_SOURCE).
_EDIT_OPERATIONS = [
    (_DEFINITION + "states/{state_id}/", "patch"),
    (_DEFINITION + "states/{state_id}/", "delete"),
    (_DEFINITION + "reset/", "post"),
]

#: The mutation actions with no path to a ``409`` (F-6): the three create
#: actions and both transition edits — ``update_transition``/``delete_transition``
#: hand the engine an unchanged state list, so neither can orphan nor
#: reference-block a state.
_NO_409_OPERATIONS = [
    (_DEFINITION + "states/", "post"),
    (_DEFINITION + "transitions/", "post"),
    (_DEFINITION + "initialize/", "post"),
    (_DEFINITION + "transitions/{transition_id}/", "patch"),
    (_DEFINITION + "transitions/{transition_id}/", "delete"),
]

#: The edit-mode actions that answer the full graph plus the shared error set.
_MUTATION_OPERATIONS = _EDIT_OPERATIONS + _NO_409_OPERATIONS


@pytest.fixture(scope="module")
def schema() -> dict:
    return SchemaGenerator().get_schema(request=None, public=True)


def _operation(schema: dict, path: str, method: str) -> dict:
    assert path in schema["paths"], f"{path} is missing from the schema"
    assert method in schema["paths"][path], f"{method.upper()} {path} is missing"
    return schema["paths"][path][method]


def _resolve(schema: dict, node: dict) -> dict:
    """Resolve a ``$ref`` (optionally wrapped in ``allOf``) against components."""
    while "allOf" in node:
        node = node["allOf"][0]
    ref = node.get("$ref")
    if not ref:
        return node
    return schema["components"]["schemas"][ref.rsplit("/", 1)[-1]]


def _response_schema(schema: dict, path: str, method: str, code: str) -> dict:
    response = _operation(schema, path, method)["responses"][code]
    content = response.get("content") or {}
    assert content, f"{method.upper()} {path} {code} declares no content schema"
    return content["application/json"]["schema"]


# ---------------------------------------------------------------------------
# Every operation is documented — no generic placeholder may remain
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("path", "method"), sorted(_OPERATIONS))
def test_operation_is_documented(schema: dict, path: str, method: str) -> None:
    """Each action carries its own summary and a described success response."""
    operation = _operation(schema, path, method)

    assert operation.get("operationId") == _OPERATIONS[(path, method)]
    assert (operation.get("summary") or "").strip(), (
        f"{method.upper()} {path} has no summary — a generic, undocumented "
        "operation is exactly what P0.1 removes"
    )
    assert operation.get("description"), f"{method.upper()} {path} has no description"


@pytest.mark.parametrize(("path", "method"), sorted(_OPERATIONS))
def test_no_operation_falls_back_to_a_generic_object(
    schema: dict, path: str, method: str
) -> None:
    """A free-form body is not a contract — the P0.1 defect was exactly that."""
    operation = _operation(schema, path, method)
    for root in (
        (operation.get("responses") or {}),
        (operation.get("requestBody") or {}),
    ):
        for node in _walk(root):
            assert node.get("x-reqlo-untyped") is not True, (
                f"{method.upper()} {path} still uses the permissive fallback"
            )


def _walk(node: object):
    """Yield every dict reachable from *node* (document-order independent)."""
    stack: list[object] = [node]
    seen: set[int] = set()
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            if id(current) in seen:
                continue
            seen.add(id(current))
            yield current
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)


# ---------------------------------------------------------------------------
# definition/ (GET) — query parameters and the graph contract
# ---------------------------------------------------------------------------


class TestDefinitionReadOperation:
    """``GET /workflows/definition/`` — the graph the editor renders."""

    def test_documents_both_mandatory_query_parameters(self, schema: dict) -> None:
        operation = _operation(schema, _DEFINITION, "get")
        params = {
            p["name"]: p for p in operation.get("parameters", []) if p["in"] == "query"
        }

        assert set(params) == {"workspace_id", "item_type"}
        assert params["workspace_id"]["required"] is True
        assert params["item_type"]["required"] is True
        assert params["workspace_id"]["schema"]["type"] == "string"
        assert params["workspace_id"]["schema"]["format"] == "uuid"

    def test_success_is_the_full_graph_component(self, schema: dict) -> None:
        node = _response_schema(schema, _DEFINITION, "get", "200")
        assert node.get("$ref", "").endswith("/WorkflowDefinitionGraph")

    def test_documents_only_the_statuses_it_can_produce(self, schema: dict) -> None:
        """F1: the route has no read gate, so it claims no 403/404 of its own.

        ``WorkflowFacade.get_definition`` collapses every domain error to
        ``None`` and the empty-graph branch answers 200 — a foreign-tenant
        workspace included (pinned by
        ``test_workflow_definition_views_rest.py``). The dedicated 403/404
        entries that promised "no read access to the workspace" / "the
        workspace does not exist for the caller's tenant" described a gate the
        handler does not have. The global postprocessing hook still injects
        403/404 into every operation — that is fine, they just may not carry a
        stronger, package-specific claim than the generic one.
        """
        responses = _operation(schema, _DEFINITION, "get")["responses"]

        assert "200" in responses
        # The one error the handler produces itself: missing/invalid scope.
        assert "VALIDATION_ERROR" in responses["400"]["description"]
        assert responses["400"]["content"]["application/json"]["schema"][
            "$ref"
        ].endswith("/ErrorResponse")

        # 403/404 stay in the document (the hook adds them to every operation)
        # with the generic wording only.
        assert responses["403"]["description"] == "RBAC permission denied."
        assert responses["404"]["description"] == "Resource not found."

        declared = " ".join(
            str(node.get("description") or "") for node in responses.values()
        ).lower()
        assert "no read access to the workspace" not in declared, (
            "the read route has no workspace gate — it must not claim one"
        )
        assert "does not exist for the caller's tenant" not in declared

    def test_description_states_the_uninitialized_and_preset_behaviour(
        self, schema: dict
    ) -> None:
        """P1.5 / M-7: the empty graph names the preset it would be seeded with."""
        description = _operation(schema, _DEFINITION, "get")["description"]

        assert "initialized: false" in description
        assert "preset" in description
        assert "404" in description  # explicitly: an unconfigured type is NOT a 404


# ---------------------------------------------------------------------------
# The graph component matches ``_serialize_definition`` exactly
# ---------------------------------------------------------------------------


class TestGraphContract:
    def test_graph_component_fields_match_the_serializer(self, schema: dict) -> None:
        component = schema["components"]["schemas"]["WorkflowDefinitionGraph"]
        assert set(component["properties"]) == _GRAPH_FIELDS

    def test_transition_component_fields_match_the_serializer(
        self, schema: dict
    ) -> None:
        component = schema["components"]["schemas"]["WorkflowTransitionGraph"]
        assert set(component["properties"]) == _TRANSITION_FIELDS
        assert component["properties"]["allowed_roles"]["type"] == "array"

    def test_preset_is_nullable_and_initial_state_is_nullable(
        self, schema: dict
    ) -> None:
        component = schema["components"]["schemas"]["WorkflowDefinitionGraph"]
        assert component["properties"]["preset"].get("nullable") is True
        assert component["properties"]["initial_state"].get("nullable") is True


# ---------------------------------------------------------------------------
# Edit-mode mutations — 201/200 plus the shared error classes (400/403/404,
# and 409 only on a state rename/delete or ``reset/``)
# ---------------------------------------------------------------------------


class TestEditModeOperations:
    @pytest.mark.parametrize(("path", "method"), _MUTATION_OPERATIONS)
    def test_every_mutation_declares_the_shared_error_set(
        self, schema: dict, path: str, method: str
    ) -> None:
        responses = _operation(schema, path, method)["responses"]

        assert {"400", "403", "404"}.issubset(set(responses)), (
            f"{method.upper()} {path} does not document the 400/403/404 "
            "classes the handler can answer"
        )
        for code in ("400", "403", "404"):
            assert responses[code]["content"]["application/json"]["schema"][
                "$ref"
            ].endswith("/ErrorResponse")

    @pytest.mark.parametrize(("path", "method"), _EDIT_OPERATIONS)
    def test_edit_operations_declare_the_409_they_can_emit(
        self, schema: dict, path: str, method: str
    ) -> None:
        """F-6: only the operations that can raise NO_GLOBAL_SOURCE/CONFLICT."""
        responses = _operation(schema, path, method)["responses"]

        assert "409" in responses, (
            f"{method.upper()} {path} can answer 409 and must document it"
        )
        assert responses["409"]["content"]["application/json"]["schema"][
            "$ref"
        ].endswith("/ErrorResponse")

    @pytest.mark.parametrize(("path", "method"), _NO_409_OPERATIONS)
    def test_no_409_operations_do_not_declare_the_status_they_cannot_emit(
        self, schema: dict, path: str, method: str
    ) -> None:
        """F-6: neither the creates nor the transition edits can raise a 409.

        ``add_state``/``add_transition``/``initialize`` raise none of the three
        conflict errors, and ``update_transition``/``delete_transition`` pass an
        unchanged state list to ``validate_and_persist_custom`` — so no state can
        be orphaned or left reference-blocked by a transition edit.
        """
        responses = _operation(schema, path, method)["responses"]

        assert "409" not in responses, (
            f"{method.upper()} {path} documents a 409 the handler cannot emit"
        )

    @pytest.mark.parametrize(("path", "method"), _MUTATION_OPERATIONS)
    def test_every_mutation_answers_the_full_graph(
        self, schema: dict, path: str, method: str
    ) -> None:
        """Every edit answers the re-serialised graph, never a bare 204."""
        responses = _operation(schema, path, method)["responses"]
        success = {
            code: node for code, node in responses.items() if code.startswith("2")
        }

        assert success, f"{method.upper()} {path} declares no success response"
        assert "204" not in success, (
            f"{method.upper()} {path} answers the full graph, not 204"
        )
        for code in success:
            node = _response_schema(schema, path, method, code)
            assert node.get("$ref", "").endswith("/WorkflowDefinitionGraph")

    @pytest.mark.parametrize(
        ("path", "method", "code"),
        [
            (_DEFINITION + "states/", "post", "201"),
            (_DEFINITION + "transitions/", "post", "201"),
            (_DEFINITION + "initialize/", "post", "201"),
            (_DEFINITION + "reset/", "post", "200"),
        ],
    )
    def test_create_and_reset_status_codes_are_the_handlers(
        self, schema: dict, path: str, method: str, code: str
    ) -> None:
        responses = _operation(schema, path, method)["responses"]
        assert code in responses
        other_success = {
            status
            for status in responses
            if status.startswith("2") and status not in {code, "204"}
        }
        assert other_success == set(), (
            f"{method.upper()} {path} answers exactly {code}; also declared: "
            f"{sorted(other_success)}"
        )

    def test_state_and_transition_deletes_answer_200_not_204(
        self, schema: dict
    ) -> None:
        for path in (
            _DEFINITION + "states/{state_id}/",
            _DEFINITION + "transitions/{transition_id}/",
        ):
            responses = _operation(schema, path, "delete")["responses"]
            assert "204" not in responses, f"DELETE {path} answers 200, not 204"
            assert "200" in responses

    @pytest.mark.parametrize(
        ("path", "method"),
        [
            (_DEFINITION + "states/{state_id}/", "delete"),
            (_DEFINITION + "transitions/{transition_id}/", "delete"),
        ],
    )
    def test_deletes_document_the_scope_as_query_parameters(
        self, schema: dict, path: str, method: str
    ) -> None:
        """``DELETE`` has no body, so the scope travels in the query string."""
        params = {
            p["name"]
            for p in _operation(schema, path, method).get("parameters", [])
            if p["in"] == "query"
        }
        assert params == {"workspace_id", "item_type"}

    def test_state_create_documents_its_request_body(self, schema: dict) -> None:
        """The body is the scope plus the state name — not a bare object."""
        body = _operation(schema, _DEFINITION + "states/", "post")["requestBody"]
        node = body["content"]["application/json"]["schema"]
        component = _resolve(schema, node)

        assert node.get("$ref", "").endswith(
            "/WorkspaceWorkflowStateCreateRequestRequest"
        )
        assert set(component["properties"]) == {"workspace_id", "item_type", "name"}
        assert set(component["required"]) == {"workspace_id", "item_type", "name"}
        # F2: the engine accepts custom item types, so the document must not
        # close the field with an enum — it is a plain string whose help text
        # lists the known types as examples.
        item_type = component["properties"]["item_type"]
        assert item_type["type"] == "string"
        assert "enum" not in item_type, (
            "item_type must not publish a closed enum: the engine accepts "
            "custom spellings beyond the known types"
        )
        help_text = item_type["description"]
        assert "'Requirement'" in help_text
        assert "'WorkItem'" in help_text
        assert "custom" in help_text.lower()

    def test_transition_create_documents_the_rule_fields(self, schema: dict) -> None:
        component = schema["components"]["schemas"][
            "WorkspaceWorkflowTransitionCreateRequestRequest"
        ]
        assert set(component["properties"]) == {
            "workspace_id",
            "item_type",
            "from_state",
            "to_state",
            "allowed_roles",
            "requires_change_reason",
            "signature_gate",
        }
        assert {"from_state", "to_state"}.issubset(set(component["required"]))

    def test_transition_update_documents_nullable_rule_fields(
        self, schema: dict
    ) -> None:
        """A PATCH body carries only the fields the caller wants to change."""
        component = schema["components"]["schemas"][
            "PatchedWorkspaceWorkflowTransitionUpdateRequestRequest"
        ]
        assert set(component["properties"]) == {
            "workspace_id",
            "item_type",
            "allowed_roles",
            "requires_change_reason",
            "signature_gate",
        }


# ---------------------------------------------------------------------------
# list / retrieve / destroy — the non-CRUD routes (P1.4)
# ---------------------------------------------------------------------------


class TestListContract:
    """``GET /workflows/`` is an empty compatibility envelope, not a collection."""

    def test_success_is_the_single_envelope_component(self, schema: dict) -> None:
        node = _response_schema(schema, _BASE, "get", "200")

        assert node.get("type") != "array", (
            "the handler answers ONE envelope object; an array of envelopes "
            "would describe a collection that does not exist"
        )
        assert node.get("$ref", "").endswith("/WorkflowDefinitionListEnvelope")

    def test_documents_no_pagination_parameters(self, schema: dict) -> None:
        """A route that never pages must not advertise ``page``/``page_size``."""
        params = {
            p["name"]
            for p in _operation(schema, _BASE, "get").get("parameters", [])
            if p["in"] == "query"
        }
        assert params == set(), f"unexpected pagination parameters: {params}"

    def test_description_does_not_promise_a_crud_collection(self, schema: dict) -> None:
        operation = _operation(schema, _BASE, "get")
        text = f"{operation.get('summary', '')} {operation.get('description', '')}"

        # It says what it is...
        assert "always empty" in text.lower()
        assert "compatibility envelope" in text.lower()
        assert "definition/" in text
        # ...and it states the negative explicitly, which is what P1.4 asked for.
        assert "not a collection" in text.lower()
        assert "not** a crud list" in text.lower() or "not a crud list" in text.lower()
        # ...and it does not promise the collection semantics it lacks.
        assert "returns the list of" not in text.lower()
        assert "all workflow definitions" not in text.lower()


class TestNonCrudDetailRoutes:
    def test_retrieve_documents_only_the_404_it_answers(self, schema: dict) -> None:
        responses = _operation(schema, f"{_BASE}{{id}}/", "get")["responses"]

        assert "404" in responses
        assert not [
            code for code in responses if code.startswith("2")
        ], "the detail GET always answers 404 — a documented 2xx would be a lie"
        assert responses["404"]["content"]["application/json"]["schema"][
            "$ref"
        ].endswith("/ErrorResponse")

    def test_destroy_documents_only_the_403_it_answers(self, schema: dict) -> None:
        responses = _operation(schema, f"{_BASE}{{id}}/", "delete")["responses"]

        assert "403" in responses
        assert not [
            code for code in responses if code.startswith("2")
        ], "workflow definitions cannot be deleted — a documented 2xx would be a lie"


# ---------------------------------------------------------------------------
# The legacy create / partial_update pair
# ---------------------------------------------------------------------------


class TestLegacyArtifactRoutes:
    def test_create_documents_its_request_and_201(self, schema: dict) -> None:
        operation = _operation(schema, _BASE, "post")
        body = operation["requestBody"]["content"]["application/json"]["schema"]

        assert body.get("$ref", "").endswith("/WorkflowDefinitionRequest")
        assert "201" in operation["responses"]
        assert "400" in operation["responses"]

    def test_partial_update_documents_the_transition_body(self, schema: dict) -> None:
        operation = _operation(schema, f"{_BASE}{{id}}/", "patch")
        node = operation["requestBody"]["content"]["application/json"]["schema"]
        component = _resolve(schema, node)

        assert node.get("$ref", "").endswith(
            "/PatchedWorkflowLegacyTransitionRequestRequest"
        ), (
            "F-7: the inline request serializer keeps the distinct "
            "WorkflowLegacyTransitionRequest name so the generated document does "
            "not read like serializers_diagram's WorkflowTransitionRequestSerializer"
        )
        assert "target_state" in component["properties"]
        assert "change_reason" in component["properties"]
        assert set(operation["responses"]) >= {"200", "400", "404"}
        # drf-spectacular treats a PATCH body as partial, so the runtime
        # requirement lives in the description instead of `required`.
        assert "target_state" in operation["description"]
        assert "400" in operation["description"]
