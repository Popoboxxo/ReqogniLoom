/**
 * Regression test for BUG-07 (SYSTEMAUDIT_2026-08-18 §4).
 *
 * The diagram detail pane's "no diagram selected" placeholder used
 * `t("diagrams.selectDiagram", "Select a diagram from the list")`, but the
 * `diagrams.selectDiagram` key did not exist in either `de.json` or
 * `en.json`. i18next therefore always fell through to the literal English
 * default string passed as the second `t()` argument, regardless of the
 * active UI language (fixed by adding the key to both locale files).
 *
 * Same technique as `IcdView.i18n.test.tsx` for BUG-06: a *real* i18next
 * instance loaded with the actual locale resources (cf.
 * `frontend/src/test/ProfileSection.test.tsx`), language switched between
 * tests. The container's own smoke test (`DiagramView.smoke.test.tsx`) mocks
 * `react-i18next` with a fallback-only stub and therefore cannot catch a
 * missing-key bug like this one.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { I18nextProvider, initReactI18next } from "react-i18next";
import i18next from "i18next";
import de from "../../i18n/locales/de.json";
import en from "../../i18n/locales/en.json";

vi.mock("../../api/diagrams");
vi.mock("../../context/WorkspaceContext");

import * as diagramsModule from "../../api/diagrams";
import * as workspaceContext from "../../context/WorkspaceContext";

import DiagramView from "./DiagramView";

const i18n = i18next.createInstance();
i18n.use(initReactI18next).init({
  resources: {
    en: { translation: en },
    de: { translation: de },
  },
  lng: "de",
  fallbackLng: "en",
  interpolation: { escapeValue: false },
});

const MOCK_WORKSPACE = { id: "ws-diag-001", name: "System Design WS", preset: "standard" };

const MOCK_DIAGRAMS = [
  {
    id: "diag-001",
    workspace_id: "ws-diag-001",
    name: "System Context Diagram (C4 Level 1)",
    diagram_type: "context",
    payload_format: "mermaid",
    created_at: "2026-02-01T10:00:00Z",
    updated_at: "2026-02-01T10:00:00Z",
  },
];

function renderDiagramView(): ReturnType<typeof render> {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <I18nextProvider i18n={i18n}>
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={["/diagrams"]}>
          <Routes>
            <Route path="/diagrams" element={<DiagramView />} />
            <Route path="/diagrams/:id" element={<DiagramView />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </I18nextProvider>,
  );
}

describe("DiagramView i18n (BUG-07 regression)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(workspaceContext.useWorkspace).mockReturnValue({
      activeWorkspace: MOCK_WORKSPACE,
    } as any);
    vi.mocked(diagramsModule.diagramsApi.list).mockResolvedValue({
      results: MOCK_DIAGRAMS,
    } as any);
  });

  // See the equivalent note in IcdView.i18n.test.tsx: L-04 unified the
  // placeholder wording, so the expected strings are read from the locale
  // files instead of being duplicated here. The regression under test — a
  // missing German key letting the English `t()` default through — is still
  // caught by "DE renders and EN does not".
  const DE_PLACEHOLDER = de.diagrams.selectDiagram;
  const EN_PLACEHOLDER = en.diagrams.selectDiagram;

  it("[BUG-07] shows the German placeholder when no diagram is selected and language is de", async () => {
    expect(DE_PLACEHOLDER).not.toBe(EN_PLACEHOLDER);

    await i18n.changeLanguage("de");
    renderDiagramView();

    await waitFor(() => {
      expect(screen.getByText(DE_PLACEHOLDER)).toBeInTheDocument();
    });
    expect(screen.queryByText(EN_PLACEHOLDER)).not.toBeInTheDocument();
  });

  it("[BUG-07] shows the English placeholder when language is en", async () => {
    await i18n.changeLanguage("en");
    renderDiagramView();

    await waitFor(() => {
      expect(screen.getByText(EN_PLACEHOLDER)).toBeInTheDocument();
    });
  });
});
