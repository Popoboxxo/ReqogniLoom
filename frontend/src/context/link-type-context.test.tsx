import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";

import { LinkTypeProvider, useLinkTypes } from "./LinkTypeContext";
import { linkTypesApi } from "../api/link-types";

vi.mock("../api/link-types", () => ({
  linkTypesApi: { listForWorkspace: vi.fn() },
}));

vi.mock("./WorkspaceContext", () => ({
  useWorkspace: () => ({ activeWorkspace: { id: "ws-1" } }),
}));

const verifies = {
  id: "1",
  workspace_id: "ws-1",
  key: "verifies",
  definition: {
    label: {
      de: { downstream: "verifiziert", upstream: "wird verifiziert von", neutral: "Verifikation" },
      en: { downstream: "verifies", upstream: "is verified by", neutral: "Verification" },
    },
    allowed_pairs: [{ source_type: "TestCase", target_type: "Requirement" }],
    coverage_relevant: true,
    suspect_rule: "target_change_flags_source" as const,
    impact_weight: 1,
    manual_creatable: true,
    system_owned: false,
    active: true,
    built_in: true,
  },
  is_customized: false,
  source_global_id: null,
  version: 1,
};

const references = {
  ...verifies,
  id: "2",
  key: "references",
  definition: {
    ...verifies.definition,
    allowed_pairs: [{ source_type: "*", target_type: "Diagram" }],
    coverage_relevant: false,
    suspect_rule: "none" as const,
  },
};

function Probe() {
  const { linkTypes, isLoading, isAllowedPair, labelFor } = useLinkTypes();
  if (isLoading) return <div>loading</div>;
  return (
    <div>
      <span data-testid="count">{linkTypes.length}</span>
      <span data-testid="ok">{String(isAllowedPair("verifies", "TestCase", "Requirement"))}</span>
      <span data-testid="bad">{String(isAllowedPair("verifies", "Risk", "Requirement"))}</span>
      <span data-testid="wild">{String(isAllowedPair("references", "Risk", "Diagram"))}</span>
      <span data-testid="sub">{String(isAllowedPair("verifies", "TestCase:unit", "Requirement"))}</span>
      <span data-testid="unknown">{String(isAllowedPair("nope", "TestCase", "Requirement"))}</span>
      {/* Caller-supplied "*" (e.g. CreateTraceLinkDialog before a target is
          picked yet) must match ANY real backend value on that side — not
          just a backend pair's own literal "*". */}
      <span data-testid="callerTargetWild">{String(isAllowedPair("verifies", "TestCase", "*"))}</span>
      <span data-testid="callerSourceWild">{String(isAllowedPair("verifies", "*", "Requirement"))}</span>
      {/* A caller-side "*" still can't rescue a genuinely wrong source. */}
      <span data-testid="callerTargetWildBadSource">{String(isAllowedPair("verifies", "Risk", "*"))}</span>
      <span data-testid="label">{labelFor("verifies", "de", "neutral")}</span>
      <span data-testid="fallback">{labelFor("nope", "de", "neutral")}</span>
    </div>
  );
}

describe("LinkTypeContext", () => {
  beforeEach(() => vi.clearAllMocks());

  it("loads the catalog for the active workspace", async () => {
    vi.mocked(linkTypesApi.listForWorkspace).mockResolvedValue([verifies, references]);
    render(
      <LinkTypeProvider>
        <Probe />
      </LinkTypeProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("count")).toHaveTextContent("2"));
  });

  it("matches allowed pairs, wildcards and sub-typed artifact types", async () => {
    vi.mocked(linkTypesApi.listForWorkspace).mockResolvedValue([verifies, references]);
    render(
      <LinkTypeProvider>
        <Probe />
      </LinkTypeProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("ok")).toHaveTextContent("true"));
    expect(screen.getByTestId("bad")).toHaveTextContent("false");
    expect(screen.getByTestId("wild")).toHaveTextContent("true");
    expect(screen.getByTestId("sub")).toHaveTextContent("true");
  });

  // Regression (Task 23 review finding): before Task 23's dialog had picked
  // a target, it queries isAllowedPair(key, sourceType, "*") — a
  // caller-supplied "*" must act as a real wildcard, not just a backend
  // pair's own "*", or every normal (non-wildcard-target) type would
  // spuriously reject with no target chosen yet.
  it("treats a caller-supplied '*' as a wildcard on either side, not just the backend pair's own", async () => {
    vi.mocked(linkTypesApi.listForWorkspace).mockResolvedValue([verifies, references]);
    render(
      <LinkTypeProvider>
        <Probe />
      </LinkTypeProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("callerTargetWild")).toHaveTextContent("true"));
    expect(screen.getByTestId("callerSourceWild")).toHaveTextContent("true");
    // Still rejects when the concrete side genuinely doesn't match.
    expect(screen.getByTestId("callerTargetWildBadSource")).toHaveTextContent("false");
  });

  it("rejects an unknown key rather than defaulting to permissive", async () => {
    vi.mocked(linkTypesApi.listForWorkspace).mockResolvedValue([verifies]);
    render(
      <LinkTypeProvider>
        <Probe />
      </LinkTypeProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("unknown")).toHaveTextContent("false"));
  });

  it("labels from the catalog and falls back to the raw key", async () => {
    vi.mocked(linkTypesApi.listForWorkspace).mockResolvedValue([verifies]);
    render(
      <LinkTypeProvider>
        <Probe />
      </LinkTypeProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("label")).toHaveTextContent("Verifikation"));
    expect(screen.getByTestId("fallback")).toHaveTextContent("nope");
  });

  it("surfaces a load failure without crashing the tree", async () => {
    vi.mocked(linkTypesApi.listForWorkspace).mockRejectedValue(new Error("boom"));
    render(
      <LinkTypeProvider>
        <Probe />
      </LinkTypeProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("count")).toHaveTextContent("0"));
  });
});
