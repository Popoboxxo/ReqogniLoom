"""Detached listen-mode worker: deliver the write-ahead queue to ReqogniLoom.

Spawned by the ``pre_llm_call`` hook (see ``__init__.py``) as its own process,
deliberately. The hook sits on the turn's critical path; one capture delivery is
a network call to ReqogniLoom *plus* an LLM turn on the server side, so the hook
only writes the message to ``~/.reqogniloom/listen/capture-queue.jsonl`` and
this worker does the sending.

Contract (``docs/clients/listen-mode-contract.md``):

* ``--drain`` takes the queue lock, merges lock-less segments, delivers at most
  five entries and writes ``listen-status.json``;
* ``--enqueue <payload.json>`` appends one entry (used by the hook's fallback
  path and by the conformance suite); the payload is
  ``{"text", "workspace_id", "client", "source_session", "message_id"}``;
* nothing is ever written to stdout and a data problem never surfaces as a
  non-zero exit the parent could act on — progress and failures go to
  ``capture.log`` without message text;
* the worker only *queues suggestions* on the server. Creating artifacts stays
  behind a human decision in the suggestion inbox.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Run as a script: its own directory is sys.path[0], which is exactly the plugin
# root these modules live in.
import reqogniloom_listen as listen
from reqogniloom_client import ReqogniLoomClient


def _client() -> ReqogniLoomClient:
    """Build the client from the listen-mode config.

    The relay contract names ``REQOGNILOOM_MCP_URL`` (base URL) and
    ``REQOGNILOOM_API_KEY``; without passing them explicitly the client would
    fall back to its own default base URL and the capture POST would 404. Keep
    ``REQOGNILOOM_BASE_URL`` as the legacy alias.
    """
    import os

    base = (
        os.environ.get("REQOGNILOOM_MCP_URL")
        or os.environ.get("REQOGNILOOM_BASE_URL")
        or ""
    ).strip()
    key = (os.environ.get("REQOGNILOOM_API_KEY") or "").strip()
    kwargs: Dict[str, Any] = {}
    if base:
        kwargs["base_url"] = base
    if key:
        kwargs["api_key"] = key
    return ReqogniLoomClient(**kwargs)


def enqueue_payload(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    text = listen.normalize_text(payload.get("text"))
    workspace_id = str(payload.get("workspace_id") or "").strip()
    if not workspace_id:
        switch = listen.load_switch()
        workspace_id = str(switch.get("workspace_id") or "").strip()
    if not workspace_id:
        listen.log("capture skipped: no workspace_id")
        return None
    return listen.enqueue(
        workspace_id=workspace_id,
        text=text,
        client=str(payload.get("client") or "hermes"),
        source_session=str(payload.get("source_session") or ""),
        message_id=str(payload.get("message_id") or ""),
    )


def main(argv: List[str]) -> int:
    if "--drain" in argv:
        try:
            listen.drain(_client())
        except Exception as exc:  # noqa: BLE001 — a worker must not crash loudly
            listen.log(f"drain failed unexpectedly: {type(exc).__name__}")
            return 1
        return 0

    if "--off" in argv:
        switch = listen.load_switch()
        listen.save_switch(enabled=False, workspace_id=switch.get("workspace_id"))
        removed = listen.clear_pending()
        print("Listen mode: OFF (local).")
        deleted = removed["queued"] + removed["incoming"]
        if deleted:
            print(f"{deleted} unsent message(s) were deleted: nothing that was not sent is kept.")
        return 0

    if "--on" in argv:
        index = argv.index("--on")
        if len(argv) <= index + 1:
            listen.log("--on without a workspace id")
            return 2
        listen.save_switch(enabled=True, workspace_id=argv[index + 1])
        print("Listen mode: ON (local).")
        return 0

    if "--enqueue" in argv:
        index = argv.index("--enqueue")
        if len(argv) <= index + 1:
            listen.log("--enqueue without a payload path")
            return 2
        path = Path(argv[index + 1])
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            listen.log(f"unreadable payload {path.name}: {type(exc).__name__}")
            return 2
        try:
            path.unlink()
        except OSError:
            pass
        if not isinstance(payload, dict):
            return 2
        enqueue_payload(payload)
        return 0

    # Legacy invocation (``_capture.py <payload.json>``): enqueue only. The
    # detached ``--drain`` run is what delivers, so a killed turn can never lose
    # the message or leave a half-finished request behind.
    if len(argv) >= 2 and not argv[1].startswith("-"):
        path = Path(argv[1])
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            listen.log(f"unreadable payload {path.name}: {type(exc).__name__}")
            return 2
        try:
            path.unlink()
        except OSError:
            pass
        if isinstance(payload, dict):
            enqueue_payload(payload)
        return 0

    listen.log("invoked without a mode")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
