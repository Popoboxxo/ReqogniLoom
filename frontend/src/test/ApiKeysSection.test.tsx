/**
 * ARCH-L1-001 ReactFrontend — ApiKeysSection (UserProfileSettings).
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { ApiKeysSection } from "../components/UserProfileSettings/ApiKeysSection";
import { apiKeysApi } from "../api/api-keys";
import "../i18n/index";
import { i18n } from "../i18n/index";

vi.mock("../api/api-keys", () => ({
  apiKeysApi: {
    list: vi.fn(),
    create: vi.fn(),
    revoke: vi.fn(),
  },
}));

describe("ApiKeysSection", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(apiKeysApi.list).mockResolvedValue([]);
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
});
