/**
 * ARCH-L1-001 ReactFrontend — usePersistedListState hook.
 *
 * BUG-19 (docs/SYSTEMAUDIT_2026-08-18.md §4): sessionStorage-backed
 * replacement for useState used by list-view filter/sort controls, so
 * selections survive an unmount/remount (route change) within a tab
 * session. See src/hooks/usePersistedListState.ts for the full rationale.
 *
 * Code-quality audit blocker 5: reads are shape-validated against the
 * initial value (or a caller-supplied `validate`) instead of trusting
 * `JSON.parse(raw) as T` — valid JSON of the wrong shape falls back to the
 * initial value just like corrupt JSON does.
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

  it("falls back to the initial value for valid JSON of an incompatible shape", () => {
    // A number where the caller expects a string — JSON.parse succeeds, but
    // the payload is foreign to this hook instance and must be discarded.
    window.sessionStorage.setItem("test:key:g", JSON.stringify(42));
    const { result } = renderHook(() =>
      usePersistedListState("test:key:g", "fallback")
    );
    expect(result.current[0]).toBe("fallback");
  });

  it("still restores a stored value whose shape matches the initial value", () => {
    window.sessionStorage.setItem("test:key:h", JSON.stringify({ q: "needle" }));
    const { result } = renderHook(() =>
      usePersistedListState("test:key:h", { q: "" })
    );
    expect(result.current[0]).toEqual({ q: "needle" });
  });

  it("rejects an array where the initial value is an object", () => {
    window.sessionStorage.setItem(
      "test:key:i",
      JSON.stringify(["not", "an", "object"])
    );
    const { result } = renderHook(() =>
      usePersistedListState<{ q: string }>("test:key:i", { q: "" })
    );
    expect(result.current[0]).toEqual({ q: "" });
  });

  it("rejects a non-array where the initial value is an array", () => {
    window.sessionStorage.setItem("test:key:j", JSON.stringify({ q: "" }));
    const { result } = renderHook(() =>
      usePersistedListState<string[]>("test:key:j", [])
    );
    expect(result.current[0]).toEqual([]);
  });

  it("lets a caller-supplied validate replace the derived shape check", () => {
    // `typeof` alone accepts any string; the caller's guard narrows the
    // payload to the union the list actually supports (RequirementList's
    // ReqSortKey case) — a foreign string is rejected...
    const validate = (value: unknown): value is "default" | "title" =>
      value === "default" || value === "title";

    window.sessionStorage.setItem("test:key:k", JSON.stringify("not-a-sort-key"));
    const { result } = renderHook(() =>
      usePersistedListState<"default" | "title">("test:key:k", "default", { validate })
    );
    expect(result.current[0]).toBe("default");

    // ...while a value the guard approves is still restored.
    window.sessionStorage.setItem("test:key:k", JSON.stringify("title"));
    const { result: accepted } = renderHook(() =>
      usePersistedListState<"default" | "title">("test:key:k", "default", { validate })
    );
    expect(accepted.current[0]).toBe("title");
  });
});
