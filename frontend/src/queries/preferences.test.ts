/**
 * Q1 preference query hooks (Plan C, T-C2-5).
 *
 * Pins the behaviour the settings sections and the future hydration consumer
 * rely on:
 *
 *   - `useEffectivePreferences` reads through the wrapper and caches under the
 *     `preferenceKeys.effective` key (so a PATCH can invalidate it by prefix);
 *     its optional `enabled` flag keeps the first-load placeholder id idle;
 *   - `usePreferenceValue` degrades to the caller's `fallback` while loading
 *     and on error — a preference never blocks a render;
 *   - a *falsy* stored value is a real value (`false`/`0`/`""`), not "unset";
 *   - `usePatchPreferenceLevel` writes through the level route and invalidates
 *     the whole `preferences` namespace, because one write changes both the
 *     level and the effective value.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement, type ReactNode } from "react";

import { preferenceValuesApi } from "../api/preference-values";
import { PLACEHOLDER_WORKSPACE_ID } from "../utils/workspaceId";
import {
  preferenceKeys,
  useEffectivePreferences,
  usePatchPreferenceLevel,
  usePreferenceLevel,
  usePreferenceValue,
} from "./preferences";

vi.mock("../api/preference-values");
const mockUseOptionalWorkspace = vi.fn();
vi.mock("../context/WorkspaceContext", () => ({
  useOptionalWorkspace: () => mockUseOptionalWorkspace(),
  useWorkspace: () => ({ activeWorkspace: { id: "ws-1" } }),
}));

beforeEach(() => {
  mockUseOptionalWorkspace.mockReturnValue({
    activeWorkspace: { id: "ws-1" },
    isLoadingWorkspace: false,
  });
});

function newQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
}

function wrapper(queryClient: QueryClient) {
  // `.ts` (not `.tsx`) because the task contract fixes this path — build the
  // provider element without JSX.
  return ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client: queryClient }, children);
}

describe("preferenceKeys", () => {
  it("shapes the effective and level keys so a prefix invalidation matches both", () => {
    expect(preferenceKeys.effective("ws-1")).toEqual([
      "preferences",
      "effective",
      "ws-1",
    ]);
    expect(preferenceKeys.effective(null)).toEqual([
      "preferences",
      "effective",
      null,
    ]);
    expect(preferenceKeys.level("workspace", "ws-1")).toEqual([
      "preferences",
      "level",
      "workspace",
      "ws-1",
    ]);
    expect(preferenceKeys.level("user")).toEqual([
      "preferences",
      "level",
      "user",
      null,
    ]);
  });
});

describe("useEffectivePreferences", () => {
  beforeEach(() => vi.clearAllMocks());

  it("reads and caches the workspace-scoped effective values", async () => {
    vi.mocked(preferenceValuesApi.effective).mockResolvedValue({
      workspace_id: "ws-1",
      values: {
        "ui.markdown.toolbar": { value: "on", source: "workspace" },
      },
    });
    const queryClient = newQueryClient();

    const { result } = renderHook(
      () => useEffectivePreferences("ws-1"),
      { wrapper: wrapper(queryClient) }
    );

    await waitFor(() =>
      expect(result.current.data?.values["ui.markdown.toolbar"]).toEqual({
        value: "on",
        source: "workspace",
      })
    );
    expect(preferenceValuesApi.effective).toHaveBeenCalledWith("ws-1");
    expect(
      queryClient.getQueryData(preferenceKeys.effective("ws-1"))
    ).toBeDefined();
  });

  it("reads the account-wide view when there is no workspace", async () => {
    vi.mocked(preferenceValuesApi.effective).mockResolvedValue({
      workspace_id: null,
      values: {},
    });
    const queryClient = newQueryClient();

    const { result } = renderHook(() => useEffectivePreferences(null), {
      wrapper: wrapper(queryClient),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(preferenceValuesApi.effective).toHaveBeenCalledWith(null);
  });

  it("stays idle when disabled, even with a truthy workspace id", async () => {
    // Mirrors the first-load state: the context carries the fake placeholder
    // UUID, so a truthy id alone is not a signal that the workspace resolved.
    const queryClient = newQueryClient();

    const { result } = renderHook(
      () => useEffectivePreferences("00000000-0000-0000-0000-000000000000", false),
      { wrapper: wrapper(queryClient) }
    );

    await act(async () => {});
    expect(preferenceValuesApi.effective).not.toHaveBeenCalled();
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("stays idle for a truthy id while the workspace is still the placeholder", async () => {
    // FR-01: isLoadingWorkspace is false during auth restore, so identity is
    // the only reliable signal. Covers id-only consumers (PreferenceLevelSection).
    mockUseOptionalWorkspace.mockReturnValue({
      activeWorkspace: { id: PLACEHOLDER_WORKSPACE_ID },
      isLoadingWorkspace: false,
    });
    const queryClient = newQueryClient();

    const { result } = renderHook(
      () => useEffectivePreferences("00000000-0000-0000-0000-000000000000"),
      { wrapper: wrapper(queryClient) }
    );

    await act(async () => {});
    expect(preferenceValuesApi.effective).not.toHaveBeenCalled();
    expect(result.current.fetchStatus).toBe("idle");
  });
});

describe("usePreferenceValue", () => {
  beforeEach(() => vi.clearAllMocks());

  it("returns the fallback until the value arrives, then the effective value", async () => {
    vi.mocked(preferenceValuesApi.effective).mockResolvedValue({
      workspace_id: "ws-1",
      values: { "ui.markdown.toolbar": { value: "off", source: "user" } },
    });
    const queryClient = newQueryClient();

    const { result } = renderHook(
      () => usePreferenceValue("ui.markdown.toolbar", "auto"),
      { wrapper: wrapper(queryClient) }
    );

    expect(result.current).toBe("auto");
    await waitFor(() => expect(result.current).toBe("off"));
    // The hook resolves against the active workspace.
    expect(preferenceValuesApi.effective).toHaveBeenCalledWith("ws-1");
  });

  it("treats a stored `false` as a value, not as 'unset'", async () => {
    vi.mocked(preferenceValuesApi.effective).mockResolvedValue({
      workspace_id: "ws-1",
      values: { "ui.ids.show_readable": { value: false, source: "user" } },
    });
    const queryClient = newQueryClient();

    const { result } = renderHook(
      () => usePreferenceValue("ui.ids.show_readable", true),
      { wrapper: wrapper(queryClient) }
    );

    await waitFor(() => expect(result.current).toBe(false));
  });

  it("degrades to the fallback when the read fails", async () => {
    vi.mocked(preferenceValuesApi.effective).mockRejectedValue(
      new Error("offline")
    );
    const queryClient = newQueryClient();

    const { result } = renderHook(
      () => usePreferenceValue("ui.markdown.toolbar", "auto"),
      { wrapper: wrapper(queryClient) }
    );

    await waitFor(() =>
      expect(preferenceValuesApi.effective).toHaveBeenCalled()
    );
    expect(result.current).toBe("auto");
  });

  it("makes no request while the workspace is a placeholder, then reads the real id", async () => {
    // FR-01 failing path: isLoadingWorkspace=false + placeholder workspace id.
    const PLACEHOLDER = "00000000-0000-0000-0000-000000000000";
    mockUseOptionalWorkspace.mockReturnValue({
      activeWorkspace: { id: PLACEHOLDER_WORKSPACE_ID },
      isLoadingWorkspace: false,
    });
    vi.mocked(preferenceValuesApi.effective).mockResolvedValue({
      workspace_id: "ws-1",
      values: { "ui.markdown.toolbar": { value: "off", source: "user" } },
    });
    const queryClient = newQueryClient();

    const { result, rerender } = renderHook(
      () => usePreferenceValue("ui.markdown.toolbar", "auto"),
      { wrapper: wrapper(queryClient) }
    );

    await act(async () => {});
    expect(preferenceValuesApi.effective).not.toHaveBeenCalled();
    expect(result.current).toBe("auto");

    mockUseOptionalWorkspace.mockReturnValue({
      activeWorkspace: { id: "ws-1" },
      isLoadingWorkspace: false,
    });
    rerender();

    await waitFor(() => expect(result.current).toBe("off"));
    expect(preferenceValuesApi.effective).toHaveBeenCalledWith("ws-1");
    expect(preferenceValuesApi.effective).not.toHaveBeenCalledWith(PLACEHOLDER);
    expect(preferenceValuesApi.effective).not.toHaveBeenCalledWith(null);
  });
});

describe("usePreferenceLevel", () => {
  beforeEach(() => vi.clearAllMocks());

  it("does not read the workspace level against the placeholder", async () => {
    const PLACEHOLDER = "00000000-0000-0000-0000-000000000000";
    mockUseOptionalWorkspace.mockReturnValue({
      activeWorkspace: { id: PLACEHOLDER_WORKSPACE_ID },
      isLoadingWorkspace: false,
    });
    vi.mocked(preferenceValuesApi.getLevel).mockResolvedValue({
      scope: "workspace",
      workspace_id: "ws-1",
      values: {},
    });
    const queryClient = newQueryClient();
    let currentId: string | null = PLACEHOLDER;

    const { result, rerender } = renderHook(
      () => usePreferenceLevel("workspace", currentId ?? undefined),
      { wrapper: wrapper(queryClient) }
    );

    await act(async () => {});
    expect(preferenceValuesApi.getLevel).not.toHaveBeenCalled();
    expect(result.current.fetchStatus).toBe("idle");

    currentId = "ws-1";
    mockUseOptionalWorkspace.mockReturnValue({
      activeWorkspace: { id: "ws-1" },
      isLoadingWorkspace: false,
    });
    rerender();

    await waitFor(() =>
      expect(preferenceValuesApi.getLevel).toHaveBeenCalledWith(
        "workspace",
        "ws-1"
      )
    );
    expect(preferenceValuesApi.getLevel).not.toHaveBeenCalledWith(
      "workspace",
      PLACEHOLDER
    );
  });

  it("keeps account-wide levels readable while the workspace is a placeholder", async () => {
    mockUseOptionalWorkspace.mockReturnValue({
      activeWorkspace: { id: PLACEHOLDER_WORKSPACE_ID },
      isLoadingWorkspace: false,
    });
    vi.mocked(preferenceValuesApi.getLevel).mockResolvedValue({
      scope: "user",
      workspace_id: null,
      values: {},
    });
    const queryClient = newQueryClient();

    const { result } = renderHook(() => usePreferenceLevel("user"), {
      wrapper: wrapper(queryClient),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(preferenceValuesApi.getLevel).toHaveBeenCalledWith("user", undefined);
  });
});

describe("usePatchPreferenceLevel", () => {
  beforeEach(() => vi.clearAllMocks());

  it("writes through the level route and invalidates the preferences namespace", async () => {
    vi.mocked(preferenceValuesApi.patchLevel).mockResolvedValue({
      scope: "user",
      workspace_id: null,
      values: { "ui.markdown.toolbar": "on" },
    });
    const queryClient = newQueryClient();
    const invalidate = vi.spyOn(queryClient, "invalidateQueries");

    const { result } = renderHook(() => usePatchPreferenceLevel("user"), {
      wrapper: wrapper(queryClient),
    });

    await result.current.mutateAsync({ "ui.markdown.toolbar": "on" });

    expect(preferenceValuesApi.patchLevel).toHaveBeenCalledWith(
      "user",
      { "ui.markdown.toolbar": "on" },
      undefined
    );
    await waitFor(() =>
      expect(invalidate).toHaveBeenCalledWith({ queryKey: ["preferences"] })
    );
  });

  it("passes the workspace id through for the workspace level", async () => {
    vi.mocked(preferenceValuesApi.patchLevel).mockResolvedValue({
      scope: "workspace",
      workspace_id: "ws-1",
      values: {},
    });
    const queryClient = newQueryClient();

    const { result } = renderHook(
      () => usePatchPreferenceLevel("workspace", "ws-1"),
      { wrapper: wrapper(queryClient) }
    );

    await result.current.mutateAsync({ "ui.ids.show_readable": null });

    expect(preferenceValuesApi.patchLevel).toHaveBeenCalledWith(
      "workspace",
      { "ui.ids.show_readable": null },
      "ws-1"
    );
  });
});
