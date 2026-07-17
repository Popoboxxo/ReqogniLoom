/**
 * REQ-162: NeedForm — change_reason support for the Extended preset.
 *
 * Regression coverage for the bug where NeedForm did not surface the
 * `change_reason` field at all, causing the backend (preset_policy_service.py,
 * `is_change_reason_required`) to reject every save with HTTP 400 once a
 * workspace uses the Extended preset.
 *
 * Verifies:
 * - The field is rendered when the active workspace preset is "extended".
 * - The field is hidden for "standard" and "minimal" presets.
 * - Save is blocked client-side (no API call) when Extended and the reason
 *   is empty.
 * - `change_reason` is included in the PATCH payload when provided.
 */

import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

// ---------------------------------------------------------------------------
// Mocks (must precede component import)
// ---------------------------------------------------------------------------

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => {
      const map: Record<string, string> = {
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
        "customFields.section": "Benutzerdefinierte Felder",
        "traceability.deriveTitleRequired": "Titel erforderlich",
        "traceability.create": "Erstellen",
        "traceability.viewAll": "Alle anzeigen",
        "traceability.deriveArchitectureElementRequired": "Architektur erforderlich",
        "nav.traceability": "Traceability",
        "req.changeReason": "Change Reason",
        "req.changeReasonPlaceholder": "Why is this being changed?",
        "req.changeReasonRequired": "Change reason is required.",
      };
      return map[key] ?? key;
    },
    i18n: { language: "de" },
  }),
}));

// Directly mock the workspace hook so each test controls the active preset
// without needing a real WorkspaceProvider + workspace fetch round-trip.
const useWorkspaceMock = vi.fn();
vi.mock("../../context/WorkspaceContext", () => ({
  useWorkspace: () => useWorkspaceMock(),
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

// Must import AFTER vi.mock
import { NeedForm } from "./NeedForm";
import { stakeholderNeedApi } from "../../api/stakeholder-need";
import type { StakeholderNeed, Workspace } from "../../types";

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
  updated_at: "2026-01-01T00:00:00Z",
  custom_fields: {},
};

function makeWorkspace(preset: "minimal" | "standard" | "extended"): Workspace {
  return {
    id: "ws-001",
    name: "WS",
    preset,
    terminology_profile: "se_mode",
    language: "en",
    is_active: true,
    closed_at: null,
    closed_by: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  } as Workspace;
}

const renderForm = (preset: "minimal" | "standard" | "extended") => {
  useWorkspaceMock.mockReturnValue({ activeWorkspace: makeWorkspace(preset) });
  return render(
    <MemoryRouter>
      <NeedForm need={MOCK_NEED} onSaved={vi.fn()} onDeleted={vi.fn()} />
    </MemoryRouter>
  );
};

describe("NeedForm — change_reason support for Extended preset (REQ-162)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows the change_reason field when the workspace preset is Extended", () => {
    renderForm("extended");
    expect(screen.getByTestId("need-change-reason-input")).toBeInTheDocument();
  });

  it("hides the change_reason field for the Standard preset", () => {
    renderForm("standard");
    expect(screen.queryByTestId("need-change-reason-input")).not.toBeInTheDocument();
  });

  it("hides the change_reason field for the Minimal preset", () => {
    renderForm("minimal");
    expect(screen.queryByTestId("need-change-reason-input")).not.toBeInTheDocument();
  });

  it("blocks save and does not call the API when Extended and change_reason is empty", async () => {
    renderForm("extended");

    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Change reason is required.");
    expect(stakeholderNeedApi.update).not.toHaveBeenCalled();
  });

  it("includes change_reason in the update payload when provided", async () => {
    renderForm("extended");

    const input = screen.getByTestId("need-change-reason-input");
    await userEvent.type(input, "Clarified wording per stakeholder review");
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => {
      expect(stakeholderNeedApi.update).toHaveBeenCalledWith(
        MOCK_NEED.id,
        expect.objectContaining({ change_reason: "Clarified wording per stakeholder review" })
      );
    });
  });
});
