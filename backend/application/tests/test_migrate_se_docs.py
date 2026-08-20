"""Tests for the ``migrate_se_docs`` management command's two post-import passes.

Covers Feature 1 (ArchitectureElement hierarchy / ``parent_id`` resolution from
the docs/se folder structure) and Feature 2 (TraceLink creation from
``traceability-matrix.md``), including the intentional skipping of ``—`` cells
and idempotency on a repeated run. The generic CSV entity import
(ImportService / ENTITY_FIELD_SPECS) is exercised only indirectly, as the
fixtures the two new passes depend on.
"""
from __future__ import annotations

import io
from pathlib import Path, PurePosixPath

import pytest
from django.core.management import call_command

from application.management.commands.migrate_se_docs import (
    _LINK_DERIVES_FROM,
    _LINK_IMPLEMENTS,
    _parse_requirements_table_file,
    _parse_trace_matrix,
    _resolve_architecture_parents,
    _split_table_row,
)
from auth_tenancy.provisioning import DEFAULT_WORKSPACE_ID
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import (
    ArchitectureElement,
    Requirement,
    StakeholderNeed,
    TraceLink,
    Workspace,
)
from workflow.models import WorkflowItemState

# ---------------------------------------------------------------------------
# Unit tests — pure parsing helpers (no DB)
# ---------------------------------------------------------------------------


def _p(rel: str) -> Path:
    """Build a stable pure-POSIX path for folder-structure resolution tests."""
    return Path(PurePosixPath("/docs/se") / rel)


def test_resolve_architecture_parents_root_subsystem_component():
    entries = [
        ("ARCH-L1-000", "subsystem", _p("L1/Gesamtsystem/L1_Gesamtsystem_Architecture.md")),
        (
            "ARCH-L1-008",
            "subsystem",
            _p("L1/Gesamtsystem/L2/AppSys/L2_AppSys_Architecture.md"),
        ),
        (
            "COMP-AS-001",
            "component",
            _p(
                "L1/Gesamtsystem/L2/AppSys/Components/"
                "COMP-AS-001_Foo/L3_COMP-AS-001_Foo_Architecture.md"
            ),
        ),
    ]

    parent_of, warnings = _resolve_architecture_parents(entries)

    assert parent_of["ARCH-L1-000"] is None
    assert parent_of["ARCH-L1-008"] == "ARCH-L1-000"
    assert parent_of["COMP-AS-001"] == "ARCH-L1-008"
    assert warnings == []


def test_resolve_architecture_parents_orphan_component_warns():
    # Component with no L2 subsystem ancestor in the entry set.
    entries = [
        (
            "COMP-XX-001",
            "component",
            _p("L1/Gesamtsystem/L2/Ghost/Components/COMP-XX-001_X/L3_x_Architecture.md"),
        ),
    ]

    parent_of, warnings = _resolve_architecture_parents(entries)

    assert parent_of["COMP-XX-001"] is None
    assert len(warnings) == 1
    assert "COMP-XX-001" in warnings[0]


def test_parse_trace_matrix_orientation_and_link_types():
    text = "\n".join(
        [
            "## 1. REQ-L0 → REQ-L1",
            "| REQ-L0 | Titel | REQ-L1 IDs |",
            "|--------|-------|-----------|",
            "| REQ-L0-001 | Need | REQ-L1-008, REQ-L1-006 |",
            "",
            "## 2. REQ-L1 → REQ-L2",
            "| REQ-L1 | Title | System | REQ-L2 IDs |",
            "|--------|-------|--------|-----------|",
            "| REQ-L1-008 | Baselines | AppSys | REQ-L2-AS-001 |",
            "",
            "## 3. REQ-L2 → Component",
            "### 3.1 AppSys",
            "| REQ-L2 | Title | Component | Test Case |",
            "|--------|-------|-----------|-----------|",
            "| REQ-L2-AS-001 | X | COMP-AS-001, COMP-AS-002 | TC-AS-001 |",
        ]
    )

    triples = set(_parse_trace_matrix(text))

    assert ("REQ-L1-008", "REQ-L0-001", _LINK_DERIVES_FROM) in triples
    assert ("REQ-L1-006", "REQ-L0-001", _LINK_DERIVES_FROM) in triples
    assert ("REQ-L2-AS-001", "REQ-L1-008", _LINK_DERIVES_FROM) in triples
    assert ("COMP-AS-001", "REQ-L2-AS-001", _LINK_IMPLEMENTS) in triples
    assert ("COMP-AS-002", "REQ-L2-AS-001", _LINK_IMPLEMENTS) in triples
    # The Test-Case column is intentionally not linked.
    assert not any("TC-AS-001" in t for triple in triples for t in triple)


def test_split_table_row_handles_escaped_pipe():
    cells = _split_table_row(
        r"| REQ-001 | Functional | Title | Desc with \| an escaped pipe | Done |"
    )
    assert cells == ["REQ-001", "Functional", "Title", "Desc with | an escaped pipe", "Done"]


def test_parse_requirements_table_file(tmp_path):
    path = tmp_path / "REQUIREMENTS.md"
    path.write_text(
        "\n".join(
            [
                "## Cluster A",
                "",
                "| REQ-ID | Kategorie | Titel | Beschreibung | Status |",
                "|--------|-----------|-------|-------------|--------|",
                "| REQ-001 | Functional | Title A | Body A | Done |",
                "| REQ-002 | Security | Title B | Body B | Backlog |",
                "",
                "## Cluster B",
                "",
                "| REQ-ID | Kategorie | Titel | Beschreibung | Status |",
                "|--------|-----------|-------|-------------|--------|",
                "| REQ-003 | Non-Functional | Title C | Body \\| with pipe | Active |",
            ]
        ),
        encoding="utf-8",
    )

    rows, warnings = _parse_requirements_table_file(path)

    assert warnings == []
    assert [uid for uid, _ in rows] == ["REQ-001", "REQ-002", "REQ-003"]

    row1 = dict(rows[0][1])
    assert row1["uid"] == "REQ-001"
    assert row1["title"] == "Title A"
    assert row1["category"] == "Functional"
    assert row1["description"] == "Body A"
    assert row1["status"] == "Done"

    row3 = dict(rows[2][1])
    assert row3["description"] == "Body | with pipe"
    assert row3["status"] == "Active"


def test_parse_requirements_table_file_no_rows_warns(tmp_path):
    path = tmp_path / "REQUIREMENTS.md"
    path.write_text("Just prose, no tables here.\n", encoding="utf-8")

    rows, warnings = _parse_requirements_table_file(path)

    assert rows == []
    assert len(warnings) == 1
    assert "no 'REQ-<number>'" in warnings[0]


def test_parse_trace_matrix_skips_dash_and_placeholder_rows():
    text = "\n".join(
        [
            "## 1. REQ-L0 → REQ-L1",
            "| REQ-L0 | Titel | REQ-L1 IDs |",
            "|--------|-------|-----------|",
            "| REQ-L0-023 | ReqIF-Support | — |",
            "",
            "## 3. REQ-L2 → Component",
            "### 3.1 AppSys",
            "| REQ-L2 | Title | Component | Test Case |",
            "|--------|-------|-----------|-----------|",
            "| ... (20 weitere REQ-L2-AS) | ... | ... | ... |",
            "",
            "## 4. Coverage Summary",
            "| REQ-L0 | 34 | 22 | 64% |",
        ]
    )

    triples = _parse_trace_matrix(text)

    # '—' cell, placeholder '...' row and the coverage table produce no links.
    assert triples == []


# ---------------------------------------------------------------------------
# Integration test — end-to-end command run + idempotency
# ---------------------------------------------------------------------------


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _build_docs_fixture(root: Path) -> None:
    """Create a minimal docs/se tree exercising both post-import passes."""
    gesamt = root / "L1" / "Gesamtsystem"

    _write(
        gesamt / "L1_Gesamtsystem_Architecture.md",
        "# Gesamtsystem\n\n## 1. Verantwortlichkeit\nRoot responsibility.\n",
    )
    _write(
        gesamt / "L2" / "AppSys" / "L2_AppSys_Architecture.md",
        "# AppSys\n\n> **System:** AppSys (ARCH-L1-008)\n\n"
        "## 1. Verantwortlichkeit\nSubsystem responsibility.\n",
    )
    _write(
        gesamt
        / "L2"
        / "AppSys"
        / "Components"
        / "COMP-AS-001_Foo"
        / "L3_COMP-AS-001_Foo_Architecture.md",
        "# COMP-AS-001 Foo\n\n## 1. Verantwortlichkeit\nComponent responsibility.\n",
    )

    _write(
        root / "L0" / "L0_Needs.md",
        "# Stakeholder Needs\n\n### REQ-L0-001: Machine-readable context\nBody.\n",
    )
    _write(
        gesamt / "L1_Gesamtsystem_Requirements.md",
        "# System Requirements\n\n"
        "### REQ-L1-008: Multi-Level Baselines\nBody.\n\n"
        "### REQ-L2-AS-001: Artifact Hierarchy\nBody.\n",
    )

    _write(
        root / "traceability-matrix.md",
        "\n".join(
            [
                "# Traceability Matrix",
                "",
                "## 1. REQ-L0 → REQ-L1",
                "| REQ-L0 | Titel | REQ-L1 IDs |",
                "|--------|-------|-----------|",
                "| REQ-L0-001 | Need | REQ-L1-008 |",
                "| REQ-L0-002 | Missing | — |",
                "",
                "## 2. REQ-L1 → REQ-L2",
                "| REQ-L1 | Title | System | REQ-L2 IDs |",
                "|--------|-------|--------|-----------|",
                "| REQ-L1-008 | Baselines | AppSys | REQ-L2-AS-001 |",
                "",
                "## 3. REQ-L2 → Component",
                "### 3.1 AppSys",
                "| REQ-L2 | Title | Component | Test Case |",
                "|--------|-------|-----------|-----------|",
                "| REQ-L2-AS-001 | X | COMP-AS-001 | TC-AS-001 |",
                "",
            ]
        ),
    )


def _arch_by_uid(workspace_id) -> dict:
    return {
        el.uid: el
        for el in ArchitectureElement.objects.filter(
            artifact__workspace_id=workspace_id
        )
    }


@pytest.mark.django_db
def test_migrate_sets_hierarchy_trace_links_and_is_idempotent(tmp_path):
    call_command("seed_demo")
    _build_docs_fixture(tmp_path)

    def _run() -> None:
        call_command(
            "migrate_se_docs",
            docs_root=str(tmp_path),
            stdout=io.StringIO(),
            stderr=io.StringIO(),
        )

    _run()

    workspace = Workspace.unscoped.get(id=DEFAULT_WORKSPACE_ID)
    set_request_tenant(workspace.tenant_id)
    try:
        arch = _arch_by_uid(workspace.id)
        assert set(arch) >= {"ARCH-L1-000", "ARCH-L1-008", "COMP-AS-001"}

        # Feature 1: parent_id resolved from the folder structure.
        assert arch["ARCH-L1-000"].parent_id is None
        assert arch["ARCH-L1-008"].parent_id == arch["ARCH-L1-000"].id
        assert arch["COMP-AS-001"].parent_id == arch["ARCH-L1-008"].id

        sn = StakeholderNeed.objects.get(
            uid="REQ-L0-001", artifact__workspace_id=workspace.id
        )
        req_l1 = Requirement.objects.get(
            uid="REQ-L1-008", artifact__workspace_id=workspace.id
        )
        req_l2 = Requirement.objects.get(
            uid="REQ-L2-AS-001", artifact__workspace_id=workspace.id
        )

        # Feature 2: the three resolvable links exist with correct orientation.
        assert TraceLink.objects.filter(
            source_id=req_l1.artifact_id,
            target_id=sn.artifact_id,
            link_type=_LINK_DERIVES_FROM,
        ).exists()
        assert TraceLink.objects.filter(
            source_id=req_l2.artifact_id,
            target_id=req_l1.artifact_id,
            link_type=_LINK_DERIVES_FROM,
        ).exists()
        assert TraceLink.objects.filter(
            source_id=arch["COMP-AS-001"].artifact_id,
            target_id=req_l2.artifact_id,
            link_type=_LINK_IMPLEMENTS,
        ).exists()

        # The '—' row (REQ-L0-002) produced no link.
        assert TraceLink.objects.filter(link_type=_LINK_DERIVES_FROM).count() == 2
        assert TraceLink.objects.filter(link_type=_LINK_IMPLEMENTS).count() == 1

        link_count_after_first = TraceLink.objects.count()
        version_after_first = {
            uid: el.version for uid, el in _arch_by_uid(workspace.id).items()
        }
    finally:
        clear_request_tenant()

    # Second run must be a no-op: no new links, no version churn.
    _run()

    set_request_tenant(workspace.tenant_id)
    try:
        assert TraceLink.objects.count() == link_count_after_first
        version_after_second = {
            uid: el.version for uid, el in _arch_by_uid(workspace.id).items()
        }
        assert version_after_second == version_after_first
    finally:
        clear_request_tenant()


@pytest.mark.django_db
def test_migrate_sets_status_field_to_draft(tmp_path):
    """Verify that imported Requirements and StakeholderNeeds have status='draft'.

    Source documents (docs/se/) do not track status for individual requirements
    and stakeholder needs. This test ensures the migrate_se_docs command
    explicitly sets status='draft' as the conscious default, rather than
    relying on the model's implicit default.
    """
    call_command("seed_demo")
    _build_docs_fixture(tmp_path)

    call_command(
        "migrate_se_docs",
        docs_root=str(tmp_path),
        stdout=io.StringIO(),
        stderr=io.StringIO(),
    )

    workspace = Workspace.unscoped.get(id=DEFAULT_WORKSPACE_ID)
    set_request_tenant(workspace.tenant_id)
    try:
        # Check StakeholderNeed status.
        sn = StakeholderNeed.objects.get(
            uid="REQ-L0-001", artifact__workspace_id=workspace.id
        )
        assert sn.status == "draft"

        # Check Requirement (L1 and L2) statuses.
        req_l1 = Requirement.objects.get(
            uid="REQ-L1-008", artifact__workspace_id=workspace.id
        )
        assert req_l1.status == "draft"

        req_l2 = Requirement.objects.get(
            uid="REQ-L2-AS-001", artifact__workspace_id=workspace.id
        )
        assert req_l2.status == "draft"
    finally:
        clear_request_tenant()


# ---------------------------------------------------------------------------
# Integration test — --format=table (issue #117)
# ---------------------------------------------------------------------------


def _write_table_fixture(path: Path) -> None:
    _write(
        path,
        "\n".join(
            [
                "<!-- legacy flat requirements register -->",
                "",
                "## Cluster A",
                "",
                "| REQ-ID | Kategorie | Titel | Beschreibung | Status |",
                "|--------|-----------|-------|-------------|--------|",
                "| REQ-001 | Functional | First Req | Body with a \\| pipe. | Done |",
                "| REQ-002 | Security | Second Req | Another body. | Backlog |",
                "",
            ]
        ),
    )


@pytest.mark.django_db
def test_migrate_table_format_imports_requirements_with_workflow_state(tmp_path):
    """--format=table (issue #117) must import Requirement rows AND wire them
    into the workspace's WorkflowEngineDefinition via WorkflowItemState — the
    same COMP-AS-009 ImportService path the CSV importer uses, per the
    REQ-143 / issue #113 status-mirror contract. A bare "just create
    Requirement rows" import would be the wrong pattern."""
    from workflow.models import WorkflowEngineDefinition

    call_command("seed_demo")
    workspace = Workspace.unscoped.get(id=DEFAULT_WORKSPACE_ID)

    set_request_tenant(workspace.tenant_id)
    try:
        # #41: seed_demo now provisions a default Requirement workflow
        # definition itself, so this test's fixture-specific states
        # ("Backlog"/"Active"/"Done") must overwrite it rather than
        # collide with it on the (tenant, workspace, item_type) constraint.
        WorkflowEngineDefinition.objects.update_or_create(
            tenant=workspace.tenant,
            workspace_id=workspace.id,
            item_type="Requirement",
            defaults={
                "preset": WorkflowEngineDefinition.PRESET_STANDARD,
                "workflow_json": {
                    "states": ["Backlog", "Active", "Done"],
                    "transitions": [],
                },
            },
        )
    finally:
        clear_request_tenant()

    fixture = tmp_path / "REQUIREMENTS.md"
    _write_table_fixture(fixture)

    def _run() -> None:
        call_command(
            "migrate_se_docs",
            format="table",
            file=str(fixture),
            stdout=io.StringIO(),
            stderr=io.StringIO(),
        )

    _run()

    set_request_tenant(workspace.tenant_id)
    try:
        req1 = Requirement.objects.get(uid="REQ-001", artifact__workspace_id=workspace.id)
        req2 = Requirement.objects.get(uid="REQ-002", artifact__workspace_id=workspace.id)

        assert req1.title == "First Req"
        assert req1.category == "Functional"
        assert "pipe" in req1.description
        assert req1.status == "Done"

        assert req2.title == "Second Req"
        assert req2.status == "Backlog"

        # REQ-143 / issue #113: imported rows must be workflow-alive, not just
        # bare content rows — WorkflowItemState mirrors the mapped status.
        state1 = WorkflowItemState.objects.get(
            item_id=req1.id, item_type="Requirement", workspace_id=workspace.id
        )
        assert state1.current_state == "Done"

        state2 = WorkflowItemState.objects.get(
            item_id=req2.id, item_type="Requirement", workspace_id=workspace.id
        )
        assert state2.current_state == "Backlog"

        imported_count_after_first = Requirement.objects.filter(
            artifact__workspace_id=workspace.id
        ).count()
    finally:
        clear_request_tenant()

    # Idempotency: a second run must not create duplicate Requirements.
    _run()

    set_request_tenant(workspace.tenant_id)
    try:
        imported_count_after_second = Requirement.objects.filter(
            artifact__workspace_id=workspace.id
        ).count()
        assert imported_count_after_second == imported_count_after_first
        assert (
            Requirement.objects.filter(
                uid="REQ-001", artifact__workspace_id=workspace.id
            ).count()
            == 1
        )
    finally:
        clear_request_tenant()


@pytest.mark.django_db
def test_migrate_table_format_dry_run_writes_nothing(tmp_path):
    call_command("seed_demo")
    workspace = Workspace.unscoped.get(id=DEFAULT_WORKSPACE_ID)

    fixture = tmp_path / "REQUIREMENTS.md"
    _write_table_fixture(fixture)

    call_command(
        "migrate_se_docs",
        format="table",
        file=str(fixture),
        dry_run=True,
        stdout=io.StringIO(),
        stderr=io.StringIO(),
    )

    set_request_tenant(workspace.tenant_id)
    try:
        assert not Requirement.objects.filter(
            uid="REQ-001", artifact__workspace_id=workspace.id
        ).exists()
    finally:
        clear_request_tenant()
