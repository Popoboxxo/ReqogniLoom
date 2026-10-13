/**
 * IcdLinkedElements.test.tsx — #1268 ICD detail linked-elements panel.
 *
 * Verifies both directions are rendered from the trace-link surface, and that
 * the counterpart is resolved from the API's title/type enrichment.
 */
import { render, screen } from "@testing-library/react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import { IcdLinkedElements } from "./IcdLinkedElements";
import { tracelinksApi } from "../../api/tracelinks";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, fallback?: string) => fallback ?? key,
  }),
}));

vi.mock("../../api/tracelinks");

const ICD_ID = "icd-001";
const WS_ID = "ws-001";

function renderPanel() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <IcdLinkedElements icdId={ICD_ID} workspaceId={WS_ID} />
    </QueryClientProvider>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("IcdLinkedElements (#1268)", () => {
  it("renders incoming and outgoing links in both directions", async () => {
    vi.mocked(tracelinksApi.listForArtifact).mockResolvedValue({
      count: 2,
      next: null,
      previous: null,
      results: [
        {
          // ArchitectureElement references the ICD (incoming).
          id: "link-1",
          source_id: "arch-artifact-1",
          target_id: ICD_ID,
          link_type: "references",
          version: 1,
          created_at: "2026-01-01T00:00:00Z",
          source_title: "Power Bus",
          source_type: "ArchitectureElement",
          target_title: "Power Bus ICD",
          target_type: "Icd",
        },
        {
          // The ICD references a Requirement (outgoing).
          id: "link-2",
          source_id: ICD_ID,
          target_id: "req-artifact-1",
          link_type: "references",
          version: 1,
          created_at: "2026-01-01T00:00:00Z",
          source_title: "Power Bus ICD",
          source_type: "Icd",
          target_title: "Provide 28V",
          target_type: "Requirement",
        },
      ],
    });

    renderPanel();

    const incoming = await screen.findByTestId("icd-linked-incoming");
    expect(incoming.textContent).toContain("Power Bus");
    expect(incoming.textContent).toContain("references");

    const outgoing = screen.getByTestId("icd-linked-outgoing");
    expect(outgoing.textContent).toContain("Provide 28V");
  });

  it("shows the empty state when no links exist", async () => {
    vi.mocked(tracelinksApi.listForArtifact).mockResolvedValue({
      count: 0,
      next: null,
      previous: null,
      results: [],
    });

    renderPanel();

    expect(await screen.findByTestId("icd-linked-incoming-empty")).toBeInTheDocument();
    expect(screen.getByTestId("icd-linked-outgoing-empty")).toBeInTheDocument();
  });
});
