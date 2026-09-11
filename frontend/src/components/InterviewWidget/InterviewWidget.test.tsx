/**
 * Interview-management web widget — quick entry point (plan Task 5 / 16).
 *
 * Since Task 16 the widget navigates instead of hosting a session, so every
 * render needs a router around it (`useNavigate`).
 */
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { InterviewWidget } from "./InterviewWidget";
import enLocale from "../../i18n/locales/en.json";

vi.mock("../../context/WorkspaceContext", () => ({
  useWorkspace: () => ({ activeWorkspace: { id: "ws-1", name: "WS" } }),
}));

// Plan Task 13 pins English copy ("Architecture Element"), so resolve keys
// against en.json instead of the de.json-based shared helper
// (src/test/i18n-test-helpers.ts) used by specs that assert German copy.
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => {
      const value = key
        .split(".")
        .reduce<unknown>(
          (node, segment) =>
            node && typeof node === "object"
              ? (node as Record<string, unknown>)[segment]
              : undefined,
          enLocale
        );
      return typeof value === "string" ? value : key;
    },
  }),
}));

// Factory vi.mock, same convention as InterviewChatPane.test.tsx (plan Task 8).
// Since Task 16 the widget must not call any of these at all -- they are
// mocked so "was never called" is an assertion, not an accident.
vi.mock("../../api/interviews", () => ({
  interviewsApi: {
    start: vi.fn(),
    getState: vi.fn(),
    propose: vi.fn(),
    formalize: vi.fn(),
  },
}));
import { interviewsApi } from "../../api/interviews";

/** The widget uses `useNavigate`, so it only mounts inside a router. */
function renderWidget(): ReturnType<typeof render> {
  return render(
    <MemoryRouter>
      <InterviewWidget />
    </MemoryRouter>
  );
}

describe("InterviewWidget", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("renders collapsed by default", () => {
    renderWidget();
    expect(screen.getByTestId("interview-widget-toggle")).toBeInTheDocument();
    expect(screen.queryByTestId("interview-widget-panel")).not.toBeInTheDocument();
  });

  it("expands on toggle click and persists the open state", () => {
    renderWidget();
    fireEvent.click(screen.getByTestId("interview-widget-toggle"));

    expect(screen.getByTestId("interview-widget-panel")).toBeInTheDocument();
    expect(localStorage.getItem("reqflow-interview-widget-open")).toBe("true");
  });

  it("renders expanded on mount when localStorage says open", () => {
    localStorage.setItem("reqflow-interview-widget-open", "true");
    renderWidget();
    expect(screen.getByTestId("interview-widget-panel")).toBeInTheDocument();
  });

  it("collapses on a second toggle click", () => {
    renderWidget();
    const toggle = screen.getByTestId("interview-widget-toggle");
    fireEvent.click(toggle);
    fireEvent.click(toggle);
    expect(screen.queryByTestId("interview-widget-panel")).not.toBeInTheDocument();
  });

  // Issue #679: direct `window.localStorage` access threw an unhandled
  // TypeError/SecurityError in storage-restricted environments (private
  // browsing, third-party-cookie lockouts, some JSDOM setups) and froze the
  // widget. `safeLocalStorage` must absorb that instead of crashing.
  describe("when localStorage access throws (issue #679)", () => {
    let originalLocalStorage: Storage;

    beforeEach(() => {
      originalLocalStorage = window.localStorage;
      Object.defineProperty(window, "localStorage", {
        configurable: true,
        value: {
          getItem: vi.fn(() => {
            throw new Error("SecurityError: localStorage access is blocked");
          }),
          setItem: vi.fn(() => {
            throw new Error("SecurityError: localStorage access is blocked");
          }),
        },
      });
    });

    afterEach(() => {
      Object.defineProperty(window, "localStorage", {
        configurable: true,
        value: originalLocalStorage,
      });
    });

    it("mounts and renders the collapsed toggle without crashing", () => {
      expect(() => renderWidget()).not.toThrow();
      expect(screen.getByTestId("interview-widget-toggle")).toBeInTheDocument();
      expect(screen.queryByTestId("interview-widget-panel")).not.toBeInTheDocument();
    });

    it("still expands on toggle click even though persisting the state fails", () => {
      renderWidget();
      const toggle = screen.getByTestId("interview-widget-toggle");
      expect(() => fireEvent.click(toggle)).not.toThrow();
      expect(screen.getByTestId("interview-widget-panel")).toBeInTheDocument();
    });
  });
});

describe("InterviewWidget multi entry", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
  });

  it("renders a 9th button for multi-mode discovery", () => {
    localStorage.setItem("reqflow-interview-widget-open", "true");
    renderWidget();
    expect(screen.getByTestId("interview-widget-start-multi")).toBeInTheDocument();
  });

  it("existing type buttons show translated labels, not raw type strings", () => {
    localStorage.setItem("reqflow-interview-widget-open", "true");
    renderWidget();
    expect(screen.getByText("Requirement")).toBeInTheDocument(); // en.json value happens to match the raw string for this one type
    expect(screen.queryByText("ArchitectureElement")).not.toBeInTheDocument(); // raw string must NOT appear
    expect(screen.getByText("Architecture Element")).toBeInTheDocument(); // translated value
  });
});

// Task 16 (spec L2.5): the widget is a quick entry point, not a session host.
describe("InterviewWidget hand-off to /interviews", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
  });

  function renderRouted(): ReturnType<typeof render> {
    return render(
      <MemoryRouter initialEntries={["/requirements"]}>
        <Routes>
          <Route path="/requirements" element={<InterviewWidget />} />
          <Route path="/interviews" element={<div data-testid="interviews-route" />} />
        </Routes>
      </MemoryRouter>
    );
  }

  it("navigates to the interviews route instead of hosting a session", async () => {
    renderRouted();

    fireEvent.click(screen.getByTestId("interview-widget-toggle"));
    fireEvent.click(screen.getByTestId("interview-widget-start-Risk"));

    expect(await screen.findByTestId("interviews-route")).toBeInTheDocument();
    // The widget must not start the session itself -- /interviews owns that,
    // so there is exactly one start path and one chat surface.
    expect(interviewsApi.start).not.toHaveBeenCalled();
  });

  it("routes the discovery entry point to ?start=multi", async () => {
    renderRouted();

    fireEvent.click(screen.getByTestId("interview-widget-toggle"));
    fireEvent.click(screen.getByTestId("interview-widget-start-multi"));

    expect(await screen.findByTestId("interviews-route")).toBeInTheDocument();
    expect(interviewsApi.start).not.toHaveBeenCalled();
  });

  it("closes the panel after navigating away", async () => {
    render(
      <MemoryRouter initialEntries={["/requirements"]}>
        <Routes>
          <Route path="/requirements" element={<InterviewWidget />} />
          <Route path="/interviews" element={<InterviewWidget />} />
        </Routes>
      </MemoryRouter>
    );

    fireEvent.click(screen.getByTestId("interview-widget-toggle"));
    fireEvent.click(screen.getByTestId("interview-widget-start-Adr"));

    await waitFor(() => {
      expect(screen.queryByTestId("interview-widget-panel")).not.toBeInTheDocument();
    });
    expect(localStorage.getItem("reqflow-interview-widget-open")).toBe("false");
  });

  it("renders no chat pane at all", () => {
    renderWidget();

    fireEvent.click(screen.getByTestId("interview-widget-toggle"));

    expect(screen.queryByTestId("interview-chat-input")).not.toBeInTheDocument();
    expect(screen.queryByTestId("interview-artifact-formalize")).not.toBeInTheDocument();
  });
});
