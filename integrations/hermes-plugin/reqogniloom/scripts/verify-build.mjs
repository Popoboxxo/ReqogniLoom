#!/usr/bin/env -S node --experimental-vm-modules
/**
 * Build-output guard for the ReqogniLoom Hermes plugin (Issue #599 port).
 *
 * Context: neither `tsc --noEmit` nor `vitest` exercises the real Vite
 * bundling pipeline, so a class of bug (wrong module format, an
 * accidentally-inlined external dependency, a stale IIFE/`window.*`
 * registration footer left over from the pre-#599 contract) is invisible to
 * both and can only be caught by inspecting the actual shipped artifact.
 * See git history for this file's pre-#599 version and the concrete
 * `process is not defined` incident that motivated it originally.
 *
 * This script:
 *   1. Greps the built bundle for tokens that should never appear
 *      (`process`, an inlined `react/jsx-runtime`, `REACT_ELEMENT_TYPE`,
 *      the old `window.__hermesPlugins` IIFE-footer contract).
 *   2. Smoke-loads the bundle as a real ES module (via `vm.SourceTextModule`,
 *      hence `--experimental-vm-modules`) with `react` resolved to a stub,
 *      and confirms the default export matches the `{ id, name, register }`
 *      contract and that `register(ctx)` runs without throwing and
 *      registers at least one panel via `ctx.register()`.
 *
 * Run via `npm run verify-build` (or automatically as a postbuild step of
 * `npm run build`).
 */

import { readFileSync, existsSync } from "node:fs";
import { fileURLToPath, pathToFileURL } from "node:url";
import { dirname, resolve } from "node:path";
import vm from "node:vm";

const __dirname = dirname(fileURLToPath(import.meta.url));
const packageRoot = resolve(__dirname, "..");
const manifestPath = resolve(packageRoot, "hermes-plugin.json");
const manifest = JSON.parse(readFileSync(manifestPath, "utf8"));
const bundlePath = resolve(packageRoot, manifest.main ?? "dist/plugin.js");

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
const forbiddenPatterns = [
  { name: "process", pattern: /\bprocess\b/ },
  { name: "jsx-runtime", pattern: /jsx-runtime/ },
  { name: "REACT_ELEMENT_TYPE", pattern: /REACT_ELEMENT_TYPE/ },
  {
    name: "window.__hermesPlugins (old pre-#599 IIFE contract)",
    pattern: /__hermesPlugins/,
  },
];

let tokenCheckFailed = false;
for (const { name, pattern } of forbiddenPatterns) {
  const match = bundleSource.match(pattern);
  if (match) {
    tokenCheckFailed = true;
    const line = bundleSource.slice(0, match.index).split("\n").length;
    fail(
      `forbidden token "${name}" found in ${bundlePath}:${line} — check ` +
        `tsconfig.json's "jsx" setting (must stay "react", not "react-jsx") ` +
        `and vite.config.ts's rollupOptions.external / build.lib.formats.`
    );
  }
}

// Rollup emits `export { plugin as default };`, not the literal source text
// "export default" -- match either form.
if (!/\bexport\s+default\b/.test(bundleSource) && !/\bas\s+default\s*[,}]/.test(bundleSource)) {
  tokenCheckFailed = true;
  fail(`bundle has no default export — the {id, name, register} contract requires one.`);
}

if (!tokenCheckFailed) {
  console.log("verify-build: token check passed");
}

// --- Check 2: smoke-load as a real ES module --------------------------------
//
// register(ctx) only *passes a render callback* to ctx.register(); nothing
// here actually calls that callback (that would require a working React
// reconciler), so a minimal Proxy-based React stub that never throws on
// property access is enough -- same approach the pre-#599 version of this
// script used for its `window`-global React stand-in.
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

function createStubCtx() {
  const registered = [];
  const ctx = {
    register(descriptor) {
      registered.push(descriptor);
      return { update() {}, dispose() {} };
    },
    storage: {
      async get() {
        return null;
      },
      async set() {},
      async remove() {},
    },
  };
  return { ctx, registered };
}

// The exact set of named `react` bindings the bundle imports is derived from
// the bundle itself (`import { useState, useEffect, ... } from "react"`)
// rather than hardcoded, so this stays correct if the plugin starts using
// more/different hooks without anyone having to remember to update this
// script. `vm.SyntheticModule` requires the export names up front.
function namedReactImportsUsedByBundle(source) {
  const names = new Set();
  const importRe = /import\s*\{([^}]*)\}\s*from\s*["']react["']/g;
  let match;
  while ((match = importRe.exec(source))) {
    for (const raw of match[1].split(",")) {
      const name = raw.trim().split(/\s+as\s+/)[0].trim();
      if (name) names.add(name);
    }
  }
  return [...names];
}

let smokeLoadFailed = false;
try {
  const reactStub = createReactStub();
  const namedReactExports = namedReactImportsUsedByBundle(bundleSource);

  async function linker(specifier, referencingModule) {
    if (specifier === "react") {
      return new vm.SyntheticModule(
        ["default", ...namedReactExports],
        function () {
          this.setExport("default", reactStub);
          for (const name of namedReactExports) this.setExport(name, reactStub);
        },
        { context: referencingModule.context }
      );
    }
    if (specifier === "@hermes/plugin-sdk") {
      return new vm.SyntheticModule([], function () {}, { context: referencingModule.context });
    }
    throw new Error(`verify-build stub linker: unexpected import "${specifier}"`);
  }

  const context = vm.createContext({ window: {}, console, fetch: async () => { throw new Error("stub fetch"); } });
  const source = new vm.SourceTextModule(bundleSource, { identifier: pathToFileURL(bundlePath).href, context });
  await source.link(linker);
  await source.evaluate();

  const plugin = source.namespace.default;
  if (!plugin || typeof plugin.register !== "function") {
    throw new Error(
      `default export is not a { id, name, register } plugin descriptor (got: ${JSON.stringify(plugin)})`
    );
  }
  if (!plugin.id || !plugin.name) {
    throw new Error(`default export is missing "id" or "name" (got id=${plugin.id}, name=${plugin.name})`);
  }

  const { ctx, registered } = createStubCtx();
  await plugin.register(ctx);

  if (registered.length < 1) {
    throw new Error("register(ctx) ran but registered zero panels/commands/status-bar items via ctx.register()");
  }
  const panels = registered.filter((r) => r.area === "panes");
  if (panels.length < 1) {
    throw new Error("register(ctx) ran but registered zero panels (area: 'panes')");
  }

  console.log(
    `verify-build: smoke-load passed (register() ran, id="${plugin.id}", registered ${registered.length} item(s): ` +
      registered.map((r) => `${r.id} (${r.area})`).join(", ") +
      ")"
  );
} catch (err) {
  smokeLoadFailed = true;
  fail(`smoke-load failed — register() did not run cleanly: ${err.stack ?? err}`);
}

if (tokenCheckFailed || smokeLoadFailed) {
  process.exit(1);
}

console.log("verify-build: OK");
