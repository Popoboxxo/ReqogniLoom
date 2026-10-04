"""RES-04 / RES-06 regressions for the Celery queue topology and task registry.

Covers the audit findings fixed here:

* AUD-2026-09-120 — all four task queues were declared with identical
  ``(exchange='default', routing_key='default')`` bindings, so a publish through
  the named exchange fanned out to every queue (up to 4 deliveries). Each queue
  must now own a distinct routing key on the shared direct exchange.
* AUD-2026-09-125 / -270 — ``audit.archive_lifecycle_manager`` was defined but
  never registered with a worker because ``audit/tasks.py`` did not exist and
  ``app.autodiscover_tasks()`` only imports ``<app>.tasks``. The monthly audit
  retention schedule therefore delivered to an unknown task.
* AUD-2026-09-126 — ``task_acks_late`` / ``task_reject_on_worker_lost`` were
  left at celery's pre-ack defaults, so an OOM-killed worker lost the in-flight
  task.

These tests exercise the real ``reqogniloom.celery`` app configuration and the
in-memory kombu transport; they need no database and no broker.
"""
from __future__ import annotations


def _queues():
    from reqogniloom.celery import app

    return list(app.conf.task_queues)


def test_task_queues_are_named_and_unique():
    names = [q.name for q in _queues()]
    assert names == ["default", "llm", "events", "memory"]
    assert len(names) == len(set(names))


def test_each_queue_has_a_distinct_routing_key():
    """AUD-2026-09-120: identical bindings delivered one message to 4 queues."""
    bindings = [(q.exchange.name, q.routing_key) for q in _queues()]
    assert len(bindings) == len(set(bindings)), (
        f"duplicate (exchange, routing_key) bindings: {bindings}"
    )
    assert len({q.routing_key for q in _queues()}) == len(bindings)


def test_default_exchange_binding_maps_to_one_queue():
    """The default exchange+routing-key pair must not be shared by 4 queues."""
    from reqogniloom.celery import app

    exchange = app.conf.task_default_exchange
    routing_key = app.conf.task_default_routing_key
    matches = [
        q.name
        for q in _queues()
        if q.exchange.name == exchange and q.routing_key == routing_key
    ]
    assert matches == ["default"], matches


def test_routed_tasks_target_their_own_queue():
    from reqogniloom.celery import app

    expected = {
        "llm_adapter.run_capability": "llm",
        "application.dispatch_outbox_events": "events",
        "memory.consolidate_interaction": "memory",
        "audit.archive_lifecycle_manager": "default",
    }
    for task_name, queue_name in expected.items():
        route = app.amqp.router.route({}, task_name)
        assert route["queue"].name == queue_name, (task_name, route)


def test_single_publish_matches_exactly_one_queue():
    """AUD-2026-09-120: one publish through the named exchange = 1 delivery.

    Declares the app's real queue topology on the in-memory transport, publishes
    a single message under the 'llm' routing key and counts what each queue
    received. Before the fix the same publish matched all four queues.
    """
    from kombu import Connection

    from reqogniloom.celery import app

    with Connection("memory://") as conn:
        channel = conn.default_channel
        bound = []
        for definition in app.conf.task_queues:
            queue = definition.bind(channel)
            queue.declare()
            bound.append(queue)

        producer = conn.Producer(channel)
        producer.publish(
            {"probe": "llm"},
            exchange="default",
            routing_key="llm",
            serializer="json",
        )

        received = {}
        for queue in bound:
            count = 0
            while queue.get(no_ack=True) is not None:
                count += 1
            received[queue.name] = count

    assert received == {"default": 0, "llm": 1, "events": 0, "memory": 0}, received


def test_default_routing_key_matches_only_the_default_queue():
    """The unrouted-task path must not fan out to llm/events/memory."""
    from kombu import Connection

    from reqogniloom.celery import app

    with Connection("memory://") as conn:
        channel = conn.default_channel
        bound = []
        for definition in app.conf.task_queues:
            queue = definition.bind(channel)
            queue.declare()
            bound.append(queue)

        producer = conn.Producer(channel)
        producer.publish(
            {"probe": "default"},
            exchange="default",
            routing_key="default",
            serializer="json",
        )

        received = {}
        for queue in bound:
            count = 0
            while queue.get(no_ack=True) is not None:
                count += 1
            received[queue.name] = count

    assert received == {"default": 1, "llm": 0, "events": 0, "memory": 0}, received


def test_late_acknowledgement_is_enabled():
    """AUD-2026-09-126: no pre-ack; requeue on worker loss."""
    from reqogniloom.celery import app

    assert app.conf.task_acks_late is True
    assert app.conf.task_reject_on_worker_lost is True


def test_audit_archive_task_is_autodiscovered():
    """AUD-2026-09-125/270: ``audit/tasks.py`` is the autodiscovery hook."""
    import importlib

    from celery import Task

    from reqogniloom.celery import app

    module = importlib.import_module("audit.tasks")
    task = module.run_monthly_archive_task

    assert isinstance(task, Task), "archive task is not a Celery Task"
    assert task.name == "audit.archive_lifecycle_manager"
    assert "audit.archive_lifecycle_manager" in app.tasks, sorted(
        name for name in app.tasks if name.startswith("audit.")
    )
