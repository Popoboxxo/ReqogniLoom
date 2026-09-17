"""GET transitions/ surfaces who proposed a "proposed" item (spec §4.4)."""
from __future__ import annotations

from uuid import uuid4

from rest_api.mixins.workflow_transitions import resolve_proposed_by


def test_returns_none_when_not_proposed():
    assert resolve_proposed_by("draft", uuid4(), "Requirement", uuid4()) is None


def test_returns_the_history_actor(monkeypatch):
    monkeypatch.setattr(
        "rest_api.mixins.workflow_transitions._latest_proposal_actor",
        lambda item_id, item_type, workspace_id: "Claude Code",
    )
    assert (
        resolve_proposed_by("proposed", uuid4(), "Requirement", uuid4())
        == "Claude Code"
    )


def test_returns_none_when_no_history_exists(monkeypatch):
    monkeypatch.setattr(
        "rest_api.mixins.workflow_transitions._latest_proposal_actor",
        lambda item_id, item_type, workspace_id: None,
    )
    assert resolve_proposed_by("proposed", uuid4(), "Requirement", uuid4()) is None
