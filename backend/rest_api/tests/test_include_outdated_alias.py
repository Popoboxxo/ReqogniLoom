"""P2.1 / m-8 — ``include_outdated`` is canonical, ``include_deleted`` an alias.

The review found two spellings for the same opt-in: REST lists published
``?include_deleted=`` while every MCP tool and the ``Document`` tool group said
``include_outdated``. The alias is now explicit rather than accidental:

* ``include_outdated`` is the canonical wire name (it names the state the
  workflow engine actually sets);
* ``include_deleted`` keeps working as a deprecated alias for at least one
  release;
* when both are sent the canonical key wins;
* an unparseable value on *either* key answers 400 where the endpoint validates
  its query parameters (the strict list endpoints and the table route);
* the OpenAPI document declares both and marks the alias ``deprecated``.

The transport call sites still forward to the services' ``include_deleted``
keyword — that is the service-layer vocabulary and is deliberately unchanged.
"""
from __future__ import annotations

import pytest
from drf_spectacular.generators import SchemaGenerator

from persistence.middleware import clear_request_tenant, set_request_tenant
from workflow.services import create_default_workflow

pytestmark = pytest.mark.django_db

REQUIREMENTS = "/api/v1/requirements/"
DOCUMENTS = "/api/v1/documents/"
WORK_ITEMS = "/api/v1/work-items/"
TABLE = "/api/v1/artifacts/table/"


@pytest.fixture(autouse=True)
def _workflows(tenant, workspace):
    """Provision the definitions create/outdate need for both list endpoints."""
    set_request_tenant(tenant.id)
    try:
        for item_type in ("Requirement", "Document"):
            create_default_workflow(
                workspace_id=workspace.id,
                preset="standard" if item_type == "Requirement" else "document_default",
                item_type=item_type,
                tenant_id=tenant.id,
            )
    finally:
        clear_request_tenant()


def _create_requirement(client, workspace, title: str) -> dict:
    response = client.post(
        REQUIREMENTS,
        {"workspace_id": str(workspace.id), "title": title, "category": "Functional"},
        format="json",
    )
    assert response.status_code == 201, response.content
    return response.json()


def _create_document(client, workspace, title: str) -> dict:
    response = client.post(
        DOCUMENTS,
        {"workspace_id": str(workspace.id), "title": title, "kind": "Spec"},
        format="json",
    )
    assert response.status_code == 201, response.content
    return response.json()


def _soft_delete(client, path: str, item_id: str) -> None:
    response = client.delete(
        f"{path}{item_id}/", {"change_reason": "P2.1 alias test"}, format="json"
    )
    assert response.status_code == 204, response.content


def _list_ids(client, path: str, workspace, **params) -> set[str]:
    query = {"workspace_id": str(workspace.id), "page_size": "100", **params}
    response = client.get(path, query)
    assert response.status_code == 200, response.content
    body = response.json()
    return {row["id"] for row in body["results"]}


# ---------------------------------------------------------------------------
# The canonical spelling
# ---------------------------------------------------------------------------


def test_include_outdated_shows_a_soft_deleted_requirement(authed_client, workspace):
    kept = _create_requirement(authed_client, workspace, "Kept canonical")
    gone = _create_requirement(authed_client, workspace, "Gone canonical")
    _soft_delete(authed_client, REQUIREMENTS, gone["id"])

    assert gone["id"] not in _list_ids(authed_client, REQUIREMENTS, workspace)
    assert gone["id"] in _list_ids(
        authed_client, REQUIREMENTS, workspace, include_outdated="true"
    )
    assert kept["id"] in _list_ids(
        authed_client, REQUIREMENTS, workspace, include_outdated="true"
    )


def test_include_outdated_shows_a_soft_deleted_document(authed_client, workspace):
    document = _create_document(authed_client, workspace, "Doc canonical")
    _soft_delete(authed_client, DOCUMENTS, document["id"])

    assert document["id"] not in _list_ids(authed_client, DOCUMENTS, workspace)
    assert document["id"] in _list_ids(
        authed_client, DOCUMENTS, workspace, include_outdated="true"
    )


def test_include_outdated_works_on_the_table_route(authed_client, workspace):
    requirement = _create_requirement(authed_client, workspace, "Table canonical")
    _soft_delete(authed_client, REQUIREMENTS, requirement["id"])

    def _table_count(**params) -> int:
        response = authed_client.get(
            TABLE,
            {"workspace_id": str(workspace.id), "item_type": "Requirement", **params},
        )
        assert response.status_code == 200, response.content
        return response.json()["count"]

    assert _table_count() == 0
    assert _table_count(include_outdated="true") == 1


# ---------------------------------------------------------------------------
# The deprecated alias
# ---------------------------------------------------------------------------


def test_include_deleted_alias_still_shows_the_same_rows(authed_client, workspace):
    requirement = _create_requirement(authed_client, workspace, "Alias requirement")
    document = _create_document(authed_client, workspace, "Alias document")
    _soft_delete(authed_client, REQUIREMENTS, requirement["id"])
    _soft_delete(authed_client, DOCUMENTS, document["id"])

    assert requirement["id"] in _list_ids(
        authed_client, REQUIREMENTS, workspace, include_deleted="true"
    )
    assert document["id"] in _list_ids(
        authed_client, DOCUMENTS, workspace, include_deleted="true"
    )


# ---------------------------------------------------------------------------
# Precedence: the canonical key wins when both are present
# ---------------------------------------------------------------------------


def test_canonical_false_beats_a_truthy_alias(authed_client, workspace):
    gone = _create_requirement(authed_client, workspace, "Precedence hidden")
    _soft_delete(authed_client, REQUIREMENTS, gone["id"])

    ids = _list_ids(
        authed_client,
        REQUIREMENTS,
        workspace,
        include_outdated="false",
        include_deleted="true",
    )

    assert gone["id"] not in ids


def test_canonical_true_beats_a_falsy_alias(authed_client, workspace):
    gone = _create_requirement(authed_client, workspace, "Precedence shown")
    _soft_delete(authed_client, REQUIREMENTS, gone["id"])

    ids = _list_ids(
        authed_client,
        REQUIREMENTS,
        workspace,
        include_outdated="true",
        include_deleted="false",
    )

    assert gone["id"] in ids


# ---------------------------------------------------------------------------
# Strict validation covers both keys
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("key", ["include_outdated", "include_deleted"])
def test_invalid_value_on_either_key_is_400_on_a_strict_list(
    authed_client, workspace, key
):
    response = authed_client.get(
        REQUIREMENTS, {"workspace_id": str(workspace.id), key: "maybe"}
    )

    assert response.status_code == 400, response.content
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert key in body["error"]["message"]


@pytest.mark.parametrize("key", ["include_outdated", "include_deleted"])
def test_invalid_value_on_either_key_is_400_on_the_table(
    authed_client, workspace, key
):
    response = authed_client.get(
        TABLE,
        {
            "workspace_id": str(workspace.id),
            "item_type": "Requirement",
            key: "maybe",
        },
    )

    assert response.status_code == 400, response.content


# ---------------------------------------------------------------------------
# Lenient-about-unknown-parameters endpoints still validate the flag
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", [DOCUMENTS, WORK_ITEMS])
@pytest.mark.parametrize("key", ["include_outdated", "include_deleted"])
def test_invalid_value_on_either_key_is_400_on_documents_and_work_items(
    authed_client, workspace, path, key
):
    """The document/work-item lists validate the flag, not the whole query.

    Both endpoints deliberately accept unrelated parameters (clients attach
    their own diagnostics), so they cannot use the strict
    ``reject_unknown_query_params``. ``validate_include_flag`` covers exactly
    the two boolean keys — an unparseable value must not silently mean "false".
    """
    response = authed_client.get(
        path, {"workspace_id": str(workspace.id), key: "maybe"}
    )

    assert response.status_code == 400, response.content
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert key in body["error"]["message"]


@pytest.mark.parametrize("path", [DOCUMENTS, WORK_ITEMS])
def test_documents_and_work_items_still_ignore_unrelated_parameters(
    authed_client, workspace, path
):
    """The flag validation is not licence to reject every unknown parameter."""
    response = authed_client.get(
        path,
        {"workspace_id": str(workspace.id), "some_client_diagnostic": "1"},
    )

    assert response.status_code == 200, response.content


# ---------------------------------------------------------------------------
# OpenAPI honesty
# ---------------------------------------------------------------------------


def _declared_parameters(path: str) -> dict[str, dict]:
    schema = SchemaGenerator().get_schema(request=None, public=True)
    parameters = schema["paths"][path]["get"].get("parameters", [])
    return {parameter["name"]: parameter for parameter in parameters}


@pytest.mark.parametrize("path", [DOCUMENTS, REQUIREMENTS, TABLE])
def test_schema_declares_canonical_and_deprecated_alias(path):
    declared = _declared_parameters(path)

    assert "include_outdated" in declared, path
    assert "include_deleted" in declared, path
    assert declared["include_deleted"].get("deprecated") is True, (
        f"{path} still advertises include_deleted without the deprecation marker"
    )
    assert not declared["include_outdated"].get("deprecated"), path
