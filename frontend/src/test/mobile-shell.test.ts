/**
 * M4 shell contract (REQ-210): the mobile shell must size against the *live*
 * viewport and keep its chrome clear of the device safe areas. A regression
 * here puts the save button behind the collapsing browser bar on Android.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const SRC = join(__dirname, "..");
const css = (path: string): string => readFileSync(join(SRC, path), "utf-8");

describe("mobile shell viewport sizing", () => {
  it.each([
    "components/NavigationShell/AppShell.module.css",
    "components/NavigationShell/SidebarNavigation.module.css",
    "components/NavigationShell/LoginPage.module.css",
    "components/WorkflowEditor/WorkflowEditor.module.css",
    "components/DiagramGraphEditor/DiagramGraphEditor.module.css",
    "components/SystemSettings/SystemSettings.module.css",
  ])("%s uses dvh (with a vh fallback)", (path) => {
    const content = css(path);
    expect(content).toMatch(/100vh|100vh -/);
    expect(content).toContain("100dvh");
  });

  it("keeps shell chrome clear of the safe areas", () => {
    expect(css("components/NavigationShell/AppShell.module.css")).toContain(
      "env(safe-area-inset-bottom, 0px)"
    );
    const nav = css("components/NavigationShell/SidebarNavigation.module.css");
    expect(nav).toContain("env(safe-area-inset-top, 0px)");
    expect(nav).toContain("env(safe-area-inset-bottom, 0px)");
    expect(nav).toContain("width: min(85vw, 320px)");
  });

  it("documents the phone density breakpoint as a token", () => {
    expect(css("styles/tokens.css")).toContain("--bp-sm: 640px;");
  });

  it("no longer forces a 320px login form on narrow phones", () => {
    expect(css("components/NavigationShell/LoginPage.module.css")).not.toContain("min-width: 320px");
  });
});
