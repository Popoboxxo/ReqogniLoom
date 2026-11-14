/**
 * GlossaryDetailPanel + glossary inspector mount — #1762 / M5.
 *
 * Spec §11 D8: the glossary term's trace links move out of the detail block
 * ("Verwendungen" under the definition) into the shared tabbed shell. Because
 * a term has no derivation chain (`LINKS_ROWS_ONLY`), its Links tab has to
 * list **every** type as a row — including `derives-from`/`verifies`, which
 * are spine-only rows for the other kinds — and must not render the
 * "in the spine" summary line.
 *
 * The comments tab is keyed on the backing Artifact UUID (`global_uuid`,
 * #1266/#1763), never on the term's entity id.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import type { GlossaryTerm } from "../../types";
import { GlossaryDetailPanel } from "./GlossaryDetailPanel";
import { InspectorShell } from "../shared/ArtifactInspector/InspectorShell";
import * as tracelinksModule from "../../api/tracelinks";
import * as commentsModule from "../../api/comments";
import * as glossaryModule from "../../api/glossary";

vi.mock("../../api/tracelinks");
vi.mock("../../api/comments");
vi.mock("../../api/glossary");
vi.mock("../../api/interviews", () => ({
  interviewsApi: { getProvenance: vi.fn().mockResolvedValue({ session_id: null }) },
}));
vi.mock("../../context/WorkspaceContext", () => ({
  useWorkspace: () => ({
    activeWorkspace: { id: "ws-1", name: "WS", default_link_type: "derives-from" },
  }),
}));
vi.mock("../../context/LinkTypeContext", () => ({
  useLinkTypes: () => ({
    linkTypes: [
      { key: "derives-from", definition: { label: {}, allowed_pairs: [] } },
      { key: "references", definition: { label: {}, allowed_pairs: [] } },
    ],
    creatableLinkTypes: [
      { key: "derives-from", definition: { label: {}, allowed_pairs: [] } },
    ],
    isLoading: false,
    error: null,
    reload: vi.fn(),
    definitionFor: () => undefined,
    isAllowedPair: () => true,
    labelFor: (key: string) => key,
  }),
}));

const LABELS: Record<string, string> = {
  "glossary.usages": "Verwendungen",
  "sidebar.inspector.tab.links": "Links",
  "sidebar.version.title": "Version",
  "sidebar.diff.title": "Diff",
  "comments.heading": "Kommentare",
};

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, second?: unknown): string => {
      if (LABELS[key]) return LABELS[key];
      if (typeof second === "string") return second;
      if (second && typeof second === "object" && "defaultValue" in second) {
        let text = String((second as { defaultValue: unknown }).defaultValue);
        for (const [name, value] of Object.entries(second)) {
          if (name === "defaultValue") continue;
          text = text.replaceAll(`{{${name}}}`, String(value));
        }
        return text;
      }
      return key;
    },
  }),
}));

const TERM: GlossaryTerm = {
  id: "term-a",
  global_uuid: "artifact-term-a",
  workspace_id: "ws-1",
  term: "Requirement",
  definition: "A documented need.",
  synonyms: [],
};

const TRACE_RESPONSE = {
  count: 1,
  next: null,
  previous: null,
  results: [
    {
      id: "link-1",
      link_type: "derives_from",
      // TracePanel deliberately stays on the domain-entity id (`entityId`),
      // not the backing Artifact UUID (#1763): only comments key on the UUID.
      source_id: "term-a",
      source_type: "GlossaryTerm",
      target_id: "req-1",
      target_type: "Requirement",
      target_title: "System requirement",
    },
  ],
};

function setViewport(width: number): void {
  Object.defineProperty(window, "innerWidth", {
    configurable: true,
    writable: true,
    value: width,
  });
}

function renderShell(): ReturnType<typeof render> {
  return render(
    <MemoryRouter>
      <InspectorShell
        kind="glossary"
        entityId={TERM.id}
        artifactPk={TERM.global_uuid ?? null}
      />
    </MemoryRouter>,
  );
}

describe("GlossaryDetailPanel — usages block is gone (#1762 M5)", () => {
  it("renders definition and actions, but no 'Verwendungen' block under the definition", () => {
    render(
      <GlossaryDetailPanel term={TERM} onEdit={vi.fn()} onDelete={vi.fn()} />,
    );

    expect(screen.getByTestId("glossary-detail")).toBeInTheDocument();
    expect(screen.getByText("A documented need.")).toBeInTheDocument();
    // No second trace surface in the detail block (spec §2.2 "one place").
    expect(screen.queryByText("Verwendungen")).not.toBeInTheDocument();
    expect(screen.queryByTestId("artifact-inspector")).not.toBeInTheDocument();
  });
});

describe("glossary inspector — Links tab (#1762 M5)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
    window.history.replaceState({}, "", "/glossary");
    setViewport(1440);
    vi.mocked(tracelinksModule.tracelinksApi.listForArtifact).mockResolvedValue(
      TRACE_RESPONSE as never,
    );
    vi.mocked(commentsModule.commentsApi.list).mockResolvedValue([]);
    vi.mocked(glossaryModule.glossaryApi.versions).mockResolvedValue([]);
    vi.mocked(glossaryModule.glossaryApi.diff).mockResolvedValue({
      from_version: 0,
      to_version: 1,
      changes: [],
    } as never);
  });

  it("names the Links tab 'Verwendungen' and lists derivation links as rows (no spine summary)", async () => {
    renderShell();

    const linksTab = screen.getByTestId("inspector-tab-links");
    expect(linksTab).toHaveTextContent("Verwendungen");

    fireEvent.click(linksTab);

    // rows-only: `derives-from` is a row here, not a summary line…
    await waitFor(() => {
      expect(screen.getByTestId("inspector-panel-links")).toBeVisible();
    });
    expect(await screen.findByText(/System requirement/)).toBeInTheDocument();
    // …and the "jump into the spine" line does not exist for a glossary term.
    expect(
      screen.queryByRole("button", { name: /In der Spine anzeigen/ }),
    ).not.toBeInTheDocument();
  });

  it("keys the comments tab on global_uuid, not on the entity id", async () => {
    renderShell();

    fireEvent.click(screen.getByTestId("inspector-tab-comments"));

    await waitFor(() => {
      expect(commentsModule.commentsApi.list).toHaveBeenCalledWith("artifact-term-a");
    });
    expect(commentsModule.commentsApi.list).not.toHaveBeenCalledWith("term-a");
  });
});
