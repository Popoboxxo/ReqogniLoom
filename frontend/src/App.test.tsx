/**
 * ARCH-L1-001 ReactFrontend — CSRF-cookie-unreachable banner (systemaudit
 * 2026-09-03, Task 2 / R2).
 *
 * Root cause (Task 1) was fixed backend-side: a production deployment over
 * plain HTTP silently drops the CSRF cookie, so every write from the UI
 * 403s. This is the frontend safety net — warn the user visibly instead of
 * a confusing 403 on their next click.
 *
 * Tests `CsrfCookieWarning` directly rather than the full `AppInner` tree:
 * `AppInner` also mounts `NavigationShell` (needs a Router) and the
 * Theme/Workspace providers (fire real network calls on mount), none of
 * which are relevant to this banner's logic. `CsrfCookieWarning` is the
 * self-contained piece that owns the effect and the rendered warning.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { CsrfCookieWarning } from "./App";

vi.mock("./context/AuthContext", () => ({
  useAuth: () => ({ status: "authenticated", user: { id: "1" }, roles: ["editor"] }),
}));

describe("CSRF-cookie-unreachable banner", () => {
  it("shows a warning when logged in over http with no csrftoken cookie", () => {
    Object.defineProperty(window, "location", {
      value: { protocol: "http:" },
      writable: true,
    });
    Object.defineProperty(document, "cookie", { value: "", writable: true });
    render(<CsrfCookieWarning />);
    expect(screen.getByText(/ohne TLS erreichbar/i)).toBeInTheDocument();
  });

  it("stays silent over https", () => {
    Object.defineProperty(window, "location", {
      value: { protocol: "https:" },
      writable: true,
    });
    Object.defineProperty(document, "cookie", { value: "", writable: true });
    render(<CsrfCookieWarning />);
    expect(screen.queryByText(/ohne TLS erreichbar/i)).not.toBeInTheDocument();
  });

  it("stays silent when the csrftoken cookie is present", () => {
    Object.defineProperty(window, "location", {
      value: { protocol: "http:" },
      writable: true,
    });
    Object.defineProperty(document, "cookie", {
      value: "csrftoken=abc123",
      writable: true,
    });
    render(<CsrfCookieWarning />);
    expect(screen.queryByText(/ohne TLS erreichbar/i)).not.toBeInTheDocument();
  });
});
