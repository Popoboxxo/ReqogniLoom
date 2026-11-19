/**
 * T-C2-7 (Plan C) / issue #1094 REST + Task 2 — `PreferencesHydrator` tests.
 *
 * The rest of #1094 is a *start-up* problem: before this component, the only
 * reader of the server value was `IdentifiersSection`, so a new device showed
 * the wrong readable-id visibility until the user visited `/profile`. Task 2
 * extends the same lifecycle to the two new independent display flags
 * (`trace_footer_enabled`, `inspector_enabled`): the localStorage store gives
 * every consumer a value on the very first paint, then the server value wins
 * as soon as the self-service query settles.
 *
 *   - the server value wins over the localStorage first-render cache as soon
 *     as the query settles (a rendered probe follows the store, so the
 *     assertion is observable, not internal);
 *   - a rejected query leaves the cached value untouched — a preference load
 *     must never blank the UI;
 *   - the two flags hydrate independently (one server value never moves the
 *     other store);
 *   - with no signed-in user no request is made at all.
 */

import { act, render, screen, waitFor } from "@testing-library/react";
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

vi.mock("../api/display-preferences", () => ({
  displayPreferencesApi: { get: vi.fn(), update: vi.fn() },
}));

import {
  DISPLAY_PREFERENCES_QUERY_KEY,
  PreferencesHydrator,
} from "./PreferencesHydrator";
import { displayPreferencesApi } from "../api/display-preferences";
import { preferenceValuesApi } from "../api/preference-values";
import { preferenceKeys } from "../queries/preferences";
import { IdChip } from "./shared/IdChip";
import {
  getReadableIdsVisible,
  setReadableIdsVisible,
  useReadableIdsVisible,
} from "../hooks/useReadableIdsVisible";
import {
  getInspectorVisible,
  setInspectorVisible,
  useInspectorVisible,
} from "../hooks/useInspectorVisible";
import {
  getTraceFooterVisible,
  setTraceFooterVisible,
  useTraceFooterVisible,
} from "../hooks/useTraceFooterVisible";

const WORKSPACE_ID = "ws-1";
const UID = "REQ-001";
const UUID = "12345678-1234-4abc-8def-1234567890ab";

const SERVER_PREFS = {
  show_readable_ids: true,
  visible_metrics: null,
  trace_footer_enabled: true,
  inspector_enabled: true,
};

/** A real consumer of the readable-id store — what the user actually sees. */
function IdChipProbe(): JSX.Element {
  const [visible] = useReadableIdsVisible();
  return <IdChip uid={UID} systemId={UUID} hideReadable={!visible} testId="probe" />;
}

/** A real consumer of BOTH new stores, rendered as observable text. */
function VisibilityProbe(): JSX.Element {
  const [footer] = useTraceFooterVisible();
  const [inspector] = useInspectorVisible();
  return (
    <div data-testid="visibility-probe">{`footer=${footer},inspector=${inspector}`}</div>
  );
}

function renderHydrator(): QueryClient {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <PreferencesHydrator />
      <IdChipProbe />
      <VisibilityProbe />
    </QueryClientProvider>
  );
  return queryClient;
}

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  // Cached first-render values: readable ids visible, both new flags visible.
  setReadableIdsVisible(true);
  setTraceFooterVisible(true);
  setInspectorVisible(true);
  vi.mocked(displayPreferencesApi.get).mockResolvedValue(SERVER_PREFS);
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

    await act(async () => {});
    expect(screen.getByTestId("probe-value")).toHaveTextContent(UID);

    expect(preferenceValuesApi.effective).not.toHaveBeenCalled();
    expect(displayPreferencesApi.get).not.toHaveBeenCalled();
    expect(getReadableIdsVisible()).toBe(true);
  });
});

describe("PreferencesHydrator — Task 2 display flags", () => {
  it("hydrates both flags before first paint is replaced by the server value", async () => {
    // The synchronous stores paint the localStorage cache first; the server
    // value then replaces both — visible as a live DOM change in the probe.
    setTraceFooterVisible(false);
    setInspectorVisible(false);
    vi.mocked(displayPreferencesApi.get).mockResolvedValue({
      ...SERVER_PREFS,
      trace_footer_enabled: true,
      inspector_enabled: true,
    });

    renderHydrator();

    expect(screen.getByTestId("visibility-probe")).toHaveTextContent(
      "footer=false,inspector=false"
    );
    await waitFor(() =>
      expect(screen.getByTestId("visibility-probe")).toHaveTextContent(
        "footer=true,inspector=true"
      )
    );
    expect(getTraceFooterVisible()).toBe(true);
    expect(getInspectorVisible()).toBe(true);
    expect(displayPreferencesApi.get).toHaveBeenCalledTimes(1);
  });

  it("hydrates the two flags independently", async () => {
    setTraceFooterVisible(false);
    setInspectorVisible(true);
    vi.mocked(displayPreferencesApi.get).mockResolvedValue({
      ...SERVER_PREFS,
      trace_footer_enabled: true,
      inspector_enabled: false,
    });

    renderHydrator();

    await waitFor(() =>
      expect(screen.getByTestId("visibility-probe")).toHaveTextContent(
        "footer=true,inspector=false"
      )
    );
    expect(getTraceFooterVisible()).toBe(true);
    expect(getInspectorVisible()).toBe(false);
  });

  it("keeps both cached flags when the display-preferences query rejects", async () => {
    setTraceFooterVisible(false);
    setInspectorVisible(false);
    vi.mocked(displayPreferencesApi.get).mockRejectedValue(new Error("offline"));

    const queryClient = renderHydrator();

    await waitFor(() =>
      expect(
        queryClient.getQueryState(DISPLAY_PREFERENCES_QUERY_KEY)?.status
      ).toBe("error")
    );
    expect(screen.getByTestId("visibility-probe")).toHaveTextContent(
      "footer=false,inspector=false"
    );
    expect(getTraceFooterVisible()).toBe(false);
    expect(getInspectorVisible()).toBe(false);
  });
});
