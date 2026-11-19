/**
 * TraceSpineFooter — horizontal derivation-chain footer (Schnitt 2a, Task 4).
 *
 * Exactly eight assertions (a)-(h) pin the contract from the plan §6:
 *   (a)  4 stations -> 4 chips, no `[+N]`
 *   (b)  5 stations -> `[+1 weitere]`
 *   (c)  6 stations -> `[+2 weitere]`
 *   (d)  active station at position 4 AND 6 stays visible with aria-current
 *   (e)  isOpenable=false (resolved:false / in-flight / error) -> chip disabled,
 *        no popover
 *   (f)  popover ESC closes and returns focus to the triggering chip
 *   (g)  1-station chain -> one-line placeholder, no crash
 *   (h)  no selection -> component not mounted, 0 px reserved
 *
 * The chain is produced by the REAL `useDerivationChain` hook living inside the
 * footer; only the two API wrappers are mocked. That is deliberate: the test
 * also proves the RPCs only fire when a footer with an artifact is mounted.
 *
 * i18n is mocked with a `defaultValue`-aware `t` so the literal German fallback
 * passed by the component is what gets asserted (the same pattern the vertical
 * TraceSpine suites use). i18n parity itself is guarded by a separate gate.
 */

import { act, render, screen, fireEvent, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: unknown): string => {
      if (typeof opts === "string") return opts;
      const template =
        opts && typeof opts === "object" && "defaultValue" in opts
          ? String((opts as { defaultValue: unknown }).defaultValue)
          : key;
      return template.replace(/\{\{(\w+)\}\}/g, (_m, k: string) =>
        String(
          opts && typeof opts === "object"
            ? (opts as Record<string, unknown>)[k] ?? ""
            : "",
        ),
      );
    },
  }),
}));

vi.mock("../../../api/client", async (importActual) => ({
  ...(await importActual<typeof import("../../../api/client")>()),
  extractErrorMessage: (): string => "error",
}));

vi.mock("../../../api/tracelinks", () => ({
  tracelinksApi: { impact: vi.fn() },
}));
vi.mock("../../../api/traceability", () => ({
  traceabilityApi: { resolve: vi.fn() },
}));

import { TraceSpineFooter } from "./TraceSpineFooter";
import {
  getExpandedMobileSheet,
  releaseMobileSheet,
  requestMobileSheet,
  resetMobileSheetCoordinator,
} from "../mobileSheetCoordinator";
import { tracelinksApi } from "../../../api/tracelinks";
import { traceabilityApi } from "../../../api/traceability";
import type { ArchitectureElement } from "../../../types";

/** A descriptor is turned into exactly one hook station. */
interface Descriptor {
  id: string;
  type: string;
  level?: number;
}

function makeElements(descriptors: Descriptor[]): ArchitectureElement[] {
  return descriptors
    .filter((d) => d.type === "ArchitectureElement")
    .map(
      (d) =>
        ({
          id: d.id,
          artifact_id: d.id,
          level: d.level ?? 0,
          title: d.id,
          description: "",
          element_type: "component",
          workspace_id: "ws-1",
          version: 1,
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
        }) as ArchitectureElement,
    );
}

/**
 * Wire the mocked APIs so the hook yields `descriptors` in order, with the
 * descriptor at `currentIndex` as the opened (active) artifact.
 */
function feedChain(
  descriptors: Descriptor[],
  currentIndex: number,
  resolveImpl: (ids: string[]) => Promise<unknown> = (ids) =>
    Promise.resolve(
      ids.map((id) => ({
        artifact_id: id,
        resolved: true,
        entity_type: "Requirement",
        entity_id: `entity-${id}`,
      })),
    ),
): Descriptor {
  const current = descriptors[currentIndex]!;
  vi.mocked(tracelinksApi.impact).mockImplementation(async (id, options) => {
    if (options?.direction !== "incoming") return [] as never;
    return descriptors
      .filter((d) => d.id !== id)
      .map((d) => ({
        artifact_id: d.id,
        artifact_type: d.type,
        title: `Title ${d.id}`,
        uid: `UID-${d.id}`,
        link_type: "derives-from",
        depth: 1,
        path: [current.id, d.id],
      })) as never;
  });
  vi.mocked(traceabilityApi.resolve).mockImplementation((ids) =>
    resolveImpl(ids as string[]) as never,
  );
  return current;
}

function renderFooter(
  current: Descriptor,
  descriptors: Descriptor[],
): ReturnType<typeof render> {
  return render(
    <TraceSpineFooter
      artifact={{
        artifactId: current.id,
        artifactType: current.type,
        level: current.level ?? null,
      }}
      architectureElements={makeElements(descriptors)}
      onOpenArtifact={vi.fn()}
    />,
  );
}

function chipButtons(): HTMLButtonElement[] {
  return screen.getAllByTestId("trace-footer-station") as HTMLButtonElement[];
}

function chipByKey(key: string): HTMLElement {
  const el = document.querySelector<HTMLElement>(
    `[data-testid="trace-footer-station"][data-station-key="${key}"]`,
  );
  if (!el) throw new Error(`no trace-footer chip for station key ${key}`);
  return el;
}

const FIVE_WITH_ACTIVE_AT_4: Descriptor[] = [
  { id: "need", type: "StakeholderNeed" },
  { id: "req", type: "Requirement" },
  { id: "arch0", type: "ArchitectureElement", level: 0 },
  { id: "current", type: "Current" }, // active, position 4
  { id: "goal", type: "Goal" },
];

const SIX_WITH_ACTIVE_AT_6: Descriptor[] = [
  { id: "need", type: "StakeholderNeed" },
  { id: "req", type: "Requirement" },
  { id: "arch0", type: "ArchitectureElement", level: 0 },
  { id: "arch1", type: "ArchitectureElement", level: 1 },
  { id: "arch2", type: "ArchitectureElement", level: 2 },
  { id: "current", type: "Current" }, // active, position 6
];

beforeEach(() => {
  vi.clearAllMocks();
  resetMobileSheetCoordinator();
});

describe("TraceSpineFooter — Schnitt 2a contract (Task 4)", () => {
  it("(a) 4 stations -> 4 chips, no [+N]", async () => {
    const descriptors: Descriptor[] = [
      { id: "need", type: "StakeholderNeed" },
      { id: "req", type: "Requirement" },
      { id: "goal", type: "Goal" },
      { id: "adr", type: "Adr" },
    ];
    const current = feedChain(descriptors, 0);
    renderFooter(current, descriptors);

    await waitFor(() => expect(chipButtons()).toHaveLength(4));
    expect(screen.queryByTestId("trace-footer-more")).not.toBeInTheDocument();
  });

  it("(b) 5 stations -> [+1 weitere]", async () => {
    const current = feedChain(FIVE_WITH_ACTIVE_AT_4, 3);
    renderFooter(current, FIVE_WITH_ACTIVE_AT_4);

    await waitFor(() => expect(chipButtons()).toHaveLength(4));
    const more = screen.getByTestId("trace-footer-more");
    expect(more).toHaveTextContent("+1 weitere");
    // A-01/A-06: count in accessible name, disclosure state exposed (SC 4.1.2).
    expect(more).toHaveAttribute("aria-expanded", "false");
    expect(more).toHaveAttribute("aria-controls", "trace-footer-station-list");
    // aria-controls target must exist (the <ol> carrying the station list).
    expect(document.getElementById("trace-footer-station-list")).not.toBeNull();
  });

  it("(c) 6 stations -> [+2 weitere]", async () => {
    const current = feedChain(SIX_WITH_ACTIVE_AT_6, 5);
    renderFooter(current, SIX_WITH_ACTIVE_AT_6);

    await waitFor(() => expect(chipButtons()).toHaveLength(4));
    expect(screen.getByTestId("trace-footer-more")).toHaveTextContent("+2 weitere");
  });

  it("(d) active station at position 4 AND 6 visible with aria-current", async () => {
    // Position 4 (index 3) in a 5-station chain.
    const current4 = feedChain(FIVE_WITH_ACTIVE_AT_4, 3);
    const { unmount } = renderFooter(current4, FIVE_WITH_ACTIVE_AT_4);
    await waitFor(() => expect(chipButtons()).toHaveLength(4));
    const active4 = chipByKey(current4.type);
    expect(active4).toBeInTheDocument();
    expect(active4).toHaveAttribute("aria-current", "step");
    expect(active4).toHaveAttribute("data-active", "true");
    unmount();

    vi.clearAllMocks();
    // Position 6 (index 5) in a 6-station chain.
    const current6 = feedChain(SIX_WITH_ACTIVE_AT_6, 5);
    renderFooter(current6, SIX_WITH_ACTIVE_AT_6);
    await waitFor(() => expect(chipButtons()).toHaveLength(4));
    const active6 = chipByKey(current6.type);
    expect(active6).toBeInTheDocument();
    expect(active6).toHaveAttribute("aria-current", "step");
    expect(active6).toHaveAttribute("data-active", "true");
  });

  it("(e) isOpenable=false in all 3 cases -> chip disabled, no popover", async () => {
    const allUnresolved = (ids: string[]) =>
      Promise.resolve(ids.map((id) => ({ artifact_id: id, resolved: false })));

    // Case 1: resolved:false
    let current = feedChain(FIVE_WITH_ACTIVE_AT_4, 3, allUnresolved);
    let view = renderFooter(current, FIVE_WITH_ACTIVE_AT_4);
    await waitFor(() => expect(chipButtons().length).toBeGreaterThan(0));
    expect(chipButtons().every((c) => c.disabled)).toBe(true);
    fireEvent.click(chipButtons()[0]!);
    expect(screen.queryByTestId("trace-station-popover")).not.toBeInTheDocument();
    view.unmount();

    // Case 2: resolve in flight (never settles)
    vi.clearAllMocks();
    current = feedChain(FIVE_WITH_ACTIVE_AT_4, 3, () => new Promise(() => {}));
    view = renderFooter(current, FIVE_WITH_ACTIVE_AT_4);
    await waitFor(() => expect(chipButtons().length).toBeGreaterThan(0));
    expect(chipButtons().every((c) => c.disabled)).toBe(true);
    fireEvent.click(chipButtons()[0]!);
    expect(screen.queryByTestId("trace-station-popover")).not.toBeInTheDocument();
    view.unmount();

    // Case 3: resolve failed (rejects)
    vi.clearAllMocks();
    current = feedChain(FIVE_WITH_ACTIVE_AT_4, 3, () =>
      Promise.reject(new Error("resolve down")),
    );
    renderFooter(current, FIVE_WITH_ACTIVE_AT_4);
    await waitFor(() => expect(chipButtons().length).toBeGreaterThan(0));
    await waitFor(() =>
      expect(chipButtons().every((c) => c.disabled)).toBe(true),
    );
    fireEvent.click(chipButtons()[0]!);
    expect(screen.queryByTestId("trace-station-popover")).not.toBeInTheDocument();
  });

  it("(f) popover ESC closes and returns focus to the triggering chip", async () => {
    const current = feedChain(FIVE_WITH_ACTIVE_AT_4, 3);
    renderFooter(current, FIVE_WITH_ACTIVE_AT_4);
    await waitFor(() => expect(chipButtons().length).toBeGreaterThan(0));

    const trigger = chipButtons().find((c) => !c.disabled)!;
    expect(trigger).toBeDefined();
    fireEvent.click(trigger);

    const popover = screen.getByTestId("trace-station-popover");
    expect(popover).toBeInTheDocument();
    expect(popover).toHaveAttribute("role", "dialog");

    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByTestId("trace-station-popover")).not.toBeInTheDocument();
    expect(document.activeElement).toBe(trigger);
  });

  it("(g) 1-station chain -> one-line placeholder, no crash", async () => {
    const descriptors: Descriptor[] = [{ id: "solo", type: "Current" }];
    const current = feedChain(descriptors, 0);
    renderFooter(current, descriptors);

    await waitFor(() =>
      expect(screen.getByTestId("trace-footer-placeholder")).toBeInTheDocument(),
    );
    expect(screen.queryByTestId("trace-footer-more")).not.toBeInTheDocument();
  });

  it("(h) no selection -> component not mounted, 0 px reserved", () => {
    const { container } = render(<TraceSpineFooter artifact={null} />);
    expect(screen.queryByTestId("trace-footer")).not.toBeInTheDocument();
    expect(container.firstChild).toBeNull();
    expect(tracelinksApi.impact).not.toHaveBeenCalled();
    expect(traceabilityApi.resolve).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// Task 11 (Schnitt 4b) — mobile bottom-sheet + single-expanded-sheet owner.
// jsdom has no layout engine, so the >=44px box is pinned by the stylesheet
// ratchet (interactive-hit-targets.test.ts) and the real boundingBox check in
// e2e/tests/mobile-sheets.spec.ts. These tests pin the behaviour/ARIA/focus.
// ---------------------------------------------------------------------------
describe('TraceSpineFooter — mobile bottom sheet (plan §3.5)', () => {
  function setMobileViewport(): void {
    Object.defineProperty(window, 'innerWidth', {
      configurable: true,
      writable: true,
      value: 390,
    });
  }

  function renderSingleStation(): void {
    const descriptors: Descriptor[] = [{ id: 'solo', type: 'Current' }];
    const current = feedChain(descriptors, 0);
    renderFooter(current, descriptors);
  }

  it('renders a non-modal collapsed bar; expanding moves focus into the sheet', async () => {
    setMobileViewport();
    renderSingleStation();
    await waitFor(() => expect(screen.getByTestId('trace-footer-placeholder')).toBeInTheDocument());

    const expand = screen.getByTestId('trace-footer-expand');
    expect(expand).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByTestId('trace-footer-collapse')).not.toBeInTheDocument();
    // Still region, never a dialog — the non-modal Inspector decision (#1762).
    expect(screen.getByTestId('trace-footer')).toHaveAttribute('role', 'region');
    expect(screen.getByTestId('trace-footer')).not.toHaveAttribute('aria-modal');

    fireEvent.click(expand);
    expect(expand).toHaveAttribute('aria-expanded', 'true');
    const close = screen.getByTestId('trace-footer-collapse');
    expect(close).toBeInTheDocument();
    expect(document.activeElement).toBe(close);
    expect(getExpandedMobileSheet()).toBe('trace-footer');

    fireEvent.click(close);
    expect(expand).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByTestId('trace-footer-collapse')).not.toBeInTheDocument();
    expect(document.activeElement).toBe(expand);
    expect(getExpandedMobileSheet()).toBeNull();
  });

  it('collapses when the inspector takes the single expanded-sheet slot', async () => {
    setMobileViewport();
    renderSingleStation();
    await waitFor(() => expect(screen.getByTestId('trace-footer-placeholder')).toBeInTheDocument());

    fireEvent.click(screen.getByTestId('trace-footer-expand'));
    expect(getExpandedMobileSheet()).toBe('trace-footer');

    act(() => {
      requestMobileSheet('inspector');
    });
    expect(screen.getByTestId('trace-footer-expand')).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByTestId('trace-footer-collapse')).not.toBeInTheDocument();

    // Releasing the inspector while the footer is collapsed stays a no-op.
    act(() => {
      releaseMobileSheet('inspector');
    });
    expect(getExpandedMobileSheet()).toBeNull();
  });

  it('does not claim the sheet slot on desktop (side-by-side layout)', async () => {
    Object.defineProperty(window, 'innerWidth', {
      configurable: true,
      writable: true,
      value: 1440,
    });
    renderSingleStation();
    await waitFor(() => expect(screen.getByTestId('trace-footer-placeholder')).toBeInTheDocument());

    // The bar exists in the DOM but is CSS-hidden on desktop; clicking it must
    // not claim the mobile slot (the coordinator is mobile-only).
    fireEvent.click(screen.getByTestId('trace-footer-expand'));
    expect(getExpandedMobileSheet()).toBeNull();
  });
});
