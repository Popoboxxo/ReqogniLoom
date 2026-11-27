// ReqogniLoom listen-mode relay for OpenCode.
//
// One relay core, two entry points: the V1 `chat.message` hook and the V2
// `session.hook("prompt")` hook both call `handlePrompt`. The build copies this
// file into the npm package next to the plugin module, so the two hooks and the
// `on|off|status` command cannot drift apart.
//
// Contract: docs/clients/listen-mode-contract.md. The hook does no network
// work — it appends to the shared write-ahead queue and starts the drain
// without awaiting it, so the user's turn is never delayed. Default off.
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
import { createInterface } from "node:readline";

export const CLIENT_NAME = "opencode";
export const MIN_TEXT_LENGTH = 40;
export const MAX_LINES = 300;
export const REQUEST_TIMEOUT_MS = 60_000;
const MAX_FLUSH_PER_RUN = 5;
const MAX_ATTEMPTS = 5;
const MAX_QUEUE_ENTRIES = 100;
const MAX_ENTRY_AGE_MS = 7 * 24 * 60 * 60 * 1000;
const LOCK_STALE_MS = 5 * 60 * 1000;
const MAX_FIELD_LENGTH = 255;
const MAX_IDEMPOTENCY_LENGTH = 128;
const MAX_LOG_BYTES = 1_000_000;

const LISTEN_FILE = "listen.json";
const QUEUE_FILE = "capture-queue.jsonl";
const STATUS_FILE = "listen-status.json";
const INCOMING_DIR = "capture-incoming";
const LOCK_DIR = "capture-queue.lock";
const LOG_FILE = "capture.log";

function secureDir(dir) {
  try {
    chmodSync(dir, 0o700);
  } catch {
    // ACL-only filesystems reject POSIX modes; the write still works.
  }
}

function secureFile(path) {
  try {
    chmodSync(path, 0o600);
  } catch {
    // Same as secureDir.
  }
}

export function stateDir() {
  const configured = (process.env.REQNILOOM_LISTEN_DIR || "").trim();
  if (configured) return configured;
  return join(homedir(), ".reqogniloom", "listen");
}

function ensureDir() {
  const dir = stateDir();
  mkdirSync(dir, { recursive: true, mode: 0o700 });
  secureDir(dir);
  return dir;
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
  writeFileSync(tmp, `${JSON.stringify(value, null, 2)}\n`, { encoding: "utf8", mode: 0o600 });
  secureFile(tmp);
  renameSync(tmp, path);
  secureFile(path);
}

export function log(message) {
  try {
    const dir = ensureDir();
    const path = join(dir, LOG_FILE);
    if (existsSync(path) && statSync(path).size > MAX_LOG_BYTES) {
      renameSync(path, `${path}.1`);
    }
    appendFileSync(path, `${new Date().toISOString()} ${message}\n`, { encoding: "utf8", mode: 0o600 });
    secureFile(path);
  } catch {
    // A log failure must never be the reason a capture breaks.
  }
}

export function normalizeText(value) {
  return String(value ?? "").replace(/\r\n/g, "\n").trim();
}

export function passesFilter(text) {
  if (text.length < MIN_TEXT_LENGTH) return false;
  if (/^[/!$]/.test(text)) return false;
  if (text.split("\n").length > MAX_LINES) return false;
  return true;
}

export function idempotencyKey(workspaceId, text) {
  return createHash("sha256")
    .update(`${workspaceId}\n${text}`, "utf8")
    .digest("hex")
    .slice(0, MAX_IDEMPOTENCY_LENGTH);
}

export function buildEntry({ workspaceId, text, sourceSession = "", messageId = "" }) {
  const normalized = normalizeText(text);
  if (!passesFilter(normalized)) return null;
  const truncate = (value) => String(value ?? "").slice(0, MAX_FIELD_LENGTH);
  return {
    workspace_id: String(workspaceId || ""),
    text: normalized,
    client: CLIENT_NAME,
    source_session: truncate(sourceSession),
    message_id: truncate(messageId),
    idempotency_key: idempotencyKey(String(workspaceId || ""), normalized),
    created_at: new Date().toISOString(),
    attempts: 0,
    last_attempt_at: null,
  };
}

function queuePath(dir) {
  return join(dir, QUEUE_FILE);
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
  secureFile(tmp);
  renameSync(tmp, path);
  secureFile(path);
}

function appendQueue(dir, entry) {
  appendFileSync(queuePath(dir), `${JSON.stringify(entry)}\n`, { encoding: "utf8", mode: 0o600 });
  secureFile(queuePath(dir));
}

function capQueue(dir, entries) {
  if (entries.length <= MAX_QUEUE_ENTRIES) return entries;
  log(`queue capped: dropped ${entries.length - MAX_QUEUE_ENTRIES} oldest capture(s)`);
  return entries.slice(entries.length - MAX_QUEUE_ENTRIES);
}

function acquireLock(dir) {
  const lock = join(dir, LOCK_DIR);
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

function incomingDir(dir) {
  return join(dir, INCOMING_DIR);
}

function writeIncoming(dir, entry) {
  const pending = incomingDir(dir);
  mkdirSync(pending, { recursive: true, mode: 0o700 });
  secureDir(pending);
  const name = `${Date.now()}-${process.pid}-${Math.random().toString(36).slice(2)}.json`;
  writeFileSync(join(pending, name), JSON.stringify(entry), { encoding: "utf8", mode: 0o600 });
  secureFile(join(pending, name));
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
      // Torn write from a killed process.
    }
    try {
      unlinkSync(path);
    } catch {
      // Already gone.
    }
  }
  if (entries.length === 0) return 0;
  rewriteQueue(dir, capQueue(dir, [...readQueue(dir), ...entries]));
  return entries.length;
}

export function readSwitch() {
  const data = readJson(join(stateDir(), LISTEN_FILE), {});
  return data && typeof data === "object" ? data : {};
}

export function isEnabled(switchValue) {
  const data = switchValue === undefined ? readSwitch() : switchValue;
  return data?.enabled === true;
}

export function saveSwitch({ enabled, workspaceId }) {
  const dir = ensureDir();
  const current = readSwitch();
  const updated = { ...current, enabled: Boolean(enabled), client: CLIENT_NAME };
  if (workspaceId) updated.workspace_id = String(workspaceId);
  writeJsonAtomic(join(dir, LISTEN_FILE), updated);
  return updated;
}

export function enqueue({ workspaceId, text, sourceSession = "", messageId = "" }) {
  const entry = buildEntry({ workspaceId, text, sourceSession, messageId });
  if (!entry) return null;
  if (!isEnabled()) return null;
  const dir = ensureDir();
  try {
    const release = acquireLock(dir);
    if (release) {
      try {
        appendQueue(dir, entry);
        const entries = readQueue(dir);
        if (entries.length > MAX_QUEUE_ENTRIES) rewriteQueue(dir, capQueue(dir, entries));
      } finally {
        release();
      }
    } else {
      writeIncoming(dir, entry);
      log("capture queued: queue lock held");
    }
  } catch (error) {
    log(`capture enqueue failed: ${error?.name || "Error"}`);
    return null;
  }
  return entry;
}

export function initialStatus() {
  return {
    last_success_at: null,
    last_error: null,
    last_error_at: null,
    captured: 0,
    failed: 0,
    queued: 0,
  };
}

export function readStatus() {
  return { ...initialStatus(), ...readJson(join(stateDir(), STATUS_FILE), {}) };
}

function writeStatus(state) {
  writeJsonAtomic(join(ensureDir(), STATUS_FILE), state);
}

function recordSuccess(state) {
  state.captured = (state.captured || 0) + 1;
  state.last_success_at = new Date().toISOString();
  state.last_error = null;
  state.last_error_at = null;
}

function recordFailure(state, detail) {
  state.failed = (state.failed || 0) + 1;
  state.last_error = String(detail || "error").slice(0, 120);
  state.last_error_at = new Date().toISOString();
}

function captureConfig() {
  const base = (
    process.env.REQOGNILOOM_MCP_URL ||
    process.env.REQOGNILOOM_BASE_URL ||
    process.env.REQNILOOM_MCP_URL ||
    process.env.REQNILOOM_BASE_URL ||
    ""
  ).trim();
  return {
    baseUrl: base.replace(/\/+$/, ""),
    apiKey: (
      process.env.REQOGNILOOM_API_KEY ||
      process.env.REQNILOOM_API_KEY ||
      ""
    ).trim(),
  };
}

async function deliver(config, entry) {
  const url = `${config.baseUrl}/api/v1/suggestions/capture/`;
  const body = {
    workspace_id: entry.workspace_id,
    text: entry.text,
    client: entry.client || CLIENT_NAME,
    idempotency_key: entry.idempotency_key || idempotencyKey(entry.workspace_id, entry.text),
  };
  if (entry.source_session) body.source_session = entry.source_session;
  if (entry.message_id) body.message_id = entry.message_id;
  try {
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-API-Key": config.apiKey },
      body: JSON.stringify(body),
      redirect: "error",
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    });
    if (response.ok) return { done: true, detail: `HTTP ${response.status}` };
    if (response.status === 409 || response.status === 400) {
      return { done: true, detail: `HTTP ${response.status}` };
    }
    return { done: false, detail: `HTTP ${response.status}` };
  } catch (error) {
    const name = error?.name || "Error";
    return { done: false, detail: name === "TimeoutError" || name === "AbortError" ? "timeout" : "network_error" };
  }
}

export async function drain() {
  const switchValue = readSwitch();
  if (!isEnabled(switchValue)) return 0;
  const workspaceId = String(switchValue.workspace_id || "").trim();
  const dir = ensureDir();
  const state = readStatus();
  const config = captureConfig();

  const missing = [];
  if (!workspaceId) missing.push("workspace_id");
  if (!config.baseUrl) missing.push("mcp_url");
  if (!config.apiKey) missing.push("api_key");
  if (missing.length > 0) {
    recordFailure(state, `missing_config:${missing.join(",")}`);
    state.queued = readQueue(dir).length;
    writeStatus(state);
    log(`capture skipped: missing config ${missing.join(",")}`);
    return 0;
  }

  const release = acquireLock(dir);
  if (!release) {
    log("drain skipped: queue lock held");
    return 0;
  }
  try {
    const merged = mergeIncoming(dir);
    if (merged > 0) log(`merged ${merged} queued capture(s)`);

    const now = Date.now();
    const entries = readQueue(dir);
    const candidates = [];
    for (const entry of entries) {
      if (entry.workspace_id !== workspaceId) continue;
      const created = Date.parse(entry.created_at || "");
      if (Number.isFinite(created) && now - created > MAX_ENTRY_AGE_MS) continue;
      if ((entry.attempts || 0) >= MAX_ATTEMPTS) continue;
      candidates.push(entry);
      if (candidates.length === MAX_FLUSH_PER_RUN) break;
    }
    const selected = new Set(candidates);
    const keep = [];
    let sent = 0;
    for (const entry of entries) {
      if (!selected.has(entry)) {
        const created = Date.parse(entry.created_at || "");
        const expired = Number.isFinite(created) && now - created > MAX_ENTRY_AGE_MS;
        const exhausted = (entry.attempts || 0) >= MAX_ATTEMPTS;
        if (!expired && !exhausted) keep.push(entry);
        continue;
      }
      const outcome = await deliver(config, entry);
      if (outcome.done) {
        recordSuccess(state);
        sent += 1;
      } else {
        recordFailure(state, outcome.detail);
        log(`capture failed: ${outcome.detail}`);
        keep.push({ ...entry, attempts: (entry.attempts || 0) + 1, last_attempt_at: new Date().toISOString() });
      }
    }
    rewriteQueue(dir, keep);
    state.queued = keep.length;
    writeStatus(state);
    if (sent > 0) log(`flushed ${sent} queued capture(s)`);
    return sent;
  } finally {
    release();
  }
}

function textFromV1Message(message) {
  const parts = message?.parts || message?.content || [];
  if (typeof message?.text === "string") return message.text;
  if (!Array.isArray(parts)) return "";
  return parts
    .filter((part) => part && (part.type === "text" || part.type === undefined))
    .map((part) => part.text || "")
    .join("\n");
}

/**
 * The one capture entry point shared by V1 and V2.
 *
 * Returns immediately; delivery is dispatched and never awaited, so a slow or
 * dead server cannot delay the user's turn (G2). Fail-open: no throw escapes.
 */
export function handlePrompt(payload = {}) {
  try {
    const switchValue = readSwitch();
    if (!isEnabled(switchValue)) return null;
    const text = normalizeText(payload.text);
    if (!passesFilter(text)) return null;
    const workspaceId = String(switchValue.workspace_id || "").trim();
    if (!workspaceId) {
      log("capture skipped: no workspace_id configured");
      return null;
    }
    const entry = enqueue({
      workspaceId,
      text,
      sourceSession: payload.sessionId || payload.session_id || "",
      messageId: payload.messageId || payload.message_id || "",
    });
    // No `await`: the hook contract forbids blocking the turn.
    void drain().catch((error) => log(`drain spawn failed: ${error?.name || "Error"}`));
    return entry;
  } catch (error) {
    log(`capture hook error: ${error?.name || "Error"}`);
    return null;
  }
}

/** V1 `chat.message` hook. */
export async function v1ChatMessage(input, output) {
  const message = output?.message || input?.message || {};
  handlePrompt({
    text: textFromV1Message(message),
    sessionId: input?.sessionID || input?.sessionId || message.sessionID || "",
    messageId: message.id || input?.messageID || "",
  });
}

/** V2 `session.hook("prompt")` hook. */
export async function v2SessionPrompt(event) {
  handlePrompt({
    text: event?.prompt?.text ?? event?.text ?? "",
    sessionId: event?.session?.id ?? event?.sessionID ?? event?.session_id ?? "",
    messageId: event?.message?.id ?? event?.messageID ?? "",
  });
}

export function clearPending() {
  const dir = ensureDir();
  const removed = { queued: readQueue(dir).length, incoming: 0 };
  const pending = incomingDir(dir);
  if (existsSync(pending)) {
    try {
      removed.incoming = readdirSync(pending).filter((name) => name.endsWith(".json")).length;
      rmSync(pending, { recursive: true, force: true });
    } catch {
      // Best effort.
    }
  }
  try {
    rmSync(queuePath(dir), { force: true });
  } catch {
    // Best effort.
  }
  const status = readStatus();
  status.queued = 0;
  writeStatus(status);
  return removed;
}

function formatStatus(server) {
  const switchValue = readSwitch();
  const status = readStatus();
  const lines = [
    `Local switch:  ${isEnabled(switchValue) ? "ON" : "OFF"}`,
    `Workspace:     ${switchValue.workspace_id || "(not configured)"}`,
  ];
  if (server) lines.push(`Server switch: ${server}`);
  else lines.push("Server switch: unknown (not configured)");
  if (isEnabled(switchValue) && server !== "ON") {
    lines.push("Capture is inactive: both switches must be ON.");
  }
  lines.push(`Queue:         ${status.queued ?? 0} message(s)`);
  lines.push(`Captured:      ${status.captured || 0}`);
  lines.push(`Failed:        ${status.failed || 0}`);
  lines.push(`Last success:  ${status.last_success_at || "—"}`);
  lines.push(
    `Last error:    ${status.last_error || "—"}` + (status.last_error_at ? ` (${status.last_error_at})` : ""),
  );
  return lines.join("\n");
}

async function serverSwitch() {
  const switchValue = readSwitch();
  const config = captureConfig();
  if (!config.baseUrl || !config.apiKey || !switchValue.workspace_id) return "UNKNOWN";
  const url =
    `${config.baseUrl}/api/v1/workspaces/${encodeURIComponent(switchValue.workspace_id)}` +
    `/preference-values/effective/?keys=capture.enabled`;
  try {
    const response = await fetch(url, {
      headers: { Authorization: `Bearer ${config.apiKey}` },
      signal: AbortSignal.timeout(10_000),
    });
    if (!response.ok) return "UNKNOWN";
    const payload = await response.json();
    return payload?.values?.["capture.enabled"]?.value === true ? "ON" : "OFF";
  } catch {
    return "UNKNOWN";
  }
}

function usage() {
  return [
    "Usage: reqogniloom-listen on <workspace_id> | off | status",
    "",
    "  on       enable ambient capture (needs an explicit workspace_id)",
    "  off      disable it and delete anything still queued",
    "  status   show the local switch, the server switch, the queue and the last result",
  ].join("\n");
}

export async function main(argv) {
  const action = (argv[0] || "status").toLowerCase();
  ensureDir();
  if (action === "on") {
    const current = readSwitch();
    const workspaceId = argv[1] || current.workspace_id;
    if (!workspaceId) {
      console.log("Usage: reqogniloom-listen on <workspace_id> (the workspace must be explicit)");
      return 2;
    }
    saveSwitch({ enabled: true, workspaceId });
    console.log("Listen mode: ON (local).");
    console.log(
      "Privacy: from now on the text of your user messages is sent to the configured " +
        "ReqogniLoom server and processed by its model to propose artifacts. Only user " +
        "messages are captured — never assistant text or tool output.",
    );
    console.log("Both switches must be on: the server setting `capture.enabled` stays off by default.");
    return 0;
  }
  if (action === "off") {
    saveSwitch({ enabled: false, workspaceId: readSwitch().workspace_id });
    const removed = clearPending();
    console.log("Listen mode: OFF (local).");
    const deleted = removed.queued + removed.incoming;
    if (deleted > 0) {
      console.log(`${deleted} unsent message(s) were deleted: nothing that was not sent is kept.`);
    }
    return 0;
  }
  if (action === "status") {
    console.log(formatStatus(await serverSwitch()));
    return 0;
  }
  console.log(usage());
  return 2;
}

const invokedDirectly = process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1];

if (invokedDirectly) {
  const argv = process.argv.slice(2);
  if (argv.includes("--drain")) {
    drain().then(
      () => process.exit(0),
      (error) => {
        log(`drain failed unexpectedly: ${error?.name || "Error"}`);
        process.exit(1);
      },
    );
  } else if (argv[0] === "enqueue") {
    // Conformance/test seam: `{"text", "sessionId", "messageId", "workspaceId"}` on stdin.
    let raw = "";
    if (process.stdin.isTTY) {
      process.exit(2);
    }
    const reader = createInterface({ input: process.stdin });
    reader.on("line", (line) => {
      raw += line;
    });
    reader.on("close", () => {
      try {
        if (!isEnabled()) {
          process.exit(0);
        }
        const payload = JSON.parse(raw || "{}");
        const switchValue = readSwitch();
        const workspaceId = payload.workspaceId || switchValue.workspace_id;
        if (!workspaceId) {
          log("capture skipped: no workspace_id");
          process.exit(0);
        }
        enqueue({
          workspaceId,
          text: payload.text || "",
          sourceSession: payload.sessionId || "",
          messageId: payload.messageId || "",
        });
      } catch (error) {
        log(`unreadable enqueue payload: ${error?.name || "Error"}`);
      }
      process.exit(0);
    });
  } else {
    main(argv).then(
      (code) => process.exit(code),
      (error) => {
        console.log(`listen: ${error?.name || "Error"}`);
        process.exit(1);
      },
    );
  }
}
