/**
 * InterviewProvenanceBadge — multi-artifact-interview plan, Task 14 (frontend
 * half). Renders nothing while/when no provenance row exists for the
 * artifact; renders a link to the interview area once the backend's
 * `GET /interviews/by-artifact/{artifact_id}/` lookup reports a session.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { InterviewProvenanceBadge } from "./InterviewProvenanceBadge";
import { resolveLocaleKey } from "../../test/i18n-test-helpers";

vi.mock("../../api/interviews", () => ({
  interviewsApi: { getProvenance: vi.fn() },
}));
import { interviewsApi } from "../../api/interviews";

// Same convention as InterviewChatPane.test.tsx: resolve keys against
// de.json (de/en parity itself is guarded by src/test/i18n-parity.test.ts).
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => resolveLocaleKey(key) ?? key,
  }),
}));

const BADGE_LABEL = resolveLocaleKey("interview.multi.createdBadge") ?? "";

function renderBadge(artifactId: string) {
  return render(
    <MemoryRouter>
      <InterviewProvenanceBadge artifactId={artifactId} />
    </MemoryRouter>
  );
}

describe("InterviewProvenanceBadge", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders nothing when no provenance exists", async () => {
    vi.mocked(interviewsApi.getProvenance).mockResolvedValue({ session_id: null });
    const { container } = renderBadge("a1");
    await waitFor(() =>
      expect(interviewsApi.getProvenance).toHaveBeenCalledWith("a1")
    );
    expect(
      container.querySelector('[data-testid="interview-provenance-badge"]')
    ).toBeNull();
  });

  it("renders a link to the interview area when provenance exists", async () => {
    vi.mocked(interviewsApi.getProvenance).mockResolvedValue({ session_id: "s1" });
    renderBadge("a1");
    const badge = await screen.findByTestId("interview-provenance-badge");
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveTextContent(BADGE_LABEL);
    expect(badge.getAttribute("href")).toBe("/interviews");
  });

  it("renders nothing while the lookup is still pending", () => {
    vi.mocked(interviewsApi.getProvenance).mockReturnValue(new Promise(() => {}));
    const { container } = renderBadge("a1");
    expect(
      container.querySelector('[data-testid="interview-provenance-badge"]')
    ).toBeNull();
  });
});
