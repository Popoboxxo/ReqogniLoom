/**
 * Interview-management web widget — widget shell (plan Task 5).
 */
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { InterviewWidget } from "./InterviewWidget";
import type { InterviewState } from "../../api/interviews";
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
// `propose`/`formalize` are needed because a started multi-mode session mounts
// InterviewChatPane (whose effect fetches the pending proposal) and
// InterviewArtifactPane below it.
vi.mock("../../api/interviews", () => ({
  interviewsApi: {
    start: vi.fn(),
    getState: vi.fn(),
    propose: vi.fn(),
    formalize: vi.fn(),
  },
}));
import { interviewsApi } from "../../api/interviews";

describe("InterviewWidget", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("renders collapsed by default", () => {
    render(<InterviewWidget />);
    expect(screen.getByTestId("interview-widget-toggle")).toBeInTheDocument();
    expect(screen.queryByTestId("interview-widget-panel")).not.toBeInTheDocument();
  });

  it("expands on toggle click and persists the open state", () => {
    render(<InterviewWidget />);
    fireEvent.click(screen.getByTestId("interview-widget-toggle"));

    expect(screen.getByTestId("interview-widget-panel")).toBeInTheDocument();
    expect(localStorage.getItem("reqflow-interview-widget-open")).toBe("true");
  });

  it("renders expanded on mount when localStorage says open", () => {
    localStorage.setItem("reqflow-interview-widget-open", "true");
    render(<InterviewWidget />);
    expect(screen.getByTestId("interview-widget-panel")).toBeInTheDocument();
  });

  it("collapses on a second toggle click", () => {
    render(<InterviewWidget />);
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
      expect(() => render(<InterviewWidget />)).not.toThrow();
      expect(screen.getByTestId("interview-widget-toggle")).toBeInTheDocument();
      expect(screen.queryByTestId("interview-widget-panel")).not.toBeInTheDocument();
    });

    it("still expands on toggle click even though persisting the state fails", () => {
      render(<InterviewWidget />);
      const toggle = screen.getByTestId("interview-widget-toggle");
      expect(() => fireEvent.click(toggle)).not.toThrow();
      expect(screen.getByTestId("interview-widget-panel")).toBeInTheDocument();
    });
  });
});

function makeStartedSession(overrides: Partial<InterviewState> = {}): InterviewState {
  return {
    id: "s1",
    status: "in_progress",
    phase: "elicitation",
    collected_fields: {},
    missing_fields: [],
    // start() returns `{}`, not `{ candidates: [] }` (see api/interviews.ts).
    grounding_snapshot: {},
    transcript: [],
    ...overrides,
  };
}

describe("InterviewWidget multi entry", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
    // A started multi-mode session mounts InterviewChatPane, whose effect
    // fetches the pending proposal. A bare vi.fn() returns undefined and
    // breaks the pane's .then chain synchronously (outside its own .catch),
    // so default to "no proposal" like InterviewChatPane.test.tsx does.
    vi.mocked(interviewsApi.propose).mockResolvedValue({ proposal: null });
  });

  it("renders a 9th button for multi-mode discovery", () => {
    localStorage.setItem("reqflow-interview-widget-open", "true");
    render(<InterviewWidget />);
    expect(screen.getByTestId("interview-widget-start-multi")).toBeInTheDocument();
  });

  it("existing type buttons show translated labels, not raw type strings", () => {
    localStorage.setItem("reqflow-interview-widget-open", "true");
    render(<InterviewWidget />);
    expect(screen.getByText("Requirement")).toBeInTheDocument(); // en.json value happens to match the raw string for this one type
    expect(screen.queryByText("ArchitectureElement")).not.toBeInTheDocument(); // raw string must NOT appear
    expect(screen.getByText("Architecture Element")).toBeInTheDocument(); // translated value
  });

  it("clicking the multi button starts a session with session_kind=multi and null artifact_type", async () => {
    vi.mocked(interviewsApi.start).mockResolvedValue(makeStartedSession());
    localStorage.setItem("reqflow-interview-widget-open", "true");
    render(<InterviewWidget />);
    fireEvent.click(screen.getByTestId("interview-widget-start-multi"));
    await waitFor(() =>
      expect(interviewsApi.start).toHaveBeenCalledWith(expect.any(String), null, "multi")
    );
  });
});
