/**
 * ARCH-L1-001 ReactFrontend — ApiKeysSection (UserProfileSettings).
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { ApiKeysSection } from "../components/UserProfileSettings/ApiKeysSection";
import { apiKeysApi } from "../api/api-keys";
import { getMfaStatus } from "../api/mfa";
import "../i18n/index";
import { i18n } from "../i18n/index";

vi.mock("../api/api-keys", () => ({
  apiKeysApi: {
    list: vi.fn(),
    create: vi.fn(),
    revoke: vi.fn(),
  },
}));

vi.mock("../api/mfa", () => ({
  getMfaStatus: vi.fn(),
}));

describe("ApiKeysSection", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(apiKeysApi.list).mockResolvedValue([]);
    vi.mocked(getMfaStatus).mockResolvedValue({
      enrolled: false,
      confirmed_at: null,
      recovery_codes_remaining: 0,
      enforcement: "optional",
      required: false,
    });
  });

  it("uses the unified + New API Key trigger label", async () => {
    const previousLanguage = i18n.language;
    void i18n.changeLanguage("de");

    render(<ApiKeysSection />);

    await waitFor(() => {
      expect(screen.getByTestId("api-key-create-btn")).toBeInTheDocument();
    });

    expect(screen.getByTestId("api-key-create-btn")).toHaveTextContent("+ Neu API-Key");

    void i18n.changeLanguage(previousLanguage);
  });

  it("renders the optional expiry field when the policy does not require it", async () => {
    render(<ApiKeysSection />);

    const expiry = await screen.findByTestId("api-key-expires-input");
    expect(expiry).not.toHaveAttribute("required");
  });

  it("marks the expiry field required under MFA_STAFF_ENFORCEMENT=required", async () => {
    vi.mocked(getMfaStatus).mockResolvedValue({
      enrolled: true,
      confirmed_at: "2026-10-01T10:00:00Z",
      recovery_codes_remaining: 9,
      enforcement: "required",
      required: true,
    });

    render(<ApiKeysSection />);

    await waitFor(() =>
      expect(screen.getByTestId("api-key-expires-input")).toHaveAttribute("required")
    );
  });
});
