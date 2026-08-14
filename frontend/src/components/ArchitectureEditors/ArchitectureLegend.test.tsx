/**
 * Regression coverage for #422 — the legend now explains that `role`
 * (badge, derived from tree position) and `element_type` (free-text field)
 * are two independent classifications, so seeing e.g. role "System" next to
 * element_type "component" is expected, not a data inconsistency.
 *
 * Uses the real i18n resources (not a mocked `t`) so a missing/renamed key
 * in the JSON files actually fails this test.
 */

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { i18n } from "../../i18n/index";
import { ArchitectureLegend } from "./ArchitectureLegend";

describe("ArchitectureLegend — role vs. element_type (#422)", () => {
  it("renders the German explanation of role vs. element_type", async () => {
    await i18n.changeLanguage("de");

    render(<ArchitectureLegend />);

    expect(screen.getByText("Rolle vs. Element-Typ")).toBeInTheDocument();
    expect(
      screen.getByText(/Root-Element mit der Rolle „System” kann fachlich trotzdem/)
    ).toBeInTheDocument();
  });

  it("renders the English explanation of role vs. element_type", async () => {
    await i18n.changeLanguage("en");

    render(<ArchitectureLegend />);

    expect(screen.getByText("Role vs. Element Type")).toBeInTheDocument();

    await i18n.changeLanguage("de");
  });
});
