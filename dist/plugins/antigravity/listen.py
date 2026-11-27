#!/usr/bin/env python3
"""ReqogniLoom listen-mode relay for the Antigravity `PreInvocation` hook.

Stage B of the listen mode: Antigravity has **no** submit event. `PreInvocation`
fires before every model call and carries `lastUserInput`, so the same user
message reaches this script on every turn of a conversation. The relay therefore
deduplicates on ``(session_id, sha256(text))`` before it queues anything.

The relay implements the shared contract natively
(``docs/clients/listen-mode-contract.md``): state in ``~/.reqogniloom/listen``
(override ``REQNILOOM_LISTEN_DIR``), a write-ahead ``capture-queue.jsonl``,
``listen-status.json`` with the same keys, the same 40/300/slash filter, a 60 s
delivery timeout, default off and fail-open. Values are identical to the
Claude Code, Hermes and OpenCode relays — only the language differs.

Usage:
  python3 listen.py                    PreInvocation hook: payload JSON on stdin
  python3 listen.py --drain            deliver the queue
  python3 listen.py enqueue            enqueue {"text","sessionId"} on stdin
  python3 listen.py on <workspace_id>  enable (workspace must be explicit)
  python3 listen.py off                disable and delete unsent messages
  python3 listen.py status             report switch, queue, counters, last error
"""
from __future__ import annotations

import calendar
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

CLIENT_NAME = "antigravity"
MIN_TEXT_LENGTH = 40
MAX_LINES = 300
REQUEST_TIMEOUT_SECONDS = 60.0
MAX_FLUSH_PER_RUN = 5
MAX_ATTEMPTS = 5
MAX_QUEUE_ENTRIES = 100
MAX_ENTRY_AGE_SECONDS = 7 * 24 * 60 * 60
LOCK_STALE_SECONDS = 5 * 60
MAX_FIELD_LENGTH = 255
MAX_IDEMPOTENCY_LENGTH = 128
MAX_LOG_BYTES = 1_000_000
MAX_SEEN_KEYS = 500

LISTEN_FILE = "listen.json"
QUEUE_FILE = "capture-queue.jsonl"
STATUS_FILE = "listen-status.json"
INCOMING_DIR = "capture-incoming"
LOCK_DIR = "capture-queue.lock"
LOG_FILE = "capture.log"
SEEN_FILE = "capture-seen.json"


# -- paths and file helpers -------------------------------------------------


def listen_dir() -> Path:
    configured = (os.environ.get("REQNILOOM_LISTEN_DIR") or "").strip()
    if configured:
        return Path(configured)
    return Path.home() / ".reqogniloom" / "listen"


def ensure_dir() -> Path:
    directory = listen_dir()
    directory.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(directory, 0o700)
    except OSError:
        pass
    return directory


def read_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback


def write_json_atomic(path: Path, value: Any) -> None:
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(f"{json.dumps(value, indent=2, sort_keys=True)}\n", encoding="utf-8")
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, path)


def log(message: str) -> None:
    try:
        path = ensure_dir() / LOG_FILE
        if path.exists() and path.stat().st_size > MAX_LOG_BYTES:
            path.replace(path.with_name(f"{LOG_FILE}.1"))
        stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"{stamp} {message}\n")
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    except OSError:
        pass


# -- switch -----------------------------------------------------------------


def load_switch() -> Dict[str, Any]:
    data = read_json(listen_dir() / LISTEN_FILE, {})
    return data if isinstance(data, dict) else {}


def is_enabled(switch: Dict[str, Any]) -> bool:
    return switch.get("enabled") is True


def save_switch(*, enabled: bool, workspace_id: Optional[str]) -> Dict[str, Any]:
    ensure_dir()
    updated = {**load_switch(), "enabled": bool(enabled), "client": CLIENT_NAME}
    if workspace_id:
        updated["workspace_id"] = str(workspace_id)
    write_json_atomic(listen_dir() / LISTEN_FILE, updated)
    return updated


# -- filter, idempotency, entry ---------------------------------------------


def normalize_text(value: Any) -> str:
    return str(value or "").replace("\r\n", "\n").strip()


def passes_filter(text: str) -> bool:
    if len(text) < MIN_TEXT_LENGTH:
        return False
    if text[:1] in ("/", "!", "$"):
        return False
    if text.count("\n") + 1 > MAX_LINES:
        return False
    return True


def idempotency_key(workspace_id: str, text: str) -> str:
    digest = hashlib.sha256(f"{workspace_id}\n{text}".encode("utf-8")).hexdigest()
    return digest[:MAX_IDEMPOTENCY_LENGTH]


def build_entry(workspace_id: str, text: str, session_id: str) -> Optional[Dict[str, Any]]:
    normalized = normalize_text(text)
    if not passes_filter(normalized):
        return None
    return {
        "workspace_id": str(workspace_id),
        "text": normalized,
        "client": CLIENT_NAME,
        "source_session": session_id[:MAX_FIELD_LENGTH],
        "message_id": seen_key(session_id, normalized)[:MAX_FIELD_LENGTH],
        "idempotency_key": idempotency_key(str(workspace_id), normalized),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "attempts": 0,
        "last_attempt_at": None,
    }


# -- queue ------------------------------------------------------------------


def queue_path() -> Path:
    return listen_dir() / QUEUE_FILE


def read_queue() -> List[Dict[str, Any]]:
    path = queue_path()
    if not path.exists():
        return []
    entries: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(entry, dict) and entry.get("text"):
            entries.append(entry)
    return entries


def rewrite_queue(entries: List[Dict[str, Any]]) -> None:
    path = queue_path()
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    body = "\n".join(json.dumps(entry) for entry in entries)
    tmp.write_text(f"{body}\n" if body else "", encoding="utf-8")
    os.replace(tmp, path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def append_queue(entry: Dict[str, Any]) -> None:
    path = queue_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{json.dumps(entry)}\n")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


class _Lock:
    """mkdir-based lock (portable, stale after LOCK_STALE_SECONDS)."""

    def __init__(self) -> None:
        self.acquired = False
        self.path = ensure_dir() / LOCK_DIR

    def __enter__(self) -> bool:
        try:
            self.path.mkdir()
            self.acquired = True
        except FileExistsError:
            try:
                age = time.time() - self.path.stat().st_mtime
            except OSError:
                age = 0.0
            if age > LOCK_STALE_SECONDS:
                stale = self.path.with_name(f"{LOCK_DIR}.stale-{os.getpid()}")
                try:
                    os.replace(self.path, stale)
                    stale.rmdir()
                    self.path.mkdir()
                    self.acquired = True
                except OSError:
                    self.acquired = False
        except OSError:
            self.acquired = False
        return self.acquired

    def __exit__(self, *exc_info: Any) -> None:
        if self.acquired:
            try:
                self.path.rmdir()
            except OSError:
                pass


def merge_incoming() -> int:
    pending = listen_dir() / INCOMING_DIR
    if not pending.exists():
        return 0
    entries = []
    for path in sorted(pending.glob("*.json")):
        entry = read_json(path, None)
        if isinstance(entry, dict) and entry.get("text"):
            entries.append(entry)
        try:
            path.unlink()
        except OSError:
            pass
    if not entries:
        return 0
    merged = [*read_queue(), *entries]
    rewrite_queue(merged[-MAX_QUEUE_ENTRIES:])
    return len(entries)


def enqueue(workspace_id: str, text: str, session_id: str = "") -> Optional[Dict[str, Any]]:
    entry = build_entry(workspace_id, text, session_id)
    if entry is None:
        return None
    directory = ensure_dir()
    try:
        with _Lock() as locked:
            if locked:
                append_queue(entry)
                entries = read_queue()
                if len(entries) > MAX_QUEUE_ENTRIES:
                    rewrite_queue(entries[-MAX_QUEUE_ENTRIES:])
            else:
                pending = directory / INCOMING_DIR
                pending.mkdir(parents=True, exist_ok=True)
                name = f"{int(time.time() * 1000)}-{os.getpid()}-{os.urandom(4).hex()}.json"
                write_json_atomic(pending / name, entry)
                log("capture queued: queue lock held")
    except OSError as exc:
        log(f"capture enqueue failed: {type(exc).__name__}")
        return None
    return entry


# -- status -----------------------------------------------------------------


def initial_status() -> Dict[str, Any]:
    return {
        "last_success_at": None,
        "last_error": None,
        "last_error_at": None,
        "captured": 0,
        "failed": 0,
        "queued": 0,
    }


def read_status() -> Dict[str, Any]:
    data = read_json(listen_dir() / STATUS_FILE, {})
    return {**initial_status(), **(data if isinstance(data, dict) else {})}


def write_status(state: Dict[str, Any]) -> None:
    ensure_dir()
    write_json_atomic(listen_dir() / STATUS_FILE, state)


def record_success(state: Dict[str, Any]) -> None:
    state["captured"] = int(state.get("captured") or 0) + 1
    state["last_success_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    state["last_error"] = None
    state["last_error_at"] = None


def record_failure(state: Dict[str, Any], detail: str) -> None:
    state["failed"] = int(state.get("failed") or 0) + 1
    state["last_error"] = str(detail or "error")[:120]
    state["last_error_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# -- delivery ---------------------------------------------------------------


def capture_config() -> Tuple[str, str]:
    base = (
        (os.environ.get("REQOGNILOOM_MCP_URL") or "").strip()
        or (os.environ.get("REQOGNILOOM_BASE_URL") or "").strip()
    ).rstrip("/")
    return base, (os.environ.get("REQOGNILOOM_API_KEY") or "").strip()


def deliver(base: str, api_key: str, entry: Dict[str, Any]) -> Tuple[bool, str]:
    body: Dict[str, Any] = {
        "workspace_id": entry["workspace_id"],
        "text": entry["text"],
        "client": entry.get("client") or CLIENT_NAME,
        "idempotency_key": entry.get("idempotency_key")
        or idempotency_key(entry["workspace_id"], entry["text"]),
    }
    if entry.get("source_session"):
        body["source_session"] = entry["source_session"]
    if entry.get("message_id"):
        body["message_id"] = entry["message_id"]
    request = urllib.request.Request(
        f"{base}/api/v1/suggestions/capture/",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-API-Key": api_key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(  # noqa: S310 — fixed, configured base URL
            request, timeout=REQUEST_TIMEOUT_SECONDS
        ) as response:
            response.read()
        return True, "delivered"
    except urllib.error.HTTPError as exc:
        if exc.code in (400, 409):
            # Permanent: retrying can never succeed (or already landed).
            return True, f"HTTP {exc.code}"
        return False, f"HTTP {exc.code}"
    except TimeoutError:
        return False, "timeout"
    except (urllib.error.URLError, OSError):
        return False, "network_error"


def drain() -> int:
    switch = load_switch()
    if not is_enabled(switch):
        return 0
    workspace_id = str(switch.get("workspace_id") or "").strip()
    directory = ensure_dir()
    state = read_status()
    base, api_key = capture_config()
    missing = []
    if not workspace_id:
        missing.append("workspace_id")
    if not base:
        missing.append("mcp_url")
    if not api_key:
        missing.append("api_key")
    if missing:
        record_failure(state, f"missing_config:{','.join(missing)}")
        state["queued"] = len(read_queue())
        write_status(state)
        log(f"capture skipped: missing config {','.join(missing)}")
        return 0

    with _Lock() as locked:
        if not locked:
            log("drain skipped: queue lock held")
            return 0
        merged = merge_incoming()
        if merged:
            log(f"merged {merged} queued capture(s)")
        now = time.time()
        entries = read_queue()
        candidates: List[Dict[str, Any]] = []
        keep: List[Dict[str, Any]] = []
        for entry in entries:
            created = _parse_created(entry.get("created_at"))
            if created is not None and now - created > MAX_ENTRY_AGE_SECONDS:
                continue
            if int(entry.get("attempts") or 0) >= MAX_ATTEMPTS:
                continue
            if entry.get("workspace_id") != workspace_id:
                keep.append(entry)
                continue
            if len(candidates) < MAX_FLUSH_PER_RUN:
                candidates.append(entry)
            else:
                keep.append(entry)
        selected = {id(entry) for entry in candidates}
        sent = 0
        for entry in entries:
            if id(entry) not in selected:
                continue
            terminal, detail = deliver(base, api_key, entry)
            if terminal:
                record_success(state)
                sent += 1
            else:
                record_failure(state, detail)
                log(f"capture failed: {detail}")
                keep.append(
                    {
                        **entry,
                        "attempts": int(entry.get("attempts") or 0) + 1,
                        "last_attempt_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    }
                )
        rewrite_queue(keep)
        state["queued"] = len(keep)
        write_status(state)
        if sent:
            log(f"flushed {sent} queued capture(s)")
        return sent


def _parse_created(value: Any) -> Optional[float]:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return float(calendar.timegm(time.strptime(raw[:19], "%Y-%m-%dT%H:%M:%S")))
    except (ValueError, OverflowError):
        return None


# -- dedupe (stage B) and cleanup -------------------------------------------


def seen_key(session_id: str, text: str) -> str:
    return hashlib.sha256(f"{session_id}\n{text}".encode("utf-8")).hexdigest()


def claim_seen(session_id: str, text: str) -> bool:
    """True when this ``(session, text)`` pair is new; False on a repeat."""
    directory = ensure_dir()
    path = directory / SEEN_FILE
    data = read_json(path, {})
    keys = list(data.get("keys") or []) if isinstance(data, dict) else []
    key = seen_key(session_id, text)
    if key in keys:
        return False
    keys.append(key)
    write_json_atomic(path, {"keys": keys[-MAX_SEEN_KEYS:]})
    return True


def clear_pending() -> Dict[str, int]:
    directory = ensure_dir()
    removed = {"queued": len(read_queue()), "incoming": 0}
    pending = directory / INCOMING_DIR
    if pending.exists():
        removed["incoming"] = len(list(pending.glob("*.json")))
        for path in pending.glob("*.json"):
            try:
                path.unlink()
            except OSError:
                pass
        try:
            pending.rmdir()
        except OSError:
            pass
    try:
        (directory / QUEUE_FILE).unlink()
    except OSError:
        pass
    status = read_status()
    status["queued"] = 0
    write_status(status)
    return removed


# -- hook and CLI -----------------------------------------------------------


def handle_event(payload: Dict[str, Any], *, spawn: bool = True) -> Optional[Dict[str, Any]]:
    """Handle one ``PreInvocation`` payload. Never raises, never prints."""
    try:
        switch = load_switch()
        if not is_enabled(switch):
            return None
        text = normalize_text(
            payload.get("lastUserInput")
            or payload.get("last_user_input")
            or payload.get("prompt")
            or ""
        )
        if not passes_filter(text):
            return None
        workspace_id = str(switch.get("workspace_id") or "").strip()
        if not workspace_id:
            log("capture skipped: no workspace_id configured")
            return None
        session_id = str(
            payload.get("session_id")
            or payload.get("sessionId")
            or payload.get("conversation_id")
            or ""
        )
        # PreInvocation fires before every model call: without this check the
        # same message would be queued on every turn.
        if not claim_seen(session_id, text):
            return None
        entry = enqueue(workspace_id, text, session_id)
        if spawn:
            _spawn_drain()
        return entry
    except Exception as exc:  # noqa: BLE001 — a hook must never break a turn
        log(f"capture hook error: {type(exc).__name__}")
        return None


def _spawn_drain() -> None:
    try:
        subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "--drain"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )
    except OSError as exc:
        log(f"drain spawn failed: {type(exc).__name__}")


def _server_switch() -> str:
    switch = load_switch()
    workspace_id = str(switch.get("workspace_id") or "").strip()
    base, api_key = capture_config()
    if not base or not api_key or not workspace_id:
        return "unknown (not configured)"
    url = (
        f"{base}/api/v1/workspaces/{urllib.parse.quote(workspace_id)}"
        "/preference-values/effective/?keys=capture.enabled"
    )
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {api_key}"})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310
            payload = json.loads(response.read().decode("utf-8") or "{}")
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return "unknown (unreachable)"
    entry = (payload.get("values") or {}).get("capture.enabled") or {}
    return "ON" if entry.get("value") is True else "OFF"


def status() -> str:
    switch = load_switch()
    state = read_status()
    server = _server_switch()
    lines = [
        f"Local switch:  {'ON' if is_enabled(switch) else 'OFF'}",
        f"Workspace:     {switch.get('workspace_id') or '(not configured)'}",
        f"State:         {listen_dir()}",
        f"Server switch: {server}",
    ]
    if is_enabled(switch) and server != "ON":
        lines.append("Capture is inactive: both switches must be ON.")
    lines.extend(
        [
            f"Queue:         {state.get('queued', 0)} message(s)",
            f"Captured:      {state.get('captured', 0)}",
            f"Failed:        {state.get('failed', 0)}",
            f"Last success:  {state.get('last_success_at') or '—'}",
            "Last error:    "
            + (state.get("last_error") or "—")
            + (f" ({state['last_error_at']})" if state.get("last_error_at") else ""),
        ]
    )
    return "\n".join(lines)


def main(argv: List[str]) -> int:
    action = (argv[1] if len(argv) > 1 else "").lower()

    if action == "--drain":
        try:
            drain()
        except Exception as exc:  # noqa: BLE001
            log(f"drain failed unexpectedly: {type(exc).__name__}")
            return 1
        return 0

    if action == "enqueue":
        try:
            payload = json.loads(sys.stdin.read() or "{}")
        except (json.JSONDecodeError, ValueError):
            log("unreadable enqueue payload")
            return 2
        if isinstance(payload, dict):
            handle_event(
                {
                    "lastUserInput": payload.get("text") or "",
                    "session_id": payload.get("sessionId") or "",
                },
                spawn=False,
            )
        return 0

    if action == "on":
        workspace_id = (
            argv[2] if len(argv) > 2 else str(load_switch().get("workspace_id") or "")
        )
        if not workspace_id:
            print("Usage: listen.py on <workspace_id> (the workspace must be explicit)")
            return 2
        save_switch(enabled=True, workspace_id=workspace_id)
        print("Listen mode: ON (local).")
        print(
            "Privacy: from now on the text of your user messages is sent to the configured "
            "ReqogniLoom server and processed by its model to propose artifacts. Only user "
            "messages are captured — never assistant text or tool output."
        )
        print("Both switches must be on: the server setting `capture.enabled` stays off by default.")
        return 0

    if action == "off":
        switch = load_switch()
        save_switch(enabled=False, workspace_id=switch.get("workspace_id"))
        removed = clear_pending()
        print("Listen mode: OFF (local).")
        deleted = removed["queued"] + removed["incoming"]
        if deleted:
            print(f"{deleted} unsent message(s) were deleted: nothing that was not sent is kept.")
        return 0

    if action == "status":
        print(status())
        return 0

    # Hook mode: JSON on stdin. An interactive run without a payload is not a hook.
    if sys.stdin.isatty():
        print("Usage: listen.py [--drain|enqueue|on <workspace_id>|off|status]")
        return 2
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw or "{}")
    except (json.JSONDecodeError, ValueError):
        log("unreadable hook payload")
        return 0
    if isinstance(payload, dict):
        handle_event(payload)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
