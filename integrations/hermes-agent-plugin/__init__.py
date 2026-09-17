"""reqogniloom plugin — drive a ReqogniLoom requirements interview from Hermes.

POC scope (see docs/superpowers/plans or PR description for the full
picture): a single ``/reqogniloom`` slash command wrapping the
``interview.*`` REST surface (``application/interview_service.py`` via
``rest_api/interview_views.py``), plus a minimal read-only dashboard tab
(``dashboard/``) showing a few counts.

Mirrors the shape of the other plugins in this Hermes install
(``plugins/disk-cleanup``): flat package, ``plugin.yaml`` manifest,
``register(ctx)`` wiring commands/hooks. No hooks needed here — this plugin
is purely command-driven.

State: the "current interview session" is remembered across invocations of
the slash command (each invocation is a fresh process call, not a running
session) in a small JSON file under ``$HERMES_HOME/reqogniloom/state.json``.
"""
from __future__ import annotations

import json
import logging
import shlex
from pathlib import Path
from typing import Any, Dict, Optional

from .reqogniloom_client import ReqogniLoomClient, ReqogniLoomError, resolve_workspace_id

logger = logging.getLogger(__name__)


def _hermes_home() -> Path:
    import os

    val = (os.environ.get("HERMES_HOME") or "").strip()
    return Path(val) if val else Path.home() / ".hermes"


def _state_path() -> Path:
    return _hermes_home() / "reqogniloom" / "state.json"


def _load_state() -> Dict[str, Any]:
    path = _state_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_state(state: Dict[str, Any]) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state), encoding="utf-8")


_HELP_TEXT = """\
/reqogniloom — ReqogniLoom requirements interviews from Hermes

Subcommands:
  start <artifact_type> [workspace_id]   Start a new interview (e.g. "requirement", "need").
                                          Omit workspace_id to use your first visible workspace.
  status                                 Show the current interview's phase and missing fields.
  answer <field> <value...>              Answer one field of the current interview.
  chat <message...>                      Send a free-form chat turn to the current interview.
  formalize                              Turn the current interview into a real artifact.
  abandon                                Cancel the current interview.
  workspaces                             List workspaces visible to this API key.
  stats [workspace_id]                   Quick counts (requirements, testcases, open interviews).
  help                                   Show this text.
"""


def _fmt_state(state: Dict[str, Any]) -> str:
    lines = [f"session:   {state.get('id')}", f"phase:     {state.get('phase')}"]
    missing = state.get("missing_fields") or []
    if missing:
        lines.append(f"missing:   {', '.join(missing)}")
    grounding = state.get("grounding")
    if grounding:
        lines.append("grounding: (see /reqogniloom chat for details)")
    return "\n".join(lines)


def _handle_slash(raw_args: str) -> Optional[str]:
    """Entry point registered via ``ctx.register_command``. Never raises —
    every error path returns a human-readable string instead."""
    try:
        args = shlex.split(raw_args or "")
    except ValueError as exc:
        return f"Could not parse arguments: {exc}"

    if not args or args[0] in ("help", "-h", "--help"):
        return _HELP_TEXT

    sub, rest = args[0], args[1:]
    client = ReqogniLoomClient()
    state = _load_state()

    try:
        if sub == "start":
            if not rest:
                return "Usage: /reqogniloom start <artifact_type> [workspace_id]"
            artifact_type = rest[0]
            explicit_ws = rest[1] if len(rest) > 1 else None
            workspace_id = resolve_workspace_id(client, explicit_ws)
            session = client.start_interview(artifact_type, workspace_id)
            _save_state({"session_id": session["id"], "workspace_id": workspace_id})
            return f"Started interview {session['id']} ({artifact_type}) in workspace {workspace_id}.\n\n" + _fmt_state(
                session
            )

        if sub in ("status", "answer", "chat", "formalize", "abandon"):
            session_id = state.get("session_id")
            if not session_id:
                return "No active interview. Run `/reqogniloom start <artifact_type>` first."

            if sub == "status":
                return _fmt_state(client.get_state(session_id))

            if sub == "answer":
                if len(rest) < 2:
                    return "Usage: /reqogniloom answer <field> <value...>"
                field, value = rest[0], " ".join(rest[1:])
                result = client.answer(session_id, field, value)
                return _fmt_state(result)

            if sub == "chat":
                if not rest:
                    return "Usage: /reqogniloom chat <message...>"
                result = client.chat(session_id, " ".join(rest))
                reply = result.get("reply") or result.get("message") or "(no reply)"
                return f"{reply}\n\n" + _fmt_state(result.get("state", {}))

            if sub == "formalize":
                result = client.formalize(session_id)
                return f"Formalized. Artifact: {result.get('artifact_id', result)}"

            if sub == "abandon":
                client.abandon(session_id)
                _save_state({})
                return f"Abandoned interview {session_id}."

        if sub == "workspaces":
            workspaces = client.list_workspaces()
            if not workspaces:
                return "No workspaces visible to this API key."
            return "\n".join(f"{w['id']}  {w.get('name', '')}" for w in workspaces)

        if sub == "stats":
            explicit_ws = rest[0] if rest else state.get("workspace_id")
            workspace_id = resolve_workspace_id(client, explicit_ws)
            stats = client.stats(workspace_id)
            return (
                f"workspace:       {stats['workspace_id']}\n"
                f"requirements:    {stats['requirements']}\n"
                f"testcases:       {stats['testcases']}\n"
                f"open interviews: {stats['open_interviews']}"
            )

    except ReqogniLoomError as exc:
        return f"ReqogniLoom error: {exc}"

    return f"Unknown subcommand: {sub}\n\n{_HELP_TEXT}"


def register(ctx: Any) -> None:
    ctx.register_command(
        "reqogniloom",
        handler=_handle_slash,
        description="Start and drive a ReqogniLoom requirements interview.",
    )
