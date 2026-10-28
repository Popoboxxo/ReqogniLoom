"""Tests for ``manage.py index_artifact_vectors`` (T-A2-5).

The command is the only way the generic indexer is reached before PR-A19 wires
the projector, so it has to be safe by default: ``--dry-run`` must not write a
single point (or spend a single embedding call), a second run must be a no-op,
and the embedding rate limit must actually space the calls.
"""
from __future__ import annotations

import json
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from application.management.commands import index_artifact_vectors as command_module
from memory.tests.qdrant_fakes import FakeQdrantClient, FakeQdrantModels
from persistence.models import Adr, Requirement
from persistence.qdrant_config import (
    build_collection_alias,
    build_collection_name,
    resolve_qdrant_config,
)
from persistence.tests.factories import active_tenant, make_requirement, make_workspace


def _config():
    return resolve_qdrant_config(
        base_url="http://qdrant.test:6333",
        collection_prefix="reqlo",
        distance="cosine",
        hnsw_m=16,
        hnsw_ef_construct=64,
        quantization="int8",
    )


@pytest.fixture
def fake_client(monkeypatch) -> FakeQdrantClient:
    client = FakeQdrantClient()
    monkeypatch.setattr(
        command_module.Command, "client_factory", staticmethod(lambda config: client)
    )
    monkeypatch.setattr(command_module.Command, "models_module", FakeQdrantModels)
    monkeypatch.setattr(command_module, "resolve_artifact_qdrant_config", _config)
    return client


def _run(**options) -> dict:
    out = StringIO()
    call_command("index_artifact_vectors", stdout=out, stderr=out, **options)
    return json.loads(out.getvalue().strip().splitlines()[-1])


def _make_requirements(workspace, count: int) -> list[Requirement]:
    return [
        make_requirement(workspace, title=f"Rate limited requirement {index}")
        for index in range(count)
    ]


@pytest.mark.django_db
def test_dry_run_writes_nothing(fake_client, monkeypatch) -> None:
    monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
    with active_tenant() as tenant:
        workspace = make_workspace(tenant)
        _make_requirements(workspace, 3)

        payload = _run(
            tenant=str(tenant.id),
            workspace=str(workspace.id),
            type=["Requirement"],
            dry_run=True,
        )

    assert set(payload) == {"tenant", "by_type", "failures", "embed_calls", "duration_s"}
    assert payload["tenant"] == str(tenant.id)
    assert payload["by_type"]["Requirement"] == {"upserted": 3, "skipped": 0, "failed": 0}
    assert payload["failures"] == {}
    assert payload["embed_calls"] == 3
    assert fake_client.collections == {}
    assert not [call for call in fake_client.calls if call[0] == "upsert"]


@pytest.mark.django_db
def test_rerun_is_noop(fake_client, monkeypatch) -> None:
    monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
    with active_tenant() as tenant:
        workspace = make_workspace(tenant)
        _make_requirements(workspace, 2)
        options = {
            "tenant": str(tenant.id),
            "workspace": str(workspace.id),
            "type": ["Requirement"],
        }

        first = _run(**options)
        upserts_after_first = len(
            [call for call in fake_client.calls if call[0] == "upsert"]
        )
        second = _run(**options)

    assert first["by_type"]["Requirement"]["upserted"] == 2
    assert first["embed_calls"] == 2
    assert second["by_type"]["Requirement"] == {"upserted": 0, "skipped": 2, "failed": 0}
    assert second["embed_calls"] == 0
    assert len([call for call in fake_client.calls if call[0] == "upsert"]) == (
        upserts_after_first
    )


@pytest.mark.django_db
def test_rate_limit_respected(fake_client, monkeypatch) -> None:
    monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
    now = [0.0]
    sleeps: list[float] = []

    def _fake_clock() -> float:
        return now[0]

    def _fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        now[0] += seconds

    monkeypatch.setattr(command_module, "_monotonic", _fake_clock)
    monkeypatch.setattr(command_module, "_sleep", _fake_sleep)

    with active_tenant() as tenant:
        workspace = make_workspace(tenant)
        _make_requirements(workspace, 3)

        payload = _run(
            tenant=str(tenant.id),
            workspace=str(workspace.id),
            type=["Requirement"],
            max_embeds_per_minute=60,
        )

    assert payload["embed_calls"] == 3
    assert len(sleeps) == 2
    assert all(seconds == pytest.approx(1.0) for seconds in sleeps)
    assert now[0] == pytest.approx(2.0)


@pytest.mark.django_db
def test_dry_run_and_recreate_are_mutually_exclusive(fake_client) -> None:
    with active_tenant() as tenant, pytest.raises(CommandError, match="dry-run"):
        _run(tenant=str(tenant.id), dry_run=True, recreate=True)


@pytest.mark.django_db
def test_unknown_type_is_rejected(fake_client) -> None:
    with active_tenant() as tenant, pytest.raises(CommandError, match="Unknown"):
        _run(tenant=str(tenant.id), type=["NoSuchType"])


@pytest.mark.django_db
def test_recreate_requires_tenant(fake_client) -> None:
    """``--recreate`` must never sweep every tenant's collection."""
    with active_tenant(), pytest.raises(CommandError, match="--recreate requires --tenant"):
        _run(recreate=True)


@pytest.mark.django_db
def test_malformed_tenant_and_workspace_are_command_errors(fake_client) -> None:
    with active_tenant(), pytest.raises(CommandError, match="--tenant must be a UUID"):
        _run(tenant="not-a-uuid")
    with active_tenant(), pytest.raises(CommandError, match="--workspace must be a UUID"):
        _run(workspace="not-a-uuid")


@pytest.mark.django_db
def test_recreate_drops_and_rebuilds_the_collection(fake_client, monkeypatch) -> None:
    monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
    with active_tenant() as tenant:
        workspace = make_workspace(tenant)
        _make_requirements(workspace, 2)
        options = {
            "tenant": str(tenant.id),
            "workspace": str(workspace.id),
            "type": ["Requirement"],
        }

        assert _run(**options)["by_type"]["Requirement"]["upserted"] == 2
        collection = build_collection_name(
            "reqlo", tenant.id, workspace_id=workspace.id, scope="workspace",
            artifacts=True, version=2,
        )
        alias = build_collection_alias(
            "reqlo", tenant.id, workspace_id=workspace.id, scope="workspace"
        )
        assert alias in fake_client.aliases

        payload = _run(**options, recreate=True)

    assert payload["by_type"]["Requirement"]["upserted"] == 2
    assert any(call[0] == "delete_collection" for call in fake_client.calls)
    assert fake_client.aliases[alias] == collection
    assert len(fake_client.collections[collection]) == 2


@pytest.mark.django_db
def test_one_collection_ensure_per_workspace_across_types(fake_client, monkeypatch) -> None:
    """The per-tenant indexer keeps ``_ensured``: one ensure, not one per type."""
    monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
    with active_tenant() as tenant:
        workspace = make_workspace(tenant)
        _make_requirements(workspace, 1)
        Adr.objects.create(tenant=tenant, workspace_id=workspace.id, title="A decision")

        payload = _run(
            tenant=str(tenant.id),
            workspace=str(workspace.id),
            type=["Requirement", "Adr"],
        )

    assert payload["by_type"]["Requirement"]["upserted"] == 1
    assert payload["by_type"]["Adr"]["upserted"] == 1
    assert len([call for call in fake_client.calls if call[0] == "create_collection"]) == 1


@pytest.mark.django_db
def test_failed_entities_exit_non_zero_but_still_report(fake_client, monkeypatch) -> None:
    """A row that cannot be indexed must fail the run, not just count up."""
    monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
    out = StringIO()
    with active_tenant() as tenant:
        workspace = make_workspace(tenant)
        make_requirement(workspace, title="")

        with pytest.raises(CommandError, match="indexing failed for 1 entities"):
            call_command(
                "index_artifact_vectors",
                stdout=out,
                stderr=out,
                tenant=str(tenant.id),
                workspace=str(workspace.id),
                type=["Requirement"],
            )

    payload = json.loads(out.getvalue().strip().splitlines()[-1])
    assert payload["by_type"]["Requirement"]["failed"] == 1
    assert payload["failures"] == {"empty_text": 1}
