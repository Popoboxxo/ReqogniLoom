import os
from celery import Celery
from kombu import Queue

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
#   - default  : everything else (resilience/audit maintenance tasks).
#
# Routes are matched against the registered task *name* (see @shared_task
# name=...). Unmatched tasks fall through to task_default_queue.
# ---------------------------------------------------------------------------
app.conf.task_queues = (
    Queue('default'),
    Queue('llm'),
    Queue('events'),
)
app.conf.task_default_queue = 'default'
app.conf.task_routes = {
    'llm_adapter.*': {'queue': 'llm'},
    'application.dispatch_outbox_events': {'queue': 'events'},
}

# Load task modules from all registered Django apps.
app.autodiscover_tasks()
