/**
 * Q1 generic settings section (Plan C, T-C2-5).
 *
 * The section is mounted once per level (`/profile`, workspace settings,
 * `/system-settings`) and renders itself from the server's key registry, so the
 * contract worth pinning is the level boundary, not layout:
 *
 *   - only keys whose `ui_editor` is set and whose `levels` contain *this*
 *     scope are rendered (`excludeKeys` removes a key owned elsewhere);
 *   - an edit PATCHes *this* level's route, wrapped in the `{values: …}`
 *     envelope;
 *   - "Zurücksetzen" sends an explicit `null` (= delete the row, so the next
 *     level takes over again) and is unavailable on an inherited key;
 *   - a 403 (or any failed write/read) is announced through `preference-error`
 *     instead of being swallowed.
 *
 * Stubbed at the network level (`fetch`), not at the module level: the
 * component's real path is registry + level + effective through `apiClient`, and
 * mocking the wrapper would leave that wiring untested.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement, type ReactNode } from "react";

import { PreferenceLevelSection } from "./PreferenceLevelSection";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    // Interpolate `{{source}}` so the inherited hint is assertable; every other
    // call returns the key, matching the minimal doubles used elsewhere.
    t: (key: string, options?: string | Record<string, unknown>): string => {
      if (typeof options === "string") return options;
      if (options && typeof options.source === "string") {
        return `${key}:${options.source}`;
      }
      return key;
    },
  }),
}));

// ---------------------------------------------------------------------------
// Fake server
// ---------------------------------------------------------------------------

const REGISTRY = {
  keys: [
    {
      key: "ui.ids.show_readable",
      type: "bool",
      choices: null,
      default: true,
      levels: ["global", "user", "workspace"],
      mode: "override",
      ui_editor: "checkbox",
    },
    {
      key: "ui.markdown.toolbar",
      type: "enum",
      choices: ["auto", "on", "off"],
      default: "auto",
      levels: ["global", "user", "workspace"],
      mode: "override",
      ui_editor: "select",
    },
    {
      // No generic editor: owned by a dedicated UI, never rendered here.
      key: "ui.sidebar.collapsed_groups",
      type: "str_list",
      choices: ["overview"],
      default: [],
      levels: ["user"],
      mode: "override",
      ui_editor: null,
    },
    {
      // Only settable by the user, so a workspace/system mount must skip it.
      key: "ui.user.only",
      type: "bool",
      choices: null,
      default: false,
      levels: ["user"],
      mode: "override",
      ui_editor: "checkbox",
    },
  ],
};

interface LevelBody {
  scope: string;
  workspace_id: string | null;
  values: Record<string, unknown>;
}

type RecordedCall = { url: string; method: string; body?: unknown };

let levels: Record<string, LevelBody>;
let calls: RecordedCall[];
let patchStatus: number;
let registryStatus: number;

function jsonResponse(status: number, body: unknown) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    headers: { get: () => null },
  };
}

function effectiveFor(levelsInPlay: LevelBody[]) {
  // Resolve `override` semantics: first set level in user > workspace > global.
  const values: Record<string, { value: unknown; source: string }> = {};
  for (const spec of REGISTRY.keys) {
    for (const level of levelsInPlay) {
      if (Object.prototype.hasOwnProperty.call(level.values, spec.key)) {
        values[spec.key] = {
          value: level.values[spec.key],
          source: level.scope,
        };
        break;
      }
    }
    if (!values[spec.key]) {
      values[spec.key] = { value: spec.default, source: "default" };
    }
  }
  return values;
}

function installFetchStub(): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string, init?: RequestInit) => {
      const method = (init?.method ?? "GET").toUpperCase();
      const body =
        typeof init?.body === "string" ? JSON.parse(init.body) : undefined;
      calls.push({ url: input, method, body });
      const path = new URL(input, "http://localhost").pathname;

      if (path === "/api/v1/preference-values/registry/") {
        return registryStatus === 200
          ? jsonResponse(200, REGISTRY)
          : jsonResponse(registryStatus, {
              error: { message: "registry unavailable" },
            });
      }
      if (path === "/api/v1/users/me/preference-values/effective/") {
        return jsonResponse(200, {
          workspace_id: null,
          values: effectiveFor([levels.user, levels.global]),
        });
      }
      if (path === "/api/v1/workspaces/ws-1/preference-values/effective/") {
        return jsonResponse(200, {
          workspace_id: "ws-1",
          values: effectiveFor([levels.user, levels.workspace, levels.global]),
        });
      }
      if (path === "/api/v1/users/me/preference-values/") {
        if (method === "PATCH") {
          if (patchStatus !== 200) {
            return jsonResponse(patchStatus, {
              error: { message: "You may not change this." },
            });
          }
          levels.user = { ...levels.user, values: { ...levels.user.values } };
          for (const [key, value] of Object.entries(
            (body as { values: Record<string, unknown> }).values
          )) {
            if (value === null) delete levels.user.values[key];
            else levels.user.values[key] = value;
          }
        }
        return jsonResponse(200, levels.user);
      }
      if (path === "/api/v1/workspaces/ws-1/preference-values/") {
        return jsonResponse(200, levels.workspace);
      }
      if (path === "/api/v1/system/preference-values/") {
        return jsonResponse(200, levels.global);
      }
      return jsonResponse(404, { error: { message: `unexpected ${path}` } });
    })
  );
}

function renderSection(
  scope: "user" | "workspace" | "global",
  workspaceId?: string,
  excludeKeys?: readonly string[]
): void {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    createElement(
      QueryClientProvider,
      { client: queryClient },
      createElement(PreferenceLevelSection, { scope, workspaceId, excludeKeys })
    ) as ReactNode
  );
}

/** Every write the component issued, in order. */
function writeCalls(): RecordedCall[] {
  return calls.filter((call) => call.method === "PATCH");
}

beforeEach(() => {
  calls = [];
  patchStatus = 200;
  registryStatus = 200;
  levels = {
    user: { scope: "user", workspace_id: null, values: {} },
    workspace: { scope: "workspace", workspace_id: "ws-1", values: {} },
    global: { scope: "global", workspace_id: null, values: {} },
  };
  installFetchStub();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("PreferenceLevelSection", () => {
  it("renders only keys with a generic editor that allow this level", async () => {
    renderSection("workspace", "ws-1");

    await waitFor(() =>
      expect(
        screen.getByTestId("preference-input-ui.ids.show_readable")
      ).toBeInTheDocument()
    );
    expect(
      screen.getByTestId("preference-input-ui.markdown.toolbar")
    ).toBeInTheDocument();
    expect(
      screen.queryByTestId("preference-input-ui.sidebar.collapsed_groups")
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId("preference-input-ui.user.only")
    ).not.toBeInTheDocument();
    expect(screen.getByTestId("preference-section-workspace")).toBeInTheDocument();
  });

  it("honours excludeKeys so the page's owning section keeps its key", async () => {
    renderSection("user", undefined, ["ui.ids.show_readable"]);

    await waitFor(() =>
      expect(
        screen.getByTestId("preference-input-ui.markdown.toolbar")
      ).toBeInTheDocument()
    );
    expect(
      screen.queryByTestId("preference-input-ui.ids.show_readable")
    ).not.toBeInTheDocument();
  });

  it("shows an enum key as a select over the registry's choices", async () => {
    renderSection("user");

    await waitFor(() =>
      expect(
        screen.getByTestId("preference-input-ui.markdown.toolbar")
      ).toBeInTheDocument()
    );
    const select = screen.getByTestId(
      "preference-input-ui.markdown.toolbar"
    ) as HTMLSelectElement;
    expect(Array.from(select.options).map((option) => option.value)).toEqual([
      "auto",
      "on",
      "off",
    ]);
  });

  it("PATCHes this level's route with the changed value", async () => {
    renderSection("user");

    await waitFor(() =>
      expect(
        screen.getByTestId("preference-input-ui.ids.show_readable")
      ).toBeInTheDocument()
    );
    fireEvent.click(screen.getByTestId("preference-input-ui.ids.show_readable"));

    await waitFor(() => expect(writeCalls()).toHaveLength(1));
    expect(writeCalls()[0].url).toBe("/api/v1/users/me/preference-values/");
    expect(writeCalls()[0].body).toEqual({
      values: { "ui.ids.show_readable": false },
    });
  });

  it("resets a value set at this level by sending null", async () => {
    levels.workspace.values["ui.markdown.toolbar"] = "on";
    renderSection("workspace", "ws-1");

    await waitFor(() =>
      expect(
        screen.getByTestId("preference-source-ui.markdown.toolbar")
      ).toHaveTextContent("preferences.setHere")
    );
    fireEvent.click(screen.getByTestId("preference-reset-ui.markdown.toolbar"));

    await waitFor(() => expect(writeCalls()).toHaveLength(1));
    expect(writeCalls()[0].url).toBe(
      "/api/v1/workspaces/ws-1/preference-values/"
    );
    expect(writeCalls()[0].body).toEqual({
      values: { "ui.markdown.toolbar": null },
    });
  });

  it("marks an inherited key with its source and disables its reset", async () => {
    levels.global.values["ui.ids.show_readable"] = false;
    renderSection("workspace", "ws-1");

    // The double echoes keys, so a `preferences.source.*` key falls back to the
    // raw level name — what matters is that `source` reached the interpolation.
    await waitFor(() =>
      expect(
        screen.getByTestId("preference-source-ui.ids.show_readable")
      ).toHaveTextContent("preferences.inherited:global")
    );
    expect(
      screen.getByTestId("preference-reset-ui.ids.show_readable")
    ).toBeDisabled();
    // The input still shows the value the caller currently gets.
    expect(
      screen.getByTestId("preference-input-ui.ids.show_readable")
    ).not.toBeChecked();
  });

  it("announces a 403 from a write through preference-error", async () => {
    patchStatus = 403;
    renderSection("user");

    await waitFor(() =>
      expect(
        screen.getByTestId("preference-input-ui.markdown.toolbar")
      ).toBeInTheDocument()
    );
    fireEvent.change(
      screen.getByTestId("preference-input-ui.markdown.toolbar"),
      { target: { value: "off" } }
    );

    await waitFor(() =>
      expect(screen.getByTestId("preference-error")).toHaveTextContent(
        "You may not change this."
      )
    );
  });

  it("announces a failed registry read instead of rendering an empty section", async () => {
    registryStatus = 500;
    renderSection("user");

    await waitFor(() =>
      expect(screen.getByTestId("preference-error")).toBeInTheDocument()
    );
  });
});
