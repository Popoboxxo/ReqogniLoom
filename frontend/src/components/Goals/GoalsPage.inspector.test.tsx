/**
 * GoalsPage — tabbed inspector mount (#1762/M4).
 *
 * The Goals route carries two artifact kinds in one detail pane: `goal` (has a
 * spine, a Links tab and comments) and `mainGoal` (no trace graph at all —
 * spec §3). This suite pins the M4 contract:
 *
 *  - the tab matrix per kind (4 vs 3 tabs, never a disabled Links tab),
 *  - the comments request going to the backing Artifact UUID (#1763),
 *  - **one** tab-persistence slot for both kinds (I-14), and
 *  - `?inspector=` as a reproducible deep link (spec §5.4).
 *
 * The real `InspectorShell` is mounted here on purpose — the tab matrix is the
 * subject, so stubbing it would remove the thing under test.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import GoalsPage from "./GoalsPage";
import * as goalsModule from "../../api/goals";
import * as mainGoalModule from "../../api/main-goal";
import * as workflowTransitionsModule from "../../api/workflow-transitions";
import * as workflowsModule from "../../api/workflows";
import * as tracelinksModule from "../../api/tracelinks";
import * as traceabilityModule from "../../api/traceability";
import * as commentsModule from "../../api/comments";
import type { Goal, MainGoal } from "../../types";

vi.mock("../../api/goals");
vi.mock("../../api/main-goal");
vi.mock("../../api/workflow-transitions");
vi.mock("../../api/workflows");
vi.mock("../../api/tracelinks");
vi.mock("../../api/traceability");
vi.mock("../../api/comments");

vi.mock("../../context/WorkspaceContext", () => ({
  useWorkspace: () => ({
    activeWorkspace: { id: "w1", name: "WS", goals_ai_enabled: false },
    workspaces: [],
    isLoadingWorkspace: false,
  }),
  useOptionalWorkspace: () => ({
    activeWorkspace: { id: "w1", name: "WS", goals_ai_enabled: false },
    workspaces: [],
    isLoadingWorkspace: false,
  }),
}));

// TracePanel (Links tab) reads the workspace link-type catalog. A provider-free
// stub keeps the panel renderable without mounting LinkTypeProvider.
vi.mock("../../context/LinkTypeContext", () => ({
  useLinkTypes: () => ({
    linkTypes: [],
    isLoading: false,
    error: null,
    reload: vi.fn(),
    creatableLinkTypes: [],
    definitionFor: () => undefined,
    isAllowedPair: () => false,
    labelFor: (key: string) => key,
  }),
}));

const GOAL: Goal = {
  id: "g1",
  workspace_id: "w1",
  artifact_id: "art-g1",
  lineage_id: "l1",
  sequence_number: 1,
  title: "Existing Goal",
  description: "",
  status: "Entwurf",
  version: 1,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

const MAIN_GOAL: MainGoal = {
  id: "mg1",
  workspace_id: "w1",
  artifact_id: "art-mg1",
  sequence_number: 1,
  content: "Current main goal.",
  source: "manual",
  status: "Freigegeben",
  version: 1,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

function renderGoals(entry = "/goals"): ReturnType<typeof render> {
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <GoalsPage />
    </MemoryRouter>,
  );
}

async function selectNode(id: string): Promise<void> {
  fireEvent.click(await screen.findByTestId(`goals-tree-node-${id}`));
}

/** Assert the exact tab inventory and that none of them is disabled. */
function expectTabs(expected: readonly string[]): void {
  for (const key of ["version", "diff", "links", "comments"] as const) {
    const tab = screen.queryByTestId(`inspector-tab-${key}`);
    if (expected.includes(key)) {
      expect(tab, `${key} tab should exist`).toBeInTheDocument();
      expect(tab).not.toHaveAttribute("disabled");
    } else {
      expect(tab, `${key} tab should not exist`).toBeNull();
    }
  }
}

describe("GoalsPage — inspector shell (#1762 M4)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
    window.history.replaceState({}, "", "/goals");
    // R1 (>= 1600 px) opens the panel by default; jsdom is 1024 px wide.
    Object.defineProperty(window, "innerWidth", {
      configurable: true,
      writable: true,
      value: 1920,
    });

    vi.mocked(goalsModule.goalsApi.list).mockResolvedValue([GOAL]);
    vi.mocked(goalsModule.goalsApi.getTransitions).mockResolvedValue({
      current_state: "Entwurf",
      states: ["Entwurf", "Freigegeben", "Archiviert"],
      allowed_transitions: [],
      proposed_by: null,
    });
    vi.mocked(goalsModule.goalsApi.versions).mockResolvedValue([]);
    vi.mocked(mainGoalModule.mainGoalApi.current).mockResolvedValue(MAIN_GOAL);
    vi.mocked(mainGoalModule.mainGoalApi.versions).mockResolvedValue([]);
    vi.mocked(workflowTransitionsModule.workflowTransitionsApi.getTransitions)
      .mockResolvedValue({
        current_state: "Freigegeben",
        states: ["Entwurf", "Freigegeben", "Archiviert"],
        allowed_transitions: [],
        proposed_by: null,
      });
    vi.mocked(workflowsModule.workflowsApi.getGraph).mockResolvedValue({
      item_type: "Goal",
      states: [{ name: "Entwurf" }, { name: "Freigegeben" }, { name: "Archiviert" }],
    } as never);
    vi.mocked(tracelinksModule.tracelinksApi.impact).mockResolvedValue([]);
    vi.mocked(tracelinksModule.tracelinksApi.listForArtifact).mockResolvedValue({
      count: 0,
      next: null,
      previous: null,
      results: [],
    } as never);
    vi.mocked(traceabilityModule.traceabilityApi.resolve).mockResolvedValue([]);
    vi.mocked(commentsModule.commentsApi.list).mockResolvedValue([]);
  });

  it("renders four tabs for a Goal and requests comments on the Artifact UUID (M4-2)", async () => {
    renderGoals();
    await selectNode("g1");

    await waitFor(() => expect(screen.getByTestId("inspector-shell")).toBeInTheDocument());
    expect(screen.getByTestId("inspector-shell")).toHaveAttribute(
      "data-artifact-kind",
      "goal",
    );
    expectTabs(["version", "diff", "links", "comments"]);

    fireEvent.click(screen.getByTestId("inspector-tab-comments"));
    await waitFor(() =>
      expect(commentsModule.commentsApi.list).toHaveBeenCalledWith("art-g1"),
    );
    expect(commentsModule.commentsApi.list).not.toHaveBeenCalledWith("g1");
  });

  it("renders three tabs for a MainGoal — no Links tab, none disabled (M4-3)", async () => {
    renderGoals();

    await waitFor(() => expect(screen.getByTestId("inspector-shell")).toBeInTheDocument());
    expect(screen.getByTestId("inspector-shell")).toHaveAttribute(
      "data-artifact-kind",
      "mainGoal",
    );
    expectTabs(["version", "diff", "comments"]);
    expect(screen.queryByTestId("inspector-tab-links")).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId("inspector-tab-comments"));
    await waitFor(() =>
      expect(commentsModule.commentsApi.list).toHaveBeenCalledWith("art-mg1"),
    );
  });

  it("omits the comments tab for a MainGoal that publishes no Artifact UUID (M4-4)", async () => {
    // B2.0-4 projects `MainGoal.artifact_id`, but a hand-built/legacy payload
    // may omit it. The shell then renders no comments tab at all — not an
    // empty one, not a disabled one (spec §4.3).
    vi.mocked(mainGoalModule.mainGoalApi.current).mockResolvedValue({
      ...MAIN_GOAL,
      artifact_id: undefined,
    });

    renderGoals();

    await waitFor(() => expect(screen.getByTestId("inspector-shell")).toBeInTheDocument());
    expectTabs(["version", "diff"]);
    expect(commentsModule.commentsApi.list).not.toHaveBeenCalled();
  });

  it("keeps the selected tab across a Goal → MainGoal → Goal switch, on one storage key (M4-1)", async () => {
    renderGoals();
    await selectNode("g1");

    await waitFor(() =>
      expect(screen.getByTestId("inspector-tab-links")).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByTestId("inspector-tab-links"));
    expect(screen.getByTestId("inspector-tab-links")).toHaveAttribute(
      "aria-selected",
      "true",
    );

    // Switch to the main goal: no Links tab exists there.
    await selectNode("__main-goal__");
    await waitFor(() =>
      expect(screen.queryByTestId("inspector-tab-links")).not.toBeInTheDocument(),
    );

    // …and back: the shared slot remembers the Goal tab (I-14).
    await selectNode("g1");
    await waitFor(() =>
      expect(screen.getByTestId("inspector-shell")).toHaveAttribute(
        "data-artifact-kind",
        "goal",
      ),
    );
    await waitFor(() =>
      expect(screen.getByTestId("inspector-tab-links")).toHaveAttribute(
        "aria-selected",
        "true",
      ),
    );

    // Exactly one slot for both kinds — no per-kind duplicate (I-14).
    const tabKeys = Object.keys(sessionStorage).filter((key) =>
      key.startsWith("reqflow_inspector_tab_"),
    );
    expect(tabKeys).toEqual(["reqflow_inspector_tab_goals"]);
  });

  it("opens the tab named by ?inspector= (M4, spec §5.4)", async () => {
    window.history.replaceState({}, "", "/goals?inspector=comments");
    renderGoals();

    await waitFor(() =>
      expect(screen.getByTestId("inspector-tab-comments")).toHaveAttribute(
        "aria-selected",
        "true",
      ),
    );
    await waitFor(() =>
      expect(commentsModule.commentsApi.list).toHaveBeenCalledWith("art-mg1"),
    );
  });

  it("puts the Goal chain in the spine slot and keeps it out of the detail (DoD 5/6)", async () => {
    renderGoals();
    await selectNode("g1");

    await waitFor(() => expect(screen.getByTestId("splitview-spine")).toBeInTheDocument());
    expect(screen.getByTestId("splitview-spine")).toContainElement(
      screen.getByTestId("trace-spine"),
    );
    // One trace read surface: the spine is not inside the scrolling detail.
    expect(screen.getByTestId("splitview-detail")).not.toContainElement(
      screen.getByTestId("trace-spine"),
    );
    expect(screen.queryByTestId("splitview-divider")).not.toBeInTheDocument();

    // MainGoal has no trace graph at all (spec §3).
    await selectNode("__main-goal__");
    await waitFor(() =>
      expect(screen.queryByTestId("splitview-spine")).not.toBeInTheDocument(),
    );
  });

  it("shows identity and workflow status in each kind's artifact head (DoD 2)", async () => {
    renderGoals();

    const mainHead = await screen.findByTestId("main-goal-artifact-head");
    expect(within(mainHead).getByTestId("main-goal-status")).toHaveTextContent(
      "Freigegeben",
    );
    expect(within(mainHead).getByTestId("main-goal-detail-id")).toBeInTheDocument();

    await selectNode("g1");
    const goalHead = await screen.findByTestId("goal-artifact-head");
    expect(within(goalHead).getByTestId("goal-status")).toHaveTextContent("Entwurf");
    expect(within(goalHead).getByTestId("goal-artifact-id")).toBeInTheDocument();
  });
});
