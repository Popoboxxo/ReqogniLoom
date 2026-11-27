#!/usr/bin/env node
/**
 * ReqogniLoom listen-mode relay for the Claude Code `UserPromptSubmit` hook.
 *
 * Two modes, one script:
 *
 *   (no argument)  the hook. Reads the payload from stdin, checks the local
 *                  switch and the noise filter, appends the message to the
 *                  write-ahead queue under the queue lock and starts a detached
 *                  worker. It performs **no network work**, so a turn that is
 *                  torn down (`claude -p` exit) can only cost the spawn, never
 *                  the message or a half-finished request.
 *
 *   --drain        the worker. Takes the queue lock, merges the incoming
 *                  segments, delivers up to MAX_FLUSH_PER_RUN entries, writes
 *                  `listen-status.json` and releases the lock. It is detached
 *                  (own process group, stdio ignored), so it survives the hook.
 *                  Whoever cannot get the lock exits quietly — the next drain
 *                  picks the entries up.
 *
 * Why a write-ahead queue: AP0 proved that `async: true` keeps the user's turn
 * fast but the hook process is killed when `claude -p` exits, so "sent" is not
 * "delivered". The hook therefore only writes; delivery happens in the worker,
 * and a failed send stays queued for the next drain.
 *
 * Failure policy: exit code 2 from a hook blocks the user's prompt, so this
 * script never propagates an error. Diagnostics go to `capture.log` and never
 * contain the message text.
 *
 * Test seam: `CLAUDE_PLUGIN_LISTEN_NO_WORKER=1` suppresses the detached spawn so
 * a suite can drain deterministically. It is never set in production.
 */
import { spawn } from "node:child_process";
import { createHash } from "node:crypto";
import {
  appendFileSync,
  chmodSync,
  existsSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  renameSync,
  rmSync,
  statSync,
  unlinkSync,
  writeFileSync,
} from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const SCRIPT_PATH = fileURLToPath(import.meta.url);

const MIN_TEXT_LENGTH = 40;
const MAX_LINES = 300;
const MAX_FLUSH_PER_RUN = 5;
// The worker's per-request timeout must outlast a real server-side LLM call
// (live: the capture suggestion appeared, but a 15 s client timeout made the
// worker treat the successful POST as failed and retry it; the retry then hit
// the idempotency duplicate). 60 s is below DRAIN_BUDGET_MS and still bounded;
// REQNILOOM_CAPTURE_TIMEOUT_MS exists for tests and unusual providers.
const REQUEST_TIMEOUT_MS = (() => {
  const raw = Number(process.env.REQNILOOM_CAPTURE_TIMEOUT_MS || "");
  return Number.isFinite(raw) && raw >= 1000 ? Math.min(raw, 110_000) : 60_000;
})();
// The hook no longer waits for a request, so only the worker needs a budget: it
// caps one drain so a wedged server cannot keep a detached process alive.
const DRAIN_BUDGET_MS = 120_000;
const LOCK_STALE_MS = 5 * 60 * 1000;
const CLIENT_NAME = "claude-code";
const MAX_FIELD_LENGTH = 255;
const MAX_LOG_BYTES = 1_000_000;
const MAX_IDEMPOTENCY_LENGTH = 128;
const MAX_ATTEMPTS = 5;
const MAX_QUEUE_ENTRIES = 100;
const MAX_ENTRY_AGE_MS = 7 * 24 * 60 * 60 * 1000;

function secureDir(dir) {
  try {
    chmodSync(dir, 0o700);
  } catch {
    // Windows/ACL filesystems may reject POSIX modes; the write still works.
  }
}

function secureFile(path) {
  try {
    chmodSync(path, 0o600);
  } catch {
    // Same as secureDir: best effort, never a reason to fail the hook.
  }
}

/**
 * State directory shared by the hook, the worker and `/reqogniloom:listen`.
 *
 * `CLAUDE_PLUGIN_DATA` is deliberately NOT used: the plugin command runs in a
 * shell where Claude Code sets only `${CLAUDE_PLUGIN_ROOT}`, so the variable is
 * absent there. Resolving it per process made `listen on` write one directory
 * while the hook read another — the switch then appeared OFF in a live session
 * and capture never fired. Both sides therefore resolve the same stable path,
 * and `REQNILOOM_LISTEN_DIR` is the only override (tests, diagnostics).
 */
function stateDir() {
  const configured = (process.env.REQNILOOM_LISTEN_DIR || "").trim();
  if (configured) return configured;
  return join(homedir(), ".reqogniloom", "listen");
}

function captureConfig() {
  return {
    mcpUrl: (process.env.CLAUDE_PLUGIN_OPTION_MCP_URL || "").trim(),
    apiKey: (process.env.CLAUDE_PLUGIN_OPTION_API_KEY || "").trim(),
    workspaceId: (process.env.CLAUDE_PLUGIN_OPTION_WORKSPACE_ID || "").trim(),
  };
}

function readJson(path, fallback) {
  try {
    return JSON.parse(readFileSync(path, "utf8"));
  } catch {
    return fallback;
  }
}

function writeJsonAtomic(path, value) {
  // Unique suffix: the missing-config branch writes status before the lock,
  // so two runs could otherwise share one `.tmp` and interleave.
  const tmp = `${path}.${process.pid}.tmp`;
  writeFileSync(tmp, `${JSON.stringify(value, null, 2)}\n`, {
    encoding: "utf8",
    mode: 0o600,
  });
  renameSync(tmp, path);
  secureFile(path);
}

function readStdin() {
  return new Promise((resolve) => {
    let data = "";
    // A hook always receives a payload on stdin. A manual run without one would
    // otherwise wait forever, so an interactive TTY means "no input".
    if (process.stdin.isTTY) {
      resolve("");
      return;
    }
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", (chunk) => {
      data += chunk;
    });
    process.stdin.on("end", () => resolve(data));
    process.stdin.on("error", () => resolve(data));
  });
}

function parseInput(raw) {
  try {
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

function normalizeText(value) {
  return String(value ?? "")
    .replace(/\r\n/g, "\n")
    .trim();
}

function passesFilter(text) {
  if (text.length < MIN_TEXT_LENGTH) return false;
  // Local slash commands do not fire the hook (AP0), but expanding commands
  // (`/loop`), shell echoes and prompt-injected instructions do arrive as
  // prompt text. `!` / `$` are shell prefixes, `/` is a command.
  if (/^[/!$]/.test(text)) return false;
  // A pasted log or file is not a requirement statement.
  if (text.split("\n").length > MAX_LINES) return false;
  return true;
}

function idempotencyKey(workspaceId, text) {
  return createHash("sha256")
    .update(`${workspaceId}\n${text}`, "utf8")
    .digest("hex")
    .slice(0, MAX_IDEMPOTENCY_LENGTH);
}

function buildEntry(input, config) {
  const text = normalizeText(input.prompt);
  if (!passesFilter(text)) return null;
  const truncate = (value) => String(value ?? "").slice(0, MAX_FIELD_LENGTH);
  return {
    workspace_id: config.workspaceId,
    text,
    client: CLIENT_NAME,
    source_session: truncate(input.session_id),
    message_id: truncate(input.prompt_id),
    idempotency_key: idempotencyKey(config.workspaceId, text),
    created_at: new Date().toISOString(),
    attempts: 0,
    last_attempt_at: null,
  };
}

function queuePath(dir) {
  return join(dir, "capture-queue.jsonl");
}

function readQueue(dir) {
  const path = queuePath(dir);
  if (!existsSync(path)) return [];
  const entries = [];
  for (const line of readFileSync(path, "utf8").split("\n")) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    try {
      const entry = JSON.parse(trimmed);
      if (entry && typeof entry === "object" && entry.text) entries.push(entry);
    } catch {
      // A torn line from a killed write is dropped, not retried forever.
    }
  }
  return entries;
}

function rewriteQueue(dir, entries) {
  const path = queuePath(dir);
  const tmp = `${path}.${process.pid}.tmp`;
  const body = entries.map((entry) => JSON.stringify(entry)).join("\n");
  writeFileSync(tmp, body ? `${body}\n` : "", { encoding: "utf8", mode: 0o600 });
  renameSync(tmp, path);
  secureFile(path);
}

function appendQueue(dir, entry) {
  // The queue holds message text: keep it owner-only.
  appendFileSync(queuePath(dir), `${JSON.stringify(entry)}\n`, {
    encoding: "utf8",
    mode: 0o600,
  });
  secureFile(queuePath(dir));
}

function capQueue(dir, entries) {
  if (entries.length <= MAX_QUEUE_ENTRIES) return entries;
  const dropped = entries.length - MAX_QUEUE_ENTRIES;
  log(dir, `queue capped: dropped ${dropped} oldest capture(s)`);
  return entries.slice(dropped);
}

function acquireLock(dir) {
  const lock = join(dir, "capture-queue.lock");
  for (let attempt = 0; attempt < 2; attempt += 1) {
    try {
      mkdirSync(lock);
      return () => {
        try {
          rmSync(lock, { recursive: true, force: true });
        } catch {
          // Best effort; a stale lock is reclaimed on the next run.
        }
      };
    } catch (error) {
      if (error?.code !== "EEXIST") return null;
      let age = 0;
      try {
        age = Date.now() - statSync(lock).mtimeMs;
      } catch {
        age = 0;
      }
      if (age <= LOCK_STALE_MS) return null;
      // Rename-based reclaim: two contenders may both see the stale lock, but
      // only one rename succeeds, so only one of them can acquire afterwards.
      const stale = `${lock}.stale-${process.pid}-${Date.now()}`;
      try {
        renameSync(lock, stale);
        rmSync(stale, { recursive: true, force: true });
      } catch {
        return null;
      }
    }
  }
  return null;
}

function log(dir, message) {
  try {
    const path = join(dir, "capture.log");
    if (existsSync(path) && statSync(path).size > MAX_LOG_BYTES) {
      renameSync(path, `${path}.1`);
    }
    const stamp = new Date().toISOString();
    // Callers pass codes and counts only — never the message text or the key.
    appendFileSync(path, `${stamp} ${message}\n`, { encoding: "utf8", mode: 0o600 });
    secureFile(path);
  } catch {
    // A log failure must never be the reason a capture breaks.
  }
}

function bodyFor(entry) {
  const body = {
    workspace_id: entry.workspace_id,
    text: entry.text,
    client: entry.client,
    idempotency_key: entry.idempotency_key,
  };
  if (entry.source_session) body.source_session = entry.source_session;
  if (entry.message_id) body.message_id = entry.message_id;
  return body;
}

async function deliver(config, entry, deadline) {
  const base = config.mcpUrl.replace(/\/+$/, "");
  const url = `${base}/api/v1/suggestions/capture/`;
  const remaining = Math.max(1, Math.min(REQUEST_TIMEOUT_MS, deadline - Date.now()));
  if (deadline <= Date.now()) {
    return { done: false, detail: "budget_exhausted" };
  }
  try {
    const response = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-API-Key": config.apiKey,
      },
      body: JSON.stringify(bodyFor(entry)),
      // Never follow a redirect: a 3xx could forward the API key to another host.
      redirect: "error",
      signal: AbortSignal.timeout(remaining),
    });
    let payload = {};
    try {
      payload = await response.json();
    } catch {
      payload = {};
    }
    const code = String(payload?.error?.code || "").slice(0, 80);
    if (response.status >= 200 && response.status < 300) {
      return { done: true, detail: `HTTP ${response.status}` };
    }
    if (response.status === 409 && (code === "CAPTURE_DISABLED" || code === "DUPLICATE")) {
      // Both mean "do not resend": the switch is off (the user turned it off
      // after this message was queued) or the message already landed.
      return { done: true, detail: code };
    }
    if (response.status === 400) {
      // Permanent request defect (TEXT_TOO_LONG, VALIDATION_ERROR). Retrying
      // can never succeed and would grow the queue forever.
      return { done: true, detail: code || `HTTP ${response.status}` };
    }
    return {
      done: false,
      detail: `HTTP ${response.status}${code ? `:${code.slice(0, 40)}` : ""}`,
    };
  } catch (error) {
    const name = error?.name || "Error";
    const detail = name === "TimeoutError" || name === "AbortError" ? "timeout" : "network_error";
    return { done: false, detail };
  }
}

function recordSuccess(state) {
  state.captured = (state.captured || 0) + 1;
  state.last_success_at = new Date().toISOString();
  // A recovered failure is not the "last error" any more; leaving a stale
  // timeout in the status made a healthy relay look broken.
  state.last_error = null;
  state.last_error_at = null;
}

function recordFailure(state, detail) {
  state.failed = (state.failed || 0) + 1;
  state.last_error = String(detail || "error").slice(0, 120);
  state.last_error_at = new Date().toISOString();
}

async function flushQueue(dir, config, state, deadline) {
  const entries = readQueue(dir);
  if (entries.length === 0) return 0;

  const now = Date.now();
  // Pick the sendable head first. A foreign-workspace or retry-exhausted entry
  // must not block later entries behind it (head-of-line blocking).
  const candidates = [];
  for (const entry of entries) {
    if (entry.workspace_id !== config.workspaceId) continue;
    const created = Date.parse(entry.created_at || "");
    if (Number.isFinite(created) && now - created > MAX_ENTRY_AGE_MS) continue;
    if ((entry.attempts || 0) >= MAX_ATTEMPTS) continue;
    candidates.push(entry);
    if (candidates.length === MAX_FLUSH_PER_RUN) break;
  }
  const selected = new Set(candidates);
  const keep = [];
  let sent = 0;
  let changed = false;
  let expired = 0;

  for (const entry of entries) {
    const created = Date.parse(entry.created_at || "");
    if (Number.isFinite(created) && now - created > MAX_ENTRY_AGE_MS) {
      expired += 1;
      changed = true;
      continue;
    }
    if ((entry.attempts || 0) >= MAX_ATTEMPTS) {
      expired += 1;
      changed = true;
      continue;
    }
    if (!selected.has(entry)) {
      keep.push(entry);
      continue;
    }
    if (Date.now() >= deadline) {
      // Out of budget: leave the entry untouched so the next prompt retries it
      // without burning an attempt.
      keep.push(entry);
      continue;
    }
    const outcome = await deliver(config, entry, deadline);
    if (outcome.done) {
      recordSuccess(state);
      sent += 1;
    } else {
      recordFailure(state, outcome.detail);
      // Detail only: status code / error code, never the message text.
      log(dir, `capture failed: ${outcome.detail}`);
      keep.push({
        ...entry,
        attempts: (entry.attempts || 0) + 1,
        last_attempt_at: new Date().toISOString(),
      });
    }
    changed = true;
  }

  if (expired > 0) log(dir, `queue dropped ${expired} expired/exhausted capture(s)`);
  if (changed) rewriteQueue(dir, keep);
  return sent;
}

function appendCapped(dir, entry) {
  appendQueue(dir, entry);
  const entries = readQueue(dir);
  if (entries.length > MAX_QUEUE_ENTRIES) {
    rewriteQueue(dir, capQueue(dir, entries));
  }
}

function incomingDir(dir) {
  return join(dir, "capture-incoming");
}

function writeIncoming(dir, entry) {
  // A hook that loses the lock must never rewrite the shared queue: the lock
  // holder may be rewriting it from an older snapshot. Each message gets its
  // own immutable file instead, and the next lock holder merges it.
  const pending = incomingDir(dir);
  mkdirSync(pending, { recursive: true, mode: 0o700 });
  secureDir(pending);
  const name = `${Date.now()}-${process.pid}-${Math.random()
    .toString(36)
    .slice(2)}.json`;
  const path = join(pending, name);
  writeFileSync(path, JSON.stringify(entry), { encoding: "utf8", mode: 0o600 });
  secureFile(path);
}

function mergeIncoming(dir) {
  const pending = incomingDir(dir);
  if (!existsSync(pending)) return 0;
  let names = [];
  try {
    names = readdirSync(pending);
  } catch {
    return 0;
  }
  const entries = [];
  for (const name of names) {
    if (!name.endsWith(".json")) continue;
    const path = join(pending, name);
    try {
      const entry = JSON.parse(readFileSync(path, "utf8"));
      if (entry && typeof entry === "object" && entry.text) entries.push(entry);
    } catch {
      // Torn write from a killed process: dropped like a torn queue line.
    }
    try {
      unlinkSync(path);
    } catch {
      // Already gone; nothing to merge twice.
    }
  }
  if (entries.length === 0) return 0;
  rewriteQueue(dir, capQueue(dir, [...readQueue(dir), ...entries]));
  return entries.length;
}

function initialStatus() {
  return {
    last_success_at: null,
    last_error: null,
    last_error_at: null,
    captured: 0,
    failed: 0,
    queued: 0,
  };
}

function missingConfig(config) {
  const missing = [];
  if (!config.workspaceId) missing.push("workspace_id");
  if (!config.mcpUrl) missing.push("mcp_url");
  if (!config.apiKey) missing.push("api_key");
  return missing;
}

function reportMissingConfig(dir, statusPath, state, missing) {
  recordFailure(state, `missing_config:${missing.join(",")}`);
  state.queued = readQueue(dir).length;
  writeJsonAtomic(statusPath, state);
  log(dir, `capture skipped: missing config ${missing.join(",")}`);
}

function spawnWorker(dir) {
  if (process.env.CLAUDE_PLUGIN_LISTEN_NO_WORKER === "1") return;
  try {
    const child = spawn(process.execPath, [SCRIPT_PATH, "--drain"], {
      // Detached + own process group + ignored stdio: the worker must outlive
      // the hook process, which `claude -p` kills as soon as the turn ends.
      detached: true,
      stdio: "ignore",
      env: process.env,
      cwd: dir,
    });
    child.unref();
  } catch (error) {
    // Losing the worker spawn only delays delivery; the entry is already queued.
    log(dir, `drain spawn failed: ${error?.name || "Error"}`);
  }
}

async function runHook() {
  const dir = stateDir();
  mkdirSync(dir, { recursive: true, mode: 0o700 });
  secureDir(dir);
  const input = parseInput(await readStdin());
  const listen = readJson(join(dir, "listen.json"), {});

  if (!listen || listen.enabled !== true) {
    // Default off: no request, no queue write, no worker.
    return;
  }

  const config = captureConfig();
  const statusPath = join(dir, "listen-status.json");
  const missing = missingConfig(config);
  if (missing.length > 0) {
    // Nothing can be delivered without a target: report it the way the old
    // in-hook path did, but still without touching the network.
    reportMissingConfig(
      dir,
      statusPath,
      { ...initialStatus(), ...readJson(statusPath, {}) },
      missing,
    );
    return;
  }

  const entry = buildEntry(input, config);
  const release = acquireLock(dir);
  if (!release) {
    // A run already owns the queue. Persisting the message anyway is the whole
    // point of the write-ahead queue: losing it here would silently drop a
    // prompt just because another hook process was still draining.
    if (entry) {
      writeIncoming(dir, entry);
      log(dir, "capture queued: queue lock held");
    }
  } else {
    try {
      if (entry) appendCapped(dir, entry);
    } finally {
      release();
    }
  }

  // Hand delivery to a process the turn teardown cannot reach. The hook itself
  // never awaits a response, so it stays fast and cannot be killed mid-send.
  spawnWorker(dir);
}

async function runDrain() {
  const dir = stateDir();
  mkdirSync(dir, { recursive: true, mode: 0o700 });
  secureDir(dir);
  // Detached worker: no stdin payload, no user waiting on the exit code.
  const listen = readJson(join(dir, "listen.json"), {});
  if (!listen || listen.enabled !== true) {
    // Switched off after the message was queued: never send it.
    return;
  }

  const config = captureConfig();
  const statusPath = join(dir, "listen-status.json");
  const state = { ...initialStatus(), ...readJson(statusPath, {}) };
  const missing = missingConfig(config);
  if (missing.length > 0) {
    reportMissingConfig(dir, statusPath, state, missing);
    return;
  }

  const release = acquireLock(dir);
  if (!release) {
    // Another worker (or a hook) owns the queue and will deliver. Exiting
    // quietly leaves the entries intact instead of racing a queue rewrite.
    log(dir, "drain skipped: queue lock held");
    return;
  }

  try {
    const merged = mergeIncoming(dir);
    if (merged > 0) log(dir, `merged ${merged} queued capture(s)`);
    // Drain what this or an earlier run queued. A failed send stays queued.
    const deadline = Date.now() + DRAIN_BUDGET_MS;
    const flushed = await flushQueue(dir, config, state, deadline);
    if (flushed > 0) log(dir, `flushed ${flushed} queued capture(s)`);

    state.queued = readQueue(dir).length;
    writeJsonAtomic(statusPath, state);
  } finally {
    release();
  }
}

const isDrain = process.argv.slice(2).includes("--drain");

(isDrain ? runDrain() : runHook())
  .catch((error) => {
    // Never let a relay defect escape as a non-zero exit (exit 2 blocks the
    // prompt). Diagnostics stay in the log, without message content.
    try {
      log(stateDir(), `capture ${isDrain ? "drain" : "hook"} error: ${error?.name || "Error"}`);
    } catch {
      // Nothing left to do; the relay is fail-open by contract.
    }
  })
  .finally(() => {
    process.exitCode = 0;
    process.exit(0);
  });
