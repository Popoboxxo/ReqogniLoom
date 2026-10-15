"""REST surface for the attribute reorder endpoint (feature #1260).

Covers the two seams the feature promises:

* ``POST /attribute-defaults/{item_type}/{preset}/reorder/`` and
  ``POST /workspaces/{id}/attribute-definitions/{item_type}/reorder/`` move one
  attribute inside/into a section and write ``section`` + the sparse position
  key in ONE call,
* a stale optimistic-lock ``version`` answers 409 **with the current server
  definition** (``current``) instead of overwriting the other editor's change.
"""
from __future__ import annotations

import pytest

from attribute_definitions.global_definition_store import GlobalAttributeDefinitionStore

GLOBAL_URL = "/api/v1/attribute-defaults/Risk/standard/reorder/"


def _attr(name: str, *, section: str = "general", order: int = 0, **extra):
    return {
        "name": name,
        "kind": "extended",
        "type": "text",
        "section": section,
        "order": order,
        **extra,
    }


@pytest.fixture
def seeded(tenant_fixture):
    """A gappy global default: two general entries 1000 apart, one elsewhere."""
    store = GlobalAttributeDefinitionStore()
    store.initialize(
        tenant_fixture.id,
        "Risk",
        "standard",
        [
            _attr("alpha", order=1000),
            _attr("beta", order=2000),
            _attr("gamma", section="other", order=1000),
        ],
        sections=[{"name": "general"}, {"name": "other"}],
    )
    return store


def _orders(payload) -> dict[str, int]:
    return {a["name"]: a["order"] for a in payload["attributes"]}


def _names(payload) -> list[str]:
    return [a["name"] for a in payload["attributes"]]


@pytest.mark.django_db
class TestGlobalReorder:
    def test_moves_within_a_section_into_the_free_slot(self, admin_client, seeded) -> None:
        response = admin_client.post(
            GLOBAL_URL,
            {"name": "alpha", "section": "general", "after": "beta"},
            format="json",
        )

        assert response.status_code == 200, response.content
        body = response.json()
        assert _orders(body) == {"alpha": 3000, "beta": 2000, "gamma": 1000}
        assert _names(body) == ["beta", "alpha", "gamma"]

    def test_move_to_the_front_of_the_section(self, admin_client, seeded) -> None:
        response = admin_client.post(
            GLOBAL_URL, {"name": "beta", "section": "general"}, format="json"
        )

        assert response.status_code == 200, response.content
        assert _names(response.json()) == ["beta", "alpha", "gamma"]

    def test_cross_section_move_is_atomic(self, admin_client, seeded) -> None:
        response = admin_client.post(
            GLOBAL_URL,
            {"name": "gamma", "section": "general", "after": "beta"},
            format="json",
        )

        assert response.status_code == 200, response.content
        body = response.json()
        assert _orders(body) == {"alpha": 1000, "beta": 2000, "gamma": 3000}
        assert all(a["section"] == "general" for a in body["attributes"])

    def test_only_the_moved_entry_changes(self, admin_client, seeded) -> None:
        before = admin_client.get("/api/v1/attribute-defaults/Risk/standard/").json()

        admin_client.post(
            GLOBAL_URL,
            {"name": "alpha", "section": "general", "after": "beta"},
            format="json",
        )
        after = admin_client.get("/api/v1/attribute-defaults/Risk/standard/").json()

        by_name_before = {a["name"]: a for a in before["attributes"]}
        by_name_after = {a["name"]: a for a in after["attributes"]}
        for name in ("beta", "gamma"):
            assert by_name_after[name] == by_name_before[name]
        assert by_name_after["alpha"]["order"] != by_name_before["alpha"]["order"]

    def test_empty_section_is_allowed(self, admin_client, seeded) -> None:
        response = admin_client.post(
            GLOBAL_URL,
            {"name": "gamma", "section": "fresh", "after": None},
            format="json",
        )

        assert response.status_code == 200, response.content
        assert _orders(response.json())["gamma"] == 1000

    def test_editor_is_forbidden(self, editor_client, seeded) -> None:
        response = editor_client.post(
            GLOBAL_URL,
            {"name": "alpha", "section": "general", "after": "beta"},
            format="json",
        )
        assert response.status_code == 403

    def test_unknown_attribute_is_404(self, admin_client, seeded) -> None:
        response = admin_client.post(
            GLOBAL_URL, {"name": "nope", "section": "general"}, format="json"
        )
        assert response.status_code == 404

    def test_uninitialized_definition_is_404(self, admin_client) -> None:
        response = admin_client.post(
            "/api/v1/attribute-defaults/Icd/minimal/reorder/",
            {"name": "alpha", "section": "general"},
            format="json",
        )
        assert response.status_code == 404

    def test_unknown_anchor_is_400(self, admin_client, seeded) -> None:
        response = admin_client.post(
            GLOBAL_URL,
            {"name": "alpha", "section": "general", "after": "nope"},
            format="json",
        )
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    @pytest.mark.parametrize(
        "body",
        [
            {"section": "general"},
            {"name": "alpha"},
            {"name": "  ", "section": "general"},
            {"name": "alpha", "section": "general", "after": 7},
            {"name": "alpha", "section": "general", "version": "1"},
        ],
    )
    def test_malformed_body_is_400(self, admin_client, seeded, body) -> None:
        assert admin_client.post(GLOBAL_URL, body, format="json").status_code == 400


@pytest.mark.django_db
class TestOptimisticLocking:
    def test_matching_version_succeeds_and_bumps_the_version(
        self, admin_client, seeded
    ) -> None:
        response = admin_client.post(
            GLOBAL_URL,
            {"name": "alpha", "section": "general", "after": "beta", "version": 1},
            format="json",
        )

        assert response.status_code == 200, response.content
        assert response.json()["version"] == 2

    def test_stale_version_is_409_and_carries_the_server_state(
        self, admin_client, seeded
    ) -> None:
        admin_client.post(
            GLOBAL_URL,
            {"name": "alpha", "section": "general", "after": "beta", "version": 1},
            format="json",
        )

        response = admin_client.post(
            GLOBAL_URL,
            {"name": "gamma", "section": "general", "after": "beta", "version": 1},
            format="json",
        )

        assert response.status_code == 409
        body = response.json()
        assert body["error"]["code"] == "CONFLICT"
        # "409 mit Server-Stand": the client can rebase without a second GET.
        assert body["current"]["version"] == 2
        assert [a["name"] for a in body["current"]["attributes"]] == [
            "beta",
            "alpha",
            "gamma",
        ]

    def test_a_stale_write_changes_nothing(self, admin_client, seeded) -> None:
        admin_client.post(
            GLOBAL_URL,
            {"name": "alpha", "section": "general", "after": "beta", "version": 1},
            format="json",
        )
        before = admin_client.get("/api/v1/attribute-defaults/Risk/standard/").json()

        admin_client.post(
            GLOBAL_URL,
            {"name": "gamma", "section": "general", "after": "alpha", "version": 1},
            format="json",
        )

        after = admin_client.get("/api/v1/attribute-defaults/Risk/standard/").json()
        assert after == before


@pytest.mark.django_db
class TestWorkspaceReorder:
    def _url(self, workspace) -> str:
        return f"/api/v1/workspaces/{workspace.id}/attribute-definitions/Risk/reorder/"

    def test_moves_inside_the_workspace_definition(
        self, admin_client, seeded, workspace_fixture
    ) -> None:
        response = admin_client.post(
            self._url(workspace_fixture),
            {"name": "alpha", "section": "general", "after": "beta"},
            format="json",
        )

        assert response.status_code == 200, response.content
        body = response.json()
        assert [a["name"] for a in body["attributes"]] == ["beta", "alpha", "gamma"]
        assert body["is_customized"] is True

    def test_cross_section_move_lands_in_the_target_section(
        self, admin_client, seeded, workspace_fixture
    ) -> None:
        response = admin_client.post(
            self._url(workspace_fixture),
            {"name": "gamma", "section": "general", "after": "alpha"},
            format="json",
        )

        assert response.status_code == 200, response.content
        moved = next(a for a in response.json()["attributes"] if a["name"] == "gamma")
        assert moved["section"] == "general"
        # Midpoint between alpha (1000) and beta (2000) — a single-entry write.
        assert moved["order"] == 1500

    def test_stale_version_is_409_with_the_workspace_state(
        self, admin_client, seeded, workspace_fixture
    ) -> None:
        resolved = admin_client.get(
            f"/api/v1/workspaces/{workspace_fixture.id}/attribute-definitions/Risk/"
        ).json()

        admin_client.post(
            self._url(workspace_fixture),
            {
                "name": "alpha",
                "section": "general",
                "after": "beta",
                "version": resolved["version"],
            },
            format="json",
        )

        response = admin_client.post(
            self._url(workspace_fixture),
            {
                "name": "gamma",
                "section": "general",
                "after": "beta",
                "version": resolved["version"],
            },
            format="json",
        )

        assert response.status_code == 409
        assert response.json()["current"]["is_customized"] is True

    def test_editor_is_forbidden(self, editor_client, seeded, workspace_fixture) -> None:
        response = editor_client.post(
            self._url(workspace_fixture),
            {"name": "alpha", "section": "general", "after": "beta"},
            format="json",
        )
        assert response.status_code == 403
