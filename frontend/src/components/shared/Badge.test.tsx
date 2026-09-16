/**
 * <Badge> contract tests (issue #675).
 *
 * The issue was that status, version and level badges sitting next to each
 * other disagreed on padding, corner radius and font size, and that pages
 * re-derived the variant colours locally. These tests freeze the two halves of
 * the fix:
 *
 *   1. one shared token-based component — `StatusBadge`, `LevelBadge` and
 *      `VersionBadge` must render with byte-identical box metrics;
 *   2. one variant → token mapping — no call site may introduce a colour of
 *      its own, and every value must come from a design token.
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";

import { BADGE_BASE_STYLE } from "../../utils/badgeBase";
import { Badge } from "./Badge";
import { LevelBadge } from "./LevelBadge";
import { StatusBadge } from "./StatusBadge";
import { VersionBadge } from "./VersionBadge";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (_key: string, fallback?: string) => fallback ?? _key,
  }),
}));

/**
 * The layout properties a badge row actually reacts to. Colour and the
 * semantic extras (font family, tracking, weight) are deliberately excluded —
 * those are allowed to differ per badge by design.
 */
const BOX_METRICS = [
  "display",
  "alignItems",
  "justifyContent",
  "boxSizing",
  "flexShrink",
  "minHeight",
  "padding",
  "borderRadius",
  "fontSize",
  "fontWeight",
  "lineHeight",
  "whiteSpace",
] as const;

function readBoxMetrics(element: HTMLElement): Record<string, string> {
  const metrics: Record<string, string> = {};
  for (const property of BOX_METRICS) {
    metrics[property] = element.style[property];
  }
  return metrics;
}

describe("<Badge> (issue #675)", () => {
  it("renders the variant's token pair and passes through the test id", () => {
    render(
      <Badge variant="danger" testId="b" title="tip">
        Blocked
      </Badge>,
    );
    const badge = screen.getByTestId("b");
    expect(badge).toHaveTextContent("Blocked");
    expect(badge).toHaveAttribute("title", "tip");
    expect(badge.style.background).toBe("var(--color-badge-danger-bg)");
    expect(badge.style.color).toBe("var(--color-badge-danger-text)");
  });

  it("defaults to the neutral variant rather than colour-coding by accident", () => {
    render(<Badge testId="b">Draft</Badge>);
    expect(screen.getByTestId("b").style.background).toBe("var(--color-badge-neutral-bg)");
  });

  it("merges semantic overrides without letting them replace the shared geometry", () => {
    render(
      <Badge testId="b" style={{ letterSpacing: "var(--tracking-wide)" }}>
        L1
      </Badge>,
    );
    const badge = screen.getByTestId("b");
    expect(badge.style.letterSpacing).toBe("var(--tracking-wide)");
    expect(badge.style.borderRadius).toBe(BADGE_BASE_STYLE.borderRadius);
    expect(badge.style.minHeight).toBe(BADGE_BASE_STYLE.minHeight);
  });

  it("references only design tokens for size, radius and colour (no hardcoded values)", () => {
    render(<Badge variant="success" testId="b">Done</Badge>);
    const style = screen.getByTestId("b").style;
    for (const property of ["padding", "borderRadius", "fontSize", "background", "color"] as const) {
      expect(style[property], property).toContain("var(--");
    }
  });
});

describe("shared badges render through the one <Badge> (issue #675)", () => {
  it("gives status, level and version badges identical box metrics", () => {
    render(
      <>
        <Badge variant="neutral" testId="reference">ref</Badge>
        <StatusBadge status="Freigegeben" testId="status" />
        <LevelBadge level={1} testId="level" />
        <VersionBadge version={2} />
      </>,
    );

    const reference = readBoxMetrics(screen.getByTestId("reference"));
    expect(readBoxMetrics(screen.getByTestId("status"))).toEqual(reference);
    expect(readBoxMetrics(screen.getByTestId("level"))).toEqual(reference);
    expect(readBoxMetrics(screen.getByTestId("version-badge"))).toEqual(reference);
  });

  it("keeps the badges' own semantic extras intact", () => {
    render(
      <>
        <LevelBadge level={1} testId="level" title="System Requirement" />
        <VersionBadge version={3} />
      </>,
    );

    // Level: wide tracking for the all-caps L{n} label + the spelled-out title.
    const level = screen.getByTestId("level");
    expect(level.style.letterSpacing).toBe("var(--tracking-wide)");
    expect(level).toHaveAttribute("aria-label", "System Requirement");

    // Version: monospace/tabular numerals, neutral variant, no hue.
    const version = screen.getByTestId("version-badge");
    expect(version.style.fontFamily).toBe("var(--font-mono)");
    expect(version.style.background).toBe("var(--color-badge-neutral-bg)");
  });

  it("classifies the status badge by the shared variant mapping, not by local colour", () => {
    render(
      <>
        <StatusBadge status="approved" testId="approved" />
        <StatusBadge status="blocked" testId="blocked" />
        <StatusBadge status="draft" testId="draft" />
      </>,
    );

    expect(screen.getByTestId("approved").style.background).toBe("var(--color-badge-success-bg)");
    expect(screen.getByTestId("blocked").style.background).toBe("var(--color-badge-warning-bg)");
    expect(screen.getByTestId("draft").style.background).toBe("var(--color-badge-neutral-bg)");
  });
});
