/**
 * REQ-008: NeedForm — AI derivation feedback visibility tests.
 *
 * Verifies that the AI-derive status display:
 * - Shows errors with role="alert" and danger color (not muted)
 * - Shows info/success with role="status" and normal text color
 * - Uses data-testid="need-derive-status" for test selection
 */

import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// ---------------------------------------------------------------------------
// Mock API and context before component import
// ---------------------------------------------------------------------------

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => {
      const map: Record<string, string> = {
        "needs.deriveStarting": "KI-Ableitung wird gestartet...",
        "needs.deriveStarted": `Task gestartet: ${opts?.taskId ?? ""}. Warte...`,
        "needs.deriveSuccess": "Ableitung erfolgreich!",
        "needs.deriveFailed": "Ableitung fehlgeschlagen.",
        "actions.deriving": "Leitet ab...",
        "actions.derive": "Ableiten",
        "tracelinks.panelTitle": "Trace Links",
        "actions.newLink": "Neuen Link erstellen",
        "actions.showAll": "Alle anzeigen",
        "actions.delete": "Löschen",
        "actions.save": "Speichern",
        "actions.saving": "Speichert...",
        "actions.cancel": "Abbrechen",
        "actions.deleteConfirmPrompt": "Löschen?",
        "actions.deleting": "Löschen...",
        "actions.confirmDelete": "Ja, löschen",
        "editor.title": "Titel",
        "editor.description": "Beschreibung",
        "editor.workflowState": "Status",
        "editor.category": "Kategorie",
        "editor.moscowPriority": "Priorität",
        "needs.selectNeed": "Bedarf wählen",
        "needs.priorityNone": "Keine",
        "needs.saveFailed": "Speichern fehlgeschlagen.",
        "needs.deleteFailed": "Löschen fehlgeschlagen.",
        "tracelinks.upstream": "Upstream",
        "tracelinks.downstream": "Downstream",
        "tracelinks.empty": "Keine Links.",
        "loading": "Lädt...",
        "customFields.section": "Benutzerdefinierte Felder",
        "traceability.deriveTitleRequired": "Titel erforderlich",
        "traceability.create": "Erstellen",
        "traceability.viewAll": "Alle anzeigen",
        "traceability.deriveArchitectureElementRequired": "Architektur erforderlich",
        "nav.traceability": "Traceability",
      };
      return map[key] ?? key;
    },
    i18n: { language: "de" },
  }),
}));

vi.mock("../../api/client", () => ({
  getList: vi.fn().mockResolvedValue({ results: [], count: 0 }),
  extractErrorMessage: vi.fn().mockReturnValue("Error"),
  setAuthToken: vi.fn(),
  setUnauthorizedHandler: vi.fn(),
  apiClient: {
    get: vi.fn().mockResolvedValue({}),
    post: vi.fn().mockResolvedValue({}),
    put: vi.fn().mockResolvedValue({}),
    patch: vi.fn().mockResolvedValue({}),
    delete: vi.fn().mockResolvedValue(undefined),
  },
}));

vi.mock("../../api/stakeholder-need", () => ({
  stakeholderNeedApi: {
    update: vi.fn().mockResolvedValue({}),
    delete: vi.fn().mockResolvedValue(undefined),
    deriveRequirements: vi.fn(),
  },
}));

vi.mock("../../api/requirements", () => ({
  requirementsApi: {
    create: vi.fn().mockResolvedValue({ id: "req-new" }),
  },
}));

vi.mock("../../api/architecture", () => ({
  architectureApi: {
    listAll: vi.fn().mockResolvedValue([]),
  },
}));

vi.mock("../../api/tracelinks", () => ({
  tracelinksApi: {
    listForArtifact: vi.fn().mockResolvedValue({ results: [], count: 0 }),
    create: vi.fn().mockResolvedValue({}),
    delete: vi.fn().mockResolvedValue(undefined),
  },
}));

vi.mock("../../api/artifactRefs", () => ({
  resolveArtifactRef: vi.fn().mockResolvedValue({ title: "ref", route: "" }),
}));

vi.mock("../../api/workspaces", () => ({
  workspacesApi: {
    list: vi.fn().mockResolvedValue({ results: [], count: 0 }),
    get: vi.fn().mockResolvedValue(null),
  },
}));

vi.mock("../../api/attribute-visibility", () => ({
  attributeVisibilityApi: {
    list: vi.fn().mockResolvedValue([]),
  },
}));

// Must import AFTER vi.mock
import { NeedForm } from "./NeedForm";
import { stakeholderNeedApi } from "../../api/stakeholder-need";
import { AuthProvider } from "../../context/AuthContext";
import { WorkspaceProvider } from "../../context/WorkspaceContext";
import type { StakeholderNeed } from "../../types";

// ---------------------------------------------------------------------------
// Mock data
// ---------------------------------------------------------------------------

const MOCK_NEED: StakeholderNeed = {
  id: "need-001",
  workspace_id: "ws-001",
  artifact_id: "art-001",
  title: "Als Nutzer möchte ich ...",
  description: "",
  category: "",
  status: "draft",
  moscow_priority: null,
  uid: "SN-001",
  suspect: false,
  version: 1,
  created_at: "2026-01-01T00:00:00Z",
  modified_at: "2026-01-01T00:00:00Z",
  custom_fields: {},
};

const renderForm = (onNeedsChanged?: () => void) => {
  sessionStorage.setItem("reqflow_token", "test-token");
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <AuthProvider>
          <WorkspaceProvider>
            <NeedForm
              need={MOCK_NEED}
              onSaved={vi.fn()}
              onDeleted={vi.fn()}
              onNeedsChanged={onNeedsChanged}
            />
          </WorkspaceProvider>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>
  );
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("NeedForm — AI derivation feedback (REQ-008)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
  });

  it("shows error message with role=alert when AI derive fails (REQ-008 B1)", async () => {
    vi.mocked(stakeholderNeedApi.deriveRequirements).mockRejectedValue({
      error: { message: "KI nicht verfügbar" },
    });

    renderForm();

    // The ✨ Ableiten button is rendered by TraceLinkPanel when onDerive is provided
    const deriveBtn = await screen.findByRole("button", { name: /Ableiten/i });
    await userEvent.click(deriveBtn);

    // Status must appear with role="alert" for errors (not muted role=status)
    const status = await screen.findByTestId("need-derive-status");
    expect(status).toBeInTheDocument();
    expect(status).toHaveAttribute("role", "alert");
    expect(status.textContent).toContain("KI nicht verfügbar");
  });

  it("shows status message with role=status while AI derive is loading (REQ-008 B1)", async () => {
    // Never resolves — stays in loading state
    vi.mocked(stakeholderNeedApi.deriveRequirements).mockReturnValue(
      new Promise(() => {})
    );

    renderForm();

    const deriveBtn = await screen.findByRole("button", { name: /Ableiten/i });
    await userEvent.click(deriveBtn);

    await waitFor(() => {
      const status = screen.getByTestId("need-derive-status");
      expect(status).toHaveAttribute("role", "status");
      expect(status.textContent).toContain("KI-Ableitung wird gestartet");
    });
  });
});
