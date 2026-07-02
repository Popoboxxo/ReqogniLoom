/**
 * BaselinesList.test.tsx
 *
 * Tests for BaselinesList component:
 * - Scope selection (document/project/global)
 * - Artifact picker visibility based on scope
 * - Scope preview loading
 * - API call with correct scope
 * - List refresh
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { BaselinesList } from "./BaselinesList";
import * as baselinesApi from "../../api/baselines";
import * as artifactsApi from "../../api/artifacts";
import * as workspaceContext from "../../context/WorkspaceContext";

vi.mock("../../api/baselines");
vi.mock("../../api/artifacts");
vi.mock("../../context/WorkspaceContext");
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

describe("BaselinesList", () => {
  const mockWorkspace = { id: "ws-123", name: "Test", preset: "standard" };
  const mockBaselines = [
    {
      id: "bl-1",
      workspace_id: "ws-123",
      scope: "document",
      artifact_id: "art-1",
      created_at: "2024-01-01T00:00:00Z",
    },
  ];
  const mockArtifacts = [
    { id: "art-1", artifact_type: "requirement", title: "Artifact A" },
    { id: "art-2", artifact_type: "architecture", title: "Artifact B" },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(workspaceContext.useWorkspace).mockReturnValue({
      activeWorkspace: mockWorkspace,
    } as any);
    vi.mocked(baselinesApi.baselinesApi.previewScope).mockResolvedValue({
      count: 5,
    } as any);
  });

  it("renders empty state when no baselines exist", async () => {
    vi.mocked(baselinesApi.baselinesApi.list).mockResolvedValue({
      results: [],
    } as any);
    vi.mocked(artifactsApi.artifactsApi.list).mockResolvedValue({
      results: [],
    } as any);

    render(<BaselinesList />);

    await waitFor(() => {
      expect(screen.getByText("baselines.empty")).toBeInTheDocument();
    });
  });

  it("displays list of baselines", async () => {
    vi.mocked(baselinesApi.baselinesApi.list).mockResolvedValue({
      results: mockBaselines,
    } as any);
    vi.mocked(artifactsApi.artifactsApi.list).mockResolvedValue({
      results: mockArtifacts,
    } as any);

    render(<BaselinesList />);

    await waitFor(() => {
      const items = screen.getAllByTestId("baseline-item");
      expect(items.length).toBeGreaterThan(0);
    });
  });

  it("opens create form when button is clicked", async () => {
    vi.mocked(baselinesApi.baselinesApi.list).mockResolvedValue({
      results: mockBaselines,
    } as any);
    vi.mocked(artifactsApi.artifactsApi.list).mockResolvedValue({
      results: mockArtifacts,
    } as any);

    const user = userEvent.setup();
    render(<BaselinesList />);

    await waitFor(() => {
      expect(screen.getByTestId("baseline-create-btn")).toBeInTheDocument();
    });

    await user.click(screen.getByTestId("baseline-create-btn"));

    expect(screen.getByTestId("baseline-create-form")).toBeInTheDocument();
  });

  it("shows artifact picker only for document scope", async () => {
    vi.mocked(baselinesApi.baselinesApi.list).mockResolvedValue({
      results: [],
    } as any);
    vi.mocked(artifactsApi.artifactsApi.list).mockResolvedValue({
      results: mockArtifacts,
    } as any);

    const user = userEvent.setup();
    render(<BaselinesList />);

    await waitFor(() => {
      expect(screen.getByTestId("baseline-create-btn")).toBeInTheDocument();
    });

    await user.click(screen.getByTestId("baseline-create-btn"));

    // Document scope is not selected by default, so artifact picker should not be visible
    expect(screen.queryByTestId("baseline-artifact-select")).not.toBeInTheDocument();

    // Switch to document scope
    const documentRadio = screen.getByTestId("baseline-scope-document");
    await user.click(documentRadio);

    // Now artifact picker should be visible
    await waitFor(() => {
      expect(screen.getByTestId("baseline-artifact-select")).toBeInTheDocument();
    });
  });

  it("scope change triggers preview update", async () => {
    vi.mocked(baselinesApi.baselinesApi.list).mockResolvedValue({
      results: [],
    } as any);
    vi.mocked(artifactsApi.artifactsApi.list).mockResolvedValue({
      results: mockArtifacts,
    } as any);

    const user = userEvent.setup();
    render(<BaselinesList />);

    await waitFor(() => {
      expect(screen.getByTestId("baseline-create-btn")).toBeInTheDocument();
    });

    await user.click(screen.getByTestId("baseline-create-btn"));

    // Change scope to project
    const projectRadio = screen.getByTestId("baseline-scope-project");
    await user.click(projectRadio);

    await waitFor(() => {
      expect(baselinesApi.baselinesApi.previewScope).toHaveBeenCalled();
    });
  });

  it("calls API with document scope and artifact_id", async () => {
    vi.mocked(baselinesApi.baselinesApi.list).mockResolvedValue({
      results: [],
    } as any);
    vi.mocked(artifactsApi.artifactsApi.list).mockResolvedValue({
      results: mockArtifacts,
    } as any);
    vi.mocked(baselinesApi.baselinesApi.create).mockResolvedValue({} as any);

    const user = userEvent.setup();
    render(<BaselinesList />);

    await waitFor(() => {
      expect(screen.getByTestId("baseline-create-btn")).toBeInTheDocument();
    });

    await user.click(screen.getByTestId("baseline-create-btn"));

    // Select document scope
    const documentRadio = screen.getByTestId("baseline-scope-document");
    await user.click(documentRadio);

    // Artifact should be pre-selected
    await waitFor(() => {
      expect(screen.getByTestId("baseline-artifact-select")).toBeInTheDocument();
    });

    const form = screen.getByTestId("baseline-create-form");
    fireEvent.submit(form);

    await waitFor(() => {
      expect(baselinesApi.baselinesApi.create).toHaveBeenCalledWith(
        expect.objectContaining({
          workspace_id: "ws-123",
          scope: "document",
          artifact_id: "art-1",
        })
      );
    });
  });

  it("calls API with null artifact_id for project scope", async () => {
    vi.mocked(baselinesApi.baselinesApi.list).mockResolvedValue({
      results: [],
    } as any);
    vi.mocked(artifactsApi.artifactsApi.list).mockResolvedValue({
      results: mockArtifacts,
    } as any);
    vi.mocked(baselinesApi.baselinesApi.create).mockResolvedValue({} as any);

    const user = userEvent.setup();
    render(<BaselinesList />);

    await waitFor(() => {
      expect(screen.getByTestId("baseline-create-btn")).toBeInTheDocument();
    });

    await user.click(screen.getByTestId("baseline-create-btn"));

    const projectRadio = screen.getByTestId("baseline-scope-project");
    await user.click(projectRadio);

    const form = screen.getByTestId("baseline-create-form");
    fireEvent.submit(form);

    await waitFor(() => {
      expect(baselinesApi.baselinesApi.create).toHaveBeenCalledWith(
        expect.objectContaining({
          workspace_id: "ws-123",
          scope: "project",
          artifact_id: null,
        })
      );
    });
  });

  it("shows validation error when document scope has no artifact", async () => {
    vi.mocked(baselinesApi.baselinesApi.list).mockResolvedValue({
      results: [],
    } as any);
    vi.mocked(artifactsApi.artifactsApi.list).mockResolvedValue({
      results: [],
    } as any);

    const user = userEvent.setup();
    render(<BaselinesList />);

    await waitFor(() => {
      expect(screen.getByTestId("baseline-create-btn")).toBeInTheDocument();
    });

    await user.click(screen.getByTestId("baseline-create-btn"));

    const documentRadio = screen.getByTestId("baseline-scope-document");
    await user.click(documentRadio);

    const form = screen.getByTestId("baseline-create-form");
    fireEvent.submit(form);

    await waitFor(() => {
      expect(screen.getByText("baselines.artifactRequired")).toBeInTheDocument();
    });
  });
});
