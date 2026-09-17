"""No retired link type survives in code that reads or writes link_type."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]

RETIRED = [
    "parent-child",
    "satisfies",
    "implements",
    "refines",
    "realizes",
    "documents",
    "traces",
    "uses-term",
    "copy-of",
]

#: Files that legitimately still name the retired types.
ALLOWED = {
    "link_types/builtin.py",              # the mapping table itself
    "link_types/migration_ops.py",        # the migration
    "link_types/tests/test_builtin.py",
    "link_types/tests/test_migration_ops.py",
    "traceability/tests/test_link_type_consumers.py",
    "context_graph/models.py",            # ContextEdge.edge_kind: unrelated enum, not TraceLink.link_type
    "application/tests/test_trace_link_catalog_validation.py",  # asserts 'satisfies' is rejected as unknown
    "link_types/tests/test_catalog.py",   # asserts 'satisfies' is rejected as unknown
    "link_types/tests/test_inventory_command.py",  # writes legacy 'traces' rows on purpose to test legacy-mapping detection
    "persistence/tests/test_migrate_trace_link_types.py",  # writes the legacy rows migration 0081 has to swallow (issue #893)
}


def _source_files():
    for path in BACKEND.rglob("*.py"):
        relative = path.relative_to(BACKEND).as_posix()
        if "/migrations/" in relative or relative.startswith("."):
            continue
        if relative in ALLOWED:
            continue
        yield relative, path


@pytest.mark.parametrize("retired", RETIRED)
def test_no_retired_link_type_literal_remains(retired):
    pattern = re.compile(rf"""['"]{re.escape(retired)}['"]""")
    offenders = [
        relative
        for relative, path in _source_files()
        if pattern.search(path.read_text(encoding="utf-8", errors="ignore"))
    ]
    assert offenders == [], f"'{retired}' still hardcoded in: {offenders}"


def test_link_type_enum_has_exactly_the_eight_core_members():
    from traceability.types import LinkType

    assert {member.value for member in LinkType} == {
        "derives-from",
        "decomposes",
        "allocated-to",
        "verifies",
        "decides",
        "mitigates",
        "references",
        "diagram-ref",
    }


def test_vcrm_component_query_uses_allocated_to():
    source = (BACKEND / "traceability" / "vcrm_report_generator.py").read_text(
        encoding="utf-8"
    )
    assert "allocated-to" in source
    assert "satisfies" not in source


@pytest.mark.django_db
def test_vcrm_finds_the_component_of_an_allocated_requirement():
    """Regression: the old query looked at the wrong end of the edge."""
    from persistence.models import (
        ArchitectureElement,
        Artifact,
        Requirement,
        Tenant,
        TraceLink,
        Workspace,
    )
    from persistence.tenancy import TenantContext
    from traceability.vcrm_report_generator import VCRMReportGenerator

    tenant = Tenant.objects.create(name="vcrm")
    TenantContext.set_tenant(tenant.id)
    ws = Workspace.objects.create(tenant=tenant, name="ws")

    req_art = Artifact.objects.create(
        tenant=tenant, workspace=ws, artifact_type="Requirement"
    )
    req = Requirement.objects.create(
        tenant=tenant, workspace=ws, artifact=req_art, title="R"
    )
    arch_art = Artifact.objects.create(
        tenant=tenant, workspace=ws, artifact_type="ArchitectureElement"
    )
    ArchitectureElement.objects.create(
        tenant=tenant, artifact=arch_art, title="C"
    )
    TraceLink.objects.create(
        tenant=tenant, source=req_art, target=arch_art, link_type="allocated-to"
    )

    components = VCRMReportGenerator()._get_component_ids_for_requirement(req.id)
    assert str(arch_art.id) in components
    TenantContext.clear_tenant()


def test_hierarchy_decomposition_link_types_is_only_decomposes():
    from traceability.audit.hierarchy import PARENT_TO_CHILD_LINK_TYPES

    assert PARENT_TO_CHILD_LINK_TYPES == {"decomposes"}
