/**
 * Unit tests for TriLabelOverviewDialog — read-only Tri-Label admin overview.
 *
 * Verifies:
 *   - Renders nothing when isOpen is false
 *   - Renders a row for each of the eight built-in link types when open
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
import { FALLBACK_TRI_LABELS } from "../../constants/traceLinkLabels";

const BUILTIN_LINK_TYPES = Object.keys(FALLBACK_TRI_LABELS);

describe("TriLabelOverviewDialog", () => {
  it("renders nothing when isOpen is false", () => {
    const { container } = render(
      <TriLabelOverviewDialog isOpen={false} onClose={vi.fn()} />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("renders the dialog with a row for each of the eight built-in link types when open", () => {
    render(<TriLabelOverviewDialog isOpen onClose={vi.fn()} />);

    expect(screen.getByTestId("tri-label-overview-dialog")).toBeInTheDocument();
    expect(BUILTIN_LINK_TYPES).toHaveLength(8);
    for (const lt of BUILTIN_LINK_TYPES) {
      expect(screen.getByTestId(`tri-label-row-${lt}`)).toBeInTheDocument();
    }
  });

  it("renders DE/EN downstream/upstream/neutral cells for 'verifies'", () => {
    render(<TriLabelOverviewDialog isOpen onClose={vi.fn()} />);

    expect(screen.getByTestId("tri-label-row-verifies-de-downstream")).toHaveTextContent(
      "verifiziert"
    );
    expect(screen.getByTestId("tri-label-row-verifies-de-upstream")).toHaveTextContent(
      "wird verifiziert von"
    );
    expect(screen.getByTestId("tri-label-row-verifies-en-downstream")).toHaveTextContent(
      "verifies"
    );
    expect(screen.getByTestId("tri-label-row-verifies-en-upstream")).toHaveTextContent(
      "is verified by"
    );
    expect(screen.getByTestId("tri-label-row-verifies-neutral")).toHaveTextContent(
      "Verifikation / Verification"
    );
  });

  it("renders the 'decomposes' type with its Tri-Label", () => {
    render(<TriLabelOverviewDialog isOpen onClose={vi.fn()} />);

    expect(screen.getByTestId("tri-label-row-decomposes-de-downstream")).toHaveTextContent(
      "zerlegt sich in"
    );
    expect(screen.getByTestId("tri-label-row-decomposes-en-upstream")).toHaveTextContent(
      "is part of"
    );
  });

  it("calls onClose when the header close button is clicked", () => {
    const onClose = vi.fn();
    render(<TriLabelOverviewDialog isOpen onClose={onClose} />);

    fireEvent.click(screen.getByTestId("tri-label-overview-dialog-close"));
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
