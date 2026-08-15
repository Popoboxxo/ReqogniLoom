#!/usr/bin/env node
/**
 * Build-output guard for the ReqogniLoom Hermes plugin.
 *
 * Context: a `tsconfig.json` change (classic "react" JSX -> automatic
 * "react-jsx") silently broke the production Vite bundle -- Vite's
 * `rollupOptions.external: ["react"]` only externalizes the `react` module
 * specifier, not the `react/jsx-runtime` subpath the automatic runtime
 * imports. React's JSX runtime (including a CJS shim that reads
 * `process.env` at module-load time) got bundled directly into the plugin
 * output. Hermes's plugin host has no `process` polyfill, so the built
 * plugin threw `ReferenceError: process is not defined` before `activate()`
 * ever ran. Neither `tsc --noEmit` nor `vitest` exercises the real Vite
 * bundling pipeline (vitest uses @vitejs/plugin-react with the automatic
 * runtime for tests, independent of what tsconfig.json says), so this class
 * of bug is invisible to both and can only be caught by inspecting the
 * actual shipped artifact.
 *
 * This script:
 *   1. Greps the built bundle for tokens that should never appear in a
 *      correctly-externalized build (`process`, `jsx-runtime`,
 *      `REACT_ELEMENT_TYPE`).
 *   2. Smoke-loads the bundle in a Node `vm` context with a minimal stub
 *      HermesPluginAPI and confirms `activate()` runs without throwing and
 *      registers at least one panel.
 *
 * Run via `npm run verify-build` (or automatically as a postbuild step of
 * `npm run build`).
 */

import { readFileSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import vm from "node:vm";

const __dirname = dirname(fileURLToPath(import.meta.url));
const packageRoot = resolve(__dirname, "..");
const manifestPath = resolve(packageRoot, "hermes-plugin.json");
const manifest = JSON.parse(readFileSync(manifestPath, "utf8"));
const bundlePath = resolve(packageRoot, manifest.main ?? "dist/index.js");

function fail(message) {
  console.error(`verify-build: FAIL — ${message}`);
  process.exitCode = 1;
}

if (!existsSync(bundlePath)) {
  fail(`bundle not found at ${bundlePath}. Run "npm run build" first.`);
  process.exit(1);
}

const bundleSource = readFileSync(bundlePath, "utf8");

// --- Check 1: forbidden-token grep -----------------------------------------
//
// A correctly-externalized build never references `process` (Node/CJS
// globals have no business in a browser/Electron-renderer bundle that only
// imports the externalized `react` global) and never inlines React's JSX
// runtime module or its internal element-type symbol constant.
const forbiddenPatterns = [
  { name: "process", pattern: /\bprocess\b/ },
  { name: "jsx-runtime", pattern: /jsx-runtime/ },
  { name: "REACT_ELEMENT_TYPE", pattern: /REACT_ELEMENT_TYPE/ },
];

let tokenCheckFailed = false;
for (const { name, pattern } of forbiddenPatterns) {
  const match = bundleSource.match(pattern);
  if (match) {
    tokenCheckFailed = true;
    const line = bundleSource.slice(0, match.index).split("\n").length;
    fail(
      `forbidden token "${name}" found in ${bundlePath}:${line} — this usually ` +
        `means React (or its JSX runtime) got bundled instead of staying external. ` +
        `Check tsconfig.json's "jsx" setting (must stay "react", not "react-jsx") ` +
        `and vite.config.ts's rollupOptions.external.`
    );
  }
}

if (!tokenCheckFailed) {
  console.log("verify-build: token check passed (no process/jsx-runtime/REACT_ELEMENT_TYPE in bundle)");
}

// --- Check 2: smoke-load in a Node vm context -------------------------------
//
// The token grep alone can have false negatives (a future bundler could
// inline React under different variable names) and false positives (a
// legitimate future dependency might contain the substring "process" in an
// unrelated string). Actually executing the bundle and calling activate()
// proves the artifact loads and does the one thing that matters: registers
// a panel, without throwing.
function createDisposable() {
  return { dispose() {} };
}

function createStubApi() {
  const registeredPanels = [];
  const registeredCommands = [];
  const api = {
    ui: {
      registerPanel(panelId, component) {
        registeredPanels.push({ panelId, component });
        return createDisposable();
      },
      showPanel() {},
      hidePanel() {},
      togglePanel() {},
      showToast() {},
      updateStatusBarItem() {},
    },
    commands: {
      register(commandId, handler) {
        registeredCommands.push({ commandId, handler });
        return createDisposable();
      },
      async execute() {},
    },
    storage: {
      async get() {
        // No stored connection -- exercises the "fresh install" path
        // through initState() without requiring a network stub.
        return null;
      },
      async set() {},
      async delete() {},
    },
    network: {
      async fetch() {
        throw new Error("verify-build stub: network.fetch should not be called on a fresh activate()");
      },
    },
    shell: {
      async openExternal() {},
    },
    subscriptions: [],
  };
  return { api, registeredPanels, registeredCommands };
}

// Minimal, infinitely-chainable React stand-in. activate() only *passes
// component references* to ui.registerPanel(); it never renders them, so we
// don't need a working reconciler here -- just something that won't throw
// if the bundle touches `React.something` at module-evaluation time (e.g.
// for a `React.Fragment` default parameter).
function createReactStub() {
  const handler = {
    get(_target, prop) {
      if (prop === Symbol.toPrimitive || prop === "toString") return () => "[ReactStub]";
      return createReactStub();
    },
    apply() {
      return createReactStub();
    },
  };
  return new Proxy(function ReactStub() {}, handler);
}

let smokeLoadFailed = false;
try {
  const windowStub = {};
  const sandbox = {
    window: windowStub,
    React: createReactStub(),
    console,
  };
  const context = vm.createContext(sandbox);
  vm.runInContext(bundleSource, context, { filename: bundlePath });

  const registered = windowStub.__hermesPlugins?.[manifest.id];
  if (!registered || typeof registered.activate !== "function") {
    throw new Error(
      `window.__hermesPlugins["${manifest.id}"].activate was not registered by the bundle footer`
    );
  }

  const { api, registeredPanels } = createStubApi();
  await registered.activate(api);

  if (registeredPanels.length < 1) {
    throw new Error("activate() ran but registered zero panels via ui.registerPanel()");
  }

  console.log(
    `verify-build: smoke-load passed (activate() ran, registered ${registeredPanels.length} panel(s): ` +
      registeredPanels.map((p) => p.panelId).join(", ") +
      ")"
  );
} catch (err) {
  smokeLoadFailed = true;
  fail(`smoke-load failed — activate() did not run cleanly: ${err.stack ?? err}`);
}

if (tokenCheckFailed || smokeLoadFailed) {
  process.exit(1);
}

console.log("verify-build: OK");
