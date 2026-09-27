/**
 * `<AiActionSection>` unit test (issue #1092).
 *
 * Pins the two properties the issue actually asks for, plus the one that makes
 * the grouping hold over time:
 *
 *   1. Every AI action carries the SAME flat icon from the repo's existing set
 *      (lucide `Sparkles`, `currentColor`, 16px) — the `✨` emoji is gone, so
 *      the group is recognisable at a glance and renders identically on every
 *      platform.
 *   2. No actions → no section. That is the context-awareness contract: a
 *      route or a role without AI capability gets no AI region at all, rather
 *      than an empty box or a disabled button.
 *   3. A `children`-style API could not enforce (1), so the actions are data:
 *      there is no way to render a button in this section without the icon.
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { AiActionSection, type AiActionDescriptor } from "./AiActionSection";

function action(overrides: Partial<AiActionDescriptor> = {}): AiActionDescriptor {
  return {
    label: "KI-Ableitung",
    onClick: vi.fn(),
    testId: "ai-action-1",
    ...overrides,
  };
}

describe("AiActionSection", () => {
  it("renders nothing when the context has no AI capability", () => {
    const { container } = render(
      <AiActionSection actions={[]} title="KI-Aktionen" />
    );
    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByTestId("ai-actions-section")).not.toBeInTheDocument();
  });

  it("groups every AI action in one titled region", () => {
    render(
      <AiActionSection
        title="KI-Aktionen"
        hint="Die KI erzeugt Entwürfe zur Prüfung."
        actions={[
          action({ testId: "ai-action-1", label: "KI-Ableitung" }),
          action({ testId: "ai-action-2", label: "KI-Testfall" }),
        ]}
      />
    );

    const section = screen.getByTestId("ai-actions-section");
    expect(section.tagName).toBe("SECTION");
    expect(section).toHaveAccessibleName("KI-Aktionen");
    expect(within(section).getByTestId("ai-action-1")).toBeInTheDocument();
    expect(within(section).getByTestId("ai-action-2")).toBeInTheDocument();
    // Exactly one region, so the actions cannot be spread across headers.
    expect(screen.getAllByRole("region")).toHaveLength(1);
  });

  it("gives every AI action the same flat single-colour icon", () => {
    render(
      <AiActionSection
        title="KI-Aktionen"
        actions={[
          action({ testId: "ai-action-1" }),
          action({ testId: "ai-action-2" }),
        ]}
      />
    );

    for (const testId of ["ai-action-1", "ai-action-2"]) {
      const icon = screen.getByTestId(testId).querySelector("svg.lucide-sparkles");
      expect(icon).not.toBeNull();
      expect(icon).toHaveAttribute("width", "16");
      expect(icon).toHaveAttribute("stroke", "currentColor");
      // No emoji anywhere in the button — that was the actual complaint.
      expect(screen.getByTestId(testId).textContent).not.toContain("✨");
    }
  });

  it("puts every AI action on the design system's secondary variant", () => {
    render(
      <AiActionSection
        title="KI-Aktionen"
        actions={[action({ testId: "ai-action-1" }), action({ testId: "ai-action-2" })]}
      />
    );

    // Not `btn-primary`: each artifact route already has exactly one primary
    // action, and a second one is the #797 duplicate-primary complaint.
    expect(screen.getByTestId("ai-action-1")).toHaveClass("btn-secondary");
    expect(screen.getByTestId("ai-action-2")).toHaveClass("btn-secondary");
    expect(screen.getByTestId("ai-action-1")).not.toHaveClass("btn-primary");
  });

  it("fires the action's own handler and honours disabled", async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();
    render(
      <AiActionSection
        title="KI-Aktionen"
        actions={[
          action({ testId: "ai-action-1", onClick }),
          action({ testId: "ai-action-2", disabled: true, onClick: vi.fn() }),
        ]}
      />
    );

    await user.click(screen.getByTestId("ai-action-1"));
    expect(onClick).toHaveBeenCalledTimes(1);

    expect(screen.getByTestId("ai-action-2")).toBeDisabled();
  });

  it("announces the busy state instead of the idle label while an action runs", () => {
    render(
      <AiActionSection
        title="KI-Aktionen"
        actions={[
          action({
            testId: "ai-action-1",
            disabled: true,
            busyLabel: "KI-Ableitung läuft…",
          }),
        ]}
      />
    );

    expect(screen.getByRole("button", { name: "KI-Ableitung läuft…" })).toBeDisabled();
  });

  it("exposes the action's own hint as its tooltip", () => {
    render(
      <AiActionSection
        title="KI-Aktionen"
        actions={[
          action({ testId: "ai-action-1", hint: "Entwürfe zur Prüfung" }),
        ]}
      />
    );

    expect(screen.getByTestId("ai-action-1")).toHaveAttribute(
      "title",
      "Entwürfe zur Prüfung"
    );
  });
});
