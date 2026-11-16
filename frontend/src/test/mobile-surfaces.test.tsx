/** Mobile surface contracts for M6–M8 (REQ-211/REQ-212). */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it, vi } from "vitest";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string, fallback?: string) => fallback ?? key }),
}));

const css = (path: string): string =>
  readFileSync(join(__dirname, "..", path), "utf-8");

describe("lists and tables on touch devices", () => {
  it("wraps filter rows and actions into two phone-sized lines", () => {
    expect(css("components/shared/ListToolbar.module.css")).toContain("@media (max-width: 640px)");
  });

  it("keeps the identifier column while a table scrolls", () => {
    const table = css("components/shared/ArtifactTable/ArtifactTable.module.css");
    expect(table).toContain(".headerCell:first-child");
    expect(table).toContain("position: sticky");
  });

  it("never hides touch actions behind hover", () => {
    for (const path of [
      "components/WorkflowEditor/WorkflowEditor.module.css",
      "components/DiagramGraphEditor/DiagramGraphEditor.module.css",
    ]) {
      expect(css(path)).toContain("@media (hover: none)");
    }
  });

  it("stops iOS from zooming on control focus", () => {
    expect(css("styles/tokens.css")).toContain("--control-font-size-touch: 16px");
    expect(css("styles/global.css")).toContain("(pointer: coarse)");
  });
});

describe("heavy mobile surfaces", () => {
  it("collapses the two-tree grid into tabs", () => {
    const tsx = readFileSync(
      join(__dirname, "..", "components/ConnectionView/AllocationTreesRenderer.tsx"),
      "utf-8"
    );
    expect(tsx).toContain('data-testid="allocation-trees-tabs"');
    expect(tsx).toContain('data-mobile-hidden={mobileColumn');
    expect(css("components/ConnectionView/AllocationTreesRenderer.module.css")).toContain(
      "@media (max-width: 768px)"
    );
  });

  it("shows a read-only hint on graph and canvas editors", async () => {
    const { DesktopOnlyHint } = await import(
      "../components/shared/DesktopOnlyHint/DesktopOnlyHint"
    );
    expect(DesktopOnlyHint).toBeTypeOf("function");
    for (const path of [
      "components/canvas/CanvasEditor.tsx",
      "components/DiagramGraphEditor/DiagramGraphEditorPage.tsx",
    ]) {
      expect(
        readFileSync(join(__dirname, "..", path), "utf-8")
      ).toContain("DesktopOnlyHint");
    }
  });

  it("keeps the document save bar reachable above the home indicator", () => {
    const sheet = css("components/Documents/Documents.module.css");
    expect(sheet).toContain("position: sticky");
    expect(sheet).toContain("env(safe-area-inset-bottom");
  });
});
