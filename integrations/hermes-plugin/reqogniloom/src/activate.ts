/**
 * Plugin entry point — @hermes/plugin-sdk contract (Issue #599 port).
 *
 * The Hermes desktop app loads plugins as a single ESM file
 * (`dist/plugin.js`) and expects a default export shaped
 * `{ id, name, register(ctx) }` — see `hermes-sdk-types.ts` for the (locally
 * transcribed, unverified) SDK contract this was written against.
 *
 * `register(ctx)` builds a `HermesPluginAPI` adapter (see
 * `hermes-api-types.ts`) from the real SDK's `ctx` object plus the global
 * `fetch`/`window.open` — everything downstream of that adapter (`state.ts`,
 * `mcpClient.ts`, `api.ts`, every view, every existing test) is completely
 * unchanged from before this port.
 */
import * as React from "react";
import type { HermesPluginContext, HermesRegistration } from "./hermes-sdk-types";
import type { HermesPluginAPI } from "./hermes-api-types";
import { ReqogniLoomPanel } from "./ReqogniLoomPanel";
import { initState } from "./state";

const PLUGIN_ID = "reqogniloom.reqogniloom";
const PANEL_ID = "reqogniloom-panel";
const STATUS_BAR_ID = "reqogniloom.status";

/**
 * Adapts the real SDK's `ctx` into this package's stable internal runtime
 * shape. `network.fetch` deliberately does NOT go through any SDK-provided
 * network wrapper — the old API's `api.network.fetch()` had no documented
 * replacement in Issue #599's mapping table (`host.request(method, params)`
 * reads as a host-internal RPC channel, not a general-purpose HTTP client
 * for an arbitrary external base URL with custom headers, which is what
 * `mcpClient.ts`/`api.ts` need). The plugin runs as a normal ESM module in
 * the desktop app's renderer, where the global `fetch` is always available,
 * so this uses it directly.
 */
function buildRuntime(ctx: HermesPluginContext, statusBar: HermesRegistration): HermesPluginAPI {
  return {
    ui: {
      updateStatusBarItem(_itemId, update) {
        statusBar.update?.({ text: update.text, tooltip: update.tooltip });
      },
    },
    storage: {
      get: (key) => ctx.storage.get(key),
      set: (key, value) => ctx.storage.set(key, value),
      delete: (key) => ctx.storage.remove(key),
    },
    network: {
      fetch: (url, options) => fetch(url, options),
    },
    shell: {
      async openExternal(url) {
        window.open(url, "_blank", "noopener,noreferrer");
      },
    },
  };
}

function register(ctx: HermesPluginContext): void {
  ctx.register({
    id: PANEL_ID,
    area: "panes",
    title: "ReqogniLoom",
    // React.createElement, not a direct ReqogniLoomPanel({...}) call --
    // calling a function component directly bypasses React's render cycle
    // and breaks the useState/useEffect hooks inside it.
    render: () => React.createElement(ReqogniLoomPanel, { pluginId: PLUGIN_ID, panelId: PANEL_ID }),
  });

  const statusBar = ctx.register({
    id: STATUS_BAR_ID,
    area: "statusBar.right",
    text: "ReqogniLoom",
    tooltip: "Open ReqogniLoom panel",
  });

  const runtime = buildRuntime(ctx, statusBar);

  initState(runtime).catch((err) => {
    console.error("ReqogniLoom: initState failed, staying on connect view", err);
  });
}

const plugin = {
  id: PLUGIN_ID,
  name: "ReqogniLoom",
  register,
};

export default plugin;
