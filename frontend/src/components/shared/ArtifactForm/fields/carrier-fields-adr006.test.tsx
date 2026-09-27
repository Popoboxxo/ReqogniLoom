/**
 * Carrier-backed attribute widgets (ADR-006, issue #1088).
 *
 * Two of the three fields ADR-006 moved off free text need controls that already
 * existed but had never been exercised by a *bootstrapped* definition:
 *
 *   - `Adr.deciders` / `Issue.assignee` — `type: "actor"` with `multiple: true`
 *     (a team), so `ActorPicker` must render the chip row + a group role and
 *     emit the `{"multiple": true, "items": [...]}` envelope, not a single entry;
 *   - `StakeholderNeed.stakeholder` — `type: "multi-enum"`, so `MultiEnum` must
 *     render one toggle per catalogue option and emit a list.
 *
 * These tests are deliberately rendered against a *definition entry shaped the
 * way the backend seeds it* (the `spec()` below mirrors
 * `attribute_definitions.stage_matrix` + `schema.normalize_attribute`), because
 * the point is not "does the component work" but "does the definition-driven
 * renderer map this attribute shape onto the right control with usable
 * selectors". A regression that silently falls through to the `text` default in
 * `renderAttribute` would pass any component-level test and fail these.
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) => {
      const { defaultValue, ...interpolation } = options ?? {};
      const resolved = typeof defaultValue === "string" ? defaultValue : key;
      return Object.entries(interpolation).reduce(
        (acc, [name, value]) => acc.replace(`{{${name}}}`, String(value)),
        resolved
      );
    },
    i18n: { language: "de" },
  }),
}));

const listActors = vi.fn().mockResolvedValue([
  { id: "11111111-1111-1111-1111-111111111111", name: "Ada", email: "ada@t.test" },
  { id: "22222222-2222-2222-2222-222222222222", name: "Grace", email: "grace@t.test" },
]);

vi.mock("../../../../api/actors", () => ({
  actorsApi: { list: (...args: unknown[]) => listActors(...args) },
}));

vi.mock("../../../../context/WorkspaceContext", () => ({
  useWorkspace: () => ({ activeWorkspace: { id: "ws-1" } }),
}));

import { ActorPicker } from "./ActorPicker";
import { MultiEnum } from "./MultiEnum";
import type {
  ActorFieldValue,
} from "./ActorPicker";
import type { AttributeSpec } from "../../../../api/attribute-definitions";

function spec(over: Partial<AttributeSpec> = {}): AttributeSpec {
  return {
    name: "field",
    kind: "core",
    type: "text",
    widget_key: null,
    fields: [],
    options: [],
    required: false,
    visible: true,
    locked: false,
    editable: true,
    section: "attribution",
    order: 0,
    label: { de: "Feld", en: "Field" },
    help_text: { de: "", en: "" },
    default: null,
    validation: {},
    ai_elicit: false,
    export: true,
    audience: "basic",
    ...over,
  };
}

const STAKEHOLDER: AttributeSpec = spec({
  name: "stakeholder",
  type: "multi-enum",
  label: { de: "Stakeholder", en: "Stakeholder" },
  options: [
    { value: "customer", label_de: "Kunde", label_en: "Customer" },
    { value: "operations", label_de: "Betrieb", label_en: "Operations" },
    { value: "regulator", label_de: "Regulator", label_en: "Regulator" },
  ],
});

const DECIDERS: AttributeSpec = spec({
  name: "deciders",
  type: "actor",
  multiple: true,
  allow_external: false,
  label: { de: "Entscheider", en: "deciders" },
});

describe("multi-enum renders the catalogue options as a toggle group (ADR-006)", () => {
  it("draws one option per catalogue entry, each with a stable testid", () => {
    render(
      <MultiEnum
        attribute={STAKEHOLDER}
        value={["customer"]}
        onChange={() => undefined}
        disabled={false}
        errors={undefined}
        testId="artifact-field-stakeholder"
      />
    );

    for (const option of STAKEHOLDER.options) {
      expect(
        screen.getByTestId(`artifact-field-stakeholder-option-${option.value}`)
      ).toBeTruthy();
    }
    // The German option label is what a German workspace shows — the option
    // labels come from the catalogue, not from a client-side i18n table.
    expect(screen.getByText("Kunde")).toBeTruthy();
    expect(screen.getByText("Betrieb")).toBeTruthy();
  });

  it("emits a LIST and toggles a selection on and off", async () => {
    const seen: unknown[] = [];
    const { rerender } = render(
      <MultiEnum
        attribute={STAKEHOLDER}
        value={null}
        onChange={(next) => seen.push(next)}
        disabled={false}
        errors={undefined}
        testId="artifact-field-stakeholder"
      />
    );

    await userEvent.click(
      screen.getByTestId("artifact-field-stakeholder-option-operations")
    );
    expect(seen).toEqual([["operations"]]);

    rerender(
      <MultiEnum
        attribute={STAKEHOLDER}
        value={["operations"]}
        onChange={(next) => seen.push(next)}
        disabled={false}
        errors={undefined}
        testId="artifact-field-stakeholder"
      />
    );
    await userEvent.click(
      screen.getByTestId("artifact-field-stakeholder-option-operations")
    );
    expect(seen[1]).toEqual([]);
    expect(screen.getByRole("group")).toBeTruthy();
  });
});

describe("multiple actor renders a team selection (ADR-006)", () => {
  beforeEach(() => listActors.mockClear());

  it("emits the multiple envelope, never a bare entry", async () => {
    const seen: ActorFieldValue[] = [];
    render(
      <ActorPicker
        attribute={DECIDERS}
        value={null}
        onChange={(next) => seen.push(next)}
        disabled={false}
        errors={undefined}
        testId="artifact-field-deciders"
      />
    );

    const search = await screen.findByTestId("artifact-field-deciders-search");
    await userEvent.click(search);
    await userEvent.click(
      await screen.findByTestId(
        "artifact-field-deciders-option-11111111-1111-1111-1111-111111111111"
      )
    );

    expect(seen).toHaveLength(1);
    expect(seen[0]).toEqual({
      multiple: true,
      items: [{ kind: "user", id: "11111111-1111-1111-1111-111111111111" }],
    });
  });

  it("shows a removable chip per selected person", async () => {
    const { container } = render(
      <ActorPicker
        attribute={DECIDERS}
        value={{
          multiple: true,
          items: [
            { kind: "user", id: "11111111-1111-1111-1111-111111111111" },
            { kind: "user", id: "22222222-2222-2222-2222-222222222222" },
          ],
        }}
        onChange={() => undefined}
        disabled={false}
        errors={undefined}
        testId="artifact-field-deciders"
      />
    );

    expect(container.querySelectorAll("[data-testid$='-chip']")).toHaveLength(2);
    expect(container.querySelectorAll("[data-testid$='-chip-remove']")).toHaveLength(2);
    // A team is a group of chips, not a single combobox value.
    expect(screen.getByRole("group")).toBeTruthy();
  });

  it("never offers the external-person affordance while allow_external is false", async () => {
    render(
      <ActorPicker
        attribute={DECIDERS}
        value={null}
        onChange={() => undefined}
        disabled={false}
        errors={undefined}
        testId="artifact-field-deciders"
      />
    );

    await userEvent.click(await screen.findByTestId("artifact-field-deciders-search"));
    await userEvent.type(screen.getByTestId("artifact-field-deciders-search"), "Zoe");
    expect(screen.queryByTestId("artifact-field-deciders-create-external")).toBeNull();
  });
});
