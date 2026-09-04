"""SYSTEMAUDIT P1-16 — ``lifecycle_status`` is a real mirror again.

Before this change nothing in production code ever wrote
``persistence.models.LifecycleStatus``: every soft-delete routes through
``workflow.services.outdate()``, which writes ``WorkflowItemState`` plus the
``status`` mirror — and ArchitectureElement / GlossaryTerm have no ``status``
column, so their ``lifecycle_status`` read ``"active"`` on every row forever.
That is exactly the pair the enum's own docstring claimed the column existed
for, and the pair whose ``lifecycle_status`` is read by the REST serializer
(#440), the CSV export, the frontend status filters and
``baseline.state_capture`` (which captures no other status field for
ArchitectureElement, so a deprecation was invisible to every baseline diff).

``StateLifecycleManager._sync_lifecycle_mirror`` now projects the workflow
state onto the column inside the transition's transaction.

The first two blocks run without a database (pure mapping + a fake mirror
target); the last two need one.
"""
from __future__ import annotations

import uuid
from contextlib import contextmanager
from importlib import import_module

import pytest

from workflow.lifecycle_manager import (
    _LIFECYCLE_MIRROR_MODELS,
    StateLifecycleManager,
    map_lifecycle_status,
)

_mig = import_module("workflow.migrations.0017_backfill_lifecycle_status_mirror")
backfill_lifecycle_status = _mig.backfill_lifecycle_status


# ---------------------------------------------------------------------------
# 1. State -> LifecycleStatus mapping (no DB)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "state,expected",
    [
        ("outdated", "outdated"),
        ("deprecated", "deprecated"),
        ("draft", "active"),
        ("in_review", "active"),
        ("approved", "active"),
        # A workspace that renamed its states (Extended preset, ADR-06) still
        # mirrors correctly — the lookup is case-insensitive and trimmed.
        ("Deprecated", "deprecated"),
        ("  Outdated  ", "outdated"),
        # Anything a custom workflow invents is a live artifact.
        ("waiting_for_hardware", "active"),
        ("", "active"),
        (None, "active"),
    ],
)
def test_map_lifecycle_status(state, expected) -> None:
    assert map_lifecycle_status(state) == expected


def test_mapping_never_produces_a_value_outside_the_enum() -> None:
    from persistence.models import LifecycleStatus

    valid = {choice.value for choice in LifecycleStatus}
    for state in ("outdated", "deprecated", "draft", "anything else"):
        assert map_lifecycle_status(state) in valid


def test_deleted_is_never_written_by_the_mirror() -> None:
    """``LifecycleStatus.DELETED`` is a pre-Phase-0 legacy value — the workflow
    engine's soft-delete is ``"outdated"``. Rows still carrying "deleted" are
    the *input* of ``backfill_outdated_from_legacy_status``; the mirror must
    not start producing it again."""
    for state in ("deleted", "outdated", "deprecated", "draft"):
        assert map_lifecycle_status(state) != "deleted"


# ---------------------------------------------------------------------------
# 2. Registry + write wiring (no DB — fake mirror target)
# ---------------------------------------------------------------------------


def test_registry_covers_exactly_the_two_mirrorless_types() -> None:
    """The registry is intentionally narrow. Requirement/StakeholderNeed also
    declare ``lifecycle_status``, but their soft-delete state is resolved
    through ``workflow.state_reader``/``workflow.services.outdated_item_ids``
    instead; writing their ``lifecycle_status`` too would surface every
    transition as two field-level baseline diffs."""
    assert set(_LIFECYCLE_MIRROR_MODELS) == {"ArchitectureElement", "GlossaryTerm"}


class _FakeQuerySet:
    def __init__(self, recorder: list) -> None:
        self._recorder = recorder
        self._pk = None

    def filter(self, **kwargs):
        self._pk = kwargs.get("pk")
        return self

    def update(self, **kwargs):
        self._recorder.append((self._pk, kwargs))
        return 1


class _FakeManager:
    def __init__(self) -> None:
        self.calls: list = []

    def filter(self, **kwargs):
        return _FakeQuerySet(self.calls).filter(**kwargs)


class FakeMirrorModel:
    """Stand-in for ArchitectureElement — module-level so ``import_module`` +
    ``getattr`` in ``_sync_lifecycle_mirror`` can resolve it."""

    unscoped = _FakeManager()


@pytest.fixture
def fake_mirror(monkeypatch):
    FakeMirrorModel.unscoped = _FakeManager()
    monkeypatch.setitem(
        _LIFECYCLE_MIRROR_MODELS,
        "FakeType",
        ("workflow.tests.test_lifecycle_status_mirror", "FakeMirrorModel"),
    )
    return FakeMirrorModel.unscoped


def test_sync_lifecycle_mirror_writes_the_mapped_value(fake_mirror) -> None:
    item_id = uuid.uuid4()
    StateLifecycleManager._sync_lifecycle_mirror(item_id, "FakeType", "outdated")
    assert fake_mirror.calls == [(item_id, {"lifecycle_status": "outdated"})]


def test_sync_lifecycle_mirror_writes_active_for_a_live_state(fake_mirror) -> None:
    item_id = uuid.uuid4()
    StateLifecycleManager._sync_lifecycle_mirror(item_id, "FakeType", "approved")
    assert fake_mirror.calls == [(item_id, {"lifecycle_status": "active"})]


def test_sync_lifecycle_mirror_is_a_noop_for_unregistered_types(fake_mirror) -> None:
    """Requirement is ``status``-mirrored, not lifecycle-mirrored — it must not
    be touched here."""
    StateLifecycleManager._sync_lifecycle_mirror(uuid.uuid4(), "Requirement", "outdated")
    assert fake_mirror.calls == []


def test_sync_lifecycle_mirror_never_writes_the_raw_state(fake_mirror) -> None:
    """Regression guard for the obvious copy-paste of ``_sync_status_mirror``:
    ``lifecycle_status`` has a four-value vocabulary, ``current_state`` is
    per-preset free text. Writing the raw state would violate
    ``LifecycleStatus.choices``."""
    StateLifecycleManager._sync_lifecycle_mirror(uuid.uuid4(), "FakeType", "in_review")
    (_pk, written), = fake_mirror.calls
    assert written == {"lifecycle_status": "active"}


# ---------------------------------------------------------------------------
# 3. End-to-end through outdate()/reactivate() (DB)
# ---------------------------------------------------------------------------


@contextmanager
def _tenant_scope(tenant_id):
    from persistence.tenancy import TenantContext

    TenantContext.set_tenant(tenant_id)
    try:
        yield
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def mirror_tenant(db):
    from persistence.models import Tenant

    return Tenant.objects.create(name="p116-mirror", slug="p116-mirror")


@pytest.fixture
def mirror_workspace(mirror_tenant):
    from persistence.models import Workspace

    with _tenant_scope(mirror_tenant.id):
        return Workspace.objects.create(tenant=mirror_tenant, name="P1-16 Mirror WS")


@pytest.fixture
def mirror_ctx(mirror_tenant):
    from auth_tenancy.context import AuthContext
    from persistence.models import User

    user = User.objects.create(
        username="p116-mirror-user",
        email="p116-mirror@example.com",
        tenant=mirror_tenant,
    )
    return AuthContext(
        user_id=user.id,
        tenant_id=mirror_tenant.id,
        active_roles=("editor", "admin"),
        auth_method="test",
    )


@pytest.fixture
def architecture_element(mirror_tenant, mirror_workspace, mirror_ctx):
    from application.architecture_service import ArchitectureService
    from workflow.services import create_default_workflow

    with _tenant_scope(mirror_tenant.id):
        create_default_workflow(
            workspace_id=mirror_workspace.id,
            preset="architecture_default",
            item_type="ArchitectureElement",
            tenant_id=mirror_tenant.id,
        )
        element = ArchitectureService().create_architecture_element(
            workspace_id=mirror_workspace.id,
            title="Brake Controller",
            ctx=mirror_ctx,
        )
    return element


@pytest.mark.django_db(transaction=True)
def test_outdate_writes_lifecycle_status_on_architecture_element(
    mirror_tenant, mirror_workspace, mirror_ctx, architecture_element
):
    from persistence.models import ArchitectureElement
    from workflow.services import outdate

    with _tenant_scope(mirror_tenant.id):
        before = ArchitectureElement.objects.get(id=architecture_element.id)
        assert before.lifecycle_status == "active"

        outdate(
            item_id=architecture_element.id,
            item_type="ArchitectureElement",
            workspace_id=mirror_workspace.id,
            ctx=mirror_ctx,
            reason="p1-16 mirror test",
        )

        after = ArchitectureElement.objects.get(id=architecture_element.id)
        assert after.lifecycle_status == "outdated"


@pytest.mark.django_db(transaction=True)
def test_reactivate_restores_lifecycle_status_to_active(
    mirror_tenant, mirror_workspace, mirror_ctx, architecture_element
):
    from persistence.models import ArchitectureElement
    from workflow.services import outdate, reactivate

    with _tenant_scope(mirror_tenant.id):
        outdate(
            item_id=architecture_element.id,
            item_type="ArchitectureElement",
            workspace_id=mirror_workspace.id,
            ctx=mirror_ctx,
            reason="p1-16 mirror test",
        )
        reactivate(
            item_id=architecture_element.id,
            item_type="ArchitectureElement",
            workspace_id=mirror_workspace.id,
            ctx=mirror_ctx,
        )

        restored = ArchitectureElement.objects.get(id=architecture_element.id)
        assert restored.lifecycle_status == "active"


@pytest.mark.django_db(transaction=True)
def test_outdate_does_not_bump_the_entity_version(
    mirror_tenant, mirror_workspace, mirror_ctx, architecture_element
):
    """The mirror uses a bare ``.update()`` on purpose — a workflow transition
    is not a content edit of the artifact (same contract as ``_sync_status_mirror``)."""
    from persistence.models import ArchitectureElement
    from workflow.services import outdate

    with _tenant_scope(mirror_tenant.id):
        version_before = ArchitectureElement.objects.get(
            id=architecture_element.id
        ).version

        outdate(
            item_id=architecture_element.id,
            item_type="ArchitectureElement",
            workspace_id=mirror_workspace.id,
            ctx=mirror_ctx,
            reason="p1-16 mirror test",
        )

        assert (
            ArchitectureElement.objects.get(id=architecture_element.id).version
            == version_before
        )


@pytest.mark.django_db(transaction=True)
def test_workflowitemstate_stays_authoritative_for_outdated_item_ids(
    mirror_tenant, mirror_workspace, mirror_ctx, architecture_element
):
    """The mirror is additive: the exact filter every caller uses keeps
    querying WorkflowItemState, which is also the only variant correct for rows
    soft-deleted before the mirror existed."""
    from workflow.services import outdate, outdated_item_ids

    with _tenant_scope(mirror_tenant.id):
        outdate(
            item_id=architecture_element.id,
            item_type="ArchitectureElement",
            workspace_id=mirror_workspace.id,
            ctx=mirror_ctx,
            reason="p1-16 mirror test",
        )
        assert architecture_element.id in set(
            outdated_item_ids("ArchitectureElement")
        )


@pytest.mark.django_db(transaction=True)
def test_glossary_delete_writes_lifecycle_status_on_the_model_row(
    mirror_tenant, mirror_workspace, mirror_ctx
):
    """Issue #440's overlay in ``GlossaryService.get`` patched the DTO because
    the column was dead. The column itself now carries the value, so the
    overlay is a compatibility net for pre-mirror rows rather than the only
    source of truth."""
    from application.glossary_service import GlossaryService
    from persistence.models import GlossaryTerm
    from workflow.services import create_default_workflow

    with _tenant_scope(mirror_tenant.id):
        create_default_workflow(
            workspace_id=mirror_workspace.id,
            preset="glossary_term_default",
            item_type="GlossaryTerm",
            tenant_id=mirror_tenant.id,
        )
        service = GlossaryService()
        term = service.create(
            ctx=mirror_ctx,
            workspace_id=mirror_workspace.id,
            term="Requirement",
            definition="A stated need.",
        )
        assert GlossaryTerm.objects.get(id=term.id).lifecycle_status == "active"

        service.delete(mirror_ctx, term.id)

        assert GlossaryTerm.objects.get(id=term.id).lifecycle_status == "outdated"


# ---------------------------------------------------------------------------
# 4. Backfill migration 0016 (DB)
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_backfill_sets_outdated_on_a_pre_mirror_row(
    mirror_tenant, mirror_workspace, mirror_ctx, architecture_element
):
    """Simulates a row soft-deleted before the mirror existed: WorkflowItemState
    says "outdated", the column still says "active"."""
    from django.apps import apps as django_apps

    from persistence.models import ArchitectureElement
    from workflow.services import outdate

    with _tenant_scope(mirror_tenant.id):
        outdate(
            item_id=architecture_element.id,
            item_type="ArchitectureElement",
            workspace_id=mirror_workspace.id,
            ctx=mirror_ctx,
            reason="p1-16 backfill test",
        )
        # Reset the column to the pre-mirror value.
        ArchitectureElement.objects.filter(id=architecture_element.id).update(
            lifecycle_status="active"
        )

        backfill_lifecycle_status(django_apps, None)

        assert (
            ArchitectureElement.objects.get(id=architecture_element.id).lifecycle_status
            == "outdated"
        )


@pytest.mark.django_db(transaction=True)
def test_backfill_leaves_legacy_deleted_rows_alone(
    mirror_tenant, mirror_workspace, mirror_ctx, architecture_element
):
    """``"deleted"`` is the pre-Phase-0 marker owned by
    ``backfill_outdated_from_legacy_status`` — the backfill only touches rows
    still carrying the field default."""
    from django.apps import apps as django_apps

    from persistence.models import ArchitectureElement
    from workflow.services import outdate

    with _tenant_scope(mirror_tenant.id):
        outdate(
            item_id=architecture_element.id,
            item_type="ArchitectureElement",
            workspace_id=mirror_workspace.id,
            ctx=mirror_ctx,
            reason="p1-16 backfill test",
        )
        ArchitectureElement.objects.filter(id=architecture_element.id).update(
            lifecycle_status="deleted"
        )

        backfill_lifecycle_status(django_apps, None)

        assert (
            ArchitectureElement.objects.get(id=architecture_element.id).lifecycle_status
            == "deleted"
        )


@pytest.mark.django_db(transaction=True)
def test_backfill_leaves_live_rows_active_and_is_idempotent(
    mirror_tenant, mirror_workspace, mirror_ctx, architecture_element
):
    from django.apps import apps as django_apps

    from persistence.models import ArchitectureElement

    with _tenant_scope(mirror_tenant.id):
        backfill_lifecycle_status(django_apps, None)
        backfill_lifecycle_status(django_apps, None)

        assert (
            ArchitectureElement.objects.get(id=architecture_element.id).lifecycle_status
            == "active"
        )
