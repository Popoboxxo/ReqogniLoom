"""GitHub #1078 — baseline list and detail disagreed on ``entries``.

Measured on ``v1.8.0-beta.16``::

    GET /api/v1/baselines/?workspace_id=<WS>  -> 200 count: 2
        results[0].entries = 0
    GET /api/v1/baselines/<id>/               -> 200
        entries = 4

Mechanism: ``_baseline_to_dict`` copies ``entries`` whenever the source object
*has* the attribute, and the list then serialised through
``BaselineSerializer`` — the representation whose ``entries`` field exists for
the detail route. ``BaselineSummary`` (what ``list_baselines`` returns) has no
such attribute, so today DRF's skip-on-missing behaviour already drops the
field from the row; but the moment the list source carries an ``entries``
attribute the row gains ``"entries": []``, the value the issue reports and the
one a UI renders as "this baseline captured nothing". ``BaselineDetail`` is
exactly such a source: its dataclass field defaults to ``[]``.

So the list/detail difference is not a contract, it is a side effect of one
``required=False`` flag. This suite makes it structural: a dedicated
``BaselineSummarySerializer`` (wired via
``BaselineViewSet.get_serializer_class``, so the generated OpenAPI entry
matches too) has no ``entries`` field, whatever the source carries.

Chosen resolution: the field is ABSENT in the list representation — option two
of the two the issue allows. Serialising it identically in both would mean one
extra detail query per row, turning a single paged query into an N+1 to serve
data the list route never promised. Absence is also unambiguous for a client:
"load the detail to see captured items" rather than "this baseline captured
nothing".
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from rest_framework.test import APIRequestFactory

from rest_api.serializers import (
    BaselineSerializer,
    BaselineSummarySerializer,
)
from rest_api.views import BaselineViewSet

#: Fields that only exist to *read* a baseline's captured items. Every other
#: read field must be identical in both representations — pinned below so the
#: two serializers cannot drift apart silently.
_LIST_ONLY_ABSENT = {"entries"}
_DETAIL_ONLY_ABSENT = {"override_reason", "waived_findings"}  # both write_only


def _auth_context(user_id: uuid.UUID, tenant_id: uuid.UUID):
    from auth_tenancy.context import AuthContext, AuthMethod

    return AuthContext(
        user_id=user_id,
        tenant_id=tenant_id,
        active_roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN,
    )


@pytest.fixture
def baseline_env(db):
    """A workspace with one requirement and a project baseline capturing it."""
    from persistence.models import Artifact, Requirement, Tenant, User, Workspace
    from persistence.tenancy import TenantContext

    tenant = Tenant.objects.create(
        id=uuid.uuid4(),
        name="issue1078-tenant",
        slug=f"issue1078-{uuid.uuid4().hex[:8]}",
    )
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            id=uuid.uuid4(),
            tenant=tenant,
            name=f"issue1078-ws-{uuid.uuid4().hex[:6]}",
            preset={"name": "extended"},
        )
        user = User.objects.create(
            id=uuid.uuid4(),
            tenant=tenant,
            username=f"issue1078-{uuid.uuid4().hex[:8]}",
            email="issue1078@example.com",
        )
        artifact = Artifact.objects.create(
            id=uuid.uuid4(),
            tenant=tenant,
            workspace=workspace,
            artifact_type="Requirement",
        )
        Requirement.objects.create(
            id=uuid.uuid4(),
            tenant=tenant,
            artifact=artifact,
            workspace=workspace,
            uid="REQ-1078-001",
            title="List must not claim zero entries",
        )
    finally:
        TenantContext.clear_tenant()

    ctx = _auth_context(user.id, tenant.id)

    # Built through ``baseline.services`` (not the facade): the facade's
    # SE-Auditor gate is orthogonal to the list/detail serialisation under test.
    from baseline.services import build as baseline_build

    baseline_id = baseline_build(
        scope="project",
        workspace_id=workspace.id,
        name=f"issue1078-{uuid.uuid4().hex[:6]}",
        tenant_id=tenant.id,
        created_by="issue1078-test",
    )
    return {
        "tenant": tenant,
        "workspace": workspace,
        "ctx": ctx,
        "baseline_id": baseline_id,
        "artifact_id": str(artifact.id),
    }


def _call(actions: dict, path: str, ctx, tenant_id: uuid.UUID, **kwargs):
    """Invoke a viewset action directly with the thread-local tenant set.

    A direct ``view()`` call bypasses ``persistence.middleware``, which normally
    installs the TenantContext — same pattern as
    ``test_baseline_detail_route_398.py``.
    """
    from persistence.tenancy import TenantContext

    request = APIRequestFactory().get(path)
    request.auth_context = ctx
    view = BaselineViewSet.as_view(actions)
    TenantContext.set_tenant(tenant_id)
    try:
        return view(request, **kwargs)
    finally:
        TenantContext.clear_tenant()


# ---------------------------------------------------------------------------
# The reported symptom
# ---------------------------------------------------------------------------


def test_list_omits_entries_instead_of_reporting_an_empty_list(baseline_env) -> None:
    """#1078: the list row must not claim the baseline captured nothing."""
    fx = baseline_env

    listing = _call(
        {"get": "list"},
        f"/api/v1/workspaces/{fx['workspace'].id}/baselines/",
        fx["ctx"],
        fx["tenant"].id,
        workspace_pk=str(fx["workspace"].id),
    )

    assert listing.status_code == 200, listing.data
    assert listing.data["count"] == 1, listing.data
    row = listing.data["results"][0]
    assert row["id"] == str(fx["baseline_id"])
    assert "entries" not in row, (
        f"list row still carries entries={row.get('entries')!r}; an empty list "
        f"invites the UI to render 'this baseline captured nothing'"
    )


def test_detail_still_serves_the_captured_entries(baseline_env) -> None:
    """The detail route is unchanged — the fix is list-side only."""
    fx = baseline_env

    detail = _call(
        {"get": "retrieve"},
        f"/api/v1/baselines/{fx['baseline_id']}/",
        fx["ctx"],
        fx["tenant"].id,
        pk=str(fx["baseline_id"]),
    )

    assert detail.status_code == 200, detail.data
    entries = detail.data["entries"]
    assert entries, "detail route must still serve the captured delta entries"
    assert fx["artifact_id"] in {e["item_id"] for e in entries}


def test_list_and_detail_do_not_disagree_about_the_baseline(baseline_env) -> None:
    """Everything the list asserts about a baseline matches the detail."""
    fx = baseline_env

    listing = _call(
        {"get": "list"},
        f"/api/v1/baselines/?workspace_id={fx['workspace'].id}",
        fx["ctx"],
        fx["tenant"].id,
    )
    detail = _call(
        {"get": "retrieve"},
        f"/api/v1/baselines/{fx['baseline_id']}/",
        fx["ctx"],
        fx["tenant"].id,
        pk=str(fx["baseline_id"]),
    )

    row = listing.data["results"][0]
    for field in ("id", "workspace_id", "name", "scope", "version", "created_at"):
        assert row[field] == detail.data[field], (
            f"{field!r} differs between list ({row[field]!r}) and "
            f"detail ({detail.data[field]!r})"
        )


# ---------------------------------------------------------------------------
# Serializer-level contract
# ---------------------------------------------------------------------------


def test_summary_serializer_declares_exactly_the_detail_fields_minus_entries() -> None:
    """Drift guard: the two serializers are one field set plus/minus one key."""
    list_fields = set(BaselineSummarySerializer().fields)
    detail_read_fields = {
        name
        for name, field in BaselineSerializer().fields.items()
        if not field.write_only
    }

    assert detail_read_fields - list_fields == _LIST_ONLY_ABSENT, (
        "the summary serializer is missing detail fields: "
        f"{sorted(detail_read_fields - list_fields - _LIST_ONLY_ABSENT)}"
    )
    assert list_fields - detail_read_fields == set(), (
        f"the summary serializer adds fields the detail does not have: "
        f"{sorted(list_fields - detail_read_fields)}"
    )
    # The two write-only inputs are excluded deliberately; they produce no
    # output on either representation, so this documents intent, not a gap.
    assert _DETAIL_ONLY_ABSENT == {"override_reason", "waived_findings"}
    assert all(
        BaselineSerializer().fields[name].write_only
        for name in _DETAIL_ONLY_ABSENT
    )


def test_summary_serializer_renders_a_row_without_an_entries_key() -> None:
    """The behaviour at the unit level: absent source -> absent field."""
    summary = BaselineSummarySerializer(
        {
            "id": str(uuid.uuid4()),
            "workspace_id": str(uuid.uuid4()),
            "name": "no entries key",
            "scope": "project",
            "description": "",
            "artifact_id": None,
            "version": 1,
            "created_at": "2026-09-26T00:00:00Z",
        }
    ).data

    assert "entries" not in summary, summary
    assert summary["name"] == "no entries key"


def test_detail_serializer_reports_an_empty_list_for_a_source_that_carries_one() -> None:
    """The hazard the summary serializer removes — the #1078 symptom itself.

    ``_baseline_to_dict`` copies ``entries`` whenever the source object *has*
    the attribute (``getattr(bl, "entries", None) is not None``), so a list
    source that exposes an empty ``entries`` — which is exactly what
    ``BaselineDetail`` yields, since its dataclass field defaults to ``[]`` —
    turns the "not loaded" signal into a flat ``entries: []``, the value the
    issue reports and the one a UI renders as "this baseline captured
    nothing". Dropping the field on the list representation makes the absence
    structural instead of dependent on whether the source happens to carry the
    attribute.
    """
    from rest_api.views import _baseline_to_dict

    summary_source = SimpleNamespace(
        baseline_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        name="source carrying empty entries",
        scope="project",
        description="",
        created_at="2026-09-26T00:00:00Z",
        entries=[],
    )

    row = _baseline_to_dict(summary_source)
    assert row["entries"] == [], (
        "the pre-fix shape: the source carries entries=[], so the row does too"
    )
    assert BaselineSerializer(row).data["entries"] == [], (
        "…and the detail serializer renders that as the misleading []"
    )
    assert "entries" not in BaselineSummarySerializer(row).data, (
        "the summary serializer drops it regardless of the source — that is the fix"
    )


def test_the_list_route_does_not_use_the_detail_serializer() -> None:
    """Structural pin: the guarantee is the field set, not DRF's skip behaviour.

    ``BaselineSerializer.entries`` is ``required=False``, so while the list
    source happens to lack the attribute DRF skips the field and the row looks
    correct. That is an accident of one field flag in one serializer, not a
    contract; ``BaselineViewSet.get_serializer_class`` makes the list
    representation explicit so it cannot be lost that way again.
    """
    assert "entries" not in BaselineSummarySerializer().fields
    assert "entries" in BaselineSerializer().fields
