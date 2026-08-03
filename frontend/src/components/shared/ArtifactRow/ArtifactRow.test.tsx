/**
 * <ArtifactRow> unit tests — UI concept ch. 12.3.
 *
 * Covers the row's own contract (two lines, status/version placement,
 * selection accent) plus the extraction's acceptance criterion: the
 * component must be usable with a non-Goals artifact shape (an ADR) with
 * no Goals-specific props leaking into its interface.
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import deLocale from "../../../i18n/locales/de.json";
import { ArtifactRow } from "./ArtifactRow";

function resolveLocaleKey(key: string): string | undefined {
  const value = key
    .split(".")
    .reduce<unknown>(
      (node, segment) =>
        node && typeof node === "object" ? (node as Record<string, unknown>)[segment] : undefined,
      deLocale,
    );
  return typeof value === "string" ? value : undefined;
}

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, fallback?: string) => resolveLocaleKey(key) ?? fallback ?? key,
  }),
}));

describe("ArtifactRow", () => {
  it("renders id and level on the top line, title on its own line below", () => {
    render(
      <ArtifactRow
        id="SYS-REQ-001"
        level={1}
        title="Hauptfunktion des Systems"
        status="Freigegeben"
      />,
    );
    expect(screen.getByTestId("artifact-row-id")).toHaveTextContent("SYS-REQ-001");
    expect(screen.getByTestId("artifact-row-level")).toHaveTextContent("L1");
    expect(screen.getByText("Hauptfunktion des Systems")).toBeInTheDocument();
  });

  it("renders status via StatusBadge and hides version at v1", () => {
    render(<ArtifactRow id="G-1" title="Ziel" status="Entwurf" version={1} />);
    expect(screen.getByTestId("artifact-row-status")).toHaveTextContent("Entwurf");
    expect(screen.queryByTestId("version-badge")).not.toBeInTheDocument();
  });

  it("shows the version badge from v2 on", () => {
    render(<ArtifactRow id="G-1" title="Ziel" status="Freigegeben" version={3} />);
    expect(screen.getByTestId("version-badge")).toHaveTextContent("v3");
  });

  it("marks the row selected with aria-selected when onClick is provided", () => {
    render(
      <ArtifactRow
        id="G-1"
        title="Ziel"
        status="Freigegeben"
        selected
        onClick={() => {}}
      />,
    );
    expect(screen.getByTestId("artifact-row")).toHaveAttribute("aria-selected", "true");
  });

  it("calls onClick when the row is clicked", async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();
    render(<ArtifactRow id="G-1" title="Ziel" status="Entwurf" onClick={onClick} />);
    await user.click(screen.getByTestId("artifact-row"));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("does not select the row when the id's copy button is clicked", async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();
    render(<ArtifactRow id="G-1" title="Ziel" status="Entwurf" onClick={onClick} />);
    await user.click(screen.getByTestId("artifact-row-id"));
    expect(onClick).not.toHaveBeenCalled();
  });

  it("is usable with a non-Goals artifact shape (ADR) via no Goals-specific props", () => {
    // Acceptance criterion: instantiate once with ADR-shaped data. Adr
    // (frontend/src/types/index.ts) has no `level` — the prop is optional,
    // so an ADR row simply omits it instead of requiring a Goals-only field.
    const adr = {
      id: "adr-uuid-1",
      uid: "ADR-004",
      title: "Use PostgreSQL for persistence",
      status: "Approved",
      version: 2,
    };
    render(
      <ArtifactRow
        id={adr.uid}
        idFallback={adr.id}
        title={adr.title}
        status={adr.status}
        version={adr.version}
        testId="adr-row"
      />,
    );
    expect(screen.getByTestId("adr-row-id")).toHaveTextContent("ADR-004");
    expect(screen.getByTestId("adr-row-status")).toHaveTextContent("Approved");
    expect(screen.getByTestId("version-badge")).toHaveTextContent("v2");
    expect(screen.queryByTestId("adr-row-level")).not.toBeInTheDocument();
    expect(screen.getByText("Use PostgreSQL for persistence")).toBeInTheDocument();
  });

  it("[Task 5.1] omits the status badge when no status is given (ICD/Diagram list rows)", () => {
    // ICD and Diagram list-fetch types carry no `status` field — the
    // WorkflowEngine mirror only appears on the detail type, fetched
    // per-artifact. The row must render without an empty status pill.
    render(<ArtifactRow idFallback="a1b2c3d4" title="Some ICD" testId="icd-row" />);
    expect(screen.queryByTestId("icd-row-status")).not.toBeInTheDocument();
    expect(screen.getByText("Some ICD")).toBeInTheDocument();
  });
});
