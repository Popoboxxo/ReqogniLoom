"""Task 28c-2 confirmation tests: ``IcdVersion``/``DiagramVersion`` are retired.

Datenmodell-Konsolidierung Task 28c-2 — the Contract half of the
Expand/Migrate/Contract. Mirrors
``persistence/tests/test_glossary_term_version_dropped.py`` (Task 28b): prove
both that the old store is genuinely gone (model *and* table) and that the
replacement path works end to end, so "the old thing is gone" can never pass
while the new one is broken.

Also pins the two behaviours this task had to *decide* rather than port:

* ``parameters_snapshot`` is recorded into every ``ArtifactVersion`` payload,
  and stays JSON-serialisable (``Decimal`` bounds are stringified).
* the revision counter on the header and ``ArtifactVersion.revision`` are
  allocated together and never diverge.
"""
from __future__ import annotations

import contextlib
import json
import uuid
from typing import Iterator
from unittest.mock import patch

import pytest
from django.apps import apps
from django.db import connection

from icd.services import (
    IcdCreateDTO,
    IcdParameterCreateDTO,
    IcdUpdateDTO,
    create_icd,
    create_icd_parameter,
    get_icd_history,
    update_icd,
)
from persistence.models import ArtifactVersion, Tenant, Workspace
from persistence.tenancy import TenantContext


# ---------------------------------------------------------------------------
# Test helpers — declared locally, matching the convention the two sibling
# icd test modules already follow (neither uses a conftest).
# ---------------------------------------------------------------------------


@contextlib.contextmanager
def active_tenant(tenant: Tenant) -> Iterator[None]:
    """Activate tenant context for the app-layer manager within the block."""
    TenantContext.set_tenant(tenant.id)
    try:
        yield
    finally:
        TenantContext.clear_tenant()


@pytest.fixture(autouse=True)
def _clear_tenant_context() -> Iterator[None]:
    TenantContext.clear_tenant()
    yield
    TenantContext.clear_tenant()


@pytest.fixture(autouse=True)
def _mock_resolve_arch_artifact_id() -> Iterator[None]:
    with patch(
        "icd.icd_manager.IcdManager._resolve_arch_artifact_id",
        side_effect=lambda x: x,
    ):
        yield


@pytest.fixture
def tenant_a(db) -> Tenant:
    return Tenant.objects.create(name="Tenant A", slug="ta-icd-retired")


@pytest.fixture
def workspace_id(tenant_a: Tenant) -> uuid.UUID:
    """A real Workspace row's id — ``ensure_artifact`` needs a valid FK."""
    with active_tenant(tenant_a):
        return Workspace.objects.create(tenant=tenant_a, name="ICD-Retire-WS").id


@pytest.fixture
def src_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def tgt_id() -> uuid.UUID:
    return uuid.uuid4()


# ---------------------------------------------------------------------------
# The old stores are gone
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("app_label", "model_name"),
    [("icd", "IcdVersion"), ("diagram", "DiagramVersion")],
)
def test_model_is_unregistered(app_label: str, model_name: str) -> None:
    with pytest.raises(LookupError):
        apps.get_model(app_label, model_name)


@pytest.mark.django_db
@pytest.mark.parametrize("table", ["icd_version", "diagram_diagramversion"])
def test_table_is_dropped(table: str) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_name = %s",
            [table],
        )
        assert cursor.fetchone()[0] == 0


@pytest.mark.django_db
def test_icd_version_immutability_function_is_dropped() -> None:
    """``icd/0006``'s trigger function must not outlive the table it guarded.

    ``DROP TABLE`` removes the trigger but not the standalone function, so
    ``icd/0013`` drops it explicitly. Asserted rather than assumed, because a
    leftover ``plpgsql`` function is invisible in every ORM-level check.
    """
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM pg_proc WHERE proname = 'icd_raise_version_immutable'"
        )
        assert cursor.fetchone()[0] == 0


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("table", "column"),
    [
        ("icd_icd", "current_version_id"),
        ("diagram_diagram", "current_version_id"),
        ("icd_parameter", "icd_version_id"),
    ],
)
def test_pointer_column_is_dropped(table: str, column: str) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM information_schema.columns "
            "WHERE table_name = %s AND column_name = %s",
            [table, column],
        )
        assert cursor.fetchone()[0] == 0


@pytest.mark.django_db
def test_icd_parameter_owner_is_mandatory() -> None:
    """``IcdParameter.icd`` is the owner now, so it may not be NULL."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT is_nullable FROM information_schema.columns "
            "WHERE table_name = 'icd_parameter' AND column_name = 'icd_id'"
        )
        assert cursor.fetchone()[0] == "NO"


# ---------------------------------------------------------------------------
# The replacement path works end to end
# ---------------------------------------------------------------------------


def _create(tenant, workspace_id, src_id, tgt_id, **overrides):
    dto = IcdCreateDTO(
        tenant_id=tenant.id,
        workspace_id=workspace_id,
        name="Retirement ICD",
        source_element_id=src_id,
        target_element_id=tgt_id,
        interface_type="provides",
        semantic_description="v1",
        **overrides,
    )
    with patch(
        "icd.traceability_connector.TraceabilityConnector.link_to_architecture"
    ):
        return create_icd(dto)


@pytest.mark.django_db
class TestContractHistoryViaArtifactVersion:
    """The whole point of the retirement: history still reads back correctly."""

    def test_every_revision_is_readable_after_the_drop(
        self, tenant_a, workspace_id, src_id, tgt_id
    ) -> None:
        with active_tenant(tenant_a):
            result = _create(tenant_a, workspace_id, src_id, tgt_id)
            update_icd(
                icd_id=result.icd.id,
                payload=IcdUpdateDTO(semantic_description="v2"),
                tenant_id=tenant_a.id,
            )
            update_icd(
                icd_id=result.icd.id,
                payload=IcdUpdateDTO(semantic_description="v3"),
                tenant_id=tenant_a.id,
            )
            history = get_icd_history(result.icd.id, tenant_a.id)
            result.icd.refresh_from_db()

        assert [h.version_number for h in history] == [1, 2, 3]
        assert [h.semantic_description for h in history] == ["v1", "v2", "v3"]
        # The header counter and the revision numbers are allocated together.
        assert result.icd.current_revision == 3
        assert result.icd.semantic_description == "v3"

    def test_header_revision_matches_the_recorded_revisions(
        self, tenant_a, workspace_id, src_id, tgt_id
    ) -> None:
        """No second numbering space: ``current_revision`` IS ``MAX(revision)``."""
        with active_tenant(tenant_a):
            result = _create(tenant_a, workspace_id, src_id, tgt_id)
            update_icd(
                icd_id=result.icd.id,
                payload=IcdUpdateDTO(direction="bidirectional"),
                tenant_id=tenant_a.id,
            )
            result.icd.refresh_from_db()
            revisions = sorted(
                ArtifactVersion.unscoped.filter(
                    artifact_id=result.icd.artifact_id, tenant_id=tenant_a.id
                ).values_list("revision", flat=True)
            )

        assert revisions == [1, 2]
        assert result.icd.current_revision == revisions[-1]


@pytest.mark.django_db
class TestParametersSnapshotWiring:
    """``parameters_snapshot`` is stored *and* diffed — the same set, by name."""

    def test_snapshot_is_recorded_into_the_revision_payload(
        self, tenant_a, workspace_id, src_id, tgt_id
    ) -> None:
        with active_tenant(tenant_a):
            result = _create(tenant_a, workspace_id, src_id, tgt_id)
            create_icd_parameter(
                IcdParameterCreateDTO(
                    icd_id=result.icd.id,
                    name="voltage",
                    unit="V",
                    min_value=1,
                    max_value=5,
                ),
                tenant_id=tenant_a.id,
            )
            update_icd(
                icd_id=result.icd.id,
                payload=IcdUpdateDTO(semantic_description="v2"),
                tenant_id=tenant_a.id,
            )
            payloads = {
                row.revision: row.payload
                for row in ArtifactVersion.unscoped.filter(
                    artifact_id=result.icd.artifact_id, tenant_id=tenant_a.id
                )
            }

        # Revision 1 predates the parameter, revision 2 captures it by value.
        assert payloads[1]["parameters_snapshot"] == []
        assert [p["name"] for p in payloads[2]["parameters_snapshot"]] == ["voltage"]
        assert payloads[2]["parameters_snapshot"][0]["unit"] == "V"

    def test_snapshot_payload_stays_json_serialisable(
        self, tenant_a, workspace_id, src_id, tgt_id
    ) -> None:
        """``ArtifactVersion.payload`` has no custom encoder, and ``json.dumps``
        rejects ``Decimal`` — the numeric bounds must arrive as strings."""
        with active_tenant(tenant_a):
            result = _create(tenant_a, workspace_id, src_id, tgt_id)
            create_icd_parameter(
                IcdParameterCreateDTO(
                    icd_id=result.icd.id, name="current", min_value=2, max_value=7
                ),
                tenant_id=tenant_a.id,
            )
            update_icd(
                icd_id=result.icd.id,
                payload=IcdUpdateDTO(semantic_description="v2"),
                tenant_id=tenant_a.id,
            )
            payload = ArtifactVersion.unscoped.get(
                artifact_id=result.icd.artifact_id, revision=2
            ).payload

        json.dumps(payload)  # must not raise
        entry = payload["parameters_snapshot"][0]
        assert isinstance(entry["min_value"], str)
        assert entry["min_value"] == "2.000000"

    def test_stored_keys_match_the_diffable_field_list(
        self, tenant_a, workspace_id, src_id, tgt_id
    ) -> None:
        """``icd_manager`` hand-builds the payload (ADR-01 forbids importing
        Layer 2), so the two lists can silently drift. Pin them together."""
        from application.artifact_diff_service import _ENTITY_FIELDS

        with active_tenant(tenant_a):
            result = _create(tenant_a, workspace_id, src_id, tgt_id)
            payload = ArtifactVersion.unscoped.get(
                artifact_id=result.icd.artifact_id, revision=1
            ).payload

        assert set(payload) == set(_ENTITY_FIELDS["Icd"])


@pytest.mark.django_db
class TestEmbeddingIsRetryableNow:
    """A capability the immutable ``IcdVersion`` could not offer."""

    def test_failed_generation_is_recovered_by_the_next_update(
        self, monkeypatch, tenant_a, workspace_id, src_id, tgt_id
    ) -> None:
        monkeypatch.setattr(
            "llm_adapter.embedding_service.generate_embedding",
            lambda text: None,
        )
        with active_tenant(tenant_a):
            result = _create(tenant_a, workspace_id, src_id, tgt_id)
            result.icd.refresh_from_db()
            assert result.icd.embedding is None

            from icd.models import Icd

            width = Icd._meta.get_field("embedding").dimensions
            monkeypatch.setattr(
                "llm_adapter.embedding_service.generate_embedding",
                lambda text: [0.2] * width,
            )
            update_icd(
                icd_id=result.icd.id,
                payload=IcdUpdateDTO(semantic_description="retry"),
                tenant_id=tenant_a.id,
            )
            result.icd.refresh_from_db()

        assert result.icd.embedding is not None
        assert len(result.icd.embedding) == width


@pytest.mark.django_db
class TestParameterDuplicateNamesAreTolerated:
    """Task 28c-2 decision: the flattening does not de-duplicate by name.

    Two same-named parameters were always representable on one contract (no
    unique constraint has ever existed on ``(icd, name)``), so the flattening
    introduces no new invalid state — it only makes the pre-existing one
    reachable from a second direction. Dropping a row in a migration is never
    the right default, and both rows stay individually addressable by id
    through ``/api/v1/icds/<pk>/parameters/``.
    """

    def test_two_parameters_may_share_a_name(
        self, tenant_a, workspace_id, src_id, tgt_id
    ) -> None:
        from icd.services import list_icd_parameters

        with active_tenant(tenant_a):
            result = _create(tenant_a, workspace_id, src_id, tgt_id)
            for unit in ("V", "mV"):
                create_icd_parameter(
                    IcdParameterCreateDTO(
                        icd_id=result.icd.id, name="voltage", unit=unit
                    ),
                    tenant_id=tenant_a.id,
                )
            rows = list(list_icd_parameters(result.icd.id, tenant_a.id))

        assert [r.name for r in rows] == ["voltage", "voltage"]
        assert len({r.id for r in rows}) == 2


@pytest.mark.django_db
def test_unknown_icd_history_is_empty_not_an_error(tenant_a) -> None:
    """A missing ICD reads as "no history", matching the previous behaviour of
    filtering a version table that had no matching rows."""
    with active_tenant(tenant_a):
        assert get_icd_history(uuid.uuid4(), tenant_a.id) == []
