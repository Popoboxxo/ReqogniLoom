/**
 * T-C2-7 (Plan C) / issue #1094 REST — `PreferencesHydrator` unit tests.
 *
 * The rest of #1094 is a *start-up* problem: before this component, the only
 * reader of the server value was `IdentifiersSection`, so a new device showed
 * the wrong readable-id visibility until the user visited `/profile`. The
 * contract pinned here:
 *
 *   - the server value wins over the localStorage first-render cache as soon
 *     as the effective-preference query settles (a rendered `<IdChip>` follows
 *     the store, so the assertion is observable, not internal);
 *   - a rejected query leaves the cached value untouched — a preference load
 *     must never blank the UI;
 *   - a missing key behaves like a rejected query (do nothing);
 *   - with no signed-in user no request is made at all.
 *
 * The network is stubbed at the API boundary (`vi.mock` of
 * `api/preference-values`), the same pattern as `api/*.test.ts` and
 * `queries/preferences.test.ts` — the hydrator itself is rendered for real.
 */

import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { resolveLocaleKey } from "../test/i18n-test-helpers";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) => {
      const { defaultValue, ...interpolation } = options ?? {};
      const resolved =
        resolveLocaleKey(key) ??
        (typeof defaultValue === "string" ? defaultValue : key);
      return Object.entries(interpolation).reduce(
        (acc, [name, value]) => acc.replace(`{{${name}}}`, String(value)),
        resolved
      );
    },
    i18n: { language: "de" },
  }),
}));

const mockUseAuth = vi.fn();
vi.mock("../context/AuthContext", () => ({
  useAuth: () => mockUseAuth(),
}));

const mockUseWorkspace = vi.fn();
vi.mock("../context/WorkspaceContext", () => ({
  useWorkspace: () => mockUseWorkspace(),
  useOptionalWorkspace: () => mockUseWorkspace(),
}));

vi.mock("../api/preference-values", () => ({
  preferenceValuesApi: { effective: vi.fn() },
}));

import { PreferencesHydrator } from "./PreferencesHydrator";
import { preferenceValuesApi } from "../api/preference-values";
import { preferenceKeys } from "../queries/preferences";
import { IdChip } from "./shared/IdChip";
import {
  getReadableIdsVisible,
  setReadableIdsVisible,
  useReadableIdsVisible,
} from "../hooks/useReadableIdsVisible";

const WORKSPACE_ID = "ws-1";
const UID = "REQ-001";
const UUID = "12345678-1234-4abc-8def-1234567890ab";

/** A real consumer of the shared store — what the user actually sees. */
function IdChipProbe(): JSX.Element {
  const [visible] = useReadableIdsVisible();
  return <IdChip uid={UID} systemId={UUID} hideReadable={!visible} testId="probe" />;
}

function renderHydrator(): QueryClient {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <PreferencesHydrator />
      <IdChipProbe />
    </QueryClientProvider>
  );
  return queryClient;
}

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  // Cached first-render value: readable ids visible.
  setReadableIdsVisible(true);
  mockUseAuth.mockReturnValue({ status: "authenticated" });
  mockUseWorkspace.mockReturnValue({ activeWorkspace: { id: WORKSPACE_ID } });
});

describe("PreferencesHydrator (T-C2-7)", () => {
  it("adopts the server value on start-up so a fresh device hides readable ids", async () => {
    vi.mocked(preferenceValuesApi.effective).mockResolvedValue({
      workspace_id: WORKSPACE_ID,
      values: { "ui.ids.show_readable": { value: false, source: "user" } },
    });

    renderHydrator();

    // The cache paints the readable id immediately …
    expect(screen.getByTestId("probe-value")).toHaveTextContent(UID);

    // … and the server value replaces it once the effective read settles.
    await waitFor(() => expect(getReadableIdsVisible()).toBe(false));
    await waitFor(() =>
      expect(screen.queryByTestId("probe-value")).not.toBeInTheDocument()
    );
    // Copying the system id stays available — hiding is a display choice.
    expect(screen.getByTestId("probe-copy")).toBeInTheDocument();
    expect(preferenceValuesApi.effective).toHaveBeenCalledWith(WORKSPACE_ID);
  });

  it("keeps the previous value when the query rejects", async () => {
    vi.mocked(preferenceValuesApi.effective).mockRejectedValue(new Error("offline"));

    const queryClient = renderHydrator();

    await waitFor(() =>
      expect(
        queryClient.getQueryState(preferenceKeys.effective(WORKSPACE_ID))?.status
      ).toBe("error")
    );

    expect(getReadableIdsVisible()).toBe(true);
    expect(screen.getByTestId("probe-value")).toHaveTextContent(UID);
  });

  it("does nothing when the resolved payload carries no value for the key", async () => {
    vi.mocked(preferenceValuesApi.effective).mockResolvedValue({
      workspace_id: WORKSPACE_ID,
      values: {},
    });

    const queryClient = renderHydrator();

    await waitFor(() =>
      expect(
        queryClient.getQueryState(preferenceKeys.effective(WORKSPACE_ID))?.status
      ).toBe("success")
    );

    expect(getReadableIdsVisible()).toBe(true);
    expect(screen.getByTestId("probe-value")).toHaveTextContent(UID);
  });

  it("stays idle while no user is signed in", async () => {
    mockUseAuth.mockReturnValue({ status: "anonymous" });

    renderHydrator();

    // Give a prematurely enabled query a chance to fire before claiming it did not.
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(preferenceValuesApi.effective).not.toHaveBeenCalled();
    expect(getReadableIdsVisible()).toBe(true);
  });
});
