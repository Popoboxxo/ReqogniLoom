/**
 * Task 4.5 — column picker and persisted table state
 * (plan 2026-11-04-tabellenansicht-s4).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, render, renderHook, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "../i18n/index";

import type { AttributeSpec } from "../api/attribute-definitions";

const mockGet = vi.fn();
const mockPut = vi.fn();

vi.mock("../api/table-views", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/table-views")>();
  return {
    ...actual,
    tableViewStateApi: {
      get: (...a: unknown[]) => mockGet(...a),
      put: (...a: unknown[]) => mockPut(...a),
    },
  };
});

import { ColumnPicker } from "../components/shared/ArtifactTable/ColumnPicker";
import {
  TABLE_STATE_DEBOUNCE_MS,
  useTableViewState,
} from "../components/shared/ArtifactTable/useTableViewState";

function attr(name: string, order = 0): AttributeSpec {
  return {
    name,
    kind: "core",
    type: "text",
    widget_key: null,
    fields: [],
    options: [],
    required: false,
    visible: true,
    locked: false,
    editable: true,
    section: "basics",
    order,
    label: { de: name, en: name },
    help_text: { de: "", en: "" },
    default: null,
    validation: {},
    ai_elicit: false,
    export: true,
    audience: "basic",
  };
}

const STATE = { columns: [], filters: {}, sort: [] };

describe("ColumnPicker", () => {
  it("toggles and reorders columns", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <ColumnPicker
        attributes={[attr("title", 0), attr("status", 1)]}
        state={STATE}
        onChange={onChange}
      />
    );
    await user.click(screen.getByTestId("column-toggle-status"));
    expect(onChange).toHaveBeenLastCalledWith({
      ...STATE,
      columns: [{ field: "title", order: 0 }],
    });
  });

  it("reorders with buttons, no pointer drag needed", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <ColumnPicker
        attributes={[attr("title", 0), attr("status", 1)]}
        state={STATE}
        onChange={onChange}
      />
    );
    await user.click(screen.getByTestId("column-down-title"));
    expect(onChange).toHaveBeenLastCalledWith({
      ...STATE,
      columns: [
        { field: "status", order: 0 },
        { field: "title", order: 1 },
      ],
    });
  });

  // The stored list is a whitelist (see buildColumns): a column the user hid
  // must render unchecked and be re-addable, otherwise the picker lies about
  // what the grid shows.
  it("renders a hidden column unchecked and re-adds it last", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    const state = { columns: [{ field: "status", order: 0 }], filters: {}, sort: [] };
    render(
      <ColumnPicker
        attributes={[attr("title", 0), attr("status", 1)]}
        state={state}
        onChange={onChange}
      />
    );
    expect(screen.getByTestId("column-toggle-status")).toBeChecked();
    expect(screen.getByTestId("column-toggle-title")).not.toBeChecked();

    await user.click(screen.getByTestId("column-toggle-title"));
    expect(onChange).toHaveBeenLastCalledWith({
      ...state,
      columns: [
        { field: "status", order: 0 },
        { field: "title", order: 1 },
      ],
    });
  });
});

describe("useTableViewState", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  async function settle(): Promise<void> {
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
  }

  it("loads defaults when no state was saved (404 degrades)", async () => {
    mockGet.mockRejectedValue({ error: { code: "NOT_FOUND" } });
    const { result } = renderHook(() => useTableViewState("ws", "Requirement"));
    await settle();
    expect(result.current.ready).toBe(true);
    expect(result.current.state).toEqual(STATE);
  });

  it("debounces several edits into one PUT", async () => {
    mockGet.mockResolvedValue(STATE);
    mockPut.mockResolvedValue(STATE);
    const { result } = renderHook(() => useTableViewState("ws", "Requirement"));
    await settle();

    act(() => result.current.setState({ ...STATE, sort: [{ field: "a", dir: "asc" }] }));
    act(() => result.current.setState({ ...STATE, sort: [{ field: "b", dir: "asc" }] }));
    await act(async () => {
      vi.advanceTimersByTime(TABLE_STATE_DEBOUNCE_MS);
      await Promise.resolve();
    });
    expect(mockPut).toHaveBeenCalledTimes(1);
    expect(mockPut.mock.calls[0][2].sort).toEqual([{ field: "b", dir: "asc" }]);
  });

  it("flushes a pending PUT on unmount", async () => {
    mockGet.mockResolvedValue(STATE);
    mockPut.mockResolvedValue(STATE);
    const { result, unmount } = renderHook(() => useTableViewState("ws", "Requirement"));
    await settle();
    act(() => result.current.setState({ ...STATE, columns: [{ field: "x", order: 0 }] }));
    unmount();
    expect(mockPut).toHaveBeenCalledTimes(1);
  });

  it("keeps local state and does not throw when the PUT fails", async () => {
    mockGet.mockResolvedValue(STATE);
    mockPut.mockRejectedValue({ error: { message: "nope" } });
    const { result } = renderHook(() => useTableViewState("ws", "Requirement"));
    await settle();
    const next = { ...STATE, columns: [{ field: "x", order: 0 }] };
    act(() => result.current.setState(next));
    await act(async () => {
      vi.advanceTimersByTime(TABLE_STATE_DEBOUNCE_MS);
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(result.current.state.columns).toEqual([{ field: "x", order: 0 }]);
    // The hook surfaces the rejected PUT's message verbatim — assert the
    // content, not merely that *some* truthy value landed in `error`.
    expect(result.current.error).toContain("nope");
  });

  it("loads the state of the newly selected item type", async () => {
    mockGet.mockResolvedValue({ ...STATE, sort: [{ field: "title", dir: "asc" }] });
    const { result, rerender } = renderHook(
      ({ type }: { type: string }) => useTableViewState("ws", type),
      { initialProps: { type: "Requirement" } }
    );
    await settle();
    mockGet.mockResolvedValue({ ...STATE, sort: [{ field: "name", dir: "desc" }] });
    rerender({ type: "Risk" });
    await settle();
    expect(mockGet).toHaveBeenLastCalledWith("ws", "Risk");
    expect(result.current.state.sort).toEqual([{ field: "name", dir: "desc" }]);
  });
});
