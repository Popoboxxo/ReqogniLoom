/**
 * Create-dialog field contract — GitHub #1393 (required marking) and #1392
 * (server length limits + field-bound 400 messages).
 *
 * WHY THIS FILE EXISTS
 * --------------------
 * Both defects are the same shape: the *mechanism* to render a required marker
 * and a `maxLength` already shipped inside `ArtifactForm` (#1192 field shell,
 * #1282 length feedback), but the create dialogs on 9 of 11 routes are bespoke
 * hand-written forms that read the attribute definition not at all. So the gap
 * was never in the renderer, it was in the seam: nothing forced a hand-written
 * dialog to consult the same contract.
 *
 * The fix introduces ONE shared seam — `useFieldContract` + `<FormField>` — and
 * these tests pin the two halves of it:
 *
 *   1. `FormField`/`RequiredMark` render a marker that exists as a DOM NODE
 *      (the previous marker was a CSS `::after`, i.e. invisible to
 *      `textContent` and to any measurement tooling).
 *   2. A real dialog (ADR) picks `required`/`aria-required`/`maxLength` off the
 *      server contract, and a 400 carrying `details[].field` puts the message
 *      next to the offending input instead of only in the generic banner.
 */

import React from "react";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { AttributeSpec } from "../api/attribute-definitions";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, fallback?: unknown) =>
      typeof fallback === "string" ? fallback : key,
    i18n: { language: "de" },
  }),
}));

const navigateMock = vi.fn();
vi.mock("react-router-dom", () => ({
  useParams: () => ({ id: undefined }),
  useNavigate: () => navigateMock,
}));

const useWorkspaceMock = vi.fn();
vi.mock("../context/WorkspaceContext", () => ({
  useWorkspace: () => useWorkspaceMock(),
  useOptionalWorkspace: () => useWorkspaceMock(),
}));

vi.mock("../hooks/useHasRole", () => ({
  useHasRole: () => () => true,
}));

// --- the two halves of the server contract --------------------------------

const getWorkspaceDefinitionMock = vi.fn();
vi.mock("../api/attribute-definitions", () => ({
  attributeDefinitionsApi: {
    getWorkspace: (...args: unknown[]) => getWorkspaceDefinitionMock(...args),
  },
}));

const getEffectiveCreateFormMock = vi.fn();
vi.mock("../api/create-form-config", () => ({
  createFormConfigApi: {
    getEffective: (...args: unknown[]) => getEffectiveCreateFormMock(...args),
  },
}));

vi.mock("../components/AdrEditors/useAdrData", () => ({
  useAdrData: () => ({
    items: [],
    item: null,
    isLoading: false,
    error: null,
    refresh: vi.fn(),
  }),
}));

const createMock = vi.fn();
vi.mock("../api/adrs", () => ({
  adrsApi: { create: (...args: unknown[]) => createMock(...args) },
}));

vi.mock("../components/AdrEditors/AdrList", () => ({ AdrList: () => null }));
vi.mock("../components/AdrEditors/AdrArtifactForm", () => ({
  AdrArtifactForm: () => null,
}));
vi.mock("../components/AdrEditors/AdrSupersedePanel", () => ({
  AdrSupersedePanel: () => null,
}));
vi.mock("../components/shared/ArtifactInspector", () => ({
  RightSidebar: () => null,
}));
vi.mock("../components/shared/TraceLinkPanel", () => ({
  TraceLinkPanel: () => null,
}));
vi.mock("../components/shared/useInterviewStartCta", () => ({
  useInterviewStartCta: () => ({ label: "Interview", onClick: () => {} }),
}));
vi.mock("../components/shared/TraceSpine", () => ({
  TraceSpine: () => null,
  useDerivationChain: () => ({
    stations: [],
    isLoading: false,
    error: null,
    isOpenable: () => false,
    resolveEntry: () => null,
  }),
}));

import AdrEditors from "../components/AdrEditors/AdrEditors";
import { NeedList } from "../components/NeedsEditors/NeedList";
import { FormField, RequiredMark } from "../components/shared/FormField";
import { useFieldContract } from "../hooks/useFieldContract";

const WS = { id: "ws-1", name: "WS", preset: "standard" };

/** One attribute of a resolved definition, with the server's own limits. */
function attribute(overrides: Partial<AttributeSpec> = {}): AttributeSpec {
  return {
    name: "title",
    kind: "core",
    type: "text",
    widget_key: null,
    fields: [],
    options: [],
    required: true,
    visible: true,
    locked: false,
    editable: true,
    section: "content",
    order: 1,
    label: { de: "Titel", en: "Title" },
    help_text: { de: "", en: "" },
    default: null,
    validation: { length: 200 },
    ai_elicit: false,
    export: true,
    audience: "all",
    ...overrides,
  } as AttributeSpec;
}

function resolvedDefinition(attributes: AttributeSpec[]) {
  return {
    item_type: "Adr",
    preset: "standard",
    is_customized: false,
    version: 1,
    attributes,
    origins: {},
    sections: [],
  };
}

describe("FormField + RequiredMark (GitHub #1393)", () => {
  it("renders the required marker as a real DOM node, not only a CSS ::after", () => {
    render(
      <FormField htmlFor="demo-title" label="Titel" required>
        <input id="demo-title" />
      </FormField>
    );

    const label = screen.getByText("Titel");
    // The marker is what an operator (and a measurement tool reading
    // textContent) can see; the old implementation was a `::after` on the
    // label class and therefore invisible to both.
    expect(label.textContent).toContain("*");
    expect(label.querySelector("[data-required-marker]")).not.toBeNull();
  });

  it("omits the marker for an optional field", () => {
    render(
      <FormField htmlFor="demo-notes" label="Notizen" required={false}>
        <input id="demo-notes" />
      </FormField>
    );

    expect(screen.getByText("Notizen").querySelector("[data-required-marker]")).toBeNull();
  });

  it("renders a field-bound error message with a stable test id", () => {
    render(
      <FormField
        htmlFor="demo-title"
        label="Titel"
        required
        error="Ensure this field has no more than 200 characters."
      >
        <input id="demo-title" />
      </FormField>
    );

    const error = screen.getByTestId("demo-title-error");
    expect(error).toHaveTextContent("no more than 200 characters");
    expect(error).toHaveAttribute("role", "alert");
  });

  it("exposes the marker on its own so ArtifactForm's FieldShell can reuse it", () => {
    const { container } = render(<RequiredMark />);
    const marker = container.querySelector("[data-required-marker]");
    expect(marker).not.toBeNull();
    expect(marker).toHaveAttribute("aria-hidden", "true");
    expect(marker?.textContent?.trim()).toBe("*");
  });

  // H4 (#1393 review): `role="alert"` announces the message ONCE. Without a
  // programmatic link, a user who refocuses the control hears nothing — the
  // association is what makes the message belong to the input.
  it("links the control to its error message (aria-describedby + aria-invalid)", () => {
    render(
      <FormField
        htmlFor="demo-title"
        label="Titel"
        required
        error="Ensure this field has no more than 200 characters."
      >
        <input id="demo-title" />
      </FormField>
    );

    const input = screen.getByRole("textbox");
    expect(input).toHaveAttribute("aria-describedby", "demo-title-error");
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(document.getElementById("demo-title-error")).toHaveTextContent(
      "no more than 200 characters"
    );
  });

  it("adds neither aria-describedby nor aria-invalid when there is no error", () => {
    render(
      <FormField htmlFor="demo-title" label="Titel" required>
        <input id="demo-title" />
      </FormField>
    );

    const input = screen.getByRole("textbox");
    expect(input).not.toHaveAttribute("aria-describedby");
    expect(input).not.toHaveAttribute("aria-invalid");
  });

  it("merges the error id into an aria-describedby the caller already set", () => {
    render(
      <FormField htmlFor="demo-title" label="Titel" required error="Zu lang.">
        <input id="demo-title" aria-describedby="demo-title-hint" />
      </FormField>
    );

    expect(screen.getByRole("textbox")).toHaveAttribute(
      "aria-describedby",
      "demo-title-hint demo-title-error"
    );
  });
});

describe("useFieldContract resolves the create-dialog contract (GitHub #1393/#1392)", () => {
  function Harness(): JSX.Element {
    const contract = useFieldContract("Adr", { enabled: true });
    const title = contract.field("title");
    return (
      <>
        <span data-testid="required">{String(title.required)}</span>
        <span data-testid="maxlength">{String(title.maxLength ?? "")}</span>
      </>
    );
  }

  beforeEach(() => {
    vi.clearAllMocks();
    useWorkspaceMock.mockReturnValue({ activeWorkspace: WS });
    getWorkspaceDefinitionMock.mockResolvedValue(resolvedDefinition([attribute()]));
    getEffectiveCreateFormMock.mockResolvedValue({
      item_type: "Adr",
      scope: "default",
      fields: [
        { field_key: "title", visible: true, required: true, order: 1, default: null },
      ],
      catalog: [],
    });
  });

  it("reads required and maxLength from the resolved attribute definition", async () => {
    render(<Harness />);

    await waitFor(() => expect(screen.getByTestId("required")).toHaveTextContent("true"));
    expect(screen.getByTestId("maxlength")).toHaveTextContent("200");
  });

  it("lets the create-form config override required (the #1263 authority)", async () => {
    getEffectiveCreateFormMock.mockResolvedValue({
      item_type: "Adr",
      scope: "workspace",
      fields: [
        { field_key: "title", visible: true, required: false, order: 1, default: null },
      ],
      catalog: [],
    });

    render(<Harness />);

    await waitFor(() => expect(screen.getByTestId("required")).toHaveTextContent("false"));
    // The length limit is unaffected by the required override — it belongs to
    // the attribute definition, not to the form definition.
    expect(screen.getByTestId("maxlength")).toHaveTextContent("200");
  });

  it("degrades to the attribute definition when the create-form config fails", async () => {
    getEffectiveCreateFormMock.mockRejectedValue(new Error("boom"));

    render(<Harness />);

    await waitFor(() => expect(screen.getByTestId("required")).toHaveTextContent("true"));
    expect(screen.getByTestId("maxlength")).toHaveTextContent("200");
  });
});

describe("ADR create dialog honours the contract (GitHub #1393/#1392)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    createMock.mockResolvedValue({ id: "adr-1" });
    useWorkspaceMock.mockReturnValue({ activeWorkspace: WS });
    getWorkspaceDefinitionMock.mockResolvedValue(resolvedDefinition([attribute()]));
    getEffectiveCreateFormMock.mockResolvedValue({
      item_type: "Adr",
      scope: "default",
      fields: [
        { field_key: "title", visible: true, required: true, order: 1, default: null },
      ],
      catalog: [],
    });
  });

  it("marks the title required and caps it at the server's 200 characters", async () => {
    const user = userEvent.setup();
    render(<AdrEditors />);

    await user.click(screen.getByTestId("create-adr-btn"));
    const input = screen.getByTestId("adr-new-title-input");

    await waitFor(() => expect(input).toHaveAttribute("aria-required", "true"));
    expect(input).toHaveAttribute("maxLength", "200");
    expect(screen.getByText("Title").textContent).toContain("*");
    // 400 characters pasted into a 200-char field is the measured #1392 case.
    expect((input as HTMLInputElement).maxLength).toBe(200);
  });

  it("surfaces a 400 field detail next to the title instead of only in the banner", async () => {
    const user = userEvent.setup();
    createMock.mockRejectedValue({
      error: {
        code: "VALIDATION_ERROR",
        message: "Validierung fehlgeschlagen.",
        details: [
          {
            field: "title",
            errors: ["Ensure this field has no more than 200 characters."],
          },
        ],
      },
    });

    render(<AdrEditors />);
    await user.click(screen.getByTestId("create-adr-btn"));
    await user.type(screen.getByTestId("adr-new-title-input"), "Irgendein Titel");
    await act(async () => {
      await user.click(screen.getByTestId("adr-new-save-btn"));
    });

    const fieldError = await screen.findByTestId("adr-new-title-error");
    expect(fieldError).toHaveTextContent("no more than 200 characters");
  });
});

/**
 * GitHub #1393 review follow-ups: the fallback/static path, the "closed dialog
 * costs no request" promise, and the contract's survival across a close/re-open
 * (H3). The static path is what `DiagramCreateForm` uses — `Diagram` is not an
 * attribute-catalogue item type, so `field()` can ONLY be right if
 * `staticContracts` is honoured.
 */
describe("useFieldContract static contract + no-request paths (#1393 review)", () => {
  function StaticHarness(): JSX.Element {
    const { field } = useFieldContract(null, {
      enabled: false,
      staticContracts: { name: { required: true, maxLength: 500 } },
    });
    const name = field("name");
    return (
      <>
        <span data-testid="required">{String(name.required)}</span>
        <span data-testid="maxlength">{String(name.maxLength ?? "")}</span>
        <span data-testid="control-maxlength">{String(name.controlProps.maxLength)}</span>
        <span data-testid="select-maxlength">{String(name.selectProps.maxLength)}</span>
      </>
    );
  }

  function EnabledHarness({ enabled }: { enabled: boolean }): JSX.Element {
    const { field } = useFieldContract("Adr", { enabled });
    return <span data-testid="required">{String(field("title").required)}</span>;
  }

  beforeEach(() => {
    vi.clearAllMocks();
    useWorkspaceMock.mockReturnValue({ activeWorkspace: WS });
    getWorkspaceDefinitionMock.mockResolvedValue(resolvedDefinition([attribute()]));
    getEffectiveCreateFormMock.mockResolvedValue({
      item_type: "Adr",
      scope: "default",
      fields: [
        { field_key: "title", visible: true, required: true, order: 1, default: null },
      ],
      catalog: [],
    });
  });

  it("resolves a static contract for an item type the catalogue does not cover", () => {
    render(<StaticHarness />);

    expect(screen.getByTestId("required")).toHaveTextContent("true");
    expect(screen.getByTestId("maxlength")).toHaveTextContent("500");
    // A select has no `maxlength` attribute — the contract exposes a separate
    // prop bag so no future enum can leak one onto a `<select>` (M5).
    expect(screen.getByTestId("control-maxlength")).toHaveTextContent("500");
    expect(screen.getByTestId("select-maxlength")).toHaveTextContent("undefined");
    // No server source can answer for `Diagram`, and the disabled hook must not
    // ask anyway.
    expect(getWorkspaceDefinitionMock).not.toHaveBeenCalled();
    expect(getEffectiveCreateFormMock).not.toHaveBeenCalled();
  });

  it("issues no request while the dialog is closed (enabled: false)", () => {
    render(<EnabledHarness enabled={false} />);

    expect(getWorkspaceDefinitionMock).not.toHaveBeenCalled();
    expect(getEffectiveCreateFormMock).not.toHaveBeenCalled();
  });

  it("keeps the resolved contract across a close/re-open (H3)", async () => {
    const { rerender } = render(<EnabledHarness enabled />);
    await waitFor(() => expect(screen.getByTestId("required")).toHaveTextContent("true"));

    // Close: the contract must NOT be nulled, otherwise every re-open starts
    // contract-less (#1392's "400 chars into a 200 field" window).
    await act(async () => {
      rerender(<EnabledHarness enabled={false} />);
    });
    expect(screen.getByTestId("required")).toHaveTextContent("true");

    // Re-open: still known before the refetch resolves.
    await act(async () => {
      rerender(<EnabledHarness enabled />);
    });
    expect(screen.getByTestId("required")).toHaveTextContent("true");
  });
});

/**
 * N1 (re-opened #1392): `StakeholderNeed.category` is a `<input type="text">`
 * whose contract was spread from `selectProps` — the prop bag that
 * deliberately omits `maxLength`. The server publishes 64 characters
 * (`CharField(max_length=64)`); without the attribute the field accepted a
 * value it could only learn was invalid from a 400.
 */
describe("Need create dialog caps category at the server's length (N1/#1392)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useWorkspaceMock.mockReturnValue({ activeWorkspace: WS });
    getWorkspaceDefinitionMock.mockResolvedValue(
      resolvedDefinition([
        attribute({ name: "title", label: { de: "Titel", en: "Title" }, validation: { length: 500 } }),
        attribute({
          name: "category",
          required: false,
          label: { de: "Kategorie", en: "Category" },
          validation: { length: 64 },
        }),
      ])
    );
    getEffectiveCreateFormMock.mockResolvedValue({
      item_type: "StakeholderNeed",
      scope: "default",
      fields: [],
      catalog: [],
    });
  });

  it("carries maxlength=64 on need.category", async () => {
    render(
      <NeedList
        needs={[]}
        showCreateForm
        setShowCreateForm={vi.fn()}
        newTitle=""
        setNewTitle={vi.fn()}
        newDescription=""
        setNewDescription={vi.fn()}
        newCategory=""
        setNewCategory={vi.fn()}
        onSubmitCreate={vi.fn()}
      />
    );

    const input = screen.getByTestId("need-new-category-input");
    await waitFor(() => expect(input).toHaveAttribute("maxlength", "64"));
    expect((input as HTMLInputElement).maxLength).toBe(64);

    const title = screen.getByTestId("need-new-title-input");
    await waitFor(() => expect(title).toHaveAttribute("maxlength", "500"));
  });
});

/**
 * N2 (remaining half of the #1393 review's F3): the resolved *form* definition
 * must survive a close/re-open, just like the attribute definition (H3). It
 * outranks the attribute definition in `useFieldContract`, so nulling it on
 * `enabled: false` made a field required only by the form definition lose its
 * marker until the refetch resolved.
 */
describe("useCreateFormFields keeps the form definition across close/re-open (N2)", () => {
  function FormDefinitionHarness({ enabled }: { enabled: boolean }): JSX.Element {
    const { field } = useFieldContract("Adr", { enabled });
    return <span data-testid="required">{String(field("title").required)}</span>;
  }

  beforeEach(() => {
    vi.clearAllMocks();
    useWorkspaceMock.mockReturnValue({ activeWorkspace: WS });
    // The attribute alone says "optional"…
    getWorkspaceDefinitionMock.mockResolvedValue(
      resolvedDefinition([attribute({ required: false })])
    );
    // …so only the form definition can produce the marker.
    getEffectiveCreateFormMock.mockResolvedValue({
      item_type: "Adr",
      scope: "default",
      fields: [
        { field_key: "title", visible: true, required: true, order: 1, default: null },
      ],
      catalog: [],
    });
  });

  it("keeps the form definition's required flag while the dialog is closed", async () => {
    const { rerender } = render(<FormDefinitionHarness enabled />);
    await waitFor(() => expect(getEffectiveCreateFormMock).toHaveBeenCalled());
    await waitFor(() => expect(screen.getByTestId("required")).toHaveTextContent("true"));

    // Close — the form definition must stay resolved.
    await act(async () => {
      rerender(<FormDefinitionHarness enabled={false} />);
    });
    expect(screen.getByTestId("required")).toHaveTextContent("true");

    // Re-open — still required before the refetch settles.
    await act(async () => {
      rerender(<FormDefinitionHarness enabled />);
    });
    expect(screen.getByTestId("required")).toHaveTextContent("true");
  });
});
