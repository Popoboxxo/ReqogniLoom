"""Gunicorn worker that makes ``--threads`` bound real ASGI concurrency (#1166).

The problem
-----------
The production entry point runs ``gunicorn -k uvicorn.workers.UvicornWorker``.
Under ASGI, Django executes every sync view inside a thread-sensitive executor
that asgiref creates *per request* (``django.core.handlers.asgi`` wraps the
whole request in ``ThreadSensitiveContext``). There is therefore no fixed
thread pool to size: each concurrent request gets its own worker thread, and —
because Django's DB connection is thread-local — its own PostgreSQL backend.

The stock ``uvicorn.workers.UvicornWorker`` ignores gunicorn's ``--threads``
option entirely (verified against uvicorn 0.54: it forwards only
``timeout_keep_alive``/``timeout_notify``/``limit_max_requests``/… to
``uvicorn.Config``). ``ASGI_THREADS`` is not a knob uvicorn reads either. So an
operator who writes ``--threads 8`` expecting a bound silently gets none, and
PostgreSQL connection slots can be exhausted under load.

The fix
-------
This thin worker maps the effective thread budget onto uvicorn's
``limit_concurrency``, which *is* enforced per worker by the HTTP protocol
(``protocols/http/httptools_impl.py``): once ``limit`` connections/tasks are
open, further ones are answered with HTTP 503 instead of piling on more threads
and more DB connections. Combined with ``CONN_MAX_AGE=0`` (see
``reqogniloom/settings.py``), the per-process connection ceiling is
``workers × threads``.

The limit is read from gunicorn's ``--threads`` first (so the standard flag
works) and falls back to the ``ASGI_THREADS`` environment variable. A value
``<= 1`` — gunicorn's default ``--threads`` is 1 — leaves the behaviour
unchanged (no limit), preserving the previous deployment for anyone who has not
opted in.
"""
from __future__ import annotations

import os
import warnings
from typing import Any

# uvicorn.workers emits its own DeprecationWarning pointing at the standalone
# `uvicorn-worker` package; suppress only that one so importing this module does
# not spam the worker boot log. Switching package would add a dependency, which
# this issue deliberately avoids.
with warnings.catch_warnings():
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    from uvicorn.workers import UvicornWorker


def _resolve_limit(cfg_threads: int) -> int:
    """Return the effective concurrency limit (0 = unbounded)."""
    if cfg_threads and cfg_threads > 1:
        return cfg_threads
    raw = (os.environ.get("ASGI_THREADS") or "").strip()
    if raw.isdigit():
        return int(raw)
    return 0


class BoundedUvicornWorker(UvicornWorker):
    """``UvicornWorker`` that turns the thread budget into ``limit_concurrency``."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        limit = _resolve_limit(getattr(self.cfg, "threads", 0) or 0)
        if limit > 0:
            # Read by the HTTP protocol at connection time, so setting it before
            # ``_serve()`` constructs the Server is effective.
            self.config.limit_concurrency = limit


__all__ = ["BoundedUvicornWorker"]
