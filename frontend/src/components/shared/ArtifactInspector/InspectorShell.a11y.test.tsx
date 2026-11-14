/**
 * InspectorShell — accessibility baseline (spec §7, M1-3/M1-10, plan B2.0-5.1).
 *
 * The pattern is inherited from `RightSidebar.a11y.test.tsx`: **every**
 * rendered button must have a non-empty accessible name, in both forms of the
 * shell (panel and rail) and for the kinds with the most divergent tab sets.
 * A button without a name is unusable with a screen reader, and the rail is
 * where that defect used to live (`RightSidebar.tsx:344,353`, I-20).
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { InspectorShell, type InspectorShellProps } from "./InspectorShell";
import * as requirementsModule from "../../../api/requirements";
import * as commentsModule from "../../../api/comments";
import * as tracelinksModule from "../../../api/tracelinks";

vi.mock("../../../api/requirements");
vi.mock("../../../api/comments");
vi.mock("../../../api/tracelinks");
vi.mock("../../../context/WorkspaceContext", () => ({
  useWorkspace: () => ({ activeWorkspace: { id: "ws-1" } }),
}));
vi.mock("../../../context/LinkTypeContext", () => ({
  useLinkTypes: () => ({ linkTypes: [], labelFor: (key: string) => key }),
}));
vi.mock("react-router-dom", () => ({ useNavigate: () => vi.fn() }));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, second?: unknown): string => {
      if (typeof second === "string") return second;
      if (second && typeof second === "object" && "defaultValue" in second) {
        const options = second as Record<string, unknown>;
        let text = String(options.defaultValue);
        for (const [name, value] of Object.entries(options)) {
          if (name === "defaultValue") continue;
          text = text.replaceAll(`{{${name}}}`, String(value));
        }
        return text;
      }
      // Fall back to the key, which is still a name (better than "").
      return key;
    },
  }),
}));

const CURRENT_VERSION = { version: 1, label: "v1", createdAt: null, baselineIds: [] };

function setViewport(width: number): void {
  Object.defineProperty(window, "innerWidth", {
    configurable: true,
    writable: true,
    value: width,
  });
}

function renderShell(props: Partial<InspectorShellProps>): void {
  render(
    <InspectorShell
      kind="requirement"
      entityId="req-1"
      artifactPk="artifact-1"
      currentVersion={CURRENT_VERSION}
      {...props}
    />,
  );
}

/** The shared assertion: no unnamed button anywhere in the surface. */
function expectEveryButtonNamed(): void {
  const buttons = screen.getByTestId("inspector-shell").querySelectorAll("button");
  expect(buttons.length).toBeGreaterThan(0);
  for (const button of buttons) {
    expect(button).toHaveAccessibleName();
  }
}

describe("InspectorShell a11y (M1-3 / M1-10)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
    localStorage.clear();
    window.history.replaceState({}, "", "/requirements/req-1");
    vi.mocked(requirementsModule.requirementsApi.versions).mockResolvedValue([]);
    vi.mocked(commentsModule.commentsApi.list).mockResolvedValue([]);
    vi.mocked(tracelinksModule.tracelinksApi.listForArtifact).mockResolvedValue({
      count: 0,
      next: null,
      previous: null,
      results: [],
    });
  });

  it("panel form: every button is named (requirement, four tabs)", async () => {
    setViewport(1440);
    renderShell({ kind: "requirement" });

    await waitFor(() => {
      expect(screen.getByTestId("inspector-tab-version")).toBeInTheDocument();
    });
    expectEveryButtonNamed();
  });

  it("panel form: every button is named (mainGoal, three tabs, no links)", async () => {
    setViewport(1440);
    renderShell({ kind: "mainGoal", entityId: "mg-1" });

    await waitFor(() => {
      expect(screen.getByTestId("inspector-tab-comments")).toBeInTheDocument();
    });
    expect(screen.queryByTestId("inspector-tab-links")).not.toBeInTheDocument();
    expectEveryButtonNamed();
  });

  it("panel form: every button is named (glossary, no comments tab)", async () => {
    setViewport(1440);
    renderShell({ kind: "glossary", entityId: "term-1", artifactPk: null });

    await waitFor(() => {
      expect(screen.getByTestId("inspector-tab-links")).toBeInTheDocument();
    });
    expect(screen.queryByTestId("inspector-tab-comments")).not.toBeInTheDocument();
    expectEveryButtonNamed();
  });

  // #1762 / M2: the five kinds migrated in that step all have a spine, so all
  // of them render the full four-tab set (Links is only omitted for
  // `mainGoal`) — and the "every button has a name" baseline must hold for
  // each of them, not just for Requirement. M3 (`architecture`) and M4
  // (`goal`) join the same matrix; `mainGoal` has its own case above because
  // its three-tab set is the interesting one.
  it.each([
    "stakeholderNeed",
    "risk",
    "adr",
    "issue",
    "testCase",
    "architecture",
    "goal",
  ] as const)(
    "panel form: every button is named (%s, four tabs)",
    async (kind) => {
      setViewport(1440);
      renderShell({ kind, entityId: "entity-1" });

      await waitFor(() => {
        expect(screen.getByTestId("inspector-tab-comments")).toBeInTheDocument();
      });
      for (const key of ["version", "diff", "links", "comments"] as const) {
        expect(screen.getByTestId(`inspector-tab-${key}`)).toBeInTheDocument();
      }
      expectEveryButtonNamed();
    },
  );

  it("rail form: every counter is named and the letter glyph is hidden", async () => {    setViewport(1440);
    renderShell({ kind: "requirement" });

    fireEvent.click(await screen.findByTestId("inspector-close"));
    await screen.findByTestId("inspector-rail");

    expectEveryButtonNamed();

    for (const key of ["version", "diff", "links", "comments"] as const) {
      const counter = screen.getByTestId(`inspector-rail-count-${key}`);
      const name = counter.getAttribute("aria-label") ?? "";
      // The visible glyph is `aria-hidden`; it must not leak into the name
      // as a leading "V"/"D"/"L"/"K" token (WCAG 4.1.2, I-20).
      expect(name).not.toMatch(/^[VDLK][\s,·]/);
      expect(counter.querySelector('[aria-hidden="true"]')).not.toBeNull();
    }
  });

  it("resolves every aria-controls / aria-labelledby reference", async () => {
    setViewport(1440);
    renderShell({ kind: "requirement" });

    await waitFor(() => {
      expect(screen.getByTestId("inspector-tab-version")).toBeInTheDocument();
    });

    const surface = screen.getByTestId("inspector-shell");
    for (const element of surface.querySelectorAll(
      "[aria-controls], [aria-labelledby]",
    )) {
      for (const attribute of ["aria-controls", "aria-labelledby"]) {
        const value = element.getAttribute(attribute);
        if (value === null) continue;
        for (const id of value.split(/\s+/)) {
          expect(
            document.getElementById(id),
            `${attribute}="${id}" does not resolve`,
          ).not.toBeNull();
        }
      }
    }
  });
});
