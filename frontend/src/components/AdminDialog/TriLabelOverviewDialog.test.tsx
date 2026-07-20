/**
 * Unit tests for TriLabelOverviewDialog — read-only Tri-Label admin overview.
 *
 * Verifies:
 *   - Renders nothing when isOpen is false
 *   - Renders all 14 LinkType rows when open
 *   - Renders DE/EN downstream/upstream/neutral cells for a sample type
 *   - Close button (header + footer) calls onClose
 *   - No editable form controls are rendered (read-only contract)
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string, fallback?: string) => fallback ?? key }),
}));

import { TriLabelOverviewDialog } from "./TriLabelOverviewDialog";
import { ALL_LINK_TYPES } from "../../constants/traceLinkLabels";

describe("TriLabelOverviewDialog", () => {
  it("renders nothing when isOpen is false", () => {
    const { container } = render(
      <TriLabelOverviewDialog isOpen={false} onClose={vi.fn()} />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("renders the dialog with all 14 LinkType rows when open", () => {
    render(<TriLabelOverviewDialog isOpen onClose={vi.fn()} />);

    expect(screen.getByTestId("tri-label-overview-dialog")).toBeInTheDocument();
    expect(ALL_LINK_TYPES).toHaveLength(14);
    for (const lt of ALL_LINK_TYPES) {
      expect(screen.getByTestId(`tri-label-row-${lt}`)).toBeInTheDocument();
    }
  });

  it("renders DE/EN downstream/upstream/neutral cells for 'satisfies'", () => {
    render(<TriLabelOverviewDialog isOpen onClose={vi.fn()} />);

    expect(screen.getByTestId("tri-label-row-satisfies-de-downstream")).toHaveTextContent(
      "erfüllt"
    );
    expect(screen.getByTestId("tri-label-row-satisfies-de-upstream")).toHaveTextContent(
      "wird erfüllt von"
    );
    expect(screen.getByTestId("tri-label-row-satisfies-en-downstream")).toHaveTextContent(
      "satisfies"
    );
    expect(screen.getByTestId("tri-label-row-satisfies-en-upstream")).toHaveTextContent(
      "is satisfied by"
    );
    expect(screen.getByTestId("tri-label-row-satisfies-neutral")).toHaveTextContent(
      "Erfüllung / Satisfaction"
    );
  });

  it("renders the newly added 'decomposes' type with its Tri-Label", () => {
    render(<TriLabelOverviewDialog isOpen onClose={vi.fn()} />);

    expect(screen.getByTestId("tri-label-row-decomposes-de-downstream")).toHaveTextContent(
      "zerlegt sich in"
    );
    expect(screen.getByTestId("tri-label-row-decomposes-en-upstream")).toHaveTextContent(
      "is decomposition of"
    );
  });

  it("calls onClose when the header close button is clicked", () => {
    const onClose = vi.fn();
    render(<TriLabelOverviewDialog isOpen onClose={onClose} />);

    fireEvent.click(screen.getByTestId("tri-label-overview-close"));
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("calls onClose when the footer done button is clicked", () => {
    const onClose = vi.fn();
    render(<TriLabelOverviewDialog isOpen onClose={onClose} />);

    fireEvent.click(screen.getByTestId("tri-label-overview-done"));
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("renders no editable form controls (read-only contract)", () => {
    render(<TriLabelOverviewDialog isOpen onClose={vi.fn()} />);

    const dialog = screen.getByTestId("tri-label-overview-dialog");
    expect(dialog.querySelectorAll("input, textarea, select")).toHaveLength(0);
  });
});
