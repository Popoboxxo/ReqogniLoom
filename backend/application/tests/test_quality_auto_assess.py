"""Issue #1578: the gates around automatic quality assessment.

The LLM call is patched out — these tests pin *whether* and *as whom* a run is
allowed, which is where the cost and identity risks live.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from django.core.cache import cache

from application.models import DomainEventOutbox
from application.quality_auto_assess import (
    TRIGGER_CREATE,
    TRIGGER_PERIODIC,
    TRIGGER_TRANSITION,
    QualityAutoAssessor,
    register_auto_assessor_on_event_bus,
    subscribed_event_types,
)
from auth_tenancy.models import ApiKey, UserRole
from persistence.models import Tenant, User, Workspace
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    TenantContext.clear_tenant()
    yield
    cache.clear()
    TenantContext.clear_tenant()


@pytest.fixture
def tenant() -> Tenant:
    return Tenant.objects.create(
        name="Auto Assess", slug=f"auto-assess-{uuid.uuid4().hex[:8]}"
    )


def _workspace(tenant: Tenant, preset: str = "extended") -> Workspace:
    TenantContext.set_tenant(tenant.id)
    try:
        return Workspace.objects.create(
            tenant=tenant, name=f"WS {preset}", preset={"name": preset}
        )
    finally:
        TenantContext.clear_tenant()


def _agent_key(tenant: Tenant, workspace: Workspace, *, roles=("editor",)) -> ApiKey:
    TenantContext.set_tenant(tenant.id)
    try:
        suffix = uuid.uuid4().hex[:8]
        user = User.objects.create(
            username=f"agent-{suffix}",
            email=f"agent-{suffix}@example.com",
            tenant=tenant,
        )
        for role in roles:
            UserRole.objects.create(
                tenant=tenant, workspace=workspace, user=user, role=role
            )
        return ApiKey.objects.create(
            tenant=tenant,
            user=user,
            name="quality-bot",
            key_hash=f"sha256p1:{uuid.uuid4().hex}",
            principal_type="agent",
            agent_label="Quality Bot",
            scope="write",
        )
    finally:
        TenantContext.clear_tenant()


def _assess(*, tenant, workspace, key=None, trigger=TRIGGER_TRANSITION):
    with patch(
        "application.quality_auto_assess.QualityService.assess",
        return_value=(MagicMock(), False),
    ) as assess:
        result = QualityAutoAssessor().run_for(
            tenant_id=tenant.id,
            workspace_id=workspace.id,
            entity_type="Requirement",
            entity_id=uuid.uuid4(),
            trigger=trigger,
        )
    return result, assess, key


def test_the_flag_is_off_by_default(settings, tenant) -> None:
    settings.QUALITY_AUTO_ASSESS_ENABLED = False
    workspace = _workspace(tenant)

    result, assess, _ = _assess(tenant=tenant, workspace=workspace)

    assert result == "skipped:flag_off"
    assess.assert_not_called()


def test_an_unassessable_type_skips(settings, tenant) -> None:
    settings.QUALITY_AUTO_ASSESS_ENABLED = True
    workspace = _workspace(tenant)

    with patch("application.quality_auto_assess.QualityService.assess") as assess:
        result = QualityAutoAssessor().run_for(
            tenant_id=tenant.id,
            workspace_id=workspace.id,
            entity_type="GlossaryTerm",
            entity_id=uuid.uuid4(),
            trigger=TRIGGER_PERIODIC,
        )

    assert result == "skipped:type_not_assessable"
    assess.assert_not_called()


def test_only_the_extended_tier_runs(settings, tenant) -> None:
    settings.QUALITY_AUTO_ASSESS_ENABLED = True
    for preset in ("minimal", "standard"):
        workspace = _workspace(tenant, preset=preset)
        key = _agent_key(tenant, workspace)
        settings.QUALITY_AUTO_ASSESS_AGENT_KEY_ID = str(key.id)

        result, assess, _ = _assess(tenant=tenant, workspace=workspace)

        assert result == "skipped:tier_not_extended", preset
        assess.assert_not_called()


def test_no_agent_key_means_no_run(settings, tenant) -> None:
    settings.QUALITY_AUTO_ASSESS_ENABLED = True
    settings.QUALITY_AUTO_ASSESS_AGENT_KEY_ID = ""
    workspace = _workspace(tenant)

    result, assess, _ = _assess(tenant=tenant, workspace=workspace)

    assert result == "skipped:no_agent_key"
    assess.assert_not_called()


def test_a_revoked_key_means_no_run(settings, tenant) -> None:
    from django.utils import timezone

    settings.QUALITY_AUTO_ASSESS_ENABLED = True
    workspace = _workspace(tenant)
    key = _agent_key(tenant, workspace)
    TenantContext.set_tenant(tenant.id)
    try:
        ApiKey.objects.filter(id=key.id).update(revoked_at=timezone.now())
    finally:
        TenantContext.clear_tenant()
    settings.QUALITY_AUTO_ASSESS_AGENT_KEY_ID = str(key.id)

    result, assess, _ = _assess(tenant=tenant, workspace=workspace)

    assert result == "skipped:no_agent_key"
    assess.assert_not_called()


def test_the_run_uses_the_agent_identity(settings, tenant) -> None:
    settings.QUALITY_AUTO_ASSESS_ENABLED = True
    workspace = _workspace(tenant)
    key = _agent_key(tenant, workspace, roles=("editor",))
    settings.QUALITY_AUTO_ASSESS_AGENT_KEY_ID = str(key.id)

    result, assess, _ = _assess(tenant=tenant, workspace=workspace)

    assert result == "assessed"
    ctx = assess.call_args.args[0]
    assert ctx.actor_type == "agent"
    assert ctx.api_key_id == key.id
    assert ctx.user_id == key.user_id
    assert "editor" in ctx.active_roles
    assert assess.call_args.kwargs["trigger"] == TRIGGER_TRANSITION


def test_a_cached_assessment_counts_as_unchanged(settings, tenant) -> None:
    settings.QUALITY_AUTO_ASSESS_ENABLED = True
    workspace = _workspace(tenant)
    key = _agent_key(tenant, workspace)
    settings.QUALITY_AUTO_ASSESS_AGENT_KEY_ID = str(key.id)

    with patch(
        "application.quality_auto_assess.QualityService.assess",
        return_value=(MagicMock(), True),
    ):
        result = QualityAutoAssessor().run_for(
            tenant_id=tenant.id,
            workspace_id=workspace.id,
            entity_type="Requirement",
            entity_id=uuid.uuid4(),
            trigger=TRIGGER_TRANSITION,
        )

    assert result == "skipped:unchanged_hash"


def test_the_second_run_within_the_interval_is_throttled(settings, tenant) -> None:
    settings.QUALITY_AUTO_ASSESS_ENABLED = True
    settings.QUALITY_AUTO_ASSESS_MIN_INTERVAL_SECONDS = 3600
    workspace = _workspace(tenant)
    key = _agent_key(tenant, workspace)
    settings.QUALITY_AUTO_ASSESS_AGENT_KEY_ID = str(key.id)
    entity_id = uuid.uuid4()

    with patch(
        "application.quality_auto_assess.QualityService.assess",
        return_value=(MagicMock(), False),
    ) as assess:
        first = QualityAutoAssessor().run_for(
            tenant_id=tenant.id,
            workspace_id=workspace.id,
            entity_type="Requirement",
            entity_id=entity_id,
            trigger=TRIGGER_TRANSITION,
        )
        second = QualityAutoAssessor().run_for(
            tenant_id=tenant.id,
            workspace_id=workspace.id,
            entity_type="Requirement",
            entity_id=entity_id,
            trigger=TRIGGER_TRANSITION,
        )

    assert first == "assessed"
    assert second == "skipped:throttled"
    assert assess.call_count == 1


def test_a_provider_failure_is_recorded_without_a_retry(settings, tenant) -> None:
    settings.QUALITY_AUTO_ASSESS_ENABLED = True
    workspace = _workspace(tenant)
    key = _agent_key(tenant, workspace)
    settings.QUALITY_AUTO_ASSESS_AGENT_KEY_ID = str(key.id)

    with patch(
        "application.quality_auto_assess.QualityService.assess",
        side_effect=RuntimeError("provider down"),
    ) as assess:
        result = QualityAutoAssessor().run_for(
            tenant_id=tenant.id,
            workspace_id=workspace.id,
            entity_type="Requirement",
            entity_id=uuid.uuid4(),
            trigger=TRIGGER_PERIODIC,
        )

    assert result == "failed"
    assert assess.call_count == 1


def test_the_assessor_subscribes_to_transitions_and_creates() -> None:
    event_types = subscribed_event_types()

    assert DomainEventOutbox.EventType.WORKFLOW_TRANSITIONED.value in event_types
    for entity_type in ("Requirement", "Adr", "TestCase", "Risk"):
        assert f"{entity_type}Created" in event_types


def test_the_handler_dispatches_a_task_for_a_transition(settings) -> None:
    settings.QUALITY_AUTO_ASSESS_ENABLED = True
    event = MagicMock()
    event.event_type = DomainEventOutbox.EventType.WORKFLOW_TRANSITIONED.value
    event.entity_id = uuid.uuid4()
    event.workspace_id = uuid.uuid4()
    event.tenant_id = uuid.uuid4()
    event.payload = {"item_type": "Requirement"}

    with patch("application.tasks.quality_auto_assess_entity.delay") as delay:
        QualityAutoAssessor().handle_event(event)

    delay.assert_called_once()
    kwargs = delay.call_args.kwargs
    assert kwargs["entity_type"] == "Requirement"
    assert kwargs["trigger"] == TRIGGER_TRANSITION
    assert kwargs["tenant_id"] == str(event.tenant_id)


def test_the_handler_ignores_non_assessable_events(settings) -> None:
    settings.QUALITY_AUTO_ASSESS_ENABLED = True
    event = MagicMock()
    event.event_type = DomainEventOutbox.EventType.WORKFLOW_TRANSITIONED.value
    event.payload = {"item_type": "GlossaryTerm"}

    with patch("application.tasks.quality_auto_assess_entity.delay") as delay:
        QualityAutoAssessor().handle_event(event)

    delay.assert_not_called()


def test_a_created_event_uses_the_create_trigger(settings) -> None:
    settings.QUALITY_AUTO_ASSESS_ENABLED = True
    event = MagicMock()
    event.event_type = "TestcaseCreated"  # not a real type — control case
    event.payload = {}

    with patch("application.tasks.quality_auto_assess_entity.delay") as delay:
        QualityAutoAssessor().handle_event(event)
    delay.assert_not_called()

    event.event_type = "TestCaseCreated"
    event.entity_id = uuid.uuid4()
    event.workspace_id = uuid.uuid4()
    event.tenant_id = uuid.uuid4()
    with patch("application.tasks.quality_auto_assess_entity.delay") as delay:
        QualityAutoAssessor().handle_event(event)
    assert delay.call_args.kwargs["trigger"] == TRIGGER_CREATE


def test_registration_covers_every_declared_event() -> None:
    with patch("application.event_bus.get_event_bus") as bus:
        registered = register_auto_assessor_on_event_bus()

    assert registered == len(subscribed_event_types())
    assert bus.return_value.register_subscriber.call_count == registered
