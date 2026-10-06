"""Shared state for the reqogniloom plugin — ``$HERMES_HOME/reqogniloom/state.json``.

One small JSON file, read-modify-written under a best-effort exclusive lock,
because its writers are separate short-lived processes: every ``/reqogniloom``
invocation is a fresh process, and the listen mode's capture worker is a
detached one (``_capture.py``). Losing a write here means losing a *suggestion*,
never an artifact — artifacts are only ever created through a human
``/reqogniloom accept``.

Layout (all keys optional)::

    {
      "session_id": "...", "workspace_id": "...",   # the hand-driven interview
      "listen": {                                    # ambient "listen" mode
        "enabled": true,
        "workspace_id": "3f0…",
        "session_id": "9ac…",                        # the type-less multi session
        "min_interval_seconds": 45,
        "last_capture_at": 1759700000.0              # epoch seconds
      },
      "suggestions": [                               # review-before-create queue
        {"id": "…", "session_id": "…", "created_at": "2026-10-06T23:40:11+00:00",
         "source": "listen", "signature": "…", "items": [{"type": "Requirement", …}]}
      ]
    }

Splitting this out of ``__init__.py`` (rather than importing from it) keeps the
detached worker dependency-free: it must not drag the whole plugin package —
and with it Hermes' plugin machinery — into a bare ``python3`` process.
"""
from __future__ import annotations

import json
import logging
import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, Optional

logger = logging.getLogger(__name__)

#: Hard cap on the review queue, oldest dropped first. A suggestion nobody acts
#: on must not grow the state file (and the ``/reqogniloom review`` output)
#: without bound.
MAX_SUGGESTIONS = 20

#: Seconds to wait for the state lock before giving up on it. Every writer here
#: is a short local read-modify-write, so contention is a one-off collision.
LOCK_TIMEOUT_SECONDS = 5.0


def hermes_home() -> Path:
    """``$HERMES_HOME`` when set, else ``~/.hermes``.

    Read from the environment at call time rather than cached at import: the
    plugin is loaded once per process, but the tests and the detached worker
    each set their own home.
    """
    val = (os.environ.get("HERMES_HOME") or "").strip()
    return Path(val) if val else Path.home() / ".hermes"


def state_path() -> Path:
    return hermes_home() / "reqogniloom" / "state.json"


def load_state() -> Dict[str, Any]:
    """Current state, or ``{}`` for a missing/unreadable/corrupt file.

    A corrupt file reading as "no state" is deliberate: the alternative is the
    slash command refusing to run until an operator deletes a file they cannot
    see. The corrupt copy is kept as ``state.json.bad`` so nothing is lost
    silently.
    """
    path = state_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("reqogniloom state unreadable (%s); starting from empty", exc)
        try:
            path.replace(path.with_suffix(".json.bad"))
        except OSError:
            pass
        return {}
    return data if isinstance(data, dict) else {}


def save_state(state: Dict[str, Any]) -> None:
    """Replace the state file atomically (temp file + ``os.replace``)."""
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)


@contextmanager
def state_lock(timeout: float = LOCK_TIMEOUT_SECONDS) -> Iterator[bool]:
    """Best-effort exclusive lock next to the state file.

    Yields ``True`` when the lock was taken and ``False`` when it timed out: a
    caller that cannot lock proceeds anyway rather than blocking a slash command
    or a background capture. Both uses are last-writer-wins on a file whose worst
    case is a dropped suggestion.
    """
    lock_path = state_path().with_suffix(".json.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout
    fd: Optional[int] = None
    while fd is None:
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if time.monotonic() >= deadline:
                logger.warning("reqogniloom state lock timed out; proceeding unlocked")
                yield False
                return
            time.sleep(0.05)
        except OSError:
            yield False
            return
    try:
        yield True
    finally:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            lock_path.unlink()
        except OSError:
            pass


def update_state(mutate: Callable[[Dict[str, Any]], Optional[Dict[str, Any]]]) -> Dict[str, Any]:
    """Locked read-modify-write. ``mutate`` returns the new state (or ``None``
    to leave it unchanged) and must not raise; the caller owns error handling.
    """
    with state_lock():
        state = load_state()
        result = mutate(state)
        new_state = state if result is None else result
        save_state(new_state)
        return new_state
