"""R2C-003 — RequirementUpdate command DTO and legacy-call parity.

The compatibility wrapper must be observationally identical to the DTO path:
the same optional fields, present or absent, have to produce the same
persisted row. These tests pin that contract (plus the ``UNSET`` vs ``None``
partial-PATCH distinction it is built to preserve).
"""
from __future__ import annotations

import inspect
from contextlib import nullcontext
from dataclasses import FrozenInstanceError, fields
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest

import application.requirement_service as requirement_service_module
from application.requirement_service import RequirementService
from application.requirement_update import RequirementUpdate
from application.sentinels import UNSET
from persistence.models import Requirement
from persistence.tests.factories import (
    active_tenant,
    editor_ctx,
    make_requirement,
    make_workspace,
)

# ---------------------------------------------------------------------------
# Command shape (no DB)
# ---------------------------------------------------------------------------


def test_every_optional_field_defaults_to_the_shared_sentinel():
    assert all(getattr(RequirementUpdate(), f.name) is UNSET for f in fields(RequirementUpdate))
    assert requirement_service_module._UNSET is UNSET  # R2C-002: one identity


def test_command_is_frozen():
    command = RequirementUpdate()
    with pytest.raises(FrozenInstanceError):
        command.title = "nope"


def test_from_kwargs_only_sets_present_keys():
    command = RequirementUpdate.from_kwargs(
        {"title": "present", "complexity_fibonacci": None, "unknown_key": "ignored"}
    )
    assert command.title == "present"
    assert command.complexity_fibonacci is None  # explicit None is a value
    assert command.description is UNSET
    assert not hasattr(command, "unknown_key")


def test_from_validated_data_only_forwards_present_fields():
    command = RequirementUpdate.from_validated_data(
        {
            "title": "present",
            "complexity_fibonacci": None,
            "uid": "read-only-must-not-leak",
            "level": 4,
            "acceptance_criteria_items": [],
        },
        expected_version=7,
    )
    assert command.title == "present"
    assert command.complexity_fibonacci is None
    assert command.expected_version == 7
    # Serializer read-only / transport-only keys are not command fields.
    assert command.uid is UNSET
    assert not hasattr(command, "level")
    assert not hasattr(command, "acceptance_criteria_items")


def test_public_method_keeps_the_legacy_keyword_signature():
    """No ``**kwargs``: unsupported keywords (status, level) stay TypeErrors."""
    params = inspect.signature(RequirementService.update_requirement).parameters
    assert list(params)[:3] == ["self", "requirement_id", "ctx"]
    assert "command" in params
    assert params["command"].kind is inspect.Parameter.KEYWORD_ONLY
    for legacy in ("title", "change_reason", "complexity_fibonacci", "expected_version"):
        assert legacy in params
    assert not any(
        p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()
    )


def test_wrapper_builds_equivalent_command_from_legacy_kwargs():
    """The compat wrapper maps every legacy keyword into the same command."""
    captured: dict = {}
    sentinel = object()

    def fake_apply(self, requirement_id, ctx, command):
        captured["command"] = command
        return sentinel

    # The public method is atomic; stub the transaction so this stays DB-free.
    with (
        patch("persistence.transactions.transaction.atomic", return_value=nullcontext()),
        patch.object(RequirementService, "_apply_requirement_update", fake_apply),
    ):
        result = RequirementService().update_requirement(
            UUID(int=1),
            MagicMock(),
            title="T",
            change_reason="why",
            complexity_fibonacci=None,
            parent_id=None,
            expected_version=3,
        )

    assert result is sentinel
    assert captured["command"] == RequirementUpdate(
        title="T",
        change_reason="why",
        complexity_fibonacci=None,
        parent_id=None,
        expected_version=3,
    )


def test_explicit_command_wins_over_legacy_kwargs():
    command = RequirementUpdate(title="from-command")
    captured: dict = {}

    def fake_apply(self, requirement_id, ctx, received):
        captured["command"] = received
        return None

    with (
        patch("persistence.transactions.transaction.atomic", return_value=nullcontext()),
        patch.object(RequirementService, "_apply_requirement_update", fake_apply),
    ):
        RequirementService().update_requirement(
            UUID(int=1), MagicMock(), title="ignored", command=command
        )
    assert captured["command"] is command


# ---------------------------------------------------------------------------
# Persisted-result parity (real DB)
# ---------------------------------------------------------------------------


def _service() -> RequirementService:
    service = RequirementService()
    policy = MagicMock()
    policy.is_change_reason_required.return_value = False
    service._preset_policy = policy
    return service


def _update_via_kwargs(requirement_id, ctx, **kwargs) -> None:
    _service().update_requirement(requirement_id, ctx, **kwargs)


def _update_via_command(requirement_id, ctx, command: RequirementUpdate) -> None:
    _service().update_requirement(requirement_id, ctx, command=command)


def _snapshot(requirement: Requirement) -> dict:
    """Persisted, comparable projection (parent_id asserted separately)."""
    row = Requirement.unscoped.select_related("artifact").get(id=requirement.id)
    return {
        "title": row.title,
        "description": row.description,
        "acceptance_criteria": row.acceptance_criteria,
        "rationale": row.rationale,
        "source": row.source,
        "category": row.category,
        "type": row.type,
        "complexity_fibonacci": row.complexity_fibonacci,
        "verification_method": row.verification_method,
        "uid": row.uid,
        "suspect": row.suspect,
        "allocation_intent": row.allocation_intent,
        "version": row.version,
        "custom_fields": row.artifact.custom_fields,
    }


def _setup_pair():
    """Two identical requirement rows in two workspaces of one tenant."""
    tenant_context = active_tenant()
    tenant = tenant_context.__enter__()
    ws_kwargs = make_workspace(tenant, name="DTO parity A")
    ws_command = make_workspace(tenant, name="DTO parity B")
    ctx_kwargs = editor_ctx(tenant, ws_kwargs)
    ctx_command = editor_ctx(tenant, ws_command)
    parent_kwargs = make_requirement(ws_kwargs, title="Parent A")
    parent_command = make_requirement(ws_command, title="Parent B")
    # Same uid in both workspaces: the uniqueness guard is workspace-scoped,
    # and identical seeds let the whole persisted projection be compared.
    child_kwargs = make_requirement(
        ws_kwargs, title="Original", description="orig", uid="REQ-PARITY"
    )
    child_command = make_requirement(
        ws_command, title="Original", description="orig", uid="REQ-PARITY"
    )
    return (
        tenant_context,
        ctx_kwargs,
        ctx_command,
        parent_kwargs,
        parent_command,
        child_kwargs,
        child_command,
    )


@pytest.mark.django_db
def test_parity_all_optional_fields_present():
    (
        tenant_context,
        ctx_kwargs,
        ctx_command,
        parent_kwargs,
        parent_command,
        child_kwargs,
        child_command,
    ) = _setup_pair()
    try:
        def values(parent_id):
            return dict(
                title="Parity title",
                description="Parity description",
                acceptance_criteria="Given / When / Then",
                rationale="Parity rationale",
                source="SPEC-PARITY",
                category="Functional",
                type="SyReq",
                change_reason="parity-test",
                complexity_fibonacci=5,
                verification_method="Test",
                uid="REQ-PARITY",
                suspect=True,
                allocation_intent="not_allocatable",
                custom_fields={"k": "v"},
                parent_id=parent_id,
                expected_version=1,
            )

        kwargs_values = values(parent_kwargs.artifact_id)
        command_values = values(parent_command.artifact_id)

        _update_via_kwargs(child_kwargs.id, ctx_kwargs, **kwargs_values)
        _update_via_command(
            child_command.id, ctx_command, RequirementUpdate.from_kwargs(command_values)
        )

        assert _snapshot(child_kwargs) == _snapshot(child_command)
        assert Requirement.unscoped.get(id=child_kwargs.id).artifact.parent_id == parent_kwargs.artifact_id
        assert Requirement.unscoped.get(id=child_command.id).artifact.parent_id == parent_command.artifact_id
    finally:
        tenant_context.__exit__(None, None, None)


@pytest.mark.django_db
def test_parity_all_optional_fields_absent():
    (
        tenant_context,
        ctx_kwargs,
        ctx_command,
        _parent_kwargs,
        _parent_command,
        child_kwargs,
        child_command,
    ) = _setup_pair()
    try:
        _update_via_kwargs(child_kwargs.id, ctx_kwargs)
        _update_via_command(child_command.id, ctx_command, RequirementUpdate())

        assert _snapshot(child_kwargs) == _snapshot(child_command)
        assert _snapshot(child_kwargs)["version"] == 1  # no-op PATCH, no bump
    finally:
        tenant_context.__exit__(None, None, None)


@pytest.mark.django_db
def test_parity_nullable_fields_explicit_none_versus_absent():
    """The load-bearing UNSET-vs-None split survives both call paths."""
    (
        tenant_context,
        ctx_kwargs,
        ctx_command,
        parent_kwargs,
        parent_command,
        child_kwargs,
        child_command,
    ) = _setup_pair()
    try:
        # Seed non-null values so "clear" is observable on every path.
        for child, parent, ctx in (
            (child_kwargs, parent_kwargs, ctx_kwargs),
            (child_command, parent_command, ctx_command),
        ):
            _update_via_kwargs(
                child.id,
                ctx,
                complexity_fibonacci=8,
                verification_method="Review",
                custom_fields={"seed": True},
                parent_id=parent.artifact_id,
            )

        clear = dict(
            complexity_fibonacci=None,
            verification_method=None,
            custom_fields={},
            parent_id=None,
            # sibling fields omitted -> must stay UNSET -> untouched
        )
        _update_via_kwargs(child_kwargs.id, ctx_kwargs, **clear)
        _update_via_command(
            child_command.id, ctx_command, RequirementUpdate.from_kwargs(clear)
        )

        assert _snapshot(child_kwargs) == _snapshot(child_command)
        snapshot = _snapshot(child_kwargs)
        assert snapshot["complexity_fibonacci"] is None
        assert snapshot["verification_method"] is None
        assert snapshot["custom_fields"] == {}
        assert snapshot["uid"] == "REQ-PARITY"  # omitted -> left untouched
        assert Requirement.unscoped.get(id=child_kwargs.id).artifact.parent_id is None
        assert Requirement.unscoped.get(id=child_command.id).artifact.parent_id is None
    finally:
        tenant_context.__exit__(None, None, None)
