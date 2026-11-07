/**
 * P2 Task 2.10 — TierLadderSection behaviour.
 *
 * Covers the editor contract: the loaded ladder renders with its rules, a
 * rename/add/remove is sent as a full PUT, a rejected save is surfaced inline
 * while the draft survives, a non-admin gets a read-only surface, and the
 * "three names" shortcut produces exactly the `erste`/`dazwischen`/`letzte`
 * ladder the backend's `apply_three_names` writes.
 */

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

import { TierLadderSection } from "./TierLadderSection";
import { tiersApi, type TierEntry } from "../../api/tiers";

vi.mock("../../api/tiers", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/tiers")>();
  return {
    ...actual,
    tiersApi: { get: vi.fn(), replace: vi.fn() },
  };
});

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: unknown): string =>
      typeof options === "string" ? options : key,
    i18n: { language: "de" },
  }),
}));

const DEFAULT_TIERS: TierEntry[] = [
  {
    tier_key: "erste",
    name: { de: "Erste", en: "First" },
    position: 0,
    rule: "first",
    from_end: null,
    level: 1,
  },
  {
    tier_key: "dazwischen",
    name: { de: "Dazwischen", en: "Middle" },
    position: 1,
    rule: "middle",
    from_end: null,
    level: 2,
  },
  {
    tier_key: "vorletzte",
    name: { de: "Vorletzte", en: "Second to last" },
    position: 2,
    rule: "from_end",
    from_end: 1,
    level: 3,
  },
  {
    tier_key: "letzte",
    name: { de: "Letzte", en: "Last" },
    position: 3,
    rule: "from_end",
    from_end: 0,
    level: 4,
  },
];

/** Answer a PUT the way the server does: derived position/level, same order. */
function serverEcho(tiers: Parameters<typeof tiersApi.replace>[1]) {
  return {
    workspace_id: "ws-1",
    tiers: tiers.map((tier, index) => ({
      ...tier,
      position: index,
      level: index + 1,
    })),
  };
}

describe("TierLadderSection", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(tiersApi.get).mockResolvedValue({
      workspace_id: "ws-1",
      tiers: DEFAULT_TIERS,
    });
    vi.mocked(tiersApi.replace).mockImplementation(async (_id, tiers) =>
      serverEcho(tiers)
    );
  });

  it("renders the loaded ladder with its rules and from_end heights", async () => {
    render(<TierLadderSection workspaceId="ws-1" />);

    expect(await screen.findByTestId("tier-row-erste")).toBeInTheDocument();
    expect(screen.getAllByTestId(/^tier-row-/)).toHaveLength(4);
    expect(screen.getByTestId("tier-name-de-erste")).toHaveValue("Erste");
    expect(screen.getByTestId("tier-name-en-erste")).toHaveValue("First");
    expect(screen.getByTestId("tier-rule-erste")).toHaveValue("first");
    // `from_end` is only meaningful for that rule — no input elsewhere.
    expect(screen.queryByTestId("tier-from-end-erste")).not.toBeInTheDocument();
    expect(screen.getByTestId("tier-from-end-vorletzte")).toHaveValue(1);
    expect(screen.getByTestId("tier-from-end-letzte")).toHaveValue(0);
  });

  it("renames a tier and saves the whole ladder", async () => {
    render(<TierLadderSection workspaceId="ws-1" />);
    await screen.findByTestId("tier-row-erste");

    fireEvent.change(screen.getByTestId("tier-name-de-erste"), {
      target: { value: "Oberste" },
    });
    fireEvent.click(screen.getByTestId("tier-save-button"));

    await waitFor(() => expect(tiersApi.replace).toHaveBeenCalledTimes(1));
    const [workspaceId, body] = vi.mocked(tiersApi.replace).mock.calls[0];
    expect(workspaceId).toBe("ws-1");
    expect(body).toHaveLength(4);
    expect(body[0]).toEqual({
      tier_key: "erste",
      name: { de: "Oberste", en: "First" },
      rule: "first",
      from_end: null,
    });
    expect(await screen.findByTestId("tier-ladder-saved")).toBeInTheDocument();
  });

  it("adds a new tier as the next free from_end position", async () => {
    render(<TierLadderSection workspaceId="ws-1" />);
    await screen.findByTestId("tier-row-erste");

    fireEvent.click(screen.getByTestId("tier-add-button"));

    expect(screen.getByTestId("tier-row-tier_5")).toBeInTheDocument();
    expect(screen.getByTestId("tier-rule-tier_5")).toHaveValue("from_end");
    expect(screen.getByTestId("tier-from-end-tier_5")).toHaveValue(2);

    fireEvent.click(screen.getByTestId("tier-save-button"));
    await waitFor(() => expect(tiersApi.replace).toHaveBeenCalledTimes(1));

    const [, body] = vi.mocked(tiersApi.replace).mock.calls[0];
    expect(body).toHaveLength(5);
    expect(body[4]).toMatchObject({
      tier_key: "tier_5",
      rule: "from_end",
      from_end: 2,
    });
  });

  it("removes a tier from the draft and saves the reduced ladder", async () => {
    render(<TierLadderSection workspaceId="ws-1" />);
    await screen.findByTestId("tier-row-dazwischen");

    fireEvent.click(screen.getByTestId("tier-remove-dazwischen"));
    expect(screen.queryByTestId("tier-row-dazwischen")).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId("tier-save-button"));
    await waitFor(() => expect(tiersApi.replace).toHaveBeenCalledTimes(1));

    const [, body] = vi.mocked(tiersApi.replace).mock.calls[0];
    expect(body.map((tier) => tier.tier_key)).toEqual([
      "erste",
      "vorletzte",
      "letzte",
    ]);
  });

  it("reorders the ladder in the draft and saves the new order", async () => {
    render(<TierLadderSection workspaceId="ws-1" />);
    await screen.findByTestId("tier-row-vorletzte");

    fireEvent.click(screen.getByTestId("tier-up-vorletzte"));
    fireEvent.click(screen.getByTestId("tier-save-button"));

    await waitFor(() => expect(tiersApi.replace).toHaveBeenCalledTimes(1));
    const [, body] = vi.mocked(tiersApi.replace).mock.calls[0];
    expect(body.map((tier) => tier.tier_key)).toEqual([
      "erste",
      "vorletzte",
      "dazwischen",
      "letzte",
    ]);
  });

  it("shows a rejected save inline and keeps the draft", async () => {
    vi.mocked(tiersApi.replace).mockRejectedValue({
      error: { message: "The ladder needs exactly one 'first' tier." },
    });
    render(<TierLadderSection workspaceId="ws-1" />);
    await screen.findByTestId("tier-row-erste");

    fireEvent.change(screen.getByTestId("tier-name-de-erste"), {
      target: { value: "Oberste" },
    });
    fireEvent.click(screen.getByTestId("tier-save-button"));

    const alert = await screen.findByTestId("tier-ladder-error");
    expect(alert).toHaveTextContent("The ladder needs exactly one 'first' tier.");
    expect(alert).toHaveAttribute("role", "alert");
    // The edit is not thrown away: the admin can correct and retry.
    expect(screen.getByTestId("tier-name-de-erste")).toHaveValue("Oberste");
    expect(screen.queryByTestId("tier-ladder-saved")).not.toBeInTheDocument();
  });

  it("is read-only for a non-admin", async () => {
    render(<TierLadderSection workspaceId="ws-1" readOnly />);
    await screen.findByTestId("tier-row-erste");

    expect(screen.getByTestId("tier-ladder-readonly")).toBeInTheDocument();
    expect(screen.getByTestId("tier-name-de-erste")).toBeDisabled();
    expect(screen.getByTestId("tier-rule-erste")).toBeDisabled();
    expect(screen.getByTestId("tier-add-button")).toBeDisabled();
    expect(screen.getByTestId("tier-save-button")).toBeDisabled();
    expect(screen.getByTestId("tier-remove-erste")).toBeDisabled();

    fireEvent.click(screen.getByTestId("tier-save-button"));
    expect(tiersApi.replace).not.toHaveBeenCalled();
  });

  it("builds the three-name ladder (erste/dazwischen/letzte)", async () => {
    render(<TierLadderSection workspaceId="ws-1" />);
    await screen.findByTestId("tier-row-erste");

    fireEvent.change(screen.getByTestId("tier-three-name-erste"), {
      target: { value: "Top" },
    });
    fireEvent.change(screen.getByTestId("tier-three-name-dazwischen"), {
      target: { value: "Mid" },
    });
    fireEvent.change(screen.getByTestId("tier-three-name-letzte"), {
      target: { value: "Bottom" },
    });
    fireEvent.click(screen.getByTestId("tier-three-names-apply"));

    // Exactly three positions remain; the extra default tier is gone.
    expect(screen.queryByTestId("tier-row-vorletzte")).not.toBeInTheDocument();
    expect(screen.getAllByTestId(/^tier-row-/)).toHaveLength(3);
    expect(screen.getByTestId("tier-rule-dazwischen")).toHaveValue("middle");
    expect(screen.getByTestId("tier-from-end-letzte")).toHaveValue(0);

    fireEvent.click(screen.getByTestId("tier-save-button"));
    await waitFor(() => expect(tiersApi.replace).toHaveBeenCalledTimes(1));

    const [, body] = vi.mocked(tiersApi.replace).mock.calls[0];
    expect(body).toEqual([
      {
        tier_key: "erste",
        name: { de: "Top", en: "Top" },
        rule: "first",
        from_end: null,
      },
      {
        tier_key: "dazwischen",
        name: { de: "Mid", en: "Mid" },
        rule: "middle",
        from_end: null,
      },
      {
        tier_key: "letzte",
        name: { de: "Bottom", en: "Bottom" },
        rule: "from_end",
        from_end: 0,
      },
    ]);
  });
});
