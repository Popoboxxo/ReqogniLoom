"""reqogniloom plugin — ReqogniLoom in Hermes: interviews, a dashboard tab and an
ambient "listen & anticipate" mode.

Three surfaces over one client (``reqogniloom_client.py``):

* the ``/reqogniloom`` slash command — drive a single interview by hand;
* the dashboard tab (``dashboard/``) — counts and open interviews per workspace;
* the ``pre_llm_call`` hook — the optional *listen* mode: while it is on, the
  user's own messages are captured into a type-less multi-artifact interview and
  whatever the model proposes there is parked as a **suggestion**
  (``/reqogniloom review``). Nothing is created silently: capture → propose →
  ``/reqogniloom accept``.

Artifact reads and writes beyond this flow are deliberately **not**
re-implemented here. The shared client (``reqogniloom_client.py``) speaks
ReqogniLoom's native MCP server (``POST /mcp/``, ``X-API-Key``) for every
operation — ``workspace.list``, the ``interview.*`` tools and the
``requirement.query`` / ``test.query`` counts — so this plugin uses exactly the
same tool surface the rest of the ecosystem does instead of maintaining a
second, partial client that would drift from it. Only ``GET /api/v1/version/``
stays on REST, because it is public and has no MCP tool.

State lives in ``$HERMES_HOME/reqogniloom/state.json`` (see
``reqogniloom_state.py``): the current interview, the listen switch and its
pending suggestions. Every slash-command invocation is a fresh process, so that
file is the only thing that carries over — and the capture worker is a detached
process for the same reason (``_capture.py``).
"""
from __future__ import annotations

import json
import logging
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .reqogniloom_client import ReqogniLoomClient, ReqogniLoomError, resolve_workspace_id
from .reqogniloom_state import load_state as _state_load, save_state as _state_save

logger = logging.getLogger(__name__)

#: Shortest user message worth capturing. A capture round costs one LLM turn on
#: the ReqogniLoom side, so "ok", "danke" and a bare path are not worth one.
MIN_CAPTURE_CHARS = 40

#: Floor between two capture rounds, in seconds. Overridable per install through
#: the ``listen`` block so a chatty session cannot queue a dozen LLM turns.
DEFAULT_MIN_INTERVAL_SECONDS = 45

#: A message starting with one of these is a command, not a statement about the
#: system: slash commands, shell-ish prefixes and mentions are never captured.
_SKIP_PREFIXES = ("/", "!", "$")


def _hermes_home() -> Path:
    import os as _os

    val = (_os.environ.get("HERMES_HOME") or "").strip()
    return Path(val) if val else Path.home() / ".hermes"


def _state_path() -> Path:
    return _hermes_home() / "reqogniloom" / "state.json"


def _load_state() -> Dict[str, Any]:
    """Kept as module-level names (rather than importing them at the call sites)
    because the tests stand in for exactly these two functions."""
    return _state_load()


def _save_state(state: Dict[str, Any]) -> None:
    _state_save(state)


_HELP_TEXT = """\
/reqogniloom — ReqogniLoom requirements interviews from Hermes

Subcommands:
  start <artifact_type> [workspace_id]   Start a new interview (e.g. "Requirement",
                                          "StakeholderNeed" — canonical PascalCase only).
                                          Omit workspace_id to use your first visible workspace.
  status                                 Show the current interview's phase and missing fields.
  answer <field> <value...>              Answer one field of the current interview.
  chat <message...>                      Send a free-form chat turn to the current interview.
  formalize                              Turn the current interview into a real artifact.
  abandon                                Cancel the current interview.
  workspaces                             List workspaces visible to this API key.
  stats [workspace_id]                   Quick counts (requirements, testcases, open interviews).

Listen mode ("hear along", nothing is created without your word):
  listen on [workspace_id]               Capture your messages and have ReqogniLoom
                                          propose artifacts from them.
  listen off                             Stop capturing.
  listen status                          Show whether capturing is on, and where.
  review                                 List the pending local suggestions.
  review pending [workspace_id]          List the server-side proposals awaiting review
                                          (workflow review queue + suggestion inbox).
  accept <index|all>                     Create the CAPTURED local suggestions as proposals.
  dismiss <index|all>                    Drop local suggestions without creating anything.

Server-side suggestions (ADR-019 — decided one at a time, by id, never automatically):
  suggestion list [workspace_id]         List the server-side suggestions of a workspace.
  suggestion accept <id>                 Accept ONE server-side suggestion by id.
  suggestion reject <id> [reason...]     Reject ONE server-side suggestion by id.

  `suggestion accept/reject` decide a server-side ADR-019 suggestion by id;
  `accept <index|all>` only formalizes suggestions captured locally by listen mode.

  help                                   Show this text.
"""

#: Shared usage line for the ``suggestion`` group; also the reply to a missing
#: action or a missing ``<id>`` — so an incomplete command can never decide one.
_SUGGESTION_USAGE = (
    "Usage: /reqogniloom suggestion list [workspace_id] | accept <id> | reject <id> [reason...]"
)


def _fmt_missing_field(field: Any) -> str:
    """Render one ``missing_fields`` entry.

    The server sends dicts (``interview_service._serialise_field`` →
    ``{"name", "type", "choices"}``); a bare string is tolerated for
    backwards compatibility with older servers. Before this, a dict entry
    produced ``TypeError`` in ``", ".join`` (PLUG-01).
    """
    if isinstance(field, dict):
        name = field.get("name")
        if isinstance(name, str) and name:
            return name
        return str(field)
    return str(field)


def _fmt_state(state: Dict[str, Any]) -> str:
    lines = [f"session:   {state.get('id')}", f"phase:     {state.get('phase')}"]
    missing = state.get("missing_fields") or []
    if missing:
        lines.append(f"missing:   {', '.join(_fmt_missing_field(f) for f in missing)}")
    grounding = state.get("grounding")
    if grounding:
        lines.append("grounding: (see /reqogniloom chat for details)")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Listen mode
# ---------------------------------------------------------------------------


def _worth_capturing(text: str) -> bool:
    """Cheap pre-filter, run before any I/O.

    The bar is "does this look like a statement about the system?" — long enough
    to carry a requirement or a risk, and not a command. Everything else is left
    alone: a false positive costs an LLM turn and a bogus suggestion in the
    review queue, which is worse than missing one message.
    """
    if len(text) < MIN_CAPTURE_CHARS:
        return False
    return not text.startswith(_SKIP_PREFIXES)


def _spawn_capture(text: str, platform: str, session_key: str) -> None:
    """Hand one message to the detached capture worker.

    Detached because the hook runs on the turn's critical path: the worker makes
    two to three network calls plus a server-side LLM turn. ``start_new_session``
    keeps it alive past the turn (and past a parent that exits first); the
    payload file is unlinked by the worker, and by us if the spawn itself
    fails.
    """
    payload_dir = _state_path().parent
    payload_dir.mkdir(parents=True, exist_ok=True)
    payload = payload_dir / f"capture-{int(time.time() * 1000)}-{os.getpid()}.json"
    payload.write_text(
        json.dumps({"text": text, "platform": platform, "session_key": session_key}),
        encoding="utf-8",
    )
    worker = Path(__file__).resolve().parent / "_capture.py"
    try:
        subprocess.Popen(
            [sys.executable, str(worker), str(payload)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )
    except OSError as exc:
        logger.warning("could not spawn reqogniloom capture worker: %s", exc)
        try:
            payload.unlink()
        except OSError:
            pass


def _on_pre_llm_call(*, user_message: str = "", platform: str = "", session_id: str = "", **_kwargs: Any) -> None:
    """``pre_llm_call`` observer: queue the user's own message for capture.

    Returns ``None`` on every path: this hook is a side effect, not a context
    provider — returning a string or ``{"context": ...}`` would inject text into
    the user's own prompt, which is the opposite of "listen along".

    Fail-open throughout. An exception here would be caught by the host anyway,
    but a capture problem must never be visible in the conversation.
    """
    try:
        state = _load_state()
        listen = dict(state.get("listen") or {})
        if not listen.get("enabled"):
            return None
        text = (user_message or "").strip()
        if not _worth_capturing(text):
            return None
        now = time.time()
        minimum = float(listen.get("min_interval_seconds") or DEFAULT_MIN_INTERVAL_SECONDS)
        if now - float(listen.get("last_capture_at") or 0.0) < minimum:
            return None
        # Stamp before spawning: two turns in quick succession must not both
        # clear the throttle and queue two identical capture rounds.
        listen["last_capture_at"] = now
        state["listen"] = listen
        _save_state(state)
        _spawn_capture(text, platform or "", session_id or "")
    except Exception as exc:  # noqa: BLE001 — a hook must never break a turn
        logger.debug("reqogniloom listen hook skipped: %s", exc)
    return None


def _fmt_duration(seconds: float) -> str:
    seconds = max(0.0, seconds)
    if seconds < 90:
        return f"{int(seconds)}s"
    return f"{int(seconds // 60)}min"


def _listen_status(listen: Dict[str, Any]) -> str:
    if not listen:
        return "Listen mode: off (never configured). Turn it on with `/reqogniloom listen on [workspace_id]`."
    if not listen.get("enabled"):
        return "Listen mode: off. Turn it on with `/reqogniloom listen on [workspace_id]`."
    last = float(listen.get("last_capture_at") or 0.0)
    ago = "never" if not last else f"{_fmt_duration(time.time() - last)} ago"
    return (
        "Listen mode: on\n"
        f"workspace:        {listen.get('workspace_id')}\n"
        f"interview:        {listen.get('session_id') or '(opens with the first capture)'}\n"
        f"throttle:         at most one capture every {listen.get('min_interval_seconds')}s\n"
        f"last capture:     {ago}\n"
        "Nothing is created without `/reqogniloom accept`."
    )


def _fmt_review(suggestions: Sequence[Dict[str, Any]]) -> str:
    if not suggestions:
        return (
            "No pending suggestions. Turn listen mode on with `/reqogniloom listen on`, "
            "then review again. See server-side proposals with `/reqogniloom review pending`."
        )
    lines = [f"{len(suggestions)} pending suggestion(s) — nothing is created until you accept:"]
    for index, suggestion in enumerate(suggestions):
        items = suggestion.get("items") or []
        lines.append(f"[{index}] {suggestion.get('created_at', '?')} — {len(items)} artifact(s)")
        for item in items:
            fields = item.get("fields") if isinstance(item, dict) else None
            title = ""
            if isinstance(fields, dict):
                title = str(fields.get("title") or fields.get("name") or "")
            kind = item.get("type") if isinstance(item, dict) else "?"
            lines.append(f"      - {kind}: {title or '(no title)'}")
    lines.append("Accept with `/reqogniloom accept <index|all>`, drop with `/reqogniloom dismiss <index|all>`.")
    lines.append("Accepted artifacts are created as proposals; see them with `/reqogniloom review pending`.")
    return "\n".join(lines)


def _select_suggestions(args: Sequence[str], count: int) -> Tuple[Optional[List[int]], Optional[str]]:
    """Translate ``<index|all>`` arguments into indices. Returns ``(indices,
    error)`` — exactly one of the two is set."""
    if not args:
        return None, "Usage: /reqogniloom <accept|dismiss> <index|all> (see /reqogniloom review)"
    if len(args) == 1 and args[0].lower() == "all":
        return list(range(count)), None
    indices: List[int] = []
    for raw in args:
        try:
            index = int(raw)
        except ValueError:
            return None, f"'{raw}' is not a suggestion index; use a number or 'all'."
        if not 0 <= index < count:
            return None, f"Suggestion index {index} is out of range (0–{count - 1})."
        if index not in indices:
            indices.append(index)
    return indices, None


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

    try:
        # Client/state construction lives inside the try so the "never raises"
        # contract below covers it too.
        client = ReqogniLoomClient()
        state = _load_state()

        if sub == "start":
            if not rest:
                return "Usage: /reqogniloom start <artifact_type> [workspace_id]"
            artifact_type = rest[0]
            explicit_ws = rest[1] if len(rest) > 1 else None
            workspace_id = resolve_workspace_id(client, explicit_ws)
            session = client.start_interview(artifact_type, workspace_id)
            _save_state(_with_ambient(state, {"session_id": session["id"], "workspace_id": workspace_id}))
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
                # The server returns {"resulting_artifact_ids": [...], "status"},
                # never an "artifact_id" key; surface the real IDs instead of
                # dumping the raw response dict (PLUG-03/AUD-111).
                ids = result.get("resulting_artifact_ids")
                if isinstance(ids, list) and ids:
                    return f"Formalized. Artifact(s): {', '.join(str(i) for i in ids)}"
                return f"Formalized. No artifact IDs returned: {result}"

            if sub == "abandon":
                client.abandon(session_id)
                _save_state(_with_ambient(state, {}))
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

        if sub == "listen":
            return _handle_listen(client, state, rest)

        if sub == "review":
            if rest and rest[0].lower() == "pending":
                return _handle_review_pending(client, state, rest[1:])
            return _fmt_review(state.get("suggestions") or [])

        if sub == "suggestion":
            return _handle_suggestion(client, state, rest)

        if sub in ("accept", "dismiss"):
            return _handle_review_action(client, state, sub, rest)

    except ReqogniLoomError as exc:
        return f"ReqogniLoom error: {exc}"
    except Exception as exc:  # noqa: BLE001 — _handle_slash promises never to raise
        logger.warning("Unexpected error handling /reqogniloom %s: %s", sub, exc)
        return f"ReqogniLoom plugin error: {exc}"

    return f"Unknown subcommand: {sub}\n\n{_HELP_TEXT}"


def _with_ambient(previous: Dict[str, Any], interview: Dict[str, Any]) -> Dict[str, Any]:
    """Build a new state that replaces the *interview* keys while keeping the
    listen configuration and its suggestion queue.

    ``session_id``/``workspace_id`` used to be written by replacing the whole
    file, which silently switched listen mode off whenever a hand-driven
    interview started or was abandoned.
    """
    merged = dict(interview)
    for key in ("listen", "suggestions"):
        if previous.get(key):
            merged[key] = previous[key]
    return merged


def _handle_listen(client: ReqogniLoomClient, state: Dict[str, Any], rest: Sequence[str]) -> str:
    action = (rest[0].lower() if rest else "status")
    listen = dict(state.get("listen") or {})

    if action == "status":
        return _listen_status(listen)

    if action == "off":
        if not listen:
            return "Listen mode was never on."
        listen["enabled"] = False
        state["listen"] = listen
        _save_state(state)
        return "Listen mode: off — your messages are no longer captured."

    if action == "on":
        explicit = rest[1] if len(rest) > 1 else listen.get("workspace_id")
        workspace_id = resolve_workspace_id(client, explicit)
        listen.update({"enabled": True, "workspace_id": workspace_id})
        listen.setdefault("min_interval_seconds", DEFAULT_MIN_INTERVAL_SECONDS)
        state["listen"] = listen
        _save_state(state)
        return (
            f"Listen mode: on — workspace {workspace_id}.\n"
            f"Capturing messages of at least {MIN_CAPTURE_CHARS} characters, at most one every "
            f"{listen['min_interval_seconds']}s.\n"
            "ReqogniLoom's proposals land in `/reqogniloom review`; nothing is created until "
            "`/reqogniloom accept`."
        )

    return "Usage: /reqogniloom listen on [workspace_id] | off | status"


def _handle_review_action(client: ReqogniLoomClient, state: Dict[str, Any], sub: str, rest: Sequence[str]) -> str:
    suggestions = list(state.get("suggestions") or [])
    if not suggestions:
        return "Nothing to review: no pending suggestions."

    targets, error = _select_suggestions(rest, len(suggestions))
    if error:
        return error
    assert targets is not None  # _select_suggestions sets exactly one of the two

    if sub == "dismiss":
        remaining = [entry for index, entry in enumerate(suggestions) if index not in targets]
        state["suggestions"] = remaining
        _save_state(state)
        return (
            f"Dismissed {len(targets)} suggestion(s); {len(remaining)} still pending. "
            "Nothing was created on the server."
        )

    created: List[str] = []
    failures: List[str] = []
    remaining = list(suggestions)
    # Highest index first: popping reindexes the list, and the human's indices
    # refer to the list they just read in `/reqogniloom review`.
    for index in sorted(targets, reverse=True):
        entry = suggestions[index]
        try:
            result = client.formalize(entry.get("session_id"), confirmed_proposal=entry.get("items") or [])
        except ReqogniLoomError as exc:
            failures.append(f"[{index}] {exc}")
            continue
        ids = result.get("resulting_artifact_ids") if isinstance(result, dict) else None
        created.extend(str(item) for item in (ids or []))
        remaining.pop(index)

    state["suggestions"] = remaining
    _save_state(state)

    lines: List[str] = []
    if created:
        lines.append(f"Created {len(created)} artifact(s): {', '.join(created)}")
        # The accept path is interview.formalize under the plugin's API-key
        # (agent) context: workflow.services.initial_state_for seeds the new
        # artifacts as `proposed` wherever the workspace graph knows that state,
        # so they await a human decision in the server-side review queue. They
        # are never adopted as final requirements here.
        lines.append(
            "Created as proposals / awaiting review (agent context) — nothing is "
            "adopted as final. Confirm or discard them in ReqogniLoom's review "
            "surface; list them with `/reqogniloom review pending`."
        )
    if failures:
        lines.append("Failed, still pending:")
        lines.extend(f"      {line}" for line in failures)
    if not created and not failures:
        lines.append("Nothing was created — the server returned no artifact IDs.")
    if remaining:
        lines.append(f"{len(remaining)} suggestion(s) still pending.")
    return "\n".join(lines)


def _handle_review_pending(
    client: ReqogniLoomClient, state: Dict[str, Any], rest: Sequence[str]
) -> str:
    """List the *server-side* proposals awaiting a human, not the local queue.

    Two read-only surfaces, each degrading independently so one failing call
    cannot sink the listing (the slash command's contract is "never raise; always
    a readable string"):

    * ``review.list_pending`` — the workflow review queue (items in the
      ``proposed`` state, e.g. the artifacts ``/reqogniloom accept`` created,
      plus approval-gate items);
    * ``suggestion.list`` — the ADR-019 durable suggestion inbox (generic
      proposals such as ``trace_link``).
    """
    listen = state.get("listen") or {}
    explicit = rest[0] if rest else (listen.get("workspace_id") or state.get("workspace_id"))
    workspace_id = resolve_workspace_id(client, explicit)

    lines: List[str] = [f"Pending review in workspace {workspace_id}:"]

    try:
        reviews = client.list_pending_reviews(workspace_id)
    except ReqogniLoomError as exc:
        lines.append(f"  workflow queue:  unavailable ({exc})")
    else:
        if reviews:
            lines.append(f"  workflow queue ({len(reviews)}):")
            for item in reviews:
                lines.append(
                    f"    - {item.get('item_type', '?')} "
                    f"{item.get('item_id', '?')} [{item.get('current_state', '?')}]"
                )
        else:
            lines.append("  workflow queue:  nothing awaiting review.")

    try:
        suggestions = client.list_suggestions(workspace_id)
    except ReqogniLoomError as exc:
        lines.append(f"  suggestion inbox: unavailable ({exc})")
    else:
        if suggestions:
            lines.append(f"  suggestion inbox ({len(suggestions)}):")
            for suggestion in suggestions:
                lines.append(
                    f"    - {suggestion.get('kind', '?')} "
                    f"{suggestion.get('id', '?')} [{suggestion.get('status', '?')}]"
                )
        else:
            lines.append("  suggestion inbox: empty.")

    lines.append("Nothing is adopted automatically — every item waits for a human confirm.")
    return "\n".join(lines)


def _fmt_suggestion_entry(suggestion: Dict[str, Any]) -> str:
    """Render one server-side suggestion as a single line.

    ``id`` / ``kind`` / ``status`` are always shown; the server-set provenance
    (``producer`` or ``proposed_by``) is appended only when present, so the line
    stays the same shape for a payload that omits it.
    """
    parts = [
        str(suggestion.get("id", "?")),
        str(suggestion.get("kind", "?")),
        f"[{suggestion.get('status', '?')}]",
    ]
    producer = suggestion.get("producer") or suggestion.get("proposed_by")
    if producer:
        parts.append(f"by {producer}")
    return "  ".join(parts)


def _handle_suggestion(
    client: ReqogniLoomClient, state: Dict[str, Any], rest: Sequence[str]
) -> str:
    """The ADR-019 ``suggestion`` group: list / accept / reject, by explicit id.

    ``accept`` and ``reject`` decide exactly the one *server-side* suggestion
    named on the command line — there is no default and no "all", so nothing is
    ever auto-accepted. A missing ``<id>`` returns the usage string without
    calling the tool. A ``PERMISSION_DENIED`` (e.g. an agent trying to accept
    its own proposal) is a :class:`_PermissionError`, a
    :class:`ReqogniLoomError`; it propagates to the caller's ``except
    ReqogniLoomError`` and is rendered as a readable error, never raised.
    """
    action = rest[0].lower() if rest else ""
    args = rest[1:]

    if action == "list":
        listen = state.get("listen") or {}
        explicit = args[0] if args else (listen.get("workspace_id") or state.get("workspace_id"))
        workspace_id = resolve_workspace_id(client, explicit)
        suggestions = client.list_suggestions(workspace_id)
        if not suggestions:
            return f"No open suggestions in workspace {workspace_id}."
        lines = [f"Open suggestions in workspace {workspace_id}:"]
        lines.extend(f"  {_fmt_suggestion_entry(suggestion)}" for suggestion in suggestions)
        lines.append(
            "Decide one explicitly with `/reqogniloom suggestion accept <id>` or "
            "`/reqogniloom suggestion reject <id> [reason...]`."
        )
        return "\n".join(lines)

    if action == "accept":
        if not args:
            return _SUGGESTION_USAGE
        result = client.accept_suggestion(args[0])
    elif action == "reject":
        if not args:
            return _SUGGESTION_USAGE
        result = client.reject_suggestion(args[0], " ".join(args[1:]))
    else:
        return _SUGGESTION_USAGE

    status = result.get("status", "?") if isinstance(result, dict) else "?"
    kind = result.get("kind") if isinstance(result, dict) else None
    verb = "accepted" if action == "accept" else "rejected"
    detail = f"{kind}, " if kind else ""
    return f"Suggestion {args[0]} {verb} ({detail}status {status})."


def register(ctx: Any) -> None:
    ctx.register_command(
        "reqogniloom",
        handler=_handle_slash,
        description="Start and drive a ReqogniLoom requirements interview.",
    )
    # The hook is registered defensively: the slash command is the plugin's core
    # and must still load on a host (or test double) whose context has no
    # register_hook.
    register_hook = getattr(ctx, "register_hook", None)
    if callable(register_hook):
        register_hook("pre_llm_call", _on_pre_llm_call)
