/** <QualityBadge> (B5-T5): none / score / stale states + percent formatting. */
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { resolveLocaleKey } from "../../test/i18n-test-helpers";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => resolveLocaleKey(key) ?? key }),
}));

import type { QualityAssessment } from "../../api/quality";
import { QualityBadge, formatQualityScore } from "./QualityBadge";

const LABEL = resolveLocaleKey("quality.badge.label") ?? "";
const NONE = resolveLocaleKey("quality.badge.none") ?? "";
const STALE = resolveLocaleKey("quality.stale") ?? "";

const ASSESSMENT = {
  assessment_id: "a1", entity_type: "Requirement", entity_id: "e1", score: 0.5, reasoning: "ok",
  suggestions: [], criteria: {}, prompt_slot: "quality_requirement", prompt_scope: "factory",
  provider: "mock", model: "", trigger: "manual", status: "ok", cached: false,
  assessed_at: "2026-10-21T10:00:00Z",
} as QualityAssessment;

describe("QualityBadge", () => {
  it("renders the not-assessed state without a score", () => {
    render(<QualityBadge latest={null} onToggle={vi.fn()} />);
    expect(screen.getByTestId("quality-badge")).toHaveTextContent(LABEL);
    expect(screen.getByTestId("quality-badge")).toHaveTextContent(NONE);
    expect(screen.queryByTestId("quality-badge-score")).toBeNull();
    expect(screen.queryByTestId("quality-stale-hint")).toBeNull();
  });
  it("renders the score as a rounded whole percentage", () => {
    render(<QualityBadge latest={ASSESSMENT} onToggle={vi.fn()} />);
    expect(screen.getByTestId("quality-badge-score")).toHaveTextContent("50%");
    expect(screen.queryByTestId("quality-stale-hint")).toBeNull();
    expect(formatQualityScore(0.366)).toBe("37%");
    expect(formatQualityScore(1)).toBe("100%");
  });
  it("renders the stale hint next to the score", () => {
    render(<QualityBadge latest={ASSESSMENT} stale onToggle={vi.fn()} />);
    expect(screen.getByTestId("quality-badge-score")).toHaveTextContent("50%");
    expect(screen.getByTestId("quality-stale-hint")).toHaveTextContent(STALE);
  });
  it("exposes its expanded state and toggles on click", async () => {
    const onToggle = vi.fn();
    render(<QualityBadge latest={null} onToggle={onToggle} />);
    const badge = screen.getByTestId("quality-badge");
    expect(badge).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(badge);
    expect(onToggle).toHaveBeenCalledTimes(1);
  });
});
