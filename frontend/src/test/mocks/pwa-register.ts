/** Vitest stub for the `virtual:pwa-register` module (plan M2). */
type Options = {
  onNeedRefresh?: () => void;
  onOfflineReady?: () => void;
};

let needRefresh: (() => void) | undefined;

export function registerSW(options: Options = {}): (reloadPage?: boolean) => Promise<void> {
  needRefresh = options.onNeedRefresh;
  return async () => undefined;
}

/** Test-only hook: simulate the browser reporting a waiting worker. */
export function triggerNeedRefresh(): void {
  needRefresh?.();
}
