import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { MemorySettingsSection } from "./MemorySettingsSection";
import {
  memorySettingsApi,
  type MemorySettings,
} from "../../api/memory-settings";

vi.mock("../../api/memory-settings", () => ({
  memorySettingsApi: { get: vi.fn(), update: vi.fn() },
}));

vi.mock("react-i18next", () => ({
  // Mirrors i18next closely enough for these tests: the second argument is the
  // call site's default copy, `{{name}}` placeholders are interpolated from the
  // options object (the derived HARD_OFF summary needs that).
  useTranslation: () => ({
    t: (key: string, fallback?: string, options?: { total?: number }) => {
      const text = fallback ?? key;
      return options?.total === undefined
        ? text
        : text.replace("{{total}}", String(options.total));
    },
  }),
}));

/** Full current GET payload (Plan A T-A1-3) with per-test overrides. */
function settings(overrides: Partial<MemorySettings> = {}): MemorySettings {
  return {
    enabled: true,
    disabled_slots: [],
    allow_user_opt_out: true,
    effective_disabled_slots: [],
    available_slots: [],
    ...overrides,
  };
}

describe("MemorySettingsSection", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows the current enabled state", async () => {
    vi.mocked(memorySettingsApi.get).mockResolvedValue(settings());
    render(<MemorySettingsSection workspaceId="ws-1" />);
    const toggle = await screen.findByTestId("memory-settings-toggle");
    expect(toggle).toBeChecked();
    expect(memorySettingsApi.get).toHaveBeenCalledWith("ws-1");
  });

  it("reflects a disabled state from the backend", async () => {
    vi.mocked(memorySettingsApi.get).mockResolvedValue(settings({ enabled: false }));
    render(<MemorySettingsSection workspaceId="ws-1" />);
    const toggle = await screen.findByTestId("memory-settings-toggle");
    expect(toggle).not.toBeChecked();
  });

  it("toggling calls the update endpoint and shows the saved indicator", async () => {
    vi.mocked(memorySettingsApi.get).mockResolvedValue(settings());
    vi.mocked(memorySettingsApi.update).mockResolvedValue(settings({ enabled: false }));
    render(<MemorySettingsSection workspaceId="ws-1" />);
    const toggle = await screen.findByTestId("memory-settings-toggle");
    fireEvent.click(toggle);
    await waitFor(() =>
      expect(memorySettingsApi.update).toHaveBeenCalledWith("ws-1", { enabled: false })
    );
    expect(await screen.findByTestId("memory-settings-saved")).toBeInTheDocument();
    expect(toggle).not.toBeChecked();
  });

  it("shows an error and reverts the toggle when the update fails (e.g. 403 for a viewer)", async () => {
    vi.mocked(memorySettingsApi.get).mockResolvedValue(settings());
    vi.mocked(memorySettingsApi.update).mockRejectedValue({
      error: { message: "editor or admin role required." },
    });
    render(<MemorySettingsSection workspaceId="ws-1" />);
    const toggle = await screen.findByTestId("memory-settings-toggle");
    fireEvent.click(toggle);
    expect(
      await screen.findByText("editor or admin role required.")
    ).toBeInTheDocument();
    await waitFor(() => expect(toggle).toBeChecked());
  });

  // Plan A T-A1-7: a HARD_OFF slot can never receive memory (T-A1-1), so the
  // backend rejects it in `disabled_slots` ("slot is hard-off"). The UI must
  // therefore render it disabled with the hint instead of offering a value
  // the writer refuses.
  it("renders a hard-off slot disabled with the 'never uses memory' hint", async () => {
    vi.mocked(memorySettingsApi.get).mockResolvedValue(
      settings({
        available_slots: [
          { name: "bundle_compression", hard_off: true },
          { name: "testcase_derive", hard_off: false },
        ],
      })
    );
    render(<MemorySettingsSection workspaceId="ws-1" />);

    expect(await screen.findByTestId("memory-settings-disabled-slots")).toBeInTheDocument();
    const hardOff = await screen.findByTestId(
      "memory-settings-slot-toggle-bundle-compression"
    );
    expect(hardOff).toBeDisabled();
    expect(hardOff).not.toBeChecked();
    expect(screen.getByText("never uses memory")).toBeInTheDocument();
    expect(screen.getByTestId("memory-settings-slot-toggle-testcase-derive")).not.toBeDisabled();

    // UI review: a real fieldset/legend group, the HARD_OFF explanation
    // reachable via aria-describedby, and a derived count of the activities
    // that never use memory.
    expect(screen.getByTestId("memory-settings-disabled-slots").tagName).toBe("FIELDSET");
    expect(screen.getByText("Memory per AI activity")).toBeInTheDocument();
    expect(screen.getByText("AI activities that never use memory: 1")).toBeInTheDocument();
    const hint = screen.getByText("never uses memory");
    expect(hardOff).toHaveAttribute("aria-describedby", hint.id);

    fireEvent.click(hardOff);
    expect(memorySettingsApi.update).not.toHaveBeenCalled();
  });

  it("toggling a normal slot sends the expected partial PUT body", async () => {
    vi.mocked(memorySettingsApi.get).mockResolvedValue(
      settings({ available_slots: [{ name: "testcase_derive", hard_off: false }] })
    );
    vi.mocked(memorySettingsApi.update).mockResolvedValue(
      settings({
        disabled_slots: ["testcase_derive"],
        effective_disabled_slots: ["testcase_derive"],
        available_slots: [{ name: "testcase_derive", hard_off: false }],
      })
    );
    render(<MemorySettingsSection workspaceId="ws-1" />);

    const slot = await screen.findByTestId("memory-settings-slot-toggle-testcase-derive");
    expect(slot).toBeChecked();

    fireEvent.click(slot);

    // Only the changed field: `enabled`/`allow_user_opt_out` stay untouched.
    await waitFor(() =>
      expect(memorySettingsApi.update).toHaveBeenCalledWith("ws-1", {
        disabled_slots: ["testcase_derive"],
      })
    );
    await waitFor(() => expect(slot).not.toBeChecked());
  });

  it("toggling the allow_user_opt_out checkbox sends only that field", async () => {
    vi.mocked(memorySettingsApi.get).mockResolvedValue(settings());
    vi.mocked(memorySettingsApi.update).mockResolvedValue(
      settings({ allow_user_opt_out: false })
    );
    render(<MemorySettingsSection workspaceId="ws-1" />);

    const checkbox = await screen.findByTestId("memory-settings-allow-user-opt-out");
    expect(checkbox).toBeChecked();
    fireEvent.click(checkbox);

    await waitFor(() =>
      expect(memorySettingsApi.update).toHaveBeenCalledWith("ws-1", {
        allow_user_opt_out: false,
      })
    );
  });

  // UI review (blocking): a failed GET leaves the section seeded from this
  // component's defaults (enabled=true, allow_user_opt_out=true), so an enabled
  // control would PUT a workspace policy value nobody ever read. Every control
  // family must be disabled and the slot group must stay mounted under the
  // role="alert".
  it("a failed GET disables every control and sends no PUT", async () => {
    vi.mocked(memorySettingsApi.get).mockResolvedValueOnce(
      settings({ available_slots: [{ name: "testcase_derive", hard_off: false }] })
    );
    const { rerender } = render(<MemorySettingsSection workspaceId="ws-1" />);
    await screen.findByTestId("memory-settings-slot-toggle-testcase-derive");

    vi.mocked(memorySettingsApi.get).mockRejectedValueOnce({
      error: { message: "settings unavailable" },
    });
    rerender(<MemorySettingsSection workspaceId="ws-2" />);

    const alert = await screen.findByTestId("memory-settings-error");
    expect(alert).toHaveTextContent("settings unavailable");
    expect(alert).toHaveAttribute("role", "alert");

    // The slot group stays mounted *below* the alert.
    const group = screen.getByTestId("memory-settings-disabled-slots");
    expect(group).toBeInTheDocument();
    expect(
      alert.compareDocumentPosition(group) & Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy();

    const enabledToggle = screen.getByTestId("memory-settings-toggle");
    const allowUserOptOut = screen.getByTestId("memory-settings-allow-user-opt-out");
    const slotToggle = screen.getByTestId(
      "memory-settings-slot-toggle-testcase-derive"
    );
    expect(enabledToggle).toBeDisabled();
    expect(allowUserOptOut).toBeDisabled();
    expect(slotToggle).toBeDisabled();

    fireEvent.click(enabledToggle);
    fireEvent.click(allowUserOptOut);
    fireEvent.click(slotToggle);
    expect(memorySettingsApi.update).not.toHaveBeenCalled();
    expect(enabledToggle).toBeChecked();
    expect(allowUserOptOut).toBeChecked();
  });
});
