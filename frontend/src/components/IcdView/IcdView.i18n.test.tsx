/**
 * Regression test for BUG-06 (SYSTEMAUDIT_2026-08-18 §4).
 *
 * The ICD detail pane's "no ICD selected" placeholder used
 * `t("icds.selectIcd", "Select an ICD from the list")`, but the
 * `icds.selectIcd` key did not exist in either `de.json` or `en.json`.
 * i18next therefore always fell through to the literal English default
 * string passed as the second `t()` argument, regardless of the active UI
 * language (fixed by adding the key to both locale files).
 *
 * Unlike the container's smoke test (`IcdView.smoke.test.tsx`), which mocks
 * `react-i18next` with a fallback-only stub, this test wires up a *real*
 * i18next instance loaded with the actual locale resources (same technique
 * as `frontend/src/test/ProfileSection.test.tsx`) and switches the active
 * language. A fallback-only mock cannot catch a missing-key bug like this
 * one — the fallback string renders "correctly" either way.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { I18nextProvider, initReactI18next } from "react-i18next";
import i18next from "i18next";
import de from "../../i18n/locales/de.json";
import en from "../../i18n/locales/en.json";

vi.mock("../../api/icds");
vi.mock("../../api/architecture");
vi.mock("../../context/WorkspaceContext");

import * as icdsModule from "../../api/icds";
import * as archModule from "../../api/architecture";
import * as workspaceContext from "../../context/WorkspaceContext";

import IcdView from "./IcdView";

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

const MOCK_WORKSPACE = { id: "ws-icd-001", name: "Interface Control WS", preset: "extended" };

const MOCK_ICD = {
  id: "icd-001",
  workspace_id: "ws-icd-001",
  name: "NavSub ↔ GroundControl RF Link",
  source_element_id: "arch-001",
  target_element_id: "arch-002",
  current_version: null,
  created_at: "2026-03-01T00:00:00Z",
};

function renderIcdView(): ReturnType<typeof render> {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <I18nextProvider i18n={i18n}>
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={["/icds"]}>
          <Routes>
            <Route path="/icds" element={<IcdView />} />
            <Route path="/icds/:id" element={<IcdView />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </I18nextProvider>,
  );
}

describe("IcdView i18n (BUG-06 regression)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(workspaceContext.useWorkspace).mockReturnValue({
      activeWorkspace: MOCK_WORKSPACE,
    } as any);
    vi.mocked(archModule.architectureApi.listAll).mockResolvedValue([]);
    vi.mocked(icdsModule.icdsApi.list).mockResolvedValue({ results: [MOCK_ICD] } as any);
  });

  // L-04 re-wrote the placeholder wording (one canonical "select … from the
  // list to view details" shape across every detail pane), which broke these
  // assertions on their hardcoded copies of it. The strings are now read from
  // the same locale files the component resolves against: the regression this
  // test exists for is "the German locale key is missing, so the English
  // `t()` default leaks through", and that is caught by asserting the DE text
  // renders *and* the EN text does not — neither of which needs the wording
  // itself to be duplicated here.
  const DE_PLACEHOLDER = de.icds.selectIcd;
  const EN_PLACEHOLDER = en.icds.selectIcd;

  it("[BUG-06] shows the German placeholder when no ICD is selected and language is de", async () => {
    // Guard the guard: identical strings would make the assertions below pass
    // for the very bug they are meant to catch.
    expect(DE_PLACEHOLDER).not.toBe(EN_PLACEHOLDER);

    await i18n.changeLanguage("de");
    renderIcdView();

    await waitFor(() => {
      expect(screen.getByText(DE_PLACEHOLDER)).toBeInTheDocument();
    });
    expect(screen.queryByText(EN_PLACEHOLDER)).not.toBeInTheDocument();
  });

  it("[BUG-06] shows the English placeholder when language is en", async () => {
    await i18n.changeLanguage("en");
    renderIcdView();

    await waitFor(() => {
      expect(screen.getByText(EN_PLACEHOLDER)).toBeInTheDocument();
    });
  });
});
