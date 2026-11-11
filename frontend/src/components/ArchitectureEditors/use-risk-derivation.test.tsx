/**
 * useRiskDerivation — preview/confirm lifecycle (#1360, #598 S2).
 *
 * The editor had no test for the shared AI review dialog; this pins the
 * contract the extraction must preserve: the preview fills drafts, a failed
 * preview keeps the dialog open with its own error, a decision writes and
 * closes, and a failed decision does NOT close (the drafts stay reviewable).
 */

import { act, renderHook } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import type { TFunction } from "i18next";

import { useRiskDerivation } from "./use-risk-derivation";
import { architectureApi } from "../../api/architecture";
import type { ArchitectureElement } from "../../types";

vi.mock("../../api/architecture");

const t = ((key: string, options?: { count?: number }) =>
  options?.count === undefined ? key : `${key}:${options.count}`) as unknown as TFunction;

const ELEMENT = { id: "arch-1" } as ArchitectureElement;

describe("useRiskDerivation", () => {
  beforeEach(() => vi.clearAllMocks());

  it("loads the preview drafts when the dialog opens", async () => {
    vi.mocked(architectureApi.deriveRisksPreview).mockResolvedValue({
      drafts: [
        { title: "Risk A", description: "desc A" },
        { title: "Risk B", description: "desc B" },
      ],
    });

    const { result } = renderHook(() => useRiskDerivation(ELEMENT, t));

    await act(async () => {
      await result.current.openRiskDialog();
    });

    expect(result.current.riskOpen).toBe(true);
    expect(result.current.riskLoading).toBe(false);
    expect(result.current.riskDrafts).toEqual([
      { title: "Risk A", description: "desc A" },
      { title: "Risk B", description: "desc B" },
    ]);
  });

  it("keeps the dialog open and reports the preview error", async () => {
    vi.mocked(architectureApi.deriveRisksPreview).mockRejectedValue({
      error: { message: "preview failed" },
    });

    const { result } = renderHook(() => useRiskDerivation(ELEMENT, t));

    await act(async () => {
      await result.current.openRiskDialog();
    });

    expect(result.current.riskOpen).toBe(true);
    expect(result.current.riskLoadError).toBe("preview failed");
    expect(result.current.riskDrafts).toBeNull();
  });

  it("writes, reports the count and closes the dialog", async () => {
    vi.mocked(architectureApi.deriveRisksWrite).mockResolvedValue({
      written: ["r1", "r2", "r3"],
    });

    const { result } = renderHook(() => useRiskDerivation(ELEMENT, t));

    await act(async () => {
      await result.current.decide(false);
    });

    expect(result.current.riskStatus).toBe("aiDerivation.statusCreated:3");
    expect(result.current.riskOpen).toBe(false);
    expect(result.current.riskSaving).toBe(false);
  });

  it("keeps the dialog and drafts when the write fails", async () => {
    vi.mocked(architectureApi.deriveRisksPreview).mockResolvedValue({
      drafts: [{ title: "Risk A", description: "desc A" }],
    });
    vi.mocked(architectureApi.deriveRisksWrite).mockRejectedValue({
      error: { message: "write failed" },
    });

    const { result } = renderHook(() => useRiskDerivation(ELEMENT, t));

    await act(async () => {
      await result.current.openRiskDialog();
    });
    await act(async () => {
      await result.current.decide(true);
    });

    expect(result.current.riskSubmitError).toBe("write failed");
    expect(result.current.riskSaving).toBe(false);
    // The drafts stay reviewable — a failed commit must not discard them.
    expect(result.current.riskOpen).toBe(true);
    expect(result.current.riskDrafts).toEqual([
      { title: "Risk A", description: "desc A" },
    ]);
  });
});
