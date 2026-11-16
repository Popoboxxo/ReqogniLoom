/** Visible offline/update notices (plan M2, REQ-214). */
import { act, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { PwaNotices } from "../components/shared/PwaNotices/PwaNotices";
import { registerPwa } from "../pwa/register";
import { triggerNeedRefresh } from "./mocks/pwa-register";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (_key: string, fallback?: string) => fallback ?? _key }),
}));

describe("PwaNotices", () => {
  beforeEach(() => {
    registerPwa();
  });

  it("shows the offline banner while the browser is offline", () => {
    render(<PwaNotices />);
    expect(screen.queryByTestId("offline-notice")).toBeNull();
    act(() => {
      window.dispatchEvent(new Event("offline"));
    });
    expect(screen.getByTestId("offline-notice")).toBeTruthy();
    act(() => {
      window.dispatchEvent(new Event("online"));
    });
    expect(screen.queryByTestId("offline-notice")).toBeNull();
  });

  it("asks before applying a service-worker update", () => {
    render(<PwaNotices />);
    expect(screen.queryByTestId("pwa-update-banner")).toBeNull();
    act(() => {
      triggerNeedRefresh();
    });
    expect(screen.getByTestId("pwa-update-banner")).toBeTruthy();
    expect(screen.getByTestId("pwa-update-apply")).toBeTruthy();
  });
});
