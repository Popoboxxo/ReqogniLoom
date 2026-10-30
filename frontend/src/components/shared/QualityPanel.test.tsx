/** <QualityPanel> (B5-T5): role gate, 503 fallback, plain-text reasoning. */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClientProvider } from "@tanstack/react-query";

import { resolveLocaleKey } from "../../test/i18n-test-helpers";
import { createTestQueryClient } from "../../test/query-client";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => resolveLocaleKey(key) ?? key }),
}));
vi.mock("../../context/AuthContext", () => ({ useAuth: vi.fn() }));
vi.mock("../../api/quality", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/quality")>();
  return { ...actual, assessQuality: vi.fn(), getQualityHistory: vi.fn() };
});

import { assessQuality, getQualityHistory } from "../../api/quality";
import { useAuth } from "../../context/AuthContext";
import { QualityPanel } from "./QualityPanel";

const UNAVAILABLE = resolveLocaleKey("quality.error.unavailable") ?? "";
const REASONING = '<script>alert("x")</script> keep **plain** text';

const ASSESSMENT = {
  assessment_id: "a1", entity_type: "Requirement", entity_id: "e1", score: 0.5, reasoning: REASONING,
  suggestions: ["Tighten the acceptance criteria"], criteria: { atomic: 0.5 },
  prompt_slot: "quality_requirement", prompt_scope: "factory", provider: "mock", model: "",
  trigger: "manual", status: "ok", cached: false, assessed_at: "2026-10-21T10:00:00Z",
};

function renderPanel(roles: string[]) {
  vi.mocked(useAuth).mockReturnValue({ roles } as unknown as ReturnType<typeof useAuth>);
  const client = createTestQueryClient();
  return render(
    <QueryClientProvider client={client}>
      <QualityPanel workspaceId="ws-1" entityType="Requirement" entityId="e1" entityVersion={3} />
    </QueryClientProvider>
  );
}

describe("QualityPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getQualityHistory).mockResolvedValue({
      assessments: [ASSESSMENT as never], count: 1, latest: ASSESSMENT as never,
    });
  });
  it("hides the assess button from a viewer", async () => {
    renderPanel(["viewer"]);
    await screen.findByTestId("quality-history-row-0");
    expect(screen.queryByTestId("quality-assess-button")).toBeNull();
  });
  it("maps an unavailable LLM (503) to the i18n message for an editor", async () => {
    vi.mocked(assessQuality).mockRejectedValue({
      error: { code: "LLM_UNAVAILABLE", message: "provider down", details: [] },
    });
    renderPanel(["editor"]);
    await userEvent.click(await screen.findByTestId("quality-assess-button"));
    expect(await screen.findByRole("alert")).toHaveTextContent(UNAVAILABLE);
  });
  it("renders reasoning and suggestions as plain text, never HTML/Markdown", async () => {
    const { container } = renderPanel(["viewer"]);
    await screen.findByTestId("quality-history-row-0");
    expect(screen.getByText(REASONING)).toBeInTheDocument();
    expect(screen.getByText("Tighten the acceptance criteria")).toBeInTheDocument();
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("strong")).toBeNull();
  });
});
