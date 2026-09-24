import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  installBluepencilReviewLayer,
  teardownBluepencilReviewLayer,
} from "../bluepencil/loader";

function loaderScripts(): HTMLScriptElement[] {
  return Array.from(document.querySelectorAll<HTMLScriptElement>("script[data-bluepencil-loader]"));
}

describe("bluepencil loader — timed-out attach", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.stubEnv("VITE_BLUEPENCIL_ENABLED", "1");
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          ({
            ok: true,
            status: 200,
            json: async () => ({ ok: true }),
          }) as Response,
      ),
    );
  });

  afterEach(() => {
    teardownBluepencilReviewLayer();
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
    vi.useRealTimers();
  });

  it("blocks reattach and removes artifacts arriving after the timeout", async () => {
    await expect(installBluepencilReviewLayer()).resolves.toBe(true);
    await vi.advanceTimersByTimeAsync(5_000);

    expect(loaderScripts()).toHaveLength(0);
    await expect(installBluepencilReviewLayer()).resolves.toBe(false);
    expect(fetch).toHaveBeenCalledTimes(1);

    const destroy = vi.fn();
    window.bluepencilAttach = { destroy };

    expect(destroy).toHaveBeenCalledTimes(1);
    expect(window.bluepencilAttach).toBeUndefined();

    document.body.append(document.createElement("bluepencil-notes"));
    await Promise.resolve();

    expect(document.querySelector("bluepencil-notes")).toBeNull();
  });
});
