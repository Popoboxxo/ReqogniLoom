"""Issue #271: ``Workspace.preset`` serialises in three different shapes.

Depending on when and how a workspace was created, the stored JSON blob is one
of:

  * ``{"tier": "standard", ...}``          — WorkspaceService.create
  * ``{"tier": "x", "name": "x", ...}``    — WorkspaceService.switch_preset_tier
  * ``{"name": "extended"}``               — legacy/seeded rows (e.g. Demo),
                                             written before "tier" existed

``WorkspaceSerializer.preset`` was a passthrough ``JSONField``, so all three
reached the client verbatim and the frontend had to guess (see
``frontend/src/context/WorkspaceContext.tsx``, which reads ``.tier`` with a
``.name`` fallback).

The fix normalises on READ only — no data migration, so no destructive
in-place rewrite of stored blobs for a low-priority hygiene issue.
"""
from __future__ import annotations

import uuid

import pytest
from rest_framework.test import APIRequestFactory

from persistence.models import Tenant, Workspace
from persistence.tenancy import TenantContext
from rest_api.serializers import WorkspaceSerializer, normalize_preset_blob
from rest_api.views import WorkspaceViewSet

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# The normalisation helper
# ---------------------------------------------------------------------------


def test_legacy_name_only_blob_gains_a_tier():
    """The Demo workspace shape — seeded before "tier" existed."""
    assert normalize_preset_blob({"name": "extended"}) == {
        "name": "extended",
        "tier": "extended",
    }


def test_create_shape_tier_only_blob_gains_a_name():
    assert normalize_preset_blob({"tier": "standard"}) == {
        "name": "standard",
        "tier": "standard",
    }


def test_switch_preset_tier_shape_is_already_canonical():
    blob = {"tier": "minimal", "name": "minimal"}

    assert normalize_preset_blob(blob) == {"tier": "minimal", "name": "minimal"}


def test_tier_wins_when_the_two_keys_disagree():
    """``switch_preset_tier`` is the only writer of both; ``tier`` is authoritative."""
    result = normalize_preset_blob({"tier": "extended", "name": "standard"})

    assert result["tier"] == "extended"
    assert result["name"] == "extended"


def test_unrelated_keys_are_preserved():
    """``language`` and ``terminology_profile`` also live in this blob."""
    result = normalize_preset_blob(
        {"name": "extended", "language": "de", "terminology_profile": "se_mode"}
    )

    assert result["language"] == "de"
    assert result["terminology_profile"] == "se_mode"
    assert result["tier"] == "extended"


def test_empty_blob_is_not_given_a_fabricated_tier():
    """Inventing a tier would mislabel the workspace — leave the gap visible."""
    assert normalize_preset_blob({}) == {}


def test_none_blob_becomes_an_empty_dict():
    assert normalize_preset_blob(None) == {}


def test_normalisation_does_not_mutate_the_input():
    """Read-path only: the caller's (possibly ORM-attached) dict stays untouched."""
    original = {"name": "extended"}

    normalize_preset_blob(original)

    assert original == {"name": "extended"}


def test_non_dict_blob_is_tolerated():
    """Defensive: a corrupt row must not 500 the whole workspace list."""
    assert normalize_preset_blob("extended") == {}
    assert normalize_preset_blob(["extended"]) == {}


# ---------------------------------------------------------------------------
# The serializer applies it
# ---------------------------------------------------------------------------


def _payload(preset):
    return {
        "id": str(uuid.uuid4()),
        "name": "WS",
        "preset": preset,
        "version": 1,
    }


@pytest.mark.parametrize(
    "stored",
    [
        {"name": "extended"},
        {"tier": "extended"},
        {"tier": "extended", "name": "extended"},
    ],
)
def test_serializer_emits_one_shape_for_all_three_stored_shapes(stored):
    data = WorkspaceSerializer(_payload(stored)).data

    assert data["preset"]["tier"] == "extended"
    assert data["preset"]["name"] == "extended"


# ---------------------------------------------------------------------------
# End-to-end through the ViewSet, with a real legacy-shaped row
# ---------------------------------------------------------------------------


def _make_auth_context(*, tenant_id):
    from auth_tenancy.context import AuthContext, AuthMethod

    return AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=tenant_id,
        active_roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN,
    )


def _legacy_workspace():
    """A workspace whose preset blob only has the pre-"tier" ``name`` key."""
    tenant = Tenant.objects.create(name="LegacyPresetTenant")
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="Demo", preset={"name": "extended"}
        )
    finally:
        TenantContext.clear_tenant()
    return tenant, workspace


def test_retrieve_normalises_a_legacy_seeded_workspace():
    tenant, workspace = _legacy_workspace()

    req = APIRequestFactory().get(f"/api/v1/workspaces/{workspace.id}/")
    req.auth_context = _make_auth_context(tenant_id=tenant.id)
    response = WorkspaceViewSet.as_view({"get": "retrieve"})(req, pk=str(workspace.id))

    assert response.status_code == 200
    assert response.data["preset"]["tier"] == "extended"
    assert response.data["preset"]["name"] == "extended"


def test_normalisation_is_read_only_and_leaves_the_row_alone():
    """No blind mutation of stored data — the DB blob keeps its legacy shape."""
    tenant, workspace = _legacy_workspace()

    req = APIRequestFactory().get(f"/api/v1/workspaces/{workspace.id}/")
    req.auth_context = _make_auth_context(tenant_id=tenant.id)
    WorkspaceViewSet.as_view({"get": "retrieve"})(req, pk=str(workspace.id))

    TenantContext.set_tenant(tenant.id)
    try:
        workspace.refresh_from_db()
    finally:
        TenantContext.clear_tenant()
    assert workspace.preset == {"name": "extended"}


def test_list_normalises_every_row():
    tenant, workspace = _legacy_workspace()

    req = APIRequestFactory().get("/api/v1/workspaces/")
    req.auth_context = _make_auth_context(tenant_id=tenant.id)
    response = WorkspaceViewSet.as_view({"get": "list"})(req)

    assert response.status_code == 200
    results = response.data["results"]
    assert results, "expected at least the legacy workspace"
    for row in results:
        if row["preset"]:
            assert "tier" in row["preset"] and "name" in row["preset"]
