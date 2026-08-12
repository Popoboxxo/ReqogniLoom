import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useBundleCompressionStatus } from "../hooks/useBundleCompressionStatus";

// NOTE: `@testing-library/dom`'s `waitFor` only recognizes fake timers via a
// global `jest` shim (see `jestFakeTimersAreEnabled` in
// `node_modules/@testing-library/dom/dist/helpers.js`), which this project's
// vitest setup does not provide. Combining `waitFor` with `vi.useFakeTimers()`
// here deadlocks (its internal `setTimeout`/`setInterval` polling is itself
// faked and never advances), so this suite flushes pending microtasks via
// `await act(async () => {})` and asserts state directly instead.

vi.mock("../api/requirementBundle", () => ({
  requirementBundleApi: { getCompressionStatus: vi.fn() },
}));
import { requirementBundleApi } from "../api/requirementBundle";

describe("useBundleCompressionStatus", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("does not poll when taskId is null", () => {
    renderHook(() => useBundleCompressionStatus(null));
    expect(requirementBundleApi.getCompressionStatus).not.toHaveBeenCalled();
  });

  it("polls on an interval while status is pending/running, stops at done", async () => {
    (requirementBundleApi.getCompressionStatus as any)
      .mockResolvedValueOnce({ task_id: "t1", status: "pending", result: null, error: null })
      .mockResolvedValueOnce({ task_id: "t1", status: "running", result: null, error: null })
      .mockResolvedValueOnce({ task_id: "t1", status: "done", result: { result: "text" }, error: null });

    const { result } = renderHook(() => useBundleCompressionStatus("t1", 1000));

    await act(async () => {});
    expect(result.current.status).toBe("pending");
    await act(async () => { vi.advanceTimersByTime(1000); });
    expect(result.current.status).toBe("running");
    await act(async () => { vi.advanceTimersByTime(1000); });
    expect(result.current.status).toBe("done");

    expect(requirementBundleApi.getCompressionStatus).toHaveBeenCalledTimes(3);

    // No further calls once "done" — advancing time must not poll again.
    await act(async () => { vi.advanceTimersByTime(5000); });
    expect(requirementBundleApi.getCompressionStatus).toHaveBeenCalledTimes(3);
  });

  it("prefers the flat `text` field over the deprecated result envelope", async () => {
    // Issue #448: the status payload now carries the completion on a
    // single-level `text` field matching the synchronous response shape.
    (requirementBundleApi.getCompressionStatus as any).mockResolvedValue({
      task_id: "t1",
      status: "done",
      text: "flat text",
      result: { result: "legacy envelope text" },
      error: null,
    });

    const { result } = renderHook(() => useBundleCompressionStatus("t1", 1000));
    await act(async () => {});

    expect(result.current.result).toBe("flat text");
  });

  it("falls back to the legacy envelope when `text` is absent", async () => {
    // Backward compatibility with a backend predating issue #448.
    (requirementBundleApi.getCompressionStatus as any).mockResolvedValue({
      task_id: "t1",
      status: "done",
      result: { result: "legacy envelope text" },
      error: null,
    });

    const { result } = renderHook(() => useBundleCompressionStatus("t1", 1000));
    await act(async () => {});

    expect(result.current.result).toBe("legacy envelope text");
  });

  it("stops polling and clears the interval on unmount", async () => {
    (requirementBundleApi.getCompressionStatus as any).mockResolvedValue({
      task_id: "t1", status: "pending", result: null, error: null,
    });
    const { unmount } = renderHook(() => useBundleCompressionStatus("t1", 1000));
    await act(async () => {});
    expect(requirementBundleApi.getCompressionStatus).toHaveBeenCalledTimes(1);
    unmount();
    await act(async () => { vi.advanceTimersByTime(5000); });
    expect(requirementBundleApi.getCompressionStatus).toHaveBeenCalledTimes(1);
  });

  it("surfaces a failed status without throwing", async () => {
    (requirementBundleApi.getCompressionStatus as any).mockResolvedValue({
      task_id: "t1", status: "failed", result: null, error: "LLM_TOKEN_LIMIT_EXCEEDED",
    });
    const { result } = renderHook(() => useBundleCompressionStatus("t1", 1000));
    await act(async () => {});
    expect(result.current.status).toBe("failed");
    expect(result.current.error).toBe("LLM_TOKEN_LIMIT_EXCEEDED");
  });

  it("surfaces a not_found status (cross-tenant/expired task_id, ADR-03) as terminal and stops polling", async () => {
    (requirementBundleApi.getCompressionStatus as any).mockResolvedValue({
      task_id: "t1", status: "not_found", result: null, error: null,
    });
    const { result } = renderHook(() => useBundleCompressionStatus("t1", 1000));
    await act(async () => {});
    expect(result.current.status).toBe("not_found");
    expect(result.current.error).toBeNull();
    expect(result.current.isPolling).toBe(false);

    await act(async () => { vi.advanceTimersByTime(5000); });
    expect(requirementBundleApi.getCompressionStatus).toHaveBeenCalledTimes(1);
  });

  it("surfaces a network/getCompressionStatus rejection as a synthetic failed status and stops polling", async () => {
    (requirementBundleApi.getCompressionStatus as any).mockRejectedValue(new Error("Network error"));
    const { result } = renderHook(() => useBundleCompressionStatus("t1", 1000));
    await act(async () => {});
    expect(result.current.status).toBe("failed");
    expect(result.current.error).toBe("Network error");
    expect(result.current.isPolling).toBe(false);

    await act(async () => { vi.advanceTimersByTime(5000); });
    expect(requirementBundleApi.getCompressionStatus).toHaveBeenCalledTimes(1);
  });

  it("switches to the new taskId and resets state when taskId changes mid-poll", async () => {
    (requirementBundleApi.getCompressionStatus as any).mockImplementation((taskId: string) =>
      Promise.resolve(
        taskId === "t1"
          ? { task_id: "t1", status: "pending", result: null, error: null }
          : { task_id: "t2", status: "done", result: { result: "second task result" }, error: null }
      )
    );

    const { result, rerender } = renderHook(
      ({ taskId }) => useBundleCompressionStatus(taskId, 1000),
      { initialProps: { taskId: "t1" as string | null } }
    );
    await act(async () => {});
    expect(result.current.status).toBe("pending");
    expect(requirementBundleApi.getCompressionStatus).toHaveBeenCalledWith("t1");

    rerender({ taskId: "t2" });
    await act(async () => {});
    expect(result.current.status).toBe("done");
    expect(result.current.result).toBe("second task result");
    expect(requirementBundleApi.getCompressionStatus).toHaveBeenCalledWith("t2");

    // The old t1 interval must be gone — advancing time must not re-poll t1.
    const callsAfterSwitch = (requirementBundleApi.getCompressionStatus as any).mock.calls.length;
    await act(async () => { vi.advanceTimersByTime(5000); });
    expect((requirementBundleApi.getCompressionStatus as any).mock.calls.length).toBe(callsAfterSwitch);
  });
});
