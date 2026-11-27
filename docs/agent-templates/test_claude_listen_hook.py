"""Contract tests for the Claude Code listen-mode relay (plan P4).

The Node script is exercised as a black box against a local HTTP stub, the same
way Claude Code invokes it: JSON on stdin, environment variables for the plugin
options, and a state directory under ``CLAUDE_PLUGIN_DATA``. No real server and
no message content in the assertions that touch logs.

Run by the CI job "Agent Templates & Distribution" (Node is on the runner).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

TEMPLATES_DIR = Path(__file__).resolve().parent
HOOK = TEMPLATES_DIR / "claude-plugin" / "scripts" / "capture-hook.mjs"

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
    (state_dir / "listen.json").write_text(
        json.dumps({"enabled": enabled}), encoding="utf-8"
    )


def _run_hook(
    tmp_path: Path,
    server: HTTPServer,
    *,
    prompt: str = VALID_PROMPT,
    workspace: str | None = WORKSPACE,
) -> subprocess.CompletedProcess[str]:
    state_dir = _state_dir(tmp_path)
    env = os.environ.copy()
    env.update(
        {
            "CLAUDE_PLUGIN_DATA": str(state_dir),
            "CLAUDE_PLUGIN_OPTION_MCP_URL": f"http://127.0.0.1:{server.server_port}",
            "CLAUDE_PLUGIN_OPTION_API_KEY": "reqlo_test_key",
            "CLAUDE_PLUGIN_OPTION_WORKSPACE_ID": workspace or "",
        }
    )
    payload = {
        "hook_event_name": "UserPromptSubmit",
        "session_id": "session-1",
        "prompt_id": "prompt-1",
        "cwd": str(tmp_path),
        "prompt": prompt,
    }
    return subprocess.run(
        ["node", str(HOOK)],
        input=json.dumps(payload),
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


def _run_listen(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    state_dir = _state_dir(tmp_path)
    env = os.environ.copy()
    env.update(
        {
            "CLAUDE_PLUGIN_DATA": str(state_dir),
            "CLAUDE_PLUGIN_OPTION_MCP_URL": "",
            "CLAUDE_PLUGIN_OPTION_API_KEY": "",
            "CLAUDE_PLUGIN_OPTION_WORKSPACE_ID": "",
        }
    )
    return subprocess.run(
        ["node", str(TEMPLATES_DIR / "claude-plugin" / "scripts" / "listen.mjs"), *args],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )


def test_default_off_sends_nothing(tmp_path, stub_server):
    result = _run_hook(tmp_path, stub_server)  # no listen.json -> default off
    assert result.returncode == 0
    assert result.stdout == ""
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
    assert stub_server.requests == []
    assert _queue_lines(_state_dir(tmp_path)) == []


def test_valid_message_posts_the_capture_contract(tmp_path, stub_server):
    _write_listen(_state_dir(tmp_path), True)
    result = _run_hook(tmp_path, stub_server)
    assert result.returncode == 0
    assert result.stdout == ""

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


def test_server_error_keeps_the_entry_and_the_next_run_drains_it(tmp_path, stub_server):
    _write_listen(_state_dir(tmp_path), True)
    stub_server.responses = [(500, {"error": {"code": "INTERNAL"}})]
    first = _run_hook(tmp_path, stub_server)
    assert first.returncode == 0
    assert first.stdout == ""

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
    assert _queue_lines(state_dir) == []
    status = json.loads((state_dir / "listen-status.json").read_text())
    assert status["queued"] == 0
    assert status["last_success_at"]


def test_missing_workspace_is_reported_but_never_fails(tmp_path, stub_server):
    _write_listen(_state_dir(tmp_path), True)
    result = _run_hook(tmp_path, stub_server, workspace=None)
    assert result.returncode == 0
    assert result.stdout == ""
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
    assert _queue_lines(state_dir) == []
    assert _run_hook(tmp_path, stub_server).returncode == 0
    assert _queue_lines(state_dir) == []


def test_permanent_400_is_dropped_but_401_is_kept(tmp_path, stub_server):
    _write_listen(_state_dir(tmp_path), True)
    state_dir = _state_dir(tmp_path)

    stub_server.responses = [(400, {"error": {"code": "TEXT_TOO_LONG"}})]
    assert _run_hook(tmp_path, stub_server).returncode == 0
    assert _queue_lines(state_dir) == []

    stub_server.responses = [(401, {"error": {"code": "UNAUTHORIZED"}})]
    assert _run_hook(tmp_path, stub_server).returncode == 0
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
    assert stub_server.requests == []
    assert len(_queue_lines(state_dir)) == 1


def test_lock_contention_still_queues_the_message(tmp_path, stub_server):
    state_dir = _state_dir(tmp_path)
    _write_listen(state_dir, True)
    lock = state_dir / "capture-queue.lock"
    lock.mkdir()  # a fresh lock, as a concurrently running hook would hold it

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


def test_listen_command_rejects_unknown_arguments(tmp_path):
    result = _run_listen(tmp_path, "maybe")
    assert result.returncode == 2
    assert "Usage:" in result.stdout

