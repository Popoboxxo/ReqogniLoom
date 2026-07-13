/**
 * TraceLinksForm.test.tsx
 *
 * Tests for TraceLinksForm component:
 * - Form validation (source/target required, not same)
 * - API call with correct link type
 * - Title resolution for endpoints
 * - List grouping by link type
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TraceLinksForm } from "./TraceLinksForm";
import * as tracelinksApi from "../../api/tracelinks";
import * as requirementsApi from "../../api/requirements";
import * as architectureApi from "../../api/architecture";
import * as testcasesApi from "../../api/testcases";
import * as artifactsApi from "../../api/artifacts";
import * as workspaceContext from "../../context/WorkspaceContext";

vi.mock("../../api/tracelinks");
vi.mock("../../api/requirements");
vi.mock("../../api/architecture");
vi.mock("../../api/testcases");
vi.mock("../../api/artifacts");
vi.mock("../../context/WorkspaceContext");
const mockT = (key: string) => key;
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: mockT,
  }),
}));

describe("TraceLinksForm", () => {
  const mockWorkspace = { id: "ws-123", name: "Test", preset: "standard" };
  const mockLinks = [
    {
      id: "link-1",
      source_id: "req-1",
      target_id: "arch-1",
      link_type: "satisfies",
    },
  ];
  const mockArtifacts = [
    { id: "req-1", artifact_type: "requirement" },
    { id: "arch-1", artifact_type: "architecture" },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(workspaceContext.useWorkspace).mockReturnValue({
      activeWorkspace: mockWorkspace,
    } as any);
    vi.mocked(tracelinksApi.tracelinksApi.list).mockResolvedValue({
      results: mockLinks,
    } as any);
    vi.mocked(requirementsApi.requirementsApi.list).mockResolvedValue({
      results: [{ id: "req-1", title: "Requirement A", artifact_type: "requirement" }],
    } as any);
    vi.mocked(architectureApi.architectureApi.list).mockResolvedValue({
      results: [{ id: "arch-1", title: "Architecture B", artifact_type: "architecture" }],
    } as any);
    vi.mocked(testcasesApi.testcasesApi.list).mockResolvedValue({
      results: [],
    } as any);
    vi.mocked(artifactsApi.artifactsApi.list).mockResolvedValue({
      results: mockArtifacts,
    } as any);
  });

  it("renders empty state when no links exist", async () => {
    vi.mocked(tracelinksApi.tracelinksApi.list).mockResolvedValue({
      results: [],
    } as any);

    render(<TraceLinksForm />);

    await waitFor(() => {
      expect(screen.getByText("traceability.empty")).toBeInTheDocument();
    });
  });

  it("displays grouped trace links", async () => {
    render(<TraceLinksForm />);

    await waitFor(() => {
      expect(screen.getByTestId("tracelink-group")).toBeInTheDocument();
    });
  });

  it("opens create form when button is clicked", async () => {
    const user = userEvent.setup();
    render(<TraceLinksForm />);

    await waitFor(() => {
      expect(screen.getByTestId("tracelink-create-btn")).toBeInTheDocument();
    });

    await user.click(screen.getByTestId("tracelink-create-btn"));

    expect(screen.getByTestId("tracelink-create-form")).toBeInTheDocument();
  });

  it("validates required source field", async () => {
    const user = userEvent.setup();
    render(<TraceLinksForm />);

    await waitFor(() => {
      expect(screen.getByTestId("tracelink-create-btn")).toBeInTheDocument();
    });

    await user.click(screen.getByTestId("tracelink-create-btn"));

    const form = screen.getByTestId("tracelink-create-form");
    fireEvent.submit(form);

    await waitFor(() => {
      expect(screen.getByText("traceability.sourceRequired")).toBeInTheDocument();
    });
  });

  it("validates required target field", async () => {
    const user = userEvent.setup();
    render(<TraceLinksForm />);

    await waitFor(() => {
      expect(screen.getByTestId("tracelink-create-btn")).toBeInTheDocument();
    });

    await user.click(screen.getByTestId("tracelink-create-btn"));

    const sourceSelect = screen.getByTestId("tracelink-source-select");
    await user.selectOptions(sourceSelect, "req-1");

    const form = screen.getByTestId("tracelink-create-form");
    fireEvent.submit(form);

    await waitFor(() => {
      expect(screen.getByText("traceability.targetRequired")).toBeInTheDocument();
    });
  });

  it("validates source and target are different", async () => {
    const user = userEvent.setup();
    render(<TraceLinksForm />);

    await waitFor(() => {
      expect(screen.getByTestId("tracelink-create-btn")).toBeInTheDocument();
    });

    await user.click(screen.getByTestId("tracelink-create-btn"));

    const sourceSelect = screen.getByTestId("tracelink-source-select");
    const targetSelect = screen.getByTestId("tracelink-target-select");

    await user.selectOptions(sourceSelect, "req-1");
    await user.selectOptions(targetSelect, "req-1");

    const form = screen.getByTestId("tracelink-create-form");
    fireEvent.submit(form);

    await waitFor(() => {
      expect(screen.getByText("traceability.sameEndpoints")).toBeInTheDocument();
    });
  });

  it("calls API with correct form data", async () => {
    vi.mocked(tracelinksApi.tracelinksApi.create).mockResolvedValue({} as any);

    const user = userEvent.setup();
    render(<TraceLinksForm />);

    await waitFor(() => {
      expect(screen.getByTestId("tracelink-create-btn")).toBeInTheDocument();
    });

    await user.click(screen.getByTestId("tracelink-create-btn"));

    const sourceSelect = screen.getByTestId("tracelink-source-select");
    const targetSelect = screen.getByTestId("tracelink-target-select");
    const typeSelect = screen.getByTestId("tracelink-type-select");

    await user.selectOptions(sourceSelect, "req-1");
    await user.selectOptions(targetSelect, "arch-1");
    await user.selectOptions(typeSelect, "satisfies");

    const form = screen.getByTestId("tracelink-create-form");
    fireEvent.submit(form);

    await waitFor(() => {
      expect(tracelinksApi.tracelinksApi.create).toHaveBeenCalledWith(
        expect.objectContaining({
          source_id: "req-1",
          target_id: "arch-1",
          link_type: "satisfies",
        })
      );
    });
  });

  it("reloads list after successful creation", async () => {
    vi.mocked(tracelinksApi.tracelinksApi.create).mockResolvedValue({} as any);

    const user = userEvent.setup();
    render(<TraceLinksForm />);

    await waitFor(() => {
      expect(screen.getByTestId("tracelink-create-btn")).toBeInTheDocument();
    });

    await user.click(screen.getByTestId("tracelink-create-btn"));

    const sourceSelect = screen.getByTestId("tracelink-source-select");
    const targetSelect = screen.getByTestId("tracelink-target-select");

    await user.selectOptions(sourceSelect, "req-1");
    await user.selectOptions(targetSelect, "arch-1");

    const form = screen.getByTestId("tracelink-create-form");
    fireEvent.submit(form);

    await waitFor(() => {
      expect(tracelinksApi.tracelinksApi.list).toHaveBeenCalledTimes(2);
    });
  });

  it("displays link type grouped sections", async () => {
    render(<TraceLinksForm />);

    await waitFor(() => {
      const groups = screen.getAllByTestId("tracelink-group");
      expect(groups.length).toBeGreaterThan(0);
    });
  });

  it("displays link endpoints with titles", async () => {
    render(<TraceLinksForm />);

    await waitFor(() => {
      expect(screen.getByTestId("tracelink-source")).toBeInTheDocument();
      expect(screen.getByTestId("tracelink-target")).toBeInTheDocument();
    });
  });
});
