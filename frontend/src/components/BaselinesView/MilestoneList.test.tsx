/**
 * Plan B B6-T2 (#879) — MilestoneList.
 *
 * Pins the UI contract of the milestone planning list mounted under the
 * Baselines route:
 *   - list / empty / error states are explicit,
 *   - create posts the workspace-scoped payload,
 *   - update forwards the rendered row version as the ETag precondition,
 *   - bind-baseline and record-audit call their domain actions,
 *   - every interactive element carries its `data-testid` (E2E contract).
 *
 * i18n is stubbed the same way as the neighbouring Baselines tests: the key is
 * returned verbatim, so assertions never depend on the active locale.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

vi.mock("../../api/milestones");
vi.mock("../../api/baselines");
vi.mock("react-i18next", () => {
  const t = (
    key: string,
    fallbackOrOptions?: string | Record<string, unknown>
  ): string =>
    typeof fallbackOrOptions === "string" ? fallbackOrOptions : key;
  return { useTranslation: () => ({ t }) };
});

import * as milestonesModule from "../../api/milestones";
import * as baselinesModule from "../../api/baselines";
import type { Milestone } from "../../api/milestones";
import { MilestoneList } from "./MilestoneList";

const WORKSPACE_ID = "ws-milestone-1";

function makeMilestone(overrides: Partial<Milestone> = {}): Milestone {
  return {
    id: "ms-1",
    workspace_id: WORKSPACE_ID,
    name: "PDR Fahrwerk",
    review_type: "PDR",
    target_date: "2026-12-01",
    status: "planned",
    baseline_id: null,
    audit_snapshot: null,
    version: 3,
    created_at: "2026-10-01T09:00:00Z",
    updated_at: "2026-10-02T09:00:00Z",
    ...overrides,
  };
}

function renderList(
  props: Partial<Parameters<typeof MilestoneList>[0]> = {}
): ReturnType<typeof render> {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MilestoneList workspaceId={WORKSPACE_ID} canEdit {...props} />
    </QueryClientProvider>
  );
}

describe("MilestoneList (Plan B B6-T2)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(milestonesModule.milestonesApi.list).mockResolvedValue({
      count: 1,
      next: null,
      previous: null,
      results: [makeMilestone()],
    });
    vi.mocked(baselinesModule.baselinesApi.list).mockResolvedValue({
      count: 0,
      next: null,
      previous: null,
      results: [],
    });
  });

  it("renders the milestone rows returned by the API", async () => {
    renderList();

    expect(await screen.findByTestId("milestone-row-ms-1")).toBeInTheDocument();
    expect(screen.getByTestId("milestone-list")).toBeInTheDocument();
    expect(screen.getByTestId("milestone-create-button")).toBeInTheDocument();
    expect(screen.getByText("PDR Fahrwerk")).toBeInTheDocument();
  });

  it("renders the empty state when the workspace has no milestones", async () => {
    vi.mocked(milestonesModule.milestonesApi.list).mockResolvedValue({
      count: 0,
      next: null,
      previous: null,
      results: [],
    });

    renderList();

    expect(await screen.findByTestId("milestone-empty")).toBeInTheDocument();
    expect(screen.queryByTestId("milestone-row-ms-1")).not.toBeInTheDocument();
  });

  it("renders an error alert and retries the list", async () => {
    const user = userEvent.setup();
    vi.mocked(milestonesModule.milestonesApi.list).mockRejectedValueOnce({
      error: { message: "milestone service unavailable" },
    });

    renderList();

    const alert = await screen.findByTestId("milestone-error");
    expect(alert).toHaveAttribute("role", "alert");
    expect(alert).toHaveTextContent("milestone service unavailable");

    await user.click(screen.getByTestId("milestone-retry"));

    expect(await screen.findByTestId("milestone-row-ms-1")).toBeInTheDocument();
  });

  it("creates a milestone through the create form", async () => {
    const user = userEvent.setup();
    vi.mocked(milestonesModule.milestonesApi.create).mockResolvedValue(
      makeMilestone({ id: "ms-new", name: "CDR Fahrwerk" })
    );

    renderList();
    await user.click(screen.getByTestId("milestone-create-button"));

    await user.type(
      screen.getByTestId("milestone-name-input"),
      "CDR Fahrwerk"
    );
    fireEvent.change(screen.getByTestId("milestone-target-date-input"), {
      target: { value: "2027-01-15" },
    });
    await user.click(screen.getByTestId("milestone-create-submit"));

    await waitFor(() => {
      expect(milestonesModule.milestonesApi.create).toHaveBeenCalledWith(
        expect.objectContaining({
          workspace_id: WORKSPACE_ID,
          name: "CDR Fahrwerk",
          review_type: "PDR",
          target_date: "2027-01-15",
          status: "planned",
        })
      );
    });
  });

  it("updates a milestone with its rendered version as the ETag guard", async () => {
    const user = userEvent.setup();
    vi.mocked(milestonesModule.milestonesApi.update).mockResolvedValue(
      makeMilestone({ name: "PDR Fahrwerk neu", version: 4 })
    );

    renderList();
    await user.click(await screen.findByTestId("milestone-row-select-ms-1"));
    await user.click(screen.getByTestId("milestone-edit-button"));

    const nameInput = screen.getByTestId("milestone-edit-name");
    await user.clear(nameInput);
    await user.type(nameInput, "PDR Fahrwerk neu");
    await user.click(screen.getByTestId("milestone-update-submit"));

    await waitFor(() => {
      expect(milestonesModule.milestonesApi.update).toHaveBeenCalledWith(
        "ms-1",
        expect.objectContaining({ name: "PDR Fahrwerk neu" }),
        3
      );
    });
  });

  it("binds a baseline through the domain action", async () => {
    const user = userEvent.setup();
    vi.mocked(baselinesModule.baselinesApi.list).mockResolvedValue({
      count: 1,
      next: null,
      previous: null,
      results: [
        {
          id: "bl-1",
          workspace_id: WORKSPACE_ID,
          name: "Release 1.0",
          scope: "project",
          description: "",
          artifact_id: null,
          version: 1,
          created_at: "2026-10-01T09:00:00Z",
          tags: [],
        },
      ],
    });
    vi.mocked(
      milestonesModule.milestonesApi.bindBaseline
    ).mockResolvedValue(makeMilestone({ baseline_id: "bl-1", version: 4 }));

    renderList();
    await user.click(await screen.findByTestId("milestone-row-select-ms-1"));

    const select = screen.getByTestId("milestone-baseline-select");
    await waitFor(() => {
      expect(select).toHaveTextContent("Release 1.0");
    });
    await user.selectOptions(select, "bl-1");
    await user.click(screen.getByTestId("milestone-bind-baseline"));

    await waitFor(() => {
      expect(
        milestonesModule.milestonesApi.bindBaseline
      ).toHaveBeenCalledWith("ms-1", "bl-1", 3);
    });
  });

  it("records an audit snapshot through the domain action", async () => {
    const user = userEvent.setup();
    vi.mocked(milestonesModule.milestonesApi.recordAudit).mockResolvedValue(
      makeMilestone({
        version: 4,
        audit_snapshot: {
          tier: "standard",
          counts: { total: 3, blockers: 1, warnings: 2 },
          run_at: "2026-10-03T09:00:00Z",
        },
      })
    );

    renderList();
    await user.click(await screen.findByTestId("milestone-row-select-ms-1"));
    await user.click(screen.getByTestId("milestone-record-audit"));

    await waitFor(() => {
      expect(
        milestonesModule.milestonesApi.recordAudit
      ).toHaveBeenCalledWith("ms-1", 3);
    });
  });
});
