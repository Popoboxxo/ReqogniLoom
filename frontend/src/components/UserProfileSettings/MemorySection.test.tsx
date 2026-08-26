import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { MemorySection } from "./MemorySection";
import { memorySelfServiceApi } from "../../api/memory-self-service";

vi.mock("../../api/memory-self-service", () => ({
  memorySelfServiceApi: { get: vi.fn(), deleteAll: vi.fn() },
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (_key: string, fallback?: string) => fallback ?? _key }),
}));

describe("MemorySection", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows the loading state, then resolves to the overview", async () => {
    vi.mocked(memorySelfServiceApi.get).mockResolvedValue({
      entry_count: 3,
      last_updated_at: "2026-08-20T10:00:00Z",
    });

    render(<MemorySection />);

    expect(screen.getByTestId("memory-self-service-loading")).toBeInTheDocument();

    expect(await screen.findByTestId("memory-self-service-count")).toHaveTextContent("3");
    expect(screen.queryByTestId("memory-self-service-loading")).not.toBeInTheDocument();
  });

  it("zero-entries state: delete button disabled, empty message shown", async () => {
    vi.mocked(memorySelfServiceApi.get).mockResolvedValue({
      entry_count: 0,
      last_updated_at: null,
    });

    render(<MemorySection />);

    const btn = await screen.findByTestId("memory-self-service-delete-btn");
    expect(btn).toBeDisabled();
    expect(await screen.findByTestId("memory-self-service-empty")).toBeInTheDocument();
    expect(screen.getByTestId("memory-self-service-count")).toHaveTextContent("0");
  });

  it("non-zero entries: count and last-updated render correctly", async () => {
    vi.mocked(memorySelfServiceApi.get).mockResolvedValue({
      entry_count: 7,
      last_updated_at: "2026-08-20T10:00:00Z",
    });

    render(<MemorySection />);

    expect(await screen.findByTestId("memory-self-service-count")).toHaveTextContent("7");
    const lastUpdated = screen.getByTestId("memory-self-service-last-updated");
    expect(lastUpdated.textContent).not.toBe("—");
    expect(lastUpdated.textContent).not.toBe("");

    const btn = screen.getByTestId("memory-self-service-delete-btn");
    expect(btn).not.toBeDisabled();
  });

  it("delete flow with confirm=true: calls deleteAll and resets the UI to empty", async () => {
    vi.mocked(memorySelfServiceApi.get).mockResolvedValue({
      entry_count: 4,
      last_updated_at: "2026-08-20T10:00:00Z",
    });
    vi.mocked(memorySelfServiceApi.deleteAll).mockResolvedValue({ deleted: 4 });
    vi.spyOn(window, "confirm").mockReturnValue(true);

    const user = userEvent.setup();
    render(<MemorySection />);

    const btn = await screen.findByTestId("memory-self-service-delete-btn");
    expect(btn).not.toBeDisabled();
    await user.click(btn);

    await waitFor(() => {
      expect(memorySelfServiceApi.deleteAll).toHaveBeenCalledTimes(1);
    });

    await waitFor(() => {
      expect(screen.getByTestId("memory-self-service-count")).toHaveTextContent("0");
    });
    expect(screen.getByTestId("memory-self-service-delete-btn")).toBeDisabled();
    expect(await screen.findByTestId("memory-self-service-empty")).toBeInTheDocument();
  });

  it("delete flow with confirm=false: does not call deleteAll", async () => {
    vi.mocked(memorySelfServiceApi.get).mockResolvedValue({
      entry_count: 4,
      last_updated_at: "2026-08-20T10:00:00Z",
    });
    vi.spyOn(window, "confirm").mockReturnValue(false);

    const user = userEvent.setup();
    render(<MemorySection />);

    const btn = await screen.findByTestId("memory-self-service-delete-btn");
    await user.click(btn);

    expect(memorySelfServiceApi.deleteAll).not.toHaveBeenCalled();
    expect(screen.getByTestId("memory-self-service-count")).toHaveTextContent("4");
  });

  it("shows an error message when loading fails", async () => {
    vi.mocked(memorySelfServiceApi.get).mockRejectedValue({
      error: { message: "boom" },
    });

    render(<MemorySection />);

    expect(await screen.findByTestId("memory-self-service-error")).toHaveTextContent("boom");
  });

  it("shows an error message when delete fails", async () => {
    vi.mocked(memorySelfServiceApi.get).mockResolvedValue({
      entry_count: 2,
      last_updated_at: "2026-08-20T10:00:00Z",
    });
    vi.mocked(memorySelfServiceApi.deleteAll).mockRejectedValue({
      error: { message: "delete failed" },
    });
    vi.spyOn(window, "confirm").mockReturnValue(true);

    const user = userEvent.setup();
    render(<MemorySection />);

    const btn = await screen.findByTestId("memory-self-service-delete-btn");
    await user.click(btn);

    expect(await screen.findByTestId("memory-self-service-error")).toHaveTextContent(
      "delete failed"
    );
    // Failed delete must not silently reset the count to 0.
    expect(screen.getByTestId("memory-self-service-count")).toHaveTextContent("2");
  });
});
