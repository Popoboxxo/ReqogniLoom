"""The listen-mode relay contract, implemented once for the Hermes plugin.

Every ReqogniLoom client (Claude Code, Hermes, OpenCode V1/V2, Antigravity)
implements the same contract in its own language — see
``docs/clients/listen-mode-contract.md``. This module is the Python reference:
the state directory, the write-ahead queue, the cheap pre-filter, the lock, the
status file and the drain run live here, so the ``pre_llm_call`` hook
(``__init__.py``), the detached worker (``_capture.py``) and the slash command
all read and write exactly one layout.

Design rules that are not negotiable:

* the hook does **no network work** — it appends and returns, so a slow or dead
  server can never delay the user's turn (G2);
* nothing is written to stdout by a hook path (stdout becomes model context);
* the message text never reaches ``capture.log`` or ``listen-status.json``;
* default off, and ``off`` deletes anything unsent.
"""
from __future__ import annotations

import calendar
import hashlib
import json
import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

#: Shortest user message worth a server round-trip (contract: 40 characters).
MIN_TEXT_LENGTH = 40
#: A pasted log or file is not a requirement statement (contract: 300 lines).
MAX_LINES = 300
#: One client-side request must outlast the server's inline model turn.
REQUEST_TIMEOUT_MS = 60_000
#: At most this many entries per drain run.
MAX_FLUSH_PER_RUN = 5
#: Retry/retention bounds of the write-ahead queue.
MAX_ATTEMPTS = 5
MAX_QUEUE_ENTRIES = 100
MAX_ENTRY_AGE_SECONDS = 7 * 24 * 60 * 60
LOCK_STALE_SECONDS = 5 * 60
MAX_FIELD_LENGTH = 255
MAX_IDEMPOTENCY_LENGTH = 128
MAX_LOG_BYTES = 1_000_000
#: Antigravity's dedupe set (stage B only) — bounded so it cannot grow forever.
MAX_SEEN_KEYS = 500

LISTEN_FILE = "listen.json"
QUEUE_FILE = "capture-queue.jsonl"
STATUS_FILE = "listen-status.json"
INCOMING_DIR = "capture-incoming"
LOCK_DIR = "capture-queue.lock"
LOG_FILE = "capture.log"
SEEN_FILE = "capture-seen.json"


# ---------------------------------------------------------------------------
# Paths and small file helpers
# ---------------------------------------------------------------------------


def listen_dir() -> Path:
    """``~/.reqogniloom/listen``, overridable via ``REQNILOOM_LISTEN_DIR``.

    Deliberately **not** derived from ``HERMES_HOME``: the directory is shared
    by every client on the machine, and a per-client home made ``listen on``
    write one directory while the hook read another on the first live run.
    """
    configured = (os.environ.get("REQNILOOM_LISTEN_DIR") or "").strip()
    if configured:
        return Path(configured)
    return Path.home() / ".reqogniloom" / "listen"


def ensure_dir() -> Path:
    directory = listen_dir()
    directory.mkdir(parents=True, exist_ok=True)
    _secure_dir(directory)
    return directory


def _secure_dir(directory: Path) -> None:
    try:
        os.chmod(directory, 0o700)
    except OSError:
        # ACL-only filesystems (Windows) reject POSIX modes; the write works.
        pass


def _secure_file(path: Path) -> None:
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def read_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback


def write_json_atomic(path: Path, value: Any) -> None:
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(f"{json.dumps(value, indent=2, sort_keys=True)}\n", encoding="utf-8")
    _secure_file(tmp)
    os.replace(tmp, path)
    _secure_file(path)


def log(message: str) -> None:
    """Diagnostics without message text and without the API key."""
    try:
        directory = ensure_dir()
        path = directory / LOG_FILE
        if path.exists() and path.stat().st_size > MAX_LOG_BYTES:
            path.replace(path.with_name(f"{LOG_FILE}.1"))
        stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"{stamp} {message}\n")
        _secure_file(path)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Switch
# ---------------------------------------------------------------------------


def load_switch() -> Dict[str, Any]:
    data = read_json(listen_dir() / LISTEN_FILE, {})
    return data if isinstance(data, dict) else {}


def is_enabled(switch: Optional[Dict[str, Any]] = None) -> bool:
    data = load_switch() if switch is None else switch
    return data.get("enabled") is True


def save_switch(*, enabled: bool, workspace_id: Optional[str] = None, client: str = "hermes") -> Dict[str, Any]:
    ensure_dir()
    current = load_switch()
    updated = {
        **current,
        "enabled": bool(enabled),
        "client": client,
    }
    if workspace_id:
        updated["workspace_id"] = str(workspace_id)
    write_json_atomic(listen_dir() / LISTEN_FILE, updated)
    return updated


# ---------------------------------------------------------------------------
# Filter, idempotency, entry construction
# ---------------------------------------------------------------------------


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


def build_entry(
    *,
    workspace_id: str,
    text: str,
    client: str,
    source_session: str = "",
    message_id: str = "",
) -> Optional[Dict[str, Any]]:
    normalized = normalize_text(text)
    if not passes_filter(normalized):
        return None
    truncate = lambda value: str(value or "")[:MAX_FIELD_LENGTH]  # noqa: E731
    return {
        "workspace_id": str(workspace_id),
        "text": normalized,
        "client": str(client),
        "source_session": truncate(source_session),
        "message_id": truncate(message_id),
        "idempotency_key": idempotency_key(str(workspace_id), normalized),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "attempts": 0,
        "last_attempt_at": None,
    }


# ---------------------------------------------------------------------------
# Queue
# ---------------------------------------------------------------------------


def queue_path(directory: Optional[Path] = None) -> Path:
    return (directory or listen_dir()) / QUEUE_FILE


def read_queue(directory: Optional[Path] = None) -> List[Dict[str, Any]]:
    path = queue_path(directory)
    if not path.exists():
        return []
    entries: List[Dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            # A torn line from a killed write is dropped, not retried forever.
            continue
        if isinstance(entry, dict) and entry.get("text"):
            entries.append(entry)
    return entries


def rewrite_queue(entries: List[Dict[str, Any]], directory: Optional[Path] = None) -> None:
    path = queue_path(directory)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    body = "\n".join(json.dumps(entry) for entry in entries)
    tmp.write_text(f"{body}\n" if body else "", encoding="utf-8")
    _secure_file(tmp)
    os.replace(tmp, path)
    _secure_file(path)


def append_queue(entry: Dict[str, Any], directory: Optional[Path] = None) -> None:
    path = queue_path(directory)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{json.dumps(entry)}\n")
    _secure_file(path)


def cap_queue(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if len(entries) <= MAX_QUEUE_ENTRIES:
        return entries
    dropped = len(entries) - MAX_QUEUE_ENTRIES
    log(f"queue capped: dropped {dropped} oldest capture(s)")
    return entries[dropped:]


def incoming_dir(directory: Optional[Path] = None) -> Path:
    return (directory or listen_dir()) / INCOMING_DIR


def write_incoming(entry: Dict[str, Any], directory: Optional[Path] = None) -> None:
    """Persist one message without touching the shared queue.

    A hook that loses the lock must never rewrite the queue: the lock holder may
    be rewriting it from an older snapshot. Each message gets its own immutable
    segment instead, and the next lock holder merges it.
    """
    pending = incoming_dir(directory)
    pending.mkdir(parents=True, exist_ok=True)
    _secure_dir(pending)
    name = f"{int(time.time() * 1000)}-{os.getpid()}-{os.urandom(4).hex()}.json"
    write_json_atomic(pending / name, entry)


def merge_incoming(directory: Optional[Path] = None) -> int:
    pending = incoming_dir(directory)
    if not pending.exists():
        return 0
    entries: List[Dict[str, Any]] = []
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
    rewrite_queue(cap_queue([*read_queue(directory), *entries]), directory)
    return len(entries)


# ---------------------------------------------------------------------------
# Lock (mkdir-based, portable; stale after LOCK_STALE_SECONDS)
# ---------------------------------------------------------------------------


@contextmanager
def queue_lock(directory: Optional[Path] = None) -> Iterator[bool]:
    directory = directory or listen_dir()
    lock = directory / LOCK_DIR
    acquired = False
    try:
        lock.mkdir()
        acquired = True
    except FileExistsError:
        try:
            age = time.time() - lock.stat().st_mtime
        except OSError:
            age = 0.0
        if age > LOCK_STALE_SECONDS:
            stale = lock.with_name(f"{LOCK_DIR}.stale-{os.getpid()}-{int(time.time())}")
            try:
                os.replace(lock, stale)
                for child in sorted(stale.rglob("*"), reverse=True):
                    child.unlink(missing_ok=True)
                stale.rmdir()
            except OSError:
                pass
            try:
                lock.mkdir()
                acquired = True
            except OSError:
                acquired = False
    except OSError:
        acquired = False
    try:
        yield acquired
    finally:
        if acquired:
            try:
                lock.rmdir()
            except OSError:
                pass


def enqueue(
    *,
    workspace_id: str,
    text: str,
    client: str = "hermes",
    source_session: str = "",
    message_id: str = "",
) -> Optional[Dict[str, Any]]:
    """Append one message to the write-ahead queue. Never raises.

    Returns the entry that was persisted, or ``None`` when the message was
    filtered out or could not be written (a lost message must never break the
    user's turn).
    """
    entry = build_entry(
        workspace_id=workspace_id,
        text=text,
        client=client,
        source_session=source_session,
        message_id=message_id,
    )
    if entry is None:
        return None
    if not is_enabled():
        return None
    directory = ensure_dir()
    try:
        with queue_lock(directory) as locked:
            if locked:
                append_queue(entry, directory)
                entries = read_queue(directory)
                if len(entries) > MAX_QUEUE_ENTRIES:
                    rewrite_queue(cap_queue(entries), directory)
            else:
                write_incoming(entry, directory)
                log("capture queued: queue lock held")
    except OSError as exc:
        log(f"capture enqueue failed: {type(exc).__name__}")
        return None
    return entry


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


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
    # A recovered failure is not the "last error" any more.
    state["last_error"] = None
    state["last_error_at"] = None


def record_failure(state: Dict[str, Any], detail: str) -> None:
    state["failed"] = int(state.get("failed") or 0) + 1
    state["last_error"] = str(detail or "error")[:120]
    state["last_error_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ---------------------------------------------------------------------------
# Delivery
# ---------------------------------------------------------------------------


def _error_status(exc: BaseException) -> Optional[int]:
    status = getattr(exc, "status", None)
    return status if isinstance(status, int) else None


def deliver(client: Any, entry: Dict[str, Any]) -> Tuple[bool, str]:
    """Deliver one queue entry. Returns ``(terminal, detail)``.

    ``terminal`` means "do not retry": delivered, or a response that can never
    succeed (409 duplicate/disabled, 400 permanent defect).
    """
    body = {
        "workspace_id": entry["workspace_id"],
        "text": entry["text"],
        "client": entry.get("client") or "hermes",
        "idempotency_key": entry.get("idempotency_key")
        or idempotency_key(entry["workspace_id"], entry["text"]),
    }
    if entry.get("source_session"):
        body["source_session"] = entry["source_session"]
    if entry.get("message_id"):
        body["message_id"] = entry["message_id"]

    try:
        client.capture_suggestion(
            workspace_id=body["workspace_id"],
            text=body["text"],
            client=body["client"],
            source_session=body.get("source_session") or "",
            message_id=body.get("message_id") or "",
            idempotency_key=body["idempotency_key"],
            timeout_seconds=REQUEST_TIMEOUT_MS / 1000.0,
        )
    except Exception as exc:  # noqa: BLE001 — classification is the whole job here
        status = _error_status(exc)
        if status == 409:
            return True, "HTTP 409"
        if status == 400:
            return True, "HTTP 400"
        detail = "timeout" if isinstance(exc, TimeoutError) else "network_error"
        if status is not None:
            detail = f"HTTP {status}"
        return False, detail
    return True, "delivered"


def drain(client: Any) -> int:
    """Deliver the queue head. Returns the number of delivered entries."""
    switch = load_switch()
    if not is_enabled(switch):
        # Switched off after the message was queued: never send it.
        return 0
    workspace_id = str(switch.get("workspace_id") or "").strip()
    directory = ensure_dir()
    state = read_status()

    missing: List[str] = []
    if not workspace_id:
        missing.append("workspace_id")
    if not getattr(client, "base_url", ""):
        missing.append("mcp_url")
    if not getattr(client, "api_key", ""):
        missing.append("api_key")
    if missing:
        record_failure(state, f"missing_config:{','.join(missing)}")
        state["queued"] = len(read_queue(directory))
        write_status(state)
        log(f"capture skipped: missing config {','.join(missing)}")
        return 0

    with queue_lock(directory) as locked:
        if not locked:
            log("drain skipped: queue lock held")
            return 0
        merged = merge_incoming(directory)
        if merged:
            log(f"merged {merged} queued capture(s)")

        now = time.time()
        entries = read_queue(directory)
        deliverable: List[Dict[str, Any]] = []
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
            if len(deliverable) < MAX_FLUSH_PER_RUN:
                deliverable.append(entry)
            else:
                keep.append(entry)

        selected = {id(entry) for entry in deliverable}
        sent = 0
        for entry in entries:
            if id(entry) not in selected:
                continue
            terminal, detail = deliver(client, entry)
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
        rewrite_queue(keep, directory)
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
        # ``%Y-%m-%dT%H:%M:%SZ`` is what we write; tolerate a fractional suffix.
        return float(calendar.timegm(time.strptime(raw[:19], "%Y-%m-%dT%H:%M:%S")))
    except (ValueError, OverflowError):
        return None


# ---------------------------------------------------------------------------
# Switch cleanup
# ---------------------------------------------------------------------------


def clear_pending() -> Dict[str, int]:
    """Delete unsent message text. Used by ``listen off`` (privacy action)."""
    directory = ensure_dir()
    removed = {"queued": len(read_queue(directory)), "incoming": 0}
    pending = incoming_dir(directory)
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


# ---------------------------------------------------------------------------
# Antigravity dedupe (stage B)
# ---------------------------------------------------------------------------


def seen_key(session_id: str, text: str) -> str:
    return hashlib.sha256(f"{session_id}\n{text}".encode("utf-8")).hexdigest()


def claim_seen(session_id: str, text: str) -> bool:
    """True when this ``(session, text)`` pair is new; False on a repeat.

    ``PreInvocation`` fires before every model call, so without this check one
    user message would be captured on every turn of the conversation.
    """
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
