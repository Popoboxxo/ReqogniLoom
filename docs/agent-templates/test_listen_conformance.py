"""Listen-mode conformance suite: the same scenarios against every adapter.

Feature contract: `docs/clients/listen-mode-contract.md` (G1–G6 of
`docs/superpowers/specs/2026-11-21-listen-modus-alle-clients-design.md`).
Every client implements the relay natively; this suite proves they produce the
**same request** and the **same state**, or states why a client was skipped.

Adapters (all driven as real processes, against a local HTTP stub):

* Claude Code — `claude-plugin/scripts/capture-hook.mjs` (+ `--drain`)
* Hermes — `integrations/hermes-agent-plugin/_capture.py --enqueue/--drain`
* OpenCode — `dist/npm/reqogniloom-opencode/listen.mjs` (`enqueue`/`--drain`)
* Antigravity — `dist/plugins/antigravity/listen.py` (`enqueue`/`--drain`)

A skipped client is reported as skipped with the missing runtime; it is never
counted green. The OpenCode plugin's own V1/V2 entry points are additionally
exercised through a tiny Node harness (``_opencode_plugin_harness``) so the
hook wiring, not just the relay, is covered.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = REPO_ROOT / "docs" / "agent-templates"
CLAUDE_HOOK = TEMPLATES / "claude-plugin" / "scripts" / "capture-hook.mjs"
HERMES_DIR = REPO_ROOT / "integrations" / "hermes-agent-plugin"
HERMES_RELAY = HERMES_DIR / "_capture.py"
OPENCODE_RELAY = REPO_ROOT / "dist" / "npm" / "reqogniloom-opencode" / "listen.mjs"
ANTIGRAVITY_RELAY = REPO_ROOT / "dist" / "plugins" / "antigravity" / "listen.py"

WORKSPACE = "3f1c2a9e-7b4d-4c58-9a01-2d6e8f0a1b23"
VALID_PROMPT = "The display must show a red alarm when the pressure exceeds 8 bar."
SHORT_PROMPT = "too short"
COMMAND_PROMPT = "/status — show the ReqogniLoom listen mode and the queue length"

NODE = shutil.which("node")
PYTHON = sys.executable


class _StubHandler(BaseHTTPRequestHandler):
    server_version = "ReqogniLoomConformance/1.0"

    def do_POST(self):  # noqa: N802 — BaseHTTPRequestHandler API
        length = int(self.headers.get("Content-Length") or 0)
        payload = json.loads(self.rfile.read(length) or b"{}")
        self.server.requests.append(
            {"path": self.path, "headers": dict(self.headers), "json": payload}
        )
        status, body = (
            self.server.responses.pop(0)
            if self.server.responses
            else (200, {"created": ["sug-1"], "skipped": {}, "request_id": "stub"})
        )
        encoded = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, *args):
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


class Adapter:
    """One client's relay, driven through its real command line."""

    name = "base"
    client = "other"
    requires = ""

    def __init__(self, tmp_path: Path, server: HTTPServer) -> None:
        self.tmp_path = tmp_path
        self.server = server
        self.state_dir = tmp_path / "listen"
        self.state_dir.mkdir(parents=True, exist_ok=True)

    # -- environment ---------------------------------------------------------
    def env(self) -> dict[str, str]:
        env = os.environ.copy()
        env["REQNILOOM_LISTEN_DIR"] = str(self.state_dir)
        return env

    def command(self, *args: str) -> list[str]:
        raise NotImplementedError

    # -- contract primitives -------------------------------------------------
    def write_switch(self, enabled: bool, workspace: str = WORKSPACE) -> None:
        (self.state_dir / "listen.json").write_text(
            json.dumps({"enabled": enabled, "workspace_id": workspace, "client": self.client}),
            encoding="utf-8",
        )

    def run(self, *args: str, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            self.command(*args),
            input=stdin,
            stdin=subprocess.DEVNULL if stdin is None else None,
            capture_output=True,
            text=True,
            env=self.env(),
            timeout=90,
        )

    def enqueue(self, text: str, session: str = "session-1") -> subprocess.CompletedProcess[str]:
        raise NotImplementedError

    def drain(self) -> subprocess.CompletedProcess[str]:
        raise NotImplementedError

    def switch_off(self) -> subprocess.CompletedProcess[str]:
        raise NotImplementedError

    # -- state readers -------------------------------------------------------
    def queue(self) -> list[dict]:
        path = self.state_dir / "capture-queue.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def status(self) -> dict:
        path = self.state_dir / "listen-status.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


class ClaudeAdapter(Adapter):
    name = "claude-code"
    client = "claude-code"
    requires = "node"

    def env(self) -> dict[str, str]:
        env = super().env()
        env.update(
            {
                "CLAUDE_PLUGIN_LISTEN_NO_WORKER": "1",
                "CLAUDE_PLUGIN_OPTION_MCP_URL": f"http://127.0.0.1:{self.server.server_port}",
                "CLAUDE_PLUGIN_OPTION_API_KEY": "reqlo_test_key",
                "CLAUDE_PLUGIN_OPTION_WORKSPACE_ID": WORKSPACE,
            }
        )
        env.pop("CLAUDE_PLUGIN_DATA", None)
        return env

    def command(self, *args: str) -> list[str]:
        return [NODE or "node", str(CLAUDE_HOOK), *args]

    def enqueue(self, text: str, session: str = "session-1") -> subprocess.CompletedProcess[str]:
        payload = json.dumps(
            {
                "hook_event_name": "UserPromptSubmit",
                "session_id": session,
                "prompt_id": "prompt-1",
                "prompt": text,
            }
        )
        return self.run(stdin=payload)

    def drain(self) -> subprocess.CompletedProcess[str]:
        return self.run("--drain")

    def switch_off(self) -> subprocess.CompletedProcess[str]:
        listen = TEMPLATES / "claude-plugin" / "scripts" / "listen.mjs"
        return subprocess.run(
            [NODE or "node", str(listen), "off"],
            capture_output=True,
            text=True,
            env=self.env(),
            timeout=60,
        )


class HermesAdapter(Adapter):
    name = "hermes"
    client = "hermes"

    def env(self) -> dict[str, str]:
        env = super().env()
        env.update(
            {
                "PYTHONPATH": str(HERMES_DIR),
                # No real registry: an install with a configured active server
                # would otherwise redirect the request away from the stub.
                "HERMES_HOME": str(self.tmp_path / "hermes-home"),
                # The contract names MCP_URL; BASE_URL is only the legacy alias.
                # Setting MCP_URL explicitly also overrides a value inherited
                # from the agent's own environment.
                "REQOGNILOOM_MCP_URL": f"http://127.0.0.1:{self.server.server_port}",
                "REQOGNILOOM_API_KEY": "reqlo_test_key",
            }
        )
        return env

    def command(self, *args: str) -> list[str]:
        return [PYTHON, str(HERMES_RELAY), *args]

    def enqueue(self, text: str, session: str = "session-1") -> subprocess.CompletedProcess[str]:
        payload_file = self.tmp_path / "hermes-payload.json"
        payload_file.write_text(
            json.dumps(
                {
                    "text": text,
                    "workspace_id": WORKSPACE,
                    "client": self.client,
                    "source_session": session,
                    "message_id": "prompt-1",
                }
            ),
            encoding="utf-8",
        )
        return self.run("--enqueue", str(payload_file))

    def drain(self) -> subprocess.CompletedProcess[str]:
        return self.run("--drain")

    def switch_off(self) -> subprocess.CompletedProcess[str]:
        return self.run("--off")


class OpenCodeAdapter(Adapter):
    name = "opencode"
    client = "opencode"
    requires = "node"

    def env(self) -> dict[str, str]:
        env = super().env()
        env.update(
            {
                "REQOGNILOOM_MCP_URL": f"http://127.0.0.1:{self.server.server_port}",
                "REQOGNILOOM_API_KEY": "reqlo_test_key",
            }
        )
        return env

    def command(self, *args: str) -> list[str]:
        return [NODE or "node", str(OPENCODE_RELAY), *args]

    def enqueue(self, text: str, session: str = "session-1") -> subprocess.CompletedProcess[str]:
        return self.run(
            "enqueue",
            stdin=json.dumps({"text": text, "sessionId": session, "messageId": "prompt-1"}),
        )

    def drain(self) -> subprocess.CompletedProcess[str]:
        return self.run("--drain")

    def switch_off(self) -> subprocess.CompletedProcess[str]:
        return self.run("off")


class AntigravityAdapter(Adapter):
    name = "antigravity"
    client = "antigravity"

    def env(self) -> dict[str, str]:
        env = super().env()
        env.update(
            {
                "REQOGNILOOM_MCP_URL": f"http://127.0.0.1:{self.server.server_port}",
                "REQOGNILOOM_API_KEY": "reqlo_test_key",
            }
        )
        return env

    def command(self, *args: str) -> list[str]:
        return [PYTHON, str(ANTIGRAVITY_RELAY), *args]

    def enqueue(self, text: str, session: str = "session-1") -> subprocess.CompletedProcess[str]:
        return self.run("enqueue", stdin=json.dumps({"text": text, "sessionId": session}))

    def drain(self) -> subprocess.CompletedProcess[str]:
        return self.run("--drain")

    def switch_off(self) -> subprocess.CompletedProcess[str]:
        return self.run("off")


ADAPTERS = [ClaudeAdapter, HermesAdapter, OpenCodeAdapter, AntigravityAdapter]


def _adapter_class(request) -> type[Adapter]:
    cls = request.param
    if cls.requires == "node" and NODE is None:
        pytest.skip(f"{cls.name}: node is not installed — adapter not executed, not counted green")
    return cls


@pytest.fixture(params=ADAPTERS, ids=[cls.name for cls in ADAPTERS])
def adapter(request, tmp_path, stub_server):
    cls = _adapter_class(request)
    return cls(tmp_path, stub_server)


def test_a_default_off_sends_nothing(adapter, stub_server):
    result = adapter.enqueue(VALID_PROMPT)
    assert result.returncode == 0
    assert result.stdout == ""
    assert adapter.drain().returncode == 0
    assert stub_server.requests == []
    assert adapter.queue() == []


def test_b_short_and_slash_are_filtered(adapter, stub_server):
    adapter.write_switch(True)
    assert adapter.enqueue(SHORT_PROMPT).returncode == 0
    assert adapter.enqueue(COMMAND_PROMPT).returncode == 0
    assert adapter.drain().returncode == 0
    assert stub_server.requests == []
    assert adapter.queue() == []


def test_c_valid_message_posts_the_identical_contract(adapter, stub_server):
    adapter.write_switch(True)
    result = adapter.enqueue(VALID_PROMPT)
    assert result.returncode == 0
    assert result.stdout == ""
    assert stub_server.requests == [], "the hook must not send inline"
    assert adapter.drain().returncode == 0

    assert len(stub_server.requests) == 1
    request = stub_server.requests[0]
    assert request["path"] == "/api/v1/suggestions/capture/"
    body = request["json"]
    assert body["workspace_id"] == WORKSPACE
    assert body["text"] == VALID_PROMPT
    assert body["client"] == adapter.client
    assert len(body["idempotency_key"]) == 64
    assert body["source_session"] == "session-1"
    headers = {key.lower(): value for key, value in request["headers"].items()}
    assert headers.get("x-api-key") == "reqlo_test_key"
    assert "reqlo_test_key" not in json.dumps(body)

    status = adapter.status()
    assert status["captured"] == 1
    assert status["failed"] == 0
    assert status["queued"] == 0
    assert status["last_success_at"]
    assert status["last_error"] is None


def test_d_server_error_keeps_the_entry_for_the_next_run(adapter, stub_server):
    adapter.write_switch(True)
    stub_server.responses = [(500, {"error": {"code": "INTERNAL"}})]
    assert adapter.enqueue(VALID_PROMPT).returncode == 0
    assert adapter.drain().returncode == 0

    queued = adapter.queue()
    assert len(queued) == 1
    assert queued[0]["text"] == VALID_PROMPT
    assert queued[0]["attempts"] == 1
    status = adapter.status()
    assert status["last_error"].startswith("HTTP 500")
    for name in ("capture.log", "listen-status.json"):
        raw = (adapter.state_dir / name).read_text(encoding="utf-8")
        assert VALID_PROMPT not in raw
        assert "reqlo_test_key" not in raw

    assert adapter.enqueue(VALID_PROMPT).returncode == 0
    assert adapter.drain().returncode == 0
    assert adapter.queue() == []
    assert adapter.status()["last_error"] is None


def test_e_permanent_and_auth_statuses(adapter, stub_server):
    adapter.write_switch(True)

    for status_code, body in (
        (400, {"error": {"code": "TEXT_TOO_LONG"}}),
        (409, {"error": {"code": "DUPLICATE"}}),
    ):
        stub_server.responses = [(status_code, body)]
        assert adapter.enqueue(VALID_PROMPT, session=f"session-{status_code}").returncode == 0
        assert adapter.drain().returncode == 0
        assert adapter.queue() == [], f"HTTP {status_code} must be terminal"

    stub_server.responses = [(401, {"error": {"code": "UNAUTHORIZED"}})]
    assert adapter.enqueue(VALID_PROMPT, session="session-401").returncode == 0
    assert adapter.drain().returncode == 0
    queued = adapter.queue()
    assert len(queued) == 1
    assert queued[0]["attempts"] == 1


def test_f_off_stops_and_deletes_unsent(adapter, stub_server):
    adapter.write_switch(True)
    assert adapter.enqueue(VALID_PROMPT).returncode == 0
    assert len(adapter.queue()) == 1

    off = adapter.switch_off()
    assert off.returncode == 0
    assert "OFF" in off.stdout
    assert adapter.queue() == []
    assert not (adapter.state_dir / "capture-incoming").exists()

    assert adapter.enqueue(VALID_PROMPT).returncode == 0
    assert adapter.drain().returncode == 0
    assert stub_server.requests == []
    assert adapter.queue() == []


def test_g_no_stdout_and_no_stderr(adapter, stub_server):
    adapter.write_switch(True)
    stub_server.responses = [(503, {"error": {"code": "LLM_UNAVAILABLE"}})]
    result = adapter.enqueue(VALID_PROMPT)
    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""
    assert adapter.drain().stderr == ""


@pytest.mark.skipif(NODE is None, reason="node is required to import the OpenCode plugin")
def test_opencode_v1_and_v2_hooks_use_the_same_relay(tmp_path, stub_server):
    """The two OpenCode entry points must call the same core (same request)."""
    harness = tmp_path / "harness.mjs"
    harness.write_text(
        (
            "import { ReqogniLoomPlugin } from "
            f"{json.dumps(str(OPENCODE_RELAY.parent / 'index.js'))};\n"
            "const event = process.argv[2];\n"
            "if (event === 'v1') {\n"
            "  const hooks = await ReqogniLoomPlugin();\n"
            "  await hooks['chat.message']({ sessionID: 'session-v1' },"
            " { message: { id: 'm1', parts: [{ type: 'text', text: process.env.TEXT }] } });\n"
            "} else {\n"
            "  const plugin = (await import("
            f"{json.dumps(str(OPENCODE_RELAY.parent / 'index.js'))})).default;\n"
            "  let handler;\n"
            "  await plugin.setup({ session: { hook: async (name, fn) => { handler = fn; } } });\n"
            "  await handler({ prompt: { text: process.env.TEXT },"
            " session: { id: 'session-v2' }, message: { id: 'm2' } });\n"
            "}\n"
        ),
        encoding="utf-8",
    )

    for event, session in (("v1", "session-v1"), ("v2", "session-v2")):
        state = tmp_path / f"listen-{event}"
        state.mkdir()
        (state / "listen.json").write_text(
            json.dumps({"enabled": True, "workspace_id": WORKSPACE, "client": "opencode"}),
            encoding="utf-8",
        )
        env = os.environ.copy()
        env.update(
            {
                "TEXT": VALID_PROMPT,
                "REQNILOOM_LISTEN_DIR": str(state),
                "REQOGNILOOM_MCP_URL": f"http://127.0.0.1:{stub_server.server_port}",
                "REQOGNILOOM_API_KEY": "reqlo_test_key",
            }
        )
        subprocess.run([NODE, str(harness), event], env=env, capture_output=True, text=True, timeout=60)
        subprocess.run(
            [NODE, str(OPENCODE_RELAY), "--drain"],
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert stub_server.requests[-1]["json"]["source_session"] == session
        assert stub_server.requests[-1]["json"]["client"] == "opencode"
    assert len(stub_server.requests) == 2
