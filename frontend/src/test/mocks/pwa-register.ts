/** Vitest stub for the `virtual:pwa-register` module (plan M2). */
type Options = {
  onNeedRefresh?: () => void;
  onOfflineReady?: () => void;
};

type ApplyUpdate = (reloadPage?: boolean) => Promise<void>;

let needRefresh: (() => void) | undefined;
let applyUpdateImpl: ApplyUpdate = async () => undefined;

export function registerSW(options: Options = {}): ApplyUpdate {
  needRefresh = options.onNeedRefresh;
  return (reloadPage?: boolean) => applyUpdateImpl(reloadPage);
}

/** Test-only hook: simulate the browser reporting a waiting worker. */
export function triggerNeedRefresh(): void {
  needRefresh?.();
}

/** Test-only hook: force the next apply attempt to reject (FE-007). */
export function setApplyUpdate(impl: ApplyUpdate): void {
  applyUpdateImpl = impl;
}

/** Test-only hook: restore defaults between tests. */
export function resetPwaRegisterMock(): void {
  needRefresh = undefined;
  applyUpdateImpl = async () => undefined;
}
