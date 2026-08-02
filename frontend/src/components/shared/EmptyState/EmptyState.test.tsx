/**
 * <EmptyState> unit tests — UI concept ch. 12.7 and 13.1.
 *
 * One test per obligation of the contract:
 *   - `no-match` offers "Filter zurücksetzen" and nothing else — in
 *     particular no create action
 *   - `loading` renders nothing before 300 ms, then the placeholder
 *   - `error` renders `role="alert"`
 *   - `empty` renders its actions
 *   - `forbidden` names the missing role
 *   - `filled` renders nothing
 */

import type { ComponentProps } from "react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

// The shared i18next instance is not initialised in unit tests; keep the
// literal default of every t(key, default, params?) call, with a minimal
// {{placeholder}} interpolation so the `forbidden` variant stays readable.
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (_key: string, fallback?: string, params?: Record<string, string>) => {
      if (!fallback) return _key;
      if (!params) return fallback;
      return Object.entries(params).reduce(
        (acc, [name, value]) => acc.replace(`{{${name}}}`, value),
        fallback,
      );
    },
    i18n: { language: "de", changeLanguage: vi.fn() },
  }),
}));

import { EmptyState } from "./EmptyState";

describe("<EmptyState> — UI concept ch. 12.7 and 13.1", () => {
  describe("no-match", () => {
    it("offers 'Filter zurücksetzen' and no create action", async () => {
      const user = userEvent.setup();
      const onResetFilters = vi.fn();
      render(<EmptyState variant="no-match" onResetFilters={onResetFilters} />);

      const buttons = screen.getAllByRole("button");
      expect(buttons).toHaveLength(1);
      expect(buttons[0]).toHaveTextContent("Filter zurücksetzen");

      expect(
        screen.queryByRole("button", { name: /neu|anlegen|erstellen|import/i }),
      ).not.toBeInTheDocument();

      await user.click(buttons[0]);
      expect(onResetFilters).toHaveBeenCalledTimes(1);
    });

    it("has no way to accept a create action at all (type-level contract)", () => {
      const props: ComponentProps<typeof EmptyState> = {
        variant: "no-match",
        onResetFilters: vi.fn(),
        // @ts-expect-error — `actions` does not exist on the no-match variant.
        actions: [{ label: "Neu anlegen", onClick: vi.fn() }],
      };
      expect(props.variant).toBe("no-match");
    });
  });

  describe("loading", () => {
    beforeEach(() => {
      vi.useFakeTimers();
    });

    afterEach(() => {
      vi.useRealTimers();
    });

    it("renders nothing before 300 ms", () => {
      const { container } = render(<EmptyState variant="loading" />);

      vi.advanceTimersByTime(299);
      expect(container).toBeEmptyDOMElement();
    });

    it("renders the placeholder from 300 ms onward", () => {
      render(<EmptyState variant="loading" label="Requirements werden geladen" />);

      act(() => {
        vi.advanceTimersByTime(300);
      });
      expect(
        screen.getByRole("status", { name: "Requirements werden geladen" }),
      ).toBeInTheDocument();
    });
  });

  describe("error", () => {
    it("renders role=\"alert\" and a retry action", async () => {
      const user = userEvent.setup();
      const onRetry = vi.fn();
      render(
        <EmptyState
          variant="error"
          title="Requirement konnte nicht gespeichert werden"
          description="Der Titel ist bereits vergeben."
          onRetry={onRetry}
        />,
      );

      const alert = screen.getByRole("alert");
      expect(alert).toHaveTextContent("Requirement konnte nicht gespeichert werden");

      await user.click(screen.getByRole("button", { name: "Erneut versuchen" }));
      expect(onRetry).toHaveBeenCalledTimes(1);
    });
  });

  describe("empty", () => {
    it("renders title, description and the given actions", async () => {
      const user = userEvent.setup();
      const onCreate = vi.fn();
      const onImport = vi.fn();
      render(
        <EmptyState
          variant="empty"
          title="Noch keine Requirements"
          description="Leg das erste an oder übernimm einen bestehenden Bestand."
          actions={[
            { label: "Neues Requirement", onClick: onCreate },
            { label: "CSV importieren", onClick: onImport },
          ]}
        />,
      );

      expect(screen.getByText("Noch keine Requirements")).toBeInTheDocument();
      await user.click(screen.getByRole("button", { name: "Neues Requirement" }));
      expect(onCreate).toHaveBeenCalledTimes(1);

      await user.click(screen.getByRole("button", { name: "CSV importieren" }));
      expect(onImport).toHaveBeenCalledTimes(1);
    });
  });

  describe("forbidden", () => {
    it("names the required role and who can grant it", () => {
      render(
        <EmptyState
          variant="forbidden"
          requiredRole="Editor"
          grantedBy="Wende dich an den Workspace-Administrator."
        />,
      );

      expect(screen.getByText(/Editor/)).toBeInTheDocument();
      expect(
        screen.getByText("Wende dich an den Workspace-Administrator."),
      ).toBeInTheDocument();
    });
  });

  describe("filled", () => {
    it("renders nothing", () => {
      const { container } = render(<EmptyState variant="filled" />);
      expect(container).toBeEmptyDOMElement();
    });
  });
});
