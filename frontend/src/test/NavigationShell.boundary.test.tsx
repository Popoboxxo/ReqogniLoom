/**
 * R2F-008 regression guard: an error in a shell-level child (sidebar, main
 * layout, interview widget) must be caught by the OUTER ErrorBoundary instead
 * of blanking the whole authenticated app. The narrow route-level boundary
 * inside <main> is intentionally kept for route-local failures.
 */
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { resolveLocaleKey } from "./i18n-test-helpers";
import { NavigationShell } from "../components/NavigationShell/NavigationShell";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => resolveLocaleKey(key) ?? key,
    i18n: { language: "de" },
  }),
}));

vi.mock("../context/AuthContext", () => ({
  useAuth: () => ({
    isAuthenticated: true,
    status: "authenticated",
    user: { id: "1" },
  }),
}));

// Keep unrelated shell children inert so the only failing child is the widget.
vi.mock("../components/NavigationShell/SidebarNavigation", () => ({
  SidebarNavigation: () => <div data-testid="sidebar-stub" />,
}));
vi.mock("../components/NavigationShell/BannerStack", () => ({
  BannerStack: () => null,
}));
vi.mock("../components/DashboardViews/DashboardViews", () => ({
  default: () => <div data-testid="dashboard-stub" />,
}));

vi.mock("../components/InterviewWidget/InterviewWidget", () => ({
  InterviewWidget: () => {
    throw new Error("widget exploded");
  },
}));

describe("NavigationShell shell-level error boundary (R2F-008)", () => {
  beforeEach(() => {
    vi.spyOn(console, "error").mockImplementation(() => {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows the localized error UI instead of a blank page when the widget throws", () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <NavigationShell />
      </MemoryRouter>
    );

    expect(
      screen.getByText(resolveLocaleKey("errors.generic") ?? "errors.generic")
    ).toBeInTheDocument();
    expect(
      screen.getByText(resolveLocaleKey("errors.boundaryHint") ?? "errors.boundaryHint")
    ).toBeInTheDocument();
    expect(screen.getByTestId("error-reference")).toBeInTheDocument();
    expect(screen.getByTestId("error-reload-btn")).toBeInTheDocument();
  });
});
