import os
from celery import Celery
from kombu import Exchange, Queue

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'reqogniloom.settings')

app = Celery('reqogniloom')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
# - namespace='CELERY' means all celery-related configuration keys
#   should have a `CELERY_` prefix.
app.config_from_object('django.conf:settings', namespace='CELERY')

# ---------------------------------------------------------------------------
# Task queues & routing (REQ-077, DEEP_SYSTEM_ANALYSIS.md BE-21)
#
# Splitting work into dedicated queues is the precondition for scaling each
# workload independently. With a single shared queue a slow LLM call (seconds)
# blocks the 5-second outbox dispatch and every other task behind it.
#
#   - llm      : LLM adapter capability runs (potentially long / rate-limited).
#   - events   : domain-event outbox dispatch (latency-sensitive, high volume).
#   - memory   : AI-memory projection tasks (ai-memory-and-search plan).
#   - default  : everything else (resilience/audit maintenance tasks).
#
# RES-04 / AUD-2026-09-120 — DECISION (Option A, "real routing"):
# The queues are kept because each one has a distinct purpose and a matching
# ``task_routes`` entry; Option B ("collapse to a single queue") would discard
# that documented routing intent. The bug was that the previous bare
# ``Queue(name)`` definitions all fell back to the celery defaults
# ``exchange='default'`` / ``routing_key='default'``, so the four queues were
# declared with *identical* bindings
# (``_kombu.binding.default`` = ``default\x06\x16\x06\x16{default,llm,events,memory}``).
# Any publish through that named exchange + routing key then matched all four
# queues at once (verified live: one message landed in default, llm, events and
# memory = 4 deliveries). Each queue now declares its own routing key on the
# shared direct exchange, so a publish matches exactly one queue.
#
# Routes are matched against the registered task *name* (see @shared_task
# name=...). Unmatched tasks fall through to task_default_queue.
# ---------------------------------------------------------------------------
_DEFAULT_EXCHANGE = Exchange('default', type='direct')
app.conf.task_queues = (
    Queue('default', exchange=_DEFAULT_EXCHANGE, routing_key='default'),
    Queue('llm', exchange=_DEFAULT_EXCHANGE, routing_key='llm'),
    Queue('events', exchange=_DEFAULT_EXCHANGE, routing_key='events'),
    Queue('memory', exchange=_DEFAULT_EXCHANGE, routing_key='memory'),
)
app.conf.task_default_queue = 'default'
# Pin the publish target explicitly. The 'default' routing key is bound by the
# 'default' queue only, so an unrouted task cannot fan out to llm/events/memory.
app.conf.task_default_exchange = 'default'
app.conf.task_default_exchange_type = 'direct'
app.conf.task_default_routing_key = 'default'
app.conf.task_routes = {
    'llm_adapter.*': {'queue': 'llm', 'routing_key': 'llm'},
    'application.dispatch_outbox_events': {'queue': 'events', 'routing_key': 'events'},
    'memory.*': {'queue': 'memory', 'routing_key': 'memory'},
}

# ---------------------------------------------------------------------------
# Acknowledgement semantics (RES-04 / AUD-2026-09-126)
#
# Acknowledge a task only *after* it ran, and requeue it when a worker child
# dies mid-task (OOM-kill / SIGKILL). With the previous celery defaults
# (``task_acks_late=False``, ``task_reject_on_worker_lost=False``) the message
# was acknowledged before execution, so the live OOM-kills silently lost the
# in-flight task. This is at-least-once delivery: the happy path still delivers
# exactly once, but a crashed worker re-runs the task, so task bodies must be
# idempotent — the outbox consumer (SELECT FOR UPDATE skip_locked) and the
# audit archive (export-before-drop) are; repeated LLM/memory runs on worker
# loss are accepted as the price of not losing work.
# ---------------------------------------------------------------------------
app.conf.task_acks_late = True
app.conf.task_reject_on_worker_lost = True

# Load task modules from all registered Django apps.
app.autodiscover_tasks()
