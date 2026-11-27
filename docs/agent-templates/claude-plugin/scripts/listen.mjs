#!/usr/bin/env node
/**
 * ReqogniLoom listen-mode switch for the Claude Code plugin.
 *
 * `/reqogniloom:listen on|off|status` runs this script (a command, not a hook),
 * so printing to stdout is the point. `on` prints the privacy notice: from then
 * on the text of every user message leaves this machine for the ReqogniLoom
 * server and its configured model.
 *
 * Reads the same local state as `capture-hook.mjs`:
 *   $CLAUDE_PLUGIN_DATA/listen.json          {"enabled": <bool>}
 *   $CLAUDE_PLUGIN_DATA/capture-queue.jsonl   write-ahead queue
 *   $CLAUDE_PLUGIN_DATA/listen-status.json    counters + last success/error
 */
import {
  chmodSync,
  existsSync,
  mkdirSync,
  readFileSync,
  renameSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const REQUEST_TIMEOUT_MS = 10_000;
const CAPTURE_PREFERENCE_KEY = "capture.enabled";

function stateDir() {
  const configured = process.env.CLAUDE_PLUGIN_DATA;
  return configured && configured.trim()
    ? configured.trim()
    : join(tmpdir(), "reqogniloom-plugin");
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
    "  off     disable it (already queued messages stay queued)",
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
    return 0;
  }

  if (action === "off") {
    writeJsonAtomic(listenPath, { ...readJson(listenPath, {}), enabled: false });
    console.log("Listen mode: OFF (local).");
    const queued = queueLength(dir);
    if (queued > 0) {
      console.log(
        `${queued} queued message(s) remain on disk and are not sent while the switch is off.`,
      );
    }
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
