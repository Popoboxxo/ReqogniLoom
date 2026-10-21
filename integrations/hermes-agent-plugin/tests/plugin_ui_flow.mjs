// Functional test for the dashboard tab's argument building.
//
// Why this file exists: the static smoke test (plugin_ui_smoke.mjs) builds the
// element tree with a stub createElement that never *invokes* a component, so it
// cannot see anything that happens inside one. Two mutations survived it —
// removing the "only declared parameters" guard in `withWorkspace`, and seeding
// every declared property with "" — and the second one made 11 of the 12 create
// flows unusable (the preview refused `level: ""` as "expects an integer").
//
// This harness therefore runs the real components: createElement invokes function
// components, hooks keep their state across re-renders, effects run, and events
// are dispatched by calling the handlers the components actually wired. The
// assertion is on the *request body* the tab produces — the only place where the
// guard is observable.
//
// Run: node tests/plugin_ui_flow.mjs
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const bundlePath = path.join(here, "..", "dashboard", "dist", "index.js");
const manifestPath = path.join(here, "..", "..", "..", "docs", "agent-templates", "tool-manifest.json");

const failures = [];
function check(condition, message) {
  if (!condition) failures.push(message);
}

// --------------------------------------------------------------------------
// host SDK stub: real component invocation + hook state
// --------------------------------------------------------------------------

// Hook state is keyed per component *instance*, the way React does it: the key is
// the instance's position in the tree plus the hook's ordinal inside it. A single
// flat counter would let one view read a slot another view wrote — which silently
// produced empty arguments in this very test.
const hookState = new Map();
let hookCursor = 0;
let pendingEffects = [];
let rerenderRequested = false;
let pathStack = [""];
let ordinalCounters = new Map();

function hookKey() {
  return pathStack[pathStack.length - 1] + "#" + hookCursor++;
}

function useState(initial) {
  const key = hookKey();
  if (!hookState.has(key)) hookState.set(key, typeof initial === "function" ? initial() : initial);
  const setter = (value) => {
    const next = typeof value === "function" ? value(hookState.get(key)) : value;
    if (next !== hookState.get(key)) {
      hookState.set(key, next);
      rerenderRequested = true;
    }
  };
  return [hookState.get(key), setter];
}

const hooks = {
  useState,
  useRef: (initial) => {
    const key = hookKey();
    if (!hookState.has(key)) hookState.set(key, { current: initial });
    return hookState.get(key);
  },
  // Dependency arrays are honoured: an effect that re-runs on every render would
  // wipe form state the operator already typed.
  useEffect: (fn, deps) => {
    const key = hookKey();
    const previous = hookState.get(key + ":deps");
    const changed =
      previous === undefined ||
      !Array.isArray(deps) ||
      deps.length !== previous.length ||
      deps.some((value, position) => value !== previous[position]);
    hookState.set(key + ":deps", Array.isArray(deps) ? deps.slice() : []);
    if (changed) pendingEffects.push(fn);
  },
  useMemo: (fn) => fn(),
  useCallback: (fn) => fn,
};

function createElement(type, props, ...children) {
  const merged = Object.assign({}, props || {});
  if (children.length) merged.children = children.length === 1 ? children[0] : children;
  if (typeof type !== "function") return { type, props: merged };
  // Render it, like React does — with a path that identifies this instance so its
  // hooks keep their own slots.
  const parent = pathStack[pathStack.length - 1];
  const ordinal = ordinalCounters.get(parent) || 0;
  ordinalCounters.set(parent, ordinal + 1);
  const instancePath = parent + "/" + (type.name || "anon") + ordinal;
  const outerCursor = hookCursor;
  pathStack.push(instancePath);
  hookCursor = 0;
  try {
    return type(merged);
  } finally {
    pathStack.pop();
    hookCursor = outerCursor;
  }
}

const components = {
  Card: (props) => ({ type: "section", props: props || {} }),
  CardContent: (props) => ({ type: "div", props: props || {} }),
  ConfirmDialog: () => null,
};

// --------------------------------------------------------------------------
// transport stub: capture every request, answer from canned payloads
// --------------------------------------------------------------------------

const calls = [];
const CATALOGUE = [
  {
    name: "requirement.create",
    description: "Create one requirement.",
    inputSchema: {
      type: "object",
      properties: {
        workspace_id: { type: "string" },
        title: { type: "string" },
        level: { type: "integer" },
        custom_fields: { type: "object" },
        verification_method: { type: "string", enum: ["Test", "Review"] },
        dry_run: { type: "boolean" },
      },
      required: ["workspace_id", "title"],
    },
  },
  {
    // Declares no workspace_id — the tool that made the injection rule necessary.
    name: "traceability.create_link",
    description: "Link two artifacts.",
    inputSchema: {
      type: "object",
      properties: { source_id: { type: "string" }, target_id: { type: "string" } },
      required: ["source_id", "target_id"],
    },
  },
  {
    name: "link_type.list",
    description: "List link types.",
    inputSchema: { type: "object", properties: { workspace_id: { type: "string" } }, required: ["workspace_id"] },
  },
  {
    name: "review.list_pending",
    description: "Pending proposals.",
    inputSchema: { type: "object", properties: { workspace_id: { type: "string" } } },
  },
  {
    name: "memory.overview",
    description: "Memory counters.",
    inputSchema: { type: "object", properties: {} },
  },
];

// Routes whose answer a later scenario pins. The tab talks to several endpoints
// at once, so a scenario that needs one of them to fail has to be able to replace
// exactly that answer without disturbing the rest.
const overrides = new Map();

function canned(pathname) {
  for (const [prefix, payload] of overrides) {
    if (pathname.startsWith(prefix)) return payload;
  }
  if (pathname.endsWith("/servers")) {
    return {
      registry_version: 1,
      active: "qs",
      write_gate: true,
      path: "/tmp/servers.json",
      servers: [
        {
          id: "qs",
          name: "QS",
          base_url: "http://qs.test:8001",
          active: true,
          has_api_key: true,
          api_key_source: "file",
          has_user_api_key: true,
          user_api_key_source: "file",
          last_workspace_id: "ws-remembered",
          verify: { checked_at: "2026-01-01T00:00:00Z", reachable: true, auth_ok: true, tool_count: CATALOGUE.length },
        },
      ],
    };
  }
  if (pathname.endsWith("/version")) return { app_version: "1.8.0-beta.21", commit_short: "deadbeef" };
  if (pathname.includes("/workspaces")) {
    return {
      workspaces: [
        { id: "ws-1", name: "First" },
        { id: "ws-remembered", name: "Remembered" },
      ],
    };
  }
  // Echo the requested workspace back, like the server does: this is what makes
  // the workspace flow observable.
  const requested = /[?&]workspace_id=([^&]+)/.exec(pathname);
  const workspaceId = requested ? decodeURIComponent(requested[1]) : "";
  if (pathname.includes("/stats")) {
    return { workspace_id: workspaceId, requirements: 1, testcases: 2, open_interviews: 0 };
  }
  if (pathname.includes("/interviews")) return { workspace_id: workspaceId, interviews: [] };
  if (pathname.includes("/tools")) {
    return {
      server: "qs",
      cached: false,
      tool_count: CATALOGUE.length,
      groups: [{ name: "requirement", tool_count: 1 }],
      tools: CATALOGUE.map((tool) => ({
        name: tool.name,
        group: tool.name.split(".")[0],
        description: tool.description,
        class: tool.name === "requirement.create" ? "mutate" : "read",
        risk: tool.name === "requirement.create" ? "normal" : "none",
        requires_human: false,
        destructive: false,
        input_schema: tool.inputSchema,
      })),
    };
  }
  if (pathname.includes("/write/preview")) {
    return {
      tool: "__from_request__",
      server: "qs",
      risk: "normal",
      class: "mutate",
      blocked: false,
      write_gate: true,
      requires_human: false,
      human_key_available: true,
      problems: [],
      summary: "",
      confirm_token: "token-1",
    };
  }
  if (pathname.includes("/write")) return { ok: true, result: { created: "req-1" } };
  return { ok: true };
}

function fetchStub(input, options) {
  const url = String(input);
  const method = (options && options.method) || "GET";
  let body = null;
  if (options && options.body) {
    try {
      body = JSON.parse(options.body);
    } catch (err) {
      body = options.body;
    }
  }
  const record = { url, path: url.replace(/^.*\/api\/plugins\/reqogniloom/, ""), method, body };
  calls.push(record);
  if (record.path.startsWith("/write/preview")) {
    const preview = canned(record.path);
    preview.tool = body && body.tool;
    return Promise.resolve({ ok: true, status: 200, text: () => Promise.resolve(JSON.stringify(preview)) });
  }
  return Promise.resolve({ ok: true, status: 200, text: () => Promise.resolve(JSON.stringify(canned(record.path))) });
}

// --------------------------------------------------------------------------
// load the bundle
// --------------------------------------------------------------------------

const registered = {};
const sandbox = {
  window: {
    __HERMES_PLUGIN_SDK__: { React: { createElement }, hooks, components },
    __HERMES_PLUGINS__: { register: (name, component) => { registered[name] = component; } },
    fetch: fetchStub,
  },
  console,
  Promise,
  JSON,
  Object,
  Array,
  String,
  Number,
  Boolean,
  isNaN,
  encodeURIComponent,
  setTimeout,
};
sandbox.window.window = sandbox.window;
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(bundlePath, "utf8"), sandbox, { filename: "index.js" });

const Page = registered["reqogniloom"];
check(typeof Page === "function", "the bundle did not register the reqogniloom page");

// --------------------------------------------------------------------------
// tiny render/drive helpers
// --------------------------------------------------------------------------

function render() {
  hookCursor = 0;
  pathStack = [""];
  ordinalCounters = new Map();
  pendingEffects = [];
  const tree = Page();
  for (let round = 0; round < 12; round += 1) {
    const effects = pendingEffects.slice();
    pendingEffects = [];
    effects.forEach((effect) => {
      const cleanup = effect();
      if (typeof cleanup === "function") cleanups.push(cleanup);
    });
    if (!rerenderRequested && !effects.length) break;
    rerenderRequested = false;
    hookCursor = 0;
    pathStack = [""];
    ordinalCounters = new Map();
    pendingEffects = [];
    const next = Page();
    return flatten(next);
  }
  return flatten(tree);
}
let cleanups = [];

function flatten(node, out = []) {
  if (node === null || node === undefined || node === false || node === true) return out;
  if (Array.isArray(node)) {
    node.forEach((child) => flatten(child, out));
    return out;
  }
  if (typeof node !== "object") return out;
  out.push(node);
  if (node.props && node.props.children !== undefined) flatten(node.props.children, out);
  return out;
}

function findByTestId(tree, testId) {
  return tree.filter((node) => node.props && node.props["data-testid"] === testId);
}

function settle() {
  // Drain the promise chain the handlers started.
  return new Promise((resolve) => setTimeout(resolve, 0));
}

async function drive(handler) {
  handler();
  await settle();
  await settle();
  return render();
}

// A fresh mount: clearing hook state makes the page run its load effect again,
// which is what a scenario that changes an endpoint's answer needs. The existing
// scenarios deliberately drive one continuous session and must not call this.
async function freshMount() {
  hookState.clear();
  rerenderRequested = false;
  cleanups.forEach((cleanup) => cleanup());
  cleanups = [];
  render();
  // The load effect chains several requests; render after each drain so the tree
  // is read from the settled state, not from the first intermediate payload.
  for (let round = 0; round < 6; round += 1) {
    await settle();
    render();
  }
  return render();
}

// Every text node anywhere in a rendered tree. flatten() keeps only elements (a
// text node is not an element), so the strings are read off the element children.
function textOf(nodes) {
  const parts = [];
  const walk = (node) => {
    if (node === null || node === undefined || node === false || node === true) return;
    if (Array.isArray(node)) {
      node.forEach(walk);
      return;
    }
    if (typeof node !== "object") {
      parts.push(String(node));
      return;
    }
    if (node.props && node.props.children !== undefined) walk(node.props.children);
  };
  walk(nodes);
  return parts.join(" ");
}

// The tab issues reads through the same /write/preview route, so the arguments of
// a specific action are found by tool name and by the calls made after it started.
function previewArgumentsFor(tool, fromIndex) {
  const previews = calls.filter(
    (call, index) => index >= fromIndex && call.path.startsWith("/write/preview") && call.body.tool === tool
  );
  return previews.length ? previews[previews.length - 1].body.arguments : null;
}

// --------------------------------------------------------------------------
// scenario 1: the create flow sends only what the operator stated
// --------------------------------------------------------------------------

let tree = render();
// The tab opens on Overview; the write surface lives behind its own tab.
const navWrite = findByTestId(tree, "reqlo-nav-write");
check(navWrite.length === 1, "the Write tab must be reachable from the navigation");
if (navWrite.length) tree = await drive(navWrite[0].props.onClick);
if (process.env.REQLO_UI_DEBUG) {
  console.log("testids:", tree.map((n) => n.props && n.props["data-testid"]).filter(Boolean).join(", "));
}
let buttons = findByTestId(tree, "reqlo-create-run");
check(buttons.length === 1, "the create flow's run button should exist");
const titleField = findByTestId(tree, "reqlo-field-create-title");
check(titleField.length >= 1, "the create flow should render a field for the declared 'title'");

// Type a title, then start the two-phase write. Nothing else is filled in.
if (titleField.length) {
  tree = await drive(() => titleField[0].props.onChange({ target: { value: "Retryable payment path" } }));
}
const createCallIndex = calls.length;
buttons = findByTestId(tree, "reqlo-create-run");
check(buttons.length === 1, `expected one create button, found ${buttons.length}`);
const createHandler = buttons.length ? buttons[0].props.onClick : null;
if (createHandler) {
  tree = await drive(createHandler);
  await settle();
}

const createArgs = previewArgumentsFor("requirement.create", createCallIndex);
check(createArgs !== null, "the create flow should reach POST /write/preview");
if (createArgs) {
  check(createArgs.title === "Retryable payment path", `title should be sent, got ${JSON.stringify(createArgs.title)}`);
  check(
    createArgs.workspace_id !== undefined,
    "the selected workspace should be injected into a tool that declares workspace_id"
  );
  // The three optional fields were never touched: they must be *absent*, not
  // empty. An empty string for `level` is what made the preview refuse the call.
  ["level", "custom_fields", "verification_method", "dry_run"].forEach((field) => {
    check(
      createArgs[field] === undefined,
      `untouched optional field '${field}' must not be sent (got ${JSON.stringify(createArgs[field])})`
    );
  });
}

// --------------------------------------------------------------------------
// scenario 2: a tool without workspace_id gets no workspace
// --------------------------------------------------------------------------

tree = render();
const typeSelect = findByTestId(tree, "reqlo-create-type");
check(typeSelect.length === 1, "the create flow should offer a type selector");
if (typeSelect.length) {
  tree = await drive(() => typeSelect[0].props.onChange({ target: { value: "traceability.create_link" } }));
}
// The link flow has its own form (scope "link"); the create flow above was
// switched to the same tool and renders the same field names.
const sourceField = findByTestId(tree, "reqlo-field-link-source_id");
const targetField = findByTestId(tree, "reqlo-field-link-target_id");
buttons = findByTestId(tree, "reqlo-link-run");
check(buttons.length === 1, "the link flow should render its own run button");
if (sourceField.length && targetField.length && buttons.length) {
  const linkCallIndex = calls.length;
  // Each interaction re-finds its control in the freshly rendered tree: a form
  // field's change handler closes over the values of *its* render, exactly as in
  // React, so driving a stale element would drop what was typed before it.
  tree = await drive(() => sourceField[0].props.onChange({ target: { value: "req-1" } }));
  const reFoundTarget = findByTestId(tree, "reqlo-field-link-target_id");
  check(reFoundTarget.length === 1, "the target field should still be rendered after typing the source");
  if (reFoundTarget.length) {
    tree = await drive(() => reFoundTarget[0].props.onChange({ target: { value: "req-2" } }));
  }
  buttons = findByTestId(tree, "reqlo-link-run");
  check(buttons.length === 1, `expected one link button, found ${buttons.length}`);
  const linkHandler = buttons.length ? buttons[0].props.onClick : null;
  if (linkHandler) {
    await drive(linkHandler);
    await settle();
  }
  const linkArgs = previewArgumentsFor("traceability.create_link", linkCallIndex);
  check(linkArgs !== null, "the link flow should reach POST /write/preview");
  if (linkArgs) {
    check(
      linkArgs.workspace_id === undefined,
      `traceability.create_link declares no workspace_id, so it must not receive one (got ${JSON.stringify(
        linkArgs.workspace_id
      )})`
    );
    check(
      linkArgs.source_id === "req-1" && linkArgs.target_id === "req-2",
      `both link ids should be sent, got ${JSON.stringify(linkArgs)}`
    );
  }
}

// --------------------------------------------------------------------------
// scenario 3: the workspace is remembered, not invented
// --------------------------------------------------------------------------

check(
  calls.some((call) => call.path.startsWith("/workspace-selected") && call.body.workspace_id === "ws-remembered"),
  `the tab should prefer the workspace the registry remembers over the first list entry (saw ${
    JSON.stringify(calls.filter((c) => c.path.startsWith("/workspace-selected")).map((c) => c.body))
  })`
);

// --------------------------------------------------------------------------
// scenario 4: the manifest names the curated buttons use still exist
// --------------------------------------------------------------------------

if (fs.existsSync(manifestPath)) {
  const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
  const names = new Set((manifest.tools || []).map((tool) => tool.name));
  ["requirement.create", "traceability.create_link", "review.approve", "memory.write"].forEach((name) => {
    check(names.has(name), `the tool manifest no longer knows ${name} — a curated button would be a no-op`);
  });
} else {
  failures.push("docs/agent-templates/tool-manifest.json missing — the tool-name guard did not run");
}

// --------------------------------------------------------------------------
// scenario 5: an error envelope is not an empty workspace list (issue #1443)
// --------------------------------------------------------------------------

// The server answers a refused list with HTTP 200 and {"error": …, "code": …,
// "status": 403} — there is no "workspaces" key. Reading that as an empty list is
// what rendered "none visible": a permission verdict the tab had never received.
overrides.set("/workspaces", {
  error: "PERMISSION_DENIED: RBAC denied: no active role permits 'read'",
  code: "PERMISSION_DENIED",
  status: 403,
});
const deniedTree = await freshMount();
const deniedText = textOf(deniedTree);
if (process.env.REQLO_UI_DEBUG) {
  // The operator-visible text of the workspace bar, which is what the issue is
  // about — printed on demand so a failure can be read without a browser.
  console.log("workspace bar (403):", deniedText.slice(0, 600));
}
check(
  !deniedText.includes("none visible"),
  `a refused workspace list must not render "none visible" (saw: ${deniedText})`
);
check(
  deniedText.includes("RBAC denied") && deniedText.includes("HTTP 403"),
  `the refusal must surface the server's message and the HTTP status (saw: ${deniedText})`
);
check(
  /agent key/i.test(deniedText),
  `a PERMISSION_DENIED must name the missing read permission of the configured key (saw: ${deniedText})`
);
check(
  findByTestId(deniedTree, "reqlo-workspace-select").length === 1,
  "the workspace select should still render — the control stays, only the false verdict goes"
);

// The other half of the same defect: a list that really is empty must say so, and
// must not repeat the permission wording — the two states need to be told apart.
overrides.set("/workspaces", { workspaces: [] });
const emptyTree = await freshMount();
const emptyText = textOf(emptyTree);
if (process.env.REQLO_UI_DEBUG) {
  console.log("workspace bar (empty):", emptyText.slice(0, 300));
}
check(
  /no workspaces/i.test(emptyText),
  `an empty list must say the list is empty (saw: ${emptyText})`
);
check(
  !/RBAC|HTTP 403|agent key/i.test(emptyText),
  `an empty list must not claim a permission problem (saw: ${emptyText})`
);
overrides.clear();

// --------------------------------------------------------------------------

if (failures.length) {
  console.error("ui flow: FAILED");
  failures.forEach((message) => console.error("  - " + message));
  process.exit(1);
}
console.log(`ui flow: OK — ${calls.length} request(s), create/link arguments verified`);
