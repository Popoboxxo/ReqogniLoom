"""Detached listen-mode worker: turn one captured user message into suggestions.

Spawned by the ``pre_llm_call`` hook (see ``__init__.py``) as its own process,
deliberately. The hook sits on the turn's critical path, while one capture round
is a couple of network calls to ReqogniLoom *plus* an LLM turn on the server
side; running it inline would add that latency to the user's own reply.

Contract with the parent:

* ``argv[1]`` is the path to a JSON payload ``{"text", "platform", "session_key"}``
  (the parent writes it, this process deletes it);
* nothing is ever written to stdout, and a data problem never exits non-zero in
  a way the parent could act on — it is long gone by then. Progress and failures
  go to ``$HERMES_HOME/reqogniloom/capture.log`` (best-effort, one rolled file);
* the worker only ever *queues* a suggestion. Creating artifacts stays behind
  ``/reqogniloom accept``, and a rejected round leaves the queue untouched — so
  "capture failed" is always visible as "no suggestion appeared", never as a
  half-written artifact.
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# Run as a script: its own directory is sys.path[0], which is exactly the plugin
# root these modules live in.
import reqogniloom_state as state
from reqogniloom_client import ReqogniLoomClient, ReqogniLoomError

_LOG_MAX_BYTES = 1_000_000


def _log(message: str) -> None:
    """Append one line to the capture log, rolling it once past the cap.

    Best-effort by design: a failure to log must never be the reason a capture
    breaks, and the log is a diagnostic, not a feature.
    """
    try:
        path = state.hermes_home() / "reqogniloom" / "capture.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.stat().st_size > _LOG_MAX_BYTES:
            path.replace(path.with_suffix(".log.1"))
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {message}\n")
    except OSError:
        pass


def proposal_items(proposal: Any) -> List[Dict[str, Any]]:
    """Normalise whatever ``<session>/propose/`` returned to a list of items.

    The endpoint reports ``{"proposal": null}`` until a chat turn produced a
    parseable one. A proposal is expected to be the item list itself or an
    object wrapping it under ``items``; anything else is "nothing to suggest"
    rather than an error worth surfacing.
    """
    if isinstance(proposal, dict):
        inner = proposal.get("items") or proposal.get("proposals")
        return inner if isinstance(inner, list) else []
    return proposal if isinstance(proposal, list) else []


def capture(text: str, listen: Dict[str, Any]) -> int:
    """One capture round. Returns the number of proposal items queued."""
    client = ReqogniLoomClient()
    workspace_id = listen.get("workspace_id")
    if not workspace_id:
        raise ReqogniLoomError("listen mode has no workspace_id — re-run `/reqogniloom listen on`")

    session_id: Optional[str] = listen.get("session_id")
    if not session_id:
        # A type-less multi-artifact session is the only one that can propose
        # several, differently-typed artifacts — the point of listening.
        session = client.start_interview(None, workspace_id, session_kind="multi")
        session_id = session.get("id") if isinstance(session, dict) else None
        if not session_id:
            raise ReqogniLoomError(f"multi session start returned no id: {session!r}")
        _log(f"opened multi session {session_id} in workspace {workspace_id}")
        state.update_state(
            lambda current: {
                **current,
                "listen": {**(current.get("listen") or {}), "session_id": session_id},
            }
        )

    client.chat(session_id, text)
    items = proposal_items(client.proposal(session_id))
    if not items:
        _log(f"session {session_id}: chat produced no parseable proposal")
        return 0

    signature = hashlib.sha256(
        json.dumps(items, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()[:16]

    queued: List[int] = []

    def mutate(current: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        existing = list(current.get("suggestions") or [])
        if any(str(entry.get("signature")) == signature for entry in existing):
            # The LLM proposed exactly this set again (same text, same session).
            # Re-queueing it would inflate the review list with one duplicate per
            # capture round.
            _log(f"session {session_id}: proposal {signature} already queued")
            return None
        existing.insert(
            0,
            {
                "id": signature,
                "signature": signature,
                "session_id": session_id,
                "source": "listen",
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "items": items,
            },
        )
        queued.append(len(items))
        return {**current, "suggestions": existing[: state.MAX_SUGGESTIONS]}

    state.update_state(mutate)
    return queued[0] if queued else 0


def main(argv: List[str]) -> int:
    if len(argv) < 2:
        _log("invoked without a payload path")
        return 2
    payload_path = Path(argv[1])
    try:
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _log(f"unreadable payload {payload_path}: {exc}")
        return 2
    except Exception as exc:  # noqa: BLE001 — a worker must not crash loudly
        _log(f"unreadable payload {payload_path}: {type(exc).__name__}: {exc}")
        return 2
    try:
        payload_path.unlink()
    except OSError:
        pass

    text = str(payload.get("text") or "").strip()
    if not text:
        return 0

    # Re-read the switch instead of trusting the payload: the operator may have
    # run `/reqogniloom listen off` between the hook firing and this process
    # getting scheduled, and a switch that takes a round to take effect is worse
    # than one that does not exist.
    listen = state.load_state().get("listen") or {}
    if not listen.get("enabled"):
        _log("listen turned off before the worker ran; skipping")
        return 0

    try:
        queued = capture(text, listen)
    except ReqogniLoomError as exc:
        _log(f"capture failed: {exc}")
        return 1
    except Exception as exc:  # noqa: BLE001 — see module docstring
        _log(f"capture failed unexpectedly: {type(exc).__name__}: {exc}")
        return 1
    _log(f"captured {len(text)} chars from {payload.get('platform') or '?'} -> {queued} suggestion item(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
