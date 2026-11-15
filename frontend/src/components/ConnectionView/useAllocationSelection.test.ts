/**
 * V.3 — selection state of the "Bäume" renderer.
 *
 * The selection has one requirement that is easy to get wrong: it must survive
 * a filter change without pretending that a hidden row is still selected, and a
 * frozen row must be unreachable from every entry point (checkbox, select-all,
 * programmatic toggle).
 */

import { describe, expect, it } from "vitest";
import { act, renderHook } from "@testing-library/react";

import type { AllocationRow } from "../../api/allocation-view";
import { useAllocationSelection } from "./useAllocationSelection";

function requirement(overrides: Partial<AllocationRow>): AllocationRow {
  return {
    kind: "requirement",
    id: "r1",
    artifact_id: "art-r1",
    parent_id: null,
    sort_key: "a",
    title: "Requirement 1",
    state: "draft",
    tier_key: null,
    tier_name: null,
    level: 1,
    type: "SyReq",
    category: "functional",
    allocated_to: null,
    allocation_trace_link_id: null,
    element_id: null,
    allocation_intent: "unassigned",
    locked: null,
    findings: [],
    group: null,
    ...overrides,
  };
}

const R1 = requirement({ id: "r1", title: "Bremsen", sort_key: "a" });
const R2 = requirement({ id: "r2", title: "Lenken", sort_key: "b" });
const R3_LOCKED = requirement({
  id: "r3",
  title: "Fahrwerk",
  sort_key: "c",
  locked: "approved",
});

describe("useAllocationSelection", () => {
  it("excludes locked rows from the selectable set", () => {
    const { result } = renderHook(() =>
      useAllocationSelection([R1, R2, R3_LOCKED])
    );

    expect([...result.current.selectableIds].sort()).toEqual(["r1", "r2"]);
    expect(result.current.selectableIds.has("r3")).toBe(false);
  });

  it("toggles a selectable row and ignores a locked one", () => {
    const { result } = renderHook(() =>
      useAllocationSelection([R1, R2, R3_LOCKED])
    );

    act(() => result.current.toggle("r1"));
    expect(result.current.isSelected("r1")).toBe(true);
    expect(result.current.selectedRows.map((row) => row.id)).toEqual(["r1"]);

    act(() => result.current.toggle("r3"));
    expect(result.current.isSelected("r3")).toBe(false);
    expect(result.current.selectedRows.map((row) => row.id)).toEqual(["r1"]);

    act(() => result.current.toggle("r1"));
    expect(result.current.isSelected("r1")).toBe(false);
    expect(result.current.selectedRows).toEqual([]);
  });

  it("selectAll covers visible unlocked rows only", () => {
    const { result } = renderHook(() =>
      useAllocationSelection([R1, R2, R3_LOCKED])
    );

    act(() => result.current.selectAll());

    expect(result.current.selectedRows.map((row) => row.id)).toEqual([
      "r1",
      "r2",
    ]);
    expect(result.current.isSelected("r3")).toBe(false);
  });

  it("keeps the tick across a filter change but only reports visible rows", () => {
    const { result, rerender } = renderHook(
      ({ rows }: { rows: readonly AllocationRow[] }) =>
        useAllocationSelection(rows),
      { initialProps: { rows: [R1, R2] as readonly AllocationRow[] } }
    );

    act(() => result.current.toggle("r1"));
    act(() => result.current.toggle("r2"));
    expect(result.current.selectedRows.map((row) => row.id)).toEqual([
      "r1",
      "r2",
    ]);

    // The filter hides r2: the tick is kept, the reported selection is not.
    rerender({ rows: [R1] });
    expect(result.current.selectedRows.map((row) => row.id)).toEqual(["r1"]);
    expect(result.current.isSelected("r2")).toBe(false);

    // Widening the filter again restores it — nothing was thrown away.
    rerender({ rows: [R1, R2] });
    expect(result.current.selectedRows.map((row) => row.id)).toEqual([
      "r1",
      "r2",
    ]);
  });

  it("selectAll does not drop ticks on rows the filter currently hides", () => {
    const { result, rerender } = renderHook(
      ({ rows }: { rows: readonly AllocationRow[] }) =>
        useAllocationSelection(rows),
      { initialProps: { rows: [R1, R2] as readonly AllocationRow[] } }
    );

    act(() => result.current.toggle("r2"));
    rerender({ rows: [R1] });
    act(() => result.current.selectAll());
    rerender({ rows: [R1, R2] });

    expect(result.current.selectedRows.map((row) => row.id)).toEqual([
      "r1",
      "r2",
    ]);
  });

  it("drops a row from the selection when it becomes locked", () => {
    const { result, rerender } = renderHook(
      ({ rows }: { rows: readonly AllocationRow[] }) =>
        useAllocationSelection(rows),
      { initialProps: { rows: [R1] as readonly AllocationRow[] } }
    );

    act(() => result.current.toggle("r1"));
    rerender({ rows: [{ ...R1, locked: "approved" }] });

    expect(result.current.isSelected("r1")).toBe(false);
    expect(result.current.selectedRows).toEqual([]);
  });

  it("clear empties every tick, including hidden ones", () => {
    const { result, rerender } = renderHook(
      ({ rows }: { rows: readonly AllocationRow[] }) =>
        useAllocationSelection(rows),
      { initialProps: { rows: [R1, R2] as readonly AllocationRow[] } }
    );

    act(() => result.current.selectAll());
    rerender({ rows: [R1] });
    act(() => result.current.clear());
    rerender({ rows: [R1, R2] });

    expect(result.current.selectedRows).toEqual([]);
  });
});
