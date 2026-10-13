import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, defaultValue?: string) => defaultValue ?? key,
  }),
}));

vi.mock("../context/AuthContext", () => ({
  useAuth: () => ({ roles: ["admin"] }),
}));

vi.mock("../context/WorkspaceContext", () => ({
  useWorkspace: () => ({ activeWorkspace: { id: "ws-a" } }),
}));

import { AdrList } from "../components/AdrEditors/AdrList";
import { RiskList } from "../components/RiskEditors/RiskList";
import { IssueList } from "../components/IssueEditors/IssueList";
import { TestCaseList } from "../components/TestCaseEditors/TestCaseList";
import { NeedList } from "../components/NeedsEditors/NeedList";
import { RequirementList } from "../components/RequirementEditors/RequirementList";
import type { Adr, Issue, Requirement, Risk, StakeholderNeed } from "../types";
import type { TestCase } from "../api/testcases";

function base(overrides: Record<string, unknown>) {
  return {
    id: "x-1",
    workspace_id: "ws-a",
    title: "Item",
    description: "",
    status: "draft",
    version: 1,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

describe("artifact lists — outdated badge (D6)", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
  });

  it("marks an outdated ADR row", () => {
    const adr = base({ id: "adr-1", status: "Superseded" }) as unknown as Adr;
    render(<AdrList items={[adr]} onSelect={vi.fn()} onCreateNew={vi.fn()} />);
    expect(screen.getByTestId("adr-row-adr-1-outdated")).toHaveTextContent("Veraltet");
  });

  it("marks a closed Risk row", () => {
    const risk = base({ id: "risk-1", status: "Closed" }) as unknown as Risk;
    render(<RiskList items={[risk]} onSelect={vi.fn()} onCreateNew={vi.fn()} />);
    expect(screen.getByTestId("risk-row-risk-1-outdated")).toBeInTheDocument();
  });

  it("marks a wontfix Issue row", () => {
    const issue = base({ id: "issue-1", status: "Wontfix" }) as unknown as Issue;
    render(<IssueList items={[issue]} onSelect={vi.fn()} onCreateNew={vi.fn()} />);
    expect(screen.getByTestId("issue-row-issue-1-outdated")).toBeInTheDocument();
  });

  it("marks a deprecated TestCase row", () => {
    const tc = base({ id: "tc-1", status: "Deprecated" }) as unknown as TestCase;
    render(<TestCaseList items={[tc]} onSelect={vi.fn()} onCreateNew={vi.fn()} />);
    expect(screen.getByTestId("tc-row-tc-1-outdated")).toBeInTheDocument();
  });

  it("marks an outdated StakeholderNeed row", () => {
    const need = base({ id: "need-1", status: "deprecated" }) as unknown as StakeholderNeed;
    render(
      <MemoryRouter>
        <NeedList needs={[need]} onSelect={vi.fn()} />
      </MemoryRouter>,
    );
    expect(screen.getByTestId("need-list-tree-outdated-need-1")).toBeInTheDocument();
  });

  it("marks an outdated Requirement row", () => {
    const req = base({ id: "req-1", status: "outdated" }) as unknown as Requirement;
    render(
      <RequirementList
        requirements={[req]}
        onSelect={vi.fn()}
        onDelete={vi.fn()}
        onCreateNew={vi.fn()}
      />,
    );
    expect(screen.getByTestId("req-row-req-1-outdated")).toBeInTheDocument();
  });

  it("does not badge an active row", () => {
    const adr = base({ id: "adr-2", status: "Approved" }) as unknown as Adr;
    render(<AdrList items={[adr]} onSelect={vi.fn()} onCreateNew={vi.fn()} />);
    expect(screen.queryByTestId("adr-row-adr-2-outdated")).not.toBeInTheDocument();
  });
});
