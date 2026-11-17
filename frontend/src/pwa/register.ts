/**
 * Service-worker registration and update handshake (plan M2, REQ-214).
 *
 * Registration is deliberately outside React (called from index.tsx): the
 * SW lifecycle must not restart with the component tree. Updates are never
 * applied automatically — `pwaApplyUpdate()` is wired to an explicit user
 * confirmation so a long form cannot be reloaded out from under the user.
 */
import { registerSW } from "virtual:pwa-register";

type Listener = () => void;
const updateListeners = new Set<Listener>();
let needsRefresh = false;
let applyUpdate: ((reloadPage?: boolean) => Promise<void>) | undefined;

/** True while a newer worker is waiting to be activated. */
export function pwaNeedsRefresh(): boolean {
  return needsRefresh;
}

/** Subscribe to update-available changes; returns an unsubscribe function. */
export function onPwaUpdateAvailable(listener: Listener): () => void {
  updateListeners.add(listener);
  return () => {
    updateListeners.delete(listener);
  };
}

/** Install the waiting worker and reload the page (explicit user action). */
export async function pwaApplyUpdate(): Promise<void> {
  try {
    await applyUpdate?.(true);
  } catch {
    // The worker refused to activate. Keep the banner visible so the user can
    // retry; clearing it here would silently leave a stale worker in place.
    needsRefresh = true;
    updateListeners.forEach((listener) => listener());
    return;
  }
  // Only acknowledge the update after it actually succeeded.
  needsRefresh = false;
  updateListeners.forEach((listener) => listener());
}

/** Register the generated worker once, at app start. */
export function registerPwa(): void {
  applyUpdate = registerSW({
    immediate: true,
    onNeedRefresh: () => {
      needsRefresh = true;
      updateListeners.forEach((listener) => listener());
    },
    onOfflineReady: () => {
      // No toast: offline readiness is shown contextually by PwaNotices.
    },
  });
}

/**
 * Purge every cache on logout; the SW registration itself stays installed.
 * Page and worker share one origin/cache storage, so deleting from the page
 * is enough — no custom SW message handler is needed.
 */
export async function purgePwaCaches(): Promise<void> {
  if (typeof caches === "undefined") return;
  const keys = await caches.keys();
  await Promise.all(keys.map((key) => caches.delete(key)));
}
