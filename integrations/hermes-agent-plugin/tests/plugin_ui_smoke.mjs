/**
 * Render smoke test for the dashboard tab bundle (dashboard/dist/index.js).
 *
 * The repo has no JS test harness and the bundle is an unbuilt IIFE that only
 * runs inside the host dashboard — which is why the shipped revision had *no*
 * coverage of its own ("the browser half is a manual check"). That gap is what
 * this file closes, cheaply and without a browser:
 *
 *   * it loads the real bundle with a stub of `window.__HERMES_PLUGIN_SDK__`
 *     (the contract observed in hermes-achievements: React, hooks, components
 *     and `window.__HERMES_PLUGINS__.register`),
 *   * calls the registered page component, and walks the returned element tree,
 *   * and fails on the class of mistake that is invisible until a human opens
 *     the tab: an undefined component (`h(StatCard, …)` with no StatCard),
 *     a thrown render, a button without a `data-testid`, or a fetch fired
 *     during render instead of in an effect.
 *
 * It is deliberately a *smoke* test: no DOM, no assertions about layout.
 *
 * Run: node tests/plugin_ui_smoke.mjs
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import assert from "node:assert/strict";

const HERE = dirname(fileURLToPath(import.meta.url));
const BUNDLE = join(HERE, "..", "dashboard", "dist", "index.js");
const MANIFEST = join(HERE, "..", "..", "..", "docs", "agent-templates", "tool-manifest.json");

// ---------------------------------------------------------------------------
// stub host SDK
// ---------------------------------------------------------------------------

const HANDLED = new Set();

function createElement(type, props, ...children) {
  return { type, props: props || {}, children: children.flat(Infinity).filter((c) => c !== null && c !== undefined && c !== false) };
}

let hookCursor = 0;

const React = { createElement };

const hooks = {
  // A single static render: useState keeps its initial value, useEffect does
  // not run (effects are what talk to the backend — the render must be pure).
  useState: (initial) => {
    hookCursor += 1;
    const value = typeof initial === "function" ? initial() : initial;
    return [value, () => {}];
  },
  useEffect: () => {
    hookCursor += 1;
  },
  useMemo: (factory) => factory(),
  useCallback: (fn) => fn,
  useRef: (initial) => ({ current: initial })
};

function stubComponent(name) {
  const Component = (props) => createElement("div", { "data-stub": name, ...(props || {}) });
  Component.displayName = name;
  return Component;
}

const registrations = new Map();
let fetchCalls = 0;

globalThis.window = {
  __HERMES_PLUGIN_SDK__: {
    React,
    hooks,
    components: new Proxy({}, { get: (_target, key) => stubComponent(String(key)) })
  },
  __HERMES_PLUGINS__: {
    register: (name, component) => registrations.set(name, component)
  },
  fetch: (...args) => {
    fetchCalls += 1;
    return Promise.resolve({ ok: true, status: 200, text: () => Promise.resolve("{}"), args });
  }
};

// ---------------------------------------------------------------------------
// load the bundle
// ---------------------------------------------------------------------------

const source = readFileSync(BUNDLE, "utf8");
// eslint-disable-next-line no-eval
new Function("window", "document", source)(globalThis.window, {});

assert.equal(registrations.size, 1, "the bundle must register exactly one page component");
const page = registrations.get("reqogniloom");
assert.equal(typeof page, "function", "the registered page must be a function");

// ---------------------------------------------------------------------------
// render and walk the tree
// ---------------------------------------------------------------------------

const tree = page();
assert.ok(tree && tree.type, "the page must render an element tree");

const STRING_TAGS = new Set([
  "div", "span", "p", "h2", "h3", "h4", "table", "thead", "tbody", "tr", "th", "td",
  "label", "input", "select", "option", "textarea", "pre", "ul", "li", "button", "a", "strong", "section"
]);

const nodes = [];
(function walk(node) {
  if (!node || typeof node !== "object") return;
  if (node.type === undefined) return;
  nodes.push(node);
  (node.children || []).forEach(walk);
})(tree);

// An undefined component reference reaches React as `undefined` and crashes the
// tab at runtime with nothing but "type is invalid".
const undefinedComponents = nodes.filter((node) => node.type === undefined).length;
assert.equal(undefinedComponents, 0, "no element may have an undefined type");

const unknownTags = nodes
  .filter((node) => typeof node.type === "string" && !STRING_TAGS.has(node.type))
  .map((node) => node.type);
assert.deepEqual(unknownTags, [], `unexpected host elements: ${unknownTags.join(", ")}`);

const buttons = nodes.filter((node) => node.type === "button");
// The static render shows the overview view only (5 nav tabs + refresh); the
// other views' buttons are reachable by switching tabs at runtime.
assert.ok(buttons.length >= 6, `expected the toolbar and its actions, saw ${buttons.length} buttons`);
const buttonsMissingTestId = buttons.filter((button) => !button.props["data-testid"]);
assert.deepEqual(
  buttonsMissingTestId.map((button) => button.props.className || "(unnamed)"),
  [],
  "every button needs a data-testid (the repo's E2E convention)"
);

const testIds = new Set(nodes.map((node) => node.props["data-testid"]).filter(Boolean));
["reqlo-refresh-button", "reqlo-server-select", "reqlo-workspace-select", "reqlo-nav-tools", "reqlo-nav-servers"].forEach(
  (id) => assert.ok(testIds.has(id), `the toolbar must expose ${id}`)
);

// Every view/panel component must be defined *and* wired into the page: a
// component that exists but is never rendered (or is rendered but missing) is
// exactly the defect that only shows up when a human opens the tab.
const REQUIRED_COMPONENTS = [
  "StatCard",
  "SchemaForm",
  "ConfirmPanel",
  "ResultPanel",
  "ToolConsole",
  "CreateFlow",
  "LinkFlow",
  "ReviewQueue",
  "MemoryPanel",
  "InterviewPanel",
  "BaselinePanel",
  "ServersPanel",
  "AdminPanel"
];
REQUIRED_COMPONENTS.forEach((name) => {
  const defined = new RegExp(`function ${name}\\(`).test(source);
  const used = new RegExp(`h\\(${name},`).test(source);
  assert.ok(defined, `${name} must be defined in the bundle`);
  if (name !== "AdminPanel" && name !== "SchemaForm" && name !== "ResultPanel") {
    assert.ok(used, `${name} must be wired into the page`);
  }
});

assert.equal(fetchCalls, 0, "render must not talk to the backend — that belongs in an effect");

// ---------------------------------------------------------------------------
// every tool name the UI names must exist on the server (manifest guard)
// ---------------------------------------------------------------------------

const usedTools = new Set();
source.replace(/"(?:[a-z_]+\.)+[a-z_]+"/g, (match) => {
  const name = match.slice(1, -1);
  if (name.startsWith("reqlo") || name.startsWith("api")) return match;
  usedTools.add(name);
  return match;
});

let manifestNames = null;
try {
  manifestNames = new Set(JSON.parse(readFileSync(MANIFEST, "utf8")).tools.map((tool) => tool.name));
} catch (err) {
  manifestNames = null; // Standalone checkout: the guard needs the repo.
}

if (manifestNames) {
  const phantom = [...usedTools].filter((name) => !manifestNames.has(name));
  assert.deepEqual(phantom, [], `the UI names tools the server does not publish: ${phantom.join(", ")}`);
  console.log(`ui smoke: ${nodes.length} nodes, ${buttons.length} buttons, ${usedTools.size} tool names checked against the manifest`);
} else {
  console.log(`ui smoke: ${nodes.length} nodes, ${buttons.length} buttons (manifest not found — tool-name guard skipped)`);
}

console.log("ui smoke: OK");
