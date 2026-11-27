#!/usr/bin/env node
/**
 * ReqogniLoom listen-mode switch for the Claude Code plugin.
 *
 * `/reqogniloom:listen on|off|status` runs this script (a command, not a hook),
 * so printing to stdout is the point. `on` prints the privacy notice: from then
 * on the text of every user message leaves this machine for the ReqogniLoom
 * server and its configured model.
 *
 * Reads the same local state as `capture-hook.mjs`, in the same directory:
 *   ~/.reqogniloom/listen/listen.json          {"enabled": <bool>}
 *   ~/.reqogniloom/listen/capture-queue.jsonl   write-ahead queue
 *   ~/.reqogniloom/listen/listen-status.json    counters + last success/error
 *   ~/.reqogniloom/listen/capture-incoming/     per-message segments (lock held)
 *
 * Why a stable path and not `CLAUDE_PLUGIN_DATA`: the command runs in a shell
 * where Claude Code sets only `${CLAUDE_PLUGIN_ROOT}`, so the variable is empty
 * there. Keying the state on it made `on` write one directory while the hook
 * read another — the switch read OFF in a running session and capture never
 * fired. `REQNILOOM_LISTEN_DIR` is the only override (tests, diagnostics).
 */
import {
  chmodSync,
  existsSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  renameSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

const REQUEST_TIMEOUT_MS = 10_000;
const CAPTURE_PREFERENCE_KEY = "capture.enabled";

/**
 * Mirrors `stateDir()` in capture-hook.mjs — the two must never diverge, or
 * `on`/`off` stop affecting the hook that actually captures.
 */
function stateDir() {
  const configured = (process.env.REQNILOOM_LISTEN_DIR || "").trim();
  if (configured) return configured;
  return join(homedir(), ".reqogniloom", "listen");
}

function readJson(path, fallback) {
  try {
    return JSON.parse(readFileSync(path, "utf8"));
  } catch {
    return fallback;
  }
}

function writeJsonAtomic(path, value) {
  const tmp = `${path}.${process.pid}.tmp`;
  writeFileSync(tmp, `${JSON.stringify(value, null, 2)}\n`, {
    encoding: "utf8",
    mode: 0o600,
  });
  renameSync(tmp, path);
  try {
    chmodSync(path, 0o600);
  } catch {
    // Best effort on filesystems without POSIX modes.
  }
}

function config() {
  return {
    mcpUrl: (process.env.CLAUDE_PLUGIN_OPTION_MCP_URL || "").trim(),
    apiKey: (process.env.CLAUDE_PLUGIN_OPTION_API_KEY || "").trim(),
    workspaceId: (process.env.CLAUDE_PLUGIN_OPTION_WORKSPACE_ID || "").trim(),
  };
}

function queueLength(dir) {
  const path = join(dir, "capture-queue.jsonl");
  if (!existsSync(path)) return 0;
  return readFileSync(path, "utf8")
    .split("\n")
    .filter((line) => line.trim()).length;
}

function pendingIncoming(dir) {
  const incoming = join(dir, "capture-incoming");
  try {
    if (!existsSync(incoming)) return 0;
    return readdirSync(incoming).filter((name) => name.endsWith(".json")).length;
  } catch {
    return 0;
  }
}

/**
 * Switching off is a privacy action, not a pause: nothing that has not been
 * sent is kept on disk afterwards. `listen-status.json` stays (it is a counter,
 * not content) but its queue figure is reset so `status` cannot claim unsent
 * messages that no longer exist.
 */
function clearPendingMessages(dir) {
  const removed = { queued: queueLength(dir), incoming: pendingIncoming(dir) };
  try {
    rmSync(join(dir, "capture-queue.jsonl"), { force: true });
  } catch {
    // Best effort; the switch is off either way and the next drain is a no-op.
  }
  try {
    rmSync(join(dir, "capture-incoming"), { recursive: true, force: true });
  } catch {
    // Same: a segment that survives one unlink is still never sent while off.
  }
  const statusPath = join(dir, "listen-status.json");
  const status = readJson(statusPath, null);
  if (status && typeof status === "object") {
    writeJsonAtomic(statusPath, { ...status, queued: 0 });
  }
  return removed;
}

async function serverSwitch(cfg) {
  if (!cfg.mcpUrl || !cfg.apiKey || !cfg.workspaceId) {
    return { ok: false, detail: "not configured (mcp_url, api_key or workspace_id missing)" };
  }
  const base = cfg.mcpUrl.replace(/\/+$/, "");
  const url =
    `${base}/api/v1/workspaces/${encodeURIComponent(cfg.workspaceId)}` +
    `/preference-values/effective/?keys=${encodeURIComponent(CAPTURE_PREFERENCE_KEY)}`;
  try {
    const response = await fetch(url, {
      headers: { Authorization: `Bearer ${cfg.apiKey}` },
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    });
    if (!response.ok) {
      return { ok: false, detail: `HTTP ${response.status}` };
    }
    const payload = await response.json();
    const entry = payload?.values?.[CAPTURE_PREFERENCE_KEY];
    if (!entry || typeof entry.value !== "boolean") {
      return { ok: true, enabled: false, source: "unknown" };
    }
    return { ok: true, enabled: entry.value, source: entry.source || "unknown" };
  } catch (error) {
    const name = error?.name || "Error";
    return { ok: false, detail: name === "TimeoutError" ? "timeout" : "network_error" };
  }
}

function usage() {
  return [
    "Usage: /reqogniloom:listen on|off|status",
    "",
    "  on      enable ambient capture on this machine",
    "  off     disable it and delete anything still queued (nothing unsent is kept)",
    "  status  show the local switch, the server switch, the queue and the last result",
  ].join("\n");
}

async function main(argv) {
  const dir = stateDir();
  mkdirSync(dir, { recursive: true, mode: 0o700 });
  try {
    chmodSync(dir, 0o700);
  } catch {
    // Best effort; the state still works on ACL-only filesystems.
  }
  const action = (argv[0] || "status").toLowerCase();
  const listenPath = join(dir, "listen.json");
  const cfg = config();

  if (action === "on") {
    writeJsonAtomic(listenPath, { ...readJson(listenPath, {}), enabled: true });
    console.log("Listen mode: ON (local).");
    console.log(
      "Privacy: from now on the text of your user messages is sent to the " +
        "configured ReqogniLoom server and processed by its model to propose " +
        "artifacts. Only user messages are captured — never assistant text or tool output.",
    );
    console.log(
      "Both switches must be on: the workspace setting `capture.enabled` is " +
        "server-side and stays off by default.",
    );
    if (!cfg.workspaceId) {
      console.log(
        "Warning: no workspace_id is configured for the plugin — capture stays " +
          "inactive until you set it (`claude plugin configure reqogniloom`).",
      );
    }
    console.log("Check both switches with: /reqogniloom:listen status");
    console.log("Takes effect on your next message in this session.");
    return 0;
  }

  if (action === "off") {
    writeJsonAtomic(listenPath, { ...readJson(listenPath, {}), enabled: false });
    console.log("Listen mode: OFF (local).");
    const removed = clearPendingMessages(dir);
    const deleted = removed.queued + removed.incoming;
    if (deleted > 0) {
      console.log(
        `${deleted} unsent message(s) were deleted: nothing that was not sent is kept after switching off.`,
      );
    }
    console.log("Takes effect on your next message in this session.");
    return 0;
  }

  if (action === "status") {
    const local = readJson(listenPath, {}).enabled === true;
    const status = readJson(join(dir, "listen-status.json"), {});
    console.log(`Local switch:  ${local ? "ON" : "OFF"}`);
    console.log(`Workspace:     ${cfg.workspaceId || "(not configured)"}`);

    const server = await serverSwitch(cfg);
    if (server.ok) {
      console.log(
        `Server switch: ${server.enabled ? "ON" : "OFF"} (source: ${server.source})`,
      );
      if (!local || !server.enabled) {
        console.log("Capture is inactive: both switches must be ON.");
      }
    } else {
      console.log(`Server switch: unknown (${server.detail})`);
    }

    console.log(`Queue:         ${queueLength(dir)} message(s)`);
    console.log(`Captured:      ${status.captured || 0}`);
    console.log(`Failed:        ${status.failed || 0}`);
    console.log(`Last success:  ${status.last_success_at || "—"}`);
    console.log(
      `Last error:    ${status.last_error || "—"}` +
        (status.last_error_at ? ` (${status.last_error_at})` : ""),
    );
    return 0;
  }

  console.log(usage());
  return 2;
}

main(process.argv.slice(2))
  .then((code) => {
    process.exitCode = code;
  })
  .catch((error) => {
    console.error(`listen: ${error?.name || "Error"}`);
    process.exitCode = 1;
  });
