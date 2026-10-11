"""Error-path REST coverage for TraceLinkViewSet (views.py).

leaf_id : COMP-RA-TL (TraceLinkViewSet)
req_id  : REQ-L2-RA-001, REQ-002, REQ-L2-TE-019, REQ-L2-VS-004, REQ-264

``test_tracelink_crud_rest.py`` pins the CRUD/proposal happy paths and
``test_trace_graph_endpoints_rest.py`` the graph read endpoints. This module
drives the same ViewSet through the real middleware stack for the branches
those suites leave open:

- the ``?artifact_id=`` listing edge cases — an unresolvable artifact id that is
  logged instead of being indistinguishable from "no links" (#264);
- service-error mapping on ``list``/``create``/``destroy``/``confirm`` — the
  three mapped domain errors get their status, anything unexpected a masked 500;
- the ``similar`` success path (an embedded query link) plus the pgvector
  outage (503) and unexpected-error (500) branches;
- the graph actions' handlers — ``impact``/``path``/``cycles`` mapped errors and
  their logged unexpected-error fallbacks.
"""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from application.services import (
    NotFoundError,
    PermissionDeniedError,
    PgVectorUnavailableError,
    TraceLinkService,
    ValidationError,
)
from auth_tenancy.models import ROLE_ADMIN, UserRole
from link_types.workspace_store import provision_workspace_link_types
from persistence.embedding_dimensions import EMBEDDING_VECTOR_DIMENSIONS
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Artifact, Tenant, TraceLink, User, Workspace
from traceability.types import LinkType

pytestmark = pytest.mark.django_db

_PASSWORD = "hunter2pass"
_LINK = LinkType.ALLOCATED_TO.value


def _scenario() -> tuple[Tenant, User, Workspace]:
    """Create a tenant, one admin user and one Extended-preset workspace."""
    suffix = uuid.uuid4().hex[:8]
    tenant = Tenant.objects.create(name=f"TL-{suffix}", slug=f"tl-{suffix}", is_active=True)
    user = User.objects.create(
        username=f"tl-{suffix}", email=f"tl-{suffix}@t.test", tenant=tenant
    )
    user.set_password(_PASSWORD)
    user.save(update_fields=["password"])

    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="TL WS", preset={"name": "extended"}
        )
        # Link validation is always-on: an unprovisioned workspace has an empty
        # link-type catalog and rejects every trace link (see rest_api/conftest).
        provision_workspace_link_types(workspace_id=workspace.id, tenant_id=tenant.id)
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=workspace, role=ROLE_ADMIN
        )
    finally:
        clear_request_tenant()
    return tenant, user, workspace


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


def _artifact(
    tenant: Tenant, workspace: Workspace, name: str = "Artifact", artifact_type: str = "Requirement"
) -> Artifact:
    set_request_tenant(tenant.id)
    try:
        return Artifact.objects.create(
            tenant=tenant,
            workspace=workspace,
            artifact_type=artifact_type,
            custom_fields={"name": name},
        )
    finally:
        clear_request_tenant()


def _link(
    tenant: Tenant,
    source: Artifact,
    target: Artifact,
    *,
    proposed: bool = False,
    embedding: list[float] | None = None,
) -> TraceLink:
    set_request_tenant(tenant.id)
    try:
        return TraceLink.objects.create(
            tenant=tenant,
            source=source,
            target=target,
            link_type=_LINK,
            # ``is_proposal`` reads ``proposed_at`` — an unconfirmed agent
            # proposal carries a timestamp, ``proposed_by`` stays optional.
            proposed_at=timezone.now() if proposed else None,
            embedding=embedding,
        )
    finally:
        clear_request_tenant()


def _vector(value: float) -> list[float]:
    """A full-width embedding vector so pgvector accepts the row."""
    return [value] * EMBEDDING_VECTOR_DIMENSIONS


# ---------------------------------------------------------------------------
# list — the ?artifact_id= edge cases
# ---------------------------------------------------------------------------


def test_list_with_an_unresolvable_artifact_id_is_logged_not_silent(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """#264: a bad artifact id must be distinguishable from "no links"."""
    _, user, workspace = _scenario()

    with caplog.at_level("DEBUG", logger="rest_api.views"):
        resp = _client(user).get(
            f"/api/v1/tracelinks/?workspace_id={workspace.id}&artifact_id={uuid.uuid4()}"
        )

    assert resp.status_code == 200, resp.content
    assert resp.json()["count"] == 0
    assert "TraceLink upstream query failed" in caplog.text


@pytest.mark.parametrize(
    "exc",
    [
        ValidationError("link type unknown"),
        NotFoundError("workspace gone"),
        PermissionDeniedError("no access"),
    ],
)
def test_list_maps_mapped_service_errors(exc: Exception) -> None:
    _, user, workspace = _scenario()
    with patch.object(
        TraceLinkService, "list_links_for_workspace_queryset", side_effect=exc
    ):
        resp = _client(user).get(f"/api/v1/tracelinks/?workspace_id={workspace.id}")

    assert resp.status_code in (400, 403, 404), resp.content
    assert "error" in resp.json()


def test_list_maps_an_unexpected_error_to_500() -> None:
    _, user, workspace = _scenario()
    with patch.object(
        TraceLinkService,
        "list_links_for_workspace_queryset",
        side_effect=RuntimeError("boom"),
    ):
        resp = _client(user).get(f"/api/v1/tracelinks/?workspace_id={workspace.id}")

    assert resp.status_code == 500, resp.content
    assert resp.json()["error"]["code"] == "INTERNAL_SERVER_ERROR"


# ---------------------------------------------------------------------------
# create / destroy / confirm — error mapping
# ---------------------------------------------------------------------------


def test_create_maps_an_unexpected_error_to_500() -> None:
    _, user, workspace = _scenario()
    source = _artifact(user.tenant, workspace)
    target = _artifact(user.tenant, workspace)
    with patch.object(
        TraceLinkService, "create_trace_link", side_effect=RuntimeError("boom")
    ):
        resp = _client(user).post(
            "/api/v1/tracelinks/",
            {
                "source_id": str(source.id),
                "target_id": str(target.id),
                "link_type": _LINK,
            },
            format="json",
        )

    assert resp.status_code == 500, resp.content
    assert resp.json()["error"]["code"] == "INTERNAL_SERVER_ERROR"


def test_destroy_maps_an_unexpected_error_to_500() -> None:
    tenant, user, workspace = _scenario()
    link = _link(
        tenant, _artifact(tenant, workspace), _artifact(tenant, workspace)
    )
    with patch.object(
        TraceLinkService, "delete_trace_link", side_effect=RuntimeError("boom")
    ):
        resp = _client(user).delete(f"/api/v1/tracelinks/{link.id}/")

    assert resp.status_code == 500, resp.content
    assert resp.json()["error"]["code"] == "INTERNAL_SERVER_ERROR"


def test_confirm_maps_a_value_error() -> None:
    tenant, user, workspace = _scenario()
    link = _link(
        tenant, _artifact(tenant, workspace), _artifact(tenant, workspace)
    )
    with patch.object(
        TraceLinkService,
        "confirm_proposed_link",
        side_effect=ValueError("not a proposal"),
    ):
        resp = _client(user).post(
            f"/api/v1/tracelinks/{link.id}/confirm/", {}, format="json"
        )

    assert resp.status_code == 500, resp.content
    assert resp.json()["error"]["code"] == "INTERNAL_SERVER_ERROR"


# ---------------------------------------------------------------------------
# similar — success path plus the pgvector outage
# ---------------------------------------------------------------------------


def test_similar_returns_neighbours_of_an_embedded_link() -> None:
    """REQ-L2-VS-004: the nearest neighbour of an embedded link is returned."""
    tenant, user, workspace = _scenario()
    query = _link(
        tenant,
        _artifact(tenant, workspace, "Q src"),
        _artifact(tenant, workspace, "Q tgt"),
        embedding=_vector(0.1),
    )
    neighbour = _link(
        tenant,
        _artifact(tenant, workspace, "N src"),
        _artifact(tenant, workspace, "N tgt"),
        embedding=_vector(0.2),
    )

    resp = _client(user).get(
        f"/api/v1/tracelinks/similar/?tracelink_id={query.id}"
    )

    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert [row["id"] for row in body] == [str(neighbour.id)]
    assert 0.0 <= body[0]["similarity_score"] <= 1.0


def test_similar_maps_a_pgvector_outage_to_503() -> None:
    _, user, workspace = _scenario()
    tenant = user.tenant
    link = _link(tenant, _artifact(tenant, workspace), _artifact(tenant, workspace))
    with patch.object(
        TraceLinkService,
        "find_similar_trace_links",
        side_effect=PgVectorUnavailableError("vector extension missing"),
    ):
        resp = _client(user).get(
            f"/api/v1/tracelinks/similar/?tracelink_id={link.id}"
        )

    assert resp.status_code == 503, resp.content
    assert resp.json()["error"]["code"] == "SERVICE_UNAVAILABLE"


def test_similar_maps_an_unexpected_error_to_500() -> None:
    _, user, workspace = _scenario()
    tenant = user.tenant
    link = _link(tenant, _artifact(tenant, workspace), _artifact(tenant, workspace))
    with patch.object(
        TraceLinkService,
        "find_similar_trace_links",
        side_effect=RuntimeError("boom"),
    ):
        resp = _client(user).get(
            f"/api/v1/tracelinks/similar/?tracelink_id={link.id}"
        )

    assert resp.status_code == 500, resp.content
    assert resp.json()["error"]["code"] == "INTERNAL_SERVER_ERROR"


# ---------------------------------------------------------------------------
# impact / path / cycles — the read-model graph actions
# ---------------------------------------------------------------------------


def test_impact_flags_a_truncated_result_set() -> None:
    """A full page is marked truncated so a client knows to ask for more."""
    tenant, user, workspace = _scenario()
    source = _artifact(tenant, workspace, "Source")
    _artifact(tenant, workspace, "Target")
    _link(tenant, source, _artifact(tenant, workspace, "Other target"))

    resp = _client(user).get(
        f"/api/v1/tracelinks/impact/?artifact_id={source.id}&limit=1"
    )

    assert resp.status_code == 200, resp.content
    assert resp.json(), "the walk must return at least the direct neighbour"
    assert resp.headers["X-Result-Truncated"] == "true"


def test_impact_maps_an_unexpected_error_to_500(caplog: pytest.LogCaptureFixture) -> None:
    _, user, workspace = _scenario()
    artifact = _artifact(user.tenant, workspace)
    with patch(
        "traceability.service.impact_analysis", side_effect=RuntimeError("boom")
    ):
        with caplog.at_level("ERROR", logger="rest_api.views"):
            resp = _client(user).get(
                f"/api/v1/tracelinks/impact/?artifact_id={artifact.id}"
            )

    assert resp.status_code == 500, resp.content
    assert resp.json()["error"]["code"] == "INTERNAL_SERVER_ERROR"
    assert "TraceLinkViewSet.impact" in caplog.text


def test_path_to_an_unknown_artifact_is_404() -> None:
    _, user, _ = _scenario()
    resp = _client(user).get(
        f"/api/v1/tracelinks/path/?source_id={uuid.uuid4()}&target_id={uuid.uuid4()}"
    )
    assert resp.status_code == 404, resp.content


def test_path_maps_an_unexpected_error_to_500(caplog: pytest.LogCaptureFixture) -> None:
    _, user, workspace = _scenario()
    artifact = _artifact(user.tenant, workspace)
    with patch("traceability.service.find_path", side_effect=RuntimeError("boom")):
        with caplog.at_level("ERROR", logger="rest_api.views"):
            resp = _client(user).get(
                f"/api/v1/tracelinks/path/?source_id={artifact.id}&target_id={artifact.id}"
            )

    assert resp.status_code == 500, resp.content
    assert resp.json()["error"]["code"] == "INTERNAL_SERVER_ERROR"
    assert "TraceLinkViewSet.path" in caplog.text


def test_cycles_maps_a_validation_error() -> None:
    _, user, workspace = _scenario()
    with patch(
        "traceability.service.detect_cycles",
        side_effect=ValidationError("workspace not readable"),
    ):
        resp = _client(user).get(f"/api/v1/tracelinks/cycles/?workspace_id={workspace.id}")

    assert resp.status_code == 400, resp.content
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_cycles_maps_an_unexpected_error_to_500(caplog: pytest.LogCaptureFixture) -> None:
    _, user, workspace = _scenario()
    with patch("traceability.service.detect_cycles", side_effect=RuntimeError("boom")):
        with caplog.at_level("ERROR", logger="rest_api.views"):
            resp = _client(user).get(
                f"/api/v1/tracelinks/cycles/?workspace_id={workspace.id}"
            )

    assert resp.status_code == 500, resp.content
    assert resp.json()["error"]["code"] == "INTERNAL_SERVER_ERROR"
    assert "TraceLinkViewSet.cycles" in caplog.text
