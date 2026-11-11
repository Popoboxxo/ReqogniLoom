/**
 * useRequirementDelete — confirm/retry lifecycle (#811, #598 S2).
 *
 * Pins the two rules that made the old inline handler a bug (#811): a delete
 * closes the dialog only on confirmed success, and the extended preset refuses
 * to call the API without a `change_reason`.
 */

import { act, renderHook } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";

import { useRequirementDelete } from "./use-requirement-delete";

describe("useRequirementDelete", () => {
  it("keeps the dialog open when the delete is rejected", async () => {
    const onDelete = vi.fn().mockResolvedValue(false);
    const { result } = renderHook(() =>
      useRequirementDelete({ onDelete, requiresChangeReason: false })
    );

    act(() => result.current.requestDelete("req-1"));
    await act(async () => {
      await result.current.handleConfirmDelete();
    });

    expect(onDelete).toHaveBeenCalledWith("req-1", undefined);
    expect(result.current.confirmDeleteId).toBe("req-1");
    expect(result.current.isDeleting).toBe(false);
  });

  it("closes and resets after a confirmed delete", async () => {
    const onDelete = vi.fn().mockResolvedValue(true);
    const { result } = renderHook(() =>
      useRequirementDelete({ onDelete, requiresChangeReason: false })
    );

    act(() => result.current.requestDelete("req-1"));
    await act(async () => {
      await result.current.handleConfirmDelete();
    });

    expect(result.current.confirmDeleteId).toBeNull();
    expect(result.current.deleteChangeReason).toBe("");
    expect(result.current.deleteAttempted).toBe(false);
  });

  it("blocks the call and marks the field when the reason is missing", async () => {
    const onDelete = vi.fn().mockResolvedValue(true);
    const { result } = renderHook(() =>
      useRequirementDelete({ onDelete, requiresChangeReason: true })
    );

    act(() => result.current.requestDelete("req-1"));
    await act(async () => {
      await result.current.handleConfirmDelete();
    });

    expect(onDelete).not.toHaveBeenCalled();
    expect(result.current.deleteAttempted).toBe(true);
    expect(result.current.confirmDeleteId).toBe("req-1");
  });

  it("clears the missing-reason mark while typing and sends the trimmed reason", async () => {
    const onDelete = vi.fn().mockResolvedValue(true);
    const { result } = renderHook(() =>
      useRequirementDelete({ onDelete, requiresChangeReason: true })
    );

    act(() => result.current.requestDelete("req-1"));
    await act(async () => {
      await result.current.handleConfirmDelete();
    });
    act(() => result.current.onReasonChange("  superseded by REQ-2  "));

    expect(result.current.deleteAttempted).toBe(false);

    await act(async () => {
      await result.current.handleConfirmDelete();
    });

    expect(onDelete).toHaveBeenCalledWith("req-1", "superseded by REQ-2");
  });
});
