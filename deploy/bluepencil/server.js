#!/usr/bin/env node
/*! bluepencil v0.1.0-alpha.1 — Annotate any web app — text and design notes, anchored to the element, readable by humans and agents. | MIT */

// server/index.ts
import { readFileSync as readFileSync2, renameSync, rmSync, statSync, writeFileSync } from "node:fs";
import {
  createServer
} from "node:http";
import { basename, dirname as dirname2, extname, join as join2, resolve, sep } from "node:path";
import { pathToFileURL } from "node:url";

// src/core/model.ts
var SCHEMA_VERSION = 1;
var BUNDLE_KIND = "bluepencil.bundle";
var DEFAULT_ENVIRONMENT = "dev";
var NOTE_TYPES = ["text", "design"];
var NOTE_INTENTS = ["implement", "feedback"];
var NOTE_STATUSES = ["open", "done", "needs_decision"];
var AUTHOR_TYPES = ["human", "agent"];
var MESSAGE_KINDS = [
  "note",
  "decision_request",
  "decision",
  "feedback",
  "reply"
];
var ENVIRONMENTS = ["dev", "staging", "live"];
var BluepencilValidationError = class extends Error {
  issues;
  constructor(issues) {
    super(`bluepencil: ${issues.length} validation issue(s): ${issues.join("; ")}`);
    this.name = "BluepencilValidationError";
    this.issues = issues;
  }
};
var idCounter = 0;
function newId(prefix = "n") {
  const cryptoObj = globalThis.crypto;
  if (cryptoObj?.randomUUID) {
    return `${prefix}-${cryptoObj.randomUUID()}`;
  }
  idCounter += 1;
  return `${prefix}-${Date.now().toString(36)}-${idCounter.toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}
var systemClock = {
  now: () => (/* @__PURE__ */ new Date()).toISOString()
};
function createMessage(input) {
  return {
    id: input.id ?? newId("m"),
    ts: input.now ?? systemClock.now(),
    author: input.author ?? "unknown",
    authorType: input.authorType ?? "human",
    kind: input.kind ?? "note",
    text: input.text
  };
}
function createNote(draft) {
  const issues = [];
  if (!draft || typeof draft !== "object") {
    throw new BluepencilValidationError(["draft must be an object"]);
  }
  if (typeof draft.body !== "string" || draft.body.trim() === "") {
    issues.push("body must be a non-empty string");
  }
  if (!NOTE_TYPES.includes(draft.type)) {
    issues.push(`type must be one of ${NOTE_TYPES.join(", ")}`);
  }
  if (!draft.anchor || typeof draft.anchor !== "object") {
    issues.push("anchor is required");
  } else if (!draft.anchor.hook && !draft.anchor.selector && !draft.anchor.quote) {
    issues.push("anchor needs at least one of hook, selector or quote");
  }
  if (draft.intent !== void 0 && !NOTE_INTENTS.includes(draft.intent)) {
    issues.push(`intent must be one of ${NOTE_INTENTS.join(", ")}`);
  }
  if (draft.status !== void 0 && !NOTE_STATUSES.includes(draft.status)) {
    issues.push(`status must be one of ${NOTE_STATUSES.join(", ")}`);
  }
  if (draft.authorType !== void 0 && !AUTHOR_TYPES.includes(draft.authorType)) {
    issues.push(`authorType must be one of ${AUTHOR_TYPES.join(", ")}`);
  }
  if (draft.environment !== void 0 && !ENVIRONMENTS.includes(draft.environment)) {
    issues.push(`environment must be one of ${ENVIRONMENTS.join(", ")}`);
  }
  if (issues.length > 0) {
    throw new BluepencilValidationError(issues);
  }
  const ts = draft.now ?? systemClock.now();
  const authorType = draft.authorType ?? "human";
  const note = {
    id: draft.id ?? newId("n"),
    schemaVersion: SCHEMA_VERSION,
    createdAt: ts,
    updatedAt: ts,
    type: draft.type,
    intent: draft.intent ?? "implement",
    status: draft.status ?? "open",
    body: draft.body,
    author: draft.author ?? "anonymous",
    authorType,
    anchor: { ...draft.anchor },
    context: draft.context ?? null,
    messages: draft.messages ? draft.messages.map((m) => ({ ...m })) : [],
    source: draft.source ?? (authorType === "agent" ? "agent" : "ui:human"),
    environment: draft.environment ?? "dev",
    ...draft.sessionRef !== void 0 ? { sessionRef: draft.sessionRef } : {},
    ...draft.ticketRef !== void 0 ? { ticketRef: draft.ticketRef } : {},
    ...draft.debug !== void 0 ? { debug: draft.debug } : {}
  };
  return note;
}
function appendMessage(note, message) {
  return {
    ...note,
    messages: [...note.messages, message],
    updatedAt: message.ts
  };
}
function isExceptionNote(note) {
  return note.status === "needs_decision" || note.intent === "feedback";
}
function isNoteType(value) {
  return typeof value === "string" && NOTE_TYPES.includes(value);
}
function isNoteIntent(value) {
  return typeof value === "string" && NOTE_INTENTS.includes(value);
}
function isNoteStatus(value) {
  return typeof value === "string" && NOTE_STATUSES.includes(value);
}
function isMessageKind(value) {
  return typeof value === "string" && MESSAGE_KINDS.includes(value);
}
function isAuthorType(value) {
  return typeof value === "string" && AUTHOR_TYPES.includes(value);
}
function isEnvironment(value) {
  return typeof value === "string" && ENVIRONMENTS.includes(value);
}

// src/core/adapter.ts
function isRecord(value) {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
function cloneNote(note) {
  return {
    ...note,
    anchor: { ...note.anchor },
    context: cloneContext(note.context),
    messages: note.messages.map((message) => ({ ...message })),
    ...note.debug === void 0 ? {} : { debug: { ...note.debug } }
  };
}
function cloneContext(context) {
  if (!context) {
    return null;
  }
  return {
    ...context,
    classes: [...context.classes],
    styles: { ...context.styles },
    box: { ...context.box },
    viewport: { ...context.viewport }
  };
}
function matchesFilter(note, filter) {
  if (!filter) {
    return true;
  }
  if (filter.route !== void 0 && note.anchor.route !== filter.route) {
    return false;
  }
  if (filter.type !== void 0 && note.type !== filter.type) {
    return false;
  }
  if (filter.intent !== void 0 && note.intent !== filter.intent) {
    return false;
  }
  if (filter.session !== void 0 && note.sessionRef !== filter.session) {
    return false;
  }
  if (filter.source !== void 0 && note.source !== filter.source) {
    return false;
  }
  if (filter.environment !== void 0 && note.environment !== filter.environment) {
    return false;
  }
  const statuses = filter.status === void 0 ? void 0 : Array.isArray(filter.status) ? filter.status : [filter.status];
  if (statuses && !statuses.includes(note.status)) {
    return false;
  }
  if (!statuses && filter.includeDone === false && note.status === "done") {
    return false;
  }
  if (filter.since !== void 0 && !isAtOrAfter(note.updatedAt, filter.since)) {
    return false;
  }
  return true;
}
function isAtOrAfter(value, since) {
  const left = Date.parse(value);
  const right = Date.parse(since);
  if (Number.isNaN(left) || Number.isNaN(right)) {
    return value >= since;
  }
  return left >= right;
}
function filterNotes(notes, filter) {
  return filter ? notes.filter((note) => matchesFilter(note, filter)) : [...notes];
}
function excludeDone(notes) {
  return notes.filter((note) => note.status !== "done");
}
function applyPatch(note, patch, now) {
  const issues = [];
  if (patch.status !== void 0 && !isNoteStatus(patch.status)) {
    issues.push("status must be open, done or needs_decision");
  }
  if (patch.intent !== void 0 && !isNoteIntent(patch.intent)) {
    issues.push("intent must be implement or feedback");
  }
  if (patch.body !== void 0 && (typeof patch.body !== "string" || patch.body.trim() === "")) {
    issues.push("body must be a non-empty string");
  }
  if (patch.ticketRef !== void 0 && typeof patch.ticketRef !== "string") {
    issues.push("ticketRef must be a string");
  }
  if (patch.environment !== void 0 && !isEnvironment(patch.environment)) {
    issues.push("environment must be dev, staging or live");
  }
  if (issues.length > 0) {
    throw new BluepencilValidationError(issues);
  }
  const next = cloneNote(note);
  if (patch.status !== void 0) {
    next.status = patch.status;
  }
  if (patch.intent !== void 0) {
    next.intent = patch.intent;
  }
  if (patch.body !== void 0) {
    next.body = patch.body;
  }
  if (patch.ticketRef !== void 0) {
    next.ticketRef = patch.ticketRef;
  }
  if (patch.environment !== void 0) {
    next.environment = patch.environment;
  }
  if (patch.anchor !== void 0) {
    next.anchor = { ...patch.anchor };
  }
  if (patch.context !== void 0) {
    next.context = cloneContext(patch.context);
  }
  if (patch.sessionRef !== void 0) {
    next.sessionRef = patch.sessionRef;
  }
  if (patch.messages !== void 0 && patch.messages.length > 0) {
    next.messages = [...next.messages, ...patch.messages.map((message) => ({ ...message }))];
  }
  const newest = patch.messages?.[patch.messages.length - 1];
  next.updatedAt = now ?? newest?.ts ?? systemClock.now();
  return next;
}

// src/core/protocol.ts
function reviewPriority(note) {
  if (note.status === "needs_decision") {
    return 0;
  }
  if (note.intent === "feedback") {
    return 1;
  }
  return note.status === "open" ? 2 : 3;
}
function compareText(a, b) {
  if (a < b) {
    return -1;
  }
  return a > b ? 1 : 0;
}
function exceptionNotes(notes) {
  const exceptions = notes.filter((note) => isExceptionNote(note));
  return {
    decisions: sortForReview(exceptions.filter((note) => note.status === "needs_decision")),
    feedback: sortForReview(exceptions.filter((note) => note.intent === "feedback"))
  };
}
function sortForReview(notes) {
  return [...notes].sort((a, b) => {
    const byPriority = reviewPriority(a) - reviewPriority(b);
    if (byPriority !== 0) {
      return byPriority;
    }
    const byCreated = compareText(a.createdAt, b.createdAt);
    if (byCreated !== 0) {
      return byCreated;
    }
    return compareText(a.id, b.id);
  });
}

// src/core/export/markdown.ts
var STRINGS = {
  en: {
    defaultTitle: "bluepencil review notes",
    exported: "Exported",
    notesLabel: "Notes",
    decisionsCount: "open decisions",
    feedbackCount: "feedback only",
    doneCount: "done",
    decisionsSection: "\u26A0 open decisions",
    feedbackSection: "\u{1F4AC} feedback only",
    byRouteSection: "Notes by route",
    noRoute: "(no route)",
    none: "none",
    type: "Type",
    intent: "Intent",
    status: "Status",
    source: "Source",
    author: "Author",
    created: "Created",
    updated: "Updated",
    environment: "Environment",
    session: "Session",
    ticket: "Ticket",
    quote: "Quote",
    anchor: "Anchor",
    hook: "hook",
    selector: "selector",
    route: "Route",
    routeField: "route",
    orphaned: "orphaned",
    degraded: "degraded",
    body: "Body",
    captured: "Captured state",
    debug: "Debug",
    thread: "Thread"
  },
  de: {
    defaultTitle: "bluepencil Review-Notizen",
    exported: "Exportiert",
    notesLabel: "Notizen",
    decisionsCount: "offene Entscheidungen",
    feedbackCount: "nur Feedback",
    doneCount: "erledigt",
    decisionsSection: "\u26A0 offene Entscheidungen",
    feedbackSection: "\u{1F4AC} nur Feedback",
    byRouteSection: "Notizen nach Route",
    noRoute: "(ohne Route)",
    none: "keine",
    type: "Typ",
    intent: "Absicht",
    status: "Status",
    source: "Quelle",
    author: "Autor",
    created: "Erstellt",
    updated: "Ge\xE4ndert",
    environment: "Umgebung",
    session: "Sitzung",
    ticket: "Ticket",
    quote: "Zitat",
    anchor: "Anker",
    hook: "hook",
    selector: "Selektor",
    route: "Route",
    routeField: "Route",
    orphaned: "verwaist",
    degraded: "eingeschr\xE4nkt",
    body: "Text",
    captured: "Erfasster Zustand",
    debug: "Debug",
    thread: "Verlauf"
  }
};
function flatten(value) {
  return value.replace(/\r\n?/g, "\n").replace(/\s+/g, " ").trim();
}
function inline(value) {
  return flatten(value).replace(/`/g, "\\`").replace(/\|/g, "\\|");
}
function code(value) {
  const flat = flatten(value);
  if (flat === "") {
    return "";
  }
  if (flat.includes("`")) {
    return inline(flat);
  }
  return `\`${flat}\``;
}
function fenceFor(text) {
  let longest = 0;
  let run = 0;
  for (const ch of text) {
    if (ch === "`") {
      run += 1;
      if (run > longest) {
        longest = run;
      }
    } else {
      run = 0;
    }
  }
  return "`".repeat(Math.max(3, longest + 1));
}
function fenced(text, indent) {
  const normalized = text.replace(/\r\n?/g, "\n");
  const fence = fenceFor(normalized);
  const lines = normalized.split("\n");
  if (lines.length > 1 && lines[lines.length - 1] === "") {
    lines.pop();
  }
  return [indent + fence, ...lines.map((line) => line === "" ? "" : indent + line), indent + fence];
}
function compareText2(a, b) {
  if (a < b) {
    return -1;
  }
  return a > b ? 1 : 0;
}
function bullet(label, value) {
  return `- ${label}: ${value}`;
}
function section(label) {
  return `- ${label}:`;
}
function renderNote(note, s, headingLevel) {
  const lines = [];
  lines.push(`${"#".repeat(headingLevel)} ${inline(note.id)} \u2014 ${note.type}/${note.intent}/${note.status}`);
  lines.push(bullet(s.type, note.type));
  lines.push(bullet(s.intent, note.intent));
  lines.push(bullet(s.status, note.status));
  lines.push(bullet(s.source, code(note.source)));
  lines.push(bullet(s.author, `${inline(note.author)} (${note.authorType})`));
  lines.push(bullet(s.created, inline(note.createdAt)));
  lines.push(bullet(s.updated, inline(note.updatedAt)));
  lines.push(bullet(s.environment, note.environment));
  if (note.sessionRef !== void 0 && note.sessionRef !== "") {
    lines.push(bullet(s.session, code(note.sessionRef)));
  }
  if (note.ticketRef !== void 0 && note.ticketRef !== "") {
    lines.push(bullet(s.ticket, code(note.ticketRef)));
  }
  const anchor = note.anchor;
  if (anchor.quote !== void 0 && anchor.quote !== "") {
    lines.push(bullet(s.quote, code(anchor.quote)));
  }
  const anchorParts = [];
  if (anchor.hook !== void 0 && anchor.hook !== "") {
    anchorParts.push(`${s.hook} ${code(anchor.hook)}`);
  }
  if (anchor.selector !== void 0 && anchor.selector !== "") {
    anchorParts.push(`${s.selector} ${code(anchor.selector)}`);
  }
  if (anchor.route !== void 0 && anchor.route !== "") {
    anchorParts.push(`${s.routeField} ${code(anchor.route)}`);
  }
  if (anchor.orphaned === true) {
    anchorParts.push(s.orphaned);
  }
  if (anchor.degraded !== void 0 && anchor.degraded !== "") {
    anchorParts.push(`${s.degraded} ${code(anchor.degraded)}`);
  }
  if (anchorParts.length > 0) {
    lines.push(bullet(s.anchor, anchorParts.join(" \xB7 ")));
  }
  lines.push(section(s.body));
  lines.push(...fenced(note.body, "  "));
  const context = note.context;
  if (context !== null) {
    lines.push(section(s.captured));
    lines.push(`  - tag: ${code(context.tag)}`);
    if (context.classes.length > 0) {
      lines.push(`  - classes: ${code(context.classes.join(" "))}`);
    }
    lines.push(`  - scheme: ${context.scheme}`);
    lines.push(`  - viewport: ${context.viewport.w}\xD7${context.viewport.h}`);
    lines.push(`  - box: ${context.box.w}\xD7${context.box.h} at ${context.box.x},${context.box.y}`);
    if (context.buildRef !== void 0 && context.buildRef !== "") {
      lines.push(`  - build: ${code(context.buildRef)}`);
    }
    for (const key of Object.keys(context.styles).sort(compareText2)) {
      const value = context.styles[key];
      if (value === void 0) {
        continue;
      }
      lines.push(`  - style.${inline(key)}: ${inline(value)}`);
    }
  }
  const debug = note.debug;
  if (debug !== void 0) {
    lines.push(section(s.debug));
    if (debug.test !== void 0 && debug.test !== "") {
      lines.push(`  - test: ${code(debug.test)}`);
    }
    if (debug.commit !== void 0 && debug.commit !== "") {
      lines.push(`  - commit: ${code(debug.commit)}`);
    }
    if (debug.file !== void 0 && debug.file !== "") {
      lines.push(`  - file: ${code(debug.file)}`);
    }
    if (debug.stack !== void 0 && debug.stack !== "") {
      lines.push("  - stack:");
      lines.push(...fenced(debug.stack, "    "));
    }
    if (debug.log !== void 0 && debug.log !== "") {
      lines.push("  - log:");
      lines.push(...fenced(debug.log, "    "));
    }
  }
  lines.push(section(s.thread));
  if (note.messages.length === 0) {
    lines.push(`  - ${s.none}`);
  } else {
    note.messages.forEach((message, index) => {
      lines.push(
        `  ${index + 1}. ${inline(message.author)} (${message.authorType}) \xB7 ${message.kind} \xB7 ${inline(message.ts)}`
      );
      lines.push(...fenced(message.text, "     "));
    });
  }
  return lines;
}
function groupByRoute(notes, noRouteKey) {
  const groups = /* @__PURE__ */ new Map();
  for (const note of notes) {
    const route = flatten(note.anchor.route ?? "");
    const key = route === "" ? noRouteKey : route;
    const bucket = groups.get(key);
    if (bucket === void 0) {
      groups.set(key, [note]);
    } else {
      bucket.push(note);
    }
  }
  return groups;
}
function toMarkdown(notes, options = {}) {
  const s = STRINGS[options.language === "de" ? "de" : "en"];
  const includeDone = options.includeDone !== false;
  const included = includeDone ? [...notes] : excludeDone([...notes]);
  const exceptions = exceptionNotes(included);
  const exceptionIds = new Set([...exceptions.decisions, ...exceptions.feedback].map((note) => note.id));
  const rest = sortForReview(included.filter((note) => !exceptionIds.has(note.id)));
  const doneCount = included.filter((note) => note.status === "done").length;
  const out = [];
  out.push(`# ${inline(options.title ?? s.defaultTitle)}`, "");
  if (options.generatedAt !== void 0 && options.generatedAt !== "") {
    out.push(`_${s.exported}: ${inline(options.generatedAt)}_`, "");
  }
  out.push(
    `_${s.notesLabel}: ${included.length} \xB7 ${s.decisionsCount}: ${exceptions.decisions.length} \xB7 ${s.feedbackCount}: ${exceptions.feedback.length} \xB7 ${s.doneCount}: ${doneCount}_`
  );
  const pushSection = (heading, sectionNotes) => {
    if (sectionNotes.length === 0) {
      return;
    }
    out.push("", `## ${heading}`);
    for (const note of sectionNotes) {
      out.push("", ...renderNote(note, s, 4));
    }
  };
  pushSection(s.decisionsSection, exceptions.decisions);
  pushSection(s.feedbackSection, exceptions.feedback);
  const groups = groupByRoute(rest, s.noRoute);
  if (groups.size > 0) {
    out.push("", `## ${s.byRouteSection}`);
    const keys = [...groups.keys()].filter((key) => key !== s.noRoute).sort(compareText2);
    if (groups.has(s.noRoute)) {
      keys.push(s.noRoute);
    }
    for (const key of keys) {
      const groupNotes = groups.get(key) ?? [];
      out.push("", key === s.noRoute ? `### ${s.noRoute}` : `### ${s.route}: ${code(key)}`);
      for (const note of groupNotes) {
        out.push("", ...renderNote(note, s, 4));
      }
    }
  }
  return `${out.join("\n")}
`;
}

// src/data/canonical.ts
function compareStrings(a, b) {
  if (a < b) return -1;
  if (a > b) return 1;
  return 0;
}
function priorityOf(note) {
  if (note.status === "needs_decision") return 0;
  if (note.intent === "feedback") return 1;
  if (note.status === "open") return 2;
  return 3;
}
function routeOf(note) {
  return note.anchor.route ?? "";
}
function compareNotes(a, b) {
  return compareStrings(routeOf(a), routeOf(b)) || priorityOf(a) - priorityOf(b) || compareStrings(a.createdAt, b.createdAt) || compareStrings(a.id, b.id);
}
function compareMessages(a, b) {
  return compareStrings(a.ts, b.ts) || compareStrings(a.id, b.id);
}
function compareSessions(a, b) {
  return compareStrings(a.ref, b.ref) || compareStrings(a.createdAt, b.createdAt);
}
function canonicalAnchor(anchor) {
  const out = {};
  if (anchor.hook !== void 0) out.hook = anchor.hook;
  if (anchor.selector !== void 0) out.selector = anchor.selector;
  if (anchor.quote !== void 0) out.quote = anchor.quote;
  if (anchor.route !== void 0) out.route = anchor.route;
  if (anchor.orphaned !== void 0) out.orphaned = anchor.orphaned;
  if (anchor.degraded !== void 0) out.degraded = anchor.degraded;
  return out;
}
function canonicalContext(context) {
  const styles = {};
  for (const key of Object.keys(context.styles).sort(compareStrings)) {
    const value = context.styles[key];
    if (value !== void 0) styles[key] = value;
  }
  return {
    tag: context.tag,
    classes: [...context.classes],
    styles,
    box: { w: context.box.w, h: context.box.h, x: context.box.x, y: context.box.y },
    scheme: context.scheme,
    viewport: { w: context.viewport.w, h: context.viewport.h },
    ...context.buildRef !== void 0 ? { buildRef: context.buildRef } : {}
  };
}
function canonicalDebug(debug) {
  const out = {};
  if (debug.test !== void 0) out.test = debug.test;
  if (debug.stack !== void 0) out.stack = debug.stack;
  if (debug.log !== void 0) out.log = debug.log;
  if (debug.commit !== void 0) out.commit = debug.commit;
  if (debug.file !== void 0) out.file = debug.file;
  return out;
}
function canonicalMessage(message) {
  return {
    id: message.id,
    ts: message.ts,
    author: message.author,
    authorType: message.authorType,
    kind: message.kind,
    text: message.text
  };
}
function canonicalNote(note) {
  return {
    id: note.id,
    schemaVersion: note.schemaVersion,
    createdAt: note.createdAt,
    updatedAt: note.updatedAt,
    ...note.sessionRef !== void 0 ? { sessionRef: note.sessionRef } : {},
    type: note.type,
    intent: note.intent,
    status: note.status,
    body: note.body,
    author: note.author,
    authorType: note.authorType,
    anchor: canonicalAnchor(note.anchor),
    context: note.context === null ? null : canonicalContext(note.context),
    messages: note.messages.map(canonicalMessage).sort(compareMessages),
    source: note.source,
    environment: note.environment,
    ...note.ticketRef !== void 0 ? { ticketRef: note.ticketRef } : {},
    ...note.debug !== void 0 ? { debug: canonicalDebug(note.debug) } : {}
  };
}
function canonicalSession(session) {
  return { ref: session.ref, label: session.label, createdAt: session.createdAt };
}
function canonicalBundle(bundle) {
  return {
    kind: bundle.kind,
    schemaVersion: bundle.schemaVersion,
    exportedAt: bundle.exportedAt,
    exportedBy: bundle.exportedBy,
    environment: bundle.environment,
    app: {
      name: bundle.app.name,
      ...bundle.app.buildRef !== void 0 ? { buildRef: bundle.app.buildRef } : {}
    },
    sessions: bundle.sessions.map(canonicalSession).sort(compareSessions),
    notes: bundle.notes.map(canonicalNote).sort(compareNotes)
  };
}
function isObject(value) {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
function isBundleLike(value) {
  return isObject(value) && value.kind === BUNDLE_KIND && Array.isArray(value.notes);
}
function isNoteLike(value) {
  return isObject(value) && typeof value.id === "string" && typeof value.body === "string" && Array.isArray(value.messages) && isObject(value.anchor);
}
function canonicalizeValue(value) {
  if (value === null || value === void 0) return value;
  if (Array.isArray(value)) return value.map(canonicalizeValue);
  if (isBundleLike(value)) return canonicalBundle(value);
  if (isNoteLike(value)) return canonicalNote(value);
  if (isObject(value)) {
    const out = {};
    for (const key of Object.keys(value).sort(compareStrings)) {
      out[key] = canonicalizeValue(value[key]);
    }
    return out;
  }
  return value;
}
function serializeCanonical(value) {
  return `${JSON.stringify(canonicalizeValue(value), null, 2)}
`;
}

// src/data/schema.ts
var ISO_8601 = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/;
function isObject2(value) {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
function isNonEmptyString(value) {
  return typeof value === "string" && value.trim() !== "";
}
function isIsoTimestamp(value) {
  return typeof value === "string" && ISO_8601.test(value) && !Number.isNaN(Date.parse(value));
}
function describe(value) {
  if (value === void 0) return "undefined";
  if (value === null) return "null";
  if (typeof value === "string") return JSON.stringify(value);
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return Array.isArray(value) ? "an array" : "an object";
}
function enumIssues(path, value, allowed) {
  if (typeof value === "string" && allowed.includes(value)) return [];
  return [`${path} must be one of ${allowed.join(", ")} (got ${describe(value)})`];
}
function schemaVersionIssues(path, value) {
  if (typeof value !== "number" || !Number.isInteger(value) || value < 1) {
    return [`${path} must be a positive integer (got ${describe(value)})`];
  }
  if (value > SCHEMA_VERSION) {
    return [`${path} ${value} is newer than the supported schema version ${SCHEMA_VERSION}`];
  }
  return [];
}
function anchorIssues(value, path) {
  if (!isObject2(value)) return [`${path} must be an object`];
  const issues = [];
  const hasTarget = isNonEmptyString(value.hook) || isNonEmptyString(value.selector) || isNonEmptyString(value.quote);
  if (!hasTarget) issues.push(`${path} needs at least one of hook, selector or quote`);
  for (const key of ["hook", "selector", "quote", "route", "degraded"]) {
    const field = value[key];
    if (field !== void 0 && typeof field !== "string") issues.push(`${path}.${key} must be a string`);
  }
  if (value.orphaned !== void 0 && typeof value.orphaned !== "boolean") {
    issues.push(`${path}.orphaned must be a boolean`);
  }
  return issues;
}
function stringListIssues(value, path) {
  if (!Array.isArray(value)) return [`${path} must be an array of strings`];
  const issues = [];
  value.forEach((entry2, index) => {
    if (typeof entry2 !== "string") issues.push(`${path}[${index}] must be a string`);
  });
  return issues;
}
function stringMapIssues(value, path) {
  if (!isObject2(value)) return [`${path} must be an object of strings`];
  const issues = [];
  for (const key of Object.keys(value)) {
    if (typeof value[key] !== "string") issues.push(`${path}.${key} must be a string`);
  }
  return issues;
}
function numberIssues(value, path, keys) {
  if (!isObject2(value)) return [`${path} must be an object`];
  const issues = [];
  for (const key of keys) {
    const field = value[key];
    if (typeof field !== "number" || Number.isNaN(field)) issues.push(`${path}.${key} must be a number`);
  }
  return issues;
}
function contextIssues(value, path) {
  if (value === void 0) return [`${path} must be null or an object`];
  if (value === null) return [];
  if (!isObject2(value)) return [`${path} must be null or an object`];
  const issues = [];
  if (!isNonEmptyString(value.tag)) issues.push(`${path}.tag must be a non-empty string`);
  issues.push(...stringListIssues(value.classes, `${path}.classes`));
  issues.push(...stringMapIssues(value.styles, `${path}.styles`));
  issues.push(...numberIssues(value.box, `${path}.box`, ["w", "h", "x", "y"]));
  issues.push(...enumIssues(`${path}.scheme`, value.scheme, ["light", "dark"]));
  issues.push(...numberIssues(value.viewport, `${path}.viewport`, ["w", "h"]));
  if (value.buildRef !== void 0 && typeof value.buildRef !== "string") {
    issues.push(`${path}.buildRef must be a string`);
  }
  return issues;
}
function debugIssues(value, path) {
  if (!isObject2(value)) return [`${path} must be an object`];
  const issues = [];
  for (const key of ["test", "stack", "log", "commit", "file"]) {
    const field = value[key];
    if (field !== void 0 && typeof field !== "string") issues.push(`${path}.${key} must be a string`);
  }
  return issues;
}
function messageIssues(value, path) {
  if (!isObject2(value)) return [`${path} must be an object`];
  const issues = [];
  if (!isNonEmptyString(value.id)) issues.push(`${path}.id must be a non-empty string`);
  if (!isIsoTimestamp(value.ts)) issues.push(`${path}.ts must be an ISO 8601 timestamp`);
  if (!isNonEmptyString(value.author)) issues.push(`${path}.author must be a non-empty string`);
  issues.push(...enumIssues(`${path}.authorType`, value.authorType, AUTHOR_TYPES));
  issues.push(...enumIssues(`${path}.kind`, value.kind, MESSAGE_KINDS));
  if (!isNonEmptyString(value.text)) issues.push(`${path}.text must be a non-empty string`);
  return issues;
}
function messagesIssues(value, path) {
  if (!Array.isArray(value)) return [`${path} must be an array`];
  const issues = [];
  value.forEach((message, index) => issues.push(...messageIssues(message, `${path}[${index}]`)));
  return issues;
}
function noteIssues(note, path) {
  const issues = [];
  if (!isNonEmptyString(note.id)) issues.push(`${path}.id must be a non-empty string`);
  issues.push(...schemaVersionIssues(`${path}.schemaVersion`, note.schemaVersion));
  if (!isIsoTimestamp(note.createdAt)) issues.push(`${path}.createdAt must be an ISO 8601 timestamp`);
  if (!isIsoTimestamp(note.updatedAt)) issues.push(`${path}.updatedAt must be an ISO 8601 timestamp`);
  if (note.sessionRef !== void 0 && !isNonEmptyString(note.sessionRef)) {
    issues.push(`${path}.sessionRef must be a non-empty string`);
  }
  issues.push(...enumIssues(`${path}.type`, note.type, NOTE_TYPES));
  issues.push(...enumIssues(`${path}.intent`, note.intent, NOTE_INTENTS));
  issues.push(...enumIssues(`${path}.status`, note.status, NOTE_STATUSES));
  if (!isNonEmptyString(note.body)) issues.push(`${path}.body must be a non-empty string`);
  if (!isNonEmptyString(note.author)) issues.push(`${path}.author must be a non-empty string`);
  issues.push(...enumIssues(`${path}.authorType`, note.authorType, AUTHOR_TYPES));
  issues.push(...anchorIssues(note.anchor, `${path}.anchor`));
  issues.push(...contextIssues(note.context, `${path}.context`));
  issues.push(...messagesIssues(note.messages, `${path}.messages`));
  if (!isNonEmptyString(note.source)) issues.push(`${path}.source must be a non-empty string`);
  issues.push(...enumIssues(`${path}.environment`, note.environment, ENVIRONMENTS));
  if (note.ticketRef !== void 0 && !isNonEmptyString(note.ticketRef)) {
    issues.push(`${path}.ticketRef must be a non-empty string`);
  }
  if (note.debug !== void 0) issues.push(...debugIssues(note.debug, `${path}.debug`));
  return issues;
}
function appIssues(value) {
  if (!isObject2(value)) return ["bundle.app must be an object"];
  const issues = [];
  if (!isNonEmptyString(value.name)) issues.push("bundle.app.name must be a non-empty string");
  if (value.buildRef !== void 0 && typeof value.buildRef !== "string") {
    issues.push("bundle.app.buildRef must be a string");
  }
  return issues;
}
function sessionIssues(value) {
  if (!Array.isArray(value)) return ["bundle.sessions must be an array"];
  const issues = [];
  const seen = /* @__PURE__ */ new Set();
  value.forEach((session, index) => {
    const path = `bundle.sessions[${index}]`;
    if (!isObject2(session)) {
      issues.push(`${path} must be an object`);
      return;
    }
    if (!isNonEmptyString(session.ref)) issues.push(`${path}.ref must be a non-empty string`);
    if (!isNonEmptyString(session.label)) issues.push(`${path}.label must be a non-empty string`);
    if (!isIsoTimestamp(session.createdAt)) issues.push(`${path}.createdAt must be an ISO 8601 timestamp`);
    if (typeof session.ref === "string") {
      if (seen.has(session.ref)) issues.push(`${path}.ref ${JSON.stringify(session.ref)} is not unique`);
      seen.add(session.ref);
    }
  });
  return issues;
}
function bundleNoteIssues(value) {
  if (!Array.isArray(value)) return ["bundle.notes must be an array"];
  const issues = [];
  const seen = /* @__PURE__ */ new Set();
  value.forEach((note, index) => {
    const path = `bundle.notes[${index}]`;
    if (!isObject2(note)) {
      issues.push(`${path} must be an object`);
      return;
    }
    issues.push(...noteIssues(note, path));
    if (typeof note.id === "string") {
      if (seen.has(note.id)) issues.push(`${path}.id ${JSON.stringify(note.id)} is not unique`);
      seen.add(note.id);
    }
  });
  return issues;
}
function validateNote(value) {
  if (!isObject2(value)) return ["note must be an object"];
  return noteIssues(value, "note");
}
function validateBundle(value) {
  if (!isObject2(value)) return ["bundle must be an object"];
  const issues = [];
  if (value.kind !== BUNDLE_KIND) {
    issues.push(`bundle.kind must be ${JSON.stringify(BUNDLE_KIND)} (got ${describe(value.kind)})`);
  }
  issues.push(...schemaVersionIssues("bundle.schemaVersion", value.schemaVersion));
  if (!isIsoTimestamp(value.exportedAt)) issues.push("bundle.exportedAt must be an ISO 8601 timestamp");
  if (!isNonEmptyString(value.exportedBy)) issues.push("bundle.exportedBy must be a non-empty string");
  issues.push(...enumIssues("bundle.environment", value.environment, ENVIRONMENTS));
  issues.push(...appIssues(value.app));
  issues.push(...sessionIssues(value.sessions));
  issues.push(...bundleNoteIssues(value.notes));
  return issues;
}
function assertNote(value) {
  const issues = validateNote(value);
  if (issues.length > 0) throw new BluepencilValidationError(issues);
  return value;
}
function assertBundle(value) {
  const issues = validateBundle(value);
  if (issues.length > 0) throw new BluepencilValidationError(issues);
  return value;
}

// src/data/bundle.ts
function compareStrings2(a, b) {
  if (a < b) return -1;
  if (a > b) return 1;
  return 0;
}
function uniqueEnvironments(values) {
  return [...new Set(values)].sort(compareStrings2);
}
function resolveEnvironment(found, requested) {
  if (requested !== void 0) {
    if (!isEnvironment(requested)) {
      throw new BluepencilValidationError([
        `options.environment must be one of ${ENVIRONMENTS.join(", ")}`
      ]);
    }
    return requested;
  }
  const first = found[0];
  if (found.length === 1 && first !== void 0) return first;
  if (found.length === 0) return DEFAULT_ENVIRONMENT;
  throw new BluepencilValidationError([
    `notes span multiple environments (${found.join(", ")}); export one environment at a time or pass options.environment explicitly`
  ]);
}
function deriveSessions(notes) {
  const earliest = /* @__PURE__ */ new Map();
  for (const note of notes) {
    const ref = note.sessionRef;
    if (ref === void 0 || ref === "") continue;
    const current = earliest.get(ref);
    if (current === void 0 || note.createdAt < current) earliest.set(ref, note.createdAt);
  }
  return [...earliest.entries()].map(([ref, createdAt]) => ({ ref, label: ref, createdAt }));
}
function createBundle(notes, options = {}) {
  if (!Array.isArray(notes)) {
    throw new BluepencilValidationError(["notes must be an array"]);
  }
  const validated = notes.map((note) => assertNote(note));
  const environment = resolveEnvironment(
    uniqueEnvironments(validated.map((note) => note.environment)),
    options.environment
  );
  const tagged = validated.map(
    (note) => note.environment === environment ? note : { ...note, environment }
  );
  const bundle = {
    kind: BUNDLE_KIND,
    schemaVersion: SCHEMA_VERSION,
    exportedAt: options.now ?? systemClock.now(),
    exportedBy: options.exportedBy ?? "unknown",
    environment,
    app: { name: options.app?.name ?? "unknown", ...options.app?.buildRef !== void 0 ? { buildRef: options.app.buildRef } : {} },
    sessions: options.sessions ?? deriveSessions(tagged),
    notes: tagged
  };
  return assertBundle(canonicalBundle(bundle));
}
function bundleToJson(bundle, options = {}) {
  const canonical = assertBundle(canonicalBundle(bundle));
  if (options.pretty === false) return `${JSON.stringify(canonical)}
`;
  return serializeCanonical(canonical);
}

// src/data/migrate.ts
var LEGACY_VERSION = 1;
var NOTE_MIGRATIONS = {
  1: (doc) => doc
};
var BUNDLE_MIGRATIONS = {
  1: (doc) => doc
};
var SCHEMES = ["light", "dark"];
function isObject3(value) {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
function nonEmptyString(value) {
  return typeof value === "string" && value !== "" ? value : void 0;
}
function deepCopy(value) {
  if (Array.isArray(value)) return value.map(deepCopy);
  if (isObject3(value)) {
    const out = {};
    for (const key of Object.keys(value)) out[key] = deepCopy(value[key]);
    return out;
  }
  return value;
}
function copyObject(value) {
  return deepCopy(value);
}
function readVersion(value, path) {
  if (value === void 0 || value === null) return LEGACY_VERSION;
  if (typeof value !== "number" || !Number.isInteger(value) || value < 1) {
    throw new BluepencilValidationError([`${path}.schemaVersion must be a positive integer`]);
  }
  if (value > SCHEMA_VERSION) {
    throw new BluepencilValidationError([
      `${path}.schemaVersion ${value} is newer than the supported schema version ${SCHEMA_VERSION}`
    ]);
  }
  return value;
}
function runMigrations(value, fromVersion, table) {
  let current = copyObject(value);
  for (let version = fromVersion + 1; version <= SCHEMA_VERSION; version += 1) {
    const step = table[version];
    if (step !== void 0) current = step(current);
  }
  return current;
}
function pickLiteral(value, allowed, fallback) {
  if (typeof value === "string") {
    const match = allowed.find((candidate) => candidate === value);
    if (match !== void 0) return match;
  }
  return fallback;
}
function toIso(value, fallback) {
  if (typeof value === "string") {
    const parsed = Date.parse(value);
    if (!Number.isNaN(parsed)) return new Date(parsed).toISOString();
  }
  if (typeof value === "number" && Number.isFinite(value)) return new Date(value).toISOString();
  return fallback;
}
function numberOrZero(value) {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}
function upgradeAnchor(value, path) {
  if (value === void 0 || value === null) return {};
  if (!isObject3(value)) throw new BluepencilValidationError([`${path} must be an object`]);
  const anchor = {};
  if (typeof value.hook === "string") anchor.hook = value.hook;
  if (typeof value.selector === "string") anchor.selector = value.selector;
  if (typeof value.quote === "string") anchor.quote = value.quote;
  if (typeof value.route === "string") anchor.route = value.route;
  if (typeof value.orphaned === "boolean") anchor.orphaned = value.orphaned;
  if (typeof value.degraded === "string") anchor.degraded = value.degraded;
  return anchor;
}
function upgradeContext(value, path) {
  if (value === void 0 || value === null) return null;
  if (!isObject3(value)) throw new BluepencilValidationError([`${path} must be null or an object`]);
  const box = isObject3(value.box) ? value.box : {};
  const viewport = isObject3(value.viewport) ? value.viewport : {};
  const classes = Array.isArray(value.classes) ? value.classes.filter((entry2) => typeof entry2 === "string") : [];
  const styles = {};
  if (isObject3(value.styles)) {
    for (const key of Object.keys(value.styles)) {
      const entry2 = value.styles[key];
      if (typeof entry2 === "string") styles[key] = entry2;
    }
  }
  return {
    tag: typeof value.tag === "string" ? value.tag : "",
    classes,
    styles,
    box: {
      w: numberOrZero(box.w),
      h: numberOrZero(box.h),
      x: numberOrZero(box.x),
      y: numberOrZero(box.y)
    },
    scheme: pickLiteral(value.scheme, SCHEMES, "light"),
    viewport: { w: numberOrZero(viewport.w), h: numberOrZero(viewport.h) },
    ...typeof value.buildRef === "string" ? { buildRef: value.buildRef } : {}
  };
}
function upgradeDebug(value, path) {
  if (value === void 0 || value === null) return void 0;
  if (!isObject3(value)) throw new BluepencilValidationError([`${path} must be an object`]);
  const debug = {};
  if (typeof value.test === "string") debug.test = value.test;
  if (typeof value.stack === "string") debug.stack = value.stack;
  if (typeof value.log === "string") debug.log = value.log;
  if (typeof value.commit === "string") debug.commit = value.commit;
  if (typeof value.file === "string") debug.file = value.file;
  return debug;
}
function upgradeMessage(value, path, now) {
  if (!isObject3(value)) throw new BluepencilValidationError([`${path} must be an object`]);
  return {
    id: nonEmptyString(value.id) ?? newId("m"),
    ts: toIso(value.ts, now),
    author: nonEmptyString(value.author) ?? "unknown",
    authorType: pickLiteral(value.authorType, AUTHOR_TYPES, "human"),
    kind: pickLiteral(value.kind, MESSAGE_KINDS, "note"),
    text: typeof value.text === "string" ? value.text : ""
  };
}
function upgradeMessages(value, path, now) {
  if (value === void 0 || value === null) return [];
  if (!Array.isArray(value)) throw new BluepencilValidationError([`${path} must be an array`]);
  return value.map((entry2, index) => upgradeMessage(entry2, `${path}[${index}]`, now));
}
function upgradeNote(value, defaults, path) {
  if (!isObject3(value)) throw new BluepencilValidationError([`${path} must be an object`]);
  const version = readVersion(value.schemaVersion, path);
  const doc = runMigrations(value, version, NOTE_MIGRATIONS);
  const now = systemClock.now();
  const createdAt = toIso(doc.createdAt, now);
  const sessionRef = nonEmptyString(doc.sessionRef);
  const ticketRef = nonEmptyString(doc.ticketRef);
  const debug = upgradeDebug(doc.debug, `${path}.debug`);
  const source = nonEmptyString(doc.source) ?? defaults.source ?? "cli:import";
  const note = {
    id: nonEmptyString(doc.id) ?? newId("n"),
    schemaVersion: SCHEMA_VERSION,
    createdAt,
    updatedAt: toIso(doc.updatedAt, createdAt),
    ...sessionRef !== void 0 ? { sessionRef } : {},
    type: pickLiteral(doc.type, NOTE_TYPES, "text"),
    intent: pickLiteral(doc.intent, NOTE_INTENTS, "implement"),
    status: pickLiteral(doc.status, NOTE_STATUSES, "open"),
    body: typeof doc.body === "string" ? doc.body : "",
    author: nonEmptyString(doc.author) ?? "anonymous",
    authorType: pickLiteral(doc.authorType, AUTHOR_TYPES, "human"),
    anchor: upgradeAnchor(doc.anchor, `${path}.anchor`),
    context: upgradeContext(doc.context, `${path}.context`),
    messages: upgradeMessages(doc.messages, `${path}.messages`, now),
    source,
    environment: pickLiteral(doc.environment, ENVIRONMENTS, defaults.environment ?? DEFAULT_ENVIRONMENT),
    ...ticketRef !== void 0 ? { ticketRef } : {},
    ...debug !== void 0 ? { debug } : {}
  };
  return assertNote(note);
}
function deriveSessions2(notes) {
  const earliest = /* @__PURE__ */ new Map();
  for (const note of notes) {
    const ref = note.sessionRef;
    if (ref === void 0 || ref === "") continue;
    const current = earliest.get(ref);
    if (current === void 0 || note.createdAt < current) earliest.set(ref, note.createdAt);
  }
  return [...earliest.entries()].map(([ref, createdAt]) => ({ ref, label: ref, createdAt }));
}
function upgradeSessions(value, notes, now) {
  if (value === void 0 || value === null) return deriveSessions2(notes);
  if (!Array.isArray(value)) throw new BluepencilValidationError(["bundle.sessions must be an array"]);
  return value.map((entry2, index) => {
    const path = `bundle.sessions[${index}]`;
    if (!isObject3(entry2)) throw new BluepencilValidationError([`${path} must be an object`]);
    const ref = nonEmptyString(entry2.ref) ?? `session-${index + 1}`;
    return {
      ref,
      label: nonEmptyString(entry2.label) ?? ref,
      createdAt: toIso(entry2.createdAt, now)
    };
  });
}
function upgradeApp(value) {
  if (value === void 0 || value === null) return { name: "unknown" };
  if (!isObject3(value)) throw new BluepencilValidationError(["bundle.app must be an object"]);
  const name = nonEmptyString(value.name) ?? "unknown";
  const buildRef = nonEmptyString(value.buildRef);
  return { name, ...buildRef !== void 0 ? { buildRef } : {} };
}
function migrateBundle(value) {
  const source = Array.isArray(value) ? { notes: value } : value;
  if (!isObject3(source)) {
    throw new BluepencilValidationError(["bundle must be an object or an array of notes"]);
  }
  const version = readVersion(source.schemaVersion, "bundle");
  const doc = runMigrations(source, version, BUNDLE_MIGRATIONS);
  const now = systemClock.now();
  const environment = pickLiteral(doc.environment, ENVIRONMENTS, DEFAULT_ENVIRONMENT);
  let notes = [];
  if (doc.notes !== void 0 && doc.notes !== null) {
    if (!Array.isArray(doc.notes)) throw new BluepencilValidationError(["bundle.notes must be an array"]);
    notes = doc.notes.map(
      (entry2, index) => upgradeNote(entry2, { environment, source: "cli:import" }, `bundle.notes[${index}]`)
    );
  }
  const bundle = {
    kind: BUNDLE_KIND,
    schemaVersion: SCHEMA_VERSION,
    exportedAt: toIso(doc.exportedAt, now),
    exportedBy: nonEmptyString(doc.exportedBy) ?? "unknown",
    environment,
    app: upgradeApp(doc.app),
    sessions: upgradeSessions(doc.sessions, notes, now),
    notes
  };
  return assertBundle(bundle);
}

// src/version.ts
var VERSION = true ? "0.1.0-alpha.1" : "dev";

// server/handler.ts
var SERVER_VERSION = VERSION;
var DEFAULT_BASE_PATH = "/api/v1/bluepencil";
var SIDECAR_EXPORTED_BY = "server:bluepencil";
var SIDECAR_APP_NAME = "bluepencil sidecar";
var JSON_CONTENT_TYPE = "application/json; charset=utf-8";
var HttpError = class extends Error {
  status;
  code;
  constructor(status, code2, message) {
    super(message);
    this.name = "HttpError";
    this.status = status;
    this.code = code2;
  }
};
function refuse(status, code2, message) {
  throw new HttpError(status, code2, message);
}
function oneLine(value) {
  return value.replace(/\s+/g, " ").trim();
}
function errorText(error) {
  if (error instanceof BluepencilValidationError) return error.issues.join("; ");
  return error instanceof Error ? error.message : String(error);
}
function headerValue(headers, name) {
  if (!headers) return void 0;
  const wanted = name.toLowerCase();
  for (const key of Object.keys(headers)) {
    if (key.toLowerCase() !== wanted) continue;
    const value = headers[key];
    return Array.isArray(value) ? value[0] : value;
  }
  return void 0;
}
function mediaType(value) {
  if (value === void 0) return "";
  const semicolon = value.indexOf(";");
  return (semicolon === -1 ? value : value.slice(0, semicolon)).trim().toLowerCase();
}
function normalizeBase(base) {
  const trimmed = (base ?? "").trim();
  if (trimmed === "" || trimmed === "/") return "";
  const withoutTrailing = trimmed.replace(/\/+$/, "");
  return withoutTrailing.startsWith("/") ? withoutTrailing : `/${withoutTrailing}`;
}
function parseRequestUrl(url) {
  const absolute = /^[a-z][a-z0-9+.-]*:\/\//i.test(url);
  const target = absolute ? url : `http://localhost${url.startsWith("/") ? "" : "/"}${url}`;
  const parsed = new URL(target);
  return { pathname: parsed.pathname, query: parsed.searchParams };
}
function requestPath(url) {
  return parseRequestUrl(url).pathname;
}
function isApiPath(url, base) {
  return pathWithin(requestPath(url), normalizeBase(base)) !== null;
}
function pathWithin(pathname, base) {
  if (base === "") return pathname;
  if (pathname === base) return "";
  return pathname.startsWith(`${base}/`) ? pathname.slice(base.length) : null;
}
function splitSegments(rest) {
  return rest.split("/").filter((segment) => segment !== "").map((segment) => {
    try {
      return decodeURIComponent(segment);
    } catch {
      return segment;
    }
  });
}
function allowedMethods(segments) {
  const first = segments[0];
  if (segments.length === 1) {
    if (first === "health") return ["GET"];
    if (first === "notes") return ["GET", "POST"];
    if (first === "sessions") return ["GET"];
    if (first === "bundle") return ["GET"];
    return null;
  }
  if (segments.length === 2 && first === "notes") {
    return segments[1] === "bulk-delete" ? ["POST"] : ["PATCH"];
  }
  if (segments.length === 3 && first === "notes" && segments[2] === "messages") return ["POST"];
  return null;
}
function corsHeaders(cors) {
  if (cors === void 0 || cors === "") return {};
  return {
    "access-control-allow-origin": cors,
    "access-control-allow-methods": "GET, POST, PATCH, OPTIONS",
    "access-control-allow-headers": "Content-Type, Authorization",
    "access-control-max-age": "600",
    ...cors === "*" ? {} : { vary: "Origin" }
  };
}
function json(status, payload, context) {
  return {
    status,
    headers: {
      "content-type": JSON_CONTENT_TYPE,
      "cache-control": "no-store",
      ...corsHeaders(context.cors)
    },
    body: JSON.stringify(payload)
  };
}
function errorResponse(status, code2, message, context) {
  return {
    status,
    headers: {
      "content-type": JSON_CONTENT_TYPE,
      "cache-control": "no-store",
      ...corsHeaders(context.cors)
    },
    body: errorBody(code2, message)
  };
}
function errorBody(code2, message) {
  return JSON.stringify({ error: { code: code2, message: oneLine(message) } });
}
function toErrorResponse(error, context) {
  if (error instanceof HttpError) {
    return errorResponse(error.status, error.code, error.message, context);
  }
  if (error instanceof BluepencilValidationError) {
    return errorResponse(400, "invalid_payload", error.issues.join("; ") || "invalid payload", context);
  }
  return errorResponse(500, "internal_error", errorText(error), context);
}
function applyMutation(context, mutate, event) {
  const previous = context.store.notes;
  let response;
  try {
    response = mutate();
  } catch (error) {
    context.store.notes = previous;
    return toErrorResponse(error, context);
  }
  if (context.persist) {
    try {
      context.persist(context.store, typeof event === "function" ? event() : event);
    } catch (error) {
      context.store.notes = previous;
      return errorResponse(
        500,
        "store_write_failed",
        `the note set could not be written: ${errorText(error)}`,
        context
      );
    }
  }
  return response;
}
function readJsonObject(request) {
  const type = mediaType(headerValue(request.headers, "content-type"));
  if (type !== "application/json") {
    refuse(
      415,
      "unsupported_media_type",
      `the request body must be application/json (got ${type === "" ? "no content type" : JSON.stringify(type)})`
    );
  }
  const raw = request.body ?? "";
  if (raw.trim() === "") {
    refuse(400, "invalid_json", "the request body is empty");
  }
  let parsed;
  try {
    parsed = JSON.parse(raw);
  } catch (error) {
    refuse(400, "invalid_json", `the request body is not valid JSON: ${errorText(error)}`);
  }
  if (!isRecord(parsed)) {
    refuse(400, "invalid_payload", "the request body must be a JSON object");
  }
  return parsed;
}
function currentTime(context) {
  return context.now ? context.now() : systemClock.now();
}
function filterFromQuery(query) {
  const filter = {};
  const route = query.get("route");
  if (route !== null) filter.route = route;
  const session = query.get("session");
  if (session !== null) filter.session = session;
  const source = query.get("source");
  if (source !== null) filter.source = source;
  const since = query.get("since");
  if (since !== null) filter.since = since;
  const intent = query.get("intent");
  if (intent !== null) {
    if (!isNoteIntent(intent)) {
      refuse(400, "invalid_query", `intent must be one of ${NOTE_INTENTS.join(", ")} (got ${JSON.stringify(intent)})`);
    }
    filter.intent = intent;
  }
  const type = query.get("type");
  if (type !== null) {
    if (!isNoteType(type)) {
      refuse(400, "invalid_query", `type must be one of ${NOTE_TYPES.join(", ")} (got ${JSON.stringify(type)})`);
    }
    filter.type = type;
  }
  const environment = query.get("environment");
  if (environment !== null) {
    if (!isEnvironment(environment)) {
      refuse(
        400,
        "invalid_query",
        `environment must be one of ${ENVIRONMENTS.join(", ")} (got ${JSON.stringify(environment)})`
      );
    }
    filter.environment = environment;
  }
  const includeDone = query.get("includeDone");
  if (includeDone !== null) {
    if (includeDone !== "true" && includeDone !== "false") {
      refuse(400, "invalid_query", `includeDone must be true or false (got ${JSON.stringify(includeDone)})`);
    }
    filter.includeDone = includeDone === "true";
  }
  const statuses = query.getAll("status");
  if (statuses.length > 0) {
    const checked = [];
    for (const status of statuses) {
      if (!isNoteStatus(status)) {
        refuse(
          400,
          "invalid_query",
          `status must be one of ${NOTE_STATUSES.join(", ")} (got ${JSON.stringify(status)})`
        );
      }
      checked.push(status);
    }
    filter.status = checked;
  }
  return filter;
}
function filterFromBody(value) {
  if (!isRecord(value)) {
    refuse(400, "invalid_payload", "filter must be a JSON object");
  }
  const query = new URLSearchParams();
  for (const key of Object.keys(value)) {
    const entry2 = value[key];
    if (entry2 === void 0 || entry2 === null) continue;
    if (key === "status") {
      for (const status of Array.isArray(entry2) ? entry2 : [entry2]) {
        query.append("status", String(status));
      }
      continue;
    }
    if (key === "includeDone") {
      query.set("includeDone", String(entry2));
      continue;
    }
    if (key === "route" || key === "session" || key === "source" || key === "since") {
      query.set(key, String(entry2));
      continue;
    }
    if (key === "intent" || key === "type" || key === "environment") {
      query.set(key, String(entry2));
    }
  }
  return filterFromQuery(query);
}
var PATCH_FIELDS = /* @__PURE__ */ new Set([
  "status",
  "intent",
  "body",
  "ticketRef",
  "environment",
  "anchor",
  "context",
  "sessionRef"
]);
function patchFromBody(payload) {
  const unknown = Object.keys(payload).filter((key) => !PATCH_FIELDS.has(key));
  if (unknown.length > 0) {
    refuse(
      400,
      "invalid_payload",
      `unknown patch field(s) ${unknown.join(", ")} \u2014 a patch carries mutable note fields only`
    );
  }
  return payload;
}
function messageFromBody(payload, context) {
  const authorType = payload.author_type ?? payload.authorType ?? "human";
  const kind = payload.kind ?? "note";
  if (!isAuthorType(authorType)) {
    refuse(
      400,
      "invalid_payload",
      `author_type must be one of ${AUTHOR_TYPES.join(", ")} (got ${JSON.stringify(authorType)})`
    );
  }
  if (!isMessageKind(kind)) {
    refuse(400, "invalid_payload", `kind must be one of ${MESSAGE_KINDS.join(", ")} (got ${JSON.stringify(kind)})`);
  }
  return createMessage({
    text: typeof payload.text === "string" ? payload.text : "",
    author: typeof payload.author === "string" ? payload.author : "unknown",
    authorType,
    kind,
    now: typeof payload.ts === "string" ? payload.ts : currentTime(context),
    ...typeof payload.id === "string" ? { id: payload.id } : {}
  });
}
function findNote(context, id) {
  const note = context.store.notes.find((candidate) => candidate.id === id);
  if (!note) {
    refuse(404, "not_found", `no note with id ${JSON.stringify(id)}`);
  }
  return note;
}
function assertEnvironment(noteEnvironment, context) {
  if (noteEnvironment === context.environment || context.allowEnvMismatch) return;
  refuse(
    400,
    "environment_mismatch",
    `this sidecar serves the ${context.environment} environment \u2014 a ${noteEnvironment} note is refused (restart it with --allow-env-mismatch to promote such notes)`
  );
}
function health(context) {
  return json(200, { ok: true, status: "ok", version: context.version ?? SERVER_VERSION }, context);
}
function listNotes(query, context) {
  const filter = filterFromQuery(query);
  const matching = sortForReview(filterNotes(context.store.notes, filter));
  return json(200, { notes: matching.map(canonicalNote) }, context);
}
function bundleOf(context) {
  return createBundle(context.store.notes, {
    environment: context.environment,
    app: { name: context.appName ?? SIDECAR_APP_NAME },
    exportedBy: context.exportedBy ?? SIDECAR_EXPORTED_BY,
    ...context.now !== void 0 ? { now: context.now() } : {}
  });
}
function createNoteFromBody(request, context) {
  const payload = readJsonObject(request);
  const requested = payload.environment;
  if (requested !== void 0 && !isEnvironment(requested)) {
    refuse(
      400,
      "invalid_payload",
      `environment must be one of ${ENVIRONMENTS.join(", ")} (got ${JSON.stringify(requested)})`
    );
  }
  let created = "";
  return applyMutation(context, () => {
    if (requested !== void 0) assertEnvironment(requested, context);
    const draft = {
      ...payload,
      // A note is always born in the sidecar's environment (see `assertEnvironment`).
      environment: context.environment
    };
    if (draft.now === void 0 && context.now !== void 0) draft.now = context.now();
    const note = createNote(draft);
    const issues = validateNote(note);
    if (issues.length > 0) {
      throw new BluepencilValidationError(issues);
    }
    if (context.store.notes.some((candidate) => candidate.id === note.id)) {
      refuse(400, "duplicate_id", `a note with id ${JSON.stringify(note.id)} already exists`);
    }
    context.store.notes = [...context.store.notes, note];
    created = note.id;
    return json(200, { note: canonicalNote(note) }, context);
  }, () => ({ op: "create", noteId: created }));
}
function patchNote(id, request, context) {
  const patch = patchFromBody(readJsonObject(request));
  const note = findNote(context, id);
  return applyMutation(context, () => {
    assertEnvironment(note.environment, context);
    const next = applyPatch(note, patch, context.now ? context.now() : void 0);
    next.environment = context.environment;
    const issues = validateNote(next);
    if (issues.length > 0) {
      throw new BluepencilValidationError(issues);
    }
    context.store.notes = context.store.notes.map((candidate) => candidate.id === id ? next : candidate);
    return json(200, { note: canonicalNote(next) }, context);
  }, { op: "update", noteId: id });
}
function appendMessageToNote(id, request, context) {
  const payload = readJsonObject(request);
  const note = findNote(context, id);
  return applyMutation(context, () => {
    assertEnvironment(note.environment, context);
    const message = messageFromBody(payload, context);
    const next = appendMessage(note, message);
    next.environment = context.environment;
    const issues = validateNote(next);
    if (issues.length > 0) {
      throw new BluepencilValidationError(issues);
    }
    context.store.notes = context.store.notes.map((candidate) => candidate.id === id ? next : candidate);
    return json(200, { note: canonicalNote(next) }, context);
  }, { op: "message", noteId: id });
}
function bulkDelete(request, context) {
  const payload = readJsonObject(request);
  if (payload.confirm !== true) {
    refuse(400, "confirm_required", 'bulk-delete requires {"confirm": true} \u2014 nothing was removed');
  }
  const rawIds = payload.ids;
  const rawFilter = payload.filter;
  if (rawIds === void 0 && rawFilter === void 0) {
    refuse(400, "invalid_payload", "bulk-delete needs ids or filter \u2014 refusing to guess what to remove");
  }
  let ids = null;
  if (rawIds !== void 0) {
    if (!Array.isArray(rawIds) || rawIds.some((entry2) => typeof entry2 !== "string")) {
      refuse(400, "invalid_payload", "ids must be an array of note ids");
    }
    ids = rawIds;
  }
  const filter = rawFilter !== void 0 ? filterFromBody(rawFilter) : null;
  let removedCount = 0;
  return applyMutation(context, () => {
    const selected = ids !== null ? context.store.notes.filter((note) => ids.includes(note.id)) : filterNotes(context.store.notes, filter ?? {});
    if (!context.allowEnvMismatch) {
      const foreign = selected.map((note) => note.environment).filter((environment, index, all) => environment !== context.environment && all.indexOf(environment) === index);
      if (foreign.length > 0) {
        refuse(
          400,
          "environment_mismatch",
          `the selection contains ${foreign.join(", ")} note(s) \u2014 refusing to remove them from a ${context.environment} sidecar (restart with --allow-env-mismatch to allow it)`
        );
      }
    }
    const doomed = new Set(selected.map((note) => note.id));
    const remaining = context.store.notes.filter((note) => !doomed.has(note.id));
    const removed = context.store.notes.length - remaining.length;
    context.store.notes = remaining;
    removedCount = removed;
    return json(200, { removed }, context);
  }, () => ({ op: "bulk-delete", ...removedCount === 0 ? {} : { removed: removedCount } }));
}
function handleRequest(request, context) {
  try {
    return routeRequest(request, context);
  } catch (error) {
    return toErrorResponse(error, context);
  }
}
function routeRequest(request, context) {
  const base = normalizeBase(context.base);
  const { pathname, query } = parseRequestUrl(request.url);
  const method = (request.method ?? "GET").toUpperCase();
  const rest = pathWithin(pathname, base);
  const segments = rest === null ? [] : splitSegments(rest);
  const allow = rest === null ? null : allowedMethods(segments);
  if (allow === null) {
    return errorResponse(404, "not_found", `unknown endpoint ${pathname} \u2014 the API lives under ${base || "/"}`, context);
  }
  if (method === "OPTIONS" && context.cors !== void 0 && context.cors !== "") {
    return { status: 204, headers: corsHeaders(context.cors), body: "" };
  }
  if (!allow.includes(method)) {
    const response = errorResponse(
      405,
      "method_not_allowed",
      `${method} is not allowed on ${pathname} \u2014 documented method(s): ${allow.join(", ")}`,
      context
    );
    response.headers.allow = allow.join(", ");
    return response;
  }
  if (context.readOnly === true && method !== "GET") {
    return errorResponse(
      403,
      "read_only",
      "this sidecar runs read-only (--read-only) \u2014 writes are refused",
      context
    );
  }
  const first = segments[0];
  if (first === "health") return health(context);
  if (first === "notes") {
    if (segments.length === 1) {
      return method === "GET" ? listNotes(query, context) : createNoteFromBody(request, context);
    }
    if (segments.length === 2) {
      const second = segments[1] ?? "";
      return second === "bulk-delete" ? bulkDelete(request, context) : patchNote(second, request, context);
    }
    return appendMessageToNote(segments[1] ?? "", request, context);
  }
  if (first === "sessions") {
    try {
      return json(200, { sessions: bundleOf(context).sessions }, context);
    } catch (error) {
      return toErrorResponse(error, context);
    }
  }
  if (first === "bundle") {
    try {
      return {
        status: 200,
        headers: { "content-type": JSON_CONTENT_TYPE, "cache-control": "no-store", ...corsHeaders(context.cors) },
        body: bundleToJson(bundleOf(context), { pretty: true })
      };
    } catch (error) {
      return toErrorResponse(error, context);
    }
  }
  return errorResponse(404, "not_found", `unknown endpoint ${pathname}`, context);
}

// server/journal.ts
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { appendFileSync, existsSync, mkdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
var JOURNAL_AUTHOR_ENV = "BLUEPENCIL_JOURNAL_AUTHOR";
var JOURNAL_SUBJECT_ENV = "BLUEPENCIL_JOURNAL_SUBJECT";
function envValue(name) {
  const value = process.env[name];
  return value === void 0 || value.trim() === "" ? void 0 : value.trim();
}
var FILE_NAME = "journal.jsonl";
var DEFAULT_SUBJECT = "chore(notes): {count} change(s) in {app}";
var DEFAULT_COALESCE_MS = 2e3;
var defaultRun = (command, args, options) => {
  const result = spawnSync(command, args, { encoding: "utf8", ...options, stdio: ["ignore", "pipe", "pipe"] });
  return {
    status: result.status,
    stdout: typeof result.stdout === "string" ? result.stdout : "",
    stderr: typeof result.stderr === "string" ? result.stderr : ""
  };
};
function oneLine2(value) {
  return value.replace(/\s+/g, " ").trim();
}
function hashOf(entry2) {
  const canonical = JSON.stringify([
    entry2.seq,
    entry2.ts,
    entry2.op,
    entry2.noteId ?? "",
    entry2.actor ?? "",
    entry2.summary,
    entry2.prevHash
  ]);
  return createHash("sha256").update(canonical).digest("hex");
}
function isInsideWorkTree(dir, run = defaultRun) {
  const result = run("git", ["-C", dir, "rev-parse", "--is-inside-work-tree"], { stdio: "ignore" });
  return result.status === 0 && result.stdout.trim() === "true";
}
var FileJournal = class _FileJournal {
  backend = "file";
  #path;
  #now;
  #onError;
  #entries = 0;
  #lastSeq = 0;
  #prevHash = "";
  #issue;
  constructor(options, path) {
    this.#path = path;
    this.#now = options.now ?? (() => (/* @__PURE__ */ new Date()).toISOString());
    this.#onError = options.onError ?? (() => void 0);
    mkdirSync(dirname(this.#path), { recursive: true });
    const existing = this.read();
    const last = existing.entries[existing.entries.length - 1];
    if (last !== void 0) {
      this.#lastSeq = last.seq;
      this.#prevHash = last.hash;
    }
    if (existing.issue !== void 0) {
      this.#issue = existing.issue;
    }
  }
  get path() {
    return this.#path;
  }
  /** A fresh journal at `dir`, or `undefined` when the directory cannot be written. */
  static open(options, dir) {
    const path = join(dir, FILE_NAME);
    try {
      mkdirSync(dir, { recursive: true });
      return new _FileJournal(options, path);
    } catch (error) {
      (options.onError ?? (() => void 0))(
        `journal: cannot use ${path} \u2014 ${error instanceof Error ? error.message : String(error)}`
      );
      return void 0;
    }
  }
  record(record) {
    const base = {
      seq: this.#lastSeq + 1,
      ts: this.#now(),
      op: record.op,
      ...record.noteId === void 0 ? {} : { noteId: record.noteId },
      ...record.actor === void 0 ? {} : { actor: record.actor },
      summary: oneLine2(record.summary),
      prevHash: this.#prevHash
    };
    const entry2 = { ...base, hash: hashOf(base) };
    try {
      appendFileSync(this.#path, `${JSON.stringify(entry2)}
`, "utf8");
      this.#lastSeq = entry2.seq;
      this.#prevHash = entry2.hash;
      this.#entries += 1;
    } catch (error) {
      this.#fail(`cannot append ${this.#path} \u2014 ${error instanceof Error ? error.message : String(error)}`);
    }
  }
  flush() {
  }
  read(since = 0) {
    if (!existsSync(this.#path)) {
      return { entries: [] };
    }
    let text;
    try {
      text = readFileSync(this.#path, "utf8");
    } catch (error) {
      return { entries: [], issue: `cannot read ${this.#path} \u2014 ${error instanceof Error ? error.message : String(error)}` };
    }
    const entries = [];
    const lines = text.split("\n");
    for (let index = 0; index < lines.length; index += 1) {
      const line = lines[index];
      if (line === void 0 || line.trim() === "") continue;
      try {
        const parsed = JSON.parse(line);
        if (typeof parsed.seq === "number" && parsed.seq > since) entries.push(parsed);
      } catch {
        return { entries, issue: `line ${index + 1} of ${this.#path} is not valid JSON` };
      }
    }
    return { entries };
  }
  verify() {
    const read = this.read();
    if (read.issue !== void 0) {
      return { ok: false, entries: read.entries.length, issue: read.issue };
    }
    let prevHash = "";
    let expectedSeq = 1;
    for (const entry2 of read.entries) {
      if (entry2.seq !== expectedSeq) {
        return { ok: false, entries: read.entries.length, issue: `sequence gap at ${entry2.seq} (expected ${expectedSeq})` };
      }
      if (entry2.prevHash !== prevHash) {
        return { ok: false, entries: read.entries.length, issue: `broken chain at ${entry2.seq}` };
      }
      const { hash, ...rest } = entry2;
      if (hashOf(rest) !== hash) {
        return { ok: false, entries: read.entries.length, issue: `entry ${entry2.seq} was modified` };
      }
      prevHash = hash;
      expectedSeq += 1;
    }
    return { ok: true, entries: read.entries.length };
  }
  status() {
    return {
      backend: "file",
      location: this.#path,
      entries: this.#entries,
      lastSeq: this.#lastSeq,
      ...this.#issue === void 0 ? {} : { issue: this.#issue }
    };
  }
  /** Config problems are reported once — an operator has to see them, a request must not fail. */
  #fail(message) {
    if (this.#issue !== message) {
      this.#issue = message;
      this.#onError(`journal: ${message}`);
    }
  }
};
var GitJournal = class {
  backend = "git";
  #repo;
  #paths;
  #run;
  #coalesceMs;
  #author;
  #subject;
  #appName;
  #setTimeout;
  #clearTimeout;
  #onError;
  #pending = [];
  #timer = null;
  #entries = 0;
  #lastSeq = 0;
  #issue;
  constructor(options, repo, paths) {
    this.#repo = repo;
    this.#paths = paths;
    this.#run = options.run ?? defaultRun;
    this.#coalesceMs = options.coalesceMs ?? DEFAULT_COALESCE_MS;
    this.#subject = options.subjectTemplate ?? envValue(JOURNAL_SUBJECT_ENV) ?? DEFAULT_SUBJECT;
    this.#appName = options.appName ?? "bluepencil";
    this.#setTimeout = options.setTimeoutImpl ?? ((fn, ms) => setTimeout(fn, ms));
    this.#clearTimeout = options.clearTimeoutImpl ?? ((handle) => clearTimeout(handle));
    this.#onError = options.onError ?? (() => void 0);
    this.#author = parseAuthor(options.author ?? envValue(JOURNAL_AUTHOR_ENV));
  }
  record(record) {
    this.#pending.push(record);
    if (this.#coalesceMs <= 0) {
      this.flush();
      return;
    }
    if (this.#timer !== null) return;
    this.#timer = this.#setTimeout(() => {
      this.#timer = null;
      this.flush();
    }, this.#coalesceMs);
  }
  /** Stages and commits the pending batch. Safe to call at any time, including with an empty batch. */
  flush() {
    if (this.#timer !== null) {
      this.#clearTimeout(this.#timer);
      this.#timer = null;
    }
    const batch = this.#pending;
    this.#pending = [];
    if (batch.length === 0) return;
    const add = this.#run("git", ["-C", this.#repo, "add", ...this.#paths], { stdio: "ignore" });
    if (add.status !== 0) {
      this.#fail(`git add failed \u2014 ${oneLine2(add.stderr) || `exit ${add.status}`}`);
      return;
    }
    const diff = this.#run("git", ["-C", this.#repo, "diff", "--cached", "--quiet", "--", ...this.#paths], { stdio: "ignore" });
    if (diff.status === 0) return;
    const subject = this.#subject.replace(/\{count\}/g, String(batch.length)).replace(/\{op\}/g, batch[batch.length - 1]?.op ?? "update").replace(/\{app\}/g, this.#appNameText());
    const env = { ...process.env };
    if (this.#author !== void 0) {
      env.GIT_AUTHOR_NAME = this.#author.name;
      env.GIT_AUTHOR_EMAIL = this.#author.email;
      env.GIT_COMMITTER_NAME = this.#author.name;
      env.GIT_COMMITTER_EMAIL = this.#author.email;
    }
    const commit = this.#run("git", ["-C", this.#repo, "commit", "-q", "--only", "-m", oneLine2(subject), "--", ...this.#paths], {
      stdio: "ignore",
      env
    });
    if (commit.status !== 0) {
      this.#fail(`git commit failed \u2014 ${oneLine2(commit.stderr) || `exit ${commit.status}`}`);
      return;
    }
    this.#entries += 1;
    this.#lastSeq += 1;
  }
  /** The commit subjects this server wrote, newest last — the git equivalent of the entry list. */
  read(since = 0) {
    const limit = Math.max(0, this.#entries - since);
    if (limit === 0) return { entries: [] };
    const log = this.#run(
      "git",
      ["-C", this.#repo, "log", "-n", String(limit), "--format=%H%x09%cI%x09%s", "--", ...this.#paths],
      { stdio: "ignore" }
    );
    if (log.status !== 0) {
      return { entries: [], issue: `git log failed \u2014 ${oneLine2(log.stderr) || `exit ${log.status}`}` };
    }
    const entries = [];
    const lines = log.stdout.trim().split("\n").filter((line) => line.trim() !== "");
    lines.reverse().forEach((line, index) => {
      const [hash = "", ts = "", ...rest] = line.split("	");
      entries.push({
        seq: since + index + 1,
        ts,
        op: "update",
        summary: rest.join("	"),
        hash,
        prevHash: ""
      });
    });
    return { entries };
  }
  verify() {
    const rev = this.#run("git", ["-C", this.#repo, "rev-parse", "--is-inside-work-tree"], { stdio: "ignore" });
    if (rev.status !== 0 || rev.stdout.trim() !== "true") {
      return { ok: false, entries: this.#entries, issue: `${this.#repo} is not a git work tree` };
    }
    const fsck = this.#run("git", ["-C", this.#repo, "rev-parse", "--verify", "HEAD"], { stdio: "ignore" });
    return { ok: true, entries: this.#entries, ...fsck.status === 0 ? {} : { issue: "the repository has no commit yet" } };
  }
  status() {
    return {
      backend: "git",
      location: this.#repo,
      entries: this.#entries,
      lastSeq: this.#lastSeq,
      // Visible here instead of only in `git log`: the first question about an unexpected commit.
      author: this.#author === void 0 ? "(the repository's configured identity)" : `${this.#author.name} <${this.#author.email}>`,
      ...this.#issue === void 0 ? {} : { issue: this.#issue }
    };
  }
  #appNameText() {
    return this.#appName;
  }
  #fail(message) {
    this.#issue = message;
    this.#onError(`journal: ${message}`);
  }
};
function parseAuthor(value) {
  if (value === void 0 || value.trim() === "") return void 0;
  const match = /^(.*?)\s*<([^>]+)>\s*$/.exec(value);
  if (match === null) return { name: value.trim(), email: value.trim() };
  return { name: (match[1] ?? "").trim(), email: (match[2] ?? "").trim() };
}
var NoJournal = class {
  backend = "none";
  #reason;
  constructor(reason) {
    this.#reason = reason;
  }
  record() {
  }
  flush() {
  }
  read() {
    return { entries: [] };
  }
  verify() {
    return { ok: true, entries: 0, ...this.#reason === void 0 ? {} : { issue: this.#reason } };
  }
  status() {
    return { backend: "none", entries: 0, lastSeq: 0, ...this.#reason === void 0 ? {} : { issue: this.#reason } };
  }
};
function selectJournal(options) {
  const requested = options.backend ?? "auto";
  if (requested === "none") return new NoJournal();
  const dir = options.dir ?? dirname(options.storePath);
  if (requested === "file") return FileJournal.open(options, dir) ?? new NoJournal("the journal file could not be created");
  const repo = options.repo ?? dir;
  const insideWorkTree = isInsideWorkTree(repo, options.run ?? defaultRun);
  if (requested === "git") {
    return insideWorkTree ? new GitJournal(options, repo, options.paths ?? [options.storePath]) : new NoJournal(`${repo} is not a git work tree`);
  }
  if (insideWorkTree) return new GitJournal(options, repo, options.paths ?? [options.storePath]);
  return FileJournal.open(options, dir) ?? new NoJournal("the journal file could not be created");
}

// server/index.ts
var DEFAULT_PORT = 8787;
var DEFAULT_HOST = "127.0.0.1";
var MAX_BODY_BYTES = 8 * 1024 * 1024;
var StoreFileError = class extends Error {
  constructor(message) {
    super(message);
    this.name = "StoreFileError";
  }
};
function resolveOptions(options) {
  return {
    storePath: options.storePath,
    port: options.port ?? DEFAULT_PORT,
    host: options.host ?? DEFAULT_HOST,
    base: normalizeBase(options.base ?? DEFAULT_BASE_PATH),
    root: options.root === void 0 ? void 0 : resolve(options.root),
    environment: options.environment ?? DEFAULT_ENVIRONMENT,
    readOnly: options.readOnly ?? false,
    allowEnvMismatch: options.allowEnvMismatch ?? false,
    mirror: options.mirror,
    cors: options.cors,
    quiet: options.quiet ?? false,
    appName: options.appName ?? SIDECAR_APP_NAME,
    exportedBy: options.exportedBy ?? SIDECAR_EXPORTED_BY,
    journal: options.journal ?? "auto",
    journalDir: options.journalDir,
    journalRepo: options.journalRepo,
    journalCoalesceMs: options.journalCoalesceMs,
    journalAuthor: options.journalAuthor,
    journalSubject: options.journalSubject,
    now: options.now
  };
}
function readTextIfExists(path) {
  try {
    return readFileSync2(path, "utf8");
  } catch (error) {
    if (error.code === "ENOENT") return null;
    throw new StoreFileError(`cannot read ${path}: ${errorText2(error)}`);
  }
}
function parseNoteSet(text, path) {
  if (text === null) return [];
  if (text.trim() === "") {
    throw new StoreFileError(`${path} is not a valid note set: the file is empty`);
  }
  let parsed;
  try {
    parsed = JSON.parse(text);
  } catch (error) {
    throw new StoreFileError(`${path} is not a valid note set: the file is not valid JSON (${errorText2(error)})`);
  }
  const record = isRecord(parsed) ? parsed : null;
  const looksLikeNoteSet = Array.isArray(parsed) || record !== null && (Array.isArray(record.notes) || record.kind === BUNDLE_KIND);
  if (!looksLikeNoteSet) {
    throw new StoreFileError(
      `${path} is not a valid note set: expected a bluepencil bundle (kind "${BUNDLE_KIND}") or an array of notes`
    );
  }
  const legacy = record === null || record.schemaVersion === void 0 || record.schemaVersion === null;
  try {
    return legacy ? migrateBundle(parsed).notes : assertBundle(parsed).notes;
  } catch (error) {
    throw new StoreFileError(`${path} is not a valid note set: ${errorText2(error)}`);
  }
}
function loadNotes(path) {
  return parseNoteSet(readTextIfExists(path), path);
}
var writeCounter = 0;
function writeAtomic(path, text) {
  writeCounter += 1;
  const tmp = join2(dirname2(path), `.${basename(path)}.tmp-${process.pid}-${writeCounter}`);
  try {
    writeFileSync(tmp, text, "utf8");
    renameSync(tmp, path);
  } finally {
    rmSync(tmp, { force: true });
  }
}
function createFileStore(options) {
  const state = { notes: loadNotes(options.storePath) };
  const appName = options.appName ?? SIDECAR_APP_NAME;
  const bundleText = (current) => bundleToJson(
    createBundle(current.notes, {
      environment: options.environment,
      app: { name: appName },
      exportedBy: options.exportedBy ?? SIDECAR_EXPORTED_BY,
      ...options.now !== void 0 ? { now: options.now() } : {}
    }),
    { pretty: true }
  );
  return {
    state,
    bundleText: (current = state) => bundleText(current),
    mirrorText: (current = state) => options.mirror === void 0 ? null : toMarkdown(current.notes, { includeDone: true, title: `${appName} review notes` }),
    persist: (current = state) => {
      writeAtomic(options.storePath, bundleText(current));
      if (options.mirror !== void 0) {
        writeAtomic(options.mirror, toMarkdown(current.notes, { includeDone: true, title: `${appName} review notes` }));
      }
    }
  };
}
var CONTENT_TYPES = {
  ".html": "text/html; charset=utf-8",
  ".htm": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".map": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".gif": "image/gif",
  ".webp": "image/webp",
  ".avif": "image/avif",
  ".ico": "image/x-icon",
  ".woff": "font/woff",
  ".woff2": "font/woff2",
  ".ttf": "font/ttf",
  ".txt": "text/plain; charset=utf-8",
  ".md": "text/markdown; charset=utf-8",
  ".wasm": "application/wasm"
};
function contentTypeOf(path) {
  return CONTENT_TYPES[extname(path).toLowerCase()] ?? "application/octet-stream";
}
function isInside(root, candidate) {
  return candidate === root || candidate.startsWith(`${root}${sep}`);
}
function findStaticFile(root, relative) {
  const resolved = resolve(root, relative.replace(/^\/+/, ""));
  if (!isInside(root, resolved)) return null;
  for (const candidate of [resolved, join2(resolved, "index.html"), join2(root, "index.html")]) {
    if (!isInside(root, candidate)) continue;
    try {
      if (statSync(candidate).isFile()) return candidate;
    } catch {
    }
  }
  return null;
}
function write(response, result) {
  response.writeHead(result.status, result.headers);
  response.end(result.body);
}
function errorText2(error) {
  return error instanceof Error ? error.message : String(error);
}
function oneLine3(value) {
  return value.replace(/\s+/g, " ").trim();
}
function glueError(status, code2, message, options) {
  return {
    status,
    headers: { "content-type": JSON_CONTENT_TYPE, ...corsHeaders(options.cors) },
    body: errorBody(code2, message)
  };
}
var BodyTooLargeError = class extends Error {
};
function readBody(request, limit) {
  return new Promise((resolvePromise, rejectPromise) => {
    const declared = Number(request.headers["content-length"] ?? NaN);
    if (Number.isFinite(declared) && declared > limit) {
      request.resume();
      rejectPromise(new BodyTooLargeError(`the request body exceeds ${limit} bytes`));
      return;
    }
    const chunks = [];
    let size = 0;
    let tooLarge = false;
    request.on("data", (chunk) => {
      size += chunk.length;
      if (size > limit) {
        tooLarge = true;
        chunks.length = 0;
        return;
      }
      chunks.push(chunk);
    });
    request.on("end", () => {
      if (tooLarge) rejectPromise(new BodyTooLargeError(`the request body exceeds ${limit} bytes`));
      else resolvePromise(Buffer.concat(chunks).toString("utf8"));
    });
    request.on("error", (error) => rejectPromise(error));
  });
}
function serveStatic(url, method, options, response) {
  const pathname = requestPath(url);
  if (method === "OPTIONS" && options.cors !== void 0 && options.cors !== "") {
    write(response, { status: 204, headers: corsHeaders(options.cors), body: "" });
    return;
  }
  if (method !== "GET" && method !== "HEAD") {
    write(
      response,
      glueError(405, "method_not_allowed", `${method} is not allowed on ${pathname} \u2014 documented method(s): GET, HEAD`, options)
    );
    return;
  }
  let relative;
  try {
    relative = decodeURIComponent(pathname);
  } catch {
    relative = pathname;
  }
  const root = options.root ?? ".";
  const file = findStaticFile(root, relative);
  if (file === null) {
    write(response, {
      status: 404,
      headers: { "content-type": "text/plain; charset=utf-8", ...corsHeaders(options.cors) },
      body: "not found\n"
    });
    return;
  }
  let body;
  try {
    body = readFileSync2(file);
  } catch (error) {
    write(response, glueError(500, "internal_error", `cannot read ${file}: ${errorText2(error)}`, options));
    return;
  }
  write(response, {
    status: 200,
    headers: {
      "content-type": contentTypeOf(file),
      "content-length": String(body.byteLength),
      ...corsHeaders(options.cors)
    },
    body
  });
}
var activeJournal = null;
function describeMutation(state, event) {
  const op = event?.op ?? "update";
  const removed = event?.removed;
  const detail = op === "bulk-delete" && removed !== void 0 ? `bulk-delete ${removed} note(s)` : `${op}${event?.noteId === void 0 ? "" : ` ${event.noteId}`}`;
  return {
    op,
    ...event?.noteId === void 0 ? {} : { noteId: event.noteId },
    summary: `${detail} \u2014 ${state.notes.length} note(s) in the set`
  };
}
function journalPathOf(base) {
  return base === "" ? "/journal" : `${base}/journal`;
}
function journalResponse(method, url, journal, options) {
  if (method !== "GET") {
    return glueError(405, "method_not_allowed", `${method} is not allowed on the journal \u2014 use GET`, options);
  }
  let since = 0;
  const query = url.indexOf("?");
  if (query !== -1) {
    const raw = new URLSearchParams(url.slice(query + 1)).get("since");
    if (raw !== null) {
      const parsed = Number(raw);
      if (!Number.isInteger(parsed) || parsed < 0) {
        return glueError(400, "invalid_query", `since must be a non-negative integer (got ${JSON.stringify(raw)})`, options);
      }
      since = parsed;
    }
  }
  const read = journal.read(since);
  const status = journal.status();
  return {
    status: 200,
    headers: { "content-type": JSON_CONTENT_TYPE, ...corsHeaders(options.cors) },
    body: JSON.stringify({
      journal: status,
      ...read.issue === void 0 ? {} : { issue: read.issue },
      entries: read.entries
    })
  };
}
async function respond(request, response, options, context, journal) {
  const url = request.url ?? "/";
  const method = (request.method ?? "GET").toUpperCase();
  if (requestPath(url) === journalPathOf(options.base)) {
    write(response, journalResponse(method, url, journal, options));
    return;
  }
  if (options.root !== void 0 && !isApiPath(url, context.base)) {
    serveStatic(url, method, options, response);
    return;
  }
  let body = "";
  try {
    body = await readBody(request, MAX_BODY_BYTES);
  } catch (error) {
    const tooLarge = error instanceof BodyTooLargeError;
    write(
      response,
      tooLarge ? glueError(413, "payload_too_large", oneLine3(errorText2(error)), options) : glueError(400, "invalid_json", `the request body could not be read: ${errorText2(error)}`, options)
    );
    return;
  }
  write(
    response,
    handleRequest(
      { method, url, headers: request.headers, body },
      context
    )
  );
}
async function startServer(options) {
  const resolved = resolveOptions(options);
  const journal = selectJournal({
    backend: resolved.journal,
    storePath: resolved.storePath,
    ...resolved.journalDir === void 0 ? {} : { dir: resolved.journalDir },
    ...resolved.journalRepo === void 0 ? {} : { repo: resolved.journalRepo },
    ...resolved.journalCoalesceMs === void 0 ? {} : { coalesceMs: resolved.journalCoalesceMs },
    ...resolved.journalAuthor === void 0 ? {} : { author: resolved.journalAuthor },
    ...resolved.journalSubject === void 0 ? {} : { subjectTemplate: resolved.journalSubject },
    appName: resolved.appName,
    paths: [resolved.storePath, ...resolved.mirror === void 0 ? [] : [resolved.mirror]],
    onError: (message) => {
      if (!resolved.quiet) process.stderr.write(`bluepencil server: ${oneLine3(message)}
`);
    }
  });
  activeJournal = journal;
  const store = createFileStore({
    ...resolved.mirror !== void 0 ? { mirror: resolved.mirror } : {},
    storePath: resolved.storePath,
    environment: resolved.environment,
    appName: resolved.appName,
    exportedBy: resolved.exportedBy,
    ...resolved.now !== void 0 ? { now: resolved.now } : {}
  });
  const context = {
    store: store.state,
    base: resolved.base,
    environment: resolved.environment,
    readOnly: resolved.readOnly,
    allowEnvMismatch: resolved.allowEnvMismatch,
    version: SERVER_VERSION,
    appName: resolved.appName,
    exportedBy: resolved.exportedBy,
    ...resolved.cors !== void 0 ? { cors: resolved.cors } : {},
    ...resolved.now !== void 0 ? { now: resolved.now } : {},
    persist: (state, event) => {
      store.persist(state);
      journal.record(describeMutation(state, event));
    }
  };
  const server = createServer((request, response) => {
    respond(request, response, resolved, context, journal).catch((error) => {
      if (response.headersSent) {
        response.end();
        return;
      }
      write(response, glueError(500, "internal_error", errorText2(error), resolved));
    });
  });
  await new Promise((resolvePromise, rejectPromise) => {
    const onStartupError = (error) => rejectPromise(error);
    server.once("error", onStartupError);
    server.listen(resolved.port, resolved.host, () => {
      server.off("error", onStartupError);
      server.on("error", (error) => {
        if (!resolved.quiet) process.stderr.write(`bluepencil server: ${oneLine3(errorText2(error))}
`);
      });
      resolvePromise();
    });
  });
  const address = server.address();
  const port = address !== null && typeof address === "object" ? address.port : resolved.port;
  if (!resolved.quiet) {
    process.stderr.write(
      `bluepencil server: http://${resolved.host}:${port}${resolved.base || "/"} \u2014 ${store.state.notes.length} note(s), environment ${resolved.environment}, ${resolved.readOnly ? "read-only" : "read-write"}, store ${resolved.storePath}
`
    );
  }
  return {
    server,
    host: resolved.host,
    port,
    url: `http://${resolved.host}:${port}${resolved.base}`,
    close: () => new Promise((resolvePromise, rejectPromise) => {
      server.close((error) => error ? rejectPromise(error) : resolvePromise());
    })
  };
}
function parseServerArgs(argv) {
  const get = (flag) => {
    const withEquals = argv.find((arg) => arg.startsWith(`${flag}=`));
    if (withEquals !== void 0) return withEquals.slice(flag.length + 1);
    const index = argv.indexOf(flag);
    if (index < 0) return void 0;
    const next = argv[index + 1];
    return next !== void 0 && !next.startsWith("--") ? next : void 0;
  };
  const has = (flag) => argv.includes(flag);
  const storePath = get("--store") ?? process.env.BLUEPENCIL_STORE ?? "";
  if (storePath === "") {
    return "--store <path> is required (the canonical bundle JSON the notes live in)";
  }
  const portRaw = get("--port");
  let port = DEFAULT_PORT;
  if (portRaw !== void 0) {
    const parsed = Number(portRaw);
    if (!Number.isInteger(parsed) || parsed < 0 || parsed > 65535) {
      return `--port must be an integer between 0 and 65535 (got ${JSON.stringify(portRaw)})`;
    }
    port = parsed;
  }
  const environment = get("--environment") ?? process.env.BLUEPENCIL_ENVIRONMENT ?? DEFAULT_ENVIRONMENT;
  if (!isEnvironment(environment)) {
    return `--environment must be one of ${ENVIRONMENTS.join(", ")} (got ${JSON.stringify(environment)})`;
  }
  const root = get("--root");
  const mirror = get("--mirror");
  const host = get("--host");
  const base = get("--base");
  const journalRaw = get("--journal") ?? process.env.BLUEPENCIL_JOURNAL;
  if (journalRaw !== void 0 && !["auto", "git", "file", "none"].includes(journalRaw)) {
    return `--journal must be one of auto, git, file, none (got ${JSON.stringify(journalRaw)})`;
  }
  const coalesceRaw = get("--journal-coalesce");
  let journalCoalesceMs;
  if (coalesceRaw !== void 0) {
    const parsed = Number(coalesceRaw);
    if (!Number.isInteger(parsed) || parsed < 0) {
      return `--journal-coalesce must be a non-negative integer (got ${JSON.stringify(coalesceRaw)})`;
    }
    journalCoalesceMs = parsed;
  }
  const cors = argv.some((arg) => arg === "--cors" || arg.startsWith("--cors=")) ? get("--cors") ?? "*" : void 0;
  return {
    storePath,
    port,
    ...host !== void 0 ? { host } : {},
    ...base !== void 0 ? { base } : {},
    ...root !== void 0 ? { root } : {},
    environment,
    readOnly: has("--read-only"),
    allowEnvMismatch: has("--allow-env-mismatch"),
    ...mirror !== void 0 ? { mirror } : {},
    ...cors !== void 0 ? { cors } : {},
    ...journalRaw !== void 0 ? { journal: journalRaw } : {},
    ...get("--journal-dir") === void 0 ? {} : { journalDir: get("--journal-dir") },
    ...get("--journal-repo") === void 0 ? {} : { journalRepo: get("--journal-repo") },
    ...journalCoalesceMs === void 0 ? {} : { journalCoalesceMs },
    ...get("--journal-author") === void 0 ? {} : { journalAuthor: get("--journal-author") },
    ...get("--journal-subject") === void 0 ? {} : { journalSubject: get("--journal-subject") },
    quiet: has("--quiet")
  };
}
var HELP = `bluepencil sidecar ${SERVER_VERSION} \u2014 static site + notes API on one port.

Usage:
  node dist/server.js --store notes.json [--port 8787] [--host 127.0.0.1]
    [--base /api/v1/bluepencil] [--root <static dir>] [--environment dev|staging|live]
    [--read-only] [--allow-env-mismatch] [--mirror notes.md] [--cors <origin|*>] [--quiet]
    [--journal auto|git|file|none] [--journal-dir <dir>] [--journal-repo <dir>]
    [--journal-coalesce <ms>] [--journal-author "Name <mail>"] [--journal-subject "<template>"]
      env: BLUEPENCIL_JOURNAL (backend), BLUEPENCIL_JOURNAL_AUTHOR, BLUEPENCIL_JOURNAL_SUBJECT
      a flag wins over the env; without an author the commits carry the repository's identity,
      and the journal status reports which identity is in use

Endpoints (base defaults to /api/v1/bluepencil \u2014 the default of the built-in http adapter):
  GET    {base}/health              { ok, status, version }
  GET    {base}/notes               filters: route, intent, type, session, source, environment,
                                    includeDone, since, repeated status  \u2192 { notes }
  POST   {base}/notes               NoteDraft JSON                     \u2192 { note }
  PATCH  {base}/notes/{id}          note fields only                   \u2192 { note }
  POST   {base}/notes/{id}/messages { id, ts, text, author, author_type, kind } \u2192 { note }
  POST   {base}/notes/bulk-delete   { ids? , filter?, confirm: true }  \u2192 { removed }
  GET    {base}/sessions            \u2192 { sessions }
  GET    {base}/bundle              canonical bundle (src/data) \u2014 for agents/exports
  GET    {base}/journal             history: { journal: {backend, location, entries, lastSeq},
                                    entries } \u2014 optional ?since=<seq> for agents (FR-18)

Rules: bulk-delete requires "confirm": true; an unknown id is 404; a malformed body is 400; a body
that is not application/json is 415; a known path with the wrong method is 405; every error is
{"error":{"code","message"}}. --read-only refuses every write (403). The sidecar is bound to ONE
environment: a write that names another one is refused (400) unless --allow-env-mismatch promotes
it (FR-14.8). The store file is canonical bundle JSON, written atomically; a corrupt store file
refuses the start (exit 2) instead of being served as an empty set. --root serves a static
directory with an index.html fallback on the same origin. --cors is off by default.

Journal (FR-18): the sidecar keeps a history of every accepted mutation. --journal auto (default)
commits through the surrounding git work tree when there is one (staged paths, empty diffs skipped,
batched over --journal-coalesce ms, default 2000) and otherwise appends to a hash-chained
journal.jsonl next to the store; --journal none switches the history off. A journal failure never
fails a request: it is reported once on stderr and stays visible in GET {base}/journal.

Exit codes: 0 serving ended normally, 1 usage error, 2 the store file is not a valid note set.`;
function fail(message, code2) {
  process.stderr.write(`bluepencil server: ${oneLine3(message)}
`);
  process.exit(code2);
}
async function main(argv) {
  if (argv.includes("--help") || argv.includes("-h")) {
    process.stdout.write(`${HELP}
`);
    return;
  }
  if (argv.includes("--version")) {
    process.stdout.write(`${SERVER_VERSION}
`);
    return;
  }
  const parsed = parseServerArgs(argv);
  if (typeof parsed === "string") {
    fail(parsed, 1);
  }
  const flushAndExit = (signal) => {
    activeJournal?.flush();
    if (!argv.includes("--quiet")) {
      process.stderr.write(`bluepencil server: ${signal} \u2014 journal flushed
`);
    }
    process.exit(0);
  };
  process.once("SIGINT", () => flushAndExit("SIGINT"));
  process.once("SIGTERM", () => flushAndExit("SIGTERM"));
  try {
    await startServer(parsed);
  } catch (error) {
    fail(errorText2(error), error instanceof StoreFileError ? 2 : 1);
  }
}
var entry = process.argv[1];
if (entry !== void 0 && import.meta.url === pathToFileURL(entry).href) {
  void main(process.argv.slice(2));
}
export {
  DEFAULT_HOST,
  DEFAULT_PORT,
  MAX_BODY_BYTES,
  StoreFileError,
  createFileStore,
  loadNotes,
  parseNoteSet,
  parseServerArgs,
  startServer
};
//# sourceMappingURL=server.js.map
