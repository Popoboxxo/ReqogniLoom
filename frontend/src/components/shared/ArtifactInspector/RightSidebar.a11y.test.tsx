/**
 * RightSidebar a11y — every inspector button has a name (Plan C T-C3-3, C-L9).
 *
 * The inspector stacks VersionPanel / DiffPanel / TracePanel / CommentPanel
 * under one shell. A button without an accessible name is unusable with a
 * screen reader and is exactly the class of defect this task exists for
 * (C-L9): the trace-row button rendered only its (possibly empty) type/title
 * spans and could end up announced as nothing.
 *
 * For all three inspected kinds the test walks every rendered button and
 * asserts a non-empty accessible name (`toHaveAccessibleName()` with no
 * argument). The glossary kind is rendered through `GlossaryDetailPanel`,
 * the component that actually mounts `RightSidebar kind="glossary"`.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { I18nextProvider, initReactI18next } from "react-i18next";
import i18next from "i18next";
import de from "../../../i18n/locales/de.json";
import en from "../../../i18n/locales/en.json";
import type { GlossaryTerm } from "../../../types";
import * as requirementsModule from "../../../api/requirements";
import * as risksModule from "../../../api/risks";
import * as glossaryModule from "../../../api/glossary";
import * as diagramsModule from "../../../api/diagrams";
import * as commentsModule from "../../../api/comments";
import * as interviewsModule from "../../../api/interviews";
import * as tracelinksModule from "../../../api/tracelinks";
import * as workspaceModule from "../../../context/WorkspaceContext";
import * as linkTypeModule from "../../../context/LinkTypeContext";
import { RightSidebar } from "./RightSidebar";
import { GlossaryDetailPanel } from "../../GlossaryView/GlossaryDetailPanel";

vi.mock("../../../api/requirements");
vi.mock("../../../api/risks");
vi.mock("../../../api/glossary");
vi.mock("../../../api/diagrams");
vi.mock("../../../api/comments");
vi.mock("../../../api/interviews");
vi.mock("../../../api/tracelinks");
vi.mock("../../../context/WorkspaceContext");
vi.mock("../../../context/LinkTypeContext");

const i18n = i18next.createInstance();
void i18n.use(initReactI18next).init({
  resources: {
    en: { translation: en },
    de: { translation: de },
  },
  lng: "de",
  fallbackLng: "en",
  interpolation: { escapeValue: false },
});

const ARTIFACT_ID = "artifact-001";
const WORKSPACE = { id: "ws-a11y", name: "A11y", preset: "standard" };

const TERM: GlossaryTerm = {
  id: ARTIFACT_ID,
  workspace_id: "ws-a11y",
  term: "Anforderung",
  definition: "A documented need.",
  synonyms: [],
  version: 1,
};

/** The inspector defaults to collapsed below 1600px (#419) — force expanded. */
function forceExpanded(kind: string): void {
  Object.defineProperty(window, "innerWidth", {
    configurable: true,
    writable: true,
    value: 1920,
  });
  window.localStorage.clear();
  window.localStorage.setItem(`reqflow_inspector_collapsed_${kind}`, "false");
}

function mockVersionApis(): void {
  vi.mocked(requirementsModule.requirementsApi.versions).mockResolvedValue([
    { version: 1, label: "v1", modified_at: "2026-01-01T00:00:00Z" },
  ]);
  vi.mocked(risksModule.risksApi.versions).mockResolvedValue([
    { version: 1, label: "v1", modified_at: "2026-01-01T00:00:00Z" },
  ]);
  vi.mocked(glossaryModule.glossaryApi.versions).mockResolvedValue([
    { version: 1, label: "v1", modified_at: "2026-01-01T00:00:00Z" },
  ]);
  vi.mocked(diagramsModule.diagramsApi.versions).mockResolvedValue([]);
}

function renderInspector(kind: "glossary" | "requirement" | "risk"): void {
  forceExpanded(kind);
  const tree =
    kind === "glossary" ? (
      <GlossaryDetailPanel term={TERM} onEdit={vi.fn()} onDelete={vi.fn()} />
    ) : (
      <RightSidebar kind={kind} artifactId={ARTIFACT_ID} />
    );

  render(
    <I18nextProvider i18n={i18n}>
      <MemoryRouter>{tree}</MemoryRouter>
    </I18nextProvider>,
  );
}

/** Every rendered button must carry a non-empty accessible name. */
function expectEveryButtonNamed(): void {
  const buttons = screen.getAllByRole("button");
  expect(buttons.length).toBeGreaterThan(0);
  // `toHaveAccessibleName()` with no expected value asserts "has a name".
  buttons.forEach((button, index) => {
    expect(
      button,
      `button #${index} (${button.outerHTML.slice(0, 120)})`,
    ).toHaveAccessibleName();
  });
}

describe("RightSidebar a11y — button names (C-L9)", () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    await i18n.changeLanguage("de");

    vi.mocked(workspaceModule.useWorkspace).mockReturnValue({
      activeWorkspace: WORKSPACE,
    } as unknown as ReturnType<typeof workspaceModule.useWorkspace>);
    vi.mocked(linkTypeModule.useLinkTypes).mockReturnValue({
      // One catalog type so the filter chips render (and get name-checked).
      linkTypes: [{ key: "verifies", definition: { label: {}, allowed_pairs: [] } }],
      isLoading: false,
      error: null,
      reload: vi.fn(),
      creatableLinkTypes: [],
      definitionFor: () => undefined,
      isAllowedPair: () => true,
      labelFor: (key: string) => key,
    } as unknown as ReturnType<typeof linkTypeModule.useLinkTypes>);

    mockVersionApis();
    vi.mocked(commentsModule.commentsApi.list).mockResolvedValue([]);
    vi.mocked(interviewsModule.interviewsApi.getProvenance).mockResolvedValue({
      session_id: null,
    });
    vi.mocked(tracelinksModule.tracelinksApi.listForArtifact).mockResolvedValue({
      results: [],
    } as unknown as Awaited<
      ReturnType<typeof tracelinksModule.tracelinksApi.listForArtifact>
    >);
  });

  describe.each(["glossary", "requirement", "risk"] as const)("kind=%s", (kind) => {
    it("renders every button with a non-empty accessible name", async () => {
      renderInspector(kind);

      // Wait until the version list (and therefore the panel's own controls)
      // has rendered instead of asserting against the loading skeleton only.
      await waitFor(() => {
        expect(screen.getByTestId("version-row-1")).toBeInTheDocument();
      });
      // CommentPanel settles independently of the version list.
      await waitFor(() => {
        expect(screen.getByTestId("comment-panel-empty")).toBeInTheDocument();
      });

      expectEveryButtonNamed();
    });
  });

  it("keeps a chip named when the workspace catalog label is an empty string", async () => {
    // A workspace can save an empty label for a link type. That used to
    // render a nameless filter chip and a nameless trace-row button.
    vi.mocked(linkTypeModule.useLinkTypes).mockReturnValue({
      linkTypes: [{ key: "verifies", definition: { label: {}, allowed_pairs: [] } }],
      isLoading: false,
      error: null,
      reload: vi.fn(),
      creatableLinkTypes: [],
      definitionFor: () => undefined,
      isAllowedPair: () => true,
      labelFor: () => "",
    } as unknown as ReturnType<typeof linkTypeModule.useLinkTypes>);

    renderInspector("requirement");

    const chip = await screen.findByTestId("trace-filter-chip-verifies");
    expect(chip).toHaveAccessibleName();
    expectEveryButtonNamed();
  });

  it("keeps the trace-row button named when the other endpoint has no title", async () => {
    vi.mocked(tracelinksModule.tracelinksApi.listForArtifact).mockResolvedValue({
      results: [
        {
          id: "link-untitled",
          source_id: ARTIFACT_ID,
          target_id: "req-2",
          link_type: "verifies",
          source_title: "Inspected",
          source_type: "Requirement",
          target_title: "",
          target_type: "Requirement",
          created_at: "2026-01-17T08:00:00Z",
        },
      ],
    } as unknown as Awaited<
      ReturnType<typeof tracelinksModule.tracelinksApi.listForArtifact>
    >);

    renderInspector("requirement");

    const rowButton = await screen.findByTestId("trace-row-open-link-untitled");
    expect(rowButton).toHaveAccessibleName();
    // The localised placeholder (plus the link-type label) names the row —
    // an empty title must not leave the button nameless.
    expect(rowButton.getAttribute("aria-label")).toContain(
      de.sidebar.trace.untitled,
    );
    expectEveryButtonNamed();
  });
});
