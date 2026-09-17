/**
 * ARCH-L1-001 ReactFrontend — usePersistedListState hook.
 *
 * BUG-19 (docs/SYSTEMAUDIT_2026-08-18.md §4): sessionStorage-backed
 * replacement for useState used by list-view filter/sort controls, so
 * selections survive an unmount/remount (route change) within a tab
 * session. See src/hooks/usePersistedListState.ts for the full rationale.
 */

import { describe, it, expect, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { usePersistedListState } from "../hooks/usePersistedListState";

describe("usePersistedListState", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
  });

  it("returns the initial value when nothing is stored yet", () => {
    const { result } = renderHook(() =>
      usePersistedListState("test:key:a", "default")
    );
    expect(result.current[0]).toBe("default");
  });

  it("persists updates to sessionStorage under the given key", () => {
    const { result } = renderHook(() =>
      usePersistedListState("test:key:b", "")
    );

    act(() => {
      result.current[1]("changed");
    });

    expect(result.current[0]).toBe("changed");
    expect(window.sessionStorage.getItem("test:key:b")).toBe(
      JSON.stringify("changed")
    );
  });

  it("rehydrates from sessionStorage on a fresh mount with the same key", () => {
    const { result: first } = renderHook(() =>
      usePersistedListState("test:key:c", "")
    );
    act(() => {
      first.current[1]("status");
    });

    // Fresh hook instance, same key — simulates a remount after navigation.
    const { result: second } = renderHook(() =>
      usePersistedListState("test:key:c", "")
    );
    expect(second.current[0]).toBe("status");
  });

  it("falls back to the initial value for a corrupt stored payload", () => {
    window.sessionStorage.setItem("test:key:d", "{not valid json");
    const { result } = renderHook(() =>
      usePersistedListState("test:key:d", "fallback")
    );
    expect(result.current[0]).toBe("fallback");
  });

  // Review finding F-03: a plain `useState(() => readStored(key, ...))`
  // only evaluates its initializer on first mount, so it can't react to a
  // later `key` change — the caller (RequirementList, F-02 fix) derives the
  // key from the active workspace ID, which changes across rerenders
  // without an unmount when the user switches workspaces.
  it("re-reads sessionStorage when `key` changes across rerenders (no unmount)", () => {
    const { result, rerender } = renderHook(
      ({ key }: { key: string }) => usePersistedListState(key, "default"),
      { initialProps: { key: "test:key:e1" } }
    );

    act(() => {
      result.current[1]("e1-value");
    });
    expect(result.current[0]).toBe("e1-value");

    // Switch to a key that has never been written — must show the initial
    // value, NOT carry over "e1-value" from the old key.
    rerender({ key: "test:key:e2" });
    expect(result.current[0]).toBe("default");

    // Switching back to the first key must restore ITS OWN value — proving
    // the earlier `rerender` didn't clobber "test:key:e1" in storage with
    // the stale in-memory value under the wrong key.
    rerender({ key: "test:key:e1" });
    expect(result.current[0]).toBe("e1-value");
  });

  it("does not overwrite the new key's stored value with the old key's value on key change", () => {
    // Pre-seed both keys as if from earlier sessions.
    window.sessionStorage.setItem("test:key:f1", JSON.stringify("from-f1"));
    window.sessionStorage.setItem("test:key:f2", JSON.stringify("from-f2"));

    const { result, rerender } = renderHook(
      ({ key }: { key: string }) => usePersistedListState(key, "default"),
      { initialProps: { key: "test:key:f1" } }
    );
    expect(result.current[0]).toBe("from-f1");

    rerender({ key: "test:key:f2" });
    expect(result.current[0]).toBe("from-f2");

    // The bug this guards against: an effect keyed only on the NEW key
    // writing the OLD (stale) in-memory value into it would corrupt
    // "test:key:f2" here.
    expect(window.sessionStorage.getItem("test:key:f2")).toBe(
      JSON.stringify("from-f2")
    );
  });
});
