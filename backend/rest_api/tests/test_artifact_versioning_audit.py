"""Cross-type versioning audit — every artifact type must version cleanly.

Follow-up to GH-737. That issue was a *single-type* symptom of a *systemic*
risk: ``TestService.create_test_case`` tags ``Artifact.artifact_type`` with a
sub-type suffix (``"TestCase:Unit"``), while
``ArtifactDiffService._ENTITY_FIELDS`` / ``_ENTITY_MODELS`` key on the plain
type name. The un-normalised lookup silently degraded ``/versions/`` to "only
the creation baseline exists" and made ``/diff/`` raise ``NotFoundError`` — all
while the ``version`` counter itself kept incrementing correctly, so nothing
looked broken from the write side.

This module is the regression net for the whole artifact-type surface rather
than for TestCase alone. For every type that has a create *and* an update path
it drives the real REST endpoints against a real database and asserts the two
properties GH-737 violated:

  1. after an update, ``/versions/`` lists an entry with
     ``content_available: True`` — the snapshot actually materialised, not just
     the counter,
  2. ``/diff/`` between two listed versions answers 200 instead of 404.

Three version models coexist and are asserted separately (ADR-AS-019, #213,
REQ-142, REQ-L2-TE-020):

  * **single-row** (StakeholderNeed, Requirement, ArchitectureElement,
    TestCase, Adr, Risk, Issue) — only ``v0`` (synthetic creation baseline) and
    the current lock counter are addressable,
  * **immutable version table** (GlossaryTerm, Diagram, Icd) — every listed
    version has a stored snapshot,
  * **immutable row per version / lineage** (Goal, MainGoal) — editing means
    POSTing a new version; there is deliberately no ``/diff/`` endpoint.

.. note::
   The two TestCase assertions require the GH-737 normalisation fix in
   ``ArtifactDiffService`` (``normalize_artifact_type()`` in ``diff()`` and
   ``list_versions()``). They fail on any tree that predates it — which is
   exactly what makes them regression tests.
"""
from __future__ import annotations

import uuid
from typing import Any, Callable
from uuid import UUID

import pytest
from rest_framework.test import APIClient

from application.artifact_diff_service import _ENTITY_FIELDS
from application.workspace_provisioning import provision_workspace_defaults
from auth_tenancy.models import ROLE_ADMIN, UserRole
from persistence.models import Artifact, Tenant, User
from persistence.models import Workspace as PersistenceWorkspace
from persistence.tenancy import TenantContext
from traceability.types import normalize_artifact_type

pytestmark = pytest.mark.django_db

_PASSWORD = "audit-pass-2026"


# ---------------------------------------------------------------------------
# Fixtures
#
# The suite drives the real URL routing through ``APIClient`` rather than
# ``APIRequestFactory`` + ``as_view``: the tenant context is established by
# ``auth_tenancy.rest.AuthTenancyAuthentication`` during DRF authentication, so
# a hand-attached ``request.auth_context`` leaves ``TenantContext`` unset and
# several services then fail with ``TenantContextNotSetError`` for reasons that
# have nothing to do with versioning.
# ---------------------------------------------------------------------------


@pytest.fixture
def tenant() -> Tenant:
    return Tenant.objects.create(
        name="versioning-audit", slug=f"vaudit-{uuid.uuid4().hex[:8]}"
    )


@pytest.fixture
def workspace(tenant: Tenant) -> PersistenceWorkspace:
    """A fully provisioned workspace.

    ``provision_workspace_defaults`` is the same seeding
    ``WorkspaceService.create_workspace`` performs — an ORM-only Workspace has
    no workflow definitions and every lifecycle-aware endpoint then fails.
    ``goals_enabled`` is off by default and gates the Goal/MainGoal endpoints.
    """
    TenantContext.set_tenant(tenant.id)
    try:
        ws = PersistenceWorkspace.objects.create(
            tenant=tenant,
            name="Versioning Audit WS",
            preset={"name": "standard"},
            goals_enabled=True,
        )
        provision_workspace_defaults(
            workspace_id=ws.id, tenant_id=tenant.id, requirement_preset="standard"
        )
        return ws
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def client(tenant: Tenant, workspace: PersistenceWorkspace) -> APIClient:
    """An ``APIClient`` authenticated as a workspace admin via JWT."""
    username = f"vaudit-{uuid.uuid4().hex[:8]}"
    user = User.objects.create(
        username=username, email=f"{username}@example.com", tenant=tenant
    )
    user.set_password(_PASSWORD)
    user.save(update_fields=["password"])

    TenantContext.set_tenant(tenant.id)
    try:
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=workspace, role=ROLE_ADMIN
        )
    finally:
        TenantContext.clear_tenant()

    login = APIClient().post(
        "/api/v1/auth/login/",
        {"username": username, "password": _PASSWORD},
        format="json",
    )
    assert login.status_code == 200, login.content

    authed = APIClient()
    authed.credentials(HTTP_AUTHORIZATION=f"Bearer {login.json()['token']}")
    return authed


@pytest.fixture
def root_architecture_id(client: APIClient, workspace: PersistenceWorkspace) -> str:
    """The workspace's single root ArchitectureElement.

    Invariant I5: a workspace may hold exactly one root element, so every
    further ArchitectureElement in this module must be attached below it.
    """
    response = client.post(
        "/api/v1/architecture/",
        {
            "workspace_id": str(workspace.id),
            "title": "Audit System",
            "description": "root",
        },
        format="json",
    )
    assert response.status_code == 201, response.content
    return str(response.json()["id"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _versions(client: APIClient, prefix: str, pk: str) -> Any:
    return client.get(f"/api/v1/{prefix}/{pk}/versions/")


def _diff(client: APIClient, prefix: str, pk: str, from_v: int, to_v: int) -> Any:
    return client.get(
        f"/api/v1/{prefix}/{pk}/diff/?from_version={from_v}&to_version={to_v}"
    )


def _field(diff_payload: dict[str, Any], name: str) -> dict[str, Any]:
    """Return the named field entry of a diff response."""
    return next(f for f in diff_payload["fields"] if f["name"] == name)


# ---------------------------------------------------------------------------
# Family 1 — single-row version model (ADR-AS-019 / issue #213)
#
# Only v0 (the synthetic creation baseline) and the current lock counter are
# addressable. GH-737's symptom was the *current* entry silently disappearing
# from the list while the counter kept climbing.
# ---------------------------------------------------------------------------

#: (name, url prefix, entity_type reported by /diff/, create-payload builder,
#:  patch payload, patched field name, expected value after the patch)
_SingleRowCase = tuple[str, str, str, Callable[[str, str], dict], dict, str, str]

_SINGLE_ROW_TYPES: tuple[_SingleRowCase, ...] = (
    (
        "StakeholderNeed",
        "needs",
        "StakeholderNeed",
        lambda ws, root: {"workspace_id": ws, "title": "Need A", "description": "v1"},
        {"description": "v2 need"},
        "description",
        "v2 need",
    ),
    (
        "Requirement",
        "requirements",
        "Requirement",
        lambda ws, root: {"workspace_id": ws, "title": "Req A", "description": "v1"},
        {"description": "v2 req"},
        "description",
        "v2 req",
    ),
    (
        "ArchitectureElement",
        "architecture",
        "ArchitectureElement",
        lambda ws, root: {
            "workspace_id": ws,
            "title": "Arch A",
            "description": "v1",
            "parent_id": root,
        },
        {"description": "v2 arch"},
        "description",
        "v2 arch",
    ),
    (
        "TestCase",
        "testcases",
        "TestCase",
        lambda ws, root: {"workspace_id": ws, "title": "TC A", "description": "v1"},
        {"description": "v2 tc"},
        "description",
        "v2 tc",
    ),
    (
        "Adr",
        "adrs",
        "Adr",
        lambda ws, root: {
            "workspace_id": ws,
            "title": "ADR A",
            "description": "v1",
            "context": "ctx",
        },
        {"description": "v2 adr"},
        "description",
        "v2 adr",
    ),
    (
        "Risk",
        "risks",
        "Risk",
        lambda ws, root: {"workspace_id": ws, "title": "Risk A", "description": "v1"},
        {"description": "v2 risk"},
        "description",
        "v2 risk",
    ),
    (
        "Issue",
        "issues",
        "Issue",
        lambda ws, root: {"workspace_id": ws, "title": "Issue A", "description": "v1"},
        {"description": "v2 issue"},
        "description",
        "v2 issue",
    ),
)


@pytest.mark.parametrize(
    "name,prefix,entity_type,create_payload,patch_payload,field_name,expected",
    _SINGLE_ROW_TYPES,
    ids=[case[0] for case in _SINGLE_ROW_TYPES],
)
def test_single_row_type_versions_and_diffs_after_update(
    name: str,
    prefix: str,
    entity_type: str,
    create_payload: Callable[[str, str], dict],
    patch_payload: dict[str, Any],
    field_name: str,
    expected: str,
    client: APIClient,
    workspace: PersistenceWorkspace,
    root_architecture_id: str,
) -> None:
    """GH-737 generalised: a PATCH must produce a retrievable version + diff.

    The two properties GH-737 broke for TestCase, asserted for every single-row
    type:

      * ``/versions/`` lists an entry beyond the creation baseline whose
        ``content_available`` is ``True``,
      * ``/diff/`` between the baseline and that entry answers 200 and carries
        the value written by the PATCH.
    """
    created = client.post(
        f"/api/v1/{prefix}/",
        create_payload(str(workspace.id), root_architecture_id),
        format="json",
    )
    assert created.status_code == 201, created.content
    pk = str(created.json()["id"])

    patched = client.patch(f"/api/v1/{prefix}/{pk}/", patch_payload, format="json")
    assert patched.status_code == 200, patched.content

    listed = _versions(client, prefix, pk)
    assert listed.status_code == 200, listed.content
    payload = listed.json()
    entries = {entry["version"]: entry for entry in payload}

    # v0 is the synthetic "before creation" state — diffable against, but it
    # has no stored content of its own.
    assert 0 in entries, f"{name}: creation baseline missing from {payload}"
    assert entries[0]["content_available"] is False

    # ... and the current state must be listed *and* retrievable. This is the
    # entry that silently vanished for TestCase (GH-737).
    current = [version for version in entries if version != 0]
    assert current, (
        f"{name}: /versions/ listed only the creation baseline — the current "
        f"snapshot did not materialise (GH-737 signature). Got {payload}"
    )
    to_version = max(current)
    assert entries[to_version]["content_available"] is True

    diffed = _diff(client, prefix, pk, 0, to_version)
    assert diffed.status_code == 200, diffed.content
    diff_payload = diffed.json()
    assert diff_payload["entity_type"] == entity_type
    assert _field(diff_payload, field_name)["to"] == expected


def test_testcase_versions_and_diff_survive_the_subtype_suffix(
    client: APIClient, workspace: PersistenceWorkspace
) -> None:
    """GH-737 root cause, asserted at its source rather than at its symptom.

    ``TestService.create_test_case`` writes ``Artifact.artifact_type =
    "TestCase:<test_type>"``. It is the only create service in the codebase
    that tags the column with a sub-type suffix, and the version/diff lookup
    tables key on the plain name — so the suffix has to be normalised away
    before the lookup. This pins both halves: the tag really is written, and
    the endpoints still resolve through it.
    """
    created = client.post(
        "/api/v1/testcases/",
        {"workspace_id": str(workspace.id), "title": "Suffix TC"},
        format="json",
    )
    assert created.status_code == 201, created.content
    tc_id = UUID(str(created.json()["id"]))

    TenantContext.set_tenant(workspace.tenant_id)
    try:
        from persistence.models import TestCase

        artifact_type = TestCase.objects.get(id=tc_id).artifact.artifact_type
    finally:
        TenantContext.clear_tenant()

    assert ":" in artifact_type, (
        "TestService no longer tags a sub-type suffix — if that is intentional, "
        "this test and the normalisation in ArtifactDiffService can go."
    )
    assert normalize_artifact_type(artifact_type) in _ENTITY_FIELDS

    patched = client.patch(
        f"/api/v1/testcases/{tc_id}/", {"description": "suffix-safe"}, format="json"
    )
    assert patched.status_code == 200, patched.content
    to_version = patched.json()["version"]

    listed = _versions(client, "testcases", str(tc_id))
    assert listed.status_code == 200, listed.content
    payload = listed.json()
    entries = {entry["version"]: entry for entry in payload}
    assert to_version in entries, (
        f"GH-737 regression: current version {to_version} missing from {payload}"
    )
    assert entries[to_version]["content_available"] is True

    diffed = _diff(client, "testcases", str(tc_id), 0, to_version)
    assert diffed.status_code == 200, diffed.content
    assert diffed.json()["entity_type"] == "TestCase"


def test_stored_artifact_types_all_resolve_through_normalisation(
    client: APIClient, workspace: PersistenceWorkspace, root_architecture_id: str
) -> None:
    """Every artifact-backed type must key into the diff tables after normalising.

    The structural invariant behind GH-737: whatever a create service writes
    into ``Artifact.artifact_type`` has to resolve in ``_ENTITY_FIELDS`` once
    the sub-type suffix is stripped. A newly suffixed (or renamed) artifact type
    trips this before it reaches a user-visible endpoint.
    """
    ws_id = str(workspace.id)
    for prefix, payload in (
        ("needs", {"workspace_id": ws_id, "title": "N"}),
        ("requirements", {"workspace_id": ws_id, "title": "R"}),
        (
            "architecture",
            {"workspace_id": ws_id, "title": "A", "parent_id": root_architecture_id},
        ),
        ("testcases", {"workspace_id": ws_id, "title": "T"}),
    ):
        response = client.post(f"/api/v1/{prefix}/", payload, format="json")
        assert response.status_code == 201, response.content

    TenantContext.set_tenant(workspace.tenant_id)
    try:
        stored = set(
            Artifact.objects.filter(workspace_id=workspace.id).values_list(
                "artifact_type", flat=True
            )
        )
    finally:
        TenantContext.clear_tenant()

    assert stored, "no artifacts were created"
    unresolvable = {
        raw for raw in stored if normalize_artifact_type(raw) not in _ENTITY_FIELDS
    }
    assert not unresolvable, (
        "artifact_type values that do not resolve into ArtifactDiffService's "
        f"lookup tables even after normalisation: {sorted(unresolvable)}"
    )


def test_issue_payload_exposes_the_lock_version(
    client: APIClient, workspace: PersistenceWorkspace
) -> None:
    """``version`` must be part of the Issue representation.

    ``IssueSerializer`` declares ``version`` (read-only, LOCK_VERSION_HELP_TEXT)
    — so the OpenAPI schema advertises it and the frontend ``Issue`` type
    declares it non-optional — but ``_issue_to_dict`` never supplied it. DRF
    silently drops a missing read-only field instead of erroring, so every
    Issue response shipped without the lock counter while
    ``GET /issues/{id}/versions/`` kept handing out version numbers the entity
    payload could not be correlated with. Same shape as GH-737: the counter was
    fine, the surface was silently short.
    """
    created = client.post(
        "/api/v1/issues/",
        {"workspace_id": str(workspace.id), "title": "Issue V", "description": "v1"},
        format="json",
    )
    assert created.status_code == 201, created.content
    created_payload = created.json()
    assert "version" in created_payload, f"POST response lost `version`: {created_payload}"
    pk = str(created_payload["id"])

    patched = client.patch(
        f"/api/v1/issues/{pk}/", {"description": "v2"}, format="json"
    )
    assert patched.status_code == 200, patched.content
    patched_payload = patched.json()
    assert "version" in patched_payload, (
        f"PATCH response lost `version`: {patched_payload}"
    )
    assert patched_payload["version"] > created_payload["version"]

    fetched = client.get(f"/api/v1/issues/{pk}/")
    assert fetched.status_code == 200, fetched.content
    assert fetched.json()["version"] == patched_payload["version"]

    # The version the entity reports must be one /versions/ actually addresses.
    listed = _versions(client, "issues", pk)
    assert listed.status_code == 200, listed.content
    assert fetched.json()["version"] in {
        entry["version"] for entry in listed.json()
    }


# ---------------------------------------------------------------------------
# Family 2 — real immutable version tables (REQ-142)
#
# Unlike the single-row types these keep historical snapshots, so every listed
# version must be retrievable and a v(n-1) -> v(n) diff must resolve.
# ---------------------------------------------------------------------------


def test_glossary_term_versions_and_diff(
    client: APIClient, workspace: PersistenceWorkspace
) -> None:
    """GlossaryTerm writes an ArtifactVersion row per update (Task 28b)."""
    created = client.post(
        "/api/v1/glossary/",
        {
            "workspace_id": str(workspace.id),
            "term": "Latency",
            "definition": "v1 definition",
        },
        format="json",
    )
    assert created.status_code == 201, created.content
    pk = str(created.json()["id"])

    patched = client.patch(
        f"/api/v1/glossary/{pk}/", {"definition": "v2 definition"}, format="json"
    )
    assert patched.status_code == 200, patched.content

    listed = _versions(client, "glossary", pk)
    assert listed.status_code == 200, listed.content
    payload = listed.json()
    assert len(payload) >= 2, payload
    # Task 29 (M5): /versions/ is now the same generic list for every type,
    # so it always includes the synthetic v0 creation baseline
    # (content_available: False) ahead of the real recorded revisions.
    assert all(
        entry["content_available"] for entry in payload if entry["version"] != 0
    )

    numbers = sorted(
        entry["version"] for entry in payload if entry["content_available"]
    )
    diffed = _diff(client, "glossary", pk, numbers[-2], numbers[-1])
    assert diffed.status_code == 200, diffed.content
    diff_payload = diffed.json()
    assert diff_payload["entity_type"] == "GlossaryTerm"
    definition = _field(diff_payload, "definition")
    assert definition["status"] == "modified"
    assert definition["to"] == "v2 definition"


def test_diagram_versions_and_diff(
    client: APIClient, workspace: PersistenceWorkspace
) -> None:
    """Diagram writes an immutable DiagramVersion per update (REQ-L2-DS-001)."""
    created = client.post(
        "/api/v1/diagrams/",
        {
            "workspace_id": str(workspace.id),
            "name": "Audit Diagram",
            "diagram_type": "block",
            "payload_format": "mermaid",
            "content": "graph TD; A-->B;",
        },
        format="json",
    )
    assert created.status_code == 201, created.content
    pk = str(created.json()["id"])

    patched = client.patch(
        f"/api/v1/diagrams/{pk}/",
        {"payload_format": "mermaid", "content": "graph TD; A-->C;"},
        format="json",
    )
    assert patched.status_code == 200, patched.content

    listed = _versions(client, "diagrams", pk)
    assert listed.status_code == 200, listed.content
    payload = listed.json()
    assert len(payload) >= 2, payload
    # Task 29 (M5): /versions/ is now the same generic list for every type,
    # so it always includes the synthetic v0 creation baseline
    # (content_available: False) ahead of the real recorded revisions.
    assert all(
        entry["content_available"] for entry in payload if entry["version"] != 0
    )

    numbers = sorted(
        entry["version"] for entry in payload if entry["content_available"]
    )
    diffed = _diff(client, "diagrams", pk, numbers[-2], numbers[-1])
    assert diffed.status_code == 200, diffed.content
    diff_payload = diffed.json()
    assert diff_payload["entity_type"] == "Diagram"
    diagram_payload = _field(diff_payload, "payload")
    assert diagram_payload["status"] == "modified"
    assert diagram_payload["to"] == "graph TD; A-->C;"


def test_icd_versions_and_diff(
    client: APIClient, workspace: PersistenceWorkspace, root_architecture_id: str
) -> None:
    """Icd writes an IcdVersion per update and diffs between two of them."""
    target = client.post(
        "/api/v1/architecture/",
        {
            "workspace_id": str(workspace.id),
            "title": "ICD target",
            "parent_id": root_architecture_id,
        },
        format="json",
    )
    assert target.status_code == 201, target.content

    created = client.post(
        "/api/v1/icds/",
        {
            "workspace_id": str(workspace.id),
            "name": "Audit ICD",
            "source_element_id": root_architecture_id,
            "target_element_id": str(target.json()["id"]),
            "semantic_description": "v1 contract",
        },
        format="json",
    )
    assert created.status_code == 201, created.content
    pk = str(created.json()["id"])

    patched = client.patch(
        f"/api/v1/icds/{pk}/", {"semantic_description": "v2 contract"}, format="json"
    )
    assert patched.status_code == 200, patched.content

    listed = _versions(client, "icds", pk)
    assert listed.status_code == 200, listed.content
    payload = listed.json()
    retrievable = sorted(
        entry["version"] for entry in payload if entry["content_available"]
    )
    assert len(retrievable) >= 2, payload

    diffed = _diff(client, "icds", pk, retrievable[-2], retrievable[-1])
    assert diffed.status_code == 200, diffed.content
    diff_payload = diffed.json()
    assert diff_payload["entity_type"] == "Icd"
    description = _field(diff_payload, "semantic_description")
    assert description["status"] == "modified"
    assert description["to"] == "v2 contract"


# ---------------------------------------------------------------------------
# Family 3 — immutable row per version (REQ-L2-TE-020)
#
# Goal/MainGoal are never mutated in place: PATCH is a deliberate 405 and there
# is no /diff/ endpoint. "Updating" means POSTing a new version, which must show
# up in the lineage's version list.
# ---------------------------------------------------------------------------


def test_goal_new_version_appears_in_lineage_versions(
    client: APIClient, workspace: PersistenceWorkspace
) -> None:
    """Appending a Goal version must extend the lineage's version list."""
    first = client.post(
        "/api/v1/goals/",
        {"workspace_id": str(workspace.id), "title": "Goal A", "description": "v1"},
        format="json",
    )
    assert first.status_code == 201, first.content
    first_payload = first.json()

    second = client.post(
        "/api/v1/goals/",
        {
            "workspace_id": str(workspace.id),
            "title": "Goal A",
            "description": "v2",
            "lineage_id": str(first_payload["lineage_id"]),
        },
        format="json",
    )
    assert second.status_code == 201, second.content
    second_payload = second.json()
    assert (
        second_payload["sequence_number"] == first_payload["sequence_number"] + 1
    )

    listed = _versions(client, "goals", str(second_payload["id"]))
    assert listed.status_code == 200, listed.content
    payload = listed.json()
    assert [entry["sequence_number"] for entry in payload] == [1, 2]
    assert all(entry["content_available"] is True for entry in payload)

    # In-place editing is refused on purpose — the version list is the history.
    patched = client.patch(
        f"/api/v1/goals/{second_payload['id']}/", {"description": "v3"}, format="json"
    )
    assert patched.status_code == 405, patched.content


def test_main_goal_new_version_appears_in_versions(
    client: APIClient, workspace: PersistenceWorkspace
) -> None:
    """Appending a MainGoal version must extend the workspace's version list."""
    first = client.post(
        "/api/v1/main-goals/",
        {"workspace_id": str(workspace.id), "content": "main goal v1"},
        format="json",
    )
    assert first.status_code == 201, first.content

    second = client.post(
        "/api/v1/main-goals/",
        {"workspace_id": str(workspace.id), "content": "main goal v2"},
        format="json",
    )
    assert second.status_code == 201, second.content
    second_payload = second.json()

    listed = _versions(client, "main-goals", str(second_payload["id"]))
    assert listed.status_code == 200, listed.content
    payload = listed.json()
    assert [entry["sequence_number"] for entry in payload] == [1, 2]
    assert all(entry["content_available"] is True for entry in payload)
    assert payload[-1]["content"] == "main goal v2"

    patched = client.patch(
        f"/api/v1/main-goals/{second_payload['id']}/", {"content": "v3"}, format="json"
    )
    assert patched.status_code == 405, patched.content
