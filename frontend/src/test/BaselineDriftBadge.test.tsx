/**
 * #399 — BaselineDriftBadge unit test.
 *
 * Covers the four states of the editor-header drift surface: success (badge +
 * CR shortcut), empty (no membership -> renders nothing), fail-open on a
 * membership error, and the summary-only path where the retrieve annotation
 * knows drift but the per-baseline list failed. Also pins the CR prefill
 * contract (`affected_item_ids == [artifactId]`, spec AC-D1-11).
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { BaselineDriftBadge } from "../components/shared/BaselineDriftBadge/BaselineDriftBadge";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock("../api/client", () => ({
  extractErrorMessage: (e: unknown) => (e instanceof Error ? e.message : "error"),
}));

const baselineMembership = vi.fn();
vi.mock("../api/artifacts", () => ({
  artifactsApi: {
    baselineMembership: (...args: unknown[]) => baselineMembership(...args),
  },
}));

const createChangeRequest = vi.fn();
vi.mock("../api/change-requests", () => ({
  changeRequestsApi: {
    create: (...args: unknown[]) => createChangeRequest(...args),
  },
}));

const DRIFTED_MEMBERSHIP = {
  baseline_id: "b-1",
  baseline_name: "Release 1.8",
  scope: "project",
  baselined_at: "2026-09-01T10:00:00Z",
  baselined_version: 3,
  current_version: 4,
  drifted: true,
  drift_known: true,
};

function renderBadge(props: Partial<Parameters<typeof BaselineDriftBadge>[0]> = {}) {
  return render(
    <BaselineDriftBadge
      artifactId="a-1"
      workspaceId="ws-1"
      artifactTitle="Login requirement"
      {...props}
    />
  );
}

describe("BaselineDriftBadge (#399)", () => {
  beforeEach(() => {
    baselineMembership.mockReset();
    createChangeRequest.mockReset();
  });

  it("renders the badge and CR shortcut for a drifted membership", async () => {
    baselineMembership.mockResolvedValue({
      artifact_id: "a-1",
      drifted: true,
      memberships: [DRIFTED_MEMBERSHIP],
    });

    renderBadge();

    expect(await screen.findByTestId("baseline-drift-badge")).toBeInTheDocument();
    expect(screen.getByTestId("raise-cr-from-drift")).toBeInTheDocument();
  });

  it("renders nothing when the artifact is in no baseline", async () => {
    baselineMembership.mockResolvedValue({
      artifact_id: "a-1",
      drifted: false,
      memberships: [],
    });

    renderBadge();

    await waitFor(() => expect(baselineMembership).toHaveBeenCalledWith("a-1"));
    expect(screen.queryByTestId("baseline-drift-badge")).toBeNull();
    expect(screen.queryByTestId("raise-cr-from-drift")).toBeNull();
  });

  it("fails open (renders nothing) when the membership lookup errors", async () => {
    baselineMembership.mockRejectedValue(new Error("boom"));

    renderBadge();

    await waitFor(() => expect(baselineMembership).toHaveBeenCalled());
    expect(screen.queryByTestId("baseline-drift-badge")).toBeNull();
  });

  it("still renders the badge from the retrieve summary when the list is unknown", async () => {
    baselineMembership.mockResolvedValue({ artifact_id: "a-1", drifted: false, memberships: [] });

    renderBadge({ summary: { drifted: true, count: 1 } });

    expect(await screen.findByTestId("baseline-drift-badge")).toBeInTheDocument();
  });

  it("creates a change request pre-filled with the artifact as affected item", async () => {
    baselineMembership.mockResolvedValue({
      artifact_id: "a-1",
      drifted: true,
      memberships: [DRIFTED_MEMBERSHIP],
    });
    createChangeRequest.mockResolvedValue({ id: "cr-1" });
    const onCreated = vi.fn();

    renderBadge({ onCreated });

    await userEvent.click(await screen.findByTestId("raise-cr-from-drift"));

    await waitFor(() =>
      expect(createChangeRequest).toHaveBeenCalledWith({
        workspace_id: "ws-1",
        title: "baseline.crTitle",
        affected_item_ids: ["a-1"],
      })
    );
    expect(await screen.findByTestId("baseline-drift-cr-status")).toBeInTheDocument();
    expect(onCreated).toHaveBeenCalledTimes(1);
  });

  it("surfaces a failed change-request creation", async () => {
    baselineMembership.mockResolvedValue({
      artifact_id: "a-1",
      drifted: true,
      memberships: [DRIFTED_MEMBERSHIP],
    });
    createChangeRequest.mockRejectedValue(new Error("denied"));

    renderBadge();

    await userEvent.click(await screen.findByTestId("raise-cr-from-drift"));

    const alert = await screen.findByTestId("baseline-drift-cr-error");
    expect(alert).toHaveTextContent("denied");
    expect(alert).toHaveAttribute("role", "alert");
  });
});
