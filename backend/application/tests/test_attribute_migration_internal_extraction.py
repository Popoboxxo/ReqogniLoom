"""Regression gates for the S4.1 WP-4 AWMS internal extraction.

R2C-004 pins the facade re-export shims (the public class, import path and
method signatures are unchanged) and R2C-005 pins the ``StepContext`` handler
interface.  The parametrized round-trip replays all 14 ops through
``_execute_step`` in both dry-run and apply mode and compares the full report
against a golden snapshot taken from the pre-refactor implementation.

These tests are deliberately DB-free: every persistence boundary is mocked, so
they also run when the shared PostgreSQL test server is unavailable.
"""
from __future__ import annotations

import ast
import inspect
import json
import uuid
from contextlib import nullcontext
from dataclasses import FrozenInstanceError, is_dataclass
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from django.core.exceptions import FieldDoesNotExist

from application import attribute_migration_helpers as helpers
from application import attribute_migration_service as facade
from application.attribute_migration_helpers import (
    ExpressionRenderer,
    RunContext,
    StepContext,
)
from attribute_definitions.migration_plan import normalize_plan
from auth_tenancy.context import AuthContext, AuthMethod

FIXTURE = Path(__file__).parent / "fixtures" / "awms_stepcontext_golden.json"

WS_IDS = [
    uuid.UUID("11111111-1111-4111-8111-111111111111"),
    uuid.UUID("22222222-2222-4222-8222-222222222222"),
]
RUN_ID = uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
TENANT_ID = uuid.UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")

HANDLER_ORDER = [
    "migrate_value",
    "map_value",
    "backfill_value",
    "derive_value",
    "split_attribute",
    "merge_attribute",
    "rename_attribute",
    "retype_attribute",
    "define_attribute",
    "drop_attribute",
    "deprecate_attribute",
    "requeue_definition",
    "export_scope",
    "import_scope",
]

EXPORT_DOCUMENT = {"schema_version": 1, "item_type": "Requirement", "attributes": []}

RAW_STEPS: dict[str, dict[str, Any]] = {
    "migrate_value": {
        "op": "migrate_value",
        "from": {"source": "custom_field", "name": "source"},
        "to": {"source": "custom_field", "name": "title"},
        "mode": "copy",
    },
    "map_value": {
        "op": "map_value",
        "target": {"source": "custom_field", "name": "title"},
        "value_map": {"title-1": "one", "title-2": "two"},
        "fallback": "other",
    },
    "backfill_value": {
        "op": "backfill_value",
        "target": {"source": "custom_field", "name": "fresh"},
        "value_strategy": "constant",
        "value": "filled",
    },
    "derive_value": {
        "op": "derive_value",
        "target": {"source": "custom_field", "name": "title"},
        "expression": "{source}-{uid}",
    },
    "split_attribute": {
        "op": "split_attribute",
        "from": {"source": "custom_field", "name": "source"},
        "separator": "-",
        "targets": [
            {"to": {"source": "custom_field", "name": "title"}},
            {"to": {"source": "custom_field", "name": "priority"}},
        ],
    },
    "merge_attribute": {
        "op": "merge_attribute",
        "sources": [
            {"source": "custom_field", "name": "source"},
            {"source": "custom_field", "name": "title"},
        ],
        "to": {"source": "custom_field", "name": "priority"},
    },
    "rename_attribute": {
        "op": "rename_attribute",
        "from": {"source": "custom_field", "name": "source"},
        "to": {"source": "custom_field", "name": "renamed"},
    },
    "retype_attribute": {"op": "retype_attribute", "name": "rationale", "new_type": "textarea"},
    "define_attribute": {"op": "define_attribute", "name": "new_attr", "kind": "extended"},
    "drop_attribute": {"op": "drop_attribute", "name": "rationale", "confirm": "rationale"},
    "deprecate_attribute": {
        "op": "deprecate_attribute",
        "name": "rationale",
        "reason": "superseded",
    },
    "requeue_definition": {
        "op": "requeue_definition",
        "preset": ["standard"],
        "action": "reset_uncustomized",
    },
    "export_scope": {"op": "export_scope", "source": {"preset": "standard"}},
    "import_scope": {
        "op": "import_scope",
        "document": EXPORT_DOCUMENT,
        "target": {"preset": "standard"},
        "on_collision": "skip",
    },
}


# ---------------------------------------------------------------------------
# DB-free fixtures for the step replay
# ---------------------------------------------------------------------------


class _Field:
    def __init__(self, name: str) -> None:
        self.name = name
        self.is_relation = False


class _Meta:
    def __init__(self, names: tuple[str, ...]) -> None:
        self._names = names

    def get_fields(self) -> list[_Field]:
        return [_Field(name) for name in self._names]

    def get_field(self, name: str) -> _Field:
        if name in self._names:
            return _Field(name)
        raise FieldDoesNotExist(name)


class _Artifact:
    def __init__(self, index: int) -> None:
        self.custom_fields = {
            "source": f"alpha-{index}",
            "title": f"title-{index}",
            "priority": f"prio-{index}",
            "fresh": None,
        }
        self.workspace_id = WS_IDS[index % len(WS_IDS)]
        self.version = 1
        self.artifact_type = "Requirement"


class _Row:
    _meta = _Meta(("title", "uid", "moscow_priority"))

    def __init__(self, index: int) -> None:
        self.id = index
        suffix = "000000000000" if index == 1 else "000000000001"
        self.artifact_id = uuid.UUID(f"dddddddd-dddd-4ddd-8ddd-{suffix}")
        self.uid = f"REQ-{index:03d}"
        self.title = f"title-{index}"
        self.version = 1
        self.artifact = _Artifact(index)


class _WorkspaceRow:
    def __init__(self, index: int) -> None:
        self.id = index
        self.preset = "standard"
        self.is_customized = False
        self.definition_json = {"attributes": []}
        self.source_global = None
        self.version = 1


ROWS = [_Row(1), _Row(2)]
WORKSPACES = [{"id": ws_id, "preset": "standard"} for ws_id in WS_IDS]
DEFINITION_TARGETS = [{"kind": "global", "preset": "standard"}]
DEFINITION_ATTRIBUTES = [
    {"name": "source", "kind": "extended", "type": "text"},
    {"name": "rationale", "kind": "extended", "type": "text"},
]
CTX = AuthContext(
    user_id=uuid.UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc"),
    tenant_id=TENANT_ID,
    workspace_id=WS_IDS[0],
    active_roles=("admin",),
    auth_method=AuthMethod.BEARER_TOKEN,
)


def _raw_plan(steps: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "version": 1,
        "id": "s41wp4-golden",
        "description": "golden harness",
        "scope": {
            "tenant": "current",
            "item_type": "Requirement",
            "preset": ["standard"],
            "workspace": "*",
        },
        "mode": "apply",
        "options": {"idempotent": True, "abort_on_error": True, "audit": True},
        "steps": steps,
    }


def _replay(op: str, *, write: bool) -> dict[str, Any]:
    """Run one op through ``_execute_step`` with all persistence mocked."""
    plan = normalize_plan(_raw_plan([RAW_STEPS[op]]))
    service = facade.AttributeMigrationService()
    run = MagicMock()
    run.id = RUN_ID
    run.plan_id = "s41wp4-golden"
    snapshot_ids: list[str] = []
    call_log: list[Any] = []

    definitions = MagicMock()
    definitions.export_definition.return_value = EXPORT_DOCUMENT
    service._definitions = definitions

    def fake_snapshot(ctx, run_arg, item_type, target, snap_ids):
        call_log.append(["snapshot", item_type, target["kind"], target.get("preset")])
        snap_ids.append("snap-fixed")
        return f"fixed:{item_type}:{target['kind']}"

    def fake_persist(ctx, run_arg, row, changes, snap_ids, **kwargs):
        call_log.append(["persist", row.id, sorted(changes)])

    def fake_save(ctx, item_type, target, attributes):
        call_log.append(
            ["save_definition", item_type, target["kind"], sorted(a["name"] for a in attributes)]
        )

    def fake_read(ctx, item_type, target):
        return list(DEFINITION_ATTRIBUTES)

    context = StepContext(
        ctx=CTX,
        run=run,
        plan=plan,
        item_type=plan["scope"]["item_type"],
        workspaces=list(WORKSPACES),
        run_context=RunContext(
            write=write, audit_artifacts=True, snapshot_ids=snapshot_ids
        ),
    )
    with (
        patch.object(service, "_rows", side_effect=lambda *a, **k: list(ROWS)),
        patch.object(service, "_resolve_workspaces", side_effect=lambda *a, **k: list(WORKSPACES)),
        patch.object(service, "_definition_targets", side_effect=lambda *a, **k: list(DEFINITION_TARGETS)),
        patch.object(service, "_snapshot_definition", side_effect=fake_snapshot),
        patch.object(service, "_save_definition", side_effect=fake_save),
        patch.object(service, "_read_definition", side_effect=fake_read),
        patch.object(service, "_persist", side_effect=fake_persist),
        patch.object(service, "_workspace_row_in_sync", return_value=False),
        patch.object(service, "_audit", return_value=None),
        patch(
            "attribute_definitions.models.WorkspaceAttributeDefinition.objects.filter",
            side_effect=lambda *a, **k: [_WorkspaceRow(1), _WorkspaceRow(2)],
        ),
    ):
        outcome = service._execute_step(plan["steps"][0], context)
    return {"outcome": outcome, "snapshot_ids": snapshot_ids, "calls": call_log}


# ---------------------------------------------------------------------------
# R2C-004 — facade / re-export identity
# ---------------------------------------------------------------------------


def test_public_class_name_and_import_path_are_unchanged() -> None:
    from application.attribute_migration_service import AttributeMigrationService

    assert AttributeMigrationService is facade.AttributeMigrationService
    assert AttributeMigrationService.__module__ == "application.attribute_migration_service"
    assert facade.__all__ == [
        "AttributeMigrationConflict",
        "AttributeMigrationNotFound",
        "AttributeMigrationService",
    ]
    # The public exception types are part of the facade contract too.
    assert facade.AttributeMigrationNotFound.__module__ == "application.attribute_migration_service"
    assert facade.AttributeMigrationConflict.__module__ == "application.attribute_migration_service"
    assert issubclass(facade.AttributeMigrationNotFound, Exception)
    assert issubclass(facade.AttributeMigrationConflict, ValueError)


def test_public_method_signatures_are_unchanged() -> None:
    expected_params = {
        "validate_plan": ["self", "payload"],
        "dry_run": ["self", "ctx", "payload"],
        "apply": ["self", "ctx", "payload"],
        "rollback": ["self", "ctx", "run_id"],
        "list_runs": ["self", "ctx"],
        "get_run": ["self", "ctx", "run_id"],
    }
    public = {
        name
        for name, value in vars(facade.AttributeMigrationService).items()
        if callable(value) and not name.startswith("_")
    }
    assert public == set(expected_params)
    for name, params in expected_params.items():
        assert list(inspect.signature(getattr(facade.AttributeMigrationService, name)).parameters)[
            : len(params)
        ] == params


def test_pure_helpers_are_reexported_by_identity() -> None:
    """The facade's import surface stays intact after the helper extraction."""
    names = [
        "_ARTIFACT_ACTOR_FIELDS",
        "_ArtifactBatch",
        "_EMPTY",
        "_facts",
        "_INTERNAL_FAILURE_MESSAGE",
        "_is_blank",
        "_ITEM_MODEL_CANDIDATES",
        "_json_safe",
        "_PARTIALLY_ROLLED_BACK",
        "_REMOVE",
        "_ROLLED_BACK",
        "_RUN_APPLY",
        "_RUN_DRY_RUN",
        "_SAMPLE_FIELD_PREFIX_DEFINITION",
        "_SafeFormat",
        "_Sentinel",
        "_STATUS_CHANGED",
        "_STATUS_FAILED",
        "_STATUS_SKIPPED",
        "_STATUS_UNCHANGED",
        "_StepAbort",
        "_UNSET",
        "ExpressionRenderer",
        "RunContext",
        "StepContext",
    ]
    for name in names:
        assert getattr(facade, name) is getattr(helpers, name), name
    assert facade._EMPTY is helpers._EMPTY
    assert facade._ArtifactBatch is helpers._ArtifactBatch


def test_service_is_not_split_into_four_public_facades() -> None:
    """S4.2 owns the structural split; WP-4 only extracts internal helpers."""
    assert not hasattr(facade, "MigrationRunStore")
    assert not hasattr(facade, "MigrationStepHandlers")
    assert not hasattr(facade, "DefinitionSnapshotter")
    assert facade.AttributeMigrationService.__name__ == "AttributeMigrationService"


# ---------------------------------------------------------------------------
# R2C-005 — immutable context + dead-parameter lint
# ---------------------------------------------------------------------------


def test_contexts_are_frozen_dataclasses() -> None:
    run_context = RunContext(write=True, audit_artifacts=True, snapshot_ids=[])
    step_context = StepContext(
        ctx=CTX,
        run=None,
        plan={},
        item_type="Requirement",
        workspaces=[],
        run_context=run_context,
    )
    assert is_dataclass(run_context) and is_dataclass(step_context)
    assert step_context.write is True
    assert step_context.audit_artifacts is True
    assert step_context.snapshot_ids is run_context.snapshot_ids
    with pytest.raises(FrozenInstanceError):
        run_context.write = False
    with pytest.raises(FrozenInstanceError):
        step_context.item_type = "Other"


def test_no_handler_declares_a_parameter_it_never_reads() -> None:
    """AST lint: all 14 handlers take exactly ``(step, context)`` and read both."""
    tree = ast.parse(Path(facade.__file__).read_text(encoding="utf-8"))
    cls = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "AttributeMigrationService"
    )
    execute = next(
        node
        for node in cls.body
        if isinstance(node, ast.FunctionDef) and node.name == "_execute_step"
    )
    handler_names: set[str] = set()
    for node in ast.walk(execute):
        if isinstance(node, ast.Dict):
            for value in node.values:
                if (
                    isinstance(value, ast.Attribute)
                    and isinstance(value.value, ast.Name)
                    and value.value.id == "self"
                ):
                    handler_names.add(value.attr)
    assert handler_names == {
        "_step_" + op for op in HANDLER_ORDER
    }, "handler dict must stay the OCP seam for all 14 ops"

    for name in sorted(handler_names):
        fn = next(
            node
            for node in cls.body
            if isinstance(node, ast.FunctionDef) and node.name == name
        )
        params = [arg.arg for arg in fn.args.args if arg.arg != "self"]
        assert params == ["step", "context"], f"{name} has stale handler params: {params}"
        loaded = {
            node.id
            for node in ast.walk(fn)
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
        }
        unread = [param for param in params if param not in loaded]
        assert not unread, f"{name} declares unread parameter(s): {unread}"


def test_flush_forwards_run_context_to_persist() -> None:
    """The audit decision comes from RunContext, not from instance state."""
    service = facade.AttributeMigrationService()
    batch = helpers._ArtifactBatch()
    batch.changes["x"] = (True, "value")
    batch.staged.append(({"kind": "custom_field", "name": "x"}, None, "value"))
    outcome = facade.AttributeMigrationService._empty_outcome()
    run_context = RunContext(write=True, audit_artifacts=False, snapshot_ids=[])
    with patch.object(service, "_persist") as persist:
        service._flush(
            CTX,
            MagicMock(),
            _Row(1),
            batch,
            write=True,
            outcome=outcome,
            snapshot_ids=[],
            run_context=run_context,
        )
    assert persist.call_args.kwargs["run_context"] is run_context


def test_persist_honours_run_context_audit_flag_with_a_legacy_fallback() -> None:
    service = facade.AttributeMigrationService()
    run = MagicMock()
    # An empty change set reaches the audit branch without touching the ORM.
    with (
        patch.object(facade.transaction, "atomic", return_value=nullcontext()),
        patch.object(service, "_audit") as audit,
    ):
        service._audit_artifacts = True  # stale mirror would audit
        service._persist(
            CTX,
            run,
            _Row(1),
            {},
            [],
            run_context=RunContext(write=True, audit_artifacts=False, snapshot_ids=[]),
        )
        audit.assert_not_called()
        service._persist(
            CTX,
            run,
            _Row(1),
            {},
            [],
            run_context=RunContext(write=True, audit_artifacts=True, snapshot_ids=[]),
        )
        audit.assert_called_once()
        audit.reset_mock()
        service._persist(CTX, run, _Row(1), {}, [])  # legacy call uses mirror
        audit.assert_called_once()


def test_expression_renderer_is_pure_and_keeps_missing_placeholders() -> None:
    """The extracted renderer preserves the closed-evaluator semantics."""
    row = _Row(1)
    renderer = ExpressionRenderer(artifact_model=MagicMock())
    assert renderer.render(row, "{source}-{uid}") == "alpha-1-REQ-001"
    assert renderer.render(row, "{unknown}") == "{unknown}"


# ---------------------------------------------------------------------------
# Parametrized round-trip over all 14 ops (pre/post output snapshots)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("op", HANDLER_ORDER)
@pytest.mark.parametrize("write", [False, True], ids=["dry_run", "apply"])
def test_all_step_handlers_match_the_pre_refactor_snapshot(op: str, write: bool) -> None:
    golden = json.loads(FIXTURE.read_text(encoding="utf-8"))
    expected = golden["dry_run" if not write else "apply"][op]
    assert _replay(op, write=write) == expected
