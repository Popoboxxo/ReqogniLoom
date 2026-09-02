/**
 * Unit test for `useInterviewStartCta` (issue #798).
 *
 * The CTA navigates to `/interviews?start=<type>` — an interview-assisted
 * workflow, not an in-place form dialog. The label used to read "Im Dialog
 * erstellen" (DE) / "Create via guided dialog" (EN), which implied a modal
 * form like the primary "+ New X" action opens, and the DE/EN wording
 * diverged ("Dialog" vs "guided dialog"). This asserts the label names the
 * actual mechanism (interview) and is aligned across locales.
 */
import { describe, it, expect, vi } from "vitest";
import { renderHook } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import deLocale from "../../i18n/locales/de.json";
import enLocale from "../../i18n/locales/en.json";

vi.mock("../../context/WorkspaceContext", () => ({
  useWorkspace: () => ({ activeWorkspace: { id: "ws-001", name: "WS" } }),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

// Must import AFTER vi.mock
import { useInterviewStartCta } from "./useInterviewStartCta";

describe("useInterviewStartCta (#798)", () => {
  it("labels the CTA after the interview mechanism, not a generic dialog", () => {
    const { result } = renderHook(() => useInterviewStartCta("Requirement"), {
      wrapper: MemoryRouter,
    });

    expect(result.current.label).toBe("interviews.startCta");
    // Real DE/EN copy must both name "interview" explicitly and must not
    // reintroduce the misleading "dialog"-only wording.
    expect(deLocale.interviews.startCta).toMatch(/interview/i);
    expect(enLocale.interviews.startCta).toMatch(/interview/i);
  });

  it("keeps the interview-start-cta test id and the /interviews?start= route", () => {
    const { result } = renderHook(() => useInterviewStartCta("Requirement"), {
      wrapper: MemoryRouter,
    });

    expect(result.current.testId).toBe("interview-start-cta");
  });
});
