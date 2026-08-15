/**
 * GH-513: the SE-Auditor gate must not be a dead end in the UI.
 *
 * req_id: REQ-L1-018 (Baselines)
 *
 * The backend blocks baseline creation while the workspace has BLOCKER
 * findings (GH-490) and most findings cannot be resolved from the Auditor UI
 * (GH-451). The documented exit is an `override_reason` from an Admin or
 * Approver — these tests pin that the view offers it exactly when the backend
 * says it is available, and never for the non-waivable case.
 *
 * The api module is only *partially* mocked: `baselinesApi` is replaced, the
 * real `isSeAuditorBlocked` is kept, so the test exercises the actual envelope
 * detection rather than a re-implementation of it.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

vi.mock("../../api/baselines", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("../../api/baselines")>();
  return {
    ...actual,
    baselinesApi: {
      list: vi.fn(),
      get: vi.fn(),
      create: vi.fn(),
      delete: vi.fn(),
      compare: vi.fn(),
      previewScope: vi.fn(),
    },
  };
});
vi.mock("../../api/artifacts");
vi.mock("../../context/WorkspaceContext");
vi.mock("react-i18next", () => {
  const t = (
    key: string,
    fallbackOrOptions?: string | Record<string, unknown>,
  ): string =>
    typeof fallbackOrOptions === "string" ? fallbackOrOptions : key;
  return { useTranslation: () => ({ t }) };
});

import * as baselinesModule from "../../api/baselines";
import * as artifactsModule from "../../api/artifacts";
import * as workspaceContext from "../../context/WorkspaceContext";

import BaselinesView from "./BaselinesView";

const MOCK_WORKSPACE = {
  id: "ws-bl-513",
  name: "QA Workspace",
  preset: "extended",
};

const BLOCKED_ENVELOPE = {
  error: {
    code: "SE_AUDITOR_BLOCKED",
    message:
      "Baseline cannot be created: the SE-Auditor reported 77 blocking finding(s) …",
    details: [],
  },
};

const renderView = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <BaselinesView />
    </QueryClientProvider>,
  );
};

/** Open the create form and press Save once. */
async function submitCreateForm(user: ReturnType<typeof userEvent.setup>) {
  await waitFor(() => {
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });
  await user.click(screen.getByTestId("page-header-overflow-trigger"));
  await user.click(screen.getByTestId("create-baseline-btn"));
  await waitFor(() => {
    expect(screen.getByTestId("create-baseline-form")).toBeInTheDocument();
  });
  await user.click(screen.getByTestId("baseline-submit-btn"));
}

describe("BaselinesView — SE-Auditor override (GH-513)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(workspaceContext.useWorkspace).mockReturnValue({
      activeWorkspace: MOCK_WORKSPACE,
    } as any);
    vi.mocked(artifactsModule.artifactsApi.list).mockResolvedValue({
      results: [],
    } as any);
    vi.mocked(baselinesModule.baselinesApi.list).mockResolvedValue({
      results: [],
    } as any);
    vi.mocked(baselinesModule.baselinesApi.previewScope).mockResolvedValue({
      count: 0,
      sample: [],
    } as any);
  });

  it("offers the override panel after a blocked create", async () => {
    vi.mocked(baselinesModule.baselinesApi.create).mockRejectedValue(
      BLOCKED_ENVELOPE,
    );
    const user = userEvent.setup();

    renderView();
    await submitCreateForm(user);

    await waitFor(() => {
      expect(screen.getByTestId("baseline-override-panel")).toBeInTheDocument();
    });
    // A justification is mandatory — the button stays inert until there is one.
    expect(screen.getByTestId("baseline-override-submit-btn")).toBeDisabled();
  });

  it("sends the justification as override_reason", async () => {
    const createMock = vi.mocked(baselinesModule.baselinesApi.create);
    const created = {
      id: "bl-513",
      workspace_id: MOCK_WORKSPACE.id,
      name: "waived",
      scope: "project",
      description: "",
      artifact_id: null,
      version: 1,
      created_at: "2026-08-15T10:00:00Z",
    };
    createMock.mockRejectedValueOnce(BLOCKED_ENVELOPE);
    createMock.mockResolvedValueOnce(created as any);
    // Selecting the new baseline triggers the detail query.
    vi.mocked(baselinesModule.baselinesApi.get).mockResolvedValue(
      created as any,
    );
    const user = userEvent.setup();

    renderView();
    await submitCreateForm(user);

    await waitFor(() => {
      expect(screen.getByTestId("baseline-override-panel")).toBeInTheDocument();
    });
    await user.type(
      screen.getByTestId("baseline-override-reason"),
      "Accepted deviation for the beta cut.",
    );
    await user.click(screen.getByTestId("baseline-override-submit-btn"));

    await waitFor(() => {
      expect(createMock).toHaveBeenCalledTimes(2);
    });
    expect(createMock.mock.calls[1][0]).toMatchObject({
      override_reason: "Accepted deviation for the beta cut.",
    });
    // First attempt must stay override-free — a waiver is never implicit.
    expect(createMock.mock.calls[0][0]).not.toHaveProperty("override_reason");
  });

  it("does not offer an override for a non-waivable failure", async () => {
    // e.g. the auditor itself could not be evaluated (GH-400 fail-closed).
    vi.mocked(baselinesModule.baselinesApi.create).mockRejectedValue({
      error: { code: "VALIDATION_ERROR", message: "gate not evaluable" },
    });
    const user = userEvent.setup();

    renderView();
    await submitCreateForm(user);

    await waitFor(() => {
      expect(screen.getByText("gate not evaluable")).toBeInTheDocument();
    });
    expect(
      screen.queryByTestId("baseline-override-panel"),
    ).not.toBeInTheDocument();
  });
});
