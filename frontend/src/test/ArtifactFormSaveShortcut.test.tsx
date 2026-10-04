/**
 * Issue #1087 — the `Ctrl`/`Cmd`+`S` save shortcut and its behaviour contract on
 * the shared definition-driven form.
 *
 * This is the requirement detail view's form (and every other artifact type's,
 * plus every create dialog — one renderer, one saving mechanism), so what is
 * tested here is what all seven types get:
 *
 *   1. the shortcut saves;
 *   2. the browser default is prevented — the failure mode the issue is about;
 *   3. a save in flight neither double-submits (including the same-tick
 *      button-then-shortcut race) nor leaves the control enabled;
 *   4. a server error moves the focus to the FIELD that caused it, not merely
 *      to a banner — including when that field lives in a section that was
 *      collapsed until the error arrived.
 *
 * Kept as its own file rather than appended to `ArtifactForm.test.tsx`: this is
 * a behaviour cluster with its own fixtures (deferred promises, thrown API
 * envelopes), and interleaving it into the 1600-line definition/renderer suite
 * would obscure both.
 */

import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach } from "vitest";

import { resolveLocaleKey } from "./i18n-test-helpers";

// Same deviation as ArtifactForm.test.tsx: the shared i18next singleton is not
// initialised in unit tests, so `t()` would render raw keys without this mock.
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) => {
      const { defaultValue, ...interpolation } = options ?? {};
      const resolved =
        resolveLocaleKey(key) ??
        (typeof defaultValue === "string" ? defaultValue : key);
      return Object.entries(interpolation).reduce(
        (acc, [name, value]) => acc.replace(`{{${name}}}`, String(value)),
        resolved
      );
    },
    i18n: { language: "de" },
  }),
}));

vi.mock("../api/attribute-definitions", () => ({
  attributeDefinitionsApi: { getWorkspace: vi.fn() },
}));

vi.mock("../context/WorkspaceContext", () => ({
  useWorkspace: () => ({ activeWorkspace: { id: "ws-1", preset: "standard" } }),
}));

vi.mock("../api/users", () => ({ usersApi: { list: vi.fn() } }));
vi.mock("../api/actors", () => ({ actorsApi: { list: vi.fn() } }));

vi.mock("../components/WorkflowStatusEditor", () => ({
  WorkflowStatusEditor: () => <div data-testid="workflow-status-editor" />,
}));

import { attributeDefinitionsApi } from "../api/attribute-definitions";
import { actorsApi } from "../api/actors";
import { usersApi } from "../api/users";
import { ArtifactForm, firstErroredField } from "../components/shared/ArtifactForm";
import type { AttributeSpec, SectionSpec } from "../api/attribute-definitions";

function spec(over: Partial<AttributeSpec>): AttributeSpec {
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
    label: { de: "Titel", en: "Title" },
    help_text: { de: "", en: "" },
    default: null,
    validation: {},
    ai_elicit: false,
    export: false,
    audience: "basic",
    ...over,
  };
}

function section(over: Partial<SectionSpec>): SectionSpec {
  return { name: "general", order: 0, visible: true, layout: "full", ...over };
}

/** `apiClient` throws the parsed response body, not an axios error. */
function fieldError(field: string, message: string): unknown {
  return { error: { code: "VALIDATION_ERROR", message, details: [{ field, errors: [message] }] } };
}

/**
 * Dispatch a real keydown on `document` and return it for `defaultPrevented`.
 *
 * `act()` because the hook's handler starts a save, which is a state update:
 * the same reason `fireEvent` wraps its dispatch.
 */
function pressSave(init: KeyboardEventInit = {}): KeyboardEvent {
  const event = new KeyboardEvent("keydown", {
    key: "s",
    code: "KeyS",
    ctrlKey: true,
    bubbles: true,
    cancelable: true,
    ...init,
  });
  act(() => {
    document.dispatchEvent(event);
  });
  return event;
}

/** A promise plus its resolve/reject handles, for the in-flight assertions. */
function deferred(): {
  promise: Promise<void>;
  resolve: () => void;
  reject: (error: unknown) => void;
} {
  let resolve!: () => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<void>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

const TITLE_AND_EFFORT: AttributeSpec[] = [
  spec({ name: "title", section: "general", order: 0 }),
  spec({ name: "effort", type: "number", section: "general", order: 1 }),
];

beforeEach(() => {
  vi.mocked(attributeDefinitionsApi.getWorkspace).mockReset();
  vi.mocked(usersApi.list).mockReset();
  vi.mocked(usersApi.list).mockResolvedValue([]);
  vi.mocked(actorsApi.list).mockReset();
  vi.mocked(actorsApi.list).mockResolvedValue([]);
});

async function mountForm(onSave: (values: Record<string, unknown>) => Promise<void>) {
  vi.mocked(attributeDefinitionsApi.getWorkspace).mockResolvedValue({
    item_type: "Requirement",
    preset: "standard",
    is_customized: false,
    version: 1,
    attributes: TITLE_AND_EFFORT,
    origins: {},
    sections: [section({})],
  });
  render(
    <ArtifactForm
      itemType="Requirement"
      artifactId="r-1"
      initialValues={{ title: "Original", effort: 1 }}
      onSave={onSave}
    />
  );
  await screen.findByTestId("artifact-form");
  return screen.getByTestId("artifact-form");
}

describe("ArtifactForm Ctrl/Cmd+S (#1087)", () => {
  it("saves the edited values through the shortcut", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn().mockResolvedValue(undefined);
    await mountForm(onSave);

    const title = screen.getByTestId("artifact-field-title");
    await user.clear(title);
    await user.type(title, "Geändert");
    pressSave();

    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
    expect(onSave.mock.calls[0][0]).toMatchObject({ title: "Geändert" });
  });

  it("prevents the browser default so no save dialog opens over the form", async () => {
    await mountForm(vi.fn().mockResolvedValue(undefined));

    const ctrl = pressSave();
    const cmd = pressSave({ key: "s", code: "KeyS", metaKey: true, ctrlKey: false });

    // `defaultPrevented` is the only externally observable proof that the
    // browser's own "Save page as…" was suppressed.
    expect(ctrl.defaultPrevented).toBe(true);
    expect(cmd.defaultPrevented).toBe(true);
    // Let the two saves settle inside act() so their continuations do not
    // escape as unwrapped state updates.
    await waitFor(() => expect(screen.getByTestId("artifact-form-save")).toBeEnabled());
  });

  it("still prevents the browser default on keys it does not act on", async () => {
    // Ctrl+Shift+S belongs to the browser ("Save page as…"), so it must be
    // left alone rather than swallowed.
    await mountForm(vi.fn().mockResolvedValue(undefined));

    const event = pressSave({ key: "S", code: "KeyS", shiftKey: true });

    expect(event.defaultPrevented).toBe(false);
  });

  it("does not double-submit when the chord is held down during a save", async () => {
    const pending = deferred();
    const onSave = vi.fn().mockReturnValue(pending.promise);
    await mountForm(onSave);

    pressSave();
    pressSave();
    pressSave();

    await waitFor(() => expect(screen.getByTestId("artifact-form-save")).toBeDisabled());
    expect(onSave).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId("artifact-form-save")).toHaveTextContent(
      resolveLocaleKey("actions.saving") ?? "Speichert..."
    );

    await act(async () => {
      pending.resolve();
    });
    await waitFor(() => expect(screen.getByTestId("artifact-form-save")).toBeEnabled());
  });

  it("does not double-submit when the button and the chord land in one tick", async () => {
    // The state guard alone cannot see this: React has not re-rendered between
    // the click and the keydown, so `saving` still reads `false`. This is the
    // race the shortcut introduces and the button never had.
    const pending = deferred();
    const onSave = vi.fn().mockReturnValue(pending.promise);
    await mountForm(onSave);

    // A raw DOM click, deliberately outside userEvent's act(): that is exactly
    // the shape of the race — two submissions before React re-renders.
    act(() => {
      screen.getByTestId("artifact-form-save").click();
    });
    pressSave();

    expect(onSave).toHaveBeenCalledTimes(1);
    await act(async () => {
      pending.resolve();
    });
    await waitFor(() => expect(screen.getByTestId("artifact-form-save")).toBeEnabled());
  });

  it("advertises the binding on the save control", async () => {
    await mountForm(vi.fn().mockResolvedValue(undefined));
    // There is no app-wide shortcuts overview to list it in, so the control
    // carries the machine-readable `aria-keyshortcuts` and a pointer tooltip.
    const save = screen.getByTestId("artifact-form-save");
    expect(save).toHaveAttribute("aria-keyshortcuts", "Control+S Meta+S");
    expect(save).toHaveAttribute("title", "Speichern (Strg/Cmd+S)");
  });

  it("leaves the key alone in read mode, where there is nothing to save", async () => {
    vi.mocked(attributeDefinitionsApi.getWorkspace).mockResolvedValue({
      item_type: "Requirement",
      preset: "standard",
      is_customized: false,
      version: 1,
      attributes: TITLE_AND_EFFORT,
      origins: {},
      sections: [section({})],
    });
    const onSave = vi.fn();
    render(
      <ArtifactForm
        itemType="Requirement"
        artifactId="r-1"
        initialValues={{ title: "Original" }}
        onSave={onSave}
        mode="read"
      />
    );
    await screen.findByTestId("artifact-form");

    const event = pressSave();

    expect(onSave).not.toHaveBeenCalled();
    expect(event.defaultPrevented).toBe(false);
  });

  it("does not save through a definition that failed to load", async () => {
    // The form renders a load-error branch instead of its fields; saving a
    // half-built payload there would be worse than doing nothing.
    vi.mocked(attributeDefinitionsApi.getWorkspace).mockRejectedValue(
      new Error("definition unavailable")
    );
    const onSave = vi.fn();
    render(
      <ArtifactForm
        itemType="Requirement"
        artifactId="r-1"
        initialValues={{ title: "Original" }}
        onSave={onSave}
      />
    );
    await screen.findByTestId("artifact-form-load-error");

    pressSave();

    expect(onSave).not.toHaveBeenCalled();
  });
});

describe("ArtifactForm error-to-field focus (#1087)", () => {
  it("moves focus to the field the server rejected", async () => {
    const onSave = vi.fn().mockRejectedValue(fieldError("title", "is required"));
    await mountForm(onSave);

    pressSave();

    await waitFor(() =>
      expect(screen.getByTestId("artifact-field-title")).toHaveFocus()
    );
    // The message is at the field, not only in the top banner. `FieldShell`
    // identifies the error element by `id` (`{testId}-error`), not by a
    // `data-testid`, so the lookup goes through the id it wires into
    // `aria-describedby`.
    const message = document.getElementById("artifact-field-title-error");
    expect(message).not.toBeNull();
    expect(message).toHaveTextContent("is required");
    expect(screen.getByTestId("artifact-field-title")).toHaveAttribute(
      "aria-describedby",
      "artifact-field-title-error"
    );
  });

  it("focuses the FIRST errored field in definition order", async () => {
    const onSave = vi
      .fn()
      .mockRejectedValue(
        fieldError("effort", "must be >= 1")
      );
    await mountForm(onSave);

    pressSave();

    await waitFor(() => expect(screen.getByTestId("artifact-field-effort")).toHaveFocus());
  });

  it("opens a collapsed section and focuses the field inside it", async () => {
    // Rule 5 of `isSectionOpen` forces a section open when it holds an error —
    // but only on the render AFTER the rejection. If the focus effect ran
    // before that render it would find no control and silently do nothing,
    // which is why the effect is keyed on the state update rather than issued
    // from the catch block.
    const effort = spec({ name: "effort", type: "number", section: "advanced", order: 1, audience: "expert" });
    vi.mocked(attributeDefinitionsApi.getWorkspace).mockResolvedValue({
      item_type: "Requirement",
      preset: "standard",
      is_customized: false,
      version: 1,
      attributes: [TITLE_AND_EFFORT[0], effort],
      origins: {},
      sections: [section({}), section({ name: "advanced", order: 1 })],
    });
    const onSave = vi.fn().mockRejectedValue(fieldError("effort", "must be >= 1"));
    render(
      <ArtifactForm
        itemType="Requirement"
        artifactId="r-1"
        initialValues={{ title: "Original", effort: 1 }}
        onSave={onSave}
      />
    );
    await screen.findByTestId("artifact-form");
    // Precondition: the expert section really was collapsed.
    expect(screen.queryByTestId("artifact-field-effort")).not.toBeInTheDocument();

    pressSave();

    await waitFor(() => expect(screen.getByTestId("artifact-field-effort")).toHaveFocus());
    expect(screen.getByTestId("artifact-section-toggle-advanced")).toHaveAttribute(
      "aria-expanded",
      "true"
    );
  });

  it("honours an adapter's renamed field test ids", async () => {
    // `fieldTestIds` exists so an adapter's legacy E2E selectors keep working
    // (#583). Focus has to resolve through the same mapping or it would look
    // for a control that is not in the DOM.
    vi.mocked(attributeDefinitionsApi.getWorkspace).mockResolvedValue({
      item_type: "Requirement",
      preset: "standard",
      is_customized: false,
      version: 1,
      attributes: TITLE_AND_EFFORT,
      origins: {},
      sections: [section({})],
    });
    const onSave = vi.fn().mockRejectedValue(fieldError("title", "is required"));
    render(
      <ArtifactForm
        itemType="Requirement"
        artifactId="r-1"
        initialValues={{ title: "Original", effort: 1 }}
        onSave={onSave}
        fieldTestIds={{ title: "req-title-input" }}
      />
    );
    await screen.findByTestId("artifact-form");

    pressSave();

    await waitFor(() => expect(screen.getByTestId("req-title-input")).toHaveFocus());
  });

  it("focuses the composite when the errored field is drawn by a widget", async () => {
    // A widget owns several fields but renders one container; that container is
    // the only focusable thing on screen for the failure, so it takes focus.
    vi.mocked(attributeDefinitionsApi.getWorkspace).mockResolvedValue({
      item_type: "Requirement",
      preset: "standard",
      is_customized: false,
      version: 1,
      attributes: [
        spec({ name: "title", section: "general", order: 0 }),
        spec({
          name: "risk_matrix",
          type: "widget",
          widget_key: "risk_matrix_rpz",
          fields: ["probability", "impact", "detection"],
          section: "general",
          order: 1,
        }),
        spec({ name: "probability", type: "enum", section: "general", order: 2 }),
      ],
      origins: {},
      sections: [section({})],
    });
    const onSave = vi.fn().mockRejectedValue(fieldError("probability", "is required"));
    render(
      <ArtifactForm
        itemType="Requirement"
        artifactId="r-1"
        initialValues={{ title: "T", probability: null }}
        onSave={onSave}
      />
    );
    await screen.findByTestId("artifact-form");

    pressSave();

    await waitFor(() =>
      expect(screen.getByTestId("artifact-widget-risk_matrix")).toHaveFocus()
    );
  });

  it("falls back to the form banner when the failure has no field mapping", async () => {
    const onSave = vi.fn().mockRejectedValue({ error: { message: "Server exploded" } });
    await mountForm(onSave);

    pressSave();

    // The reload mock invokes the `ArtifactForm` definition fetch, which
    // chains render → effect → focus. Under parallel load on CI that chain
    // can exceed the 1s default `waitFor` timeout, so this waits with the
    // same 2s budget the v6 suites use for their focus assertions.
    await waitFor(() => expect(screen.getByTestId("artifact-form-error")).toHaveFocus(), {
      timeout: 2000,
    });
    expect(screen.getByTestId("artifact-form-error")).toHaveTextContent("Server exploded");
  });

  it("keeps the banner focusable but out of the tab order", async () => {
    // `tabindex="-1"` makes the programmatic focus land without adding a tab
    // stop the user has to walk through.
    const onSave = vi.fn().mockRejectedValue({ error: { message: "Server exploded" } });
    await mountForm(onSave);

    pressSave();

    const banner = await screen.findByTestId("artifact-form-error");
    expect(banner).toHaveAttribute("tabindex", "-1");
  });

  it("does not move focus on a successful save", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn().mockResolvedValue(undefined);
    await mountForm(onSave);

    const title = screen.getByTestId("artifact-field-title");
    await user.click(title);
    expect(title).toHaveFocus();

    pressSave();

    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
    expect(title).toHaveFocus();
  });
});

describe("firstErroredField", () => {
  it("returns null for an empty mapping", () => {
    expect(firstErroredField({}, TITLE_AND_EFFORT)).toBeNull();
  });

  it("orders by the definition, not by object key order", () => {
    // `effort` comes first in the object but second on screen.
    expect(firstErroredField({ effort: ["a"], title: ["b"] }, TITLE_AND_EFFORT)).toBe("title");
  });

  it("still resolves a field the definition does not declare", () => {
    // e.g. a `custom_fields` key from the error envelope.
    expect(firstErroredField({ custom_fields: ["a"] }, TITLE_AND_EFFORT)).toBe("custom_fields");
  });
});
