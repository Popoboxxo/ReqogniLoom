import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

/**
 * Regression coverage for systemaudit 2026-08-29 Bug 4 — the "Supersede
 * durch..." button was only gated on `candidateSuccessors.length === 0`, not
 * on the ADR's own workflow status. The only defined transition into
 * 'Superseded' is 'Approved' -> 'Superseded' (backend/workflow/
 * definition_store.py::_adr_transitions), so a Draft/In-Review ADR let the
 * user fill in the whole supersede form only to hit a generic
 * "Transition not allowed" error from the backend at submit time.
 *
 * Moved verbatim from the deleted `AdrForm.test.tsx` (Task 21, ADR rollout
 * wave) — the ADR-Supersede-Flow itself moved unchanged into its own
 * component, `AdrSupersedePanel`, alongside `AdrArtifactForm`.
 */

vi.mock("../../api/adrs", () => ({
  adrsApi: {
    update: vi.fn().mockResolvedValue({}),
    delete: vi.fn().mockResolvedValue(undefined),
    supersede: vi.fn().mockResolvedValue({}),
  },
}));

vi.mock("../../api/tracelinks", () => ({
  tracelinksApi: {
    listForArtifact: vi.fn().mockResolvedValue({ results: [], count: 0 }),
  },
}));

vi.mock("../../context/WorkspaceContext", () => ({
  useWorkspace: () => ({ activeWorkspace: { id: "ws-1", preset: "standard" } }),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (k: string, d?: string) => d ?? k }),
}));

import { AdrSupersedePanel } from "./AdrSupersedePanel";
import type { Adr } from "../../types";

const baseAdr: Adr = {
  id: "adr-1",
  artifact_id: "art-adr-1",
  uid: "ADR-001",
  title: "Use PostgreSQL",
  description: "",
  context: "",
  consequences: "",
  status: "Approved",
  version: 1,
} as Adr;

const otherAdr: Adr = {
  ...baseAdr,
  id: "adr-2",
  uid: "ADR-002",
  title: "Use Redis",
};

describe("AdrSupersedePanel — supersede button workflow-status gating (systemaudit Bug 4)", () => {
  it("enables the supersede button when the ADR is Approved and candidates exist", () => {
    render(
      <AdrSupersedePanel
        adr={{ ...baseAdr, status: "Approved" }}
        otherAdrs={[otherAdr]}
        onSaved={vi.fn()}
      />
    );

    expect(screen.getByTestId("adr-supersede-btn")).not.toBeDisabled();
  });

  it("disables the supersede button when the ADR is Draft, even with candidates", () => {
    render(
      <AdrSupersedePanel
        adr={{ ...baseAdr, status: "Draft" }}
        otherAdrs={[otherAdr]}
        onSaved={vi.fn()}
      />
    );

    const btn = screen.getByTestId("adr-supersede-btn");
    expect(btn).toBeDisabled();
    expect(btn).toHaveAttribute(
      "title",
      'Supersede ist nur für ADRs im Status "Approved" möglich.'
    );
  });

  it("disables the supersede button when the ADR is In Review", () => {
    render(
      <AdrSupersedePanel
        adr={{ ...baseAdr, status: "In Review" }}
        otherAdrs={[otherAdr]}
        onSaved={vi.fn()}
      />
    );

    expect(screen.getByTestId("adr-supersede-btn")).toBeDisabled();
  });
});

// -----------------------------------------------------------------------
// UI-LOW-3 (Systemaudit, LOW finding): the status badge stayed "Approved"
// after a successful supersede until a full page reload. Root cause: the
// caller only invalidated the query cache and waited on a background
// refetch to reflect the new status; `onSaved` now forwards the mutation's
// own response so the caller can update its state/cache synchronously
// instead (see useAdrData.refresh's doc comment).
// -----------------------------------------------------------------------
describe("AdrSupersedePanel — supersede forwards the fresh ADR to onSaved (UI-LOW-3)", () => {
  it("passes the API response through onSaved after a successful supersede", async () => {
    const user = userEvent.setup();
    const onSaved = vi.fn();
    const superseded = { ...baseAdr, status: "Superseded" };
    const { adrsApi } = await import("../../api/adrs");
    vi.mocked(adrsApi.supersede).mockResolvedValueOnce(superseded as any);

    render(
      <AdrSupersedePanel
        adr={{ ...baseAdr, status: "Approved" }}
        otherAdrs={[otherAdr]}
        onSaved={onSaved}
      />
    );

    await user.click(screen.getByTestId("adr-supersede-btn"));
    await user.selectOptions(screen.getByTestId("adr-supersede-target-select"), "adr-2");
    await user.click(screen.getByTestId("adr-supersede-confirm-btn"));

    await waitFor(() => {
      expect(onSaved).toHaveBeenCalledWith(superseded);
    });
  });
});
