"""Deterministic impact-summary generator (plan S5.4, spec §4.4/§4.5, AC-28).

Covers the promises the gate relies on: the text is byte-identical for one run,
no LLM is involved, nothing identifying leaks into it, and the write is a plain
``QuerySet.update()`` on the newest *completed* run.
"""
from __future__ import annotations

import re
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest
from django.utils import timezone

from application.base import ValidationError
from application.change_impact_summary import (
    MAX_SUMMARY_CHARS,
    TRUNCATION_MARKER,
    build_summary,
    generate_summary,
    latest_completed_run,
)
from application.models import (
    ChangeImpactFinding,
    ChangeImpactRun,
    ChangeRequest,
    ChangeRequestAffectedItem,
)
from persistence.models import Artifact
from persistence.tests.factories import (
    active_tenant,
    editor_ctx,
    make_workspace,
)

pytestmark = pytest.mark.django_db

_UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}"
    r"-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


class _Env:
    """Tenant + workspace + ctx + one change request (no run yet)."""

    def __init__(self, tenant, workspace, ctx, cr):
        self.tenant = tenant
        self.workspace = workspace
        self.ctx = ctx
        self.cr = cr


@contextmanager
def _env(title: str = "Impact CR") -> Iterator[_Env]:
    with active_tenant() as tenant:
        workspace = make_workspace(tenant)
        ctx = editor_ctx(tenant, workspace)
        cr = ChangeRequest.objects.create(
            tenant=tenant,
            workspace_id=workspace.id,
            title=title,
        )
        yield _Env(tenant, workspace, ctx, cr)


def _artifact(env: _Env, artifact_type: str = "Requirement") -> Artifact:
    return Artifact.objects.create(
        tenant=env.tenant,
        workspace=env.workspace,
        artifact_type=artifact_type,
    )


def _run(
    env: _Env,
    fingerprint: str,
    *,
    status: str = ChangeImpactRun.Status.COMPLETED,
    **kwargs: Any,
) -> ChangeImpactRun:
    now = timezone.now()
    defaults: dict[str, Any] = {
        "tenant": env.tenant,
        "change_request": env.cr,
        "workspace_id": env.workspace.id,
        "status": status,
        "graph_fingerprint": fingerprint,
        "roots_source": ChangeImpactRun.RootsSource.CHANGE_SET,
        "gate_eligible": True,
        "node_count": 12,
        "edge_count": 15,
        "path_count": 4,
        "visited_node_ids": [str(uuid.uuid4()) for _ in range(3)],
        "started_at": now,
        "finished_at": (
            now if status == ChangeImpactRun.Status.COMPLETED else None
        ),
    }
    defaults.update(kwargs)
    return ChangeImpactRun.objects.create(**defaults)


def _affected(
    env: _Env,
    *,
    item_id: str | None = None,
    action: str = "modify",
    entity_type: str = "item",
    rationale: str = "",
) -> ChangeRequestAffectedItem:
    return ChangeRequestAffectedItem.objects.create(
        tenant=env.tenant,
        change_request=env.cr,
        item_id=item_id or str(_artifact(env).id),
        entity_type=entity_type,
        change_action=action,
        rationale=rationale,
    )


def _finding(
    run: ChangeImpactRun,
    *,
    artifact_id: str | None = None,
    entity_type: str = "Requirement",
    severity: str = ChangeImpactFinding.Severity.WARNING,
    hop_distance: int = 1,
    weight: str = "0.9000",
    chain_count: int = 0,
    rationale: str = "",
    note: str = "",
) -> ChangeImpactFinding:
    return ChangeImpactFinding.objects.create(
        tenant_id=run.tenant_id,
        run=run,
        artifact_id=artifact_id or str(uuid.uuid4()),
        entity_type=entity_type,
        hop_distance=hop_distance,
        weight=Decimal(weight),
        severity=severity,
        origin=ChangeImpactFinding.Origin.DETERMINISTIC,
        chain_count=chain_count,
        rationale=rationale,
        note=note,
    )


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_two_calls_produce_identical_bytes() -> None:
    with _env() as env:
        _affected(env, action="add")
        _affected(env, action="remove")
        run = _run(env, "a" * 64)
        _finding(run, entity_type="TestCase", severity="blocking")
        _finding(run, entity_type="Requirement")

        first = generate_summary(env.cr.id, ctx=env.ctx)
        second = generate_summary(env.cr.id, ctx=env.ctx)

        assert first  # non-empty
        assert first == second
        assert first == build_summary(
            cr_id=env.cr.id, run=run, tenant_id=env.tenant.id
        )


def test_output_is_independent_of_finding_insertion_order() -> None:
    with _env() as env:
        for action in ("add", "modify", "modify"):
            _affected(env, action=action)

        specs = [
            ("Requirement", "blocking", 1, "0.9500", 1),
            ("TestCase", "warning", 2, "0.8000", 0),
            ("ArchitectureElement", "info", 3, "0.5000", 2),
        ]

        def _seed(run: ChangeImpactRun, ordered: list[tuple]) -> None:
            for entity_type, severity, hop, weight, chains in ordered:
                _finding(
                    run,
                    entity_type=entity_type,
                    severity=severity,
                    hop_distance=hop,
                    weight=weight,
                    chain_count=chains,
                )

        first_run = _run(env, "b" * 64)
        _seed(first_run, specs)
        second_run = _run(env, "c" * 64)
        _seed(second_run, list(reversed(specs)))

        first = build_summary(
            cr_id=env.cr.id, run=first_run, tenant_id=env.tenant.id
        )
        second = build_summary(
            cr_id=env.cr.id, run=second_run, tenant_id=env.tenant.id
        )

        assert first == second
        assert first.count("- Findings: total=3") == 1


# ---------------------------------------------------------------------------
# No LLM
# ---------------------------------------------------------------------------


def test_works_with_the_provider_factory_booby_trapped(monkeypatch) -> None:
    with _env() as env:
        _affected(env)
        run = _run(env, "d" * 64)
        _finding(run)

        def _explode(*args: Any, **kwargs: Any):
            raise AssertionError("the summary generator must never call an LLM")

        import llm_adapter.providers

        monkeypatch.setattr(llm_adapter.providers, "get_provider", _explode)

        text = generate_summary(env.cr.id, ctx=env.ctx)

        assert "Findings: total=1" in text


# ---------------------------------------------------------------------------
# No identities / no free text (AC-28)
# ---------------------------------------------------------------------------


def test_output_contains_no_titles_uids_ids_or_free_text() -> None:
    title_marker = "SECRET-ARTIFACT-TITLE"
    rationale_marker = "SECRET-RATIONALE"
    note_marker = "SECRET-NOTE"

    with _env(title=title_marker) as env:
        artifact = _artifact(env)
        _affected(
            env,
            item_id=str(artifact.id),
            rationale=rationale_marker,
        )
        run = _run(env, "e" * 64)
        _finding(
            run,
            artifact_id=str(artifact.id),
            entity_type="Requirement",
            rationale=rationale_marker,
            note=note_marker,
        )

        text = generate_summary(env.cr.id, ctx=env.ctx)

        assert title_marker not in text
        assert rationale_marker not in text
        assert note_marker not in text
        assert str(artifact.id) not in text
        assert str(env.cr.id) not in text
        assert str(run.id) not in text
        assert _UUID_RE.search(text) is None


# ---------------------------------------------------------------------------
# Run selection
# ---------------------------------------------------------------------------


def test_summary_pairs_to_latest_completed_run_ignoring_later_failure() -> None:
    with _env() as env:
        _affected(env)
        completed = _run(env, "f" * 64)
        _finding(completed)
        ChangeImpactRun.objects.filter(id=completed.id).update(
            created_at=timezone.now() - timedelta(hours=2)
        )

        failed = _run(
            env,
            "1" * 64,
            status=ChangeImpactRun.Status.FAILED,
            error="capture incomplete",
        )
        assert failed.created_at > completed.created_at

        assert latest_completed_run(env.cr.id).id == completed.id

        text = generate_summary(env.cr.id, ctx=env.ctx)

        env.cr.refresh_from_db()
        assert env.cr.summary_run_id == completed.id
        assert env.cr.impact_summary == text
        assert env.cr.impact_source == "analysis"
        assert env.cr.impact_generated_at is not None


def test_explicit_run_id_wins_over_the_latest_one() -> None:
    with _env() as env:
        _affected(env)
        older = _run(env, "2" * 64)
        _finding(older, entity_type="TestCase")
        ChangeImpactRun.objects.filter(id=older.id).update(
            created_at=timezone.now() - timedelta(hours=2)
        )
        newer = _run(env, "3" * 64)

        text = generate_summary(env.cr.id, ctx=env.ctx, run_id=older.id)

        env.cr.refresh_from_db()
        assert env.cr.summary_run_id == older.id
        assert "TestCase=1" in text
        assert latest_completed_run(env.cr.id).id == newer.id


# ---------------------------------------------------------------------------
# Persistence shape
# ---------------------------------------------------------------------------


def test_write_uses_queryset_update_and_does_not_bump_the_version() -> None:
    with _env() as env:
        _affected(env)
        run = _run(env, "4" * 64)
        _finding(run)

        before = ChangeRequest.objects.get(id=env.cr.id)
        assert before.version == 1

        generate_summary(env.cr.id, ctx=env.ctx)

        after = ChangeRequest.objects.get(id=env.cr.id)
        assert after.version == before.version == 1
        assert after.modified_at == before.modified_at
        assert after.summary_run_id == run.id


def test_no_completed_run_returns_empty_string_and_writes_nothing() -> None:
    with _env() as env:
        _affected(env)
        _run(env, "5" * 64, status=ChangeImpactRun.Status.FAILED)
        _run(env, "6" * 64, status=ChangeImpactRun.Status.RUNNING)

        assert latest_completed_run(env.cr.id) is None
        assert generate_summary(env.cr.id, ctx=env.ctx) == ""

        env.cr.refresh_from_db()
        assert env.cr.impact_summary == ""
        assert env.cr.summary_run_id is None
        assert env.cr.impact_source == "none"
        assert env.cr.impact_generated_at is None


# ---------------------------------------------------------------------------
# Length cap
# ---------------------------------------------------------------------------


def test_length_cap_is_honoured_and_marked() -> None:
    with _env() as env:
        # One distinct entity_type per item: the change-set type line is the
        # only unbounded aggregate, so this is the realistic way to exceed the
        # cap without inventing identities.
        for index in range(200):
            _affected(env, entity_type=f"EntityType{index:04d}xxxxxxxx")
        run = _run(env, "7" * 64)
        _finding(run)

        text = generate_summary(env.cr.id, ctx=env.ctx)

        assert len(text) <= MAX_SUMMARY_CHARS
        assert text.endswith(TRUNCATION_MARKER)
        # The gate-relevant lines survive the cut.
        assert "gate_eligible=true" in text
        assert "Truncated: false" in text
        # Same input, same truncated bytes.
        assert text == build_summary(
            cr_id=env.cr.id, run=run, tenant_id=env.tenant.id
        )


def test_short_summary_is_not_marked_as_truncated() -> None:
    with _env() as env:
        _affected(env)
        run = _run(env, "8" * 64)
        _finding(run)

        text = generate_summary(env.cr.id, ctx=env.ctx)

        assert 0 < len(text) < MAX_SUMMARY_CHARS
        assert TRUNCATION_MARKER not in text


# ---------------------------------------------------------------------------
# Defensive guards
# ---------------------------------------------------------------------------


def test_explicit_non_completed_run_is_rejected() -> None:
    with _env() as env:
        failed = _run(env, "9" * 64, status=ChangeImpactRun.Status.FAILED)

        with pytest.raises(ValidationError):
            generate_summary(env.cr.id, ctx=env.ctx, run_id=failed.id)

        env.cr.refresh_from_db()
        assert env.cr.impact_summary == ""
