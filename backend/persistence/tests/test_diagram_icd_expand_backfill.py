"""Diagram/Icd carry their own current content (Tasks 28c-1 + 28c-2).

Datenmodell-Konsolidierung Phase 5: the Expand/Migrate/Contract that retired
``DiagramVersion`` and ``IcdVersion``. Task 28c-1 added the columns and
backfilled them; Task 28c-2 made them authoritative and dropped both tables.

**What changed in this module for 28c-2, and why.** It used to drive
``diagram/0010_backfill_current_content`` and
``icd/0011_backfill_current_content`` directly against the live registry with a
fixture-built pre-state — a ``Diagram`` pointing at a ``DiagramVersion``, an
``Icd`` pointing at an ``IcdVersion``. Those two models no longer exist, so
that pre-state cannot be constructed at all: not a mock to update, a fixture
whose subject is physically gone (the same wall Task 28b hit for
``GlossaryTermVersion``, see ``test_legacy_version_migration.py``).

What survives here is everything that does not need a source row: the schema
assertions, and ``Icd.parameters_snapshot``. The backfills' *behaviour* is now
covered where it can still be observed — end to end against a ``pg_dump`` clone
of the real dev database (both 28c-1's and 28c-2's rehearsals), and forward
through the live write paths in ``icd/tests/test_icd_version_retired.py``.
"""
import json
import uuid

import pytest
from django.db import connection

pytestmark = pytest.mark.django_db


@pytest.fixture
def env(db):
    """Tenant + workspace with an armed TenantContext."""
    from persistence.models import Tenant, Workspace
    from persistence.tenancy import TenantContext

    tenant = Tenant.objects.create(name="t-expand-backfill")
    TenantContext.set_tenant(tenant.id)
    workspace = Workspace.objects.create(tenant=tenant, name="ws-expand-backfill")
    return tenant, workspace


# ---------------------------------------------------------------------------
# Schema — the content columns really exist
# ---------------------------------------------------------------------------


def _columns(table):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = %s",
            [table],
        )
        return {row[0] for row in cursor.fetchall()}


def test_diagram_has_the_content_columns():
    assert {
        "payload_format",
        "payload",
        "canvas_json",
        "current_revision",
    } <= _columns("diagram_diagram")


def test_icd_has_the_contract_columns():
    assert {
        "direction",
        "interface_type",
        "semantic_description",
        "preconditions",
        "postconditions",
        "invariants",
        "embedding",
        "current_revision",
    } <= _columns("icd_icd")


def test_icd_parameter_is_owned_by_the_icd():
    assert "icd_id" in _columns("icd_parameter")


def test_icd_embedding_has_its_own_hnsw_index():
    """ICD semantic search must stay indexed now that it reads the Icd row.

    ``icd_version_embedding_hnsw`` went away with its table in Task 28c-2, so
    without this index every ``artifact.search`` semantic pass over ICDs
    degrades to a sequential scan — a silent performance cliff, not an error.
    """
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT indexdef FROM pg_indexes "
            "WHERE tablename = 'icd_icd' AND indexname = 'icd_embedding_hnsw'"
        )
        row = cursor.fetchone()
    assert row is not None, "icd_embedding_hnsw is missing"
    assert "hnsw" in row[0].lower()
    assert "vector_cosine_ops" in row[0]


# ---------------------------------------------------------------------------
# Icd.parameters_snapshot — the by-value bridge wired into _ENTITY_FIELDS["Icd"]
# ---------------------------------------------------------------------------


def test_parameters_snapshot_is_ordered_and_json_serializable(env):
    """``ArtifactVersion.payload`` is a plain JSONField — Decimal would raise."""
    from application.artifact_version_service import snapshot_fields
    from icd.models import Icd, IcdParameter

    tenant, workspace = env
    icd = Icd.objects.create(
        tenant=tenant,
        workspace_id=workspace.id,
        source_element_id=uuid.uuid4(),
        target_element_id=uuid.uuid4(),
        name="ICD-params",
    )
    IcdParameter.objects.create(
        tenant=tenant,
        icd=icd,
        name="legacy_param",
        unit="V",
        data_type="float",
        direction="input",
        min_value="1.500000",
        max_value="9.000000",
        ordering=1,
    )
    IcdParameter.objects.create(
        tenant=tenant,
        icd=icd,
        name="current_param",
        unit="A",
        data_type="int",
        direction="output",
        ordering=0,
    )

    snapshot = icd.parameters_snapshot
    assert [p["name"] for p in snapshot] == ["current_param", "legacy_param"]
    assert snapshot[1]["min_value"] == "1.500000"
    assert snapshot[0]["min_value"] is None
    # Must survive the exact encoder ArtifactVersion.payload uses.
    json.dumps(snapshot)

    # snapshot_fields() resolves plain attributes with getattr, which sees a
    # property transparently — this is what made the 28c-2 wiring a one-line
    # _ENTITY_FIELDS change rather than a special case.
    fields = snapshot_fields(icd, "Icd")
    assert fields["name"] == icd.name
    assert fields["parameters_snapshot"] == snapshot


def test_parameters_snapshot_is_empty_without_parameters(env):
    from icd.models import Icd

    tenant, workspace = env
    icd = Icd.objects.create(
        tenant=tenant,
        workspace_id=workspace.id,
        source_element_id=uuid.uuid4(),
        target_element_id=uuid.uuid4(),
        name="ICD-no-params",
    )
    assert icd.parameters_snapshot == []
