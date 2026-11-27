"""Contract tests for the Claude Code listen-mode relay (plan P4).

The Node scripts are exercised as a black box against a local HTTP stub, the way
Claude Code invokes them: JSON on stdin, environment variables for the plugin
options and one state directory that both entry points resolve identically.

The hook never performs network work any more — it queues and starts a detached
worker. The deterministic contract is therefore checked in two halves:

* ``_run_hook`` (with ``CLAUDE_PLUGIN_LISTEN_NO_WORKER=1``) proves what the hook
  itself does: filter, queue write, lock behaviour, no request, fast exit.
* ``_drain`` runs the worker in the foreground and proves delivery, retry
  semantics and the status file.

One separate test lets the hook spawn the real detached worker and waits for it,
because "the worker survives the hook process" is the defect this suite guards.

Run by the CI job "Agent Templates & Distribution" (Node is on the runner).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

TEMPLATES_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = TEMPLATES_DIR / "claude-plugin" / "scripts"
HOOK = SCRIPTS_DIR / "capture-hook.mjs"
LISTEN = SCRIPTS_DIR / "listen.mjs"

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None, reason="node is required for the relay tests"
)

WORKSPACE = "3f1c2a9e-7b4d-4c58-9a01-2d6e8f0a1b23"
VALID_PROMPT = (
    "The display must show a red alarm when the pressure exceeds 8 bar."
)


class _StubHandler(BaseHTTPRequestHandler):
    server_version = "ReqogniLoomStub/1.0"

    def do_POST(self):  # noqa: N802 — BaseHTTPRequestHandler API
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length)
        payload = json.loads(raw or b"{}")
        self.server.requests.append(
            {"path": self.path, "headers": dict(self.headers), "json": payload}
        )
        status, body = (
            self.server.responses.pop(0)
            if self.server.responses
            else (200, {"created": [], "skipped": {}, "request_id": "stub"})
        )
        encoded = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, *args):  # keep pytest output clean
        return


@pytest.fixture()
def stub_server():
    server = HTTPServer(("127.0.0.1", 0), _StubHandler)
    server.requests = []
    server.responses = []
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _state_dir(tmp_path: Path) -> Path:
    path = tmp_path / "plugin-data"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_listen(state_dir: Path, enabled: bool) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "listen.json").write_text(
        json.dumps({"enabled": enabled}), encoding="utf-8"
    )


def _base_env(
    state_dir: Path,
    server: HTTPServer | None,
    *,
    workspace: str | None = WORKSPACE,
) -> dict[str, str]:
    """Environment shared by hook, worker and command.

    ``CLAUDE_PLUGIN_DATA`` is removed on purpose: the plugin command shell does
    not set it, and keying the state on it is exactly the divergence this suite
    now pins. Both entry points must resolve ``REQNILOOM_LISTEN_DIR``.
    """
    env = os.environ.copy()
    env.pop("CLAUDE_PLUGIN_DATA", None)
    env["REQNILOOM_LISTEN_DIR"] = str(state_dir)
    env["CLAUDE_PLUGIN_OPTION_MCP_URL"] = (
        f"http://127.0.0.1:{server.server_port}" if server is not None else ""
    )
    env["CLAUDE_PLUGIN_OPTION_API_KEY"] = "reqlo_test_key" if server is not None else ""
    env["CLAUDE_PLUGIN_OPTION_WORKSPACE_ID"] = workspace or ""
    return env


def _hook_payload(tmp_path: Path, prompt: str) -> str:
    return json.dumps(
        {
            "hook_event_name": "UserPromptSubmit",
            "session_id": "session-1",
            "prompt_id": "prompt-1",
            "cwd": str(tmp_path),
            "prompt": prompt,
        }
    )


def _run_hook(
    tmp_path: Path,
    server: HTTPServer,
    *,
    prompt: str = VALID_PROMPT,
    workspace: str | None = WORKSPACE,
    no_worker: bool = True,
) -> subprocess.CompletedProcess[str]:
    state_dir = _state_dir(tmp_path)
    env = _base_env(state_dir, server, workspace=workspace)
    if no_worker:
        # Deterministic seam: the detached worker is what the suite runs itself.
        env["CLAUDE_PLUGIN_LISTEN_NO_WORKER"] = "1"
    return subprocess.run(
        ["node", str(HOOK)],
        input=_hook_payload(tmp_path, prompt),
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )


def _drain(
    tmp_path: Path,
    server: HTTPServer,
    *,
    workspace: str | None = WORKSPACE,
) -> subprocess.CompletedProcess[str]:
    state_dir = _state_dir(tmp_path)
    env = _base_env(state_dir, server, workspace=workspace)
    return subprocess.run(
        ["node", str(HOOK), "--drain"],
        # The worker needs no payload: it must not read stdin at all.
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )


def _queue_lines(state_dir: Path) -> list[dict]:
    path = state_dir / "capture-queue.jsonl"
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _run_listen(
    tmp_path: Path,
    *args: str,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    if env is None:
        env = _base_env(_state_dir(tmp_path), None, workspace=None)
    return subprocess.run(
        ["node", str(LISTEN), *args],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )


def test_default_off_sends_nothing(tmp_path, stub_server):
    result = _run_hook(tmp_path, stub_server)  # no listen.json -> default off
    assert result.returncode == 0
    assert result.stdout == ""
    assert _drain(tmp_path, stub_server).returncode == 0
    assert stub_server.requests == []
    assert _queue_lines(_state_dir(tmp_path)) == []


def test_short_message_and_slash_command_are_filtered(tmp_path, stub_server):
    _write_listen(_state_dir(tmp_path), True)
    short = _run_hook(tmp_path, stub_server, prompt="too short")
    assert short.returncode == 0
    assert short.stdout == ""

    command = _run_hook(
        tmp_path,
        stub_server,
        prompt="/status — show the ReqogniLoom listen mode and the queue length",
    )
    assert command.returncode == 0
    assert command.stdout == ""
    assert _drain(tmp_path, stub_server).returncode == 0
    assert stub_server.requests == []
    assert _queue_lines(_state_dir(tmp_path)) == []


def test_valid_message_posts_the_capture_contract(tmp_path, stub_server):
    _write_listen(_state_dir(tmp_path), True)
    result = _run_hook(tmp_path, stub_server)
    assert result.returncode == 0
    assert result.stdout == ""

    # The hook itself sent nothing; the worker does the network work.
    assert stub_server.requests == []
    assert len(_queue_lines(_state_dir(tmp_path))) == 1
    assert _drain(tmp_path, stub_server).returncode == 0

    assert len(stub_server.requests) == 1
    request = stub_server.requests[0]
    assert request["path"] == "/api/v1/suggestions/capture/"
    body = request["json"]
    assert body["workspace_id"] == WORKSPACE
    assert body["text"] == VALID_PROMPT
    assert body["client"] == "claude-code"
    assert len(body["idempotency_key"]) == 64
    assert body["source_session"] == "session-1"
    assert body["message_id"] == "prompt-1"

    # The API key travels in a header, never in the body or the log.
    assert request["headers"].get("X-API-Key") == "reqlo_test_key"
    assert "reqlo_test_key" not in json.dumps(body)

    state_dir = _state_dir(tmp_path)
    assert _queue_lines(state_dir) == []
    status = json.loads((state_dir / "listen-status.json").read_text())
    assert status["captured"] == 1
    assert status["failed"] == 0
    assert status["queued"] == 0
    assert status["last_success_at"]


def test_hook_returns_fast_and_leaves_the_message_queued(tmp_path, stub_server):
    """The hook must not wait for the network: queue in, exit in well under 2 s."""
    _write_listen(_state_dir(tmp_path), True)
    started = time.monotonic()
    result = _run_hook(tmp_path, stub_server)
    elapsed = time.monotonic() - started

    assert result.returncode == 0
    assert result.stdout == ""
    assert elapsed < 2.0

    state_dir = _state_dir(tmp_path)
    queued = _queue_lines(state_dir)
    assert len(queued) == 1
    assert queued[0]["text"] == VALID_PROMPT
    # Nothing was sent and no status file was written by the hook alone.
    assert stub_server.requests == []
    assert not (state_dir / "listen-status.json").exists()

    # The subsequent worker drains the queue and writes the status.
    assert _drain(tmp_path, stub_server).returncode == 0
    assert len(stub_server.requests) == 1
    assert _queue_lines(state_dir) == []
    status = json.loads((state_dir / "listen-status.json").read_text())
    assert status["captured"] == 1
    assert status["queued"] == 0
    assert status["last_success_at"]


def test_detached_worker_delivers_without_a_second_prompt(tmp_path, stub_server):
    """The worker outlives the hook process — the AP0 defect this change fixes."""
    _write_listen(_state_dir(tmp_path), True)
    result = _run_hook(tmp_path, stub_server, no_worker=False)
    assert result.returncode == 0
    assert result.stdout == ""

    state_dir = _state_dir(tmp_path)
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if stub_server.requests and not _queue_lines(state_dir):
            break
        time.sleep(0.05)

    assert len(stub_server.requests) == 1
    assert stub_server.requests[0]["json"]["text"] == VALID_PROMPT
    assert _queue_lines(state_dir) == []
    status = json.loads((state_dir / "listen-status.json").read_text())
    assert status["captured"] == 1
    assert status["queued"] == 0
    assert status["last_success_at"]


def test_server_error_keeps_the_entry_and_the_next_run_drains_it(tmp_path, stub_server):
    _write_listen(_state_dir(tmp_path), True)
    stub_server.responses = [(500, {"error": {"code": "INTERNAL"}})]
    first = _run_hook(tmp_path, stub_server)
    assert first.returncode == 0
    assert first.stdout == ""
    assert _drain(tmp_path, stub_server).returncode == 0

    state_dir = _state_dir(tmp_path)
    queued = _queue_lines(state_dir)
    assert len(queued) == 1
    assert queued[0]["text"] == VALID_PROMPT
    assert queued[0]["attempts"] == 1

    # The log and the status file are diagnostics: they must not leak the
    # message text or the API key (the queue itself is local state).
    log = (state_dir / "capture.log").read_text(encoding="utf-8")
    status_raw = (state_dir / "listen-status.json").read_text(encoding="utf-8")
    for haystack in (log, status_raw):
        assert VALID_PROMPT not in haystack
        assert "reqlo_test_key" not in haystack
    assert "HTTP 500" in log

    second = _run_hook(tmp_path, stub_server)
    assert second.returncode == 0
    assert second.stdout == ""
    assert _drain(tmp_path, stub_server).returncode == 0
    assert _queue_lines(state_dir) == []
    status = json.loads((state_dir / "listen-status.json").read_text())
    assert status["queued"] == 0
    assert status["last_success_at"]


def test_missing_workspace_is_reported_but_never_fails(tmp_path, stub_server):
    _write_listen(_state_dir(tmp_path), True)
    result = _run_hook(tmp_path, stub_server, workspace=None)
    assert result.returncode == 0
    assert result.stdout == ""
    assert _drain(tmp_path, stub_server, workspace=None).returncode == 0
    assert stub_server.requests == []

    status = json.loads(
        (_state_dir(tmp_path) / "listen-status.json").read_text(encoding="utf-8")
    )
    assert status["last_error"].startswith("missing_config")
    assert "workspace_id" in status["last_error"]


def test_hook_never_writes_to_stdout_or_stderr(tmp_path, stub_server):
    _write_listen(_state_dir(tmp_path), True)
    stub_server.responses = [(503, {"error": {"code": "LLM_UNAVAILABLE"}})]
    result = _run_hook(tmp_path, stub_server)
    assert result.returncode == 0
    assert result.stdout == ""
    # A hook's stderr is shown to the user; the relay stays silent there too.
    assert result.stderr == ""
    assert _drain(tmp_path, stub_server).stderr == ""
    state_dir = _state_dir(tmp_path)
    for name in ("capture.log", "listen-status.json"):
        raw = (state_dir / name).read_text(encoding="utf-8")
        assert VALID_PROMPT not in raw
        assert "reqlo_test_key" not in raw


def test_duplicate_and_disabled_are_terminal(tmp_path, stub_server):
    """409 CAPTURE_DISABLED / DUPLICATE must not be retried forever."""
    _write_listen(_state_dir(tmp_path), True)
    stub_server.responses = [
        (409, {"error": {"code": "DUPLICATE"}}),
        (409, {"error": {"code": "CAPTURE_DISABLED"}}),
    ]
    state_dir = _state_dir(tmp_path)
    assert _run_hook(tmp_path, stub_server).returncode == 0
    assert _drain(tmp_path, stub_server).returncode == 0
    assert _queue_lines(state_dir) == []
    assert _run_hook(tmp_path, stub_server).returncode == 0
    assert _drain(tmp_path, stub_server).returncode == 0
    assert _queue_lines(state_dir) == []


def test_permanent_400_is_dropped_but_401_is_kept(tmp_path, stub_server):
    _write_listen(_state_dir(tmp_path), True)
    state_dir = _state_dir(tmp_path)

    stub_server.responses = [(400, {"error": {"code": "TEXT_TOO_LONG"}})]
    assert _run_hook(tmp_path, stub_server).returncode == 0
    assert _drain(tmp_path, stub_server).returncode == 0
    assert _queue_lines(state_dir) == []

    stub_server.responses = [(401, {"error": {"code": "UNAUTHORIZED"}})]
    assert _run_hook(tmp_path, stub_server).returncode == 0
    assert _drain(tmp_path, stub_server).returncode == 0
    queued = _queue_lines(state_dir)
    assert len(queued) == 1
    assert queued[0]["attempts"] == 1


def test_disabled_listen_does_not_drain_a_queued_message(tmp_path, stub_server):
    state_dir = _state_dir(tmp_path)
    (state_dir / "capture-queue.jsonl").write_text(
        json.dumps(
            {
                "workspace_id": WORKSPACE,
                "text": VALID_PROMPT,
                "client": "claude-code",
                "source_session": "s",
                "message_id": "m",
                "idempotency_key": "k" * 64,
                "created_at": "2026-11-27T00:00:00.000Z",
                "attempts": 0,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    # No listen.json -> default off.
    result = _run_hook(tmp_path, stub_server)
    assert result.returncode == 0
    assert _drain(tmp_path, stub_server).returncode == 0
    assert stub_server.requests == []
    assert len(_queue_lines(state_dir)) == 1


def test_lock_contention_still_queues_the_message(tmp_path, stub_server):
    state_dir = _state_dir(tmp_path)
    _write_listen(state_dir, True)
    lock = state_dir / "capture-queue.lock"
    lock.mkdir()  # a fresh lock, as a concurrently running hook/worker would hold it

    result = _run_hook(tmp_path, stub_server)
    assert result.returncode == 0
    assert stub_server.requests == []
    pending = list((state_dir / "capture-incoming").glob("*.json"))
    assert len(pending) == 1
    assert json.loads(pending[0].read_text())["text"] == VALID_PROMPT

    # The next lock holder merges the segment and delivers it with its own
    # message; nothing is lost by the no-lock append or the queue rewrite.
    lock.rmdir()
    second = _run_hook(tmp_path, stub_server)
    assert second.returncode == 0
    assert _drain(tmp_path, stub_server).returncode == 0
    assert len(stub_server.requests) == 2
    assert all(r["json"]["text"] == VALID_PROMPT for r in stub_server.requests)
    assert _queue_lines(state_dir) == []
    assert list((state_dir / "capture-incoming").glob("*.json")) == []


def test_listen_command_switches_and_reports(tmp_path):
    off = _run_listen(tmp_path, "off")
    assert off.returncode == 0
    assert "OFF" in off.stdout
    assert json.loads((_state_dir(tmp_path) / "listen.json").read_text())[
        "enabled"
    ] is False

    on = _run_listen(tmp_path, "on")
    assert on.returncode == 0
    assert "privacy" in on.stdout.lower()
    # The switch must reach the next message without a restart.
    assert "next message in this session" in on.stdout
    assert json.loads((_state_dir(tmp_path) / "listen.json").read_text())[
        "enabled"
    ] is True

    status = _run_listen(tmp_path, "status")
    assert status.returncode == 0
    assert "Local switch:  ON" in status.stdout
    assert "Queue:" in status.stdout
    # No URL/key/workspace configured: the server switch is reported unknown,
    # never fabricated.
    assert "unknown" in status.stdout.lower()


def test_listen_off_deletes_queued_and_incoming_messages(tmp_path):
    """Privacy: switching off must not leave unsent message text on disk."""
    state_dir = _state_dir(tmp_path)
    _write_listen(state_dir, True)
    (state_dir / "capture-queue.jsonl").write_text(
        json.dumps(
            {
                "workspace_id": WORKSPACE,
                "text": VALID_PROMPT,
                "client": "claude-code",
                "idempotency_key": "k" * 64,
                "created_at": "2026-11-27T00:00:00.000Z",
                "attempts": 0,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    incoming = state_dir / "capture-incoming"
    incoming.mkdir()
    (incoming / "segment.json").write_text(
        json.dumps({"text": VALID_PROMPT, "workspace_id": WORKSPACE}),
        encoding="utf-8",
    )
    (state_dir / "listen-status.json").write_text(
        json.dumps({"captured": 3, "failed": 0, "queued": 2}), encoding="utf-8"
    )

    off = _run_listen(tmp_path, "off")
    assert off.returncode == 0
    assert "OFF" in off.stdout
    assert "deleted" in off.stdout
    assert VALID_PROMPT not in off.stdout

    assert not (state_dir / "capture-queue.jsonl").exists()
    assert not incoming.exists()
    status = json.loads((state_dir / "listen-status.json").read_text())
    assert status["queued"] == 0
    # Counters are history, not content: they survive the switch.
    assert status["captured"] == 3


def test_listen_command_and_hook_share_one_state_dir(tmp_path, stub_server):
    """`/reqogniloom:listen on` must reach the hook in the same session.

    Live defect: the command shell has no ``CLAUDE_PLUGIN_DATA``, so the command
    wrote a different directory than the hook read and the switch never applied.
    """
    state_dir = _state_dir(tmp_path)
    env = _base_env(state_dir, stub_server)
    assert "CLAUDE_PLUGIN_DATA" not in env

    assert _run_listen(tmp_path, "on", env=env).returncode == 0
    assert json.loads((state_dir / "listen.json").read_text())["enabled"] is True

    # The hook resolves the same directory and now captures.
    hook_env = dict(env, CLAUDE_PLUGIN_LISTEN_NO_WORKER="1")
    hook = subprocess.run(
        ["node", str(HOOK)],
        input=_hook_payload(tmp_path, VALID_PROMPT),
        capture_output=True,
        text=True,
        env=hook_env,
        timeout=60,
    )
    assert hook.returncode == 0
    assert len(_queue_lines(state_dir)) == 1

    assert _drain(tmp_path, stub_server).returncode == 0
    assert len(stub_server.requests) == 1

    # `off` stops the very next message and clears what is pending.
    assert _run_listen(tmp_path, "off", env=env).returncode == 0
    assert not (state_dir / "capture-queue.jsonl").exists()
    second = subprocess.run(
        ["node", str(HOOK)],
        input=_hook_payload(tmp_path, VALID_PROMPT),
        capture_output=True,
        text=True,
        env=hook_env,
        timeout=60,
    )
    assert second.returncode == 0
    assert len(stub_server.requests) == 1
    assert _queue_lines(state_dir) == []


def test_state_dir_defaults_to_the_home_directory(tmp_path, stub_server):
    """Without the override both entry points resolve ``~/.reqogniloom/listen``."""
    home = tmp_path / "home"
    home.mkdir()
    env = os.environ.copy()
    env.pop("REQNILOOM_LISTEN_DIR", None)
    env.pop("CLAUDE_PLUGIN_DATA", None)
    env.update(
        {
            "HOME": str(home),
            "USERPROFILE": str(home),
            "CLAUDE_PLUGIN_OPTION_MCP_URL": f"http://127.0.0.1:{stub_server.server_port}",
            "CLAUDE_PLUGIN_OPTION_API_KEY": "reqlo_test_key",
            "CLAUDE_PLUGIN_OPTION_WORKSPACE_ID": WORKSPACE,
            "CLAUDE_PLUGIN_LISTEN_NO_WORKER": "1",
        }
    )
    stable = home / ".reqogniloom" / "listen"

    assert _run_listen(tmp_path, "on", env=env).returncode == 0
    assert json.loads((stable / "listen.json").read_text())["enabled"] is True

    hook = subprocess.run(
        ["node", str(HOOK)],
        input=_hook_payload(tmp_path, VALID_PROMPT),
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    assert hook.returncode == 0
    assert len(_queue_lines(stable)) == 1

    drain = subprocess.run(
        ["node", str(HOOK), "--drain"],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    assert drain.returncode == 0
    assert len(stub_server.requests) == 1
    assert _queue_lines(stable) == []
    # Nothing was written into the real home of the test runner.
    assert _queue_lines(_state_dir(tmp_path)) == []


def test_listen_command_rejects_unknown_arguments(tmp_path):
    result = _run_listen(tmp_path, "maybe")
    assert result.returncode == 2
    assert "Usage:" in result.stdout
