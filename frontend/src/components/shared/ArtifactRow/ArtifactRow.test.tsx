/**
 * <ArtifactRow> unit tests — UI concept ch. 12.3.
 *
 * Covers the row's own contract (two lines, status/version placement,
 * selection accent) plus the extraction's acceptance criterion: the
 * component must be usable with a non-Goals artifact shape (an ADR) with
 * no Goals-specific props leaking into its interface.
 *
 * The identity line is `<IdChip>` since issue #1094, so the row's copy
 * affordance is covered here too: the row SHOWS the readable uid and COPIES the
 * system id.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import deLocale from "../../../i18n/locales/de.json";
import { ArtifactRow } from "./ArtifactRow";
import {
  READABLE_IDS_STORAGE_KEY,
  setReadableIdsVisible,
} from "../../../hooks/useReadableIdsVisible";

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
    // Interpolation-aware, like the shared helper: `<IdChip>` builds its copy
    // label from `t(key, { kind })`, and an options OBJECT returned as a React
    // child would throw.
    t: (key: string, options?: Record<string, unknown>) => {
      const { defaultValue, ...interpolation } = options ?? {};
      const resolved =
        resolveLocaleKey(key) ??
        (typeof defaultValue === "string" ? defaultValue : key);
      return Object.entries(interpolation).reduce(
        (acc, [name, value]) => acc.replace(`{{${name}}}`, String(value)),
        resolved
      );
    },
    i18n: { language: "de" },
  }),
}));

const writeText = vi.fn();

beforeEach(() => {
  writeText.mockReset();
  writeText.mockResolvedValue(undefined);
  Object.defineProperty(navigator, "clipboard", {
    value: { writeText },
    configurable: true,
  });
  setReadableIdsVisible(true);
});

afterEach(() => {
  window.localStorage?.removeItem?.(READABLE_IDS_STORAGE_KEY);
  setReadableIdsVisible(true);
});

describe("ArtifactRow", () => {
  it("leads with the title and shows the labelled identifier below (issue #807)", () => {
    render(
      <ArtifactRow
        id="SYS-REQ-001"
        level={1}
        title="Hauptfunktion des Systems"
        status="Freigegeben"
      />,
    );
    const title = screen.getByText("Hauptfunktion des Systems");
    const id = screen.getByTestId("artifact-row-id");
    // The title must come *before* the identifier in document order: the
    // artifact's name leads, the short reference follows.
    expect(
      title.compareDocumentPosition(id) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(id).toHaveTextContent("SYS-REQ-001");
    expect(screen.getByTestId("artifact-row-level")).toHaveTextContent("L1");
    // Issue #807: the identifier is visibly labelled ("ID") so a short hash
    // never reads as the artifact's name.
    expect(screen.getByText("ID")).toBeInTheDocument();
  });

  it("omits the identifier label when idLabel is null (issue #807 opt-out)", () => {
    render(<ArtifactRow id="X-1" title="Ohne Label" idLabel={null} />);
    expect(screen.queryByText("ID")).not.toBeInTheDocument();
    expect(screen.getByTestId("artifact-row-id")).toHaveTextContent("X-1");
  });

  it("renders provided SE attributes and skips empty ones (issue #804)", () => {
    render(
      <ArtifactRow
        id="SYS-REQ-001"
        title="Anforderung mit SE-Attributen"
        attributes={[
          { label: "Kategorie", value: "functional" },
          { label: "V-Modell-Ebene", value: "L1 System" },
          { label: "Verifikationsmethode", value: null },
        ]}
      />,
    );
    const attrs = screen.getByTestId("artifact-row-attributes");
    expect(attrs).toHaveTextContent("Kategorie");
    expect(attrs).toHaveTextContent("functional");
    expect(attrs).toHaveTextContent("L1 System");
    // The null-valued attribute is dropped, not rendered as an empty chip.
    expect(attrs).not.toHaveTextContent("Verifikationsmethode");
    expect(screen.getAllByTestId("artifact-row-attribute")).toHaveLength(2);
  });

  it("renders no attribute line when every value is empty (issue #804)", () => {
    render(
      <ArtifactRow
        id="X-1"
        title="Leer"
        attributes={[{ label: "Kategorie", value: "" }]}
      />,
    );
    expect(screen.queryByTestId("artifact-row-attributes")).not.toBeInTheDocument();
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

describe("ArtifactRow identity chip (issue #1094)", () => {
  const UUID = "12345678-1234-4abc-8def-1234567890ab";

  // `fireEvent`, not `userEvent`: `userEvent.setup()` installs its own
  // `navigator.clipboard` stub, which would replace the `writeText` spy the
  // assertions below read.
  it("shows the readable uid but copies the system id", async () => {
    render(<ArtifactRow id="ARCH-001" systemId={UUID} title="Element" testId="row" />);

    expect(screen.getByTestId("row-id-value")).toHaveTextContent("ARCH-001");

    fireEvent.click(screen.getByTestId("row-id-copy"));

    expect(writeText).toHaveBeenCalledWith(UUID);
    await waitFor(() =>
      expect(screen.getByTestId("row-id-status")).toHaveTextContent("UUID kopiert")
    );
  });

  it("falls back to copying the uid, and says so, when no system id was passed", async () => {
    // A call site that has not been migrated to pass `systemId` yet must not
    // put an empty string on the clipboard; the announcement states which
    // identity actually made it there.
    render(<ArtifactRow id="ARCH-001" title="Element" testId="row" />);

    fireEvent.click(screen.getByTestId("row-id-copy"));

    expect(writeText).toHaveBeenCalledWith("ARCH-001");
    await waitFor(() =>
      expect(screen.getByTestId("row-id-status")).toHaveTextContent(
        "UID kopiert, weil keine System-ID vorhanden"
      )
    );
  });

  it("does not select the row when the copy control is used", () => {
    const onClick = vi.fn();
    render(
      <ArtifactRow
        id="ARCH-001"
        systemId={UUID}
        title="Element"
        onClick={onClick}
        testId="row"
      />
    );

    fireEvent.click(screen.getByTestId("row-id-copy"));

    expect(writeText).toHaveBeenCalledWith(UUID);
    expect(onClick).not.toHaveBeenCalled();
  });

  it("hides the readable identifier and its label when the preference is off", () => {
    setReadableIdsVisible(false);
    render(
      <ArtifactRow id="ARCH-001" systemId={UUID} title="Element" testId="row" />
    );

    expect(screen.queryByTestId("row-id-value")).not.toBeInTheDocument();
    // Nothing is left for the "ID" label to label, so it goes with it.
    expect(screen.queryByText("ID")).not.toBeInTheDocument();
    // Copying the system id is unaffected by the display preference.
    expect(screen.getByTestId("row-id-copy")).toBeInTheDocument();
  });

  it("keeps the identifier visible again when the preference is turned back on", () => {
    const { rerender } = render(
      <ArtifactRow id="ARCH-001" systemId={UUID} title="Element" testId="row" />
    );
    expect(screen.getByTestId("row-id-value")).toHaveTextContent("ARCH-001");

    setReadableIdsVisible(false);
    rerender(<ArtifactRow id="ARCH-001" systemId={UUID} title="Element" testId="row" />);
    expect(screen.queryByTestId("row-id-value")).not.toBeInTheDocument();
  });

  it("keeps the label opt-out working independently of the preference", () => {
    render(<ArtifactRow id="X-1" title="Ohne Label" idLabel={null} testId="row" />);
    expect(screen.queryByText("ID")).not.toBeInTheDocument();
    expect(screen.getByTestId("row-id-value")).toHaveTextContent("X-1");
  });
});
