/**
 * TraceSpine — one station per architecture tree level (#1762/M3).
 *
 * Spec/UI concept ch. 5.1: architecture contributes one station **per real
 * tree depth**, never a fixed L0–L4 ladder. The station order stays the chain
 * order (L0 → L4) regardless of the order the neighbourhood query returns the
 * nodes in, and each station carries the shared `<LevelBadge>` — no second
 * badge implementation, no local geometry.
 *
 * The horizontal form (below `--bp-lg`) is a CSS-only invariant: jsdom does
 * not load CSS modules (`vite.config` runs with `css: false`), so the last
 * test asserts it against the module source instead of a computed style.
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { render, renderHook, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { TraceSpine } from "./TraceSpine";
import { useDerivationChain, type ChainStation } from "./useDerivationChain";
import { tracelinksApi } from "../../../api/tracelinks";
import { traceabilityApi } from "../../../api/traceability";
import type { ArchitectureElement } from "../../../types";

vi.mock("../../../api/tracelinks", () => ({
  tracelinksApi: { impact: vi.fn() },
}));
vi.mock("../../../api/traceability", () => ({
  traceabilityApi: { resolve: vi.fn() },
}));
vi.mock("../../../api/client", async (importActual) => ({
  ...(await importActual<typeof import("../../../api/client")>()),
  extractErrorMessage: (): string => "error",
}));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, second?: unknown) =>
      typeof second === "string" ? second : key,
  }),
}));

const CURRENT_ARTIFACT_ID = "art-current";

/** Five real tree depths (L0–L4), each with its backing Artifact id. */
const ELEMENTS = [0, 1, 2, 3, 4].map(
  (level) =>
    ({
      id: `arch-${level}`,
      workspace_id: "ws-1",
      artifact_id: level === 2 ? CURRENT_ARTIFACT_ID : `art-${level}`,
      title: `Element L${level}`,
      description: "",
      element_type: "component",
      level,
      version: 1,
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    }) as ArchitectureElement,
);

/** Incoming nodes deliberately *not* in chain order. */
const INCOMING = [4, 0, 3, 1].map((level) => ({
  artifact_id: `art-${level}`,
  artifact_type: "ArchitectureElement",
  title: `Element L${level}`,
  uid: `ARCH-L${level}`,
  link_type: "derives-from",
  depth: 1,
  path: [CURRENT_ARTIFACT_ID, `art-${level}`],
}));

function station(
  key: string,
  level: number,
  isCurrent = false,
): ChainStation {
  return {
    key,
    artifactType: "ArchitectureElement",
    level,
    direction: isCurrent ? "current" : "origin",
    isCurrent,
    artifacts: isCurrent
      ? []
      : [
          {
            id: `art-${level}`,
            title: `Element L${level}`,
            uid: `ARCH-L${level}`,
            artifactType: "ArchitectureElement",
            linkType: "derives-from",
          },
        ],
    verifications: [],
  } as ChainStation;
}

describe("useDerivationChain — architecture stations per tree level (M3-2)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(tracelinksApi.impact).mockImplementation(async (_id, options) =>
      options?.direction === "incoming" ? (INCOMING as never) : ([] as never),
    );
    vi.mocked(traceabilityApi.resolve).mockResolvedValue([]);
  });

  it("yields exactly one station per level, ordered L0 → L4", async () => {
    const { result } = renderHook(() =>
      useDerivationChain(CURRENT_ARTIFACT_ID, "ArchitectureElement", 2, {
        architectureElements: ELEMENTS,
      }),
    );

    await waitFor(() => expect(result.current.stations).toHaveLength(5));
    expect(result.current.stations.map((s) => s.level)).toEqual([0, 1, 2, 3, 4]);
    expect(result.current.stations.map((s) => s.key)).toEqual(
      [0, 1, 2, 3, 4].map((level) => `ArchitectureElement:${level}`),
    );
    // Exactly one "you are here" station — the opened element's own level.
    expect(result.current.stations.filter((s) => s.isCurrent)).toHaveLength(1);
    expect(result.current.stations[2]?.isCurrent).toBe(true);
  });

  it("does not invent stations for levels the chain does not reach", async () => {
    vi.mocked(tracelinksApi.impact).mockResolvedValue([] as never);

    const { result } = renderHook(() =>
      useDerivationChain(CURRENT_ARTIFACT_ID, "ArchitectureElement", 2, {
        architectureElements: ELEMENTS,
      }),
    );

    await waitFor(() => expect(result.current.stations).toHaveLength(1));
    expect(result.current.stations[0]?.key).toBe("ArchitectureElement:2");
    expect(result.current.stations[0]?.isCurrent).toBe(true);
  });
});

describe("TraceSpine — level badge and verification on architecture stations (M3-2/M3-4)", () => {
  it("renders one station per level in chain order, each with the shared LevelBadge", () => {
    render(
      <TraceSpine
        stations={[0, 1, 2, 3, 4].map((level) =>
          station(`ArchitectureElement:${level}`, level, level === 2),
        )}
        testId="spine"
      />,
    );

    const stations = screen.getAllByTestId("spine-station");
    expect(stations).toHaveLength(5);

    stations.forEach((item, index) => {
      const badge = within(item).getByTestId("spine-level");
      expect(badge).toHaveTextContent(`L${index}`);
      // Geometry comes from `BADGE_BASE_STYLE` (utils/badgeBase.ts), not from
      // a local rule: the fixed 22px height is that module's own constant.
      expect(badge).toHaveStyle({ minHeight: "22px" });
    });
  });

  it("shows the verification badge only on architecture stations with verifications", () => {
    const covered = station("ArchitectureElement:1", 1);
    covered.verifications = [
      {
        id: "tc-1",
        title: "Test 1",
        uid: "TC-1",
        artifactType: "TestCase",
        linkType: "verifies",
      },
    ];
    const uncovered = station("ArchitectureElement:3", 3);

    render(<TraceSpine stations={[covered, uncovered]} testId="spine" />);

    const [withData, withoutData] = screen.getAllByTestId("spine-station");
    // U-07: the badge appears at **every** station with data — architecture
    // included — and the empty badge stays where it already was (the two
    // derivation levels); any other type shows nothing.
    expect(within(withData!).getByTestId("spine-verification")).toHaveTextContent("·1");
    expect(within(withoutData!).getByTestId("spine-verification")).toBeDisabled();
  });

  it("keeps the horizontal form scrollable sideways instead of wrapping", () => {
    // jsdom ignores media queries and CSS modules, so this pins the module
    // source: below --bp-lg the rail is one no-wrap row inside an
    // `overflow-x: auto` container (ch. 5 "Verhalten").
    const css = readFileSync(resolve(__dirname, "TraceSpine.module.css"), "utf-8");
    const narrowBlock = css.slice(css.indexOf("@media (max-width: 1024px)"));
    expect(narrowBlock).toContain("overflow-x: auto");
    expect(narrowBlock).toContain("flex-wrap: nowrap");
    expect(narrowBlock).toContain("flex: 0 0 auto");
  });
});
