/**
 * Internal runtime adapter interface (Issue #599 port).
 *
 * Not the real `@hermes/plugin-sdk` shape — `activate.ts` is the only file
 * that talks to the real SDK (`ctx.register`/`ctx.storage`, see
 * `hermes-sdk-types.ts`); it builds one of these from the SDK's `ctx`
 * object plus the global `fetch`/`window.open`, and everything else in this
 * package (`state.ts`, `mcpClient.ts`, `api.ts`, all views, all tests)
 * continues to depend on this stable, host-agnostic shape unchanged.
 * Keeping this indirection means a future SDK contract change only touches
 * `activate.ts`.
 */
export interface PluginPanelProps {
  pluginId: string;
  panelId: string;
}

export interface HermesPluginAPI {
  ui: {
    updateStatusBarItem(itemId: string, update: { text?: string; tooltip?: string; visible?: boolean }): void;
  };
  storage: {
    get(key: string): Promise<string | null>;
    set(key: string, value: string): Promise<void>;
    delete(key: string): Promise<void>;
  };
  network: {
    fetch(url: string, options?: RequestInit): Promise<unknown>;
  };
  shell: {
    openExternal(url: string): Promise<void>;
  };
}
