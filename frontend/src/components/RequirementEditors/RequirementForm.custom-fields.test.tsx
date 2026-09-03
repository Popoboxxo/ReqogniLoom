import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";

/**
 * Issue #673 — "particularly custom fields" half of the inconsistent-reset
 * bug. `CustomFieldsEditor` seeds its internal row list from `value` once on
 * mount and never resyncs it on a prop update (by design — so mid-edit rows
 * with a transiently empty/duplicate key are not clobbered). Without a
 * `key={requirement.id}` on the mount site, switching the selected
 * requirement left CustomFieldsEditor showing (and, on the next edit,
 * splicing into the payload) the PREVIOUS requirement's stale rows.
 *
 * Unlike RequirementForm.test.tsx, this file deliberately does NOT mock
 * CustomFieldsEditor — the whole point is to exercise its real internal
 * row-list statefulness across a requirement switch.
 */

vi.mock("../../api/requirements", () => ({
  requirementsApi: {
    update: vi.fn().mockResolvedValue({}),
  },
}));

vi.mock("../../api/client", () => ({
  extractErrorMessage: (err: unknown) =>
    (err as { error?: { message?: string } })?.error?.message ?? "Save failed.",
}));

vi.mock("../WorkflowStatusEditor", () => ({
  WorkflowStatusEditor: () => <div data-testid="workflow-status-editor-stub" />,
}));

vi.mock("../../context/EntityTypeContext", () => ({
  useEntityType: () => ({
    isFieldVisible: () => true,
    isFieldRequired: () => false,
  }),
}));

vi.mock("../../context/WorkspaceContext", () => ({
  useWorkspace: () => ({ activeWorkspace: { preset: "standard" } }),
}));

// R2/T1 (systemaudit 2026-09-02): RequirementForm now reads roles via
// useHasRole/useAuth to gate Save — this file is about custom-field reset
// behavior, not role gating, so it stays on an editor session (role gating
// itself is covered by RequirementForm.test.tsx's own role-gate block).
vi.mock("../../context/AuthContext", () => ({
  useAuth: () => ({ roles: ["editor"] }),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (k: string, d?: string) => d ?? k }),
}));

vi.mock("./MarkdownPreview", () => ({
  MarkdownPreview: ({
    value,
    onChange,
  }: {
    value: string;
    onChange: (v: string) => void;
  }) => (
    <textarea
      data-testid="req-description-input"
      value={value}
      onChange={(e) => onChange(e.target.value)}
    />
  ),
}));

// ArtifactCustomFields is a separate, independently-fetched component (own
// artifactId-keyed effect, unrelated to this bug) — stubbed to avoid an
// unrelated network call.
vi.mock("../shared/ArtifactCustomFields", () => ({
  ArtifactCustomFields: () => <div data-testid="artifact-custom-fields" />,
}));
vi.mock("../shared/VersionBadge", () => ({
  VersionBadge: () => <span data-testid="version-badge" />,
}));

import { RequirementForm } from "./RequirementForm";
import { requirementsApi } from "../../api/requirements";
import type { Requirement } from "../../types";

const reqA = {
  id: "req-a",
  artifact_id: "art-a",
  title: "Requirement A",
  description: "desc a",
  category: "",
  status: "draft",
  change_reason: "",
  type: "SyReq",
  complexity_fibonacci: 1,
  verification_method: "",
  custom_fields: { owner: "team-a" },
  suspect: false,
  uid: null,
  version: 1,
} as unknown as Requirement;

const reqB = {
  ...reqA,
  id: "req-b",
  artifact_id: "art-b",
  title: "Requirement B",
  description: "desc b",
  change_reason: "",
  // Deliberately a DIFFERENT key than reqA's ("owner") — if a stale row list
  // from reqA ever leaked through, the saved payload would still contain
  // "owner" (never "region"), and it would land with reqA's own stale
  // value if the two keys happened to coincide by accident.
  custom_fields: { region: "emea" },
} as unknown as Requirement;

function renderForm(requirement: Requirement, onSaved = vi.fn()) {
  return render(
    <RequirementForm
      requirement={requirement}
      upstreamLinks={[]}
      downstreamLinks={[]}
      linkedTitles={{}}
      linkedRoutes={{}}
      requirements={[]}
      workspaceId="ws-1"
      onSaved={onSaved}
    />
  );
}

describe("RequirementForm — CustomFieldsEditor resets on entity switch (#673)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows the newly-selected requirement's own custom fields, not the previous one's edited draft, after switching", () => {
    const { rerender } = renderForm(reqA);

    expect(screen.getByTestId("custom-field-key")).toHaveValue("owner");
    expect(screen.getByTestId("custom-field-value")).toHaveValue("team-a");

    // User edits the value for requirement A, without saving.
    fireEvent.change(screen.getByTestId("custom-field-value"), {
      target: { value: "team-a-edited" },
    });
    expect(screen.getByTestId("custom-field-value")).toHaveValue("team-a-edited");

    // Switches to requirement B.
    rerender(
      <RequirementForm
        requirement={reqB}
        upstreamLinks={[]}
        downstreamLinks={[]}
        linkedTitles={{}}
        linkedRoutes={{}}
        requirements={[]}
        workspaceId="ws-1"
        onSaved={vi.fn()}
      />
    );

    // Must show B's own custom fields, not A's unsaved draft.
    expect(screen.getByTestId("custom-field-key")).toHaveValue("region");
    expect(screen.getByTestId("custom-field-value")).toHaveValue("emea");
  });

  it("does not splice the previous requirement's stale custom field rows into a save made after switching", async () => {
    const { rerender } = renderForm(reqA);

    fireEvent.change(screen.getByTestId("custom-field-value"), {
      target: { value: "team-a-edited" },
    });

    rerender(
      <RequirementForm
        requirement={reqB}
        upstreamLinks={[]}
        downstreamLinks={[]}
        linkedTitles={{}}
        linkedRoutes={{}}
        requirements={[]}
        workspaceId="ws-1"
        onSaved={vi.fn()}
      />
    );

    // Touch a field on B so CustomFieldsEditor's onChange fires again —
    // this is the exact moment a stale row list would leak into the payload.
    fireEvent.change(screen.getByTestId("custom-field-value"), {
      target: { value: "team-b-edited" },
    });

    fireEvent.click(screen.getByTestId("save-btn"));
    await waitFor(() => expect(requirementsApi.update).toHaveBeenCalled());

    const [savedId, payload] = (requirementsApi.update as ReturnType<typeof vi.fn>)
      .mock.calls[0];
    expect(savedId).toBe("req-b");
    // B's own key ("region") carries the edit; A's stale key ("owner") must
    // not have leaked through.
    expect(payload).toMatchObject({
      custom_fields: { region: "team-b-edited" },
    });
    expect(
      (payload as { custom_fields: Record<string, unknown> }).custom_fields
    ).not.toHaveProperty("owner");
  });
});
