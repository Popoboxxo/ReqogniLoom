/**
 * UI-006 keyboard regression: every clickable region migrated to the shared
 * `useActivationKeys` contract must activate on BOTH Enter and Space.
 *
 * The concrete defect this pins down: AttributeTable's `<tr onClick>` and
 * `<th onClick>` had no keyboard path at all. The other rows duplicated the
 * handler locally; a shared hook now owns it, and the design-system ratchet
 * exemptions for all nine regions are gone (maxViolations stays 0).
 */
import { useState } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { useActivationKeys } from "../hooks/useActivationKeys";
import { WorkspaceCard } from "../components/DashboardViews/WorkspaceCard";
import { AttributeList } from "../components/AttributeEditor/AttributeList";
import { AttributeTable } from "../components/AttributeEditor/AttributeTable";
import { GlossaryTermList } from "../components/GlossaryView/GlossaryTermList";
import { IcdDetailPane } from "../components/IcdView/IcdDetailPane";
import { ArtifactRow } from "../components/shared/ArtifactRow/ArtifactRow";
import { WorkspaceTree } from "../components/shared/WorkspaceTree/workspace-tree";
import type { AttributeSpec } from "../api/attribute-definitions";
import type { WorkspaceWithMetrics } from "../types";
import type { WorkspaceTreeNode } from "../components/shared/WorkspaceTree/workspace-tree";

vi.mock("react-i18next", () => ({
  // Several components call t(key, { defaultValue }) — echo the string
  // fallback, never the options object (that would be an invalid React child).
  useTranslation: () => ({
    t: (key: string, options?: string | { defaultValue?: string }) =>
      typeof options === "string" ? options : (options?.defaultValue ?? key),
  }),
  initReactI18next: { type: "3rdParty", init: () => undefined },
}));

vi.mock("../context/WorkspaceContext", () => ({
  useWorkspace: () => ({ terminologyLabel: (key: string) => key }),
  useOptionalWorkspace: () => ({ terminologyLabel: (key: string) => key }),
}));

vi.mock("../components/shared/ArtifactInspector", () => ({
  InspectorShell: () => <aside data-testid="inspector-shell-stub" />,
}));
vi.mock("../components/WorkflowStatusEditor", () => ({
  WorkflowStatusEditor: () => null,
}));

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const WORKSPACE = {
  id: "ws-001",
  name: "Keyboard Workspace",
  preset: "standard",
  terminology_profile: "se_mode",
  language: "en",
  is_active: true,
  closed_at: null,
  closed_by: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  requirement_count: 3,
  open_item_count: 1,
} as WorkspaceWithMetrics;

function attr(overrides: Partial<AttributeSpec>): AttributeSpec {
  return {
    name: "title",
    kind: "core",
    type: "text",
    widget_key: null,
    fields: [],
    options: [],
    required: false,
    visible: true,
    locked: false,
    editable: true,
    section: "general",
    order: 0,
    label: { de: "", en: "" },
    help_text: { de: "", en: "" },
    default: null,
    validation: {},
    ai_elicit: false,
    export: false,
    audience: "basic",
    ...overrides,
  };
}

const ATTRIBUTES = [attr({ name: "title" })];

const TERM = {
  id: "term-1",
  term: "Requirement",
  definition: "A need",
  abbreviation: "REQ",
  workspace_id: "ws-001",
} as never;

const ICD = {
  id: "icd-1",
  name: "Nav to Ground Link",
  workspace_id: "ws-001",
  source_element_id: "arch-1",
  target_element_id: "arch-2",
  current_version: null,
  created_at: "2026-01-01T00:00:00Z",
  version: 1,
  direction: "unidirectional",
  interface_type: "data",
  semantic_description: "link",
  preconditions: [],
  postconditions: [],
  invariants: [],
} as never;

const TREE_NODES: WorkspaceTreeNode[] = [
  { id: "n1", name: "Alpha Need", parentId: null },
];

/** A tiny host for the hook itself. */
function ActivationHost({ onActivate }: { onActivate: () => void }): JSX.Element {
  const activation = useActivationKeys(onActivate, { role: "button" });
  return <div data-testid="host" {...activation}>host</div>;
}

// ---------------------------------------------------------------------------
// The shared contract
// ---------------------------------------------------------------------------

describe("useActivationKeys (APG button pattern)", () => {
  it.each(["Enter", " "])("activates on %s and suppresses default", (key) => {
    const onActivate = vi.fn();
    const preventDefault = vi.spyOn(Event.prototype, "preventDefault");
    try {
      render(<ActivationHost onActivate={onActivate} />);
      const host = screen.getByTestId("host");
      expect(host).toHaveAttribute("role", "button");
      expect(host).toHaveAttribute("tabindex", "0");

      fireEvent.keyDown(host, { key });
      expect(onActivate).toHaveBeenCalledTimes(1);
      // Space's default page scroll must be suppressed for a focused region.
      expect(preventDefault).toHaveBeenCalled();
    } finally {
      preventDefault.mockRestore();
    }
  });

  it("ignores non-activation keys", () => {
    const onActivate = vi.fn();
    render(<ActivationHost onActivate={onActivate} />);
    fireEvent.keyDown(screen.getByTestId("host"), { key: "ArrowDown" });
    expect(onActivate).not.toHaveBeenCalled();
  });

  it("does not re-activate the region for a key press on a nested control", () => {
    const onActivate = vi.fn();
    function WithButton(): JSX.Element {
      const activation = useActivationKeys(onActivate, { role: "button" });
      return (
        <div data-testid="outer" {...activation}>
          <button type="button" data-testid="inner">inner</button>
        </div>
      );
    }
    render(<WithButton />);
    fireEvent.keyDown(screen.getByTestId("inner"), { key: "Enter" });
    expect(onActivate).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// Per-region activation
// ---------------------------------------------------------------------------

describe("clickable regions activate with Enter and Space (UI-006)", () => {
  it.each(["Enter", " "])("WorkspaceCard body — %s", (key) => {
    const onSelect = vi.fn();
    render(
      <WorkspaceCard
        workspace={WORKSPACE}
        onSelect={onSelect}
        onOpenSettings={vi.fn()}
      />,
    );
    const region = screen.getByTestId("workspace-card-clickable-region");
    expect(region).toHaveAttribute("role", "button");
    fireEvent.keyDown(region, { key });
    expect(onSelect).toHaveBeenCalledWith(WORKSPACE);
  });

  it.each(["Enter", " "])("AttributeList row — %s", (key) => {
    const onSelect = vi.fn();
    render(
      <AttributeList
        attributes={ATTRIBUTES}
        sections={[]}
        emptySections={[]}
        selected={null}
        origins={undefined}
        onSelect={onSelect}
        onMove={vi.fn()}
        onRenameSection={vi.fn()}
        onDeleteSection={vi.fn()}
        onMoveSection={vi.fn()}
        onAddAttribute={vi.fn()}
        onDeleteAttribute={vi.fn()}
        onToggleSectionVisible={vi.fn()}
        onSetSectionLayout={vi.fn()}
        readOnly={false}
      />,
    );
    const row = screen.getByTestId("attribute-row-title");
    expect(row).toHaveAttribute("role", "button");
    fireEvent.keyDown(row, { key });
    expect(onSelect).toHaveBeenCalledWith("title");
  });

  it.each(["Enter", " "])("AttributeTable row (previously broken) — %s", (key) => {
    const onSelect = vi.fn();
    render(
      <AttributeTable attributes={ATTRIBUTES} selected={null} onSelect={onSelect} />,
    );
    const row = screen.getByTestId("attribute-table-row-title");
    // Native table semantics stay: no fake button role on the <tr>.
    expect(row.tagName).toBe("TR");
    expect(row).not.toHaveAttribute("role", "button");
    expect(row).toHaveAttribute("tabindex", "0");
    fireEvent.keyDown(row, { key });
    expect(onSelect).toHaveBeenCalledWith("title");
  });

  it("AttributeTable sort header is a native button (built-in keyboard activation)", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    render(
      <AttributeTable
        attributes={[attr({ name: "alpha" }), attr({ name: "beta" })]}
        selected={null}
        onSelect={onSelect}
      />,
    );
    const sortButton = screen.getByTestId("attribute-table-sort-name");
    expect(sortButton.tagName).toBe("BUTTON");
    expect(sortButton).toHaveClass("btn-ghost");
    expect(sortButton.closest("th")).toBeInTheDocument();

    // Real keyboard interaction on a native button: focus + Enter/Space
    // produces a click, toggling the sort order.
    sortButton.focus();
    await user.keyboard("{Enter}");
    expect(
      screen.getAllByTestId(/^attribute-table-row-[a-z]+$/).map((r) => r.getAttribute("data-testid")),
    ).toEqual(["attribute-table-row-beta", "attribute-table-row-alpha"]);

    await user.keyboard(" ");
    expect(
      screen.getAllByTestId(/^attribute-table-row-[a-z]+$/).map((r) => r.getAttribute("data-testid")),
    ).toEqual(["attribute-table-row-alpha", "attribute-table-row-beta"]);
  });

  it.each(["Enter", " "])("GlossaryTermList row — %s", (key) => {
    const onSelect = vi.fn();
    render(
      <GlossaryTermList
        terms={[TERM]}
        selectedId={null}
        onSelect={onSelect}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
      />,
    );
    const row = screen.getByTestId("glossary-row-term-1");
    expect(row).toHaveAttribute("role", "button");
    fireEvent.keyDown(row, { key });
    expect(onSelect).toHaveBeenCalledWith(TERM);
  });

  it.each(["Enter", " "])("IcdDetailPane similar row (native <li>) — %s", (key) => {
    const onSelect = vi.fn();
    render(
      <IcdDetailPane
        detail={ICD}
        // The panel derives `currentICD` from this list, so the current row
        // must be present alongside the similar one.
        allICDs={[ICD, { ...ICD, id: "icd-2" }]}
        artifactLabel={(id) => id}
        onSelectIcd={onSelect}
        showNewVersion={false}
        setShowNewVersion={vi.fn()}
        formError={null}
        setFormError={vi.fn()}
        isSaving={false}
        onNewVersion={vi.fn()}
        nvDirection="unidirectional"
        setNvDirection={vi.fn()}
        nvInterfaceType=""
        setNvInterfaceType={vi.fn()}
        nvContract=""
        setNvContract={vi.fn()}
        nvPre=""
        setNvPre={vi.fn()}
        nvPost=""
        setNvPost={vi.fn()}
        nvInv=""
        setNvInv={vi.fn()}
      />,
    );
    const row = screen.getByTestId("similar-icd-icd-2");
    expect(row.tagName).toBe("LI");
    expect(row).not.toHaveAttribute("role", "button");
    fireEvent.keyDown(row, { key });
    expect(onSelect).toHaveBeenCalledWith("icd-2");
  });

  it.each(["Enter", " "])("ArtifactRow — %s", (key) => {
    const onClick = vi.fn();
    render(<ArtifactRow title="A requirement" onClick={onClick} testId="row-1" />);
    const row = screen.getByTestId("row-1");
    expect(row).toHaveAttribute("role", "button");
    fireEvent.keyDown(row, { key });
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("ArtifactRow without an onClick stays a plain container", () => {
    render(<ArtifactRow title="A requirement" testId="row-plain" />);
    const row = screen.getByTestId("row-plain");
    expect(row).not.toHaveAttribute("role");
    expect(row).not.toHaveAttribute("tabindex");
    fireEvent.keyDown(row, { key: "Enter" });
    fireEvent.click(row);
    // No callback exists; this only asserts no crash / no accidental activation.
    expect(row).toBeInTheDocument();
  });

  it.each(["Enter", " "])("WorkspaceTree treeitem (native <li>) — %s", (key) => {
    const onSelect = vi.fn();
    render(<WorkspaceTree nodes={TREE_NODES} onSelect={onSelect} showSearch={false} />);
    const row = screen.getByTestId("workspace-tree-node-n1");
    expect(row.tagName).toBe("LI");
    expect(row).toHaveAttribute("role", "treeitem");
    fireEvent.keyDown(row, { key });
    expect(onSelect).toHaveBeenCalledWith("n1");
  });
});

/** Guards against future edits dropping the composed arrow-key handler. */
describe("WorkspaceTree arrow navigation still works alongside activation", () => {
  it("ArrowRight expands a parent node", () => {
    const nodes: WorkspaceTreeNode[] = [
      { id: "parent", name: "Parent", parentId: null },
      { id: "child", name: "Child", parentId: "parent" },
    ];
    render(<WorkspaceTree nodes={nodes} onSelect={vi.fn()} showSearch={false} />);
    const parent = screen.getByTestId("workspace-tree-node-parent");
    // The tree auto-expands new nodes; collapse first so ArrowRight has an
    // observable effect.
    if (parent.getAttribute("aria-expanded") === "true") {
      fireEvent.keyDown(parent, { key: "ArrowLeft" });
    }
    expect(parent).toHaveAttribute("aria-expanded", "false");
    fireEvent.keyDown(parent, { key: "ArrowRight" });
    expect(parent).toHaveAttribute("aria-expanded", "true");
  });
});

/** Keeps the hook's update-on-change behaviour explicit. */
describe("useActivationKeys follows the latest callback", () => {
  it("uses the current callback after a re-render", () => {
    const first = vi.fn();
    const second = vi.fn();
    function Host(): JSX.Element {
      const [n, setN] = useState(0);
      const activation = useActivationKeys(n === 0 ? first : second);
      return (
        <div data-testid="changing" {...activation}>
          <button type="button" onClick={() => setN(1)}>next</button>
        </div>
      );
    }
    render(<Host />);
    fireEvent.keyDown(screen.getByTestId("changing"), { key: "Enter" });
    expect(first).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button"));
    fireEvent.keyDown(screen.getByTestId("changing"), { key: "Enter" });
    expect(second).toHaveBeenCalledTimes(1);
  });
});
