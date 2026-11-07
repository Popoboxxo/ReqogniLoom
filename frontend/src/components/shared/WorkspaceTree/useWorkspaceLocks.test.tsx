/**
 * P4.4 — `useWorkspaceLocks` degradation contract.
 *
 * The tree must never break (or block a move) because the lock *display* could
 * not be loaded: the backend enforces the freeze, so a rejected read yields an
 * empty map and the rows simply render unlocked. A falsy workspace id must not
 * issue a request at all.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { useWorkspaceLocks } from "./useWorkspaceLocks";
import { fetchLocks } from "../../../api/locks";

vi.mock("../../../api/locks", () => ({
  fetchLocks: vi.fn(),
}));

const mockedFetchLocks = vi.mocked(fetchLocks);

describe("useWorkspaceLocks (P4.4)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("returns the batch lock map on success", async () => {
    mockedFetchLocks.mockResolvedValue({ "req-1": "Freigegeben" });

    const { result } = renderHook(() =>
      useWorkspaceLocks("ws-1", "requirement"),
    );

    await waitFor(() =>
      expect(result.current).toEqual({ "req-1": "Freigegeben" }),
    );
    expect(mockedFetchLocks).toHaveBeenCalledWith("ws-1", "requirement");
    expect(mockedFetchLocks).toHaveBeenCalledTimes(1);
  });

  it("degrades to 'no locks' when the read fails", async () => {
    mockedFetchLocks.mockRejectedValue(new Error("403"));

    const { result } = renderHook(() =>
      useWorkspaceLocks("ws-1", "architecture"),
    );

    await waitFor(() => expect(mockedFetchLocks).toHaveBeenCalledTimes(1));
    // Nothing is thrown and no marker is rendered — the tree stays usable.
    expect(result.current).toEqual({});
  });

  it("does not request locks without a workspace", () => {
    const { result } = renderHook(() => useWorkspaceLocks(null, "requirement"));

    expect(mockedFetchLocks).not.toHaveBeenCalled();
    expect(result.current).toEqual({});
  });
});
