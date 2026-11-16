/** Runtime behaviour of the PWA update/cache handshake (plan M2, REQ-214). */
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  onPwaUpdateAvailable,
  purgePwaCaches,
  pwaApplyUpdate,
  pwaNeedsRefresh,
  registerPwa,
} from "../pwa/register";
import { triggerNeedRefresh } from "./mocks/pwa-register";

describe("PWA update handshake", () => {
  beforeEach(() => {
    registerPwa();
  });

  it("notifies subscribers when a waiting worker appears", () => {
    const listener = vi.fn();
    const unsubscribe = onPwaUpdateAvailable(listener);
    triggerNeedRefresh();
    expect(pwaNeedsRefresh()).toBe(true);
    expect(listener).toHaveBeenCalledTimes(1);
    unsubscribe();
    triggerNeedRefresh();
    expect(listener).toHaveBeenCalledTimes(1);
  });

  it("clears the update flag after the user applies it", async () => {
    triggerNeedRefresh();
    expect(pwaNeedsRefresh()).toBe(true);
    await pwaApplyUpdate();
    expect(pwaNeedsRefresh()).toBe(false);
  });
});

describe("cache purge on logout", () => {
  it("deletes every cache but keeps the worker registration", async () => {
    const del = vi.fn().mockResolvedValue(true);
    vi.stubGlobal("caches", {
      keys: vi.fn().mockResolvedValue(["workbox-precache-v2", "reqlo-assets"]),
      delete: del,
    });
    await purgePwaCaches();
    expect(del.mock.calls.map((call) => call[0])).toEqual([
      "workbox-precache-v2",
      "reqlo-assets",
    ]);
    vi.unstubAllGlobals();
  });
});
