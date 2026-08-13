export interface Disposable {
  dispose(): void;
}

export interface PluginPanelProps {
  pluginId: string;
  panelId: string;
}

export interface HermesPluginAPI {
  ui: {
    registerPanel(panelId: string, component: React.ComponentType<PluginPanelProps>): Disposable;
    showPanel(panelId: string): void;
    hidePanel(panelId: string): void;
    togglePanel(panelId: string): void;
    showToast(message: string, options?: { type?: "info" | "success" | "warning" | "error"; duration?: number }): void;
    updateStatusBarItem(itemId: string, update: { text?: string; tooltip?: string; visible?: boolean }): void;
  };
  commands: {
    register(commandId: string, handler: () => void | Promise<void>): Disposable;
    execute(commandId: string): Promise<void>;
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
  subscriptions: Disposable[];
}
