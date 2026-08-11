/**
 * ARCH-L1-001 ReactFrontend — RequirementBundleExportPanel unit test.
 *
 * Requirement Bundle Export — Plan 3 (UI Panel), Task 4.
 *
 * Covers the lazy-load invariant (no fetch on mount), raw JSON export,
 * compressed sync export (mock-fallback banner), compressed async export
 * (dispatch + poll via the real useBundleCompressionStatus hook, backed by
 * the mocked requirementBundleApi), and the error/retry path.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { RequirementBundleExportPanel } from "../components/RequirementBundleExport/RequirementBundleExportPanel";

// t() returns the key so assertions can rely on data-testid, not copy.
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock("../api/client", () => ({
  extractErrorMessage: (e: unknown) => (e instanceof Error ? e.message : "error"),
}));

const exportRaw = vi.fn();
const exportCompressed = vi.fn();
const getCompressionStatus = vi.fn();
vi.mock("../api/requirementBundle", () => ({
  requirementBundleApi: {
    exportRaw: (...args: unknown[]) => exportRaw(...args),
    exportCompressed: (...args: unknown[]) => exportCompressed(...args),
    getCompressionStatus: (...args: unknown[]) => getCompressionStatus(...args),
  },
}));

function renderPanel() {
  return render(
    <RequirementBundleExportPanel elementId="elem-1" elementTitle="Payment Subsystem" />
  );
}

describe("RequirementBundleExportPanel", () => {
  beforeEach(() => {
    exportRaw.mockReset();
    exportCompressed.mockReset();
    getCompressionStatus.mockReset();
  });

  it("does not call any API on mount (lazy-load invariant)", () => {
    renderPanel();
    expect(exportRaw).not.toHaveBeenCalled();
    expect(exportCompressed).not.toHaveBeenCalled();
  });

  it("fetches and renders a raw JSON bundle on export", async () => {
    exportRaw.mockResolvedValue({
      format: "json",
      items: [{ requirement_id: "r1", found_under_element_id: "a1", depth: 0, fields: { title: "Req A" } }],
      truncated_at_depth: false,
    });
    const user = userEvent.setup();
    renderPanel();

    await user.click(screen.getByTestId("arch-bundle-export-submit"));

    await waitFor(() => expect(screen.getByTestId("arch-bundle-export-result")).toBeInTheDocument());
    expect(exportRaw).toHaveBeenCalledWith("elem-1", expect.objectContaining({ output_format: "json" }));
    expect(screen.getByTestId("arch-bundle-export-result")).toHaveTextContent("Req A");
  });

  it("renders compressed sync text via markdown", async () => {
    exportCompressed.mockResolvedValue({ text: "**compressed**", cache_hit: false, is_mock_fallback: true });
    const user = userEvent.setup();
    renderPanel();

    await user.click(screen.getByTestId("arch-bundle-export-mode-compressed"));
    await user.click(screen.getByTestId("arch-bundle-export-submit"));

    await waitFor(() => expect(screen.getByTestId("arch-bundle-export-result")).toBeInTheDocument());
    expect(screen.getByTestId("arch-bundle-export-mock-fallback")).toBeInTheDocument();
  });

  it("shows a cache-hit indicator when the compressed result was served from cache", async () => {
    exportCompressed.mockResolvedValue({ text: "cached text", cache_hit: true, is_mock_fallback: false });
    const user = userEvent.setup();
    renderPanel();

    await user.click(screen.getByTestId("arch-bundle-export-mode-compressed"));
    await user.click(screen.getByTestId("arch-bundle-export-submit"));

    await waitFor(() => expect(screen.getByTestId("arch-bundle-export-cache-hit")).toBeInTheDocument());
    expect(screen.queryByTestId("arch-bundle-export-mock-fallback")).toBeNull();
  });

  it("polls for an async dispatch and renders the result once done", async () => {
    exportCompressed.mockResolvedValue({ task_id: "task-1" });
    getCompressionStatus.mockResolvedValue({
      task_id: "task-1", status: "done", result: { result: "async compressed text" }, error: null,
    });
    const user = userEvent.setup();
    renderPanel();

    await user.click(screen.getByTestId("arch-bundle-export-mode-compressed"));
    await user.click(screen.getByTestId("arch-bundle-export-async"));
    await user.click(screen.getByTestId("arch-bundle-export-submit"));

    await waitFor(() => expect(screen.getByTestId("arch-bundle-export-result")).toHaveTextContent("async compressed text"));
  });

  it("shows a fallback error when an async compression poll ends in 'not_found'", async () => {
    exportCompressed.mockResolvedValue({ task_id: "task-1" });
    getCompressionStatus.mockResolvedValue({
      task_id: "task-1", status: "not_found", result: null, error: null,
    });
    const user = userEvent.setup();
    renderPanel();

    await user.click(screen.getByTestId("arch-bundle-export-mode-compressed"));
    await user.click(screen.getByTestId("arch-bundle-export-async"));
    await user.click(screen.getByTestId("arch-bundle-export-submit"));

    await waitFor(() => expect(screen.getByTestId("arch-bundle-export-error")).toBeInTheDocument());
    expect(screen.getByTestId("arch-bundle-export-error")).toHaveTextContent("bundleExport.taskNotFound");
    expect(screen.queryByTestId("arch-bundle-export-polling")).toBeNull();
  });

  it("shows a fallback error when an async compression poll ends in 'failed' with no error message", async () => {
    exportCompressed.mockResolvedValue({ task_id: "task-1" });
    getCompressionStatus.mockResolvedValue({
      task_id: "task-1", status: "failed", result: null, error: null,
    });
    const user = userEvent.setup();
    renderPanel();

    await user.click(screen.getByTestId("arch-bundle-export-mode-compressed"));
    await user.click(screen.getByTestId("arch-bundle-export-async"));
    await user.click(screen.getByTestId("arch-bundle-export-submit"));

    await waitFor(() => expect(screen.getByTestId("arch-bundle-export-error")).toBeInTheDocument());
    expect(screen.getByTestId("arch-bundle-export-error")).toHaveTextContent("bundleExport.compressionFailed");
  });

  it("shows an error on failure and lets the user retry", async () => {
    exportRaw.mockRejectedValue(new Error("Element not found"));
    const user = userEvent.setup();
    renderPanel();

    await user.click(screen.getByTestId("arch-bundle-export-submit"));

    await waitFor(() => expect(screen.getByTestId("arch-bundle-export-error")).toHaveTextContent("Element not found"));
    expect(screen.getByTestId("arch-bundle-export-submit")).not.toBeDisabled();
  });

  it("shows the custom fields input only when filter mode is custom, and sends it comma-joined", async () => {
    exportRaw.mockResolvedValue({ format: "json", items: [], truncated_at_depth: false });
    const user = userEvent.setup();
    renderPanel();

    expect(screen.queryByTestId("arch-bundle-export-fields")).toBeNull();

    await user.selectOptions(screen.getByTestId("arch-bundle-export-filter-mode"), "custom");
    expect(screen.getByTestId("arch-bundle-export-fields")).toBeInTheDocument();

    await user.type(screen.getByTestId("arch-bundle-export-fields"), "title, status");
    await user.click(screen.getByTestId("arch-bundle-export-submit"));

    await waitFor(() => expect(exportRaw).toHaveBeenCalled());
    expect(exportRaw).toHaveBeenCalledWith(
      "elem-1",
      expect.objectContaining({ filter_mode: "custom", fields: ["title", "status"] })
    );
  });
});
