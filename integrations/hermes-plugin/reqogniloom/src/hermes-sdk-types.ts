/**
 * Local type shim for `@hermes/plugin-sdk` (Issue #599).
 *
 * IMPORTANT — unverified against the real package: `@hermes/plugin-sdk` is
 * not published on the public npm registry (404 on `npm view`) and no local
 * Hermes installation was available in the environment this port was written
 * in (`~/.hermes` does not exist, no `hermes` CLI on PATH). This file is a
 * best-effort transcription of the contract documented in Issue #599's
 * solution sketch (authored 2026-08-16 against a real, installed Hermes
 * instance) — it has NOT been checked against the actual SDK's type
 * declarations or a live smoke-load in the Hermes desktop app.
 *
 * Before trusting this in production: load the built `dist/plugin.js` into
 * a real Hermes instance (`~/.hermes/desktop-plugins/reqogniloom/plugin.js`)
 * and confirm the panel/command/status-bar item actually render — this is
 * the one verification step this port could not perform.
 *
 * Kept intentionally narrow: only the surface `activate.ts` actually calls.
 * `@hermes/plugin-sdk` almost certainly exports much more.
 */

export interface HermesPanelDescriptor {
  id: string;
  area: "panes";
  title: string;
  render: () => unknown;
}

export interface HermesCommandDescriptor {
  id: string;
  area: "commandPalette";
  title: string;
  run: () => void | Promise<void>;
}

export interface HermesStatusBarDescriptor {
  id: string;
  area: "statusBar.right";
  text: string;
  tooltip?: string;
}

/** Handle returned by `ctx.register()` for descriptors that expose mutable state (status bar text). */
export interface HermesRegistration {
  update?(patch: { text?: string; tooltip?: string }): void;
  dispose?(): void;
}

export interface HermesPluginStorage {
  get(key: string): Promise<string | null>;
  set(key: string, value: string): Promise<void>;
  remove(key: string): Promise<void>;
}

export interface HermesPluginContext {
  register(
    descriptor: HermesPanelDescriptor | HermesCommandDescriptor | HermesStatusBarDescriptor
  ): HermesRegistration;
  storage: HermesPluginStorage;
}

/** Default export contract the Hermes desktop app expects from `dist/plugin.js`. */
export interface HermesPlugin {
  id: string;
  name: string;
  register(ctx: HermesPluginContext): void | (() => void);
}
