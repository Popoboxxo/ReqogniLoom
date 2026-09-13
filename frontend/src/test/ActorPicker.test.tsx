/**
 * ActorPicker unit tests (Attribut v3 WS2, #936, spec section 4).
 *
 * Covers the two value shapes (single / `multiple`), the `allow_external`
 * gate, the read-only rendering and the load/empty/error states. The combobox
 * ARIA wiring is exercised through the same interactions the E2E suite will
 * use (type -> option appears -> click).
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { resolveLocaleKey } from "./i18n-test-helpers";

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

vi.mock("../context/WorkspaceContext", () => ({
  useWorkspace: () => ({ activeWorkspace: { id: "ws-1", preset: "standard" } }),
}));

vi.mock("../api/actors", () => ({
  actorsApi: { list: vi.fn() },
}));

import { actorsApi } from "../api/actors";
import { ActorPicker } from "../components/shared/ArtifactForm/fields";
import type { AttributeSpec } from "../api/attribute-definitions";
import type { ActorValue } from "../types";

function spec(over: Partial<AttributeSpec> = {}): AttributeSpec {
  return {
    name: "owner",
    kind: "core",
    type: "actor",
    widget_key: null,
    fields: [],
    options: [],
    required: false,
    visible: true,
    locked: false,
    editable: true,
    section: "general",
    order: 0,
    label: { de: "Owner", en: "Owner" },
    help_text: { de: "", en: "" },
    default: null,
    validation: {},
    ai_elicit: false,
    export: false,
    audience: "basic",
    multiple: false,
    allow_external: false,
    ...over,
  };
}

const MEMBERS = [
  { id: "u-1", name: "Alice Admin", email: "alice@example.com" },
  { id: "u-2", name: "Bob Builder", email: "bob@example.com" },
];

interface RenderArgs {
  attribute?: Partial<AttributeSpec>;
  value?: unknown;
  disabled?: boolean;
}

function renderPicker({ attribute, value = null, disabled = false }: RenderArgs) {
  const onChange = vi.fn();
  render(
    <ActorPicker
      attribute={spec(attribute)}
      value={value as never}
      onChange={onChange}
      disabled={disabled}
      testId="artifact-field-owner"
    />
  );
  return { onChange };
}

describe("ActorPicker", () => {
  beforeEach(() => {
    vi.mocked(actorsApi.list).mockReset();
    vi.mocked(actorsApi.list).mockResolvedValue(MEMBERS);
  });

  it("renders a combobox and stores the single internal-actor wire form", async () => {
    const { onChange } = renderPicker({});
    const input = await screen.findByTestId("artifact-field-owner-input");
    expect(input).toHaveAttribute("role", "combobox");

    await userEvent.click(input);
    await userEvent.click(await screen.findByTestId("artifact-field-owner-option-u-2"));

    expect(onChange).toHaveBeenCalledWith({ kind: "user", id: "u-2" });
  });

  it("shows the selected actor's name as the placeholder", async () => {
    renderPicker({ value: { kind: "user", id: "u-1" } });
    const input = await screen.findByTestId("artifact-field-owner-input");
    await waitFor(() => expect(input).toHaveAttribute("placeholder", "Alice Admin"));
  });

  it("stores the multiple wrapper and renders removable chips", async () => {
    const { onChange } = renderPicker({
      attribute: { multiple: true },
      value: { multiple: true, items: [{ kind: "user", id: "u-1" }] },
    });

    // Existing entry renders as a chip with a remove control.
    const chips = await screen.findAllByTestId("artifact-field-owner-chip");
    expect(chips).toHaveLength(1);
    expect(chips[0]).toHaveTextContent("Alice Admin");

    // Adding a second person emits `{multiple: true, items: [...]}`.
    const search = screen.getByTestId("artifact-field-owner-search");
    await userEvent.click(search);
    await userEvent.click(await screen.findByTestId("artifact-field-owner-option-u-2"));
    expect(onChange).toHaveBeenCalledWith({
      multiple: true,
      items: [
        { kind: "user", id: "u-1" },
        { kind: "user", id: "u-2" },
      ],
    });
  });

  it("removes an actor from the multiple value", async () => {
    const { onChange } = renderPicker({
      attribute: { multiple: true },
      value: {
        multiple: true,
        items: [
          { kind: "user", id: "u-1" },
          { kind: "user", id: "u-2" },
        ],
      },
    });
    const remove = await screen.findAllByTestId("artifact-field-owner-chip-remove");
    await userEvent.click(remove[0]);
    expect(onChange).toHaveBeenCalledWith({
      multiple: true,
      items: [{ kind: "user", id: "u-2" }],
    });
  });

  it("offers 'create as external person' when a query has no match and allow_external is true", async () => {
    const { onChange } = renderPicker({ attribute: { allow_external: true } });
    const input = await screen.findByTestId("artifact-field-owner-input");
    await userEvent.type(input, "Frau Müller (TÜV)");
    const create = await screen.findByTestId("artifact-field-owner-create-external");
    await userEvent.click(create);
    expect(onChange).toHaveBeenCalledWith({
      kind: "external",
      name: "Frau Müller (TÜV)",
    });
  });

  it("never offers an external person when allow_external is false", async () => {
    renderPicker({ attribute: { allow_external: false } });
    const input = await screen.findByTestId("artifact-field-owner-input");
    await userEvent.type(input, "Frau Müller (TÜV)");
    expect(
      screen.queryByTestId("artifact-field-owner-create-external")
    ).not.toBeInTheDocument();
  });

  it("renders static read-only text instead of a combobox when disabled", async () => {
    renderPicker({ disabled: true, value: { kind: "user", id: "u-2" } });
    const readOnly = await screen.findByTestId("artifact-field-owner");
    expect(readOnly.tagName).toBe("TEXTAREA");
    expect(readOnly).toHaveAttribute("readonly");
    expect(readOnly).toHaveValue("Bob Builder");
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
  });

  it("shows the unassigned label when disabled with no value", async () => {
    renderPicker({ disabled: true, value: null });
    expect(await screen.findByTestId("artifact-field-owner")).toHaveValue(
      "Nicht zugewiesen"
    );
  });

  it("surfaces an unreadable member directory while keeping the stored value", async () => {
    vi.mocked(actorsApi.list).mockRejectedValue(
      new Error("You are not a member of this workspace.")
    );
    renderPicker({ value: { kind: "user", id: "u-1" } });
    const input = await screen.findByTestId("artifact-field-owner-input");
    await userEvent.click(input);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Mitgliederliste nicht verfügbar"
    );
    // The assigned actor is still displayed, so a save cannot silently drop it.
    await waitFor(() =>
      expect(input).toHaveAttribute("placeholder", "Unbekannter Wert: u-1")
    );
  });

  it("shows an empty state when the directory has no people", async () => {
    vi.mocked(actorsApi.list).mockResolvedValue([]);
    renderPicker({});
    const input = await screen.findByTestId("artifact-field-owner-input");
    await userEvent.click(input);
    expect(await screen.findByTestId("artifact-field-owner-empty")).toHaveTextContent(
      "Keine Personen verfügbar"
    );
  });

  it("exposes a remove affordance for a single selected actor", async () => {
    const { onChange } = renderPicker({ value: { kind: "user", id: "u-1" } });
    const input = await screen.findByTestId("artifact-field-owner-input");
    await userEvent.click(input);
    await waitFor(() =>
      expect(input).toHaveAttribute("placeholder", "Alice Admin")
    );
    await userEvent.click(await screen.findByTestId("artifact-field-owner-clear"));
    expect(onChange).toHaveBeenCalledWith(null);
  });

  it("does not offer 'unassigned' for a required actor", async () => {
    renderPicker({ attribute: { required: true }, value: { kind: "user", id: "u-1" } });
    const input = await screen.findByTestId("artifact-field-owner-input");
    await userEvent.click(input);
    await waitFor(() =>
      expect(input).toHaveAttribute("placeholder", "Alice Admin")
    );
    expect(screen.queryByTestId("artifact-field-owner-clear")).not.toBeInTheDocument();
  });
});

describe("ActorPicker multiple value helpers", () => {
  it("renders an unknown internal id rather than a blank chip", async () => {
    renderPicker({
      attribute: { multiple: true },
      value: {
        multiple: true,
        items: [{ kind: "user", id: "actor-not-in-directory" } as ActorValue],
      },
    });
    const chip = await screen.findByTestId("artifact-field-owner-chip");
    expect(chip).toHaveTextContent("Unbekannter Wert: actor-not-in-directory");
  });
});
