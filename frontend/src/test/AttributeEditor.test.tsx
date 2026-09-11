import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

// Real i18next instance (DE/EN resources + interpolation) — without this
// side-effect import `useTranslation()` has no provider in the test
// environment and `t()` returns the raw key instead of the interpolated
// string, same precedent as RiskEditors.test.tsx/AdrEditors.test.tsx etc.
import "../i18n/index";
import { attributeDefinitionsApi } from "../api/attribute-definitions";
import { AttributeEditorPage } from "../components/AttributeEditor";
import {
  deleteSection,
  deleteSectionSpec,
  isMetaPropertyLocked,
  moveAttribute,
  patchAttribute,
  renameSection,
  renameSectionSpec,
  sectionNames,
} from "../components/AttributeEditor/attribute-edits";
import type { AttributeSpec, SectionSpec } from "../api/attribute-definitions";

vi.mock("../api/attribute-definitions", () => ({
  attributeDefinitionsApi: {
    getWorkspace: vi.fn(),
    putWorkspace: vi.fn(),
    resetWorkspace: vi.fn(),
    getGlobal: vi.fn(),
    putGlobal: vi.fn(),
  },
}));
vi.mock("../context/WorkspaceContext", () => ({
  useWorkspace: () => ({ activeWorkspace: { id: "ws-1", preset: "standard" } }),
}));
vi.mock("../context/AuthContext", () => ({
  useAuth: () => ({ roles: ["admin"] }),
}));

function attr(over: Partial<AttributeSpec>): AttributeSpec {
  return {
    name: "title", kind: "core", type: "text", widget_key: null, fields: [],
    options: [], required: false, visible: true, locked: false, editable: true,
    section: "general", order: 0, label: { de: "", en: "" },
    help_text: { de: "", en: "" }, default: null, validation: {},
    ai_elicit: false, export: false, audience: "basic", ...over,
  };
}

function section(over: Partial<SectionSpec>): SectionSpec {
  return { name: "general", order: 0, visible: true, layout: "full", ...over };
}

const STATUS = attr({
  name: "status", type: "enum", locked: true, editable: "workflow",
  options: [{ value: "draft", label_de: "E", label_en: "D" }],
});

describe("attribute-edits", () => {
  it("moves an attribute between sections and renumbers order", () => {
    const out = moveAttribute(
      [attr({ name: "a", order: 0 }), attr({ name: "b", section: "extra", order: 0 })],
      "a",
      "extra",
      0
    );
    const moved = out.find((a) => a.name === "a")!;
    expect(moved.section).toBe("extra");
    expect(moved.order).toBe(0);
    expect(out.find((a) => a.name === "b")!.order).toBe(1);
  });

  it("renames a section on every attribute in it", () => {
    const out = renameSection(
      [attr({ name: "a" }), attr({ name: "b" })],
      "general",
      "basics"
    );
    expect(out.every((a) => a.section === "basics")).toBe(true);
  });

  it("refuses to delete a non-empty section", () => {
    expect(() => deleteSection([attr({ name: "a" })], "general")).toThrow();
  });

  // Post-review M6: renaming/deleting a section used to leave its SectionSpec
  // behind — the renamed section lost its hidden/half state (no matching
  // spec => default visible/full) and the stale entry stayed forever.
  it("renames the matching SectionSpec and keeps its visibility", () => {
    const out = renameSectionSpec(
      [section({ name: "general", visible: false, layout: "half" })],
      "general",
      "basics"
    );
    expect(out).toEqual([
      { name: "basics", order: 0, visible: false, layout: "half" },
    ]);
  });

  it("drops the source spec when renaming onto an existing section", () => {
    const out = renameSectionSpec(
      [section({ name: "general" }), section({ name: "basics", order: 1 })],
      "general",
      "basics"
    );
    expect(out.map((s) => s.name)).toEqual(["basics"]);
  });

  it("removes the SectionSpec of a deleted section", () => {
    expect(
      deleteSectionSpec([section({ name: "extra" }), section({ name: "general" })], "extra")
    ).toEqual([section({ name: "general" })]);
  });

  it("lists sections in first-appearance order", () => {
    expect(
      sectionNames([
        attr({ name: "a", section: "zzz" }),
        attr({ name: "b", section: "general" }),
      ])
    ).toEqual(["zzz", "general"]);
  });

  it("locks visible/required/editable on a locked attribute but not cosmetics", () => {
    expect(isMetaPropertyLocked(STATUS, "visible")).toBe(true);
    expect(isMetaPropertyLocked(STATUS, "required")).toBe(true);
    expect(isMetaPropertyLocked(STATUS, "editable")).toBe(true);
    expect(isMetaPropertyLocked(STATUS, "section")).toBe(false);
    expect(isMetaPropertyLocked(STATUS, "order")).toBe(false);
    expect(isMetaPropertyLocked(STATUS, "label")).toBe(false);
  });

  it("locks name and type on any core attribute", () => {
    const core = attr({ name: "title" });
    expect(isMetaPropertyLocked(core, "name")).toBe(true);
    expect(isMetaPropertyLocked(core, "type")).toBe(true);
    expect(isMetaPropertyLocked(attr({ name: "x", kind: "extended" }), "type")).toBe(false);
  });

  it("patches one attribute and leaves the rest untouched", () => {
    const out = patchAttribute(
      [attr({ name: "a" }), attr({ name: "b" })],
      "a",
      { audience: "expert" }
    );
    expect(out.find((x) => x.name === "a")!.audience).toBe("expert");
    expect(out.find((x) => x.name === "b")!.audience).toBe("basic");
  });
});

describe("AttributeEditorPage", () => {
  beforeEach(() => {
    vi.mocked(attributeDefinitionsApi.getWorkspace).mockResolvedValue({
      item_type: "Requirement",
      preset: "standard",
      is_customized: false,
      version: 1,
      attributes: [STATUS, attr({ name: "title", order: 1 })],
      origins: {},
      sections: [],
    });
    vi.mocked(attributeDefinitionsApi.putWorkspace).mockReset();
    vi.mocked(attributeDefinitionsApi.resetWorkspace).mockReset();
  });

  function renderPage(scope: "workspace" | "global" = "workspace") {
    return render(
      <MemoryRouter initialEntries={["/attributes/Requirement"]}>
        <AttributeEditorPage scope={scope} />
      </MemoryRouter>
    );
  }

  it("lists the attributes grouped by section", async () => {
    renderPage();
    expect(await screen.findByTestId("attribute-row-title")).toBeInTheDocument();
    expect(screen.getByTestId("attribute-section-general")).toBeInTheDocument();
  });

  it("shows a lock icon and no toggles for a locked attribute", async () => {
    renderPage();
    await screen.findByTestId("attribute-row-status");
    expect(screen.getByTestId("attribute-row-status-lock")).toBeInTheDocument();
    expect(
      screen.queryByTestId("attribute-row-status-visible")
    ).not.toBeInTheDocument();
  });

  it("toggles audience through the expert switch", async () => {
    // Findings from this plan's mandated final full-suite run (not a
    // pre-existing assertion this task touches): putWorkspace previously
    // had no resolved value here, so handleSave's `result.attributes` read
    // threw internally on every run -- caught by handleSave's own
    // try/catch and invisible to this test's assertion (it only checks the
    // call args, which are recorded before the throw), but real. Mocking a
    // real resolved shape makes the save path actually complete instead of
    // silently erroring underneath a passing assertion.
    vi.mocked(attributeDefinitionsApi.putWorkspace).mockResolvedValue({
      item_type: "Requirement",
      preset: "standard",
      is_customized: true,
      version: 2,
      attributes: [STATUS, attr({ name: "title", order: 1, audience: "expert" })],
      origins: {},
      sections: [],
    });
    renderPage();
    await userEvent.click(await screen.findByTestId("attribute-row-title"));
    await userEvent.click(screen.getByTestId("attribute-inspector-audience"));
    await userEvent.click(screen.getByTestId("attribute-editor-save"));
    await waitFor(() =>
      // Task 8: putWorkspace gained a 4th argument (sections) -- toHaveBeenCalledWith
      // requires an exact arg count match, so the pre-Task-8 3-arg assertion
      // would never match again regardless of the first 3 args' content
      // (caught by this plan's mandated final full-suite run).
      expect(attributeDefinitionsApi.putWorkspace).toHaveBeenCalledWith(
        "ws-1",
        "Requirement",
        expect.arrayContaining([
          expect.objectContaining({ name: "title", audience: "expert" }),
        ]),
        []
      )
    );
  });

  it("resets a customized workspace definition after confirmation", async () => {
    vi.mocked(attributeDefinitionsApi.getWorkspace).mockResolvedValue({
      item_type: "Requirement",
      preset: "standard",
      is_customized: true,
      version: 2,
      attributes: [STATUS, attr({ name: "title", order: 1 })],
      origins: {},
      sections: [],
    });
    vi.mocked(attributeDefinitionsApi.resetWorkspace).mockResolvedValue({
      item_type: "Requirement",
      preset: "standard",
      is_customized: false,
      version: 3,
      attributes: [STATUS],
      origins: {},
      sections: [],
    });
    renderPage();
    await userEvent.click(await screen.findByTestId("attribute-editor-reset"));
    await userEvent.click(screen.getByTestId("attribute-editor-reset-confirm"));
    await waitFor(() =>
      expect(attributeDefinitionsApi.resetWorkspace).toHaveBeenCalledWith(
        "ws-1",
        "Requirement"
      )
    );
  });

  it("reads and writes the global default in global scope", async () => {
    vi.mocked(attributeDefinitionsApi.getGlobal).mockResolvedValue({
      item_type: "Requirement",
      preset: "standard",
      initialized: true,
      version: 1,
      attributes: [attr({ name: "title" })],
      sections: [],
    });
    vi.mocked(attributeDefinitionsApi.putGlobal).mockResolvedValue({
      item_type: "Requirement",
      preset: "standard",
      initialized: true,
      version: 2,
      attributes: [attr({ name: "title", audience: "expert" })],
      sections: [],
      propagated_workspace_count: 3,
    });
    renderPage("global");
    await userEvent.click(await screen.findByTestId("attribute-row-title"));
    await userEvent.click(screen.getByTestId("attribute-inspector-audience"));
    await userEvent.click(screen.getByTestId("attribute-editor-save"));
    await waitFor(() => expect(attributeDefinitionsApi.putGlobal).toHaveBeenCalled());
    expect(await screen.findByTestId("attribute-editor-toast")).toHaveTextContent("3");
  });

  it("renames a section from its header", async () => {
    renderPage();
    await userEvent.click(await screen.findByTestId("attribute-section-general-rename"));
    const input = screen.getByTestId("attribute-section-general-name");
    await userEvent.clear(input);
    await userEvent.type(input, "basics{Enter}");
    expect(await screen.findByTestId("attribute-section-basics")).toBeInTheDocument();
    expect(screen.queryByTestId("attribute-section-general")).not.toBeInTheDocument();
  });

  it("keeps a hidden section hidden after renaming it (M6: no orphaned spec)", async () => {
    vi.mocked(attributeDefinitionsApi.getWorkspace).mockResolvedValue({
      item_type: "Requirement",
      preset: "standard",
      is_customized: false,
      version: 1,
      attributes: [attr({ name: "title" })],
      origins: {},
      sections: [section({ name: "general", visible: false, layout: "half" })],
    });
    vi.mocked(attributeDefinitionsApi.putWorkspace).mockResolvedValue({
      item_type: "Requirement",
      preset: "standard",
      is_customized: true,
      version: 2,
      attributes: [attr({ name: "title", section: "basics" })],
      origins: {},
      sections: [section({ name: "basics", visible: false, layout: "half" })],
    });
    renderPage();
    await userEvent.click(await screen.findByTestId("attribute-section-general-rename"));
    const input = screen.getByTestId("attribute-section-general-name");
    await userEvent.clear(input);
    await userEvent.type(input, "basics{Enter}");
    await userEvent.click(screen.getByTestId("attribute-editor-save"));
    await waitFor(() =>
      expect(attributeDefinitionsApi.putWorkspace).toHaveBeenCalledWith(
        "ws-1",
        "Requirement",
        expect.anything(),
        [{ name: "basics", order: 0, visible: false, layout: "half" }]
      )
    );
  });

  it("adds an empty section and lets it be deleted again", async () => {
    renderPage();
    await userEvent.click(await screen.findByTestId("attribute-editor-add-section"));
    const input = screen.getByTestId("attribute-editor-new-section-name");
    await userEvent.type(input, "extra{Enter}");
    expect(await screen.findByTestId("attribute-section-extra")).toBeInTheDocument();
    await userEvent.click(screen.getByTestId("attribute-section-extra-delete"));
    expect(screen.queryByTestId("attribute-section-extra")).not.toBeInTheDocument();
  });

  it("refuses to delete a section that still holds attributes", async () => {
    renderPage();
    await userEvent.click(await screen.findByTestId("attribute-section-general-delete"));
    expect(await screen.findByTestId("attribute-editor-error")).toHaveTextContent(
      "not empty"
    );
    expect(screen.getByTestId("attribute-section-general")).toBeInTheDocument();
  });

  it("moves a whole section up in the sequence", async () => {
    vi.mocked(attributeDefinitionsApi.getWorkspace).mockResolvedValue({
      item_type: "Requirement",
      preset: "standard",
      is_customized: false,
      version: 1,
      attributes: [
        attr({ name: "title", section: "general", order: 0 }),
        attr({ name: "uid", section: "change_control", order: 0 }),
      ],
      origins: {},
      sections: [],
    });
    renderPage();
    await userEvent.click(
      await screen.findByTestId("attribute-section-change_control-up")
    );
    const sections = screen.getAllByTestId(/^attribute-section-[a-z_]+$/);
    expect(sections[0]).toHaveAttribute(
      "data-testid",
      "attribute-section-change_control"
    );
  });

  it("surfaces a backend rejection instead of silently discarding the edit", async () => {
    // NOTE (deviation from the plan's literal test snippet): the real
    // apiClient (frontend/src/api/client.ts) throws a plain `ApiError`
    // object shaped `{ error: { message } }`, not an axios-style
    // `{ response: { data: { error } } }` wrapper — the plan's own snippet
    // used the wrong shape, which `extractErrorMessage` would not have
    // unwrapped (it would have fallen through to the plain `Error`'s own
    // "x" message instead of the intended server message). Matches the
    // shape every other rollout wave's tests + `WorkflowPermissionsSection`'s
    // local `extractErrorMessage` already use.
    vi.mocked(attributeDefinitionsApi.putWorkspace).mockRejectedValue(
      Object.assign(new Error("x"), {
        error: { message: "status: 'visible' is not changeable" },
      })
    );
    renderPage();
    await userEvent.click(await screen.findByTestId("attribute-row-title"));
    await userEvent.click(screen.getByTestId("attribute-inspector-audience"));
    await userEvent.click(screen.getByTestId("attribute-editor-save"));
    expect(await screen.findByTestId("attribute-editor-error")).toHaveTextContent(
      "not changeable"
    );
  });

  it("switches entity type in place when embedded outside the routed /attributes path (e.g. WorkspaceSettings)", async () => {
    // No `/attributes/*` route in scope — this is how `WorkspaceSettings.tsx`
    // mounts the "Attributes" tab: `<AttributeEditorPage />` inside `/settings`,
    // with no `:entityType` route param at all.
    render(
      <MemoryRouter initialEntries={["/settings"]}>
        <AttributeEditorPage />
      </MemoryRouter>
    );
    await screen.findByTestId("attribute-row-title");
    expect(attributeDefinitionsApi.getWorkspace).toHaveBeenCalledWith("ws-1", "Requirement");

    await userEvent.selectOptions(
      screen.getByTestId("attribute-editor-entity-type"),
      "Risk"
    );

    // Must stay mounted in place (no navigation away from the host page) and
    // actually switch what it displays.
    expect(screen.getByTestId("attribute-editor")).toBeInTheDocument();
    await waitFor(() =>
      expect(attributeDefinitionsApi.getWorkspace).toHaveBeenCalledWith("ws-1", "Risk")
    );
  });

  it("renumbers order when moving an attribute via the inspector's section field", async () => {
    vi.mocked(attributeDefinitionsApi.getWorkspace).mockResolvedValue({
      item_type: "Requirement",
      preset: "standard",
      is_customized: false,
      version: 1,
      attributes: [
        attr({ name: "title", section: "general", order: 0 }),
        attr({ name: "uid", section: "change_control", order: 0 }),
      ],
      origins: {},
      sections: [],
    });
    // Same finding as "toggles audience through the expert switch" above.
    vi.mocked(attributeDefinitionsApi.putWorkspace).mockResolvedValue({
      item_type: "Requirement",
      preset: "standard",
      is_customized: true,
      version: 2,
      attributes: [
        attr({ name: "uid", section: "change_control", order: 0 }),
        attr({ name: "title", section: "change_control", order: 1 }),
      ],
      origins: {},
      sections: [],
    });
    renderPage();
    await userEvent.click(await screen.findByTestId("attribute-row-title"));
    fireEvent.change(screen.getByTestId("attribute-inspector-section"), {
      target: { value: "change_control" },
    });
    await userEvent.click(screen.getByTestId("attribute-editor-save"));
    await waitFor(() =>
      // Task 8: same 4th-argument (sections) finding as the "toggles
      // audience" test above.
      expect(attributeDefinitionsApi.putWorkspace).toHaveBeenCalledWith(
        "ws-1",
        "Requirement",
        expect.arrayContaining([
          expect.objectContaining({ name: "title", section: "change_control", order: 1 }),
          expect.objectContaining({ name: "uid", section: "change_control", order: 0 }),
        ]),
        []
      )
    );
  });

  it("rejects an empty section name typed into the inspector instead of round-tripping it to the backend", async () => {
    renderPage();
    await userEvent.click(await screen.findByTestId("attribute-row-title"));
    fireEvent.change(screen.getByTestId("attribute-inspector-section"), {
      target: { value: "" },
    });
    expect(await screen.findByTestId("attribute-editor-error")).toHaveTextContent(
      "may not be empty"
    );
    // The attribute stays put — no half-applied move.
    expect(screen.getByTestId("attribute-section-general")).toBeInTheDocument();
    expect(attributeDefinitionsApi.putWorkspace).not.toHaveBeenCalled();
  });
});
