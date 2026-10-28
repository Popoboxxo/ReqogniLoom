"""Tests for the artifact-index projector (Plan A, Task T-A2-4).

Four behaviours, all against real DB rows with a fake Qdrant client:

* a ``*_DELETED`` event really removes the point (deletion is mandatory, not
  optional) -- delete through the service, drain the outbox, inspect the fake;
* on the default ``pgvector`` backend nothing is registered at all (the
  additive principle: the hook layer must be byte-identical when unused);
* the new event types added by this task are actually emitted by their
  services (a declared ``EventType`` member with no emitter would be a
  vocabulary entry, not a hook);
* an outbox row without a tenant is skipped fail-closed (O-2) -- counted and
  logged, never indexed.

Event-type assertions are set-membership (``<=``), never a magic total, so a
later task may add event types without breaking these tests.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any
from unittest.mock import patch

import pytest

from application import artifact_index_projector as projector_module
from application.artifact_index_projector import (
    INDEXED_EVENT_TYPES,
    ArtifactIndexProjector,
    register_projector_on_event_bus,
    skipped_without_tenant_count,
)
from application.artifact_indexer import ArtifactIndexer
from application.event_bus import get_event_bus, poll_and_dispatch
from application.glossary_service import GlossaryService
from application.models import DomainEventOutbox
from auth_tenancy.context import AuthContext, AuthMethod
from memory.tests.qdrant_fakes import FakeQdrantClient, FakeQdrantModels
from persistence.qdrant_config import build_collection_name, resolve_qdrant_config
from persistence.tests.factories import active_tenant, make_user, make_workspace

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _config():
    """An env-independent Qdrant config (the DB-override resolver is not under test)."""
    return resolve_qdrant_config(
        collection_prefix="reqlo",
        distance="cosine",
        hnsw_m=16,
        hnsw_ef_construct=64,
        quantization="int8",
    )


def _points(client: FakeQdrantClient, tenant_id: Any, workspace_id: Any) -> list:
    name = build_collection_name(
        "reqlo",
        tenant_id,
        workspace_id=workspace_id,
        scope="workspace",
        artifacts=True,
        version=2,
    )
    return client.collections.get(name, [])


def _registered_projectors() -> set:
    """Every ``ArtifactIndexProjector`` currently wired on the process bus."""
    return {
        subscriber.__self__
        for subscribers in get_event_bus().get_subscriber_registry().values()
        for subscriber in subscribers
        if isinstance(getattr(subscriber, "__self__", None), ArtifactIndexProjector)
    }


def _ctx(tenant, workspace) -> AuthContext:
    user = make_user(tenant)
    return AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=("editor",),
        auth_method=AuthMethod.BEARER_TOKEN,
        workspace_id=workspace.id,
    )


def _provision_workflow(workspace, *, item_type: str, preset: str) -> None:
    """Seed one entity's workflow so ``outdate()``/transitions have a row.

    Called inside ``active_tenant()``, which already armed both isolation
    layers — re-arming (and clearing) here would clobber that context.
    """
    from workflow.services import create_default_workflow

    create_default_workflow(
        workspace_id=workspace.id,
        preset=preset,
        item_type=item_type,
        tenant_id=workspace.tenant_id,
    )


@pytest.fixture
def fake_qdrant(monkeypatch) -> tuple[FakeQdrantClient, ArtifactIndexer]:
    """Hand the production task seam a real indexer over an in-memory Qdrant."""
    client = FakeQdrantClient()
    indexer = ArtifactIndexer(client, models_module=FakeQdrantModels, config=_config())
    monkeypatch.setattr(projector_module, "build_indexer", lambda: indexer)
    return client, indexer


@pytest.fixture
def registered_projector():
    """Wire the projector on the real bus for this test, and unwire it after."""
    projector = ArtifactIndexProjector()
    bus = get_event_bus()
    for event_type in INDEXED_EVENT_TYPES:
        bus.register_subscriber(event_type, projector.handle_event)
    try:
        yield projector
    finally:
        for event_type in INDEXED_EVENT_TYPES:
            bus.unregister_subscriber(event_type, projector.handle_event)


# ---------------------------------------------------------------------------
# Deletion is mandatory
# ---------------------------------------------------------------------------


def test_delete_event_removes_point(fake_qdrant, registered_projector) -> None:
    client, indexer = fake_qdrant

    with active_tenant() as tenant:
        workspace = make_workspace(tenant)
        ctx = _ctx(tenant, workspace)
        _provision_workflow(
            workspace, item_type="GlossaryTerm", preset="glossary_term_default"
        )

        term = GlossaryService().create(
            ctx, workspace.id, "Artifact", "Any traceable entity."
        )
        assert indexer.index_entity(tenant.id, "GlossaryTerm", term.id) == "upserted"
        assert len(_points(client, tenant.id, workspace.id)) == 1

        GlossaryService().delete(ctx, term.id)
        assert DomainEventOutbox.objects.filter(
            event_type=DomainEventOutbox.EventType.GLOSSARY_TERM_DELETED
        ).exists()

        assert poll_and_dispatch() >= 1

    assert _points(client, tenant.id, workspace.id) == []
    assert indexer.metrics.deleted == 1


# ---------------------------------------------------------------------------
# Additive: nothing is registered on the default backend
# ---------------------------------------------------------------------------


def test_projector_not_registered_on_pgvector(monkeypatch) -> None:
    monkeypatch.delenv("ARTIFACT_VECTOR_BACKEND", raising=False)

    assert register_projector_on_event_bus() == 0

    assert _registered_projectors() == set()


def test_projector_registers_when_qdrant_is_selected(monkeypatch) -> None:
    monkeypatch.setattr(
        projector_module, "_artifact_vector_backend_selected", lambda: True
    )
    try:
        assert register_projector_on_event_bus() == len(INDEXED_EVENT_TYPES)
        assert len(_registered_projectors()) == 1
    finally:
        for projector in _registered_projectors():
            for event_type in INDEXED_EVENT_TYPES:
                get_event_bus().unregister_subscriber(
                    event_type, projector.handle_event
                )
    assert _registered_projectors() == set()


# ---------------------------------------------------------------------------
# The new event types are really emitted
# ---------------------------------------------------------------------------


def test_new_event_types_emitted_by_icd_and_glossary() -> None:
    from icd.icd_manager import IcdCreateDTO, IcdUpdateDTO
    from icd.services import create_icd, delete_icd, update_icd

    with active_tenant() as tenant:
        workspace = make_workspace(tenant)
        ctx = _ctx(tenant, workspace)
        _provision_workflow(
            workspace, item_type="GlossaryTerm", preset="glossary_term_default"
        )

        service = GlossaryService()
        term = service.create(ctx, workspace.id, "Interface", "A shared boundary.")
        service.update(ctx, term.id, definition="A shared boundary between parts.")
        service.delete(ctx, term.id)

        # The two endpoint lookups resolve a real ArchitectureElement in
        # production; only the ids matter here, so they are stubbed exactly
        # like icd/tests/test_icd.py does.
        with patch(
            "icd.icd_manager.IcdManager._resolve_arch_artifact_id",
            side_effect=lambda element_id: element_id,
        ), patch(
            "icd.traceability_connector.TraceabilityConnector.link_to_architecture"
        ):
            result = create_icd(
                IcdCreateDTO(
                    tenant_id=tenant.id,
                    workspace_id=workspace.id,
                    name="IF-1",
                    source_element_id=uuid.uuid4(),
                    target_element_id=uuid.uuid4(),
                    interface_type="REST",
                    semantic_description="Exchanges artifacts.",
                )
            )
            update_icd(
                result.icd.id,
                IcdUpdateDTO(semantic_description="Exchanges artifact metadata."),
                tenant.id,
            )
            delete_icd(result.icd.id, tenant.id)

        emitted = set(DomainEventOutbox.objects.values_list("event_type", flat=True))
        assert {
            DomainEventOutbox.EventType.GLOSSARY_TERM_CREATED,
            DomainEventOutbox.EventType.GLOSSARY_TERM_UPDATED,
            DomainEventOutbox.EventType.GLOSSARY_TERM_DELETED,
        } <= emitted
        assert {
            DomainEventOutbox.EventType.ICD_CREATED,
            DomainEventOutbox.EventType.ICD_UPDATED,
            DomainEventOutbox.EventType.ICD_DELETED,
        } <= emitted


def test_goal_main_goal_and_diagram_events_are_emitted() -> None:
    """The remaining new emitters: a Goal version update, the Goal soft delete,
    the second MainGoal version and the three Diagram writes."""
    from collections import Counter

    from application.goal_service import GoalService
    from application.main_goal_service import MainGoalService
    from diagram.manager import DiagramManager
    from diagram.services import delete_diagram

    with active_tenant() as tenant:
        workspace = make_workspace(tenant, goals_enabled=True)
        editor = _ctx(tenant, workspace)
        approver = AuthContext(
            user_id=editor.user_id,
            tenant_id=tenant.id,
            active_roles=("approver",),
            auth_method=AuthMethod.BEARER_TOKEN,
            workspace_id=workspace.id,
        )
        _provision_workflow(workspace, item_type="Goal", preset="goal_default")

        goals = GoalService()
        first = goals.create_version(
            workspace_id=workspace.id,
            title="Goal",
            description="",
            lineage_id=None,
            ctx=editor,
        )
        second = goals.create_version(
            workspace_id=workspace.id,
            title="Goal revised",
            description="",
            lineage_id=uuid.UUID(first["lineage_id"]),
            ctx=editor,
        )
        goals.archive(uuid.UUID(second["id"]), approver, change_reason="archive")

        main_goals = MainGoalService()
        main_goals.create_manual(workspace_id=workspace.id, content="First", ctx=editor)
        main_goals.create_manual(workspace_id=workspace.id, content="Second", ctx=editor)

        manager = DiagramManager()
        diagram = manager.create_diagram(
            name="Indexed diagram",
            diagram_type="flow",
            payload_format="mermaid",
            content="flowchart TD\n  A --> B",
            tenant=tenant,
            workspace_id=workspace.id,
        )
        manager.update_diagram(
            diagram_id=diagram.id,
            payload_format="mermaid",
            content="flowchart TD\n  A --> C",
        )
        _provision_workflow(workspace, item_type="Diagram", preset="diagram_default")
        delete_diagram(diagram.id, tenant.id, editor)

        def _events(entity_id) -> Counter:
            return Counter(
                DomainEventOutbox.objects.filter(entity_id=entity_id).values_list(
                    "event_type", flat=True
                )
            )

        # A version appended to a lineage is an update, not a second creation.
        assert "GoalCreated" in _events(uuid.UUID(first["id"]))
        second_goal = _events(uuid.UUID(second["id"]))
        assert "GoalUpdated" in second_goal
        assert "GoalDeleted" in second_goal
        assert "GoalCreated" not in second_goal

        assert {
            DomainEventOutbox.EventType.MAIN_GOAL_CREATED,
            DomainEventOutbox.EventType.MAIN_GOAL_UPDATED,
        } <= set(
            DomainEventOutbox.objects.filter(
                event_type__startswith="MainGoal"
            ).values_list("event_type", flat=True)
        )

        diagram_events = _events(diagram.id)
        assert {
            DomainEventOutbox.EventType.DIAGRAM_CREATED,
            DomainEventOutbox.EventType.DIAGRAM_UPDATED,
            DomainEventOutbox.EventType.DIAGRAM_DELETED,
        } <= set(diagram_events)


# ---------------------------------------------------------------------------
# O-2: an outbox row without a tenant is skipped fail-closed
# ---------------------------------------------------------------------------


def test_projector_skips_outbox_row_without_tenant(
    fake_qdrant, registered_projector, caplog
) -> None:
    client, _indexer = fake_qdrant

    with active_tenant() as tenant:
        workspace = make_workspace(tenant)

    DomainEventOutbox.objects.create(
        event_type=DomainEventOutbox.EventType.GLOSSARY_TERM_CREATED,
        workspace_id=workspace.id,
        entity_id=uuid.uuid4(),
        payload={},
        tenant_id=None,  # O-2: unresolvable workspace anchor, must never be indexed
    )

    before = skipped_without_tenant_count()
    with caplog.at_level(logging.WARNING, logger="application.artifact_index_projector"):
        assert poll_and_dispatch() >= 1

    assert skipped_without_tenant_count() == before + 1
    assert any(
        record.levelno == logging.WARNING and "no tenant" in record.getMessage().lower()
        for record in caplog.records
    )
    assert client.collections == {}
