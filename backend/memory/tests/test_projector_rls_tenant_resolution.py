"""RLS-in-Celery-worker regression test for ``MemoryProjector`` (final
whole-branch review ROUND 2, Finding A).

Root cause (see ``memory/projector.py``'s module docstring for the full
story): ``MemoryProjector._resolve_tenant_id`` resolved ``event.workspace_id``
-> ``tenant_id`` via ``Workspace.unscoped.filter(...)`` with no tenant
context armed -- mirroring ``ContextGraphProjector._resolve_tenant_id``.
``unscoped`` only bypasses the Django-ORM-manager-level tenant filter; it
does **not** bypass PostgreSQL Row-Level Security. ``pl_workspace`` has
``ENABLE + FORCE ROW LEVEL SECURITY`` (persistence/migrations/
0003_rls_policies.py) and the real Celery worker connects as the
least-privilege, NOSUPERUSER ``reqogniloom_app`` role (persistence/
db_roles.py, REQ-L2-PL-010) -- RLS applies to it regardless of ``unscoped``.
``application/event_bus.py::poll_and_dispatch`` (the real dispatch path)
never arms ``app.current_tenant`` before calling a subscriber, so the
``Workspace`` SELECT was silently hidden (0 rows) for every real event, and
``handle_event`` always took the "workspace gone" skip branch -- the SAME
end symptom as the original Finding 2 bug (no memory ever consolidated from
a real interaction), just via a subtler, still-RLS-shaped cause.

The default *test* DB connection authenticates as a Postgres superuser
(``persistence/reqogniloom.settings_test``'s ``DB_USER`` default), which
bypasses RLS unconditionally, even with FORCE ROW LEVEL SECURITY -- this is
why every existing ``memory/tests/test_projector.py`` /
``test_consolidation_e2e.py`` test (which also always runs inside
``active_tenant()``, pre-arming the session variable regardless) could not
have caught this. To reproduce the real production condition, ``SET ROLE``
to the least-privilege application role on the test's own connection before
calling ``handle_event`` -- same established pattern as
``llm_adapter/tests/test_rls_token_usage_444.py`` (issue #444),
``se_metrics/tests/test_rls_worker_threads_405.py`` (issue #405), and
``persistence/tests/test_migrations_and_indexes.py::
test_rls_blocks_raw_query_without_set_local``.

The fix (memory/projector.py, round-2 Finding A): ``tenant_id`` is now
stamped onto the ``INTERVIEW_CHAT_TURN`` payload at EMISSION time (both
sites in ``application/interview_service.py``, where real request-scoped
``ctx.tenant_id`` is genuinely available) and read straight off the payload
in the projector -- no ``Workspace`` DB query, and therefore no RLS
exposure, remains in the tenant-resolution path at all. The
``WorkspaceMemorySettings`` toggle lookup (Finding 4) is armed with that
payload-resolved ``tenant_id`` via ``memory.backends._tenant_context``
before running, so it is *correctly* subject to RLS (scoped to the right
tenant) instead of either raising or silently defaulting to the wrong
answer for the wrong reason.
"""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from django.db import connection

from application.event_bus import DomainEvent
from memory.projector import MemoryProjector
from persistence.db_roles import APP_DB_ROLE
from persistence.tenancy import TenantContext
from persistence.tests.factories import active_tenant, make_user, make_workspace

pytestmark = pytest.mark.django_db(transaction=True)

_IS_POSTGRES = connection.vendor == "postgresql"
_pg_only = pytest.mark.skipif(not _IS_POSTGRES, reason="PostgreSQL-only assertion")


def _set_app_role() -> None:
    with connection.cursor() as cursor:
        cursor.execute(f'SET ROLE "{APP_DB_ROLE}"')


def _reset_role() -> None:
    with connection.cursor() as cursor:
        cursor.execute("RESET ROLE")


@_pg_only
class TestMemoryProjectorTenantResolutionUnderRls:
    def test_handle_event_enqueues_task_with_no_ambient_context_under_app_role(self):
        """Reproduces the real Celery worker's exact starting condition:
        connected as ``reqogniloom_app`` (RLS FORCEd), no ``TenantContext``
        armed, no ``app.current_tenant`` session variable set. Before the
        fix, this would silently skip (0-row-hidden ``Workspace`` SELECT);
        after the fix, ``tenant_id`` never needs a DB lookup at all.

        Setup data is created under the superuser test connection (bypasses
        RLS -- not under test), then the connection is switched to the
        least-privilege role for the actual assertion.
        """
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            user = make_user(tenant)
            tenant_id, ws_id, user_id = tenant.id, ws.id, user.id
        assert not TenantContext.is_set()

        event = DomainEvent(
            event_type="InterviewChatTurn",
            entity_id=ws_id,
            workspace_id=ws_id,
            payload={
                "session_kind": "single",
                "user_message": "We are a B2B SaaS company.",
                "reply": "Got it, noted your company is B2B SaaS.",
                "extracted_fields": ["title"],
                "user_id": str(user_id),
                "tenant_id": str(tenant_id),
            },
        )

        _set_app_role()
        try:
            with patch("memory.projector.consolidate_interaction_task") as mock_task:
                MemoryProjector().handle_event(event)
        finally:
            _reset_role()

        assert mock_task.delay.call_count == 1, (
            "MemoryProjector.handle_event silently skipped a real chat-turn "
            "event under the RLS-enforced application role with no ambient "
            "tenant context -- tenant resolution must not depend on an "
            "RLS-gated Workspace query with no context armed (round-2 "
            "Finding A)"
        )
        kwargs = mock_task.delay.call_args.kwargs
        assert kwargs["tenant_id"] == str(tenant_id)
        assert kwargs["workspace_id"] == str(ws_id)
        assert kwargs["user_id"] == str(user_id)

    def test_disabled_workspace_toggle_honoured_with_no_ambient_context_under_app_role(self):
        """Same RLS condition as above, but with
        ``WorkspaceMemorySettings(enabled=False)`` -- proves the settings
        lookup is armed via ``_tenant_context(tenant_id)`` using the
        payload-resolved tenant, not run unscoped/context-free (which RLS
        would hide, silently defaulting to enabled=True for the wrong,
        DSGVO-relevant-wrong reason)."""
        from memory.models import WorkspaceMemorySettings

        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            user = make_user(tenant)
            WorkspaceMemorySettings.objects.create(
                tenant_id=tenant.id, workspace=ws, enabled=False
            )
            tenant_id, ws_id, user_id = tenant.id, ws.id, user.id
        assert not TenantContext.is_set()

        event = DomainEvent(
            event_type="InterviewChatTurn",
            entity_id=ws_id,
            workspace_id=ws_id,
            payload={
                "session_kind": "single",
                "user_message": "hello",
                "reply": "hi",
                "extracted_fields": [],
                "user_id": str(user_id),
                "tenant_id": str(tenant_id),
            },
        )

        _set_app_role()
        try:
            with patch("memory.projector.consolidate_interaction_task") as mock_task:
                MemoryProjector().handle_event(event)
        finally:
            _reset_role()

        assert mock_task.delay.call_count == 0, (
            "the disabled-workspace toggle was not honoured under the "
            "RLS-enforced role -- the settings lookup must be armed with "
            "the payload-resolved tenant_id, not run unscoped with no "
            "context"
        )

    def test_missing_settings_row_still_defaults_to_enabled_under_app_role(self):
        """No ``WorkspaceMemorySettings`` row at all, under the same RLS
        condition -- must still enqueue (missing row -> enabled=True is a
        genuine "no settings configured" default, not an RLS-hidden false
        negative, once tenant_id is correctly armed via the payload)."""
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            user = make_user(tenant)
            tenant_id, ws_id, user_id = tenant.id, ws.id, user.id
        assert not TenantContext.is_set()

        event = DomainEvent(
            event_type="InterviewChatTurn",
            entity_id=ws_id,
            workspace_id=ws_id,
            payload={
                "session_kind": "single",
                "user_message": "hello",
                "reply": "hi",
                "extracted_fields": [],
                "user_id": str(user_id),
                "tenant_id": str(tenant_id),
            },
        )

        _set_app_role()
        try:
            with patch("memory.projector.consolidate_interaction_task") as mock_task:
                MemoryProjector().handle_event(event)
        finally:
            _reset_role()

        assert mock_task.delay.call_count == 1


@_pg_only
def test_missing_tenant_id_in_payload_skips_without_touching_the_db(monkeypatch):
    """A malformed chat-turn payload with no ``tenant_id`` at all must be
    skipped WITHOUT any DB round-trip (there is no Workspace fallback left
    in the projector) -- proven by running this under the app role with no
    ambient context and no exception raised."""
    event = DomainEvent(
        event_type="InterviewChatTurn",
        entity_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        payload={
            "session_kind": "single",
            "user_message": "hello",
            "reply": "hi",
            "extracted_fields": [],
            "user_id": str(uuid.uuid4()),
        },
    )

    _set_app_role()
    try:
        with patch("memory.projector.consolidate_interaction_task") as mock_task:
            MemoryProjector().handle_event(event)  # must not raise
    finally:
        _reset_role()

    assert mock_task.delay.call_count == 0
