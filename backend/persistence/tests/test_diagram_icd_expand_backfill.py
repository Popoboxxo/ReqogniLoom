"""Task 28c-1: Diagram/Icd current content moves onto the header rows.

Datenmodell-Konsolidierung Phase 5, Expand half of the Expand/Migrate/Contract
that retires ``DiagramVersion`` and ``IcdVersion``.

Exercises ``diagram/migrations/0010_backfill_current_content`` and
``icd/migrations/0011_backfill_current_content`` directly against the live
registry rather than replaying the migration graph — the same approach (and
the same reason) as ``test_legacy_version_migration.py``: both migrations are
already applied in the test database and are no-ops against an empty one, so a
fixture-built pre-state is the only way to observe what the backfill does.

Both migrations touch only raw SQL and the schema editor's connection, so the
``apps_registry`` argument is unused and ``django.apps.apps`` is a valid stand-in.
"""
import json
import uuid
from importlib import import_module

import pytest
from django.apps import apps
from django.db import connection
from django.test.utils import CaptureQueriesContext

pytestmark = pytest.mark.django_db

_DIAGRAM_MIGRATION = "diagram.migrations.0010_backfill_current_content"
_ICD_MIGRATION = "icd.migrations.0011_backfill_current_content"


def _run(migration_path, func_name):
    """Call *func_name* from the named migration module against the live DB."""
    module = import_module(migration_path)
    with connection.schema_editor() as schema_editor:
        getattr(module, func_name)(apps, schema_editor)


@pytest.fixture
def env(db):
    """Tenant + workspace with an armed TenantContext."""
    from persistence.models import Tenant, Workspace
    from persistence.tenancy import TenantContext

    tenant = Tenant.objects.create(name="t-expand-backfill")
    TenantContext.set_tenant(tenant.id)
    workspace = Workspace.objects.create(tenant=tenant, name="ws-expand-backfill")
    return tenant, workspace


@pytest.fixture
def legacy_diagram(env):
    """A Diagram whose content lives only on its current DiagramVersion."""
    from diagram.models import Diagram, DiagramVersion

    tenant, workspace = env
    diagram = Diagram.objects.create(
        tenant=tenant,
        workspace_id=workspace.id,
        name="D-expand",
        diagram_type="block",
    )
    version = DiagramVersion.objects.create(
        tenant=tenant,
        diagram=diagram,
        version_number=3,
        payload_format="mermaid",
        payload="graph TD; A-->B;",
        canvas_json={"objects": [{"type": "rect"}]},
    )
    Diagram.objects.filter(pk=diagram.pk).update(current_version=version)
    diagram.refresh_from_db()
    return diagram, version


@pytest.fixture
def legacy_icd(env):
    """An Icd with two versions; parameters hang off *both* of them."""
    from icd.models import Icd, IcdParameter, IcdVersion

    tenant, workspace = env
    icd = Icd.objects.create(
        tenant=tenant,
        workspace_id=workspace.id,
        source_element_id=uuid.uuid4(),
        target_element_id=uuid.uuid4(),
        name="ICD-expand",
    )
    old_version = IcdVersion.objects.create(
        tenant=tenant,
        icd=icd,
        version_number=1,
        direction="unidirectional",
        interface_type="provides",
        semantic_description="v1",
        preconditions=["p1"],
        postconditions=[],
        invariants=[],
    )
    current_version = IcdVersion.objects.create(
        tenant=tenant,
        icd=icd,
        version_number=2,
        direction="bidirectional",
        interface_type="data",
        semantic_description="v2 contract",
        preconditions=["caller holds the lock"],
        postconditions=["result is committed"],
        invariants=["voltage stays positive"],
    )
    Icd.objects.filter(pk=icd.pk).update(current_version=current_version)
    icd.refresh_from_db()

    historical_param = IcdParameter.objects.create(
        tenant=tenant,
        icd_version=old_version,
        name="legacy_param",
        unit="V",
        data_type="float",
        direction="input",
        min_value="1.500000",
        max_value="9.000000",
        ordering=1,
    )
    current_param = IcdParameter.objects.create(
        tenant=tenant,
        icd_version=current_version,
        name="current_param",
        unit="A",
        data_type="int",
        direction="output",
        ordering=0,
    )
    return icd, current_version, current_param, historical_param


# ---------------------------------------------------------------------------
# Schema — the new columns really exist
# ---------------------------------------------------------------------------


def _columns(table):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = %s",
            [table],
        )
        return {row[0] for row in cursor.fetchall()}


def test_diagram_has_the_new_content_columns():
    assert {
        "payload_format",
        "payload",
        "canvas_json",
        "current_revision",
    } <= _columns("diagram_diagram")


def test_icd_has_the_new_contract_columns():
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


def test_icd_parameter_has_the_new_owner_column():
    assert "icd_id" in _columns("icd_parameter")


def test_icd_embedding_has_its_own_hnsw_index():
    """ICD semantic search must stay indexed once it reads the header row."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT indexdef FROM pg_indexes "
            "WHERE tablename = 'icd_icd' AND indexname = 'icd_embedding_hnsw'"
        )
        row = cursor.fetchone()
    assert row is not None, "icd_embedding_hnsw is missing"
    assert "hnsw" in row[0].lower()
    assert "vector_cosine_ops" in row[0]


def test_legacy_version_tables_are_untouched():
    """Expand adds; it must not remove. 28c-2 owns the Contract half."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_name IN ('diagram_diagramversion', 'icd_version')"
        )
        assert {row[0] for row in cursor.fetchall()} == {
            "diagram_diagramversion",
            "icd_version",
        }


# ---------------------------------------------------------------------------
# Backfill — Diagram
# ---------------------------------------------------------------------------


def test_diagram_backfill_copies_the_current_version(legacy_diagram):
    diagram, version = legacy_diagram
    assert diagram.payload == ""
    assert diagram.current_revision == 0

    _run(_DIAGRAM_MIGRATION, "backfill")
    diagram.refresh_from_db()

    assert diagram.payload_format == version.payload_format
    assert diagram.payload == version.payload
    assert diagram.canvas_json == version.canvas_json
    assert diagram.current_revision == version.version_number


def test_diagram_without_a_current_version_keeps_the_defaults(env):
    from diagram.models import Diagram

    tenant, workspace = env
    diagram = Diagram.objects.create(
        tenant=tenant,
        workspace_id=workspace.id,
        name="D-empty",
        diagram_type="block",
    )

    _run(_DIAGRAM_MIGRATION, "backfill")
    _run(_DIAGRAM_MIGRATION, "verify")
    diagram.refresh_from_db()

    assert diagram.payload_format == ""
    assert diagram.payload == ""
    assert diagram.canvas_json is None
    assert diagram.current_revision == 0


def test_diagram_backfill_is_idempotent(legacy_diagram):
    diagram, version = legacy_diagram
    _run(_DIAGRAM_MIGRATION, "backfill")
    _run(_DIAGRAM_MIGRATION, "backfill")
    _run(_DIAGRAM_MIGRATION, "verify")
    diagram.refresh_from_db()
    assert diagram.current_revision == version.version_number


def test_diagram_verify_raises_on_an_incomplete_backfill(legacy_diagram):
    """The guard fires; it is not unreachable prose."""
    from diagram.models import Diagram

    diagram, _version = legacy_diagram
    _run(_DIAGRAM_MIGRATION, "backfill")
    Diagram.objects.filter(pk=diagram.pk).update(payload="tampered")

    with pytest.raises(RuntimeError, match="Diagram content backfill incomplete"):
        _run(_DIAGRAM_MIGRATION, "verify")


# ---------------------------------------------------------------------------
# Backfill — Icd
# ---------------------------------------------------------------------------


def test_icd_backfill_copies_the_current_contract(legacy_icd):
    icd, current_version, _current_param, _historical_param = legacy_icd
    assert icd.semantic_description == ""
    assert icd.current_revision == 0

    _run(_ICD_MIGRATION, "backfill")
    icd.refresh_from_db()

    assert icd.direction == current_version.direction
    assert icd.interface_type == current_version.interface_type
    assert icd.semantic_description == current_version.semantic_description
    assert icd.preconditions == current_version.preconditions
    assert icd.postconditions == current_version.postconditions
    assert icd.invariants == current_version.invariants
    assert icd.current_revision == current_version.version_number


def test_icd_backfill_repoints_every_parameter_including_historical(legacy_icd):
    """Option (b): parameters on a non-current version are kept, not dropped.

    ``IcdManager.update_icd`` never copies parameters onto the new version, so
    a parameter created before an update is the ICD's only parameter of that
    name. Backfilling only the current version's would silently delete live,
    user-visible data.
    """
    icd, _current_version, current_param, historical_param = legacy_icd

    _run(_ICD_MIGRATION, "backfill")
    current_param.refresh_from_db()
    historical_param.refresh_from_db()

    assert current_param.icd_id == icd.id
    assert historical_param.icd_id == icd.id


def test_icd_backfill_is_idempotent(legacy_icd):
    icd, current_version, _current_param, _historical_param = legacy_icd
    _run(_ICD_MIGRATION, "backfill")
    _run(_ICD_MIGRATION, "backfill")
    _run(_ICD_MIGRATION, "verify")
    icd.refresh_from_db()
    assert icd.current_revision == current_version.version_number


def test_icd_verify_raises_on_an_incomplete_contract_backfill(legacy_icd):
    from icd.models import Icd

    icd, _cv, _cp, _hp = legacy_icd
    _run(_ICD_MIGRATION, "backfill")
    Icd.objects.filter(pk=icd.pk).update(semantic_description="tampered")

    with pytest.raises(RuntimeError, match="Icd contract backfill incomplete"):
        _run(_ICD_MIGRATION, "verify")


def test_icd_verify_raises_on_an_unowned_parameter(legacy_icd):
    from icd.models import IcdParameter

    _icd, _cv, current_param, _hp = legacy_icd
    _run(_ICD_MIGRATION, "backfill")
    IcdParameter.objects.filter(pk=current_param.pk).update(icd=None)

    with pytest.raises(RuntimeError, match="IcdParameter owner backfill incomplete"):
        _run(_ICD_MIGRATION, "verify")


# ---------------------------------------------------------------------------
# RLS guard — it actually runs, it is not just defined
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "migration_path", [_DIAGRAM_MIGRATION, _ICD_MIGRATION]
)
@pytest.mark.parametrize("func_name", ["backfill", "verify"])
def test_rls_guard_is_actually_executed(migration_path, func_name, legacy_icd):
    """Both entry points must disarm RLS before touching a FORCE-RLS table.

    Without it, a non-BYPASSRLS connection reads an empty table and reports a
    backfill of zero rows as success (persistence/0073's documented failure
    mode).
    """
    # ``verify`` is only meaningful after ``backfill`` has run.
    _run(migration_path, "backfill")

    with CaptureQueriesContext(connection) as captured:
        _run(migration_path, func_name)

    statements = [q["sql"] for q in captured.captured_queries]
    assert any(
        "row_security" in (sql or "").lower() for sql in statements
    ), f"{migration_path}.{func_name} ran without the RLS guard: {statements}"


# ---------------------------------------------------------------------------
# Icd.parameters_snapshot — the by-value bridge Task 28c-2 wires into
# _ENTITY_FIELDS["Icd"]
# ---------------------------------------------------------------------------


def test_parameters_snapshot_is_ordered_and_json_serializable(legacy_icd):
    """``ArtifactVersion.payload`` is a plain JSONField — Decimal would raise."""
    from application.artifact_version_service import snapshot_fields

    icd, _cv, _cp, _hp = legacy_icd
    _run(_ICD_MIGRATION, "backfill")
    icd.refresh_from_db()

    snapshot = icd.parameters_snapshot
    assert [p["name"] for p in snapshot] == ["current_param", "legacy_param"]
    assert snapshot[1]["min_value"] == "1.500000"
    assert snapshot[0]["min_value"] is None
    # Must survive the exact encoder ArtifactVersion.payload uses.
    json.dumps(snapshot)

    # snapshot_fields() resolves plain attributes with getattr, which sees a
    # property transparently — this is what makes the 28c-2 wiring a one-line
    # _ENTITY_FIELDS change rather than a special case.
    assert snapshot_fields(icd, "Icd")["name"] == icd.name
    assert getattr(icd, "parameters_snapshot") == snapshot


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
