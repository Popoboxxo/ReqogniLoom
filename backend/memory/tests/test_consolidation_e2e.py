"""End-to-end regression proof for the full memory-consolidation loop
(final whole-branch review Finding 7).

Exercises the REAL chain end to end, nothing internal mocked away except the
two genuine external calls (the interview-chat LLM completion and the
``memory.extract`` LLM completion) and the embedding provider (set to
``mock`` -- no real model/network needed):

    real interview chat turn (``InterviewService.generate_chat_turn``)
    -> a real ``DomainEvent`` through the real event bus (Transactional
       Outbox -- ``application.event_bus``)
    -> the real ``MemoryProjector`` (registered via
       ``MemoryConfig.ready()``, the same startup hook that runs in
       production)
    -> the real Celery task BODY (``consolidate_interaction_task``, invoked
       via ``.run(**kwargs)`` -- see the ``_run_celery_tasks_inline``
       fixture below for why ``.delay()`` itself is not usable here)
    -> a real ``WorkspaceMemory`` row written via the real
       ``MemoryBackend``
    -> a SUBSEQUENT chat turn's ``build_memory_context()`` call retrieves it
       and it appears in the rendered prompt.

This is the test Findings 2 and 3 would have caught immediately:

* Finding 2: before the fix, ``MemoryProjector.handle_event()`` read
  ``payload["tenant_id"]``/``payload["user_id"]``/``payload["message"]`` --
  keys no real producer (``interview_service.py``'s ``INTERVIEW_CHAT_TURN``
  emissions) ever set -- so it ALWAYS took the "missing tenant/user" skip
  branch and no memory was ever consolidated from a real interaction, in any
  deployment, ever. This test would have asserted an empty ``WorkspaceMemory``
  queryset and failed.
* Finding 3: separately, even with Finding 2 fixed, no docker-compose celery
  worker consumed the new ``memory`` queue at all -- irrelevant to THIS
  in-process test (which never touches Redis or a real worker by
  construction -- see the ``_run_celery_tasks_inline`` fixture below), but
  see ``docker-compose.yml``'s celery service definition for that fix, which
  this test cannot exercise. Both fixes were required for the real pipeline
  to run; this test proves the in-process half (2), the docker-compose diff
  proves the other half (3).

``pytest.mark.django_db(transaction=True)`` (NOT the default) is required:
``DomainEventBus.publish()`` defers the outbox insert to
``transaction.on_commit()``, which only fires on a REAL commit -- the
default non-transactional test wrapper (one outer atomic block, rolled back
at the end) never commits, so the event would silently never reach the
outbox. Mirrors ``context_graph/tests/test_projector.py``'s identical
real-mutation-reaches-the-projector end-to-end test, which uses the same
marker for the same reason.
"""
from __future__ import annotations

import pytest

from application.event_bus import poll_and_dispatch
from application.interview_service import InterviewService
from memory.backends import _tenant_context
from memory.models import WorkspaceMemory
from persistence.tenancy import TenantContext
from persistence.tests.factories import active_tenant, editor_ctx, make_workspace

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def _run_celery_tasks_inline(monkeypatch):
    """Make ``consolidate_interaction_task.delay(...)`` run its real body
    synchronously, in-process, instead of publishing to a broker.

    ``settings_test.py`` sets ``CELERY_TASK_ALWAYS_EAGER = True`` for exactly
    this purpose, but it has no effect in THIS repo's actual test-running
    convention: ``pytest`` is invoked with ``DJANGO_SETTINGS_MODULE`` already
    set to ``reqogniloom.settings`` (production) in the container
    environment, and pytest-django/Django honour an already-set environment
    variable over ``pyproject.toml``'s ini option -- confirmed empirically
    (the pytest banner reports ``settings: reqogniloom.settings (from env)``,
    and ``reqogniloom.celery``'s ``app.config_from_object(...)`` caches
    ``task_always_eager=False`` from that module the first time ``app.conf``
    is touched in the process). Under that config, an unmocked ``.delay()``
    silently publishes to the real Redis broker and returns immediately --
    no exception, no log line, just nothing written, because no worker
    consumes the test database.

    Calling the task's ``.run(**kwargs)`` directly (the Celery ``Task``
    instance's actual undecorated function body) mirrors this codebase's own
    established precedent for testing a Celery task synchronously without a
    broker -- see ``llm_adapter/tests/test_tenant_teardown_522.py``'s
    ``tasks.run_capability.run(...)`` calls. This replaces ONLY the
    async-dispatch transport (which a test must never depend on anyway); the
    real event bus, the real ``MemoryProjector``, and the real task/business
    logic all still run unmocked.
    """
    from memory.tasks import consolidate_interaction_task

    def _run_inline(*args, **kwargs):
        return consolidate_interaction_task.run(*args, **kwargs)

    monkeypatch.setattr(consolidate_interaction_task, "delay", _run_inline)


class _ChatFakeProvider:
    """Non-vacuous LLM double for the interview-chat completion -- same
    principle as ``application.tests.test_interview_service._ChatFakeProvider``:
    returns exactly what a real provider following the chat_turn prompt's
    JSON contract would, driven by the caller, and records the rendered
    prompt it was called with so a test can assert on prompt content (e.g.
    that ``build_memory_context()``'s output actually reached it)."""

    def __init__(self, response_json: str):
        self._response_json = response_json
        self.last_prompt = None

    def complete(self, prompt, *, purpose="", context=None, timeout=None):
        self.last_prompt = prompt
        return self._response_json


class TestFullMemoryConsolidationLoop:
    def test_chat_turn_to_stored_memory_to_next_prompt(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")

        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            ctx = editor_ctx(tenant, ws)

            session = InterviewService().start(ctx, "Requirement", ws.id)

            # Turn 1: the user states a durable fact in the interview chat.
            # The chat-turn LLM call and the memory.extract LLM call
            # (inside consolidate_interaction) are two DIFFERENT completions
            # in the real pipeline -- both are mocked here, independently,
            # exactly like memory/tests/test_consolidation.py already mocks
            # memory.tasks._call_llm for the extraction call alone.
            chat_provider = _ChatFakeProvider(
                '{"extracted_fields": {}, "reply": "Noted, thanks."}'
            )
            monkeypatch.setattr(
                InterviewService, "_resolve_provider", lambda self: (chat_provider, "anthropic", None)
            )
            fake_extraction_response = (
                '{"facts": [{"content": "The project uses hexagonal architecture.", '
                '"scope": "workspace"}]}'
            )
            monkeypatch.setattr("memory.tasks._call_llm", lambda prompt: fake_extraction_response)

            InterviewService().generate_chat_turn(
                ctx, session.id, "We are building this with hexagonal architecture."
            )

            # Real outbox -> real dispatch -> real MemoryProjector -> real
            # (eager) Celery task -> real MemoryBackend.upsert().
            processed = poll_and_dispatch()

            assert processed >= 1, (
                "poll_and_dispatch found nothing to dispatch -- the "
                "generate_chat_turn() call above never reached the outbox "
                "(check the on_commit wiring, not this test)"
            )

            stored = WorkspaceMemory.objects.filter(workspace_id=ws.id)
            assert stored.exists(), (
                "no WorkspaceMemory row was written -- the producer -> event "
                "bus -> MemoryProjector -> Celery task -> MemoryBackend chain "
                "is broken (this is exactly the failure mode Findings 2/3 of "
                "the final whole-branch review fixed: a payload-contract "
                "mismatch made MemoryProjector always skip real events, and "
                "no worker consumed the 'memory' queue either)"
            )
            assert "hexagonal architecture" in stored.first().content

            # Turn 2: a SUBSEQUENT chat turn's build_memory_context() call
            # must retrieve the just-consolidated fact and it must appear in
            # the rendered prompt -- proves the READ side closes the loop,
            # not just that a row landed in the table.
            chat_provider_2 = _ChatFakeProvider('{"extracted_fields": {}, "reply": "ok"}')
            monkeypatch.setattr(
                InterviewService, "_resolve_provider", lambda self: (chat_provider_2, "anthropic", None)
            )

            InterviewService().generate_chat_turn(
                ctx, session.id, "What architecture style are we using again?"
            )

        assert "hexagonal architecture" in chat_provider_2.last_prompt, (
            "the consolidated memory fact never made it back into a "
            "subsequent prompt -- build_memory_context() is not retrieving "
            "what consolidate_interaction just wrote"
        )

    def test_disabled_workspace_breaks_the_loop_at_the_projector(self, monkeypatch):
        """Finding 4, proven end-to-end: with the workspace memory toggle
        OFF, the same real chat turn must produce NO consolidation at all --
        no WorkspaceMemory row, and (implicitly) no memory.extract LLM call
        (the mocked _call_llm would raise AttributeError-free either way,
        but proving zero rows is the real DSGVO-relevant contract)."""
        from memory.models import WorkspaceMemorySettings

        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")

        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            WorkspaceMemorySettings.objects.create(tenant_id=tenant.id, workspace=ws, enabled=False)
            ctx = editor_ctx(tenant, ws)

            session = InterviewService().start(ctx, "Requirement", ws.id)
            chat_provider = _ChatFakeProvider('{"extracted_fields": {}, "reply": "Noted."}')
            monkeypatch.setattr(
                InterviewService, "_resolve_provider", lambda self: (chat_provider, "anthropic", None)
            )
            monkeypatch.setattr(
                "memory.tasks._call_llm",
                lambda prompt: '{"facts": [{"content": "Should never be stored.", "scope": "workspace"}]}',
            )

            InterviewService().generate_chat_turn(
                ctx, session.id, "We are building this with hexagonal architecture."
            )
            poll_and_dispatch()

            assert not WorkspaceMemory.objects.filter(workspace_id=ws.id).exists()

    def test_full_loop_survives_no_ambient_tenant_context_at_dispatch(self, monkeypatch):
        """Final whole-branch review ROUND 2, Finding A -- proven end-to-end.

        The real Celery worker's ``poll_and_dispatch`` (application/
        event_bus.py) runs with NO ambient tenant context: nothing calls
        ``persistence.middleware.set_request_tenant`` before dispatching to
        ``MemoryProjector.handle_event``. Both tests above (and every other
        test in this module) call ``poll_and_dispatch()`` from INSIDE
        ``with active_tenant():``, which pre-arms both isolation layers for
        the whole block -- structurally unable to catch a tenant-resolution
        bug that only manifests with no context armed (see
        memory/projector.py's module docstring for the RLS root cause this
        guards against).

        This test moves ``poll_and_dispatch()`` OUTSIDE the ``active_tenant()``
        block (whose ``__exit__`` already clears both layers) to genuinely
        reproduce the real worker's starting condition, then re-arms tenant
        context only for the final read-side assertion.
        """
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")

        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            ctx = editor_ctx(tenant, ws)

            session = InterviewService().start(ctx, "Requirement", ws.id)

            chat_provider = _ChatFakeProvider(
                '{"extracted_fields": {}, "reply": "Noted, thanks."}'
            )
            monkeypatch.setattr(
                InterviewService, "_resolve_provider", lambda self: (chat_provider, "anthropic", None)
            )
            fake_extraction_response = (
                '{"facts": [{"content": "The project uses hexagonal architecture.", '
                '"scope": "workspace"}]}'
            )
            monkeypatch.setattr("memory.tasks._call_llm", lambda prompt: fake_extraction_response)

            InterviewService().generate_chat_turn(
                ctx, session.id, "We are building this with hexagonal architecture."
            )
            tenant_id, ws_id = tenant.id, ws.id

        # active_tenant()'s __exit__ already cleared both isolation layers;
        # assert it explicitly so this test genuinely proves the
        # no-ambient-context case, not an accident of ordering.
        assert not TenantContext.is_set()

        processed = poll_and_dispatch()
        assert processed >= 1, (
            "poll_and_dispatch found nothing to dispatch with no ambient "
            "tenant context -- check the outbox wiring, not this test"
        )

        with _tenant_context(tenant_id):
            stored = WorkspaceMemory.objects.filter(workspace_id=ws_id)
            assert stored.exists(), (
                "no WorkspaceMemory row was written when poll_and_dispatch ran "
                "with NO ambient tenant context -- MemoryProjector's tenant "
                "resolution still depends on context being pre-armed by the "
                "caller (round-2 Finding A: this is exactly the real Celery "
                "worker's starting condition, which the other tests in this "
                "module (running inside active_tenant()) cannot exercise)"
            )
            assert "hexagonal architecture" in stored.first().content
