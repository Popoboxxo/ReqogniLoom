"""Tests for WorkflowStateSerializerMixin (Datenmodell-Konsolidierung Phase 0)."""
import uuid
from unittest.mock import patch

from rest_framework import serializers

from rest_api.mixins.workflow_state import WorkflowStateSerializerMixin


class _Row:
    def __init__(self, pk: uuid.UUID, title: str) -> None:
        self.pk = pk
        self.id = pk
        self.title = title


class _RowSerializer(WorkflowStateSerializerMixin, serializers.Serializer):
    workflow_item_type = "Requirement"
    title = serializers.CharField()


class TestWorkflowStateSerializerMixin:
    def test_single_object_resolves_status(self):
        row = _Row(uuid.uuid4(), "R1")
        with patch(
            "rest_api.mixins.workflow_state.state_reader.current_states",
            return_value={str(row.pk): "approved"},
        ):
            assert _RowSerializer(row).data["status"] == "approved"

    def test_missing_state_is_empty_string(self):
        row = _Row(uuid.uuid4(), "R1")
        with patch(
            "rest_api.mixins.workflow_state.state_reader.current_states",
            return_value={},
        ):
            assert _RowSerializer(row).data["status"] == ""

    def test_list_resolves_all_in_one_lookup(self):
        rows = [_Row(uuid.uuid4(), "R1"), _Row(uuid.uuid4(), "R2")]
        mapping = {str(rows[0].pk): "draft", str(rows[1].pk): "approved"}
        with patch(
            "rest_api.mixins.workflow_state.state_reader.current_states",
            return_value=mapping,
        ) as spy:
            data = _RowSerializer(rows, many=True).data

        assert [entry["status"] for entry in data] == ["draft", "approved"]
        assert spy.call_count == 1

    def test_item_type_is_passed_through(self):
        row = _Row(uuid.uuid4(), "R1")
        with patch(
            "rest_api.mixins.workflow_state.state_reader.current_states",
            return_value={},
        ) as spy:
            _RowSerializer(row).data

        assert spy.call_args[0][0] == "Requirement"

    def test_missing_item_type_raises(self):
        class _Broken(WorkflowStateSerializerMixin, serializers.Serializer):
            title = serializers.CharField()

        row = _Row(uuid.uuid4(), "R1")
        try:
            _Broken(row).data
        except AssertionError as exc:
            assert "workflow_item_type" in str(exc)
        else:  # pragma: no cover - guard
            raise AssertionError("expected AssertionError")
