/** Install-prompt state machine (plan M3, REQ-213). */
import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useInstallPrompt } from "../hooks/useInstallPrompt";

describe("useInstallPrompt", () => {
  beforeEach(() => {
    vi.stubGlobal("matchMedia", vi.fn(() => ({ matches: false, addEventListener() {}, removeEventListener() {} })));
  });

  it("stays installed-only when the platform is iOS", () => {
    vi.stubGlobal("navigator", { userAgent: "iPhone", onLine: true });
    const { result } = renderHook(() => useInstallPrompt());
    expect(result.current.platform).toBe("ios");
    expect(result.current.canInstall).toBe(false);
  });

  it("promotes a captured beforeinstallprompt to an install action", async () => {
    vi.stubGlobal("navigator", { userAgent: "Android", onLine: true });
    const { result } = renderHook(() => useInstallPrompt());
    expect(result.current.canInstall).toBe(false);

    let resolveChoice: (value: { outcome: "accepted" }) => void = () => undefined;
    const userChoice = new Promise<{ outcome: "accepted" }>((resolve) => {
      resolveChoice = resolve;
    });
    const event = Object.assign(new Event("beforeinstallprompt"), {
      preventDefault: vi.fn(),
      prompt: vi.fn().mockResolvedValue(undefined),
      userChoice,
    });
    act(() => {
      window.dispatchEvent(event);
    });
    expect(result.current.canInstall).toBe(true);

    const pending = result.current.promptInstall();
    expect(event.prompt).toHaveBeenCalledTimes(1);
    await act(async () => {
      resolveChoice({ outcome: "accepted" });
      expect(await pending).toBe("accepted");
    });
    expect(result.current.canInstall).toBe(false);
  });

  it("reports unavailable when no prompt was offered", async () => {
    const { result } = renderHook(() => useInstallPrompt());
    expect(await result.current.promptInstall()).toBe("unavailable");
  });

  it("resolves unavailable and clears the event when prompt() rejects", async () => {
    vi.stubGlobal("navigator", { userAgent: "Android", onLine: true });
    const { result } = renderHook(() => useInstallPrompt());

    const rejectingPrompt = vi.fn().mockRejectedValue(new Error("prompt blocked"));
    const event = Object.assign(new Event("beforeinstallprompt"), {
      preventDefault: vi.fn(),
      prompt: rejectingPrompt,
      userChoice: Promise.resolve({ outcome: "accepted" }),
    });
    act(() => {
      window.dispatchEvent(event);
    });
    expect(result.current.canInstall).toBe(true);

    // A rejected prompt() must resolve to "unavailable" (no unhandled
    // rejection) and the finally block must drop the captured event.
    await act(async () => {
      await expect(result.current.promptInstall()).resolves.toBe("unavailable");
    });
    expect(rejectingPrompt).toHaveBeenCalledTimes(1);
    expect(result.current.canInstall).toBe(false);
  });
});
