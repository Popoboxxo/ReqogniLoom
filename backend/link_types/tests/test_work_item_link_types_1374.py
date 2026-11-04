"""WorkItem link types (Plan F, F3-T3, #1374).

Spec: ``docs/superpowers/specs/Archive/2026-11-02-f3-workitem-design.md`` §5 (Link-Fabric)
and plan F §WP F3. A ``WorkItem`` is a first-class artifact, so two shipped link
types gain a pair instead of a new key:

* ``decomposes`` — ``Document -> WorkItem`` and ``WorkItem -> WorkItem``;
* ``references`` — ``WorkItem -> *``.

``depends-on`` already ships ``WorkItem -> WorkItem`` since F2, so it needs no
pair extension here (asserted below: exactly one pair, no duplicate).

Two groups of tests live here:

* pair validation against a provisioned workspace (the catalog contract), and
  the G-1/G-2 link context: a catalog-valid ``references`` link is what turns
  the G-2 document gate green;
* the seed migration ``0015_merge_work_item_pairs``, exercised through the real
  ``MigrationExecutor`` with migration *names* (never bare numbers) and real
  ``Workspace`` rows created *before* the migration runs — a catalog addition
  must reach an existing workspace, not only a freshly provisioned one
  (KA-G-10). The reverse refuses to orphan a link that relies on a merged pair.

Membership, never a pinned total (KA-F-07): the catalog grows with the plan
series, so no test here counts the built-in set.
"""
from __future__ import annotations

import importlib
import uuid
from contextlib import contextmanager

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from link_types.builtin import BUILTIN_LINK_TYPES
from link_types.catalog import validate_link_pair
from link_types.migrations import _seed_helpers
from link_types.models import WorkspaceLinkTypeDefinition
from persistence.errors import ValidationError
from persistence.models import (
    Artifact,
    Document,
    Tenant,
    TraceLink,
    WorkItem,
)
from persistence.tenancy import TenantContext
from persistence.tests.factories import make_workspace

pytestmark = pytest.mark.django_db

# ``from link_types.migrations.0015_... import ...`` is a syntax error; the
# module is loaded by name, like the other data-migration tests.
_MIGRATION = importlib.import_module(
    "link_types.migrations.0015_merge_work_item_pairs"
)
MIGRATION_MERGED_PAIRS = _MIGRATION.MERGED_PAIRS

_LINK_TYPES_APP = "link_types"
_PRE_TARGET = (_LINK_TYPES_APP, "0014_seed_document_link_types")
_SEED = (_LINK_TYPES_APP, "0015_merge_work_item_pairs")

_DECOMPOSES_PAIRS = {
    ("Document", "WorkItem"),
    ("WorkItem", "WorkItem"),
}
_REFERENCES_PAIRS = {("WorkItem", "*")}

_RELEASE_STATE = "Freigegeben"


def _pairs(definition: dict) -> list[tuple[str, str]]:
    return [
        (pair["source_type"], pair["target_type"])
        for pair in definition["allowed_pairs"]
    ]


@contextmanager
def _tenant_scope(tenant_id):
    TenantContext.set_tenant(tenant_id)
    try:
        yield
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def env(db):
    """Tenant + provisioned workspace (real rows; ``make_workspace`` seeds the catalog)."""
    tenant = Tenant.objects.create(
        name="work-item-linktypes", slug=f"work-item-lt-{uuid.uuid4().hex[:8]}"
    )
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = make_workspace(tenant, name="work-item-linktypes-ws")
        yield {"tenant": tenant, "workspace": workspace}
    finally:
        TenantContext.clear_tenant()


# ---------------------------------------------------------------------------
# Built-in definitions
# ---------------------------------------------------------------------------


def test_decomposes_gained_both_work_item_pairs():
    pairs = _pairs(BUILTIN_LINK_TYPES["decomposes"])
    assert _DECOMPOSES_PAIRS <= set(pairs)
    # Additive: the shipped Requirement/ArchitectureElement pairs are untouched.
    assert ("Requirement", "Requirement") in pairs
    assert ("ArchitectureElement", "ArchitectureElement") in pairs
    # No duplicate entry, whatever the append order was.
    assert len(pairs) == len(set(pairs))


def test_references_gained_work_item_as_source():
    pairs = _pairs(BUILTIN_LINK_TYPES["references"])
    assert _REFERENCES_PAIRS <= set(pairs)
    # The target side is deliberately not extended: ``*`` covers everything.
    assert ("*", "WorkItem") not in pairs
    assert len(pairs) == len(set(pairs))


def test_depends_on_needed_no_extension():
    """F2 already shipped the WorkItem pair — F3 must not duplicate it."""
    definition = BUILTIN_LINK_TYPES["depends-on"]
    assert _pairs(definition) == [("WorkItem", "WorkItem")]


def test_migration_pins_exactly_the_builtin_pairs_it_merges():
    """The migration's pinned pairs match the live built-ins (no drift)."""
    for key, wanted in MIGRATION_MERGED_PAIRS.items():
        assert set(_pairs(BUILTIN_LINK_TYPES[key])) >= {
            (pair["source_type"], pair["target_type"]) for pair in wanted
        }, key


# ---------------------------------------------------------------------------
# Pair validation against a provisioned workspace
# ---------------------------------------------------------------------------


def test_decomposes_accepts_document_to_work_item(env):
    validate_link_pair(
        env["workspace"].id, "decomposes", "Document", "WorkItem", manual=True
    )


def test_decomposes_accepts_a_document_subtype_as_source(env):
    """The untagged pair keeps matching every ``Document:<kind>`` (expand)."""
    validate_link_pair(
        env["workspace"].id, "decomposes", "Document:spec", "WorkItem", manual=True
    )


def test_decomposes_accepts_work_item_to_work_item(env):
    validate_link_pair(
        env["workspace"].id, "decomposes", "WorkItem", "WorkItem", manual=True
    )


def test_decomposes_still_accepts_the_shipped_pairs(env):
    validate_link_pair(
        env["workspace"].id, "decomposes", "Requirement", "Requirement", manual=True
    )
    validate_link_pair(
        env["workspace"].id,
        "decomposes",
        "ArchitectureElement",
        "ArchitectureElement",
        manual=True,
    )


def test_decomposes_rejects_the_reversed_work_item_pair(env):
    with pytest.raises(ValidationError, match="Allowed:"):
        validate_link_pair(
            env["workspace"].id, "decomposes", "WorkItem", "Document", manual=True
        )


def test_references_accepts_a_work_item_source(env):
    validate_link_pair(
        env["workspace"].id, "references", "WorkItem", "Requirement", manual=True
    )
    validate_link_pair(
        env["workspace"].id, "references", "WorkItem", "Document", manual=True
    )
    validate_link_pair(
        env["workspace"].id, "references", "WorkItem", "WorkItem", manual=True
    )


def test_references_rejects_work_item_as_target_only(env):
    """``WorkItem -> *`` does not make WorkItem a target of every source."""
    with pytest.raises(ValidationError, match="Allowed:"):
        validate_link_pair(
            env["workspace"].id, "references", "Requirement", "WorkItem", manual=True
        )


def test_depends_on_accepts_work_item_to_work_item(env):
    validate_link_pair(
        env["workspace"].id, "depends-on", "WorkItem", "WorkItem", manual=True
    )


# ---------------------------------------------------------------------------
# G-1 / G-2 in the link context
# ---------------------------------------------------------------------------


def _document(tenant, workspace, **overrides) -> Document:
    data = {
        "tenant": tenant,
        "title": "Work item plan",
        "kind": Document.Kind.PLAN,
        "body": "## Plan\n\nWork state.",
    }
    data.update(overrides)
    with _tenant_scope(tenant.id):
        data.setdefault(
            "artifact",
            Artifact.objects.create(
                tenant=tenant, workspace=workspace, artifact_type="Document"
            ),
        )
        return Document.objects.create(**data)


def _work_item(tenant, workspace, document, *, kind=None, **overrides) -> WorkItem:
    data = {
        "tenant": tenant,
        "document": document,
        "kind": kind or WorkItem.Kind.STEP,
        "ordinal": 1,
        "title": "Step 1",
    }
    data.update(overrides)
    with _tenant_scope(tenant.id):
        data.setdefault(
            "artifact",
            Artifact.objects.create(
                tenant=tenant, workspace=workspace, artifact_type="WorkItem"
            ),
        )
        return WorkItem.objects.create(**data)


def _gate_details(tenant, workspace, document):
    from workflow.precondition_rules import check_document_gates

    with _tenant_scope(tenant.id):
        violation = check_document_gates(
            workspace_id=str(workspace.id),
            item_type="Document",
            item_id=document.pk,
            target_state=_RELEASE_STATE,
        )
    if violation is None:
        return set()
    return {entry["gate"] for entry in violation[2]}


def _seed_document_workflow(tenant, workspace) -> None:
    from workflow.services import create_default_workflow

    with _tenant_scope(tenant.id):
        create_default_workflow(
            workspace_id=workspace.id,
            preset="document_default",
            item_type="Document",
            tenant_id=tenant.id,
        )


def test_g2_is_fail_closed_until_a_catalog_valid_link_exists(env):
    """The gate reads trace links; only a *catalog-valid* link can satisfy it."""
    tenant, workspace = env["tenant"], env["workspace"]
    _seed_document_workflow(tenant, workspace)
    document = _document(tenant, workspace)
    item = _work_item(tenant, workspace, document)

    assert "G-2" in _gate_details(tenant, workspace, document)

    from application.trace_link_service import TraceLinkService
    from auth_tenancy.context import AuthContext, AuthMethod

    ctx = AuthContext(
        user_id=None,
        tenant_id=tenant.id,
        active_roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN,
        workspace_id=workspace.id,
    )
    with _tenant_scope(tenant.id):
        requirement_artifact = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="Requirement"
        )

    # ``WorkItem -> Requirement`` is only legal because of the F3-T3 pair, and
    # the service validates it against the workspace catalog.
    with _tenant_scope(tenant.id):
        TraceLinkService().create_trace_link(
            item.artifact_id, requirement_artifact.id, "references", ctx
        )

    assert "G-2" not in _gate_details(tenant, workspace, document)


# ---------------------------------------------------------------------------
# Seed migration 0015_merge_work_item_pairs
# ---------------------------------------------------------------------------

_OLD_DECOMPOSES_PAIRS = [
    {"source_type": "Requirement", "target_type": "Requirement"},
    {"source_type": "ArchitectureElement", "target_type": "ArchitectureElement"},
]
_OLD_REFERENCES_PAIRS = [
    {"source_type": "*", "target_type": "GlossaryTerm"},
    {"source_type": "Document", "target_type": "*"},
]


def _pair_set(pairs: list[dict]) -> set[tuple[str, str]]:
    return {(pair["source_type"], pair["target_type"]) for pair in pairs}


def _seeded_rows(tenant_id: uuid.UUID, workspace_id: uuid.UUID) -> int:
    """Count this tenant's merged-key rows in *workspace_id*."""
    return WorkspaceLinkTypeDefinition.unscoped.filter(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        key__in=MIGRATION_MERGED_PAIRS,
    ).count()


@pytest.mark.django_db(transaction=True)
def test_migration_merges_work_item_pairs_on_existing_workspace() -> None:
    """0014 -> 0015 merges additively into global + non-customized rows."""
    executor = MigrationExecutor(connection)
    latest_target = executor.loader.graph.leaf_nodes()

    try:
        executor.migrate([_PRE_TARGET])
        executor.loader.build_graph()
        historical = executor.loader.project_state([_PRE_TARGET]).apps
        TenantModel = historical.get_model("persistence", "Tenant")
        WorkspaceModel = historical.get_model("persistence", "Workspace")
        GlobalDefinition = historical.get_model(
            _LINK_TYPES_APP, "GlobalLinkTypeDefinition"
        )
        WorkspaceDefinition = historical.get_model(
            _LINK_TYPES_APP, "WorkspaceLinkTypeDefinition"
        )

        tenant = TenantModel.objects.create(
            name="work-item-1374", slug=f"work-item-{uuid.uuid4().hex[:8]}"
        )
        # Real workspace rows created *before* the migration runs (KA-G-10).
        workspace_row = WorkspaceModel.objects.create(
            tenant_id=tenant.id, name="pre-existing-ws"
        )
        customized_ws = WorkspaceModel.objects.create(
            tenant_id=tenant.id, name="customized-ws"
        )

        # Pre-0015 state of the definitions this migration extends.
        for key, pairs in (
            ("decomposes", _OLD_DECOMPOSES_PAIRS),
            ("references", _OLD_REFERENCES_PAIRS),
        ):
            GlobalDefinition.objects.create(
                tenant_id=tenant.id,
                key=key,
                definition_json={"allowed_pairs": list(pairs)},
            )
            WorkspaceDefinition.objects.create(
                tenant_id=tenant.id,
                workspace_id=workspace_row.id,
                key=key,
                definition_json={"allowed_pairs": list(pairs)},
                is_customized=False,
            )

        # A workspace that tailored ``decomposes`` made a decision; the seed
        # must neither overwrite it nor add a second row for that key.
        customized = WorkspaceDefinition.objects.create(
            tenant_id=tenant.id,
            workspace_id=customized_ws.id,
            key="decomposes",
            definition_json={"allowed_pairs": list(_OLD_DECOMPOSES_PAIRS)},
            is_customized=True,
        )

        executor.migrate([_SEED])
        executor.loader.build_graph()
        seeded_apps = executor.loader.project_state([_SEED]).apps
        SeededGlobalDefinition = seeded_apps.get_model(
            _LINK_TYPES_APP, "GlobalLinkTypeDefinition"
        )
        SeededWorkspaceDefinition = seeded_apps.get_model(
            _LINK_TYPES_APP, "WorkspaceLinkTypeDefinition"
        )

        # Global templates: additive, duplicate-free merge.
        global_decomposes = SeededGlobalDefinition.objects.get(
            tenant_id=tenant.id, key="decomposes"
        )
        global_references = SeededGlobalDefinition.objects.get(
            tenant_id=tenant.id, key="references"
        )
        assert _pair_set(global_decomposes.definition_json["allowed_pairs"]) == (
            _pair_set(_OLD_DECOMPOSES_PAIRS) | _DECOMPOSES_PAIRS
        )
        assert _pair_set(global_references.definition_json["allowed_pairs"]) == (
            _pair_set(_OLD_REFERENCES_PAIRS) | _REFERENCES_PAIRS
        )
        for row in (global_decomposes, global_references):
            pairs = _pairs(row.definition_json)
            assert len(pairs) == len(set(pairs))

        # The non-customized workspace copy is merged too.
        workspace_decomposes = SeededWorkspaceDefinition.objects.get(
            tenant_id=tenant.id, workspace_id=workspace_row.id, key="decomposes"
        )
        workspace_references = SeededWorkspaceDefinition.objects.get(
            tenant_id=tenant.id, workspace_id=workspace_row.id, key="references"
        )
        assert _DECOMPOSES_PAIRS <= set(
            _pairs(workspace_decomposes.definition_json)
        )
        assert _REFERENCES_PAIRS <= set(_pairs(workspace_references.definition_json))

        # The customized row is untouched, and no second row was added there.
        untouched = SeededWorkspaceDefinition.objects.get(pk=customized.pk)
        assert untouched.is_customized is True
        assert untouched.definition_json == {
            "allowed_pairs": list(_OLD_DECOMPOSES_PAIRS)
        }
        assert (
            SeededWorkspaceDefinition.objects.filter(
                tenant_id=tenant.id,
                workspace_id=customized_ws.id,
                key__in=MIGRATION_MERGED_PAIRS,
            ).count()
            == 1
        )
        assert _seeded_rows(tenant.id, workspace_row.id) == 2
    finally:
        # Always restore the schema for every other test in the suite.
        executor = MigrationExecutor(connection)
        executor.migrate(latest_target)


@pytest.mark.django_db(transaction=True)
def test_reverse_refuses_to_orphan_a_work_item_link_then_cleans_up() -> None:
    """Dropping a merged pair would leave a link on a disallowed pair."""
    executor = MigrationExecutor(connection)
    latest_target = executor.loader.graph.leaf_nodes()

    try:
        executor.migrate([_PRE_TARGET])
        executor.loader.build_graph()
        historical = executor.loader.project_state([_PRE_TARGET]).apps
        TenantModel = historical.get_model("persistence", "Tenant")
        WorkspaceModel = historical.get_model("persistence", "Workspace")
        GlobalDefinition = historical.get_model(
            _LINK_TYPES_APP, "GlobalLinkTypeDefinition"
        )
        WorkspaceDefinition = historical.get_model(
            _LINK_TYPES_APP, "WorkspaceLinkTypeDefinition"
        )

        tenant = TenantModel.objects.create(
            name="work-item-1374-reverse",
            slug=f"work-item-rev-{uuid.uuid4().hex[:8]}",
        )
        workspace = WorkspaceModel.objects.create(
            tenant_id=tenant.id, name="reverse-ws"
        )
        for key, pairs in (
            ("decomposes", _OLD_DECOMPOSES_PAIRS),
            ("references", _OLD_REFERENCES_PAIRS),
        ):
            GlobalDefinition.objects.create(
                tenant_id=tenant.id,
                key=key,
                definition_json={"allowed_pairs": list(pairs)},
            )
            WorkspaceDefinition.objects.create(
                tenant_id=tenant.id,
                workspace_id=workspace.id,
                key=key,
                definition_json={"allowed_pairs": list(pairs)},
                is_customized=False,
            )

        executor.migrate([_SEED])
        executor.loader.build_graph()

        TenantContext.set_tenant(tenant.id)
        try:
            document_artifact = Artifact.objects.create(
                tenant_id=tenant.id,
                workspace_id=workspace.id,
                artifact_type="Document",
            )
            work_item_artifact = Artifact.objects.create(
                tenant_id=tenant.id,
                workspace_id=workspace.id,
                artifact_type="WorkItem",
            )
            link = TraceLink.objects.create(
                tenant_id=tenant.id,
                source=document_artifact,
                target=work_item_artifact,
                link_type="decomposes",
            )

            with pytest.raises(RuntimeError, match="1 TraceLink row") as exc:
                executor.migrate([_PRE_TARGET])
            assert "0015_merge_work_item_pairs" in str(exc.value)
            assert "decomposes" in str(exc.value)
            # ... and the refused reverse left the catalog merged.
            assert _seeded_rows(tenant.id, workspace.id) == 2

            link.delete()
        finally:
            TenantContext.clear_tenant()

        # A refused migration leaves the session's transaction state undefined,
        # so the follow-up migrations start on a freshly opened connection.
        connection.close()
        executor = MigrationExecutor(connection)
        executor.migrate([_PRE_TARGET])
        executor.loader.build_graph()
        RevertedWorkspaceDefinition = executor.loader.project_state(
            [_PRE_TARGET]
        ).apps.get_model(_LINK_TYPES_APP, "WorkspaceLinkTypeDefinition")
        reverted = RevertedWorkspaceDefinition.objects.get(
            tenant_id=tenant.id, workspace_id=workspace.id, key="decomposes"
        )
        # Exactly the pairs this migration added are gone, order intact.
        assert reverted.definition_json == {"allowed_pairs": _OLD_DECOMPOSES_PAIRS}
        reverted_references = RevertedWorkspaceDefinition.objects.get(
            tenant_id=tenant.id, workspace_id=workspace.id, key="references"
        )
        assert reverted_references.definition_json == {
            "allowed_pairs": _OLD_REFERENCES_PAIRS
        }

        executor.migrate([_SEED])
        executor.loader.build_graph()
        assert _seeded_rows(tenant.id, workspace.id) == 2
    finally:
        # Always restore the schema for every other test in the suite.
        executor = MigrationExecutor(connection)
        executor.migrate(latest_target)


@pytest.mark.django_db
def test_fresh_provisioning_carries_the_work_item_pairs(env):
    """A workspace provisioned after this commit gets the pairs from builtin.py."""
    tenant, workspace = env["tenant"], env["workspace"]
    with _tenant_scope(tenant.id):
        decomposes = WorkspaceLinkTypeDefinition.unscoped.get(
            tenant_id=tenant.id, workspace_id=workspace.id, key="decomposes"
        )
        references = WorkspaceLinkTypeDefinition.unscoped.get(
            tenant_id=tenant.id, workspace_id=workspace.id, key="references"
        )

    assert _DECOMPOSES_PAIRS <= set(_pairs(decomposes.definition_json))
    assert _REFERENCES_PAIRS <= set(_pairs(references.definition_json))

    # The seed helper is the same path the backfill migration delegates to.
    assert _seed_helpers.seed_tenant(tenant.id, [workspace.id]) == (0, 0)
