"""The three Document link types are regular catalog built-ins (#1374).

Plan F, F2-T3 (``docs/plans/2026-10-21-plan-f-dokumente-baselines.md``, spec
``docs/superpowers/specs/2026-11-02-f2-document-design.md`` §5, ADR-026):
``documented-in``, ``evidences`` and ``depends-on`` join ``BUILTIN_LINK_TYPES``,
and ``references`` is extended additively with ``Document`` as source and target.

The kind restriction of ``evidences`` (``Conclusion``/``Review``/``AuditReport``)
is a ``Document:<kind>`` pair — the generic sub-type register from Plan B B3-T2
(``link_types.catalog.SUBTYPE_FIELDS``), never a second validation rule.

Two groups of tests live here:

* pair/sub-type validation against a provisioned workspace (the catalog
  contract), and
* the seed migration ``0014_seed_document_link_types``, exercised through the
  real ``MigrationExecutor`` with migration *names* (never bare numbers) and a
  real ``Workspace`` row created *before* the migration runs — a catalog
  addition must reach an existing workspace, not only a freshly provisioned
  one (KA-G-10).

Membership, never a pinned total (KA-F-07): the catalog grows with the plan
series, so no test here counts the built-in set.
"""
from __future__ import annotations

import uuid

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from link_types.builtin import BUILTIN_LINK_TYPES
from link_types.catalog import SUBTYPE_FIELDS, validate_link_pair
from link_types.models import (
    GlobalLinkTypeDefinition,
    WorkspaceLinkTypeDefinition,
)
from persistence.errors import ValidationError
from persistence.models import Artifact, Document, Tenant, TraceLink, Workspace
from persistence.tenancy import TenantContext
from persistence.tests.factories import make_workspace

pytestmark = pytest.mark.django_db

_LINK_TYPES_APP = "link_types"
_PRE_TARGET = (_LINK_TYPES_APP, "0013_seed_issue_risk_link_types")
_SEED = (_LINK_TYPES_APP, "0014_seed_document_link_types")
_NEW_KEYS = ("documented-in", "evidences", "depends-on")
_DOCUMENT_REFERENCE_PAIRS = [
    {"source_type": "Document", "target_type": "*"},
    {"source_type": "*", "target_type": "Document"},
]

_EVIDENCE_KINDS = ("conclusion", "review", "auditreport")
_EVIDENCE_TARGETS = ("Requirement", "ArchitectureElement", "StakeholderNeed")


def _pairs(definition: dict) -> list[tuple[str, str]]:
    return [
        (pair["source_type"], pair["target_type"])
        for pair in definition["allowed_pairs"]
    ]


@pytest.fixture
def env(db):
    """Tenant + provisioned workspace (real rows; ``make_workspace`` seeds the catalog)."""
    tenant = Tenant.objects.create(
        name="document-linktypes", slug=f"document-lt-{uuid.uuid4().hex[:8]}"
    )
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = make_workspace(tenant, name="document-linktypes-ws")
        yield {"tenant": tenant, "workspace": workspace}
    finally:
        TenantContext.clear_tenant()


# ---------------------------------------------------------------------------
# Built-in definitions
# ---------------------------------------------------------------------------


def test_the_three_document_types_are_built_ins():
    assert set(_NEW_KEYS) <= set(BUILTIN_LINK_TYPES)


def test_documented_in_allows_every_documented_artifact_to_a_document():
    definition = BUILTIN_LINK_TYPES["documented-in"]
    assert _pairs(definition) == [
        ("Requirement", "Document"),
        ("StakeholderNeed", "Document"),
        ("ArchitectureElement", "Document"),
        ("Adr", "Document"),
        ("Risk", "Document"),
        ("Issue", "Document"),
        ("Goal", "Document"),
    ]
    assert definition["suspect_rule"] == "target_change_flags_source"
    assert definition["coverage_relevant"] is False
    assert definition["impact_weight"] == 0.3
    assert definition["label"]["de"] == {
        "downstream": "dokumentiert in",
        "upstream": "dokumentiert",
        "neutral": "Dokumentation",
    }
    assert definition["label"]["en"] == {
        "downstream": "documented in",
        "upstream": "documents",
        "neutral": "Documentation",
    }


def test_evidences_is_restricted_to_result_kinds():
    """Only Conclusion/Review/AuditReport evidence anything (spec §5)."""
    definition = BUILTIN_LINK_TYPES["evidences"]
    assert _pairs(definition) == [
        (f"Document:{kind}", target)
        for kind in _EVIDENCE_KINDS
        for target in _EVIDENCE_TARGETS
    ]
    assert definition["suspect_rule"] == "target_change_flags_source"
    # Test coverage stays exclusively ``verifies`` (spec §5).
    assert definition["coverage_relevant"] is False
    assert definition["impact_weight"] == 0.5
    assert definition["label"]["de"] == {
        "downstream": "belegt",
        "upstream": "wird belegt durch",
        "neutral": "Beleg",
    }


def test_depends_on_is_the_work_item_ordering_edge():
    """Inert until F3 ships the WorkItem artifact — documented, not an error."""
    definition = BUILTIN_LINK_TYPES["depends-on"]
    assert _pairs(definition) == [("WorkItem", "WorkItem")]
    assert definition["suspect_rule"] == "target_change_flags_source"
    assert definition["coverage_relevant"] is False
    assert definition["label"]["en"] == {
        "downstream": "depends on",
        "upstream": "is prerequisite for",
        "neutral": "Dependency",
    }


def test_references_gained_document_in_both_directions():
    pairs = {
        (p["source_type"], p["target_type"])
        for p in BUILTIN_LINK_TYPES["references"]["allowed_pairs"]
    }
    for pair in _DOCUMENT_REFERENCE_PAIRS:
        assert (pair["source_type"], pair["target_type"]) in pairs


def test_subtype_register_lists_document_kind():
    """KA-F-02: the generic register gains ``Document -> kind``."""
    assert SUBTYPE_FIELDS["Document"] == "kind"


# ---------------------------------------------------------------------------
# Pair validation against a provisioned workspace
# ---------------------------------------------------------------------------


def test_documented_in_accepts_a_requirement_to_document(env):
    validate_link_pair(
        env["workspace"].id, "documented-in", "Requirement", "Document", manual=True
    )


def test_documented_in_rejects_the_reversed_pair(env):
    with pytest.raises(ValidationError, match="Allowed:"):
        validate_link_pair(
            env["workspace"].id, "documented-in", "Document", "Requirement", manual=True
        )


def test_documented_in_rejects_a_test_case_source(env):
    with pytest.raises(ValidationError, match="Allowed:"):
        validate_link_pair(
            env["workspace"].id, "documented-in", "TestCase", "Document", manual=True
        )


@pytest.mark.parametrize("kind", _EVIDENCE_KINDS)
@pytest.mark.parametrize("target", _EVIDENCE_TARGETS)
def test_evidences_accepts_the_three_result_kinds(env, kind, target):
    validate_link_pair(
        env["workspace"].id, "evidences", f"Document:{kind}", target, manual=True
    )


def test_evidences_rejects_document_kind_spec(env):
    """A Spec is not evidence: the kind restriction is the sub-type pair."""
    with pytest.raises(ValidationError, match="Document:conclusion"):
        validate_link_pair(
            env["workspace"].id, "evidences", "Document:spec", "Requirement", manual=True
        )


def test_evidences_rejects_a_test_case_target(env):
    with pytest.raises(ValidationError, match="Allowed:"):
        validate_link_pair(
            env["workspace"].id, "evidences", "Document:conclusion", "TestCase", manual=True
        )


def test_depends_on_accepts_work_item_to_work_item(env):
    validate_link_pair(
        env["workspace"].id, "depends-on", "WorkItem", "WorkItem", manual=True
    )


def test_depends_on_rejects_a_non_work_item_endpoint(env):
    with pytest.raises(ValidationError, match="Allowed:"):
        validate_link_pair(
            env["workspace"].id, "depends-on", "Requirement", "WorkItem", manual=True
        )


def test_references_accepts_document_in_both_directions(env):
    validate_link_pair(
        env["workspace"].id, "references", "Document", "Requirement", manual=True
    )
    validate_link_pair(
        env["workspace"].id, "references", "Requirement", "Document", manual=True
    )


def test_service_derives_the_document_kind_tag(env):
    """The endpoint resolver reads ``Document.kind`` like ``element_type``.

    This is the integration half of KA-F-02: a ``Document:spec`` link is refused
    by the pair check even though only the base type was passed in.
    """
    from application.trace_link_service import TraceLinkService
    from auth_tenancy.context import AuthContext, AuthMethod

    workspace = env["workspace"]
    requirement = Artifact.objects.create(
        tenant_id=workspace.tenant_id,
        workspace=workspace,
        artifact_type="Requirement",
    )
    document_artifact = Artifact.objects.create(
        tenant_id=workspace.tenant_id,
        workspace=workspace,
        artifact_type="Document",
    )
    Document.objects.create(
        tenant_id=workspace.tenant_id,
        workspace=workspace,
        artifact=document_artifact,
        title="Audit round 7",
        kind=Document.Kind.AUDIT_REPORT,
    )
    ctx = AuthContext(
        user_id=None,
        tenant_id=workspace.tenant_id,
        active_roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN,
        workspace_id=workspace.id,
    )

    link = TraceLinkService().create_trace_link(
        document_artifact.id, requirement.id, "evidences", ctx
    )
    assert link.link_type == "evidences"

    spec_artifact = Artifact.objects.create(
        tenant_id=workspace.tenant_id,
        workspace=workspace,
        artifact_type="Document",
    )
    Document.objects.create(
        tenant_id=workspace.tenant_id,
        workspace=workspace,
        artifact=spec_artifact,
        title="Design spec",
        kind=Document.Kind.SPEC,
    )
    with pytest.raises(ValidationError, match="Document:conclusion"):
        TraceLinkService().create_trace_link(
            spec_artifact.id, requirement.id, "evidences", ctx
        )


# ---------------------------------------------------------------------------
# Seed migration 0014_seed_document_link_types
# ---------------------------------------------------------------------------


def _seeded_rows(tenant_id: uuid.UUID, workspace_id: uuid.UUID) -> int:
    """Count this tenant's seeded Document rows in *workspace_id*."""
    return WorkspaceLinkTypeDefinition.unscoped.filter(
        tenant_id=tenant_id, workspace_id=workspace_id, key__in=_NEW_KEYS
    ).count()


@pytest.mark.django_db(transaction=True)
def test_migration_seeds_document_link_types_on_existing_workspace() -> None:
    """0013 -> 0014 adds three rows per pre-existing workspace, customized stays."""
    executor = MigrationExecutor(connection)
    latest_target = executor.loader.graph.leaf_nodes()
    # The pairs ``references`` shipped with before this migration.
    old_reference_pairs = [
        {"source_type": "*", "target_type": "GlossaryTerm"},
        {"source_type": "*", "target_type": "Diagram"},
    ]

    try:
        executor.migrate([_PRE_TARGET])
        executor.loader.build_graph()
        historical = executor.loader.project_state([_PRE_TARGET]).apps
        TenantModel = historical.get_model("persistence", "Tenant")
        WorkspaceModel = historical.get_model("persistence", "Workspace")
        GlobalDefinition = historical.get_model(_LINK_TYPES_APP, "GlobalLinkTypeDefinition")
        WorkspaceDefinition = historical.get_model(
            _LINK_TYPES_APP, "WorkspaceLinkTypeDefinition"
        )

        tenant = TenantModel.objects.create(
            name="document-1374", slug=f"document-{uuid.uuid4().hex[:8]}"
        )
        workspace_row = WorkspaceModel.objects.create(
            tenant_id=tenant.id, name="pre-existing-ws"
        )
        customized_ws = WorkspaceModel.objects.create(
            tenant_id=tenant.id, name="customized-ws"
        )

        # Pre-0014 state of the references rows this migration extends.
        GlobalDefinition.objects.create(
            tenant_id=tenant.id,
            key="references",
            definition_json={"allowed_pairs": list(old_reference_pairs)},
        )
        WorkspaceDefinition.objects.create(
            tenant_id=tenant.id,
            workspace_id=workspace_row.id,
            key="references",
            definition_json={"allowed_pairs": list(old_reference_pairs)},
            is_customized=False,
        )

        # A workspace that tailored `evidences` made a decision; the seed must
        # neither overwrite it nor add a second row for that key.
        customized = WorkspaceDefinition.objects.create(
            tenant_id=tenant.id,
            workspace_id=customized_ws.id,
            key="evidences",
            definition_json={"impact_weight": 0.42},
            is_customized=True,
        )

        assert not WorkspaceDefinition.objects.filter(
            tenant_id=tenant.id, key=_NEW_KEYS[0]
        ).exists()
        assert not GlobalDefinition.objects.filter(
            tenant_id=tenant.id, key__in=_NEW_KEYS
        ).exists()

        executor.migrate([_SEED])
        executor.loader.build_graph()
        seeded_apps = executor.loader.project_state([_SEED]).apps
        SeededWorkspaceDefinition = seeded_apps.get_model(
            _LINK_TYPES_APP, "WorkspaceLinkTypeDefinition"
        )
        SeededGlobalDefinition = seeded_apps.get_model(
            _LINK_TYPES_APP, "GlobalLinkTypeDefinition"
        )

        seeded = {
            key: SeededWorkspaceDefinition.objects.get(
                tenant_id=tenant.id, workspace_id=workspace_row.id, key=key
            )
            for key in _NEW_KEYS
        }
        for key, row in seeded.items():
            assert row.is_customized is False
            assert _pairs(row.definition_json) == _pairs(
                BUILTIN_LINK_TYPES[key]
            )
            assert row.definition_json["suspect_rule"] == "target_change_flags_source"
            assert row.definition_json["coverage_relevant"] is False
            assert row.source_global_id is not None

            global_row = SeededGlobalDefinition.objects.get(
                tenant_id=tenant.id, key=key
            )
            assert _pairs(global_row.definition_json) == _pairs(
                BUILTIN_LINK_TYPES[key]
            )

        assert (
            seeded["documented-in"].definition_json["label"]["de"]["downstream"]
            == "dokumentiert in"
        )
        assert (
            seeded["evidences"].definition_json["label"]["en"]["upstream"]
            == "is evidenced by"
        )
        assert (
            seeded["depends-on"].definition_json["label"]["de"]["upstream"]
            == "ist Voraussetzung für"
        )

        # Additive, order-preserving `references` merge, once, on the global
        # template and the non-customized workspace copy.
        merged_workspace = SeededWorkspaceDefinition.objects.get(
            tenant_id=tenant.id, workspace_id=workspace_row.id, key="references"
        )
        assert merged_workspace.definition_json["allowed_pairs"] == (
            old_reference_pairs + _DOCUMENT_REFERENCE_PAIRS
        )
        merged_global = SeededGlobalDefinition.objects.get(
            tenant_id=tenant.id, key="references"
        )
        assert merged_global.definition_json["allowed_pairs"] == (
            old_reference_pairs + _DOCUMENT_REFERENCE_PAIRS
        )

        # The customized row is untouched, and no second `evidences` row was
        # added there ... while the two keys it did not customize were seeded.
        untouched = SeededWorkspaceDefinition.objects.get(pk=customized.pk)
        assert untouched.is_customized is True
        assert untouched.definition_json == {"impact_weight": 0.42}
        assert (
            SeededWorkspaceDefinition.objects.filter(
                tenant_id=tenant.id,
                workspace_id=customized_ws.id,
                key__in=("documented-in", "depends-on"),
            ).count()
            == 2
        )
    finally:
        # Always restore the schema for every other test in the suite.
        executor = MigrationExecutor(connection)
        executor.migrate(latest_target)


@pytest.mark.django_db(transaction=True)
def test_reverse_refuses_to_orphan_a_document_link_then_cleans_up() -> None:
    """Dropping a type would leave links on a key no catalog can resolve."""
    executor = MigrationExecutor(connection)
    latest_target = executor.loader.graph.leaf_nodes()

    try:
        executor.migrate([_PRE_TARGET])
        executor.loader.build_graph()

        tenant = Tenant.objects.create(
            name="document-1374-reverse",
            slug=f"document-rev-{uuid.uuid4().hex[:8]}",
        )
        TenantContext.set_tenant(tenant.id)
        try:
            workspace = Workspace.objects.create(tenant=tenant, name="reverse-ws")
            requirement = Artifact.objects.create(
                tenant=tenant, workspace=workspace, artifact_type="Requirement"
            )
            document = Artifact.objects.create(
                tenant=tenant, workspace=workspace, artifact_type="Document"
            )
            link = TraceLink.objects.create(
                tenant=tenant,
                source=requirement,
                target=document,
                link_type="documented-in",
            )

            executor.migrate([_SEED])
            executor.loader.build_graph()
            assert _seeded_rows(tenant.id, workspace.id) == 3

            with pytest.raises(RuntimeError, match="1 TraceLink row") as exc:
                executor.migrate([_PRE_TARGET])
            assert "documented-in" in str(exc.value)
            # ... and the refused reverse left the catalog untouched.
            assert _seeded_rows(tenant.id, workspace.id) == 3

            link.delete()
        finally:
            TenantContext.clear_tenant()

        # A refused migration leaves the session's transaction state undefined,
        # so the follow-up migrations start on a freshly opened connection.
        connection.close()
        executor = MigrationExecutor(connection)
        executor.migrate([_PRE_TARGET])
        executor.loader.build_graph()
        assert _seeded_rows(tenant.id, workspace.id) == 0
        assert not GlobalLinkTypeDefinition.unscoped.filter(
            tenant_id=tenant.id, key__in=_NEW_KEYS
        ).exists()

        executor.migrate([_SEED])
        executor.loader.build_graph()
        assert _seeded_rows(tenant.id, workspace.id) == 3
    finally:
        # Always restore the schema for every other test in the suite.
        executor = MigrationExecutor(connection)
        executor.migrate(latest_target)
