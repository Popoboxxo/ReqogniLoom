"""Focused unit tests for the R2C-006 insert-path extraction.

These cases were originally only covered by the end-to-end
``export -> import`` round-trip test (:mod:`test_export_import_roundtrip`).
They now exercise the extracted collaborators directly, with the ORM mocked,
so identity preservation and the ``auto_now`` timestamp bypass can be verified
independently of the full Django DB round-trip (which stays unchanged).
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock

from application.import_service import (
    _ImportContext,
    _ImportRow,
    _create_entity_pair,
    _resolve_import_identity,
)
from application.export_service import ENTITY_FIELD_SPECS

_FIXED_TS = datetime(2020, 1, 2, 3, 4, 5, tzinfo=UTC)
_FIXED_VERSION = 7


def _context(*, entity_type: str = "Requirement", app_model: bool = False) -> _ImportContext:
    """Build a minimal import context whose ORM collaborators are mocks."""
    artifact_model = MagicMock()
    artifact_model.objects.create.return_value = MagicMock(id=uuid.uuid4())

    entity_model = MagicMock()
    entity_model.objects.create.return_value = MagicMock(
        id=uuid.uuid4(), pk=uuid.uuid4()
    )

    models = MagicMock()
    models.artifact = artifact_model

    workspace = MagicMock(id=uuid.uuid4(), tenant=MagicMock(id=uuid.uuid4()))
    lifecycle_status = MagicMock()
    lifecycle_status.values = ["active", "outdated"]
    lifecycle_status.ACTIVE = "active"

    taken_artifact_ids: set[str] = set()
    taken_entity_ids: set[str] = set()

    return _ImportContext(
        entity_type=entity_type,
        spec=ENTITY_FIELD_SPECS[entity_type],
        workspace=workspace,
        tenant=workspace.tenant,
        artifact_type_tag=entity_type,
        definition=None,
        valid_states=None,
        has_status_column=False,
        has_lifecycle_status_column=False,
        entity_model=entity_model,
        lifecycle_status_model=lifecycle_status,
        models=models,
        taken_artifact_ids=taken_artifact_ids,
        taken_entity_ids=taken_entity_ids,
    )


def _row(**identity) -> _ImportRow:
    """Build a parsed row with the given identity columns."""
    return _ImportRow(
        identity=identity,
        content={"title": "T"},
        mapped_status=None,
        lifecycle_status_value=None,
    )


# ---- _resolve_import_identity (identity preservation) ---------------------


def test_resolve_identity_queries_preserved_ids_and_returns_taken_sets():
    artifact_id = uuid.uuid4()
    entity_id = uuid.uuid4()
    artifact_model = MagicMock()
    artifact_model.unscoped.filter.return_value.values_list.return_value = [
        artifact_id
    ]
    entity_model = MagicMock()
    entity_model.unscoped.filter.return_value.values_list.return_value = [entity_id]

    rows = [(1, {"artifact_id": str(artifact_id), "id": str(entity_id)})]
    taken_artifacts, taken_entities = _resolve_import_identity(
        rows,
        ENTITY_FIELD_SPECS["Requirement"],
        artifact_model=artifact_model,
        entity_model=entity_model,
    )

    assert taken_artifacts == {str(artifact_id)}
    assert taken_entities == {str(entity_id)}
    art_kwargs = artifact_model.unscoped.filter.call_args.kwargs
    ent_kwargs = entity_model.unscoped.filter.call_args.kwargs
    assert art_kwargs["id__in"] == [artifact_id]
    assert ent_kwargs["id__in"] == [entity_id]


def test_resolve_identity_skips_empty_cells_and_never_queries():
    artifact_model = MagicMock()
    entity_model = MagicMock()

    rows = [(1, {"artifact_id": "", "id": ""}), (2, {"title": "no ids"})]
    taken_artifacts, taken_entities = _resolve_import_identity(
        rows,
        ENTITY_FIELD_SPECS["Requirement"],
        artifact_model=artifact_model,
        entity_model=entity_model,
    )

    assert taken_artifacts == set()
    assert taken_entities == set()
    artifact_model.unscoped.filter.assert_not_called()
    entity_model.unscoped.filter.assert_not_called()


def test_resolve_identity_free_ids_produce_empty_taken_sets():
    artifact_model = MagicMock()
    artifact_model.unscoped.filter.return_value.values_list.return_value = []
    entity_model = MagicMock()
    entity_model.unscoped.filter.return_value.values_list.return_value = []

    entity_id = uuid.uuid4()
    rows = [(1, {"id": str(entity_id)})]
    taken_artifacts, taken_entities = _resolve_import_identity(
        rows,
        ENTITY_FIELD_SPECS["Requirement"],
        artifact_model=artifact_model,
        entity_model=entity_model,
    )

    assert taken_artifacts == set()
    assert taken_entities == set()


# ---- _create_entity_pair (timestamp preservation) -------------------------


def test_create_entity_pair_preserves_version_id_and_audit_timestamps():
    ic = _context()
    preserved_id = uuid.uuid4()
    preserved_artifact_id = uuid.uuid4()
    parsed = _row(
        id=preserved_id,
        artifact_id=preserved_artifact_id,
        version=_FIXED_VERSION,
        created_at=_FIXED_TS,
        modified_at=_FIXED_TS,
    )
    ctx = MagicMock(user_id=uuid.uuid4())

    _create_entity_pair(parsed, ic=ic, ctx=ctx)

    entity_kwargs = ic.entity_model.objects.create.call_args.kwargs
    assert entity_kwargs["id"] == preserved_id
    assert entity_kwargs["version"] == _FIXED_VERSION
    assert ic.models.artifact.objects.create.call_args.kwargs["id"] == preserved_artifact_id

    # auto_now/auto_now_add are bypassed through a follow-up .update().
    ic.entity_model.objects.filter.assert_called_once_with(pk=ic.entity_model.objects.create.return_value.pk)
    ic.entity_model.objects.filter.return_value.update.assert_called_once_with(
        created_at=_FIXED_TS, modified_at=_FIXED_TS
    )


def test_create_entity_pair_uses_updated_at_for_app_models():
    ic = _context(entity_type="Adr", app_model=True)
    parsed = _row(created_at=_FIXED_TS, updated_at=_FIXED_TS)
    ctx = MagicMock(user_id=uuid.uuid4())

    _create_entity_pair(parsed, ic=ic, ctx=ctx)

    ic.entity_model.objects.filter.return_value.update.assert_called_once_with(
        created_at=_FIXED_TS, updated_at=_FIXED_TS
    )


def test_create_entity_pair_uses_modified_at_when_both_present():
    """``modified_at`` wins over ``updated_at`` on persistence models."""
    ic = _context()
    other_ts = datetime(1999, 1, 1, tzinfo=UTC)
    parsed = _row(modified_at=_FIXED_TS, updated_at=other_ts)

    _create_entity_pair(parsed, ic=ic, ctx=MagicMock(user_id=uuid.uuid4()))

    ic.entity_model.objects.filter.return_value.update.assert_called_once_with(
        modified_at=_FIXED_TS
    )


def test_create_entity_pair_skips_update_without_timestamps():
    """A hand-authored CSV has no audit columns -> no follow-up update."""
    ic = _context()
    parsed = _row()  # no version/timestamps

    _create_entity_pair(parsed, ic=ic, ctx=MagicMock(user_id=uuid.uuid4()))

    ic.entity_model.objects.filter.assert_not_called()
    entity_kwargs = ic.entity_model.objects.create.call_args.kwargs
    assert "version" not in entity_kwargs
    assert "id" not in entity_kwargs


# ---- collision-safe identity during create --------------------------------


def test_create_entity_pair_drops_taken_ids():
    ic = _context()
    preserved_id = uuid.uuid4()
    preserved_artifact_id = uuid.uuid4()
    ic.taken_entity_ids.add(str(preserved_id))
    ic.taken_artifact_ids.add(str(preserved_artifact_id))
    parsed = _row(id=preserved_id, artifact_id=preserved_artifact_id)

    _create_entity_pair(parsed, ic=ic, ctx=MagicMock(user_id=uuid.uuid4()))

    assert "id" not in ic.entity_model.objects.create.call_args.kwargs
    assert "id" not in ic.models.artifact.objects.create.call_args.kwargs


def test_create_entity_pair_marks_adopted_ids_taken_for_next_row():
    """Two rows with the same exported id: only the first may adopt it."""
    ic = _context()
    preserved_id = uuid.uuid4()
    ctx = MagicMock(user_id=uuid.uuid4())

    _create_entity_pair(_row(id=preserved_id), ic=ic, ctx=ctx)
    assert str(preserved_id) in ic.taken_entity_ids

    _create_entity_pair(_row(id=preserved_id), ic=ic, ctx=ctx)
    assert "id" not in ic.entity_model.objects.create.call_args.kwargs
