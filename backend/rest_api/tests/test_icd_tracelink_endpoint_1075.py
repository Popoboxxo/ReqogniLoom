"""An Icd is a first-class TraceLink endpoint, and it publishes its Artifact id (#1075).

``icd_icd`` and ``pl_artifact`` are two rows with two different primary keys, and
so is every other specialised artifact table. The client reads one id space
(``GET /icds/{id}/`` -> ``id``) while the trace graph stores the other
(``pl_artifact``). ``TraceLinkService._resolve_artifact`` bridged the two for a
hand-maintained list of ten types; ``Icd`` was not on it, so
``POST /tracelinks/`` answered **404 for an entity that demonstrably exists**
(95 ``icd_icd`` rows, 0 of their UUIDs present in ``pl_artifact``).

These tests pin the fix end to end, i.e. through the real HTTP stack:

* a link whose endpoint is an Icd id is created (201) and stored under the
  Icd's *backing* ``artifact_id`` — the id space links live in;
* both ends of an Icd-to-Icd link resolve, so Icd works as source *and* target;
* a link that already lives in the Artifact id space keeps its stored ids
  byte-for-byte (the resolver must not move existing links);
* an unknown uuid still 404s (the registry fallback must not over-resolve);
* the ICD list and detail responses publish ``artifact_id``, without which a
  client cannot obtain the correct uuid at all.
"""
from __future__ import annotations

import uuid

import pytest

from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Artifact, TraceLink

pytestmark = pytest.mark.django_db

#: ``references`` is the one built-in whose catalog carries ``("*", "Icd")``
#: (link_types/builtin.py), so an Icd is a legal endpoint without inventing a
#: link type. ``("*", "Icd")`` on the wildcard source side also admits Icd->Icd.
_LINK_TYPE = "references"


@pytest.fixture
def make_icd(tenant, workspace):
    """Factory for an Icd row with its own backing Artifact row.

    Built at the ORM level on purpose: the point of these tests is the id
    mapping, not the create endpoint, and ``icd_manager.create_icd`` would add
    its own ``decomposes`` TraceLink as noise.
    """

    def _make(name: str = "Power Bus ICD"):
        set_request_tenant(tenant.id)
        try:
            artifact = Artifact.objects.create(
                tenant=tenant, workspace=workspace, artifact_type="Icd"
            )
            from icd.models import Icd

            icd = Icd.objects.create(
                tenant=tenant,
                artifact=artifact,
                workspace_id=workspace.id,
                name=name,
                source_element_id=uuid.uuid4(),
                target_element_id=uuid.uuid4(),
            )
            assert icd.id != icd.artifact_id, (
                "fixture is wrong: the two id spaces must be distinct or the "
                "regression under test cannot be observed"
            )
            return icd
        finally:
            clear_request_tenant()

    return _make


def _create_requirement(client, workspace_id, title: str) -> dict:
    resp = client.post(
        "/api/v1/requirements/",
        {"workspace_id": str(workspace_id), "title": title},
        format="json",
    )
    assert resp.status_code == 201, resp.content
    return resp.json()


def test_a_link_against_an_icd_id_is_created_and_stored_under_the_artifact_id(
    authed_client, workspace, make_icd
) -> None:
    """#1075: the reported 404 -> 201, stored in the Artifact id space."""
    requirement = _create_requirement(authed_client, workspace.id, "L1 power req")
    icd = make_icd()

    # The id the client actually holds: the one GET /icds/{id}/ returned.
    response = authed_client.get(f"/api/v1/icds/{icd.id}/")
    assert response.status_code == 200, response.content
    icd_body = response.json()

    created = authed_client.post(
        "/api/v1/tracelinks/",
        {
            "source_id": requirement["id"],
            "target_id": icd_body["id"],
            "link_type": _LINK_TYPE,
        },
        format="json",
    )

    assert created.status_code == 201, created.content
    link = created.json()
    assert link["source_id"] == requirement["artifact_id"]
    assert link["target_id"] == icd_body["artifact_id"]
    # And the target really is the Icd's *own* row that was resolved, not some
    # other artifact that happened to share the uuid.
    assert link["target_id"] != icd_body["id"]


def test_an_icd_resolves_as_source_and_as_target(authed_client, make_icd) -> None:
    """The fallback reads each subtype's own ``id``, so both ends work."""
    source_icd = make_icd("Producer ICD")
    target_icd = make_icd("Consumer ICD")

    created = authed_client.post(
        "/api/v1/tracelinks/",
        {
            "source_id": str(source_icd.id),
            "target_id": str(target_icd.id),
            "link_type": _LINK_TYPE,
        },
        format="json",
    )

    assert created.status_code == 201, created.content
    link = created.json()
    assert link["source_id"] == str(source_icd.artifact_id)
    assert link["target_id"] == str(target_icd.artifact_id)


def test_a_pre_existing_artifact_based_link_keeps_its_stored_ids(
    authed_client, tenant, workspace
) -> None:
    """The 1982 existing links are all in the Artifact id space already.

    Step 1 of the resolver (``pl_artifact`` probe) is deliberately untouched, so
    an id that IS an artifact id keeps resolving to itself and no stored
    endpoint moves.
    """
    set_request_tenant(tenant.id)
    try:
        source = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="Requirement"
        )
        target = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="Requirement"
        )
        existing = TraceLink.objects.create(
            tenant=tenant, source=source, target=target, link_type="decomposes"
        )
    finally:
        clear_request_tenant()

    listed = authed_client.get(
        f"/api/v1/tracelinks/?workspace_id={workspace.id}"
    ).json()["results"]

    assert len(listed) == 1, listed
    assert listed[0]["id"] == str(existing.id)
    assert listed[0]["source_id"] == str(source.id)
    assert listed[0]["target_id"] == str(target.id)


def test_an_unknown_uuid_still_404s_rather_than_resolving(authed_client) -> None:
    """The registry probe is a fallback, not a blanket 200."""
    response = authed_client.post(
        "/api/v1/tracelinks/",
        {
            "source_id": str(uuid.uuid4()),
            "target_id": str(uuid.uuid4()),
            "link_type": _LINK_TYPE,
        },
        format="json",
    )

    assert response.status_code == 404, response.content


def test_icd_detail_and_list_publish_the_artifact_id(
    authed_client, workspace, make_icd
) -> None:
    """Without ``artifact_id`` a client cannot obtain the correct uuid at all.

    Both response sites are hand-built dicts (``_icd_to_dict`` for the list path,
    ``retrieve`` for the detail path) with no shared serializer, so they have to
    be pinned separately.
    """
    icd = make_icd("Bus Contract")

    detail = authed_client.get(f"/api/v1/icds/{icd.id}/")
    assert detail.status_code == 200, detail.content
    assert detail.json()["artifact_id"] == str(icd.artifact_id)
    assert detail.json()["artifact_id"] != detail.json()["id"]

    listed = authed_client.get(f"/api/v1/icds/?workspace_id={workspace.id}").json()
    rows = listed["results"] if isinstance(listed, dict) else listed
    assert len(rows) == 1, listed
    assert rows[0]["artifact_id"] == str(icd.artifact_id)
    assert rows[0]["artifact_id"] != rows[0]["id"]
