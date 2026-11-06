/**
 * P5 Task 5.2 — workspace settings editor for the allocation-graph card fields.
 *
 * Verifies the round-trip through the preference API, the row-count editor and
 * that the mandatory lock marker cannot be toggled or removed.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import de from "../../i18n/locales/de.json";

import {
  CARD_FIELDS_PREFERENCE_KEY,
  defaultCardFieldConfigMap,
  serializeCardFieldConfigMap,
  type CardFieldConfigMap,
} from "../AllocationGraph/cardFields";
import { CardFieldsSection } from "./CardFieldsSection";

vi.mock("react-i18next", () => {
  function lookup(key: string): string | undefined {
    const value = key
      .split(".")
      .reduce<unknown>(
        (node, segment) =>
          node && typeof node === "object"
            ? (node as Record<string, unknown>)[segment]
            : undefined,
        de
      );
    return typeof value === "string" ? value : undefined;
  }
  return {
    useTranslation: () => ({
      t: (key: string, options?: Record<string, unknown>) => {
        const template = lookup(key) ?? key;
        if (!options) return template;
        return Object.entries(options).reduce(
          (acc, [name, value]) => acc.replace(`{{${name}}}`, String(value)),
          template
        );
      },
    }),
  };
});

vi.mock("../../api/preference-values", () => ({
  preferenceValuesApi: {
    effective: vi.fn(),
    patchLevel: vi.fn(),
  },
}));

import { preferenceValuesApi } from "../../api/preference-values";

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  const stored = serializeCardFieldConfigMap(defaultCardFieldConfigMap());
  vi.mocked(preferenceValuesApi.effective).mockResolvedValue({
    workspace_id: "ws-1",
    values: {
      [CARD_FIELDS_PREFERENCE_KEY]: { value: stored, source: "workspace" },
    },
  });
  vi.mocked(preferenceValuesApi.patchLevel).mockResolvedValue({
    scope: "workspace",
    workspace_id: "ws-1",
    values: {},
  });
});

function renderSection(): void {
  render(<CardFieldsSection workspaceId="ws-1" />);
}

describe("CardFieldsSection", () => {
  it("loads the stored configuration and saves an edited row count", async () => {
    renderSection();

    const rows = await screen.findByTestId("card-fields-rows");
    expect(rows).toHaveValue(2);

    fireEvent.change(rows, { target: { value: "3" } });
    fireEvent.click(screen.getByTestId("card-fields-save"));

    await waitFor(() =>
      expect(preferenceValuesApi.patchLevel).toHaveBeenCalled()
    );
    const [scope, values, workspaceId] = vi.mocked(
      preferenceValuesApi.patchLevel
    ).mock.calls[0];
    expect(scope).toBe("workspace");
    expect(workspaceId).toBe("ws-1");
    const serialized = (
      values as Record<string, string[]>
    )[CARD_FIELDS_PREFERENCE_KEY];
    const requirement = JSON.parse(serialized[0]) as CardFieldConfigMap["requirement"];
    expect(requirement.rows).toBe(3);
    expect(await screen.findByTestId("card-fields-saved")).toBeInTheDocument();
  });

  it("reorders fields through the move buttons", async () => {
    renderSection();
    await screen.findByTestId("card-fields-field-id");

    fireEvent.click(screen.getByTestId("card-fields-down-id"));
    fireEvent.click(screen.getByTestId("card-fields-save"));

    await waitFor(() =>
      expect(preferenceValuesApi.patchLevel).toHaveBeenCalled()
    );
    const values = vi.mocked(preferenceValuesApi.patchLevel).mock.calls[0][1] as Record<
      string,
      string[]
    >;
    const requirement = JSON.parse(
      values[CARD_FIELDS_PREFERENCE_KEY][0]
    ) as CardFieldConfigMap["requirement"];
    expect(requirement.fields[0].key).toBe("title");
    expect(requirement.fields[1].key).toBe("id");
  });

  it("does not allow hiding or removing the mandatory lock marker", async () => {
    renderSection();
    await screen.findByTestId("card-fields-field-lock");

    expect(screen.getByTestId("card-fields-visible-lock")).toBeDisabled();
    expect(screen.getByTestId("card-fields-remove-lock")).toBeDisabled();
    expect(screen.getByTestId("card-fields-mandatory-lock")).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("card-fields-visible-lock"));
    fireEvent.click(screen.getByTestId("card-fields-remove-lock"));

    expect(screen.getByTestId("card-fields-field-lock")).toBeInTheDocument();
  });

  it("switches between requirement and element cards", async () => {
    renderSection();
    await screen.findByTestId("card-fields-field-id");

    fireEvent.click(screen.getByTestId("card-fields-kind-element"));

    expect(screen.getByTestId("card-fields-kind-element")).toHaveAttribute(
      "aria-pressed",
      "true"
    );
    expect(screen.getByTestId("card-fields-field-type")).toBeInTheDocument();
  });
});
